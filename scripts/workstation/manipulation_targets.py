"""Target-pose sequences for the three sorting destinations and their evaluation.

A sequence is an ordered list of TCP poses (position + top-down orientation with a gripper yaw, finger
opening, carried object, allowed contacts). evaluate_sequence() solves IK pose by pose (warm-starting
from the previous pose, several branches), and at every solved configuration computes joint-limit
margins, manipulability and the endpoint clearance of all robot links + carried object against the
static scene boxes. Consecutive-pose joint jumps are reported. This is NOT a motion plan: clearance is
checked only at the listed poses (and, for the crate insertion/retreat, at discretely sampled waypoints).
"""

from __future__ import annotations

import math

import numpy as np

import layout_geometry as lg
from robot_geometry import carried_points, quat_wxyz_from_R, topdown_R


def _bin_rim_and_centre(cfg, key, xy):
    b = {**cfg["bins"]["common"], **cfg["bins"][key]}
    return b["height"], np.array([xy[0], xy[1]]), b


def bin_sequence(cfg, key, xy, offset, yaw, base_xy):
    mt = cfg["manipulation_targets"][key]
    obj = mt["object"]
    g = cfg["objects"][obj]["grasp"]
    rim, centre, b = _bin_rim_and_centre(cfg, key, xy)
    toward = np.asarray(base_xy) - centre
    toward = toward / max(np.linalg.norm(toward), 1e-9)
    drop_xy = centre + toward * offset
    R = topdown_R(yaw)
    tcp_xy = drop_xy - R[:2, 1] * g["tcp_offset_along_finger_axis_m"]  # object centre over the drop point
    w = g["grasp_width_m"]
    z = lambda clear: rim + clear + g["tcp_height_from_bottom"]
    seq = [
        {"name": "pre_drop", "pos": [*tcp_xy, z(mt["pre_drop_bottom_above_rim"])], "R": R, "opening": w, "carried": obj},
        {"name": "drop", "pos": [*tcp_xy, z(mt["drop_bottom_above_rim"])], "R": R, "opening": w, "carried": obj},
        {"name": "retreat", "pos": [*tcp_xy, z(mt["drop_bottom_above_rim"]) + mt["retreat_tcp_lift"]], "R": R,
         "opening": min(w + cfg["gripper"]["release_extra_opening_m"], cfg["gripper"]["max_opening_m"]), "carried": None},
    ]
    meta = {"drop_xy": drop_xy.tolist(), "drop_offset_toward_robot_m": offset, "gripper_yaw_deg": math.degrees(yaw),
            "rim_z": rim, "opening_inner_half_m": (b["width"] - 2 * b["wall_thickness"]) / 2}
    return seq, meta


def crate_sequence(cfg, cell, yaw, step):
    mt = cfg["manipulation_targets"]["glass_crate"]
    g = cfg["objects"]["glass_bottle"]["grasp"]
    R = topdown_R(yaw)
    w = g["grasp_width_m"]
    wo = min(w + cfg["gripper"]["release_extra_opening_m"], cfg["gripper"]["max_opening_m"])
    c = np.array(cell["centre"][:2])
    gh = g["tcp_height_from_bottom"]
    rim, floor = cell["rim_z"], cell["floor_z"]
    z_pre = rim + mt["pre_place_bottom_above_rim"] + gh
    z_ins = rim + mt["insertion_start_bottom_above_rim"] + gh
    z_fin = floor + mt["final_bottom_above_floor"] + gh
    z_ret = rim + mt["retreat_tcp_above_rim"]
    contact = {("carried_object", "crate/Bottom")}
    seq = [{"name": "pre_place", "pos": [*c, z_pre], "R": R, "opening": w, "carried": "glass_bottle"},
           {"name": "insertion_start", "pos": [*c, z_ins], "R": R, "opening": w, "carried": "glass_bottle"}]
    for k, zz in enumerate(np.arange(z_ins - step, z_fin + 1e-9, -step)):
        seq.append({"name": f"insert_wp{k:02d}", "pos": [*c, float(zz)], "R": R, "opening": w, "carried": "glass_bottle",
                    "waypoint": True, "skip": contact, "in_compartment": zz - gh < cell["separator_top_z"]})
    seq.append({"name": "final_place", "pos": [*c, z_fin], "R": R, "opening": w, "carried": "glass_bottle", "skip": contact,
                "in_compartment": True})
    seq.append({"name": "release", "pos": [*c, z_fin], "R": R, "opening": wo, "carried": None, "in_compartment": True,
                "bottle_left_at": [*c, floor + mt["final_bottom_above_floor"]]})
    for k, zz in enumerate(np.arange(z_fin + step, z_ret - 1e-9, step)):
        seq.append({"name": f"retreat_wp{k:02d}", "pos": [*c, float(zz)], "R": R, "opening": wo, "carried": None,
                    "waypoint": True, "bottle_left_at": [*c, floor + mt["final_bottom_above_floor"]]})
    seq.append({"name": "retreat_vertical", "pos": [*c, z_ret], "R": R, "opening": wo, "carried": None,
                "bottle_left_at": [*c, floor + mt["final_bottom_above_floor"]]})
    meta = {"compartment": cell["index"], "compartment_centre": cell["centre"], "free_size_local": cell["free_size_local"],
            "floor_z": floor, "rim_z": rim, "separator_top_z": cell["separator_top_z"], "gripper_yaw_deg": math.degrees(yaw),
            "finger_axis_world": R[:, 1].tolist()}
    return seq, meta


