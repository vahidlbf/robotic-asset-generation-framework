"""Target derivation, world sanity checks and planning for the home -> PET pre-grasp -> home experiment.

Used by run_motion_experiment.py (both modes). Can also be run alone for a planning-only check:
    "$ISAACSIM_PYTHON" scripts/motion_planning/plan_to_pet.py
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion_utils as mu  # noqa: E402


def world_sanity(planner, hull_model, hull_boxes, prims, mc, rng, opening, n=400):
    """Cross-check the cuMotion obstacle world against the independent hull model on random configurations.
    Positive control: configs the hull model says penetrate static geometry by > 3 cm must be in collision for
    cuMotion. Negative control: configs with > 8 cm hull clearance should not be in collision."""
    planner.refresh()
    pos, neg, dist = [], [], []
    lo, hi = planner.lim[:, 0], planner.lim[:, 1]
    skip = {("panda_link0", "Tabletop")}
    for _ in range(n):
        q = lo + (hi - lo) * rng.random(len(lo))
        r = hull_model.clearance(q, opening, hull_boxes, None, skip=skip)
        c = planner.check_q(q)
        dist.append(r["min_m"])
        if r["min_m"] < -0.03:
            pos.append((c["in_collision"], r["box"]))
        elif r["min_m"] > 0.08:
            neg.append(c["in_collision"])
    # Targeted positive controls: plain (collision-unaware) Lula IK puts the TCP *inside* known obstacles.
    wc = hull_model.cfg
    top = wc["table"]["height"]
    crate = wc["crate"]
    pet = wc["objects"]["plastic_bottle"]
    probes = {"inside_tabletop": [0.30, -0.20, top - 0.015],
              "inside_crate_wall": [crate["position"][0], crate["position"][1] - crate["width"] / 2 + crate["wall_thickness"] / 2,
                                    crate["position"][2] + crate["height"] - 0.03],
              "inside_pet_bottle": [pet["position"][0], pet["position"][1], top + 0.12]}
    targeted = {}
    for name, pt in probes.items():
        sols = hull_model.ik(np.array(pt), mu.topdown_R(0.0), seeds=6, rng=rng)
        if not sols:
            targeted[name] = {"ik": False}
            continue
        q = sols[0][0]
        c = planner.check_q(q)
        r = hull_model.clearance(q, opening, hull_boxes, None, skip=skip)
        targeted[name] = {"ik": True, "tcp_point": pt, "cumotion_in_collision": c["in_collision"], "cumotion_min_distance_m": c["min_distance_m"],
                          "hull_min_m": r["min_m"], "hull_box": r["box"]}
    return {"tracked_obstacle_prims": len(prims), "samples": n, "targeted_positive_controls": targeted,
            "targeted_detected": int(sum(v.get("cumotion_in_collision", False) for v in targeted.values())),
            "targeted_total": int(sum(v.get("ik", False) for v in targeted.values())),
            "random_hull_clearance_percentiles_m": np.percentile(dist, [0, 5, 25, 50]).round(4).tolist() if dist else None,
            "positive_control_configs": len(pos), "positive_detected": int(sum(p[0] for p in pos)),
            "positive_missed_boxes": sorted({p[1] for p in pos if not p[0]})[:10],
            "negative_control_configs": len(neg), "negative_flagged": int(sum(neg))}


def frame_check(planner, art, hand_rp, lula_model=None):
    """cuMotion FK of panda_hand vs. the physics-measured hand link pose at the current configuration,
    and (optionally) the derived TCP vs. the project's Lula right_gripper frame."""
    q = art.get_dof_positions().numpy()[0][:7].astype(float)
    p, o = hand_rp.get_world_poses()
    W_meas = mu.T(mu.quat_to_R(o.numpy()[0]), p.numpy()[0])
    W_fk = planner.hand_world(q)
    out = {"hand_pos_err_m": float(np.linalg.norm(W_fk[:3, 3] - W_meas[:3, 3])), "hand_rot_err_deg": mu.rot_err_deg(W_fk[:3, :3], W_meas[:3, :3])}
    if lula_model is not None:
        lp, lR = lula_model.fk(q)
        tcp = planner.tcp_world(q)
        out.update(tcp_vs_lula_right_gripper_pos_m=float(np.linalg.norm(tcp[:3, 3] - lp)), tcp_vs_lula_rot_deg=mu.rot_err_deg(tcp[:3, :3], lR))
    return out


