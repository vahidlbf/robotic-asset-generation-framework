"""Dynamic validation of the workstation in headless Isaac Sim (PhysX, CPU dynamics).

    "$ISAACSIM_PYTHON" scripts/workstation/run_physics_test.py [--config ...]

Test D+F (settle): the saved scene is opened unchanged and simulated for settle_duration_s. The three
tabletop objects and the robot are recorded every physics step. Contact-report APIs needed for force
readback are added in the *session layer* only (never saved), so neither the scene nor the robot asset
is modified. The robot is never commanded; it only holds its authored home joint state.

Test E (bins): a temporary stage (logs/workstation/bin_drop_test_scene.usda) sublayers the final scene and
adds one test cube above each bin opening. The final scene file and its object arrangement are untouched.

Writes logs/workstation/physics_results.json and per-object CSV trajectories in logs/workstation/trajectories/.
"""

import argparse
import csv
import json
import math
import os
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="config/waste_sorting_environment.json")
args, _ = parser.parse_known_args()
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from isaacsim import SimulationApp  # noqa: E402

simulation_app = SimulationApp({"headless": True})

import numpy as np  # noqa: E402
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics  # noqa: E402
import isaacsim.core.experimental.utils.app as app_utils  # noqa: E402
import isaacsim.core.experimental.utils.stage as stage_utils  # noqa: E402
from isaacsim.core.experimental.prims import Articulation, RigidPrim  # noqa: E402
from isaacsim.core.simulation_manager import SimulationManager  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_geometry as lg  # noqa: E402

CHECKS, WARN = {}, []
TOP_COLLIDER = "/World/Workstation/Table/Tabletop/Collision/TopSlab/Shape"
OBJECTS = {"glass_bottle": "/World/Objects/GlassBottle", "plastic_bottle": "/World/Objects/PlasticBottle",
           "paper_cup": "/World/Objects/PaperCup"}


def log(*a):
    print("[physics]", *a, flush=True)


def check(group, name, passed, **detail):
    CHECKS.setdefault(group, {})[name] = {"passed": bool(passed), **detail}
    log(f"{'PASS' if passed else 'FAIL'} {group}.{name}: " + ", ".join(f"{k}={v}" for k, v in detail.items() if not isinstance(v, (list, dict)) or len(str(v)) < 90))
    return passed


def rot(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def open_and_wait(path):
    ok, stage = stage_utils.open_stage(path)
    if not ok:
        raise RuntimeError(f"open_stage failed: {path}")
    while stage_utils.is_stage_loading():
        simulation_app.update()
    return stage


def ensure_physx():
    if SimulationManager.get_active_physics_engine() != "physx":
        SimulationManager.switch_physics_engine("physx")
    return SimulationManager.get_active_physics_engine()


def session_instrumentation(stage, body_paths, articulation_path):
    """Test-only instrumentation, authored in the session layer (never saved):
    contact-report APIs for force readback, and sleeping disabled so every body is genuinely simulated for
    the whole test (PhysX stops reporting contacts for, and stops integrating, sleeping bodies)."""
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        for p in body_paths:
            prim = stage.GetPrimAtPath(p)
            PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.0)
            if not prim.HasAPI(UsdPhysics.ArticulationRootAPI) and p.startswith("/World/Objects"):
                PhysxSchema.PhysxRigidBodyAPI.Apply(prim).CreateSleepThresholdAttr(0.0)
        if articulation_path:
            PhysxSchema.PhysxArticulationAPI.Apply(stage.GetPrimAtPath(articulation_path)).CreateSleepThresholdAttr(0.0)


# ---------------------------------------------------------------------------
# D + F: settle + robot stability
# ---------------------------------------------------------------------------

