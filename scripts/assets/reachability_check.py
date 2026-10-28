"""Geometric reachability of a derived scene's pickup and drop poses (Lula IK + endpoint collision clearance), headless Isaac.

    "$ISAACSIM_PYTHON" scripts/assets/reachability_check.py --scene config/scenes/industrial_brass_sorting.json \
        --pick-support InputTray --drop FittingA_=sorting_bin_A FittingB_=sorting_bin_B

Reuses scripts/workstation/robot_geometry.RobotModel (NVIDIA's Lula Franka description, the robot's own PhysX collider
hulls, the configured base pose). For every dynamic instance on --pick-support it evaluates a top-down pre-grasp
(TCP 0.10 m above) and grasp pose (TCP at the centre of mass, fingers closing across the part axis); for every
destination container a pre-drop pose (TCP 0.15 m above the rim centre, as bins.drop_tcp_height_above_rim). Each pose:
IK success, joint limits, manipulability, and the smallest distance from the robot (links + hand >= gripper.min_robot_clearance_m;
fingers >= 5 mm, and at the grasp >= 0 to the support floor) to the table, the containers and the other parts (their
collider pieces: boxes as OBBs, convex prisms exactly; the grasped part itself is excluded at the grasp pose). The grasp
TCP is raised above the centre of mass when the finger hulls would otherwise touch the support floor.
This is an endpoint (configuration) check only: no trajectories, no swept collision checking, no grasp physics; it does
not show that pick-and-place can be executed. Writes logs/assets/<scene_id>/reachability.{json,md}.
"""

import argparse
import json
import math
import os
import sys
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("--scene", required=True)
parser.add_argument("--pick-support", required=True)
parser.add_argument("--drop", nargs="+", required=True, help="<instance name prefix>=<destination container instance>")
args, _ = parser.parse_known_args()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "workstation"))
import asset_lib as al  # noqa: E402

from isaacsim import SimulationApp  # noqa: E402

simulation_app = SimulationApp({"headless": True})

import numpy as np  # noqa: E402

import layout_geometry as lg  # noqa: E402
from robot_geometry import LINKS, RobotModel, quat_wxyz_from_R, topdown_R  # noqa: E402

FINGERS = ("panda_leftfinger", "panda_rightfinger")


class ConvexPrism:
    """Convex 8-point prism (asset_lib.collider_pieces) as an obstacle with the layout_geometry.OBB interface. The signed
    distance is max over the face planes: exact inside, a lower bound (conservative) outside."""

    FACES = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]

    def __init__(self, name, points, group):
        self.name, self.group = name, group
        P = np.asarray(points, float)
        c = P.mean(axis=0)
        planes = []
        for f in self.FACES:
            a, b, d = P[f[0]], P[f[1]], P[f[2]]
            n = np.cross(b - a, d - a)
            if np.linalg.norm(n) < 1e-12:
                continue
            n /= np.linalg.norm(n)
            if np.dot(n, c - a) > 0:
                n = -n
            planes.append((n, float(np.dot(n, a))))
        self.N = np.array([p[0] for p in planes])
        self.d = np.array([p[1] for p in planes])
        self.P = P

    def signed_distance(self, pts):
        return (np.asarray(pts, float) @ self.N.T - self.d).max(axis=1)

    def aabb(self):
        return self.P.min(axis=0), self.P.max(axis=0)


def piece_obstacles(name, spec, pose, group):
    """Collider pieces in the world: boxes as OBBs, convex prisms (tapered walls, fitting sectors) as ConvexPrism."""
    R = np.array([al.q_rot(pose["orientation"], e) for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]).T
    out = []
    for pc, (_, wpts) in zip(al.collider_pieces(spec), al.world_pieces(spec, pose)):
        if pc["kind"] == "convex":
            out.append(ConvexPrism(f"{name}/{pc['name']}", wpts, group))
            continue
        P = np.array(pc["points"])
        lo, hi = P.min(axis=0), P.max(axis=0)
        out.append(lg.OBB(f"{name}/{pc['name']}", R @ ((lo + hi) / 2) + np.array(pose["position"]), (hi - lo) / 2, R, group))
    return out