def derive_target(stage, mc, wc, pet_rp):
    """Pre-grasp TCP pose(s) from the PET's *physics* pose. Returns position, the candidate orientations and evidence."""
    from pxr import Usd, UsdGeom

    t = mc["target"]
    existing = stage.GetPrimAtPath(t["prefer_existing_target_frame"])
    p, q = pet_rp.get_world_poses()
    bottom = p.numpy()[0].astype(float)  # bottom-centre origin
    R_obj = mu.quat_to_R(q.numpy()[0])
    tilt = math.degrees(math.acos(min(1.0, R_obj[2, 2])))
    usd_bottom = np.array(UsdGeom.Xformable(stage.GetPrimAtPath(t["object_prim"])).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation())
    cfg_bottom = np.array([*wc["objects"]["plastic_bottle"]["position"], wc["table"]["height"] + wc["objects"]["clearance"]])
    grasp = bottom + np.array([0, 0, t["grasp_point_height_from_bottom_m"]])
    pre = grasp + np.array([0, 0, t["pre_grasp_clearance_above_grasp_m"]])
    cands = [(f"yaw{int(y)}", mu.T(mu.topdown_R(math.radians(y)), pre)) for y in t["gripper_yaw_candidates_deg"]]
    return {"existing_target_frame": bool(existing and existing.IsValid()), "pet_bottom_physics": bottom.tolist(),
            "pet_bottom_usd": usd_bottom.tolist(), "pet_bottom_config": cfg_bottom.tolist(), "pet_tilt_deg": tilt,
            "physics_vs_config_m": float(np.linalg.norm(bottom - cfg_bottom)), "grasp_point": grasp.tolist(),
            "pre_grasp_tcp_position": pre.tolist(), "fingertip_height_above_pet_top_m":
                float(pre[2] - mc_tip(mc) - (bottom[2] + wc["objects"]["plastic_bottle"]["height"]))}, cands


def mc_tip(mc):
    return 0.0034  # fingertips beyond the TCP (config gripper.fingertip_beyond_tcp_m)


def choose_goal(planner, sols, q_home, hull_model, hull_boxes, mc, opening):
    """Rank collision-free IK solutions: valid, hull clearance, gripper-PET clearance, joint distance from home."""
    skip = {("panda_link0", "Tabletop")}
    pet = [b for b in hull_boxes if b.name.endswith("plastic_bottle")]
    ranked = []
    for s in sols:
        if s["in_collision"] or s["self_collision"] or not s["within_limits"] or s["pos_err_m"] > 0.002 or s["rot_err_deg"] > 1.0:
            continue
        h = hull_model.clearance(s["q"], opening, hull_boxes, None, skip=skip)
        gp = hull_model.clearance(s["q"], opening, pet, None, skip={(f"panda_link{i}", "*") for i in range(8)})
        g = min(gp["per_part"][k] for k in ("panda_hand", "panda_leftfinger", "panda_rightfinger"))
        margin = float(np.minimum(s["q"] - planner.lim[:, 0], planner.lim[:, 1] - s["q"]).min())
        ok = h["min_m"] >= mc["collision"]["min_hull_clearance_m"] and g >= mc["collision"]["min_gripper_to_pet_clearance_m"]
        ranked.append({**s, "q": s["q"], "hull_clearance_m": h["min_m"], "hull_closest": [h["part"], h["box"]],
                       "gripper_to_pet_clearance_m": g, "min_joint_margin_rad": margin,
                       "joint_distance_from_home_rad": float(np.linalg.norm(s["q"] - q_home)), "accepted": ok})
    ranked.sort(key=lambda r: (not r["accepted"], r["joint_distance_from_home_rad"] - 0.5 * min(r["min_joint_margin_rad"], 0.5)))
    return ranked


if __name__ == "__main__":
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    import run_motion_experiment as rme  # noqa: E402

    code = rme.main(["--headless", "--plan-only"], app)
    app.close(exit_code=code)
    sys.exit(code)
