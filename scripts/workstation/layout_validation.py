"""Sorting-zone layout validation (called from validate_scene.py inside Isaac Sim's python.sh).

* Collision boxes are built from the static colliders of the *built USD scene* (truth) and cross-checked
  against the analytic model used by optimize_layout.py.
* Layout checks: platform support/stability, destination placement, gaps/intersections, compartments,
  bottle fit, unobstructed bin openings.
* Manipulation targets: the selected sequences are rebuilt from the config, compared with the stored poses,
  and re-evaluated (IK, joint limits/margins, manipulability, endpoint clearance) against the USD boxes.

Evidence levels reported per destination:
  ik_feasible                  every listed pose has a joint-limit-respecting IK solution
  endpoint_collision_checked   robot links + carried object clear the static scene at every listed pose
  sampled_path_collision_checked  crate insertion/retreat only: 1 cm straight-line waypoints, IK + clearance
  full_trajectory_collision_checked  NO (no continuous/swept check, no motion planner)
  manipulation_executed        NO
"""

from __future__ import annotations

import copy
import math

import numpy as np
from pxr import Gf, Usd, UsdGeom, UsdPhysics

import layout_geometry as lg
import manipulation_targets as mt
from robot_geometry import RobotModel


def _obb_from_prim(prim, name, group):
    M = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    c = np.array(M.Transform(Gf.Vec3d(0, 0, 0)))
    cols = [np.array(M.TransformDir(Gf.Vec3d(*e))) for e in np.eye(3)]
    if prim.IsA(UsdGeom.Cube):
        s = UsdGeom.Cube(prim).GetSizeAttr().Get()
        half = np.array([np.linalg.norm(v) * s / 2 for v in cols])
        R = np.column_stack([v / np.linalg.norm(v) for v in cols])
        return lg.OBB(name, c, half, R, group)
    if prim.IsA(UsdGeom.Cylinder):
        cy = UsdGeom.Cylinder(prim)
        r, h = cy.GetRadiusAttr().Get(), cy.GetHeightAttr().Get()
        return lg.OBB(name, c, [r, r, h / 2], np.column_stack([v / np.linalg.norm(v) for v in cols]), group)
    pts = np.array([list(M.Transform(Gf.Vec3d(*p))) for p in UsdGeom.Mesh(prim).GetPointsAttr().Get()])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return lg.OBB(name, (lo + hi) / 2, (hi - lo) / 2, None, group)


def usd_static_boxes(stage, cfg):
    sp = lg.scene_paths(cfg)
    groups = [("/World/Environment/Ground", "ground"), ("/World/Workstation/Table", "table"), (sp["paper_bin"], "paper_bin"),
              (sp["plastic_bin"], "plastic_bin"), (sp["crate_platform"], "platform"), (sp["crate"], "crate"),
              (sp["crate_bottles"], "crate_bottles")]
    out = []
    for root, group in groups:
        rp = stage.GetPrimAtPath(root)
        if not rp.IsValid():
            continue
        for p in Usd.PrimRange(rp, Usd.TraverseInstanceProxies()):
            if not p.HasAPI(UsdPhysics.CollisionAPI):
                continue
            part = p.GetParent().GetName() if p.GetName() == "Shape" else p.GetName()
            if group == "table":
                name = "Tabletop" if "/Tabletop/" in str(p.GetPath()) else str(p.GetPath()).split("/Table/")[1].split("/")[0]
            elif group == "ground":
                name = "ground"
            elif group == "crate_bottles":
                name = f"crate_bottle:{str(p.GetPath()).split('/CrateBottles/')[1].split('/')[0]}/{part}"
            else:
                name = f"{ {'platform': 'platform', 'crate': 'crate'}.get(group, group)}/{part}"
            out.append(_obb_from_prim(p, name, group))
    return out


