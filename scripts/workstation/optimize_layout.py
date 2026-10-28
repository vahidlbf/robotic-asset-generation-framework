"""Search a collision-aware, IK-feasible layout for the sorting zone (paper bin, plastic bin, crate on platform).

    "$ISAACSIM_PYTHON" scripts/workstation/optimize_layout.py [--apply] [--config ...]

Stage 1: every destination is evaluated on its candidate grid (config layout_search) against the table,
         ground and tabletop objects, plus its own geometry: bins with their drop sequence (pre_drop, drop,
         retreat) for several drop points and gripper yaws; the crate on its platform for every height, yaw
         and empty compartment with the full precision-placement sequence (coarse waypoints).
Stage 2: candidate trios are combined (no overlaps, gaps to the table/legs and between destinations) and
         ranked by summed score minus a compactness penalty; the best trios are re-evaluated with ALL
         destination geometry present and fine (1 cm) insertion waypoints. The first fully feasible trio wins.
--apply writes the chosen layout and target poses into the config (single source of truth).
Robot mounting is kept fixed (config robot.base_position / base_yaw_deg).
Outputs logs/workstation/layout_search.json.
"""

import argparse
import copy
import itertools
import json
import math
import os
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="config/waste_sorting_environment.json")
parser.add_argument("--apply", action="store_true")
parser.add_argument("--top-k", type=int, default=12)
args, _ = parser.parse_known_args()
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from isaacsim import SimulationApp  # noqa: E402

app = SimulationApp({"headless": True})

import numpy as np  # noqa: E402
from pxr import Usd  # noqa: E402

import layout_geometry as lg  # noqa: E402
import manipulation_targets as mt  # noqa: E402
from robot_geometry import RobotModel  # noqa: E402


def log(*a):
    print("[layout]", *a, flush=True)


def outside_table(cfg, boxes, gap):
    table = lg.table_boxes(cfg)
    return all(not lg.footprint_overlap(b, t, gap) for b in boxes for t in table)


def eval_bin(model, cfg, key, xy, rng, fine=False, extra_boxes=()):
    ls = cfg["layout_search"]
    base_xy = cfg["robot"]["base_position"][:2]
    boxes = mt.static_boxes(cfg, include=("table", "ground", "objects"), exclude_object=cfg["manipulation_targets"][key]["object"])
    boxes += lg.bin_boxes(cfg, key, [*xy, 0.0]) + list(extra_boxes)
    best = None
    for off in cfg["manipulation_targets"][key]["drop_xy_offsets_toward_robot_m"]:
        for yd in ls["bin_yaw_candidates_deg"]:
            seq, meta = mt.bin_sequence(cfg, key, xy, off, math.radians(yd), base_xy)
            r = mt.evaluate_sequence(model, cfg, seq, boxes, rng, seeds=ls["ik_seeds"])
            r["meta"] = meta
            if best is None or r["summary"]["score"] > best["summary"]["score"]:
                best = r
    dist = float(np.linalg.norm(np.array(xy) - np.array(base_xy)))
    best["summary"]["distance_from_base_m"] = dist
    best["summary"]["score_total"] = best["summary"]["score"] - ls["weights"]["distance"] * dist
    return best


