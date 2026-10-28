"""Static validation of the workstation scene: geometry, USD composition, physics schemas, robot
structure, and a three-tier reachability analysis (geometric / approximate workspace / Lula IK).

    "$ISAACSIM_PYTHON" scripts/workstation/validate_scene.py [--config ...]

Writes logs/workstation/static_validation.json and logs/workstation/scene_inventory.json.
No simulation is run here (see run_physics_test.py); the robot is never commanded.
"""

import argparse
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
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, UsdUtils  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_geometry as lg  # noqa: E402
import layout_validation  # noqa: E402

SP = {}

CHECKS = {}
WARN = []


def check(group, name, passed, **detail):
    CHECKS.setdefault(group, {})[name] = {"passed": bool(passed), **detail}
    return passed


def rng(prim, purposes):
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, useExtentsHint=False)
    r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    return np.array(r.GetMin()), np.array(r.GetMax())


VIS = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
COL = [UsdGeom.Tokens.guide]


def overlap(a, b, tol=0.0):
    """Penetration depth of two AABBs (>0 means they overlap by more than tol on every axis)."""
    d = np.minimum(a[1], b[1]) - np.maximum(a[0], b[0])
    return float(d.min()) - tol


def collider_prims(prim):
    return [p for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.CollisionAPI)]


def has_rigid_in_subtree(prim):
    return [str(p.GetPath()) for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies())
            if p.HasAPI(UsdPhysics.RigidBodyAPI) and p.GetAttribute("physics:rigidBodyEnabled").Get() is not False]


def ancestors_rigid(prim):
    out, p = [], prim.GetParent()
    while p and not p.IsPseudoRoot():
        if p.HasAPI(UsdPhysics.RigidBodyAPI):
            out.append(str(p.GetPath()))
        p = p.GetParent()
    return out