def settle_test(cfg, out_dir):
    v = cfg["validation"]
    scene = os.path.join(ROOT, cfg["paths"]["scene"])
    stage = open_and_wait(scene)
    engine = ensure_physx()
    top_z = cfg["table"]["position"][2] + cfg["table"]["height"]
    clearance = cfg["objects"]["clearance"]
    rpath = cfg["robot"]["mount_prim"] + "/" + cfg["robot"]["prim_name"]

    art = Articulation(rpath)
    link_paths = list(art.link_paths[0]) if art.link_paths and isinstance(art.link_paths[0], (list, tuple)) else list(art.link_paths)
    session_instrumentation(stage, list(OBJECTS.values()) + link_paths, rpath)
    objs = {k: RigidPrim(p, contact_filter_paths=[TOP_COLLIDER]) for k, p in OBJECTS.items()}
    links = RigidPrim(link_paths, contact_filter_paths=[TOP_COLLIDER] + list(OBJECTS.values()))
    app_utils.play(commit=True)
    SimulationManager.initialize_physics()
    dt = SimulationManager.get_physics_dt()
    t_start = SimulationManager.get_simulation_time()
    n = int(round(v["settle_duration_s"] / dt))
    names = art.dof_names
    home = cfg["robot"]["home_joint_positions_deg"]
    fingers = cfg["robot"]["home_finger_positions_m"]
    q_home = np.array([math.radians(home[nm]) if nm in home else fingers[nm] for nm in names])

    rec = {k: [] for k in OBJECTS}
    rq, rbase, rlinkF, rlinkZ = [], [], [], []
    contact_ok = True
    for step in range(n + 1):
        if step:
            SimulationManager.step(steps=1)
        t = SimulationManager.get_simulation_time() - t_start
        for k, rp in objs.items():
            p, q = rp.get_world_poses()
            lv, av = rp.get_velocities()
            f = np.zeros(3)
            if contact_ok:
                try:
                    f = np.asarray(rp.get_contact_force_matrix(dt=dt).numpy())[0, 0]
                except Exception as exc:
                    contact_ok = False
                    WARN.append(f"object contact-force readback unavailable: {exc}")
            rec[k].append({"t": t, "p": p.numpy()[0].astype(float), "q": q.numpy()[0].astype(float),
                           "v": lv.numpy()[0].astype(float), "w": av.numpy()[0].astype(float), "f": f})
        rq.append(art.get_dof_positions().numpy()[0].astype(float))
        bp, bq = art.get_world_poses()
        rbase.append(np.concatenate([bp.numpy()[0], bq.numpy()[0]]))
        lp, _ = links.get_world_poses()
        rlinkZ.append(lp.numpy()[:, 2].astype(float))
        try:
            fm = np.asarray(links.get_contact_force_matrix(dt=dt).numpy())
            rlinkF.append(np.linalg.norm(fm, axis=2))  # (links, filters)
        except Exception as exc:
            if not rlinkF:
                WARN.append(f"robot link contact-force readback unavailable: {exc}")
            rlinkF.append(None)
    app_utils.stop(commit=True)
    simulation_app.update()

    # --- analysis: objects ---
    os.makedirs(os.path.join(out_dir, "trajectories"), exist_ok=True)
    tol_pen = v["penetration_tolerance_m"]
    results = {"engine": engine, "dt": dt, "steps": n, "duration_s": n * dt, "objects": {}, "robot": {}}
    for k, R in rec.items():
        o = cfg["objects"][k]
        r_base = o.get("body_diameter", o.get("bottom_diameter")) / 2 - (0.0005 if k == "paper_cup" else 0.0)
        ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        ring = np.stack([r_base * np.cos(ang), r_base * np.sin(ang), np.zeros_like(ang)], axis=1)
        P = np.array([r["p"] for r in R])
        T = np.array([r["t"] for r in R])
        lowest = np.array([(r["p"] + ring @ rot(r["q"]).T)[:, 2].min() for r in R]) - top_z
        tilt = np.array([math.degrees(math.acos(min(1.0, rot(r["q"])[2, 2]))) for r in R])
        vfd = np.vstack([np.zeros((1, 3)), np.diff(P, axis=0) / np.diff(T)[:, None]])
        last = T >= T[-1] - 0.5
        fz = np.array([r["f"][2] if np.ndim(r["f"]) else 0 for r in R])
        mg = o["mass"] * cfg["physics"]["gravity_m_s2"]
        drift = float(np.linalg.norm(P[-1, :2] - P[0, :2]))
        dz = float(P[-1, 2] - P[0, 2])
        info = {"initial_pos": P[0].tolist(), "final_pos": P[-1].tolist(), "initial_height_bottom_m": float(P[0, 2]),
                "final_height_bottom_m": float(P[-1, 2]), "height_change_m": dz, "horizontal_drift_m": drift,
                "final_orientation_wxyz": R[-1]["q"].tolist(), "max_tilt_deg": float(tilt.max()), "final_tilt_deg": float(tilt[-1]),
                "final_lin_vel_reported": R[-1]["v"].tolist(), "final_speed_position_derived": float(np.linalg.norm(vfd[last], axis=1).mean()),
                "max_penetration_m": float(max(0.0, -lowest.min())), "final_bottom_gap_m": float(lowest[-1]),
                "mean_normal_force_last_0_5s_N": float(fz[last].mean()), "weight_N": mg}
        results["objects"][k] = info
        grp = f"settle_{k}"
        check(grp, "no_fall_through_tabletop", lowest.min() >= -tol_pen and P[-1, 2] > top_z - tol_pen,
              max_penetration_mm=round(info["max_penetration_m"] * 1000, 3), tolerance_mm=tol_pen * 1000)
        check(grp, "settled_on_tabletop", abs(lowest[-1]) <= tol_pen and abs(dz + clearance) <= v["settle_max_height_change_m"],
              final_bottom_gap_mm=round(lowest[-1] * 1000, 3), height_change_mm=round(dz * 1000, 3))
        check(grp, "remains_upright", tilt.max() <= v["settle_max_tilt_deg"], max_tilt_deg=round(float(tilt.max()), 4))
        check(grp, "no_horizontal_drift", drift <= v["settle_max_horizontal_drift_m"], drift_mm=round(drift * 1000, 3))
        check(grp, "at_rest", info["final_speed_position_derived"] <= v["settle_max_speed_m_s"],
              mean_speed_last_0_5s=f"{info['final_speed_position_derived']:.2e}")
        if contact_ok:
            check(grp, "supported_by_tabletop_force", abs(info["mean_normal_force_last_0_5s_N"] - mg) <= 0.1 * mg,
                  normal_force_N=round(info["mean_normal_force_last_0_5s_N"], 4), weight_N=round(mg, 4))
        with open(os.path.join(out_dir, "trajectories", f"settle_{k}.csv"), "w", newline="") as fcsv:
            w = csv.writer(fcsv)
            w.writerow(["t", "x", "y", "z", "qw", "qx", "qy", "qz", "vx", "vy", "vz", "wx", "wy", "wz", "fz_table", "bottom_gap", "tilt_deg"])
            for r, lo, tl in zip(R, lowest, tilt):
                w.writerow([f"{r['t']:.5f}", *(f"{x:.7g}" for x in r["p"]), *(f"{x:.7g}" for x in r["q"]),
                            *(f"{x:.6g}" for x in r["v"]), *(f"{x:.6g}" for x in r["w"]), f"{(r['f'][2] if np.ndim(r['f']) else 0):.5g}",
                            f"{lo:.6g}", f"{tl:.5g}"])

    # --- analysis: robot ---
    Q = np.array(rq)
    B = np.array(rbase)
    dq = np.degrees(np.abs(Q[:, :7] - q_home[:7])).max(axis=0)
    fdrift = np.abs(Q[:, 7:] - q_home[7:]).max(axis=0)
    base_drift = float(np.linalg.norm(B[:, :3] - B[0, :3], axis=1).max())
    zl = np.array(rlinkZ)
    results["robot"] = {"dof_names": list(names), "num_dofs": art.num_dofs, "initial_dof_positions": Q[0].tolist(),
                        "final_dof_positions": Q[-1].tolist(), "max_joint_drift_deg": dq.tolist(),
                        "max_finger_drift_m": fdrift.tolist(), "base_pose_initial": B[0].tolist(), "base_drift_m": base_drift,
                        "link_names": [p.split("/")[-1] for p in link_paths], "min_link_origin_z": zl.min(axis=0).tolist()}
    check("robot", "articulation_initialized", art.num_dofs == 9 and np.isfinite(Q).all(), num_dofs=art.num_dofs, dofs=list(names))
    check("robot", "initial_state_is_home_pose", np.degrees(np.abs(Q[0, :7] - q_home[:7])).max() <= 0.1
          and np.abs(Q[0, 7:] - q_home[7:]).max() <= 0.001, initial_deg=np.degrees(Q[0, :7]).round(3).tolist())
    check("robot", "stable_holding_home_pose", dq.max() <= v["robot_max_joint_drift_deg"] and fdrift.max() <= 0.002,
          max_joint_drift_deg=round(float(dq.max()), 4), max_finger_drift_m=round(float(fdrift.max()), 5))
    check("robot", "base_fixed", base_drift <= v["robot_max_base_drift_m"] and
          np.allclose(B[0, :3], cfg["robot"]["base_position"], atol=1e-4), base_drift_m=f"{base_drift:.2e}",
          base_position=B[0, :3].round(5).tolist())
    if rlinkF and rlinkF[0] is not None:
        F = np.array([f for f in rlinkF if f is not None])  # (steps, links, filters)
        lnames = results["robot"]["link_names"]
        non_base = [i for i, nm in enumerate(lnames) if nm != "panda_link0"]
        max_tab = float(F[:, non_base, 0].max())
        max_obj = float(F[:, :, 1:].max())
        base_tab = float(F[:, [i for i, nm in enumerate(lnames) if nm == "panda_link0"], 0].max()) if "panda_link0" in lnames else None
        results["robot"].update(max_link_table_contact_N=max_tab, max_link_object_contact_N=max_obj, base_table_contact_N=base_tab)
        check("robot", "no_initial_collision_with_table_or_objects", max_tab < 1e-3 and max_obj < 1e-3,
              max_link_table_force_N=max_tab, max_link_object_force_N=max_obj, base_table_force_N_filtered=base_tab)
    else:
        lowest_link = float(zl[:, [i for i, p in enumerate(link_paths) if not p.endswith("panda_link0")]].min())
        check("robot", "no_initial_collision_with_table_or_objects", lowest_link > cfg["table"]["height"] + 0.05,
              lowest_non_base_link_origin_z=lowest_link, note="geometric fallback")
    return results