def eval_crate(model, cfg, cand, rng, step, extra_boxes=()):
    ls = cfg["layout_search"]
    c2 = copy.deepcopy(cfg)
    c2["crate"]["position"] = [*cand["xy"], cand["height"]]
    c2["crate"]["yaw_deg"] = cand["yaw"]
    boxes = mt.static_boxes(c2, include=("table", "ground", "objects", "platform", "crate", "crate_bottles"),
                            exclude_object="glass_bottle",
                            crate={"xy": cand["xy"], "base_z": cand["height"], "yaw": cand["yaw"],
                                   "platform_xy": cand["xy"], "platform_height": cand["height"]})
    boxes += list(extra_boxes)
    best, options = None, []
    wsl = c2["manipulation_targets"]["glass_crate"]["max_joint_step_between_waypoints_rad"]
    shoulder = np.array(cfg["robot"]["base_position"]) + np.array([0, 0, cfg["robot"]["shoulder_height_m"]])
    for cell in lg.crate_cells(c2):
        if cell["occupied"]:
            continue
        top = np.array([*cell["centre"][:2], cell["rim_z"] + 0.3])
        if np.linalg.norm(np.array([*cell["centre"][:2], cell["floor_z"] + 0.21]) - shoulder) > 0.95:
            continue  # cheap reach pre-filter (well beyond the 0.855 m nominal reach incl. the tool)
        ax = np.array(cell["local_x_axis_world"][:2])
        for along in ("x", "y"):
            a = ax if along == "x" else np.array([-ax[1], ax[0]])
            for sign in (1, -1):
                # finger axis (sin yaw, -cos yaw) aligned with the chosen compartment axis
                fa = sign * a
                yaw = math.atan2(fa[0], -fa[1])
                seq, meta = mt.crate_sequence(c2, cell, yaw, step)
                meta["finger_axis_along"] = f"crate local {along}"
                r = mt.evaluate_sequence(model, c2, seq, boxes, rng, seeds=ls["ik_seeds"], branches=2, endpoints_only=True)
                options.append((r["summary"]["feasible"], r["summary"]["score"], seq, meta))
    options.sort(key=lambda t: (t[0], t[1]), reverse=True)
    for feas, _, seq, meta in options[:2]:  # full sequence (with waypoints) only for the best endpoint options
        if not feas:
            break
        r = mt.evaluate_sequence(model, c2, seq, boxes, rng, seeds=ls["ik_seeds"], branches=2, waypoint_step_limit=wsl)
        r["meta"] = meta
        if best is None or (r["summary"]["feasible"], r["summary"]["score"]) > (best["summary"]["feasible"], best["summary"]["score"]):
            best = r
    if best is None:
        best = {"summary": {"feasible": False, "score": -1e9, "min_robot_clearance_m": None, "min_joint_margin_frac": None,
                            "min_manipulability": None, "poses_evaluated": 0, "poses_total": 0},
                "meta": options[0][3] if options else {}, "poses": []}
    dist = float(np.linalg.norm(np.array(cand["xy"]) - np.array(cfg["robot"]["base_position"][:2])))
    best["summary"]["distance_from_base_m"] = dist
    best["summary"]["score_total"] = best["summary"]["score"] - ls["weights"]["distance"] * dist
    return best