def run(stage, cfg, check, warn, simulation_app):
    sp = lg.scene_paths(cfg)
    gcfg = cfg["gripper"]
    usd_boxes = usd_static_boxes(stage, cfg)
    by = {b.name: b for b in usd_boxes}
    result = {"usd_static_boxes": len(usd_boxes)}

    # ---- analytic model vs built USD (same geometry the optimiser used) ----
    analytic = lg.table_boxes(cfg) + lg.bin_boxes(cfg, "paper_bin") + lg.bin_boxes(cfg, "plastic_bin") + lg.platform_boxes(cfg) + lg.crate_boxes(cfg)
    diffs = {}
    for a in analytic:
        u = by.get(a.name)
        diffs[a.name] = None if u is None else float(max(np.abs(np.array(u.aabb()) - np.array(a.aabb())).max(), 0))
    missing = [k for k, v in diffs.items() if v is None]
    worst = max((v for v in diffs.values() if v is not None), default=0.0)
    check("layout", "analytic_model_matches_usd_colliders", not missing and worst <= 1e-4, boxes=len(analytic),
          max_aabb_difference_m=worst, missing_in_usd=missing)

    # ---- platform ----
    pf, c = cfg["crate_platform"], cfg["crate"]
    plat = [b for b in usd_boxes if b.group == "platform"]
    crate = [b for b in usd_boxes if b.group == "crate"]
    plo = np.min([b.aabb()[0] for b in plat], axis=0)
    phi = np.max([b.aabb()[1] for b in plat], axis=0)
    clo = np.min([b.aabb()[0] for b in crate], axis=0)
    chi = np.max([b.aabb()[1] for b in crate], axis=0)
    top = by["platform/Top"].aabb()
    pprim = stage.GetPrimAtPath(sp["crate_platform"])
    rb = [str(p.GetPath()) for p in Usd.PrimRange(pprim, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    check("layout", "platform_static_collider", pprim.IsValid() and len(plat) == 3 and not rb, colliders=[b.name for b in plat], rigid_bodies=rb)
    base_w = min(np.array(by["platform/Kick"].h[:2]) * 2)
    check("layout", "platform_stable_base", abs(plo[2]) <= 1e-6 and phi[2] / base_w <= 3.0 and abs(phi[2] - pf["height"]) <= 1e-6,
          on_floor_min_z=float(plo[2]), height_m=float(phi[2]), narrowest_base_m=float(base_w),
          height_to_base_ratio=float(phi[2] / base_w), note="static collider; ratio <= 3 for a visually/physically plausible stand")
    inside = bool(np.all(clo[:2] >= top[0][:2] - 1e-6) and np.all(chi[:2] <= top[1][:2] + 1e-6))
    check("layout", "crate_supported_by_platform", abs(clo[2] - top[1][2]) <= 1e-6 and inside,
          crate_bottom_z=float(clo[2]), platform_top_z=float(top[1][2]), crate_footprint_within_top=inside,
          top_margin_m=[float(clo[0] - top[0][0]), float(top[1][0] - chi[0]), float(clo[1] - top[0][1]), float(top[1][1] - chi[1])])

    # ---- destinations at configured positions, gaps, no intersections ----
    dest = {"paper_bin": [b for b in usd_boxes if b.group == "paper_bin"], "plastic_bin": [b for b in usd_boxes if b.group == "plastic_bin"],
            "crate_platform": plat + crate}
    exp = {"paper_bin": cfg["bins"]["paper_bin"]["position"][:2], "plastic_bin": cfg["bins"]["plastic_bin"]["position"][:2],
           "crate_platform": pf["position"][:2]}
    pos_err = {}
    for k, bx in dest.items():
        lo = np.min([b.aabb()[0] for b in bx], axis=0)
        hi = np.max([b.aabb()[1] for b in bx], axis=0)
        pos_err[k] = float(np.linalg.norm((lo + hi)[:2] / 2 - np.array(exp[k])))
    check("layout", "destinations_at_configured_positions", max(pos_err.values()) <= 0.002, centre_errors_m=pos_err,
          positions={k: v for k, v in exp.items()}, crate_on_platform_at=c["position"])
    table = [b for b in usd_boxes if b.group == "table"]
    gaps = {}
    names = list(dest)
    for i, a in enumerate(names):
        gaps[f"{a}-table"] = lg.min_aabb_gap(dest[a], table)
        for bname in names[i + 1:]:
            gaps[f"{a}-{bname}"] = lg.min_aabb_gap(dest[a], dest[bname])
    gmin = cfg["layout_search"]["min_gap_between_destinations_m"]
    check("layout", "no_destination_intersections", all(v >= gmin - 1e-6 for v in gaps.values()), gaps_m=gaps, minimum_m=gmin)

    # ---- compartments ----
    cells = lg.crate_cells(cfg)
    empty = [cl["index"] for cl in cells if not cl["occupied"]]
    tgt = next(cl for cl in cells if cl["index"] == list(c["target_compartment"]))
    check("layout", "empty_compartment_available", len(empty) >= 1 and not tgt["occupied"], empty=empty, target=tgt["index"])
    o = cfg["objects"]["glass_bottle"]
    clear_x = (tgt["free_size_local"][0] - o["body_diameter"]) / 2
    clear_y = (tgt["free_size_local"][1] - o["body_diameter"]) / 2
    check("layout", "glass_bottle_fits_target_compartment", min(clear_x, clear_y) >= 0.02 and o["height"] <= tgt["rim_z"] - tgt["floor_z"] + 0.1,
          free_size_m=tgt["free_size_local"], bottle_diameter_m=o["body_diameter"], radial_clearance_m=[clear_x, clear_y],
          bottle_height_m=o["height"], compartment_depth_to_rim_m=tgt["rim_z"] - tgt["floor_z"],
          separator_height_m=c["separator_height"])
    # ---- bin openings unobstructed (prism above the inner opening up to 1 m) ----
    for key in ("paper_bin", "plastic_bin"):
        b = {**cfg["bins"]["common"], **cfg["bins"][key]}
        half = (b["width"] - 2 * b["wall_thickness"]) / 2 - 1e-4
        prism = lg.OBB("opening", [b["position"][0], b["position"][1], b["height"] + 0.5], [half, half, 0.5 - 1e-4])
        hits = [x.name for x in usd_boxes if x.group != key and lg.footprint_overlap(x, prism)]
        check("layout", f"{key}_opening_unobstructed", not hits, obstacles_above_opening=hits, opening_half_m=half)

    # ---- manipulation targets ----
    model = RobotModel(cfg, stage, simulation_app)
    fkc = model.fk_consistency()
    check("reachability", "lula_fk_matches_usd_robot", max(v["pos_err_m"] for v in fkc.values()) <= 1e-4
          and max(v["rot_err_deg"] for v in fkc.values()) <= 0.05,
          max_position_error_m=max(v["pos_err_m"] for v in fkc.values()), max_rotation_error_deg=max(v["rot_err_deg"] for v in fkc.values()))
    rng = np.random.default_rng(cfg["layout_search"]["seed"])
    sel = cfg["manipulation_targets"].get("selected", {})
    base_xy = cfg["robot"]["base_position"][:2]
    dyn = lambda excl: lg.tabletop_object_boxes(cfg, exclude=(excl,))
    destinations = {}
    for key in ("paper_bin", "plastic_bin", "glass_crate"):
        s = sel.get(key)
        if not s:
            check("reachability", f"{key}_targets_defined", False, note="run optimize_layout.py --apply")
            continue
        meta = s["meta"]
        obj = cfg["manipulation_targets"][key]["object"]
        if key == "glass_crate":
            seq, _ = mt.crate_sequence(cfg, tgt, math.radians(meta["gripper_yaw_deg"]), cfg["manipulation_targets"]["glass_crate"]["insertion_waypoint_step_m"])
            wsl = cfg["manipulation_targets"]["glass_crate"]["max_joint_step_between_waypoints_rad"]
        else:
            seq, _ = mt.bin_sequence(cfg, key, cfg["bins"][key]["position"][:2], meta["drop_offset_toward_robot_m"],
                                     math.radians(meta["gripper_yaw_deg"]), base_xy)
            wsl = None
        stored = {n: np.array(p["tcp_position"]) for n, p in s["poses"].items()}
        dev = max(float(np.linalg.norm(np.array(p["pos"]) - stored[p["name"]])) for p in seq if p["name"] in stored)
        check("reachability", f"{key}_poses_match_config", dev <= 1e-4, max_deviation_m=dev, poses=list(stored))
        r = mt.evaluate_sequence(model, cfg, seq, usd_boxes + dyn(obj), rng, seeds=cfg["layout_search"]["ik_seeds"],
                                 waypoint_step_limit=wsl)
        poses = r["poses"]
        ends = [p for p in poses if not p.get("waypoint")]
        wps = [p for p in poses if p.get("waypoint")]
        ik_ok = all(p.get("ik_success") for p in poses) and len(poses) == len(seq)
        lim_ok = ik_ok and all(p["within_limits"] for p in poses)
        end_ok = ik_ok and all(p["pose_ok"] for p in ends)
        wp_ok = ik_ok and all(p["pose_ok"] for p in wps) if wps else None
        destinations[key] = {"meta": meta, "summary": r["summary"], "poses": poses, "evidence": {
            "ik_feasible": ik_ok, "joint_limits_respected": lim_ok, "endpoint_collision_checked": True, "endpoints_collision_free": end_ok,
            "sampled_path_collision_checked": bool(wps), "sampled_path_collision_free": wp_ok,
            "full_trajectory_collision_checked": False, "manipulation_executed": False}}
        check("reachability", f"{key}_ik_feasible", ik_ok, poses=len(seq))
        check("reachability", f"{key}_joint_limits", lim_ok, min_joint_margin_frac=r["summary"]["min_joint_margin_frac"],
              min_joint_margin_deg=min((math.degrees(p["min_joint_margin_rad"]) for p in poses if p.get("ik_success")), default=None))
        check("reachability", f"{key}_endpoint_collision_clear", end_ok,
              min_robot_clearance_m=min((p["robot_clearance_m"] for p in ends if p.get("ik_success")), default=None),
              min_object_clearance_m=min((p["carried_object_clearance_m"] for p in ends if p.get("carried_object_clearance_m") is not None), default=None),
              thresholds_m=[gcfg["min_robot_clearance_m"], gcfg["min_carried_object_clearance_m"]])
        if wps:
            check("reachability", f"{key}_sampled_insertion_retreat_clear", wp_ok, waypoints=len(wps),
                  max_joint_step_rad=max(p["max_joint_step_from_previous_rad"] for p in wps),
                  min_finger_clearance_m=min((p["finger_clearance_in_compartment_m"] for p in poses if p.get("finger_clearance_in_compartment_m") is not None), default=None))
    # pickups (objects stay where they are)
    pick = {}
    for key in ("paper_cup", "plastic_bottle", "glass_bottle"):
        best = None
        for yd in cfg["layout_search"]["bin_yaw_candidates_deg"]:
            seq, meta = mt.pickup_sequence(cfg, key, math.radians(yd))
            r = mt.evaluate_sequence(model, cfg, seq, usd_boxes + dyn(key), rng, seeds=cfg["layout_search"]["ik_seeds"])
            r["meta"] = meta
            if best is None or (r["summary"]["feasible"], r["summary"]["score"]) > (best["summary"]["feasible"], best["summary"]["score"]):
                best = r
        pick[key] = best
        check("reachability", f"pickup_{key}_ik_and_endpoint_clear", best["summary"]["feasible"], gripper_yaw_deg=best["meta"]["gripper_yaw_deg"],
              min_robot_clearance_m=best["summary"]["min_robot_clearance_m"], min_joint_margin_frac=best["summary"]["min_joint_margin_frac"])
    result.update(fk_consistency=fkc, destinations=destinations, pickups=pick, analytic_vs_usd=diffs, compartments=cells)
    return result
