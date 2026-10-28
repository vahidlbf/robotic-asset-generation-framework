"""First real robot motion: Franka home -> PET pre-grasp -> home, planned with cuMotion and executed in PhysX.

    "$ISAACSIM_PYTHON" scripts/motion_planning/run_motion_experiment.py --headless   # Mode A
    "$ISAACSIM_PYTHON" scripts/motion_planning/run_motion_experiment.py              # Mode B (GUI)

Both modes run identical planning and control code (control in the PhysX post-step callback). GUI mode adds a
target marker and the planned TCP path (debug draw) and keeps the window open, paused, after the run.
No grasping, no gripper actuation, no change to the workstation layout or physics properties. Test-only
instrumentation (contact-report APIs, sleeping disabled on the robot) is authored in the session layer.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class GpuMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop_flag = [], False

    def run(self):
        while not self.stop_flag:
            try:
                o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
                self.samples.append(tuple(int(x) for x in o.split(",")))
            except Exception:
                pass
            time.sleep(1.0)


def main(argv=None, app=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--config", default="config/motion_planning.json")
    ap.add_argument("--exit-when-done", action="store_true", help="GUI mode: close the window after the run")
    args, _ = ap.parse_known_args(argv)

    import motion_utils as mu

    mc, wc = mu.load_configs(args.config)
    out_dir = os.path.join(mu.ROOT, mc["logs_dir"]) if args.headless else os.path.join(mu.ROOT, mc["logs_dir"], "gui")
    os.makedirs(out_dir, exist_ok=True)
    logf = open(os.path.join(out_dir, "execution.log" if not args.plan_only else "planning_only.log"), "w")

    def log(*a):
        s = " ".join(str(x) for x in a)
        print(s, flush=True)
        logf.write(s + "\n")
        logf.flush()

    gpu = GpuMonitor()
    gpu.start()
    t_wall0 = time.time()
    import numpy as np
    from pxr import PhysxSchema, Usd, UsdGeom, UsdPhysics
    import isaacsim.core.experimental.utils.app as app_utils
    import isaacsim.core.experimental.utils.stage as stage_utils
    from isaacsim.core.experimental.prims import Articulation, RigidPrim
    from isaacsim.core.simulation_manager import SimulationManager

    import plan_to_pet as ptp
    import validate_motion as vm
    from execute_trajectory import Executor

    log(f"[motion] mode={'headless' if args.headless else 'gui'} plan_only={args.plan_only}")
    log("[motion] extensions:", mu.enable_motion_extensions(app))
    scene = os.path.join(mu.ROOT, wc["paths"]["scene"])
    scene_mtime = os.path.getmtime(scene)
    ok, stage = stage_utils.open_stage(scene)
    while stage_utils.is_stage_loading():
        app.update()
    stage = stage_utils.get_current_stage()
    rpath = wc["robot"]["mount_prim"] + "/" + wc["robot"]["prim_name"]
    if SimulationManager.get_active_physics_engine() != "physx":
        SimulationManager.switch_physics_engine("physx")

    art = Articulation(rpath)
    link_paths = list(art.link_paths[0]) if isinstance(art.link_paths[0], (list, tuple)) else list(art.link_paths)
    link_names = [p.split("/")[-1] for p in link_paths]
    hand_path = next(p for p in link_paths if p.endswith("panda_hand"))
    obstacles = mu.collect_obstacle_prims(stage, rpath)
    root_prim = stage.GetPrimAtPath(rpath)
    self_coll = PhysxSchema.PhysxArticulationAPI(root_prim).GetEnabledSelfCollisionsAttr().Get() if root_prim.HasAPI(PhysxSchema.PhysxArticulationAPI) else None
    with Usd.EditContext(stage, stage.GetSessionLayer()):  # test instrumentation only (never saved)
        for p in link_paths:
            PhysxSchema.PhysxContactReportAPI.Apply(stage.GetPrimAtPath(p)).CreateThresholdAttr(0.0)
        PhysxSchema.PhysxArticulationAPI.Apply(root_prim).CreateSleepThresholdAttr(0.0)
    hand_rp = RigidPrim(hand_path)
    links_rp = RigidPrim(link_paths, contact_filter_paths=obstacles)
    pet_rp = RigidPrim(mc["target"]["object_prim"])

    app_utils.play(commit=True)
    SimulationManager.initialize_physics()
    dt = SimulationManager.get_physics_dt()
    log(f"[motion] physics dt={dt:.6f}s ({1 / dt:.0f} Hz), engine={SimulationManager.get_active_physics_engine()}, "
        f"articulation self-collisions={self_coll}, {len(obstacles)} obstacle collider prims")
    q0 = art.get_dof_positions().numpy()[0].astype(float)
    home_cfg = np.radians([wc["robot"]["home_joint_positions_deg"][n] for n in art.dof_names[:7]])
    home_err = float(np.degrees(np.abs(q0[:7] - home_cfg)).max())
    log(f"[motion] dofs {art.dof_names}; initial q (deg) {np.degrees(q0[:7]).round(3).tolist()} fingers {q0[7:].round(4).tolist()}; "
        f"max |q - home| = {home_err:.4f} deg")
    app_utils.pause(commit=True)  # no physics stepping while the world is built and the outbound motion is planned

    sq_before = mu.scene_query_count(rpath)
    exposed = mu.expose_guide_colliders(stage, obstacles)
    sq_after = mu.scene_query_count(rpath)
    log(f"[motion] obstacle discovery: explicit {len(obstacles)} collider prims; mg.SceneQuery {sq_before} before / {sq_after} after "
        f"exposing {exposed} guide-purpose colliders (session layer, invisible)")
    binding, wi, tracked = mu.build_world(art, rpath, stage, mc)
    planner = mu.Planner(mc, wc, wi)
    log(f"[motion] cuMotion robot: joints {planner.joints}, planning tool frame {planner.tool}, "
        f"world spheres {planner.inspector.num_world_collision_spheres()}, self spheres {planner.inspector.num_self_collision_spheres()}")
    from robot_geometry import RobotModel  # independent PhysX-hull collision model (Lula FK, validated vs. USD)
    usd_stage = Usd.Stage.Open(scene)
    hull_model = RobotModel(wc, usd_stage, app)
    hull_boxes = mu.hull_obstacles(usd_stage, wc)
    opening = float(sum(q0[7:]))
    fc = ptp.frame_check(planner, art, hand_rp, hull_model)
    log(f"[motion] frame check: {json.dumps({k: round(v, 7) for k, v in fc.items()})}")
    rng = np.random.default_rng(0)
    sanity = ptp.world_sanity(planner, hull_model, hull_boxes, tracked, mc, rng, opening)
    log(f"[motion] world sanity: {json.dumps(sanity)}")
    tgt_info, cands = ptp.derive_target(stage, mc, wc, pet_rp)
    log(f"[motion] target: {json.dumps(tgt_info)}")
    seeds = [q0[:7]] + [planner.lim[:, 0] + (planner.lim[:, 1] - planner.lim[:, 0]) * rng.random(7) for _ in range(6)]
    sols = planner.solve_goal(cands, seeds)
    ranked = ptp.choose_goal(planner, sols, q0[:7], hull_model, hull_boxes, mc, opening)
    log(f"[motion] collision-free IK: {len(sols)} solutions over {len(cands)} yaw candidates, {sum(r['accepted'] for r in ranked)} accepted")
    report = {"mode": "headless" if args.headless else "gui", "frame_check": fc, "world_sanity": sanity, "target": tgt_info,
              "obstacle_discovery": {"explicit": len(obstacles), "scene_query_before": sq_before, "scene_query_after": sq_after,
                                     "guide_colliders_exposed_in_session_layer": exposed},
              "self_collision_physx_enabled": self_coll, "obstacle_prims": len(tracked), "initial_home_error_deg": home_err,
              "ik_candidates": [{k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in r.items()} for r in ranked[:8]]}
    goal = next((r for r in ranked if r["accepted"]), None)
    if goal is None:
        log("[motion] FAILURE: no accepted collision-free IK solution for the pre-grasp target")
        report["failure"] = "no accepted collision-free IK solution"
        vm.write_failure(out_dir, report, mc)
        return 1
    W_target = dict(cands)[goal["target"]]
    log(f"[motion] goal: {goal['target']} q(deg)={np.degrees(goal['q']).round(2).tolist()} hull clearance {goal['hull_clearance_m']:.3f} m, "
        f"gripper-PET {goal['gripper_to_pet_clearance_m']:.3f} m, IK err {goal['pos_err_m'] * 1000:.3f} mm / {goal['rot_err_deg']:.3f} deg")
    skip = {("panda_link0", "Tabletop")}
    t0 = time.time()
    traj_out, wps_out, raw_out, samp_out, rep_out = mu.plan_validated(planner, q0[:7], goal["q"], hull_model, hull_boxes, mc, opening, skip, log)
    report["outbound_planning"] = {**rep_out, "planning_time_s": time.time() - t0}
    if traj_out is None:
        log("[motion] FAILURE: no validated outbound trajectory")
        report["failure"] = "outbound planning failed"
        vm.write_failure(out_dir, report, mc)
        return 1
    W_home = planner.tcp_world(q0[:7])
    if args.plan_only:
        vm.write_planned(out_dir, [("outbound", samp_out)])
        json.dump(report, open(os.path.join(out_dir, "planning_only.json"), "w"), indent=2, default=vm.js)
        log("[motion] plan-only run complete")
        return 0

    ex = Executor(art, hand_rp, links_rp, link_names, obstacles, planner, mc, log)
    ex.add_hold("settle_home", q0[:7], mc["execution"]["settle_home_s"], W_home)
    ex.add_trajectory("outbound", traj_out, W_target)
    ex.add_hold("hold_target", goal["q"], mc["execution"]["hold_target_s"], W_target)
    ex.add_planning_break("plan_return")
    gui = None
    shots = {}
    if not args.headless:
        try:
            from omni.kit.viewport.utility import get_active_viewport
            get_active_viewport().camera_path = "/World/Cameras/RobotSide"
        except Exception as exc:
            log(f"[gui] camera switch failed: {exc}")
        gui = vm.GuiOverlay(stage, mc)
        gui.show_target(W_target)
        gui.draw_path([planner.tcp_world(q)[:3, 3] for q in samp_out[1][::6]], (0.1, 0.8, 0.2, 1.0))
    ex.start()
    app_utils.play(commit=True)
    planned_total = mc["execution"]["settle_home_s"] + rep_out["selected"]["duration_s"] + mc["execution"]["hold_target_s"]
    traj_ret = samp_ret = rep_ret = None
    t_exec0 = time.time()
    while not ex.done:
        app.update()
        if gui is not None and ex.k < len(ex.phases):
            name = ex.phases[ex.k]["name"]
            if name in ("hold_target", "hold_home") and name not in shots and ex.t - ex.phase_t0 > 0.5:
                try:
                    from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport
                    f = os.path.join(out_dir, f"gui_{name}.png")
                    capture_viewport_to_file(get_active_viewport(), f)
                    shots[name] = os.path.relpath(f, mu.ROOT)
                    log(f"[gui] captured {f}")
                except Exception as exc:
                    shots[name] = f"failed: {exc}"
        if ex.needs_planning:
            app_utils.pause(commit=True)
            q_now = art.get_dof_positions().numpy()[0][:7].astype(float)
            log(f"[motion] planning return from measured q(deg) {np.degrees(q_now).round(3).tolist()}")
            t1 = time.time()
            traj_ret, wps_ret, raw_ret, samp_ret, rep_ret = mu.plan_validated(planner, q_now, q0[:7], hull_model, hull_boxes, mc, opening, skip, log)
            report["return_planning"] = {**rep_ret, "planning_time_s": time.time() - t1, "start_q": q_now.tolist()}
            if traj_ret is None:
                log("[motion] FAILURE: no validated return trajectory; robot holds the pre-grasp pose")
                ex.add_hold("hold_target_after_failed_return_plan", goal["q"], 1.0, W_target)
            else:
                ex.add_trajectory("return", traj_ret, W_home)
                ex.add_hold("hold_home", q0[:7], mc["execution"]["hold_home_s"], W_home)
                planned_total += rep_ret["selected"]["duration_s"] + mc["execution"]["hold_home_s"]
                if gui:
                    gui.draw_path([planner.tcp_world(q)[:3, 3] for q in samp_ret[1][::6]], (0.9, 0.5, 0.1, 1.0))
            ex.resume_after_planning()
            app_utils.play(commit=True)
        if ex.t > planned_total + mc["execution"]["max_phase_overrun_s"] + 5.0:
            log("[motion] ABORT: execution exceeded the planned duration")
            report["failure"] = "execution timeout"
            break
    exec_wall = time.time() - t_exec0
    ex.stop()
    pet_after = pet_rp.get_world_poses()[0].numpy()[0].astype(float)
    app_utils.pause(commit=True)
    gpu.stop_flag = True
    for _ in range(10):
        app.update()  # flush pending viewport captures
    report.update(gui_screenshots=shots, execution_wall_time_s=exec_wall, total_wall_time_s=time.time() - t_wall0, events=ex.events,
                  gpu_peak_mib=max((s[0] for s in gpu.samples), default=None), gpu_total_mib=gpu.samples[0][1] if gpu.samples else None,
                  pet_bottom_after=pet_after.tolist(), scene_file_unmodified=os.path.getmtime(scene) == scene_mtime)
    plans = [("outbound", samp_out)] + ([("return", samp_ret)] if samp_ret is not None else [])
    code = vm.analyse(out_dir, ex, planner, hull_model, hull_boxes, mc, wc, report, plans, W_target, W_home, q0, goal, log)
    if not args.headless and not args.exit_when_done:
        log("[motion] GUI: run finished; simulation paused at the final state. Close the window to exit.")
        while app.is_running():
            app.update()
    app_utils.stop(commit=True)
    logf.close()
    return code


if __name__ == "__main__":
    from isaacsim import SimulationApp

    headless = "--headless" in sys.argv
    app = SimulationApp({"headless": headless, "width": 1280, "height": 720})
    code = 1
    try:
        code = main(sys.argv[1:], app)
    except Exception:
        traceback.print_exc()
        code = 2
    finally:
        app.close(exit_code=code)
        sys.exit(code)