# ---------------------------------------------------------------------------
# E: bin drop test on a temporary stage
# ---------------------------------------------------------------------------

def bin_drop_test(cfg, out_dir):
    v = cfg["validation"]["bin_drop"]
    scene = os.path.join(ROOT, cfg["paths"]["scene"])
    tmp = os.path.join(out_dir, "bin_drop_test_scene.usda")
    if os.path.exists(tmp):
        os.remove(tmp)
    layer = Sdf.Layer.CreateNew(tmp, args={"format": "usda"})
    layer.subLayerPaths.append(os.path.relpath(scene, out_dir))
    st = Usd.Stage.Open(layer)
    st.SetDefaultPrim(st.GetPrimAtPath("/World"))
    s = v["object_size"]
    cubes = {}
    for key in ("paper_bin", "plastic_bin"):
        b = {**cfg["bins"]["common"], **cfg["bins"][key]}
        path = f"/World/BinDropTest/{key}_probe"
        cube = UsdGeom.Cube.Define(st, path)
        cube.CreateSizeAttr(float(s))
        start = [b["position"][0] + v["xy_offset"][0], b["position"][1] + v["xy_offset"][1],
                 b["position"][2] + b["height"] + v["drop_height_above_rim"] + s / 2]
        xf = UsdGeom.Xformable(cube)
        xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*start))
        xf.AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 12.0))
        cube.CreateDisplayColorAttr([Gf.Vec3f(0.9, 0.1, 0.1)])
        UsdPhysics.RigidBodyAPI.Apply(cube.GetPrim())
        UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
        UsdPhysics.MassAPI.Apply(cube.GetPrim()).CreateMassAttr(float(v["object_mass"]))
        PhysxSchema.PhysxContactReportAPI.Apply(cube.GetPrim()).CreateThresholdAttr(0.0)
        PhysxSchema.PhysxRigidBodyAPI.Apply(cube.GetPrim()).CreateSleepThresholdAttr(0.0)  # keep simulating at rest
        cubes[key] = {"path": path, "start": start, "bin": b,
                      "bottom_collider": f"{lg.scene_paths(cfg)[key]}/Collision/Bottom/Shape"}
    # Positive control for robot-link contact readback: a light probe dropped onto the fixed robot.
    rb = cfg["robot"]["base_position"]
    probe_path, probe_start = "/World/BinDropTest/robot_contact_probe", [rb[0], rb[1], rb[2] + 0.75]
    probe = UsdGeom.Cube.Define(st, probe_path)
    probe.CreateSizeAttr(0.04)
    UsdGeom.Xformable(probe).AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*probe_start))
    UsdPhysics.RigidBodyAPI.Apply(probe.GetPrim())
    UsdPhysics.CollisionAPI.Apply(probe.GetPrim())
    UsdPhysics.MassAPI.Apply(probe.GetPrim()).CreateMassAttr(0.05)
    layer.Save()
    stage = open_and_wait(tmp)
    ensure_physx()
    rpath = cfg["robot"]["mount_prim"] + "/" + cfg["robot"]["prim_name"]
    art = Articulation(rpath)
    link_paths = list(art.link_paths[0]) if art.link_paths and isinstance(art.link_paths[0], (list, tuple)) else list(art.link_paths)
    session_instrumentation(stage, link_paths, rpath)
    links = RigidPrim(link_paths, contact_filter_paths=[probe_path])
    rps = {k: RigidPrim(c["path"], contact_filter_paths=[c["bottom_collider"]]) for k, c in cubes.items()}
    app_utils.play(commit=True)
    SimulationManager.initialize_physics()
    for k, c in cubes.items():  # explicit initial state after physics warm-up
        rps[k].set_world_poses(positions=[c["start"]])
        rps[k].set_velocities(linear_velocities=[[0, 0, 0]], angular_velocities=[[0, 0, 0]])
    dt = SimulationManager.get_physics_dt()
    t0 = SimulationManager.get_simulation_time()
    n = int(round(v["duration_s"] / dt))
    rec = {k: [] for k in cubes}
    probe_force = []
    q_start = art.get_dof_positions().numpy()[0].copy()
    for step in range(n + 1):
        if step:
            SimulationManager.step(steps=1)
        try:
            probe_force.append(np.linalg.norm(np.asarray(links.get_contact_force_matrix(dt=dt).numpy())[:, 0], axis=1))
        except Exception as exc:
            probe_force.append(None)
        for k, rp in rps.items():
            p, _ = rp.get_world_poses()
            lv, _ = rp.get_velocities()
            try:
                f = float(np.linalg.norm(np.asarray(rp.get_contact_force_matrix(dt=dt).numpy())[0, 0]))
            except Exception:
                f = float("nan")
            rec[k].append((SimulationManager.get_simulation_time() - t0, p.numpy()[0].astype(float), lv.numpy()[0].astype(float), f))
    q_end = art.get_dof_positions().numpy()[0].copy()  # read before stop() invalidates the tensor views
    app_utils.stop(commit=True)
    simulation_app.update()

    results = {"temp_stage": os.path.relpath(tmp, ROOT), "dt": dt, "steps": n, "bins": {}}
    pf = np.array([f for f in probe_force if f is not None]) if any(f is not None for f in probe_force) else None
    lnames = [lp.split("/")[-1] for lp in link_paths]
    hit = {lnames[i]: float(pf[:, i].max()) for i in range(len(lnames)) if pf is not None and pf[:, i].max() > 0}
    results["robot_contact_positive_control"] = {"probe_start": probe_start, "links_with_contact_N": hit,
                                                 "max_joint_disturbance_deg": float(np.degrees(np.abs(q_end[:7] - q_start[:7])).max())}
    check("robot", "link_contact_readback_positive_control", pf is not None and max(hit.values(), default=0) > 0.1,
          links_with_contact=hit, note="probe dropped onto the fixed robot in the temporary stage; proves the link contact view reports real contacts")
    for k, c in cubes.items():
        b = c["bin"]
        t_ = np.array([r[0] for r in rec[k]])
        P = np.array([r[1] for r in rec[k]])
        F = np.array([r[3] for r in rec[k]])
        wt, H = b["wall_thickness"], b["height"]
        cx, cy = b["position"][0], b["position"][1]
        half_in = (b["width"] - 2 * wt) / 2
        rim_z = b["position"][2] + H
        floor_z = b["position"][2] + wt
        hs = s / 2
        cross = np.nonzero(P[:, 2] - hs <= rim_z)[0]
        ic = int(cross[0]) if len(cross) else None
        corner = hs * math.sqrt(2) * 1.0
        inside_at_cross = ic is not None and abs(P[ic, 0] - cx) <= half_in - hs and abs(P[ic, 1] - cy) <= half_in - hs
        min_bottom = float((P[:, 2] - hs).min())
        final = P[-1]
        vfd = np.linalg.norm(np.diff(P[-30:], axis=0) / dt, axis=1).mean()
        contained = abs(final[0] - cx) <= half_in and abs(final[1] - cy) <= half_in and final[2] + hs <= rim_z
        on_floor = abs((final[2] - hs) - floor_z) <= 0.003
        last = t_ >= t_[-1] - 0.3
        mg = v["object_mass"] * cfg["physics"]["gravity_m_s2"]
        info = {"start": c["start"], "final": final.tolist(), "t_cross_rim": float(t_[ic]) if ic is not None else None,
                "xy_at_rim_crossing": P[ic, :2].tolist() if ic is not None else None, "min_bottom_z": min_bottom,
                "floor_top_z": floor_z, "rim_z": rim_z, "final_speed": float(vfd),
                "mean_bottom_contact_force_N": float(np.nanmean(F[last])), "weight_N": mg}
        results["bins"][k] = info
        grp = f"bin_drop_{k}"
        check(grp, "enters_through_open_top", inside_at_cross, xy_at_rim=info["xy_at_rim_crossing"], opening_half_m=half_in)
        check(grp, "falls_inside", ic is not None and final[2] + hs < rim_z, final_top_z=round(final[2] + hs, 4), rim_z=rim_z)
        check(grp, "collides_with_bottom", on_floor and abs(info["mean_bottom_contact_force_N"] - mg) <= 0.15 * mg,
              rest_bottom_z=round(final[2] - hs, 5), floor_top_z=floor_z,
              bottom_contact_force_N=round(info["mean_bottom_contact_force_N"], 4), weight_N=round(mg, 4))
        check(grp, "no_pass_through_bottom", min_bottom >= floor_z - cfg["validation"]["penetration_tolerance_m"],
              min_cube_bottom_z=round(min_bottom, 5), floor_top_z=floor_z)
        check(grp, "remains_contained", contained and vfd <= 0.01, final=final.round(4).tolist(), final_speed=f"{vfd:.2e}")
        with open(os.path.join(out_dir, "trajectories", f"bin_drop_{k}.csv"), "w", newline="") as fcsv:
            w = csv.writer(fcsv)
            w.writerow(["t", "x", "y", "z", "vx", "vy", "vz", "bottom_contact_N"])
            for tt, pp, vv, ff in rec[k]:
                w.writerow([f"{tt:.5f}", *(f"{x:.7g}" for x in pp), *(f"{x:.6g}" for x in vv), f"{ff:.5g}"])
    return results