def pickup_sequence(cfg, key, yaw):
    """Pre-grasp / grasp / lift for an object at its configured tabletop position (top-down)."""
    o = cfg["objects"][key]
    g = o["grasp"]
    R = topdown_R(yaw)
    top = cfg["table"]["position"][2] + cfg["table"]["height"] + cfg["objects"]["clearance"]
    centre = np.array(o["position"][:2])
    tcp_xy = centre - R[:2, 1] * g["tcp_offset_along_finger_axis_m"]
    z = top + g["tcp_height_from_bottom"]
    w_open = min(g["grasp_width_m"] + cfg["gripper"]["release_extra_opening_m"], cfg["gripper"]["max_opening_m"])
    at = [centre[0], centre[1], top]
    seq = [{"name": "pre_grasp", "pos": [*tcp_xy, z + 0.12], "R": R, "opening": w_open, "carried": None, "grasp_target": (key, at)},
           {"name": "grasp", "pos": [*tcp_xy, z], "R": R, "opening": g["grasp_width_m"], "carried": None, "grasp_target": (key, at)},
           {"name": "lift", "pos": [*tcp_xy, z + 0.10], "R": R, "opening": g["grasp_width_m"], "carried": key}]
    return seq, {"object": key, "gripper_yaw_deg": math.degrees(yaw), "object_centre": centre.tolist()}


def object_profile_boxes(cfg, key, at, group):
    o = cfg["objects"][key]
    if key == "glass_bottle":
        return lg.bottle_profile_boxes(cfg, f"{group}/{key}", at, group)
    if key == "plastic_bottle":
        R, zb, zs, H = o["body_diameter"] / 2, o["body_top_z"], o["shoulder_top_z"], o["height"]
        rc = o["cap_diameter"] / 2
        x, y, zz = at
        return [lg.OBB(f"{group}/{key}/body", [x, y, zz + zb / 2], [R, R, zb / 2], group=group),
                lg.OBB(f"{group}/{key}/shoulder", [x, y, zz + (zb + zs) / 2], [(R + rc) / 2] * 2 + [(zs - zb) / 2], group=group),
                lg.OBB(f"{group}/{key}/neck", [x, y, zz + (zs + H) / 2], [rc, rc, (H - zs) / 2], group=group)]
    r = o["top_diameter"] / 2
    return [lg.OBB(f"{group}/{key}", [at[0], at[1], at[2] + o["height"] / 2], [r, r, o["height"] / 2], group=group)]


def placed_bottle_boxes(cfg, at):
    return lg.bottle_profile_boxes(cfg, "placed_glass_bottle", at, "placed_bottle")


