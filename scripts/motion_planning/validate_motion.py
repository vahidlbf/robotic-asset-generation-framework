"""Validation and reporting for the motion experiment.

analyse() runs inside Isaac Sim at the end of run_motion_experiment.py (it needs the cuMotion inspector and the
hull model to re-check the *executed* joint states). The CLI finalises the classification with the workstation
regression results (logs/motion_planning/regression.json from run_regression.sh); it needs numpy, so use Isaac's python:
    "$ISAACSIM_PYTHON" scripts/motion_planning/validate_motion.py --finalize
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def js(x):
    if hasattr(x, "tolist"):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return str(x)


def write_failure(out_dir, report, mc):
    report["classification"] = "FAILED" if "outbound" not in json.dumps(report.get("failure", "")) else "PARTIAL SUCCESS"
    json.dump(report, open(os.path.join(out_dir, "validation_results.json"), "w"), indent=2, default=js)


def write_planned(out_dir, plans):
    with open(os.path.join(out_dir, "joint_trajectory.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["segment", "t_s"] + [f"q{i + 1}" for i in range(7)] + [f"qd{i + 1}" for i in range(7)] + [f"qdd{i + 1}" for i in range(7)])
        for name, (t, Q, V, A) in plans:
            for k in range(len(t)):
                w.writerow([name, f"{t[k]:.4f}", *(f"{x:.6f}" for x in Q[k]), *(f"{x:.6f}" for x in V[k]), *(f"{x:.6f}" for x in A[k])])


class GuiOverlay:
    """GUI-only visual aids: a target marker (session layer, no physics) and the planned TCP path (debug draw)."""

    def __init__(self, stage, mc):
        self.stage, self.mc, self.draw = stage, mc, None
        try:
            from isaacsim.core.utils.extensions import enable_extension
            enable_extension("isaacsim.util.debug_draw")
            from isaacsim.util.debug_draw import _debug_draw
            self.draw = _debug_draw.acquire_debug_draw_interface()
        except Exception as exc:
            print(f"[gui] debug draw unavailable: {exc}")

    def show_target(self, W):
        from pxr import Gf, Usd, UsdGeom
        with Usd.EditContext(self.stage, self.stage.GetSessionLayer()):
            s = UsdGeom.Sphere.Define(self.stage, "/World/MotionDebug/PreGraspTarget")
            s.CreateRadiusAttr(0.012)
            s.CreateDisplayColorAttr([Gf.Vec3f(0.9, 0.1, 0.1)])
            UsdGeom.Xformable(s).AddTranslateOp().Set(Gf.Vec3d(*W[:3, 3]))
            for k, col in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
                c = UsdGeom.Cylinder.Define(self.stage, f"/World/MotionDebug/TargetAxis{k}")
                c.CreateRadiusAttr(0.003)
                c.CreateHeightAttr(0.06)
                c.CreateDisplayColorAttr([Gf.Vec3f(*col)])
                axis = W[:3, k]
                m = Gf.Matrix4d(1)
                z = np.array([0, 0, 1.0])
                v = np.cross(z, axis)
                ang = math.degrees(math.atan2(np.linalg.norm(v), z @ axis))
                rot = Gf.Rotation(Gf.Vec3d(*(v if np.linalg.norm(v) > 1e-9 else [1, 0, 0])), ang)
                m.SetRotate(rot)
                m.SetTranslateOnly(Gf.Vec3d(*(W[:3, 3] + axis * 0.03)))
                UsdGeom.Xformable(c).AddTransformOp().Set(m)

    def draw_path(self, pts, color):
        if self.draw is None or len(pts) < 2:
            return
        a = [tuple(map(float, p)) for p in pts[:-1]]
        b = [tuple(map(float, p)) for p in pts[1:]]
        self.draw.draw_lines(a, b, [color] * len(a), [3.0] * len(a))


def _rot_err(Ra, Rb):
    return float(np.degrees(np.arccos(np.clip((np.trace(Ra.T @ Rb) - 1) / 2, -1, 1))))


def analyse(out_dir, ex, planner, hull_model, hull_boxes, mc, wc, report, plans, W_target, W_home, q0, goal, log):
    tol = mc["tolerances"]
    rows = ex.rows
    t = np.array([r["t"] for r in rows])
    ph = np.array([r["phase"] for r in rows])
    Qc = np.array([r["q_cmd"] for r in rows])
    Qm = np.array([r["q_meas"] for r in rows])
    Vm = np.array([r["v_meas"] for r in rows])
    Fg = np.array([r["fingers"] for r in rows])
    B = np.array([r["base"] for r in rows])
    dt = float(np.median(np.diff(t)))
    write_planned(out_dir, plans)
    # ---- executed joint states ----
    with open(os.path.join(out_dir, "executed_joint_states.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "phase"] + [f"q_cmd{i + 1}" for i in range(7)] + [f"q_meas{i + 1}" for i in range(7)]
                   + [f"qd_meas{i + 1}" for i in range(7)] + ["finger1", "finger2", "max_contact_force_N"])
        for r in rows:
            w.writerow([f"{r['t']:.5f}", r["phase"], *(f"{x:.6f}" for x in r["q_cmd"]), *(f"{x:.6f}" for x in r["q_meas"]),
                        *(f"{x:.6f}" for x in r["v_meas"]), *(f"{x:.6f}" for x in r["fingers"]), f"{r['contact_max_N']:.4g}"])
    # ---- TCP ----
    pos_err, rot_err = [], []
    with open(os.path.join(out_dir, "tcp_trajectory.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "phase", "tcp_x", "tcp_y", "tcp_z", "tcp_qw", "tcp_qx", "tcp_qy", "tcp_qz",
                    "target_x", "target_y", "target_z", "target_qw", "target_qx", "target_qy", "target_qz", "pos_err_mm", "rot_err_deg"])
        from motion_utils import R_to_quat
        for r in rows:
            W, Tt = r["tcp"], r["tcp_target"]
            pe = float(np.linalg.norm(W[:3, 3] - Tt[:3, 3])) * 1000
            re = _rot_err(W[:3, :3], Tt[:3, :3])
            pos_err.append(pe)
            rot_err.append(re)
            w.writerow([f"{r['t']:.5f}", r["phase"], *(f"{x:.6f}" for x in W[:3, 3]), *(f"{x:.6f}" for x in R_to_quat(W[:3, :3])),
                        *(f"{x:.6f}" for x in Tt[:3, 3]), *(f"{x:.6f}" for x in R_to_quat(Tt[:3, :3])), f"{pe:.3f}", f"{re:.4f}"])
    pos_err, rot_err = np.array(pos_err), np.array(rot_err)

    def window_end(name, span=0.1):
        idx = np.nonzero(ph == name)[0]
        if not len(idx):
            return None
        te = t[idx[-1]]
        return idx[t[idx] >= te - span]

    res = {"physics_dt_s": dt, "samples": len(rows), "phases": {}}
    for name in dict.fromkeys(ph):
        idx = np.nonzero(ph == name)[0]
        e = Qm[idx[1:]] - Qc[idx[:-1]] if len(idx) > 1 else np.zeros((1, 7))
        acc = np.diff(Vm[idx], axis=0) / dt if len(idx) > 2 else np.zeros((1, 7))
        res["phases"][name] = {"start_s": float(t[idx[0]]), "end_s": float(t[idx[-1]]), "duration_s": float(t[idx[-1]] - t[idx[0]] + dt),
                               "max_tracking_error_rad": float(np.abs(e).max()), "rms_tracking_error_rad": float(np.sqrt((e ** 2).mean())),
                               "max_tracking_error_per_joint_rad": np.abs(e).max(axis=0).tolist(),
                               "max_measured_velocity_rad_s": float(np.abs(Vm[idx]).max()),
                               "max_measured_velocity_per_joint_rad_s": np.abs(Vm[idx]).max(axis=0).tolist(),
                               "max_measured_acceleration_rad_s2": float(np.abs(acc).max()),
                               "final_tcp_pos_err_mm": float(pos_err[idx[-1]]), "final_tcp_rot_err_deg": float(rot_err[idx[-1]])}
    wt = window_end("hold_target")
    wh = window_end("hold_home")
    tgt = {"reached": False}
    if wt is not None:
        tgt = {"tcp_pos_err_mm": float(pos_err[wt].mean()), "tcp_rot_err_deg": float(rot_err[wt].mean()),
               "joint_err_to_goal_deg": float(np.degrees(np.abs(Qm[wt].mean(axis=0) - goal["q"])).max())}
        tgt["reached"] = tgt["tcp_pos_err_mm"] <= tol["final_tcp_position_mm"] and tgt["tcp_rot_err_deg"] <= tol["final_tcp_orientation_deg"]
    home = {"returned": False}
    if wh is not None:
        home = {"joint_err_deg": float(np.degrees(np.abs(Qm[wh].mean(axis=0) - q0[:7])).max()),
                "tcp_pos_err_mm": float(pos_err[wh].mean()), "tcp_rot_err_deg": float(rot_err[wh].mean())}
        home["returned"] = home["joint_err_deg"] <= tol["home_joint_deg"] and home["tcp_pos_err_mm"] <= tol["final_tcp_position_mm"]
    lim = planner.lim
    within = bool(np.all(Qm >= lim[:, 0] - 1e-3) and np.all(Qm <= lim[:, 1] + 1e-3))
    margin = float(np.minimum(Qm - lim[:, 0], lim[:, 1] - Qm).min())
    base_drift = float(np.linalg.norm(B - B[0], axis=1).max())
    finger_dev = float(np.abs(Fg - mc["execution"]["finger_position_m"]).max())
    traj_phases = [n for n in ("outbound", "return") if n in res["phases"]]
    max_track = max((res["phases"][n]["max_tracking_error_rad"] for n in traj_phases), default=None)
    # ---- collision: physics contacts ----
    allowed = mc["collision"]["allowed_contacts"]
    contacts = [{"link": k[0], "collider": k[1], "max_force_N": v,
                 "allowed": any(k[0] == a and k[1].startswith(b) for a, b in allowed)} for k, v in sorted(ex.contact_max.items())]
    unintended = [c for c in contacts if not c["allowed"]]
    readback_ok = not any(e["event"].startswith("contact_readback_error") for e in ex.events)
    # ---- collision: executed configurations re-checked (every physics step) ----
    planner.refresh()
    insp = [planner.check_q(q) for q in Qm]
    skip = {("panda_link0", "Tabletop")}
    hull = []
    for i in range(0, len(Qm), 6):
        r = hull_model.clearance(Qm[i], float(Fg[i].sum()), hull_boxes, None, skip=skip)
        hull.append((float(t[i]), r["min_m"], r["part"], r["box"]))
    pet = [b for b in hull_boxes if b.name.endswith("plastic_bottle")]
    gp = [hull_model.clearance(Qm[i], float(Fg[i].sum()), pet, None, skip={(f"panda_link{j}", "*") for j in range(8)})["min_m"]
          for i in range(0, len(Qm), 6)]
    executed = {"steps_checked": len(insp), "inspector_world_collision_steps": int(sum(c["in_collision"] for c in insp)),
                "inspector_self_collision_steps": int(sum(c["self_collision"] for c in insp)),
                "inspector_min_distance_m": float(min(c["min_distance_m"] for c in insp)),
                "hull_min_clearance_m": float(min(h[1] for h in hull)), "hull_closest": list(min(hull, key=lambda h: h[1])[2:]),
                "hull_steps_checked": len(hull), "min_gripper_to_pet_clearance_m": float(min(gp))}
    collision = {
        "scope": ["PhysX contact reports: every robot link vs. every obstacle collider prim, every physics step",
                  "cuMotion RobotWorldInspector on every executed joint state (world collision with safety-padded obstacles, self-collision spheres)",
                  "independent PhysX-hull clearance (robot convex hulls, real finger opening) every 6th step"],
        "limitations": ["no continuous/swept collision checking; checks are discrete (planned 4 ms, executed 8.3 ms)",
                        "PhysX articulation self-collision is " + ("enabled" if report.get("self_collision_physx_enabled") else
                                                                    "disabled in the official asset, so self-collision is checked only with cuMotion's sphere model"),
                        "cuMotion fingertip spheres assume the XRDF finger model; the hull check uses the real 0.04 m opening"],
        "physics_contact_readback_ok": readback_ok, "physics_contacts": contacts, "unintended_contacts": unintended,
        "executed_configuration_checks": executed,
        "planned_trajectory_checks": {"outbound": report.get("outbound_planning", {}).get("selected"),
                                      "return": report.get("return_planning", {}).get("selected")}}
    json.dump(collision, open(os.path.join(out_dir, "collision_report.json"), "w"), indent=2, default=js)
    cc = mc["collision"]
    collision_ok = (readback_ok and not unintended and executed["inspector_world_collision_steps"] == 0
                    and executed["inspector_self_collision_steps"] == 0 and executed["hull_min_clearance_m"] >= cc["min_hull_clearance_m"] - 0.005)
    pet_moved = float(np.linalg.norm(np.array(report["pet_bottom_after"]) - np.array(report["target"]["pet_bottom_physics"])))
    out_sel = report.get("outbound_planning", {}).get("selected") or {}
    ret_sel = report.get("return_planning", {}).get("selected") or {}
    checks = {
        "collision_aware_outbound_plan": bool(out_sel.get("valid")),
        "collision_aware_return_plan": bool(ret_sel.get("valid")),
        "outbound_executed": "outbound" in res["phases"],
        "target_reached_within_tolerance": bool(tgt.get("reached")),
        "return_executed": "return" in res["phases"],
        "returned_home_within_tolerance": bool(home.get("returned")),
        "joint_limits_respected": within,
        "tracking_error_within_limit": max_track is not None and max_track <= tol["joint_tracking_max_rad"],
        "no_unintended_collisions": collision_ok,
        "fixed_base": base_drift <= tol["base_drift_m"],
        "gripper_held_open": finger_dev <= 0.002,
        "pet_bottle_not_disturbed": pet_moved <= 0.001,
        "workstation_scene_unmodified": bool(report.get("scene_file_unmodified")),
        "initial_home_verified": report.get("initial_home_error_deg", 99) <= 0.1,
    }
    report.update(execution=res, target_result=tgt, home_result=home, joint_limits={"within": within, "min_margin_rad": margin},
                  base_drift_m=base_drift, finger_max_deviation_m=finger_dev, pet_displacement_m=pet_moved, checks=checks,
                  max_tracking_error_rad=max_track, collision_summary={k: collision[k] for k in ("physics_contact_readback_ok", "unintended_contacts")} |
                  {"executed": executed})
    motion_ok = all(checks.values())
    report["motion_classification"] = "FULL SUCCESS (pending regression)" if motion_ok else (
        "FAILED" if "outbound" not in res["phases"] else "PARTIAL SUCCESS")
    json.dump(report, open(os.path.join(out_dir, "validation_results.json"), "w"), indent=2, default=js)
    write_report(out_dir, report, mc)
    for k, v in checks.items():
        log(f"[validate] {'PASS' if v else 'FAIL'} {k}")
    log(f"[validate] target: {json.dumps(tgt)}; home: {json.dumps(home)}; max tracking {max_track:.4f} rad; "
        f"executed-state checks {json.dumps(executed)}")
    log(f"[validate] classification: {report['motion_classification']}")
    return 0 if motion_ok else 1


def write_report(out_dir, r, mc, regression=None):
    o = ["# Motion planning experiment: Franka home → PET pre-grasp → home\n"]
    cls = r.get("classification") or r.get("motion_classification")
    o.append(f"- **Classification: {cls}**")
    o.append(f"- Mode: {r.get('mode')}; physics {1 / r['execution']['physics_dt_s']:.0f} Hz (PhysX, CPU); obstacle collider prims: {r['obstacle_prims']}")
    o.append(f"- GPU memory peak: {r.get('gpu_peak_mib')} / {r.get('gpu_total_mib')} MiB; wall time {r.get('total_wall_time_s', 0):.1f} s "
             f"(execution {r.get('execution_wall_time_s', 0):.1f} s)\n")
    o.append("## Framework\n")
    for k in ("framework", "goal_solver", "path_planner", "time_parameterization", "executor"):
        o.append(f"- {k}: {mc['planner'][k]}")
    o.append("- Why: cuMotion is NVIDIA's maintained motion-generation backend in Isaac Sim 6.2 (`isaacsim.robot_motion.cumotion` on the "
             "`experimental.motion_generation` substrate). Its graph planner checks the robot's collision spheres against the scene "
             "obstacles and its self-collision spheres. The previous Lula stack lives in the deprecated `motion_generation` extension and "
             "is used here only for the independent hull cross-check. cuRobo is not installed. RMPflow (also cuMotion) is a reactive "
             "controller, not a global planner, so it was not used.")
    o.append("- World: all PhysicsCollisionAPI prims outside the robot (explicit list; `mg.SceneQuery` misses colliders with "
             f"purpose=guide), native cube/cylinder/mesh obstacles + {mc['collision']['obstacle_safety_tolerance_m']} m safety tolerance.\n")
    fc, ws = r["frame_check"], r["world_sanity"]
    o.append("## Pre-flight checks\n")
    o.append(f"- Frames: cuMotion `panda_hand` FK vs. physics hand link: {fc['hand_pos_err_m'] * 1000:.3f} mm / {fc['hand_rot_err_deg']:.4f}°; "
             f"derived TCP vs. project TCP (Lula `right_gripper`): {fc.get('tcp_vs_lula_right_gripper_pos_m', float('nan')) * 1000:.3f} mm / "
             f"{fc.get('tcp_vs_lula_rot_deg', float('nan')):.4f}°")
    o.append(f"- Obstacle world vs. independent hull model on {ws['samples']} random configurations: positive control "
             f"{ws['positive_detected']}/{ws['positive_control_configs']} detected, negative control {ws['negative_flagged']}/"
             f"{ws['negative_control_configs']} flagged")
    o.append(f"- Home verified at start: max |q − home| = {r['initial_home_error_deg']:.4f}°\n")
    tg = r["target"]
    o.append("## Target\n")
    o.append(f"- PET bottom (physics) {np.round(tg['pet_bottom_physics'], 4).tolist()} (config {np.round(tg['pet_bottom_config'], 4).tolist()}, "
             f"Δ {tg['physics_vs_config_m'] * 1000:.2f} mm, tilt {tg['pet_tilt_deg']:.3f}°); `/World/Targets` PET frame present: {tg['existing_target_frame']} "
             f"→ derived from bottle pose + config")
    o.append(f"- Grasp point (cap) {np.round(tg['grasp_point'], 4).tolist()}; **pre-grasp TCP {np.round(tg['pre_grasp_tcp_position'], 4).tolist()}**, "
             f"top-down, {mc['target']['pre_grasp_clearance_above_grasp_m'] * 1000:.0f} mm above the grasp point; fingertips "
             f"{tg['fingertip_height_above_pet_top_m'] * 1000:.0f} mm above the cap")
    ik = r["ik_candidates"][0] if r["ik_candidates"] else {}
    if ik:
        o.append(f"- Selected goal ({ik['target']}): q = {np.round(np.degrees(ik['q']), 2).tolist()}°, IK error {ik['pos_err_m'] * 1000:.3f} mm / "
                 f"{ik['rot_err_deg']:.3f}°, inspector distance {ik['min_distance_m']:.3f} m, hull clearance {ik['hull_clearance_m']:.3f} m, "
                 f"gripper↔PET {ik['gripper_to_pet_clearance_m']:.3f} m\n")
    o.append("## Planned trajectories\n")
    o.append("| Segment | RRT waypoints | Timed waypoints | Duration (s) | Max |qd| (rad/s) | Max |qdd| (rad/s²) | Inspector min dist (m) | "
             "Hull min clearance (m) | Collision samples (world/self) | Valid |\n|---|---|---|---|---|---|---|---|---|---|")
    for seg in ("outbound", "return"):
        s = (r.get(f"{seg}_planning") or {}).get("selected")
        if s:
            o.append(f"| {seg} | {s['rrt_waypoints']} | {s['timed_waypoints']} | {s['duration_s']:.3f} | {max(s['max_velocity_rad_s']):.3f} | "
                     f"{max(s['max_acceleration_rad_s2']):.3f} | {s['inspector_min_distance_m']:.4f} | {s['hull_min_clearance_m']:.4f} | "
                     f"{s['inspector_world_collision_samples']}/{s['inspector_self_collision_samples']} | {s['valid']} |")
    o.append("\n## Execution (PhysX, articulation joint drives)\n")
    o.append("| Phase | Duration (s) | Max tracking err (rad) | RMS tracking err (rad) | Max |qd| (rad/s) | Max |qdd| (rad/s², finite diff) | Final TCP err (mm / °) |\n|---|---|---|---|---|---|---|")
    for n, p in r["execution"]["phases"].items():
        o.append(f"| {n} | {p['duration_s']:.3f} | {p['max_tracking_error_rad']:.4f} | {p['rms_tracking_error_rad']:.5f} | {p['max_measured_velocity_rad_s']:.3f} | "
                 f"{p['max_measured_acceleration_rad_s2']:.2f} | {p['final_tcp_pos_err_mm']:.2f} / {p['final_tcp_rot_err_deg']:.3f} |")
    t, h = r["target_result"], r["home_result"]
    o.append(f"\n- **Target**: TCP error (mean of the last 0.1 s of the hold) {t.get('tcp_pos_err_mm', float('nan')):.3f} mm / "
             f"{t.get('tcp_rot_err_deg', float('nan')):.4f}° (limits {mc['tolerances']['final_tcp_position_mm']} mm / "
             f"{mc['tolerances']['final_tcp_orientation_deg']}°) → reached: **{t.get('reached')}**")
    o.append(f"- **Home**: joint error {h.get('joint_err_deg', float('nan')):.4f}°, TCP error {h.get('tcp_pos_err_mm', float('nan')):.3f} mm → returned: **{h.get('returned')}**")
    o.append(f"- Joint limits respected: {r['joint_limits']['within']} (min margin {math.degrees(r['joint_limits']['min_margin_rad']):.1f}°); base drift "
             f"{r['base_drift_m']:.2e} m; finger max deviation {r['finger_max_deviation_m'] * 1000:.3f} mm; PET displacement {r['pet_displacement_m'] * 1000:.4f} mm\n")
    cs = r["collision_summary"]
    ex = cs["executed"]
    o.append("## Collision checking\n")
    o.append(f"- PhysX contact reports (all links × {r['obstacle_prims']} colliders, every step): readback OK {cs['physics_contact_readback_ok']}, "
             f"unintended contacts: {len(cs['unintended_contacts'])} {cs['unintended_contacts'][:3] if cs['unintended_contacts'] else ''}")
    o.append(f"- Executed joint states ({ex['steps_checked']} steps) re-checked with cuMotion: world-collision steps {ex['inspector_world_collision_steps']}, "
             f"self-collision steps {ex['inspector_self_collision_steps']}, min distance to padded obstacles {ex['inspector_min_distance_m']:.4f} m")
    o.append(f"- Independent hull model ({ex['hull_steps_checked']} steps): min clearance {ex['hull_min_clearance_m']:.4f} m ({ex['hull_closest']}); "
             f"min gripper↔PET clearance {ex['min_gripper_to_pet_clearance_m']:.3f} m")
    o.append(f"- PhysX articulation self-collision enabled in the official asset: {r.get('self_collision_physx_enabled')}")
    o.append("- Not available / not done: continuous (swept) collision checking — all checks are discrete in time.\n")
    o.append("## Checks\n")
    o.append("| Check | Result |\n|---|---|")
    for k, v in r["checks"].items():
        o.append(f"| {k} | {'PASS' if v else '**FAIL**'} |")
    if regression is not None:
        o.append(f"| workstation_regression | {'PASS' if regression['ok'] else '**FAIL**'} ({regression['detail']}) |")
    o.append("\n## Files\n")
    for f in ("validation_results.json", "collision_report.json", "joint_trajectory.csv", "executed_joint_states.csv", "tcp_trajectory.csv", "execution.log"):
        o.append(f"- `{mc['logs_dir']}/{f}`")
    open(os.path.join(out_dir, "planning_report.md"), "w").write("\n".join(o) + "\n")


def finalize():
    mc = json.load(open(os.path.join(ROOT, "config", "motion_planning.json")))
    out_dir = os.path.join(ROOT, mc["logs_dir"])
    r = json.load(open(os.path.join(out_dir, "validation_results.json")))
    rg = json.load(open(os.path.join(out_dir, "regression.json")))
    reg = {"ok": rg["ok"], "detail": rg["detail"]}
    motion_ok = all(r["checks"].values())
    r["regression"] = reg
    r["classification"] = "FULL SUCCESS" if motion_ok and reg["ok"] else ("PARTIAL SUCCESS" if r["checks"].get("outbound_executed") else "FAILED")
    json.dump(r, open(os.path.join(out_dir, "validation_results.json"), "w"), indent=2)
    write_report(out_dir, r, mc, reg)
    print(f"[finalize] {r['classification']} (motion checks {'all pass' if motion_ok else 'not all pass'}; regression {reg['detail']})")
    return 0 if r["classification"] == "FULL SUCCESS" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    a = ap.parse_args()
    sys.exit(finalize() if a.finalize else 0)