# ---------------------------------------------------------------------------
# Glass bottle precision placement: static stability inside the target compartment
# ---------------------------------------------------------------------------

def placement_test(cfg, out_dir):
    sp = lg.scene_paths(cfg)
    cells = {tuple(c["index"]): c for c in lg.crate_cells(cfg)}
    target = cells[tuple(cfg["crate"]["target_compartment"])]
    mtc = cfg["manipulation_targets"]["glass_crate"]
    o = cfg["objects"]["glass_bottle"]
    start = [target["centre"][0], target["centre"][1], target["floor_z"] + mtc["final_bottom_above_floor"]]
    scene = os.path.join(ROOT, cfg["paths"]["scene"])
    tmp = os.path.join(out_dir, "glass_placement_test_scene.usda")
    if os.path.exists(tmp):
        os.remove(tmp)
    layer = Sdf.Layer.CreateNew(tmp, args={"format": "usda"})
    layer.subLayerPaths.append(os.path.relpath(scene, out_dir))
    st = Usd.Stage.Open(layer)
    st.SetDefaultPrim(st.GetPrimAtPath("/World"))
    path = "/World/PlacementTest/GlassBottleCopy"
    bp = st.DefinePrim(path, "Xform")
    bp.GetReferences().AddReference(os.path.relpath(os.path.join(ROOT, cfg["paths"]["assets_dir"], "glass_bottle", "glass_bottle.usd"), out_dir))
    UsdGeom.Xformable(bp).AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*start))
    PhysxSchema.PhysxContactReportAPI.Apply(bp).CreateThresholdAttr(0.0)
    PhysxSchema.PhysxRigidBodyAPI.Apply(bp).CreateSleepThresholdAttr(0.0)
    layer.Save()
    stage = open_and_wait(tmp)
    ensure_physx()
    crate_cols = [str(p.GetPath()) for p in Usd.PrimRange(stage.GetPrimAtPath(sp["crate"])) if p.HasAPI(UsdPhysics.CollisionAPI)]
    bottom = [c for c in crate_cols if "/Collision/Bottom/" in c]
    others = [c for c in crate_cols if c not in bottom]
    rp = RigidPrim(path, contact_filter_paths=bottom + others)
    app_utils.play(commit=True)
    SimulationManager.initialize_physics()
    rp.set_world_poses(positions=[start], orientations=[[1.0, 0.0, 0.0, 0.0]])
    rp.set_velocities(linear_velocities=[[0, 0, 0]], angular_velocities=[[0, 0, 0]])
    dt = SimulationManager.get_physics_dt()
    t0 = SimulationManager.get_simulation_time()
    n = int(round(cfg["validation"]["settle_duration_s"] / dt))
    rec = []
    for step in range(n + 1):
        if step:
            SimulationManager.step(steps=1)
        p, q = rp.get_world_poses()
        F = np.linalg.norm(np.asarray(rp.get_contact_force_matrix(dt=dt).numpy())[0], axis=1)
        rec.append((SimulationManager.get_simulation_time() - t0, p.numpy()[0].astype(float), q.numpy()[0].astype(float), F))
    app_utils.stop(commit=True)
    simulation_app.update()
    T = np.array([r[0] for r in rec])
    P = np.array([r[1] for r in rec])
    F = np.array([r[3] for r in rec])
    tilt = np.array([math.degrees(math.acos(min(1.0, rot(r[2])[2, 2]))) for r in rec])
    last = T >= T[-1] - 0.5
    mg = o["mass"] * cfg["physics"]["gravity_m_s2"]
    fb = F[:, :len(bottom)].sum(axis=1)
    fo = F[:, len(bottom):].max(axis=1) if others else np.zeros(len(T))
    R = o["body_diameter"] / 2
    fx, fy = target["free_size_local"]
    off = P[:, :2] - np.array(target["centre"][:2])
    lateral_clear = float(min(min(fx, fy) / 2 - R - np.linalg.norm(off, axis=1).max(), 1.0))
    vfd = float(np.linalg.norm(np.diff(P[last], axis=0) / dt, axis=1).mean())
    res = {"temp_stage": os.path.relpath(tmp, ROOT), "compartment": target["index"], "start": start, "final": P[-1].tolist(),
           "floor_z": target["floor_z"], "max_tilt_deg": float(tilt.max()), "horizontal_drift_m": float(np.linalg.norm(off[-1] - off[0])),
           "height_change_m": float(P[-1, 2] - P[0, 2]), "final_bottom_gap_m": float(P[-1, 2] - target["floor_z"]),
           "floor_force_last_0_5s_N": float(fb[last].mean()), "weight_N": mg, "max_wall_separator_force_N": float(fo.max()),
           "min_lateral_clearance_body_to_compartment_m": lateral_clear, "mean_speed_last_0_5s": vfd,
           "free_compartment_size_m": target["free_size_local"]}
    grp = "glass_placement"
    check(grp, "remains_upright", tilt.max() <= cfg["validation"]["settle_max_tilt_deg"], max_tilt_deg=round(float(tilt.max()), 4))
    check(grp, "supported_by_crate_floor", abs(res["final_bottom_gap_m"]) <= cfg["validation"]["penetration_tolerance_m"]
          and abs(res["floor_force_last_0_5s_N"] - mg) <= 0.1 * mg,
          bottom_gap_mm=round(res["final_bottom_gap_m"] * 1000, 3), floor_force_N=round(res["floor_force_last_0_5s_N"], 4), weight_N=round(mg, 4))
    check(grp, "no_contact_with_walls_or_separators", res["max_wall_separator_force_N"] < 1e-3 and lateral_clear > 0.01,
          max_force_N=res["max_wall_separator_force_N"], min_lateral_clearance_mm=round(lateral_clear * 1000, 2), colliders_checked=len(others))
    check(grp, "stable_no_drift", res["horizontal_drift_m"] <= 0.003 and vfd <= cfg["validation"]["settle_max_speed_m_s"],
          drift_mm=round(res["horizontal_drift_m"] * 1000, 3), mean_speed=f"{vfd:.2e}")
    with open(os.path.join(out_dir, "trajectories", "glass_placement.csv"), "w", newline="") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(["t", "x", "y", "z", "qw", "qx", "qy", "qz", "floor_force_N", "max_wall_separator_force_N", "tilt_deg"])
        for (tt, pp, qq, ff), a_, b_, tl in zip(rec, fb, fo, tilt):
            w.writerow([f"{tt:.5f}", *(f"{x:.7g}" for x in pp), *(f"{x:.6g}" for x in qq), f"{a_:.5g}", f"{b_:.5g}", f"{tl:.5g}"])
    return res