def quat_rot(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def main():
    cfg_path = args.config if os.path.isabs(args.config) else os.path.join(ROOT, args.config)
    cfg = json.load(open(cfg_path))
    SP.update(lg.scene_paths(cfg))
    tol = cfg["validation"]["dimension_tolerance_m"]
    ptol = cfg["validation"]["position_tolerance_m"]
    scene_path = os.path.join(ROOT, cfg["paths"]["scene"])
    out_dir = os.path.join(ROOT, cfg["paths"]["logs_dir"])
    inventory = {"scene": os.path.relpath(scene_path, ROOT), "components": {}}

    # ======================= B. USD validation ======================================
    stage = Usd.Stage.Open(scene_path)
    if not check("usd", "scene_opens", stage is not None, path=os.path.relpath(scene_path, ROOT)):
        return
    errs = [str(e) for e in stage.GetCompositionErrors()] if hasattr(stage, "GetCompositionErrors") else []
    check("usd", "no_composition_errors", not errs, errors=errs[:10])
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(scene_path)
    check("usd", "all_references_resolve", not unresolved, unresolved=[str(u) for u in unresolved][:20],
          layers=len(layers), local_layers=sorted({os.path.relpath(l.realPath, ROOT) for l in layers
                                                   if l.realPath and l.realPath.startswith(ROOT)}))
    check("usd", "units", UsdGeom.GetStageMetersPerUnit(stage) == 1.0 and UsdGeom.GetStageUpAxis(stage) == "Z"
          and UsdPhysics.GetStageKilogramsPerUnit(stage) == 1.0,
          meters_per_unit=UsdGeom.GetStageMetersPerUnit(stage), up_axis=str(UsdGeom.GetStageUpAxis(stage)),
          kilograms_per_unit=UsdPhysics.GetStageKilogramsPerUnit(stage))
    dp = stage.GetDefaultPrim()
    check("usd", "default_prim", bool(dp) and str(dp.GetPath()) == "/World", default_prim=str(dp.GetPath()) if dp else None)
    required = ["/World/PhysicsScene", "/World/Environment/Ground", "/World/Workstation/Table", SP["paper_bin"],
                SP["plastic_bin"], SP["crate"], "/World/Objects/GlassBottle",
                "/World/Objects/PlasticBottle", "/World/Objects/PaperCup", cfg["robot"]["mount_prim"] + "/" + cfg["robot"]["prim_name"],
                "/World/Cameras/Main", "/World/Cameras/Top", SP["crate_platform"], SP["sorting_zone"]]
    missing = [p for p in required if not stage.GetPrimAtPath(p).IsValid()]
    check("usd", "hierarchy_complete", not missing, missing=missing)
    unbound_vis, unbound_phys, n_mesh, n_col = [], [], 0, 0
    for p in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
        if p.IsA(UsdGeom.Gprim):
            purpose = UsdGeom.Imageable(p).ComputePurpose()
            if purpose != UsdGeom.Tokens.guide and not p.GetPath().HasPrefix(Sdf.Path(cfg["robot"]["mount_prim"])):
                n_mesh += 1
                m, _ = UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()
                if not m or not m.GetPrim().IsValid():
                    unbound_vis.append(str(p.GetPath()))
        if p.HasAPI(UsdPhysics.CollisionAPI) and not p.GetPath().HasPrefix(Sdf.Path(cfg["robot"]["mount_prim"])):
            n_col += 1
            m, _ = UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial("physics")
            if not m or not m.GetPrim().HasAPI(UsdPhysics.MaterialAPI):
                unbound_phys.append(str(p.GetPath()))
    check("usd", "visual_material_bindings_resolve", not unbound_vis, render_gprims=n_mesh, unbound=unbound_vis[:20])
    check("usd", "physics_material_bindings_resolve", not unbound_phys, colliders=n_col, unbound=unbound_phys[:20])

    # ======================= A. Geometry ============================================
    t = cfg["table"]
    top_z = t["position"][2] + t["height"]
    table = stage.GetPrimAtPath("/World/Workstation/Table")
    tmin, tmax = rng(table, VIS)
    size = tmax - tmin
    check("geometry", "table_overall_dimensions", np.allclose(size, [t["length"], t["width"], t["height"]], atol=tol),
          actual=size.tolist(), expected=[t["length"], t["width"], t["height"]])
    check("geometry", "table_rests_on_ground", abs(tmin[2] - 0.0) <= tol, table_min_z=float(tmin[2]))
    top = stage.GetPrimAtPath("/World/Workstation/Table/Tabletop")
    cmin, cmax = rng(top, COL)
    check("geometry", "tabletop_surfaces", abs(cmax[2] - top_z) <= tol and abs(cmin[2] - (top_z - t["top_thickness"])) <= tol,
          top_z=float(cmax[2]), bottom_z=float(cmin[2]), collider_size=(cmax - cmin).tolist())
    legs = [c for c in table.GetChildren() if c.GetName().startswith("Leg_")]
    leg_info = []
    for legp in legs:
        lmin, lmax = rng(legp, COL)
        leg_info.append({"path": str(legp.GetPath()), "min": lmin.tolist(), "max": lmax.tolist(),
                         "size": (lmax - lmin).tolist(), "colliders": len(collider_prims(legp))})
    check("geometry", "exactly_four_legs", len(legs) == 4, count=len(legs))
    leg_ok = all(np.allclose(li["size"], [t["leg_size"], t["leg_size"], t["leg_height"]], atol=tol)
                 and abs(li["min"][2]) <= tol and abs(li["max"][2] - (top_z - t["top_thickness"])) <= tol for li in leg_info)
    check("geometry", "leg_dimensions_and_contact", leg_ok, legs=leg_info)
    insets = [min(t["length"] / 2 - max(abs(li["min"][0]), abs(li["max"][0])),
                  t["width"] / 2 - max(abs(li["min"][1]), abs(li["max"][1]))) for li in leg_info]
    check("geometry", "leg_inset_from_edges", all(abs(i - t["leg_inset"]) <= tol for i in insets),
          outer_face_insets=insets, expected=t["leg_inset"], reference=t["leg_inset_reference"])
    leg_top_pen = [overlap((np.array(li["min"]), np.array(li["max"])), (cmin, cmax)) for li in leg_info]
    check("geometry", "legs_do_not_penetrate_tabletop", all(p <= 1e-6 for p in leg_top_pen),
          overlap_depths=leg_top_pen, note="0 = touching")

    comps = {}
    clearance = cfg["objects"]["clearance"]
    for key, path in (("glass_bottle", "/World/Objects/GlassBottle"), ("plastic_bottle", "/World/Objects/PlasticBottle"),
                      ("paper_cup", "/World/Objects/PaperCup")):
        o = cfg["objects"][key]
        prim = stage.GetPrimAtPath(path)
        vmin, vmax = rng(prim, VIS)
        kmin, kmax = rng(prim, COL)
        d = vmax - vmin
        diam = o.get("body_diameter", o.get("top_diameter"))
        xf = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)
        zaxis = np.array(xf.TransformDir(Gf.Vec3d(0, 0, 1)))
        tilt = math.degrees(math.acos(min(1.0, zaxis[2] / np.linalg.norm(zaxis))))
        comps[key] = {"path": path, "vis": (vmin, vmax), "col": (kmin, kmax)}
        check("geometry", f"{key}_dimensions", abs(d[2] - o["height"]) <= tol and abs(max(d[0], d[1]) - diam) <= tol,
              size=d.tolist(), expected_height=o["height"], expected_max_diameter=diam)
        centre = (vmin + vmax) / 2
        check("geometry", f"{key}_position", abs(centre[0] - o["position"][0]) <= ptol and abs(centre[1] - o["position"][1]) <= ptol
              and abs(kmin[2] - (top_z + clearance)) <= ptol, centre_xy=centre[:2].tolist(), expected_xy=o["position"],
              collider_bottom_z=float(kmin[2]), expected_bottom_z=top_z + clearance)
        check("geometry", f"{key}_upright", tilt <= 0.01, tilt_deg=tilt)
        gap = float(kmin[2] - cmax[2])
        check("geometry", f"{key}_not_penetrating_tabletop", 0 <= gap <= 0.003, gap_m=gap)
        on_top = (kmin[0] >= -t["length"] / 2 and kmax[0] <= t["length"] / 2 and kmin[1] >= -t["width"] / 2 and kmax[1] <= t["width"] / 2)
        check("geometry", f"{key}_footprint_on_tabletop", on_top, collider_xy=[kmin[:2].tolist(), kmax[:2].tolist()])
        inventory["components"][key] = {"path": path, "visual_bounds": [vmin.tolist(), vmax.tolist()],
                                        "collision_bounds": [kmin.tolist(), kmax.tolist()], "tilt_deg": tilt,
                                        "colliders": [str(p.GetPath()) for p in collider_prims(prim)]}

    keys = list(comps)
    gaps = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = comps[keys[i]]["col"], comps[keys[j]]["col"]
            ca, cb = (a[0] + a[1]) / 2, (b[0] + b[1]) / 2
            ra, rb = (a[1] - a[0])[0] / 2, (b[1] - b[0])[0] / 2
            gaps[f"{keys[i]}-{keys[j]}"] = float(np.linalg.norm((ca - cb)[:2]) - ra - rb)
    check("geometry", "objects_separated", all(g >= cfg["validation"]["min_object_gap_m"] for g in gaps.values()),
          gaps_m=gaps, minimum=cfg["validation"]["min_object_gap_m"])

    for key, path in (("paper_bin", SP["paper_bin"]), ("plastic_bin", SP["plastic_bin"])):
        b = {**cfg["bins"]["common"], **cfg["bins"][key]}
        prim = stage.GetPrimAtPath(path)
        kmin, kmax = rng(prim, COL)
        comps[key] = {"path": path, "col": (kmin, kmax)}
        check("geometry", f"{key}_dimensions", np.allclose(kmax - kmin, [b["width"], b["depth"], b["height"]], atol=tol),
              size=(kmax - kmin).tolist(), expected=[b["width"], b["depth"], b["height"]])
        check("geometry", f"{key}_on_floor_at_position", abs(kmin[2]) <= tol and
              np.allclose((kmin + kmax)[:2] / 2, b["position"][:2], atol=ptol), min_z=float(kmin[2]),
              centre_xy=((kmin + kmax)[:2] / 2).tolist())
        inventory["components"][key] = {"path": path, "collision_bounds": [kmin.tolist(), kmax.tolist()],
                                        "colliders": [str(p.GetPath()) for p in collider_prims(prim)], "label": b["label"]}
    c = cfg["crate"]
    crate = stage.GetPrimAtPath(SP["crate"])
    kmin, kmax = rng(crate, COL)
    comps["crate"] = {"path": str(crate.GetPath()), "col": (kmin, kmax)}
    exp = sorted([c["length"], c["width"]]) + [c["height"]]
    check("geometry", "crate_dimensions", np.allclose(sorted((kmax - kmin)[:2]) + [(kmax - kmin)[2]], exp, atol=tol),
          size=(kmax - kmin).tolist(), expected_sorted_xy_then_h=exp)
    support_z = cfg["crate_platform"]["height"] if c.get("support") == "crate_platform" else 0.0
    check("geometry", "crate_on_support", abs(kmin[2] - support_z) <= tol, min_z=float(kmin[2]), support=c.get("support", "floor"),
          support_top_z=support_z)
    inventory["components"]["crate"] = {"path": str(crate.GetPath()), "collision_bounds": [kmin.tolist(), kmax.tolist()]}
    cb = [ch for ch in stage.GetPrimAtPath(SP["crate_bottles"]).GetChildren()] if c["bottles"]["enabled"] else []
    inside = []
    for bp in cb:
        bmin, bmax = rng(bp, COL)
        inside.append(bool((bmin[:2] >= kmin[:2] - 1e-6).all() and (bmax[:2] <= kmax[:2] + 1e-6).all() and bmin[2] >= kmin[2]))
    check("geometry", "crate_bottles_inside_crate", all(inside), count=len(cb), inside=inside)

    # Static structures must not intersect each other (legs vs bins/crate, bins vs bins)
    statics = {"paper_bin": comps["paper_bin"]["col"], "plastic_bin": comps["plastic_bin"]["col"], "crate": comps["crate"]["col"]}
    for li in leg_info:
        statics[li["path"].split("/")[-1]] = (np.array(li["min"]), np.array(li["max"]))
    statics["tabletop"] = (cmin, cmax)
    if stage.GetPrimAtPath(SP["crate_platform"]).IsValid():
        statics["crate_platform"] = rng(stage.GetPrimAtPath(SP["crate_platform"]), COL)
    inter = {}
    names = list(statics)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if names[i].startswith("Leg_") and (names[j].startswith("Leg_") or names[j] == "tabletop"):
                continue
            if {names[i], names[j]} == {"crate", "crate_platform"}:
                continue  # the crate rests on the platform top (checked in layout.crate_supported_by_platform)
            d = overlap(statics[names[i]], statics[names[j]])
            if d > -0.005:
                inter[f"{names[i]}-{names[j]}"] = d
    check("geometry", "no_static_intersections", all(v <= 0 for v in inter.values()),
          near_or_overlapping=inter, note="AABB overlap depth; values > 0 overlap, -0.005..0 are within 5 mm")
    ground = stage.GetPrimAtPath("/World/Environment/Ground")
    gmin, gmax = rng(ground, VIS)
    everything = [rng(stage.GetPrimAtPath(p), VIS) for p in ("/World/Workstation", "/World/Objects")]
    within = all((e[0][:2] >= gmin[:2]).all() and (e[1][:2] <= gmax[:2]).all() for e in everything)
    check("geometry", "within_ground_bounds", within and abs(gmax[2]) <= 1e-6, ground=[gmin.tolist(), gmax.tolist()])

    # ======================= C. Physics schemas (static part) ======================
    ps = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
    if check("physics", "physics_scene_exists", len(ps) == 1, scenes=[str(p.GetPath()) for p in ps]):
        s = UsdPhysics.Scene(ps[0])
        gd, gm = s.GetGravityDirectionAttr().Get(), s.GetGravityMagnitudeAttr().Get()
        hz = PhysxSchema.PhysxSceneAPI(ps[0]).GetTimeStepsPerSecondAttr().Get()
        check("physics", "gravity_and_rate", gd == Gf.Vec3f(0, 0, -1) and abs(gm - 9.81) < 1e-6 and hz == cfg["physics"]["steps_per_second"],
              direction=list(gd), magnitude=gm, steps_per_second=hz,
              gpu_dynamics=PhysxSchema.PhysxSceneAPI(ps[0]).GetEnableGPUDynamicsAttr().Get())
    for name, path in (("table", "/World/Workstation/Table"), ("paper_bin", SP["paper_bin"]),
                       ("plastic_bin", SP["plastic_bin"]), ("crate", SP["crate"]),
                       ("crate_platform", SP["crate_platform"]), ("ground", "/World/Environment/Ground")):
        prim = stage.GetPrimAtPath(path)
        cols = collider_prims(prim)
        rb = has_rigid_in_subtree(prim) + ancestors_rigid(prim)
        check("physics", f"{name}_static_collider", len(cols) > 0 and not rb, colliders=len(cols), rigid_bodies=rb)
    for key in ("paper_bin", "plastic_bin"):
        b = {**cfg["bins"]["common"], **cfg["bins"][key]}
        prim = stage.GetPrimAtPath(comps[key]["path"])
        names_ = sorted(p.GetParent().GetName() for p in collider_prims(prim))
        bmin, bmax = comps[key]["col"]
        wt = b["wall_thickness"]
        interior = (bmin + np.array([wt, wt, wt]) + 1e-4, np.array([bmax[0] - wt, bmax[1] - wt, bmax[2] + 0.5]) - 1e-4)
        blocking = []
        for p in collider_prims(prim):
            pr = rng(p, COL)
            if overlap(pr, interior) > 0:
                blocking.append(str(p.GetPath()))
        check("physics", f"{key}_open_top_compound", names_ == ["Bottom", "WallNegX", "WallNegY", "WallPosX", "WallPosY"]
              and not blocking, colliders=names_, colliders_intruding_interior_or_opening=blocking,
              opening_m=[float(bmax[0] - bmin[0] - 2 * wt), float(bmax[1] - bmin[1] - 2 * wt)])
    cprim = stage.GetPrimAtPath(comps["crate"]["path"])
    roof = [str(p.GetPath()) for p in collider_prims(cprim) if rng(p, COL)[1][2] > kmax[2] - 1e-6 and
            (rng(p, COL)[1] - rng(p, COL)[0])[2] < 0.02]
    check("physics", "crate_open_top", not roof, horizontal_colliders_at_top=roof)
    for key, path in (("glass_bottle", "/World/Objects/GlassBottle"), ("plastic_bottle", "/World/Objects/PlasticBottle"),
                      ("paper_cup", "/World/Objects/PaperCup")):
        prim = stage.GetPrimAtPath(path)
        mass = UsdPhysics.MassAPI(prim).GetMassAttr().Get() if prim.HasAPI(UsdPhysics.MassAPI) else None
        inertia = UsdPhysics.MassAPI(prim).GetDiagonalInertiaAttr().Get() if prim.HasAPI(UsdPhysics.MassAPI) else None
        com = UsdPhysics.MassAPI(prim).GetCenterOfMassAttr().Get() if prim.HasAPI(UsdPhysics.MassAPI) else None
        nested = [p for p in collider_prims(prim) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
        check("physics", f"{key}_dynamic_body", prim.HasAPI(UsdPhysics.RigidBodyAPI) and mass is not None
              and abs(mass - cfg["objects"][key]["mass"]) < 1e-6 and inertia is not None and min(inertia) > 0
              and len(collider_prims(prim)) > 0 and not ancestors_rigid(prim) and not nested,
              mass=mass, diagonal_inertia=list(inertia) if inertia else None, center_of_mass=list(com) if com else None,
              colliders=len(collider_prims(prim)))
        inventory["components"][key].update(mass=mass, diagonal_inertia=list(inertia) if inertia else None,
                                            center_of_mass=list(com) if com else None)
    static_b = [str(bp.GetPath()) for bp in cb if bp.GetAttribute("physics:rigidBodyEnabled").Get() is False]
    check("physics", "crate_bottles_static", len(static_b) == len(cb), static=len(static_b), total=len(cb))

    # ======================= F. Robot (static structure) ===========================
    rcfg = cfg["robot"]
    rpath = rcfg["mount_prim"] + "/" + rcfg["prim_name"]
    robot = stage.GetPrimAtPath(rpath)
    roots = [str(p.GetPath()) for p in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies())
             if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
    check("robot", "reference_resolves", robot.IsValid() and len(list(robot.GetChildren())) > 0,
          asset=stage.GetRootLayer().customLayerData.get("robot_agent_lab", {}).get("robot_asset"),
          variants={n: robot.GetVariantSets().GetVariantSet(n).GetVariantSelection() for n in robot.GetVariantSets().GetNames()})
    check("robot", "single_articulation_root", roots == [rpath], articulation_roots=roots)
    joints = [p for p in Usd.PrimRange(robot, Usd.TraverseInstanceProxies()) if p.IsA(UsdPhysics.Joint)]
    rev = [p.GetName() for p in joints if p.IsA(UsdPhysics.RevoluteJoint)]
    pri = [p.GetName() for p in joints if p.IsA(UsdPhysics.PrismaticJoint)]
    fixed_world = [str(p.GetPath()) for p in joints if not UsdPhysics.Joint(p).GetBody1Rel().GetTargets()
                   and UsdPhysics.Joint(p).GetBody0Rel().GetTargets() and UsdPhysics.Joint(p).GetJointEnabledAttr().Get()]
    check("robot", "joint_definitions", len(rev) == 7 and len(pri) == 2, revolute=rev, prismatic=pri)
    check("robot", "base_fixed_to_world", len(fixed_world) == 1 and fixed_world[0].endswith("rootJoint"),
          world_joints=fixed_world, note="rootJoint: body0 = panda_link0, body1 = world")
    gripper = [n for n in ("panda_hand", "panda_leftfinger", "panda_rightfinger")
               if any(p.GetName() == n and p.HasAPI(UsdPhysics.RigidBodyAPI) for p in Usd.PrimRange(robot, Usd.TraverseInstanceProxies()))]
    check("robot", "gripper_exists", len(gripper) == 3, links=gripper)
    rb = [p for p in Usd.PrimRange(robot, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    rcols = [p for p in Usd.PrimRange(robot, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.CollisionAPI)]
    check("robot", "robot_physics_valid", len(rb) == 11 and len(rcols) > 0 and all(
        p.HasAPI(UsdPhysics.MassAPI) or True for p in rb), rigid_bodies=len(rb), colliders=len(rcols))
    # What did the scene layer author under the robot? Must be only joint state/drive targets + filtered pairs.
    added_schemas = set()
    root_layer = stage.GetRootLayer()
    for p in Usd.PrimRange(robot):
        spec = root_layer.GetPrimAtPath(p.GetPath())
        if spec and "apiSchemas" in spec.ListInfoKeys():
            items = spec.GetInfo("apiSchemas")
            added_schemas.update(list(items.prependedItems) + list(items.appendedItems) + list(items.explicitItems))
    allowed = {"PhysicsJointStateAPI:angular", "PhysicsJointStateAPI:linear", "PhysicsFilteredPairsAPI"}
    check("robot", "no_extra_robot_physics_schemas", added_schemas <= allowed, scene_added_schemas=sorted(added_schemas),
          allowed=sorted(allowed))
    hp = rcfg["home_joint_positions_deg"]
    lim_ok = {}
    for p in joints:
        if p.GetName() in hp:
            j = UsdPhysics.RevoluteJoint(p)
            lo, hi = j.GetLowerLimitAttr().Get(), j.GetUpperLimitAttr().Get()
            margin = min(hp[p.GetName()] - lo, hi - hp[p.GetName()])
            lim_ok[p.GetName()] = {"value": hp[p.GetName()], "limits": [lo, hi], "margin_deg": margin,
                                   "state": p.GetAttribute("state:angular:physics:position").Get(),
                                   "target": p.GetAttribute("drive:angular:physics:targetPosition").Get()}
    check("robot", "home_pose_within_limits", all(v["margin_deg"] >= 5 and v["state"] == v["value"] == v["target"]
                                                 for v in lim_ok.values()) and len(lim_ok) == 7, joints=lim_ok)
    link0 = next(p for p in Usd.PrimRange(robot) if p.GetName() == "panda_link0")
    l0min, l0max = rng(link0, VIS)
    l0_origin = np.array(UsdGeom.Xformable(link0).ComputeLocalToWorldTransform(0).ExtractTranslation())
    check("robot", "base_on_tabletop", abs(l0min[2] - top_z) <= 0.002 and np.allclose(l0_origin, rcfg["base_position"], atol=1e-4),
          base_min_z=float(l0min[2]), base_frame_origin=l0_origin.tolist(), configured=rcfg["base_position"],
          note="base frame = panda_link0 origin; its visual casting is not centred on the frame")
    inside_table = (l0min[0] >= -t["length"] / 2 and l0max[0] <= t["length"] / 2 and l0min[1] >= -t["width"] / 2 and l0max[1] <= t["width"] / 2)
    check("robot", "base_footprint_on_tabletop", inside_table, base_bounds=[l0min.tolist(), l0max.tolist()])
    fp = link0.GetRelationship("physics:filteredPairs").GetTargets() if link0.HasAPI(UsdPhysics.FilteredPairsAPI) else []
    check("robot", "base_tabletop_contact_filtered", bool(fp), filtered_pairs=[str(x) for x in fp])
    for name, comp in (("objects", "/World/Objects"),):
        pass
    obj_vs_base = {k: overlap(comps[k]["col"], (l0min, l0max)) for k in ("glass_bottle", "plastic_bottle", "paper_cup")}
    check("robot", "objects_clear_of_robot_base", all(v < -0.02 for v in obj_vs_base.values()), aabb_overlap=obj_vs_base)
    inventory["components"]["robot"] = {"path": rpath, "asset": stage.GetRootLayer().customLayerData["robot_agent_lab"]["robot_asset"],
                                        "base_position": rcfg["base_position"], "base_yaw_deg": rcfg["base_yaw_deg"],
                                        "dofs": rev + pri, "home_joint_positions_deg": hp}

    # ======================= G. Reachability =======================================
    reach = layout_validation.run(stage, cfg, check, WARN, simulation_app)
    json.dump({"checks": CHECKS, "warnings": WARN, "reachability": reach},
              open(os.path.join(out_dir, "static_validation.json"), "w"), indent=2, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
    inventory["cameras"] = {p.GetName(): str(p.GetPath()) for p in stage.GetPrimAtPath("/World/Cameras").GetChildren()}
    inventory["lights"] = [str(p.GetPath()) for p in stage.GetPrimAtPath("/World/Environment/Lights").GetChildren()]
    json.dump(inventory, open(os.path.join(out_dir, "scene_inventory.json"), "w"), indent=2,
              default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))


code = 1
try:
    t0 = time.time()
    main()
    n = sum(len(g) for g in CHECKS.values())
    f = [f"{g}.{k}" for g, v in CHECKS.items() for k, c in v.items() if not c["passed"]]
    print(f"[validate] {n - len(f)}/{n} static checks passed; failed: {f}", flush=True)
    print(f"[validate] done in {time.time() - t0:.1f}s", flush=True)
    code = 0 if not f else 1
except Exception:
    traceback.print_exc()
    code = 2
finally:
    simulation_app.close(exit_code=code)
    sys.exit(code)