def main():
    cfg_path = os.path.join(ROOT, args.config)
    cfg = json.load(open(cfg_path))
    ls = cfg["layout_search"]
    rng = np.random.default_rng(ls["seed"])
    stage = Usd.Stage.Open(os.path.join(ROOT, cfg["paths"]["scene"]))
    model = RobotModel(cfg, stage, app)
    fkc = model.fk_consistency()
    log("FK vs USD link frames (max):", max(v["pos_err_m"] for v in fkc.values()), "m,",
        max(v["rot_err_deg"] for v in fkc.values()), "deg")
    gap_t = ls["min_gap_to_table_m"]
    out = {"fk_consistency": fkc, "bins": {}, "crate": [], "chosen": None}

    # ---- stage 1: bins ----
    t0 = time.time()
    for key in ("paper_bin", "plastic_bin"):
        res = []
        for x, y in itertools.product(ls["bin_x"], ls["bin_y"]):
            if not outside_table(cfg, lg.bin_boxes(cfg, key, [x, y, 0.0]), gap_t):
                continue
            r = eval_bin(model, cfg, key, [x, y], rng)
            res.append({"xy": [x, y], **{k: r["summary"][k] for k in ("feasible", "score", "score_total", "min_robot_clearance_m",
                                                                     "min_joint_margin_frac", "min_manipulability", "distance_from_base_m")},
                        "meta": r["meta"]})
        out["bins"][key] = res
        log(f"{key}: {sum(r['feasible'] for r in res)}/{len(res)} candidate positions feasible ({time.time() - t0:.0f}s)")

    # ---- stage 1: crate on platform ----
    cands = [{"xy": [x, y]} for x, y in itertools.product(ls["crate_x"], ls["crate_y"])] + [{"xy": xy} for xy in ls["front_crate_xy"]]
    full = []
    for c in cands:
        for h in ls["platform_heights"]:
            for yaw in ls["crate_yaws_deg"]:
                cand = {"xy": c["xy"], "height": h, "yaw": yaw}
                c2 = copy.deepcopy(cfg)
                c2["crate_platform"]["yaw_deg"] = yaw
                plat = lg.platform_boxes(c2, cand["xy"], h, yaw)
                if not outside_table(cfg, plat, gap_t):
                    continue
                full.append(cand)
    for i, cand in enumerate(full):
        c2 = copy.deepcopy(cfg)
        c2["crate_platform"]["yaw_deg"] = cand["yaw"]
        r = eval_crate(model, c2, cand, rng, step=0.03)
        out["crate"].append({**cand, **{k: r["summary"][k] for k in ("feasible", "score", "score_total", "min_robot_clearance_m",
                                                                     "min_joint_margin_frac", "min_manipulability", "distance_from_base_m",
                                                                     "poses_evaluated", "poses_total")}, "meta": r["meta"]})
        if (i + 1) % 20 == 0:
            log(f"crate candidates {i + 1}/{len(full)} ({time.time() - t0:.0f}s), feasible so far {sum(c['feasible'] for c in out['crate'])}")
    log(f"crate: {sum(c['feasible'] for c in out['crate'])}/{len(out['crate'])} candidates feasible")

    # ---- stage 2: combine ----
    P = sorted([r for r in out["bins"]["paper_bin"] if r["feasible"]], key=lambda r: -r["score_total"])[:15]
    Q = sorted([r for r in out["bins"]["plastic_bin"] if r["feasible"]], key=lambda r: -r["score_total"])[:15]
    C = sorted([r for r in out["crate"] if r["feasible"]], key=lambda r: -r["score_total"])[:15]
    gap = ls["min_gap_between_destinations_m"]
    combos = []
    for p, q, c in itertools.product(P, Q, C):
        c2 = copy.deepcopy(cfg)
        c2["crate_platform"]["yaw_deg"] = c["yaw"]
        bp, bq = lg.bin_boxes(cfg, "paper_bin", [*p["xy"], 0]), lg.bin_boxes(cfg, "plastic_bin", [*q["xy"], 0])
        pc = lg.platform_boxes(c2, c["xy"], c["height"], c["yaw"])
        groups = [bp, bq, pc]
        if any(lg.footprint_overlap(a, b, gap) for g1, g2 in itertools.combinations(groups, 2) for a in g1 for b in g2):
            continue
        pts = np.array([p["xy"], q["xy"], c["xy"]])
        spread = float(np.linalg.norm(pts - pts.mean(axis=0), axis=1).mean())
        bins_gap = float(np.linalg.norm(np.array(p["xy"]) - np.array(q["xy"]))) - cfg["bins"]["common"]["width"]
        tidy = abs(bins_gap - 0.06) + abs(p["xy"][0] - q["xy"][0])  # bins side by side, small even gap
        combos.append({"paper": p, "plastic": q, "crate": c, "spread": spread, "bins_gap": bins_gap,
                       "rank": p["score_total"] + q["score_total"] + c["score_total"] - 1.0 * spread - 1.0 * tidy})
    combos.sort(key=lambda d: -d["rank"])
    log(f"{len(combos)} non-overlapping combinations; re-evaluating the best {min(args.top_k, len(combos))} with all geometry")
    for k, cb in enumerate(combos[:args.top_k]):
        c2 = copy.deepcopy(cfg)
        c2["bins"]["paper_bin"]["position"] = [*cb["paper"]["xy"], 0.0]
        c2["bins"]["plastic_bin"]["position"] = [*cb["plastic"]["xy"], 0.0]
        c2["crate"]["position"] = [*cb["crate"]["xy"], cb["crate"]["height"]]
        c2["crate"]["yaw_deg"] = cb["crate"]["yaw"]
        c2["crate_platform"].update(position=[*cb["crate"]["xy"], 0.0], height=cb["crate"]["height"], yaw_deg=cb["crate"]["yaw"])
        allb = lambda excl: mt.static_boxes(c2, exclude_object=excl)
        res = {}
        for key in ("paper_bin", "plastic_bin"):
            others = [b for b in allb(c2["manipulation_targets"][key]["object"]) if b.group not in (key,)]
            # eval_bin adds table/ground/objects + this bin; give it the other destinations as extra geometry
            extra = [b for b in others if b.group in ("paper_bin", "plastic_bin", "platform", "crate", "crate_bottles")]
            res[key] = eval_bin(model, c2, key, cb["paper" if key == "paper_bin" else "plastic"]["xy"], rng, extra_boxes=extra)
        extra = [b for b in allb("glass_bottle") if b.group in ("paper_bin", "plastic_bin")]
        res["glass_crate"] = eval_crate(model, c2, cb["crate"], rng, step=c2["manipulation_targets"]["glass_crate"]["insertion_waypoint_step_m"],
                                        extra_boxes=extra)
        feas = {k: v["summary"]["feasible"] for k, v in res.items()}
        log(f"combo #{k}: paper {cb['paper']['xy']} plastic {cb['plastic']['xy']} crate {cb['crate']['xy']} h={cb['crate']['height']} "
            f"yaw={cb['crate']['yaw']} -> {feas}")
        if all(feas.values()):
            out["chosen"] = {"rank": k, "combo": cb, "config": {"paper_bin": c2["bins"]["paper_bin"]["position"],
                                                                "plastic_bin": c2["bins"]["plastic_bin"]["position"],
                                                                "crate": c2["crate"]["position"], "crate_yaw": c2["crate"]["yaw_deg"],
                                                                "platform": c2["crate_platform"]},
                             "results": res}
            break
    json.dump(out, open(os.path.join(ROOT, cfg["paths"]["logs_dir"], "layout_search.json"), "w"), indent=1,
              default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
    if not out["chosen"]:
        log("NO fully feasible layout found")
        return 1
    ch = out["chosen"]
    log("chosen:", json.dumps(ch["config"]))
    if args.apply:
        cfg["bins"]["paper_bin"]["position"] = ch["config"]["paper_bin"]
        cfg["bins"]["plastic_bin"]["position"] = ch["config"]["plastic_bin"]
        cfg["crate"]["position"] = ch["config"]["crate"]
        cfg["crate"]["yaw_deg"] = ch["config"]["crate_yaw"]
        cfg["crate_platform"].update(ch["config"]["platform"])
        cfg["crate"]["target_compartment"] = ch["results"]["glass_crate"]["meta"]["compartment"]
        sel = {}
        for key, r in ch["results"].items():
            sel[key] = {"meta": r["meta"], "poses": {p["name"]: {"tcp_position": p["tcp_position"], "tcp_orientation_wxyz": p["tcp_orientation_wxyz"],
                                                               "finger_opening_m": p["finger_opening_m"]}
                                                     for p in r["poses"] if not p.get("waypoint")}}
        cfg["manipulation_targets"]["selected"] = sel
        cfg["manipulation_targets"]["selected_by"] = "scripts/workstation/optimize_layout.py (seeded, reproducible)"
        json.dump(cfg, open(cfg_path, "w"), indent=2)
        open(cfg_path, "a").write("\n")
        log("config updated")
    return 0


code = 1
try:
    t0 = time.time()
    code = main()
    log(f"done in {time.time() - t0:.0f}s")
except Exception:
    traceback.print_exc()
    code = 2
finally:
    app.close(exit_code=code)
    sys.exit(code)