def main():
    cfg = json.load(open(args.config if os.path.isabs(args.config) else os.path.join(ROOT, args.config)))
    out_dir = os.path.join(ROOT, cfg["paths"]["logs_dir"])
    os.makedirs(os.path.join(out_dir, "trajectories"), exist_ok=True)
    scene = os.path.join(ROOT, cfg["paths"]["scene"])
    mtime = os.path.getmtime(scene)
    t0 = time.time()
    settle = settle_test(cfg, out_dir)
    log(f"settle test done in {time.time() - t0:.1f}s")
    t0 = time.time()
    drop = bin_drop_test(cfg, out_dir)
    log(f"bin drop test done in {time.time() - t0:.1f}s")
    placement = None
    if cfg["crate"].get("target_compartment") is not None:
        t0 = time.time()
        placement = placement_test(cfg, out_dir)
        log(f"glass placement test done in {time.time() - t0:.1f}s")
    check("integrity", "final_scene_unmodified", os.path.getmtime(scene) == mtime, scene=os.path.relpath(scene, ROOT))
    json.dump({"checks": CHECKS, "warnings": WARN, "settle": settle, "bin_drop": drop, "glass_placement": placement},
              open(os.path.join(out_dir, "physics_results.json"), "w"), indent=2,
              default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
    failed = [f"{g}.{k}" for g, v in CHECKS.items() for k, c in v.items() if not c["passed"]]
    total = sum(len(v) for v in CHECKS.values())
    log(f"{total - len(failed)}/{total} dynamic checks passed; failed: {failed}")
    return 0 if not failed else 1


code = 1
try:
    code = main()
except Exception:
    traceback.print_exc()
    code = 2
finally:
    simulation_app.close(exit_code=code)
    sys.exit(code)