def evaluate_sequence(model, cfg, seq, boxes, rng, seeds=4, branches=3, joint_step_limit=0.6, waypoint_step_limit=None,
                      endpoints_only=False):
    if endpoints_only:
        seq = [p for p in seq if not p.get("waypoint")]
    gcfg = cfg["gripper"]
    base_skip = {("panda_link0", "Tabletop")}
    first = seq[0]
    starts = model.ik(np.array(first["pos"]), first["R"], seeds=seeds, rng=rng)
    starts = sorted(starts, key=lambda s: np.linalg.norm(s[0] - model.home))[:branches]
    best = None
    for q0, _, _ in starts:
        res, q_prev, ok_all = [], None, True
        for pose in seq:
            sols = model.ik(np.array(pose["pos"]), pose["R"], warm=q0 if q_prev is None else q_prev, seeds=0, rng=rng)
            if not sols:
                res.append({"name": pose["name"], "ik_success": False})
                ok_all = False
                break
            q, ep, er = min(sols, key=lambda s: np.linalg.norm(s[0] - (q0 if q_prev is None else q_prev)))
            carried = None
            if pose.get("carried"):
                carried, _ = carried_points(cfg, pose["carried"], pose["pos"], pose["R"])
            bx = list(boxes)
            if pose.get("bottle_left_at"):
                bx += placed_bottle_boxes(cfg, pose["bottle_left_at"])
            if pose.get("carried"):  # the carried object is no longer an obstacle at its pickup position
                bx = [b for b in bx if not (b.group == "tabletop_objects" and b.name.endswith(pose["carried"]))]
            skip = base_skip | set(pose.get("skip", ()))
            released_cl = None
            if pose.get("grasp_target"):  # fingers straddle the object; the hand must still clear it
                gk, gat = pose["grasp_target"]
                bx = [b for b in bx if b.group != "tabletop_objects" or not b.name.endswith(gk)]
                gboxes = object_profile_boxes(cfg, gk, gat, "grasp_target")
                rel = model.clearance(q, pose["opening"], gboxes, None,
                                      skip={(p, "*") for p in ["panda_link%d" % i for i in range(8)] + ["panda_leftfinger", "panda_rightfinger"]})
                released_cl = rel["per_part"]["panda_hand"]
            if pose.get("bottle_left_at"):
                gparts = ("panda_hand", "panda_leftfinger", "panda_rightfinger")
                rel = model.clearance(q, pose["opening"], [b for b in bx if b.group == "placed_bottle"], None,
                                      skip={(p, "*") for p in ["panda_link%d" % i for i in range(8)]})
                released_cl = min(rel["per_part"][g_] for g_ in gparts)
                skip |= {(g_, "placed_bottle") for g_ in gparts}
            if pose.get("in_compartment"):  # fingers are allowed closer to the separators/walls inside the compartment
                skip |= {("panda_leftfinger", "*"), ("panda_rightfinger", "*")}
            cl = model.clearance(q, pose["opening"], bx, carried, skip=skip)
            finger_cl = None
            if pose.get("in_compartment"):
                fc = model.clearance(q, pose["opening"], [b for b in bx if b.group in ("crate", "crate_bottles")], None,
                                     skip={(p, "*") for p in ["panda_link%d" % i for i in range(8)] + ["panda_hand"]})
                finger_cl = min(fc["per_part"]["panda_leftfinger"], fc["per_part"]["panda_rightfinger"])
            qual = model.quality(q)
            step = float(np.abs(q - q_prev).max()) if q_prev is not None else 0.0
            robot_min = min(v for k, v in cl["per_part"].items() if k != "carried_object")
            obj_min = cl["per_part"].get("carried_object")
            limit = waypoint_step_limit if (pose.get("waypoint") and waypoint_step_limit) else joint_step_limit
            ok = (qual["within_limits"] and robot_min >= gcfg["min_robot_clearance_m"]
                  and (obj_min is None or obj_min >= gcfg["min_carried_object_clearance_m"])
                  and (finger_cl is None or finger_cl >= gcfg["min_finger_clearance_in_compartment_m"])
                  and (released_cl is None or released_cl >= gcfg["min_gripper_clearance_to_released_object_m"])
                  and step <= limit)
            res.append({"name": pose["name"], "ik_success": True, "tcp_position": [round(float(x), 5) for x in pose["pos"]],
                        "tcp_orientation_wxyz": [round(x, 6) for x in quat_wxyz_from_R(pose["R"])],
                        "finger_opening_m": pose["opening"], "carried": pose.get("carried"),
                        "fk_position_error_m": ep, "fk_orientation_error_deg": er, "q_rad": q.round(5).tolist(),
                        "q_deg": np.degrees(q).round(2).tolist(), **qual,
                        "robot_clearance_m": robot_min, "closest_robot_part": cl["part"], "closest_box": cl["box"],
                        "carried_object_clearance_m": obj_min, "finger_clearance_in_compartment_m": finger_cl, "gripper_clearance_to_released_bottle_m": released_cl,
                        "max_joint_step_from_previous_rad": step, "waypoint": bool(pose.get("waypoint")), "pose_ok": bool(ok)})
            ok_all &= ok
            q_prev = q
        endpoints = [r for r in res if r.get("ik_success") and not r.get("waypoint")]
        allr = [r for r in res if r.get("ik_success")]
        summary = {"feasible": bool(ok_all and len(res) == len(seq)),
                   "min_joint_margin_frac": min((r["min_joint_margin_frac"] for r in allr), default=0.0),
                   "min_manipulability": min((r["manipulability"] for r in allr), default=0.0),
                   "min_robot_clearance_m": min((r["robot_clearance_m"] for r in allr), default=-1.0),
                   "min_object_clearance_m": min((r["carried_object_clearance_m"] for r in allr if r["carried_object_clearance_m"] is not None), default=None),
                   "max_joint_step_rad": max((r["max_joint_step_from_previous_rad"] for r in allr), default=0.0),
                   "poses_evaluated": len(res), "poses_total": len(seq), "endpoint_count": len(endpoints)}
        w = cfg["layout_search"]["weights"]
        summary["score"] = (w["joint_margin"] * summary["min_joint_margin_frac"] / 0.5 + w["manipulability"] * summary["min_manipulability"] / 0.1
                            + w["clearance"] * min(summary["min_robot_clearance_m"], 0.1) / 0.1) if summary["feasible"] else -1e9
        cand = {"summary": summary, "poses": res}
        if best is None or (cand["summary"]["feasible"], cand["summary"]["score"], len(res)) > (best["summary"]["feasible"], best["summary"]["score"], len(best["poses"])):
            best = cand
    return best or {"summary": {"feasible": False, "score": -1e9, "min_joint_margin_frac": None, "min_manipulability": None,
                                "min_robot_clearance_m": None, "min_object_clearance_m": None, "max_joint_step_rad": None,
                                "poses_evaluated": 0, "poses_total": len(seq), "endpoint_count": 0,
                                "failure": f"no IK solution for the first pose '{seq[0]['name']}'"},
                    "poses": [{"name": seq[0]["name"], "ik_success": False}]}


def static_boxes(cfg, include=("table", "ground", "bins", "platform", "crate", "crate_bottles", "objects"), exclude_object=None,
                 bins_xy=None, crate=None):
    """crate: dict(xy, base_z, yaw, platform_xy, platform_height) to override the config."""
    out = []
    if "table" in include:
        out += lg.table_boxes(cfg)
    if "ground" in include:
        out.append(lg.ground_box(cfg))
    if "bins" in include:
        for k in ("paper_bin", "plastic_bin"):
            out += lg.bin_boxes(cfg, k, None if not bins_xy or k not in bins_xy else [*bins_xy[k], 0.0])
    cr = crate or {}
    if "platform" in include:
        out += lg.platform_boxes(cfg, cr.get("platform_xy"), cr.get("platform_height"), cr.get("yaw"))
    if "crate" in include:
        out += lg.crate_boxes(cfg, cr.get("xy"), cr.get("base_z"), cr.get("yaw"))
    if "crate_bottles" in include:
        out += lg.crate_bottle_boxes(cfg, cr.get("xy"), cr.get("base_z"), cr.get("yaw"))
    if "objects" in include:
        out += lg.tabletop_object_boxes(cfg, exclude=(exclude_object,) if exclude_object else ())
    return out