def main():
    import isaacsim.core.experimental.utils.stage as stage_utils

    scene = al.load_scene(args.scene)
    env = al.load_json(scene["environment_config"])
    specs = al.specs_for(scene)
    poses = al.scene_poses(scene, env, specs)
    ok, stage = stage_utils.open_stage(al.abspath(scene["output"]))
    while stage_utils.is_stage_loading():
        simulation_app.update()
    model = RobotModel(env, stage, simulation_app)
    rng = np.random.default_rng(0)
    gcfg = env["gripper"]
    boxes = lg.table_boxes(env)
    for inst in scene["instances"]:
        if al.collider_pieces(specs[inst["asset"]]):
            boxes += piece_obstacles(inst["name"], specs[inst["asset"]], poses[inst["name"]], inst["name"])
    drops = dict(d.split("=", 1) for d in args.drop)
    seeds = env["robot"]["ik"]["seeds"]

    def evaluate(label, pos, R, opening, skip_groups=(), finger_groups=()):
        sols = model.ik(np.array(pos), R, seeds=seeds, rng=rng)
        rec = {"pose": label, "tcp_position": [round(float(x), 5) for x in pos], "tcp_orientation_wxyz": [round(x, 6) for x in quat_wxyz_from_R(R)],
               "finger_opening_m": opening, "ik_success": bool(sols)}
        if not sols:
            rec["feasible"] = False
            return rec
        q, ep, er = min(sols, key=lambda s: np.linalg.norm(s[0] - model.home))
        qual = model.quality(q)
        skip = {("panda_link0", "Tabletop")} | {(f, g) for f in FINGERS for g in finger_groups} | {(p, g) for p in LINKS for g in skip_groups}
        cl = model.clearance(q, opening, boxes, skip=skip)
        robot_min = min(v for k, v in cl["per_part"].items() if k not in FINGERS)
        worst = min((k for k in cl["per_part"] if k not in FINGERS), key=cl["per_part"].get)
        wb = model.clearance(q, opening, boxes, skip=skip | {(p, "*") for p in cl["per_part"] if p != worst})["box"]
        fing = min(cl["per_part"][f] for f in FINGERS)
        fcl = None
        if finger_groups:
            fc = model.clearance(q, opening, [b for b in boxes if b.group in finger_groups],
                                 skip={(p, "*") for p in cl["per_part"] if p not in FINGERS} | {(f, g) for f in FINGERS for g in skip_groups})
            fcl = min(fc["per_part"][f] for f in FINGERS)
        rec.update(fk_position_error_m=ep, fk_orientation_error_deg=er, q_deg=np.degrees(q).round(2).tolist(), **qual,
                   robot_clearance_m=robot_min, finger_clearance_m=fing, finger_clearance_to_support_and_part_m=fcl,
                   closest_robot_part=worst, closest_obstacle_to_robot=wb,
                   closest_part_overall=cl["part"], closest_box_overall=cl["box"])
        rec["feasible"] = bool(qual["within_limits"] and robot_min >= gcfg["min_robot_clearance_m"] and fing >= 0.005
                               and (fcl is None or fcl >= 0.0))
        return rec

    results = {"picks": {}, "drops": {}}
    for inst in scene["instances"]:
        pl = inst["placement"]
        if pl.get("support") != args.pick_support or pl["surface"] != "on_instance":
            continue
        pose = poses[inst["name"]]
        info = al.asset_info(inst["asset"])
        com = np.array(al.q_rot(pose["orientation"], info["mass_properties"]["center_of_mass"])) + np.array(pose["position"])
        axis = np.array(al.q_rot(pose["orientation"], (0, 0, 1)))
        yaw = math.atan2(-axis[1], -axis[0]) if np.hypot(axis[0], axis[1]) > 1e-6 else 0.0  # fingers close across the axis
        R = topdown_R(yaw)
        width = min(al.nominal_size(info["spec"])[:2])
        opening = min(gcfg["max_opening_m"], width + 0.02)
        pre = evaluate("pre_grasp", com + np.array([0, 0, 0.10]), R, opening, skip_groups=())
        grasp = evaluate("grasp", com, R, opening, skip_groups=(inst["name"],), finger_groups=(args.pick_support,))
        lift = 0.003 - (grasp.get("finger_clearance_to_support_and_part_m") or 0.003)
        if grasp["ik_success"] and lift > 0:  # finger hulls reach ~12 mm below the TCP: raise the grasp until they clear the floor by 3 mm
            grasp = evaluate("grasp", com + np.array([0, 0, lift]), R, opening, skip_groups=(inst["name"],), finger_groups=(args.pick_support,))
            grasp["raised_above_com_m"] = lift
        dest = next((v for k, v in drops.items() if inst["name"].startswith(k)), None)
        results["picks"][inst["name"]] = {"asset": inst["asset"], "destination": dest, "com_world": com.round(5).tolist(),
                                          "part_width_m": width, "poses": [pre, grasp], "feasible": pre["feasible"] and grasp["feasible"]}
    for dest in sorted(set(drops.values())):
        pose = poses[dest]
        H = al.nominal_size(specs[next(i["asset"] for i in scene["instances"] if i["name"] == dest)])[2]
        pos = np.array(pose["position"]) + np.array([0, 0, H + env["bins"]["drop_tcp_height_above_rim"]])
        rec = evaluate("pre_drop", pos, topdown_R(0.0), gcfg["max_opening_m"])
        results["drops"][dest] = {"poses": [rec], "feasible": rec["feasible"]}
    allp = [p for v in list(results["picks"].values()) + list(results["drops"].values()) for p in v["poses"]]
    results["summary"] = {"poses": len(allp), "ik_success": sum(p["ik_success"] for p in allp), "feasible": sum(p["feasible"] for p in allp),
                          "infeasible": [f"{k}:{p['pose']}" for k, v in {**results["picks"], **results["drops"]}.items()
                                         for p in v["poses"] if not p["feasible"]],
                          "min_robot_clearance_m": min((p["robot_clearance_m"] for p in allp if p["ik_success"]), default=None),
                          "min_joint_margin_frac": min((p["min_joint_margin_frac"] for p in allp if p["ik_success"]), default=None),
                          "scope": "Lula IK + endpoint clearance (robot collider hulls vs. collider OBBs); no trajectories, no grasp "
                                   "physics; not evidence of executable pick-and-place"}
    out = al.abspath(f"logs/assets/{scene['scene_id']}")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "reachability.json"), "w") as f:
        json.dump(results, f, indent=2, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
    o = [f"# Reachability (geometric): `{scene['scene_id']}`\n", f"- {results['summary']['scope']}",
         f"- Poses: {len(allp)}; IK solved: {results['summary']['ik_success']}; feasible (limits + clearance): "
         f"{results['summary']['feasible']}; infeasible: {results['summary']['infeasible'] or 'none'}",
         f"- Minimum robot clearance {results['summary']['min_robot_clearance_m']:.4f} m (required {gcfg['min_robot_clearance_m']} m); "
         f"minimum joint margin {results['summary']['min_joint_margin_frac']:.3f} of range\n",
         "| Target | Pose | TCP (m) | IK | Joint margin | Manipulability | Links + hand clearance (m) | Finger clearance (m) | "
         "Fingers to support floor (m) | Feasible |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in {**results["picks"], **results["drops"]}.items():
        for p in v["poses"]:
            if p["ik_success"]:
                fs = p["finger_clearance_to_support_and_part_m"]
                o.append(f"| {k} | {p['pose']} | {p['tcp_position']} | yes | {p['min_joint_margin_frac']:.3f} | {p['manipulability']:.3f} | "
                         f"{p['robot_clearance_m']:.4f} ({p['closest_robot_part']} - {p['closest_obstacle_to_robot']}) | {p['finger_clearance_m']:.4f} | "
                         f"{'' if fs is None else f'{fs:.4f}'} | {'yes' if p['feasible'] else '**no**'} |")
            else:
                o.append(f"| {k} | {p['pose']} | {p['tcp_position']} | **no** | | | | | | **no** |")
    o.append(f"\nCriteria: within joint limits; links + hand >= {gcfg['min_robot_clearance_m']} m (gripper.min_robot_clearance_m) from "
             "the table, containers and other parts; fingers >= 5 mm from everything except the grasped part; at the grasp the "
             "fingers clear the support floor (the TCP is raised above the part's centre of mass when the finger hulls would "
             "touch it). Obstacles are the collider pieces themselves (boxes as OBBs, tapered walls and fitting sectors as convex "
             "prisms; outside distances are lower bounds).")
    with open(os.path.join(out, "reachability.md"), "w") as f:
        f.write("\n".join(o) + "\n")
    print(f"[reach] {results['summary']['feasible']}/{len(allp)} poses feasible; infeasible {results['summary']['infeasible']}", flush=True)
    return 0


code = 1
try:
    code = main()
except Exception:
    traceback.print_exc()
    code = 2
finally:
    simulation_app.close(exit_code=code)
    sys.exit(code)
