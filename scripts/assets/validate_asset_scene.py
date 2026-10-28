"""Targeted validation of a derived scene (base workstation + library-asset instances), headless Isaac Sim.

    "$ISAACSIM_PYTHON" scripts/assets/validate_asset_scene.py --scene config/scenes/workstation_test_spacer.json [--no-physics]

Check groups (logs/assets/<scene_id>/validation_results.json + validation_report.md):
  structure     derived layer opens, every dependency resolves, all local asset paths are relative, units, the base
                scene is unchanged since composition, and the derived layer authors nothing outside the instances
                root / preview cameras / `active = false` on the configured deactivated base prims
  registry      each instanced asset is registered, current (spec hash) and its files match the recorded hashes
  instance:*    reference, pose (asset_lib.scene_poses), local visual + collider bounds vs the spec, collider count /
                purpose / material / PhysX combine modes, open bore (ring / fitting colliders), open top (containers),
                rigid body + mass vs asset_info, resting gap on the tabletop / support surface, attached labels on
                their mount point
  placement     footprint on the tabletop, containment in the support surface, per-collider clearance to the base
                objects, the robot base and other instances (support-surface pieces exempt for what rests on them)
  preservation  every active prim of the base scene exists in the derived stage with the same type, world transform,
                attribute values and relationship targets (robot included); deactivated subtrees are exactly the
                configured ones; new prims only under the allowed roots
  scene         scene-level `validation` block: distinct assets, rigid-body counts per support, empty drop-test containers
  physics       (unless --no-physics) PhysX CPU run of the derived scene: settle test of every dynamic instance, cube drops
                into the `drop_test` containers, the `move_test` instance teleported and resettled; base objects watched
The physics test opens the derived scene unchanged; test cubes, contact reporting and no-sleep are session-layer only.
"""

import argparse
import json
import math
import os
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("--scene", required=True)
parser.add_argument("--no-physics", action="store_true")
args, _ = parser.parse_known_args()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asset_lib as al  # noqa: E402

from isaacsim import SimulationApp  # noqa: E402

simulation_app = SimulationApp({"headless": True})

import numpy as np  # noqa: E402
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, UsdUtils  # noqa: E402

CHECKS, WARN = {}, []
TOP_COLLIDER = "/World/Workstation/Table/Tabletop/Collision/TopSlab/Shape"
VIS = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render]
COL = [UsdGeom.Tokens.guide]


def check(group, name, passed, **detail):
    CHECKS.setdefault(group, {})[name] = {"passed": bool(passed), **detail}
    return passed


def world_range(prim, purposes):
    r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, useExtentsHint=False).ComputeWorldBound(prim).ComputeAlignedRange()
    return np.array(r.GetMin()), np.array(r.GetMax())


def local_range(prim, purposes):
    """Bounds in the prim's own frame (its transform excluded): compare with the asset's nominal local bounds."""
    r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, useExtentsHint=False).ComputeUntransformedBound(prim).ComputeAlignedRange()
    return np.array(r.GetMin()), np.array(r.GetMax())


def aabb_gap(a, b):
    """Lower bound on the distance between two shapes from their AABBs (xy only; <0 = footprints overlap)."""
    return float(max(a[0][0] - b[1][0], b[0][0] - a[1][0], a[0][1] - b[1][1], b[0][1] - a[1][1]))


def aabb_gap3(a, b):
    return float(max(max(a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3)))


def collider_prims(prim):
    return [p for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.CollisionAPI)]


def piece_name(p):
    """Collider piece name as in asset_lib.collider_pieces (boxes are written as <name>/Shape)."""
    return p.GetParent().GetName() if p.GetName() == "Shape" else p.GetName()


def point_range(p):
    """Tight world AABB of one collider prim from its vertices (BBoxCache bounds of rotated meshes are loose)."""
    P = collider_points_world(p)
    return P.min(axis=0), P.max(axis=0)


def m4(m):
    return np.array([[m[i][j] for j in range(4)] for i in range(4)])


def rot(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def rot_angle_deg(Ra, Rb):
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(Ra.T @ Rb) - 1) / 2))))


def to_frame(points_world, M):
    """World points (N,3) -> frame of the row-vector transform M (Gf.Matrix4d)."""
    inv = m4(M.GetInverse())
    P = np.hstack([np.asarray(points_world, float), np.ones((len(points_world), 1))])
    return (P @ inv)[:, :3]


def collider_points_world(p):
    """Corner / vertex points of one collider prim in the world (Cube corners, Mesh points, Cylinder 16-gon envelope)."""
    W = m4(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0))
    if p.IsA(UsdGeom.Cube):
        h = UsdGeom.Cube(p).GetSizeAttr().Get() / 2
        L = np.array([[x, y, z] for x in (-h, h) for y in (-h, h) for z in (-h, h)])
    elif p.IsA(UsdGeom.Mesh):
        L = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
    else:
        c = UsdGeom.Cylinder(p)
        r, hh = c.GetRadiusAttr().Get() / math.cos(math.pi / 16), c.GetHeightAttr().Get() / 2
        L = np.array([[r * math.cos(a), r * math.sin(a), z] for a in np.linspace(0, 2 * math.pi, 16, endpoint=False) for z in (-hh, hh)])
    return (np.hstack([L, np.ones((len(L), 1))]) @ W)[:, :3]


def bore_clearance(inst_prim, cols):
    """Smallest xy distance from the instance's local Z axis to any box collider (open bore check)."""
    inv = UsdGeom.Xformable(inst_prim).ComputeLocalToWorldTransform(0).GetInverse()
    best = float("inf")
    for p in cols:
        if not p.IsA(UsdGeom.Cube):
            return 0.0
        M = UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0) * inv  # cube -> instance frame (row vectors)
        s = UsdGeom.Cube(p).GetSizeAttr().Get()
        A = m4(M)
        axes = A[:3, :3]
        centre = A[3, :3]
        half = np.linalg.norm(axes, axis=1) * s / 2
        dirs = axes / np.linalg.norm(axes, axis=1)[:, None]
        # closest point of the (axis-aligned in its own frame) box to the line x = y = 0, sampled along z inside the box
        local_o = (np.array([0.0, 0.0, centre[2]]) - centre) @ dirs.T
        clamped = np.clip(local_o, -half, half)
        pt = centre + clamped @ dirs
        best = min(best, float(np.hypot(pt[0], pt[1])))
    return best


def cross2(u, v):
    """z component of the 2-D cross product u x v (NumPy 2 no longer accepts 2-D vectors in np.cross)."""
    return u[0] * v[1] - u[1] * v[0]


def axis_distance_convex(points_local):
    """Distance from the local Z axis to a z-prism convex piece (its xy polygon); 0 if the axis passes through it."""
    xy = points_local[:, :2]
    c = xy.mean(axis=0)
    ang = np.arctan2(xy[:, 1] - c[1], xy[:, 0] - c[0])
    poly = xy[np.argsort(ang)]
    n = len(poly)
    inside = all(cross2(poly[(i + 1) % n] - poly[i], -poly[i]) >= -1e-12 for i in range(n))
    if inside:
        return 0.0
    d = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        t = np.clip(np.dot(-a, b - a) / max(np.dot(b - a, b - a), 1e-18), 0, 1)
        d.append(np.linalg.norm(a + t * (b - a)))
    return float(min(d))


def base_prim_snapshot(stage, root):
    out = {}
    for p in Usd.PrimRange(stage.GetPrimAtPath(root), Usd.TraverseInstanceProxies()):
        out[str(p.GetPath())] = p
    return out


def compare_prims(pa, pb):
    """List of differences between a base-stage prim and the same path in the derived stage."""
    diffs = []
    if pa.GetTypeName() != pb.GetTypeName():
        diffs.append(f"type {pa.GetTypeName()} != {pb.GetTypeName()}")
    if pa.IsA(UsdGeom.Xformable):
        A = m4(UsdGeom.Xformable(pa).ComputeLocalToWorldTransform(0))
        B = m4(UsdGeom.Xformable(pb).ComputeLocalToWorldTransform(0))
        if np.abs(A - B).max() > 1e-12:
            diffs.append(f"world transform differs by {np.abs(A - B).max():.3e}")
    names_a = sorted(a.GetName() for a in pa.GetAttributes())
    names_b = sorted(a.GetName() for a in pb.GetAttributes())
    if names_a != names_b:
        diffs.append(f"attributes {sorted(set(names_a) ^ set(names_b))[:5]}")
    for a in pa.GetAttributes():
        b = pb.GetAttribute(a.GetName())
        if b and a.HasValue() and not (a.Get() == b.Get()):
            diffs.append(f"{a.GetName()} {a.Get()!r:.60} != {b.Get()!r:.60}")
    for r in pa.GetRelationships():
        rb = pb.GetRelationship(r.GetName())
        if not rb or r.GetTargets() != rb.GetTargets():
            diffs.append(f"relationship {r.GetName()}")
    if sorted(pa.GetAppliedSchemas()) != sorted(pb.GetAppliedSchemas()):
        diffs.append("applied schemas")
    return diffs


def camera_paths(scene):
    out = ["/World/Cameras/AssetPreview"] if scene.get("preview_camera") else []
    return out + [f"/World/Cameras/{al.camel(k)}" for k in scene.get("preview_cameras", {})]


def structure_checks(scene, out_rel):
    out = al.abspath(out_rel)
    layer = Sdf.Layer.FindOrOpen(out)
    if not check("structure", "derived_layer_exists", layer is not None, path=out_rel):
        return None
    meta = dict(layer.customLayerData.get("robot_agent_lab", {}))
    stage = Usd.Stage.Open(out)
    check("structure", "stage_opens", stage is not None and stage.GetPrimAtPath("/World").IsValid())
    layers, _, unresolved = UsdUtils.ComputeAllDependencies(out)
    local = sorted({al.relpath(l.realPath) for l in layers if l.realPath and l.realPath.startswith(al.ROOT)})
    check("structure", "all_dependencies_resolve", not unresolved, unresolved=[str(u) for u in unresolved][:10],
          layers=len(layers), local_layers=local)
    absolute, urls = [], set()
    for lr in local:
        subs, refs, pays = UsdUtils.ExtractExternalReferences(al.abspath(lr))
        for ap in list(subs) + list(refs) + list(pays):
            if "://" in ap:
                urls.add(ap)
            elif os.path.isabs(ap):
                absolute.append(f"{lr}: {ap}")
    check("structure", "local_asset_paths_relative", not absolute, absolute=absolute[:10],
          remote_urls=sorted(urls), note="remote URLs are reported, not rejected (the robot is NVIDIA-hosted)")
    check("structure", "units_and_default_prim", UsdGeom.GetStageMetersPerUnit(stage) == 1.0 and UsdGeom.GetStageUpAxis(stage) == "Z"
          and UsdPhysics.GetStageKilogramsPerUnit(stage) == 1.0 and str(stage.GetDefaultPrim().GetPath()) == "/World")
    check("structure", "sublayers_only_base_scene", list(layer.subLayerPaths) ==
          [os.path.relpath(al.abspath(scene["base_scene"]), os.path.dirname(out))], sublayers=list(layer.subLayerPaths))
    cur = al.sha256_file(scene["base_scene"])
    check("structure", "base_scene_unchanged_since_compose", meta.get("base_scene_sha256") == cur,
          composed_against=meta.get("base_scene_sha256"), current=cur)
    # what the derived layer authors
    allowed = [scene["instances_root"]] + camera_paths(scene)
    deact = scene.get("deactivate_base_prims", [])
    ancestors = {"/World", "/World/Cameras"} | {str(a) for d in deact for a in Sdf.Path(d).GetAncestorsRange() if str(a) != d}
    outside, bad_deact = [], []

    def visit(path):
        if not path.IsPrimPath():
            return
        ps = layer.GetPrimAtPath(path)
        p = str(path)
        if any(p == a or p.startswith(a + "/") for a in allowed):
            return
        pure_over = ps.specifier == Sdf.SpecifierOver and not ps.properties
        if p in ancestors and pure_over and set(ps.ListInfoKeys()) <= {"specifier"}:
            return
        if p in deact:
            if not (pure_over and set(ps.ListInfoKeys()) <= {"specifier", "active"} and ps.active is False and not ps.nameChildren):
                bad_deact.append(p)
            return
        outside.append(p)

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    check("structure", "derived_layer_scope", not outside and not bad_deact, authored_outside_allowed_roots=outside,
          deactivations_with_extra_opinions=bad_deact, allowed_roots=allowed, deactivated=deact)
    return stage


def registry_checks(scene):
    reg = al.registry()["assets"]
    for aid in sorted({i["asset"] for i in scene["instances"]}):
        status, info = al.asset_status(aid)
        check("registry", f"{aid}_current", aid in reg and status == "current" and info["ok"], status=status,
              spec_file=info and info["spec_file"], generated_utc=info and info["generated_utc"],
              generation_checks={k: v["passed"] for k, v in (info or {}).get("checks", {}).items()})


def instance_checks(stage, scene, env, poses):
    ph = env["physics"]
    top_z = al.table_top_z(env)
    ptol = env["validation"]["position_tolerance_m"]
    out_dir = os.path.dirname(al.abspath(scene["output"]))
    derived = Sdf.Layer.FindOrOpen(al.abspath(scene["output"]))
    insts = {i["name"]: i for i in scene["instances"]}
    boxes = {}
    for inst in scene["instances"]:
        g = f"instance:{inst['name']}"
        path = f"{scene['instances_root']}/{inst['name']}"
        prim = stage.GetPrimAtPath(path)
        if not check(g, "prim_exists", prim.IsValid(), path=path):
            continue
        info = al.asset_info(inst["asset"])
        spec = info["spec"]
        pl = inst["placement"]
        tol = spec.get("validation", {}).get("dimension_tolerance_m", al.DEFAULT_TOL)
        expect_ref = os.path.relpath(al.abspath(al.asset_paths(inst["asset"])["usd"]), out_dir)
        refs = [str(r.assetPath) for r in derived.GetPrimAtPath(path).referenceList.prependedItems]
        check(g, "references_library_asset", refs == [expect_ref], references=refs, expected=expect_ref)
        pose = poses[inst["name"]]
        M = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)
        t = np.array(M.ExtractTranslation())
        R = m4(M)[:3, :3].T  # column-vector rotation
        R_exp = rot(pose["orientation"])
        dang = rot_angle_deg(R_exp, R)
        yaw_meas = math.degrees(math.atan2(R[1, 0], R[0, 0]))
        tilt = math.degrees(math.acos(min(1.0, R[2, 2])))
        check(g, "pose", np.abs(t - pose["position"]).max() <= 1e-9 and np.abs(R_exp - R).max() <= 1e-9, position=t.tolist(),
              expected=pose["position"], rotation_matrix_max_error=float(np.abs(R_exp - R).max()), rotation_error_deg=dang, yaw_deg=yaw_meas, tilt_deg=tilt, pose=pl.get("pose", "upright"))
        nb = np.array(info["nominal_bounds_m"])
        vlo, vhi = local_range(prim, VIS)
        check(g, "visual_dimensions", np.abs(np.array([vlo, vhi]) - nb).max() <= tol, local_bounds=[vlo.tolist(), vhi.tolist()],
              nominal=nb.tolist(), size=(vhi - vlo).tolist(), tolerance_m=tol)
        cols = collider_prims(prim)
        rep = spec["collision"]["representation"]
        if rep != "none":
            clo, chi = local_range(prim, COL)
            check(g, "collider_dimensions", np.abs(np.array([clo, chi]) - nb).max() <= tol, local_bounds=[clo.tolist(), chi.tolist()],
                  nominal=nb.tolist(), size=(chi - clo).tolist())
        mats = [UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial("physics")[0] for p in cols]
        pm = info["resolved_physics_material"]
        co = spec["collision"].get("contact_offset_m")
        co_vals = sorted({round(float(p.GetAttribute("physxCollision:contactOffset").Get()), 6) for p in cols
                          if p.GetAttribute("physxCollision:contactOffset").HasValue()})
        check(g, "colliders", len(cols) == al.expected_colliders(spec) and all(
            UsdGeom.Imageable(p).ComputePurpose() == UsdGeom.Tokens.guide for p in cols)
              and (co_vals == ([round(co, 6)] if co else [])), count=len(cols), expected=al.expected_colliders(spec), representation=rep,
              contact_offset_m=co_vals or "PhysX default")
        if pm:
            mat_ok = all(m and m.GetPrim().HasAPI(UsdPhysics.MaterialAPI) for m in mats)
            vals, combine = set(), set()
            for m in mats:
                if m:
                    api = UsdPhysics.MaterialAPI(m.GetPrim())
                    vals.add((round(api.GetStaticFrictionAttr().Get(), 6), round(api.GetDynamicFrictionAttr().Get(), 6),
                              round(api.GetRestitutionAttr().Get(), 6)))
                    px = PhysxSchema.PhysxMaterialAPI(m.GetPrim())
                    combine.add((px.GetFrictionCombineModeAttr().Get(), px.GetRestitutionCombineModeAttr().Get()))
            expect_vals = {(round(pm["static_friction"], 6), round(pm["dynamic_friction"], 6), round(pm["restitution"], 6))}
            check(g, "physics_material", mat_ok and vals == expect_vals, bound=mat_ok, values=sorted(vals), expected=sorted(expect_vals))
            check(g, "physx_combine_modes", combine == {(ph["friction_combine_mode"], ph["restitution_combine_mode"])},
                  combine_modes=sorted(combine))
        if spec["geometry"]["method"] == "tube" and rep == "ring_segments":
            bc = bore_clearance(prim, cols)
            ri = spec["geometry"]["inner_diameter"] / 2
            check(g, "bore_open", bc >= ri - 1e-6, collider_distance_from_axis_m=bc, bore_radius_m=ri)
        if rep == "fitting_sections":
            d = [axis_distance_convex(to_frame(collider_points_world(p), M)) for p in cols]
            narrowest = min(al.section_radius_range(b, True)[0] for b in al.fitting_sections(al.collision_geometry(spec), "bore"))
            check(g, "bore_open", min(d) >= narrowest - 1e-6, collider_distance_from_axis_min_m=min(d),
                  narrowest_visual_bore_radius_m=narrowest, note="every collider piece clears the narrowest bore circle along the whole axis")
        if rep == "container_walls":
            hx, hy = al.container_inner_half(spec, al.container_dims(spec["geometry"])["tf"])
            intr = {}
            for p in cols:
                if piece_name(p) == "Floor":
                    continue
                L = to_frame(collider_points_world(p), M)
                lo, hi = L.min(axis=0), L.max(axis=0)
                intr[piece_name(p)] = float(min(hi[0] + hx, hx - lo[0], hi[1] + hy, hy - lo[1]))  # > 0: piece reaches into the column
            floor = next((p for p in cols if piece_name(p) == "Floor"), None)
            fz = to_frame(collider_points_world(floor), M)[:, 2].max() if floor else None
            check(g, "open_top", floor is not None and max(intr.values()) <= 1e-6 and len(intr) == 4,
                  max_intrusion_into_floor_column_m=max(intr.values()) if intr else None, walls=sorted(intr),
                  floor_top_local_z=fz, inner_floor_half_m=[hx, hy],
                  note="no collider above the floor reaches into the vertical column over the inner floor (no lid, opening clear)")
        vis = [p for p in Usd.PrimRange(prim) if p.IsA(UsdGeom.Mesh) and UsdGeom.Imageable(p).ComputePurpose() != UsdGeom.Tokens.guide]
        check(g, "visual_material_bound", vis and all(UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0] for p in vis),
              visual_meshes=len(vis))
        dyn = spec["physics"]["body"] == "dynamic"
        rb_enabled = prim.HasAPI(UsdPhysics.RigidBodyAPI) and prim.GetAttribute("physics:rigidBodyEnabled").Get() is not False
        nested = [str(p.GetPath()) for p in Usd.PrimRange(prim) if p != prim and p.HasAPI(UsdPhysics.RigidBodyAPI)]
        if dyn:
            mapi = UsdPhysics.MassAPI(prim)
            mass, inertia = mapi.GetMassAttr().Get(), mapi.GetDiagonalInertiaAttr().Get()
            mp = info["mass_properties"]
            mass_ok = abs(mass - mp["mass_kg"]) <= 1e-6 * mp["mass_kg"] and \
                np.allclose(list(inertia), mp["diagonal_inertia"], rtol=1e-5, atol=0)
            check(g, "rigid_body", (rb_enabled != bool(inst.get("static"))) and mass_ok and not nested, rigid_body_enabled=rb_enabled,
                  static_override=bool(inst.get("static")), mass_kg=mass, expected_mass_kg=mp["mass_kg"],
                  implied_density_kg_m3=mp["density_kg_m3"], diagonal_inertia=list(inertia),
                  center_of_mass=list(mapi.GetCenterOfMassAttr().Get()), nested_rigid_bodies=nested)
        else:
            check(g, "static_body", not prim.HasAPI(UsdPhysics.RigidBodyAPI) and not nested)
        expected_gap = env["objects"]["clearance"] if dyn and not inst.get("static") else 0.0
        if cols:
            pr = [(piece_name(p), point_range(p)) for p in cols]
            wlo = min(b[0][2] for _, b in pr)
            boxes[inst["name"]] = (pr, inst, spec, M)
        if pl["surface"] == "tabletop":
            gap = float(wlo - top_z)
            check(g, "resting_on_tabletop", -1e-6 <= gap <= env["validation"]["penetration_tolerance_m"] and abs(gap - expected_gap) <= ptol,
                  collider_bottom_z=float(wlo), tabletop_z=top_z, gap_m=gap, expected_gap_m=expected_gap)
        if pl["surface"] == "on_instance":
            sup = stage.GetPrimAtPath(f"{scene['instances_root']}/{pl['support']}")
            ss = al.support_surface(al.asset_info(insts[pl["support"]]["asset"])["spec"], pl.get("support_surface"))
            sfz = [point_range(p)[1][2] for p in collider_prims(sup) if piece_name(p) in ss["pieces"]]
            gap = float(wlo - max(sfz)) if sfz else float("nan")
            check(g, "resting_on_support", bool(sfz) and -1e-6 <= gap <= env["validation"]["penetration_tolerance_m"]
                  and abs(gap - expected_gap) <= ptol, collider_bottom_z=float(wlo), support_surface_z=max(sfz) if sfz else None,
                  gap_m=gap, expected_gap_m=expected_gap, support=pl["support"])
        if pl["surface"] == "attached":
            sup = stage.GetPrimAtPath(f"{scene['instances_root']}/{pl['support']}")
            sinfo = al.asset_info(insts[pl["support"]]["asset"])
            mpos = np.array(sinfo["mounts"][pl["mount"]][0] + [1.0]) @ m4(UsdGeom.Xformable(sup).ComputeLocalToWorldTransform(0))
            ap = np.array(list(al.attach_point(spec)) + [1.0]) @ m4(M)
            check(g, "on_mount_point", np.abs(mpos[:3] - ap[:3]).max() <= 1e-9 and not cols and not prim.HasAPI(UsdPhysics.RigidBodyAPI),
                  mount=pl["mount"], support=pl["support"], mount_world=mpos[:3].tolist(), attach_point_world=ap[:3].tolist(),
                  colliders=len(cols), note="visual-only: no colliders, no rigid body; back face on the label holder")
    return boxes


def placement_checks(stage, scene, env, boxes):
    t = env["table"]
    gap_min = env["validation"]["min_object_gap_m"]
    insts = {i["name"]: i for i in scene["instances"]}
    others = {}
    objs = stage.GetPrimAtPath("/World/Objects")
    if objs.IsValid() and objs.IsActive():
        others = {p.GetName(): world_range(p, COL) for p in objs.GetChildren()}
    link0 = next(p for p in Usd.PrimRange(stage.GetPrimAtPath(env["robot"]["mount_prim"])) if p.GetName() == "panda_link0")
    others["robot:panda_link0"] = world_range(link0, VIS)
    zone = env.get("scene_paths", {}).get("sorting_zone", "/World/Workstation/SortingZone")
    zp = stage.GetPrimAtPath(zone)
    if zp.IsValid() and zp.IsActive():
        others["sorting_zone"] = world_range(zp, COL)
    for name, (pieces, inst, spec, M) in boxes.items():
        g = f"instance:{name}"
        pl = inst["placement"]
        lo = np.min([b[0] for _, b in pieces], axis=0)
        hi = np.max([b[1] for _, b in pieces], axis=0)
        if pl["surface"] == "tabletop":
            on = lo[0] >= t["position"][0] - t["length"] / 2 and hi[0] <= t["position"][0] + t["length"] / 2 and \
                lo[1] >= t["position"][1] - t["width"] / 2 and hi[1] <= t["position"][1] + t["width"] / 2
            check(g, "footprint_on_tabletop", on, collider_xy=[lo[:2].tolist(), hi[:2].tolist()])
        if pl["surface"] == "on_instance":
            sup = stage.GetPrimAtPath(f"{scene['instances_root']}/{pl['support']}")
            hx, hy = al.support_surface(al.asset_info(insts[pl["support"]]["asset"])["spec"], pl.get("support_surface"))["half"]
            pts = np.vstack([collider_points_world(p) for p in collider_prims(stage.GetPrimAtPath(f"{scene['instances_root']}/{name}"))])
            L = to_frame(pts, UsdGeom.Xformable(sup).ComputeLocalToWorldTransform(0))
            margin = float(min(hx - np.abs(L[:, 0]).max(), hy - np.abs(L[:, 1]).max()))
            check(g, "inside_support", margin >= gap_min, margin_to_support_edge_m=margin, required_m=gap_min, support=pl["support"],
                  note="every collider vertex inside the support surface, at least min_object_gap_m from its edge")
        gaps = {k: aabb_gap((lo, hi), v) for k, v in others.items()}
        for k, (opieces, oinst, _, _) in boxes.items():
            if k == name:
                continue
            exempt = set()
            for a, b in ((name, k), (k, name)):
                ap = insts[a]["placement"]
                if ap["surface"] == "on_instance" and ap.get("support") == b:
                    exempt |= {(b, pn) for pn in al.support_surface(al.asset_info(insts[b]["asset"])["spec"], ap.get("support_surface"))["pieces"]}
            d = [aabb_gap3(x, y) for px, x in pieces for py, y in opieces if (name, px) not in exempt and (k, py) not in exempt]
            gaps[f"instance:{k}"] = min(d) if d else float("inf")
        check(g, "clearance_to_scene", min(gaps.values()) >= gap_min, min_gap_m=min(gaps.values()),
              closest=min(gaps, key=gaps.get), required_m=gap_min,
              note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt")


def preservation_checks(stage, scene):
    base = Usd.Stage.Open(al.abspath(scene["base_scene"]))
    a = base_prim_snapshot(base, "/")
    b = base_prim_snapshot(stage, "/")
    deact = scene.get("deactivate_base_prims", [])
    under = lambda p: any(p == d or p.startswith(d + "/") for d in deact)
    missing = sorted(set(a) - set(b))
    expected_missing = sorted(p for p in a if under(p))
    added = sorted(set(b) - set(a))
    allowed = [scene["instances_root"]] + camera_paths(scene)
    bad_added = [p for p in added if not any(p == r or p.startswith(r + "/") for r in allowed)]
    diffs, n_attr = {}, 0
    for path, pa in a.items():
        pb = b.get(path)
        if pb is None:
            continue
        n_attr += len(pa.GetAttributes())
        d = compare_prims(pa, pb)
        if d:
            diffs[path] = d[:3]
    inactive_ok = all(stage.GetPrimAtPath(d).IsValid() and not stage.GetPrimAtPath(d).IsActive() and d in a for d in deact)
    check("preservation", "all_base_prims_present", missing == expected_missing and inactive_ok, base_prims=len(a),
          missing_unexpected=sorted(set(missing) - set(expected_missing))[:10], deactivated_roots=deact,
          deactivated_prims=len(expected_missing), deactivated_roots_inactive=inactive_ok,
          note="prims under deactivate_base_prims are intentionally inactive in the derived scene (base file unchanged)")
    check("preservation", "base_prims_unchanged", not diffs, prims_compared=len(a) - len(missing), attributes_compared=n_attr,
          differing=dict(list(diffs.items())[:10]), note="type, world transform, every attribute value, relationships, applied schemas")
    check("preservation", "new_prims_only_under_allowed_roots", not bad_added, new_prims=len(added), outside=bad_added[:10],
          allowed_roots=allowed)
    robot = [p for p in a if p.startswith("/World/RobotMount")]
    check("preservation", "robot_unchanged", robot and not any(p in diffs for p in robot) and not any(under(p) for p in robot),
          robot_prims=len(robot))


def scene_checks(stage, scene):
    v = scene.get("validation", {})
    insts = {i["name"]: i for i in scene["instances"]}
    for a, b in v.get("distinct_assets", []):
        ia, ib = al.asset_info(a), al.asset_info(b)
        va, vb = ia["mesh"]["volume_m3"], ib["mesh"]["volume_m3"]
        sa = [s["type"] for s in ia["spec"]["geometry"].get("outer", [])]
        sb = [s["type"] for s in ib["spec"]["geometry"].get("outer", [])]
        size_a, size_b = al.nominal_size(ia["spec"]), al.nominal_size(ib["spec"])
        differ = {"visual_mesh_hash": ia["file_sha256"][ia["files"][1]] != ib["file_sha256"][ib["files"][1]],
                  "size": max(abs(x - y) for x, y in zip(size_a, size_b)) > 0.002,
                  "volume": abs(va - vb) / max(va, vb) > 0.1, "section_layout": sa != sb}
        check("scene", f"distinct_geometry_{a}_vs_{b}", all(differ.values()), criteria=differ, size_m=[size_a, size_b],
              volume_m3=[va, vb], sections=[sa, sb], triangles=[ia["mesh"]["triangles"], ib["mesh"]["triangles"]])
    for a, b in v.get("compare_assets", []):
        ia, ib = al.asset_info(a), al.asset_info(b)
        tol = max(ia["spec"].get("validation", {}).get("dimension_tolerance_m", al.DEFAULT_TOL),
                  ib["spec"].get("validation", {}).get("dimension_tolerance_m", al.DEFAULT_TOL))
        na, nb = np.array(ia["nominal_bounds_m"]), np.array(ib["nominal_bounds_m"])
        ba, bb = np.array(ia["bounds_visual_m"]), np.array(ib["bounds_visual_m"])
        ma, mb = ia.get("mass_properties") or {}, ib.get("mass_properties") or {}
        rel = lambda x, y: (y - x) / x if x else None
        check("scene", f"same_envelope_{a}_vs_{b}", np.abs(na - nb).max() <= tol and np.abs(ba - bb).max() <= tol,
              nominal_max_diff_m=float(np.abs(na - nb).max()), measured_max_diff_m=float(np.abs(ba - bb).max()), tolerance_m=tol,
              backends=[(ia.get("geometry_backend") or {}).get("backend", "blender"), (ib.get("geometry_backend") or {}).get("backend", "blender")],
              volume_m3=[ia["mesh"]["volume_m3"], ib["mesh"]["volume_m3"]], volume_rel_diff=rel(ia["mesh"]["volume_m3"], ib["mesh"]["volume_m3"]),
              mass_kg=[ma.get("mass_kg"), mb.get("mass_kg")], mass_rel_diff=rel(ma.get("mass_kg"), mb.get("mass_kg")) if ma and mb else None,
              inertia_rel_diff=[rel(x, y) for x, y in zip(ma.get("diagonal_inertia", []), mb.get("diagonal_inertia", []))],
              triangles=[ia["mesh"]["triangles"], ib["mesh"]["triangles"]],
              note="variants of one part: the envelope must match; volume / mass / inertia differences are reported, not judged")
    for sup, n in v.get("rigid_bodies_on", {}).items():
        bodies = []
        for i in scene["instances"]:
            if i["placement"].get("support") == sup and i["placement"]["surface"] == "on_instance":
                p = stage.GetPrimAtPath(f"{scene['instances_root']}/{i['name']}")
                if p.HasAPI(UsdPhysics.RigidBodyAPI) and p.GetAttribute("physics:rigidBodyEnabled").Get() is not False:
                    bodies.append(i["name"])
        check("scene", f"individual_rigid_bodies_on_{sup}", len(bodies) == n and len(set(bodies)) == n, count=len(bodies), expected=n,
              bodies=bodies, note="each with its own RigidBodyAPI root (no merged meshes, no nested bodies)")
    for name in v.get("drop_test", []):
        on = [i["name"] for i in scene["instances"] if i["placement"].get("support") == name and i["placement"]["surface"] == "on_instance"]
        check("scene", f"{name}_initially_empty", name in insts and not on, objects_inside=on)


def physics_checks(scene, env):
    import isaacsim.core.experimental.utils.app as app_utils
    import isaacsim.core.experimental.utils.stage as stage_utils
    from isaacsim.core.experimental.prims import RigidPrim
    from isaacsim.core.simulation_manager import SimulationManager

    v = env["validation"]
    sv = scene.get("validation", {})
    root = scene["instances_root"]
    insts = {i["name"]: i for i in scene["instances"]}
    ok, stage = stage_utils.open_stage(al.abspath(scene["output"]))
    if not ok:
        raise RuntimeError("open_stage failed")
    while stage_utils.is_stage_loading():
        simulation_app.update()
    if SimulationManager.get_active_physics_engine() != "physx":
        SimulationManager.switch_physics_engine("physx")
    top_z = al.table_top_z(env)
    specs = al.specs_for(scene)
    dyn = [i for i in scene["instances"] if specs[i["asset"]]["physics"]["body"] == "dynamic" and not i.get("static")]
    inst_paths = {i["name"]: f"{root}/{i['name']}" for i in dyn}
    objs = stage.GetPrimAtPath("/World/Objects")
    base_paths = {p.GetName(): str(p.GetPath()) for p in objs.GetChildren()} if objs.IsValid() and objs.IsActive() else {}
    filt = {}
    for i in dyn:
        pl = i["placement"]
        if pl["surface"] == "on_instance":
            ss = al.support_surface(specs[insts[pl["support"]]["asset"]], pl.get("support_surface"))
            filt[i["name"]] = [str(p.GetPath()) for p in collider_prims(stage.GetPrimAtPath(f"{root}/{pl['support']}"))
                               if piece_name(p) in ss["pieces"]]
        else:
            filt[i["name"]] = [TOP_COLLIDER]
    drop = {}
    cube = v["bin_drop"]
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        for p in list(inst_paths.values()) + list(base_paths.values()):
            prim = stage.GetPrimAtPath(p)
            PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.0)
            PhysxSchema.PhysxRigidBodyAPI.Apply(prim).CreateSleepThresholdAttr(0.0)
        for name in sv.get("drop_test", []):  # session-layer test cube above each empty container (never saved)
            cprim = stage.GetPrimAtPath(f"{root}/{name}")
            cspec = specs[insts[name]["asset"]]
            M = UsdGeom.Xformable(cprim).ComputeLocalToWorldTransform(0)
            s = cube["object_size"]
            H = al.nominal_size(cspec)[2]
            start = (np.array([cube["xy_offset"][0], cube["xy_offset"][1], H + cube["drop_height_above_rim"] + s / 2, 1.0]) @ m4(M))[:3]
            path = f"/World/SessionDropTest/{name}_probe"
            c = UsdGeom.Cube.Define(stage, path)
            c.CreateSizeAttr(float(s))
            UsdGeom.Xformable(c).AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*start.tolist()))
            UsdGeom.Xformable(c).AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 12.0))
            c.CreateDisplayColorAttr([Gf.Vec3f(0.9, 0.1, 0.1)])
            UsdPhysics.RigidBodyAPI.Apply(c.GetPrim())
            UsdPhysics.CollisionAPI.Apply(c.GetPrim())
            UsdPhysics.MassAPI.Apply(c.GetPrim()).CreateMassAttr(float(cube["object_mass"]))
            PhysxSchema.PhysxContactReportAPI.Apply(c.GetPrim()).CreateThresholdAttr(0.0)
            PhysxSchema.PhysxRigidBodyAPI.Apply(c.GetPrim()).CreateSleepThresholdAttr(0.0)
            drop[name] = {"path": path, "start": start.tolist(), "M": M, "spec": cspec,
                          "floor": [str(p.GetPath()) for p in collider_prims(cprim) if piece_name(p) == "Floor"]}
    bodies = {k: RigidPrim(p, contact_filter_paths=filt.get(k, [TOP_COLLIDER])) for k, p in {**inst_paths, **base_paths}.items()}
    cubes = {k: RigidPrim(d["path"], contact_filter_paths=d["floor"]) for k, d in drop.items()}
    # Reference = the authored USD pose: play() already advances physics before the first recorded sample.
    authored = {}
    for k, p in {**inst_paths, **base_paths}.items():
        M = UsdGeom.Xformable(stage.GetPrimAtPath(p)).ComputeLocalToWorldTransform(0)
        authored[k] = (np.array(M.ExtractTranslation()), m4(M)[:3, :3].T)
    app_utils.play(commit=True)
    SimulationManager.initialize_physics()
    for k, d in drop.items():  # explicit initial state after physics warm-up
        cubes[k].set_world_poses(positions=[d["start"]])
        cubes[k].set_velocities(linear_velocities=[[0, 0, 0]], angular_velocities=[[0, 0, 0]])
    dt = SimulationManager.get_physics_dt()
    t0 = SimulationManager.get_simulation_time()
    n = int(round(sv.get("settle_duration_s", v["settle_duration_s"]) / dt))

    def sample(rps, rec):
        for k, rp in rps.items():
            p, q = rp.get_world_poses()
            try:
                f = np.asarray(rp.get_contact_force_matrix(dt=dt).numpy())[0].sum(axis=0)
            except Exception as exc:
                f = np.full(3, np.nan)
                if not WARN:
                    WARN.append(f"contact readback unavailable: {exc}")
            rec[k].append((SimulationManager.get_simulation_time() - t0, p.numpy()[0].astype(float), q.numpy()[0].astype(float), f))

    rec = {k: [] for k in bodies}
    crec = {k: [] for k in cubes}
    for step in range(n + 1):
        if step:
            SimulationManager.step(steps=1)
        sample(bodies, rec)
        sample(cubes, crec)
    move = None
    mname = sv.get("move_test")
    if mname in bodies:  # Test C: move one fitting independently (teleport up + yaw), let it resettle
        p, q = bodies[mname].get_world_poses()
        p0, q0 = p.numpy()[0].astype(float), q.numpy()[0].astype(float)
        before = {k: bodies[k].get_world_poses()[0].numpy()[0].astype(float) for k in bodies if k != mname}
        h = math.radians(45.0) / 2
        dq = np.array([math.cos(h), 0, 0, math.sin(h)])
        w1, x1, y1, z1 = dq
        w2, x2, y2, z2 = q0
        q1 = np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                       w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])
        target = p0 + np.array([0.0, 0.0, 0.05])
        bodies[mname].set_world_poses(positions=[target.tolist()], orientations=[q1.tolist()])
        bodies[mname].set_velocities(linear_velocities=[[0, 0, 0]], angular_velocities=[[0, 0, 0]])
        SimulationManager.step(steps=1)
        p_after = bodies[mname].get_world_poses()[0].numpy()[0].astype(float)
        mprim = stage.GetPrimAtPath(inst_paths[mname])
        vprims = [p for p in Usd.PrimRange(mprim) if p.IsA(UsdGeom.Mesh) and UsdGeom.Imageable(p).ComputePurpose() != UsdGeom.Tokens.guide]
        cprims = collider_prims(mprim)
        usd_root = np.array(UsdGeom.Xformable(mprim).ComputeLocalToWorldTransform(0).ExtractTranslation())
        rel_vis = [np.abs(m4(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0) * UsdGeom.Xformable(mprim).ComputeLocalToWorldTransform(0).GetInverse())
                          - np.eye(4)).max() for p in vprims]
        reset = [str(p.GetPath()) for p in Usd.PrimRange(mprim) if p.IsA(UsdGeom.Xformable) and UsdGeom.Xformable(p).GetResetXformStack()]
        mrec = []
        for _ in range(int(round(1.5 / dt))):
            SimulationManager.step(steps=1)
            pp, qq = bodies[mname].get_world_poses()
            mrec.append((pp.numpy()[0].astype(float), qq.numpy()[0].astype(float)))
        after = {k: bodies[k].get_world_poses()[0].numpy()[0].astype(float) for k in before}
        p_final, q_final = mrec[-1]
        speeds = [np.linalg.norm(b[0] - a[0]) / dt for a, b in zip(mrec[-30:-1], mrec[-29:])]
        move = {"instance": mname, "start": p0.tolist(), "teleport_target": target.tolist(), "pose_after_teleport": p_after.tolist(),
                "usd_root_after_teleport": usd_root.tolist(), "final": p_final.tolist(),
                "yaw_change_deg": float(rot_angle_deg(rot(q0), rot(q_final))), "final_speed_m_s": float(np.mean(speeds)),
                "others_max_displacement_m": float(max(np.linalg.norm(after[k] - before[k]) for k in before)),
                "visual_mesh_offset_from_root": float(max(rel_vis)) if rel_vis else None, "reset_xform_stack": reset,
                "visual_meshes": len(vprims), "colliders": len(cprims)}
    app_utils.stop(commit=True)
    simulation_app.update()
    res = {"dt": dt, "steps": n, "duration_s": n * dt, "bodies": {}, "drop_test": {}, "move_test": move}
    for k, R in rec.items():
        T = np.array([r[0] for r in R])
        P = np.array([r[1] for r in R])
        Rs = [rot(r[2]) for r in R]
        A, RA = authored[k]
        rot_dev = np.array([rot_angle_deg(RA, Rq) for Rq in Rs])
        tilt = np.array([math.degrees(math.acos(min(1.0, Rq[2, 2]))) for Rq in Rs])
        vfd = np.vstack([np.zeros((1, 3)), np.diff(P, axis=0) / np.diff(T)[:, None]])
        speed = np.linalg.norm(vfd, axis=1)
        wang = np.array([0.0] + [math.radians(rot_angle_deg(Rs[i], Rs[i + 1])) / (T[i + 1] - T[i]) for i in range(len(Rs) - 1)])
        acc = np.linalg.norm(np.diff(vfd[1:], axis=0) / np.diff(T[1:])[:, None], axis=1) if len(T) > 2 else np.zeros(1)
        last = T >= T[-1] - 0.5
        drift = float(np.linalg.norm(P[-1, :2] - A[:2]))
        dz = float(P[-1, 2] - A[2])
        info = {"authored": A.tolist(), "first_sample": P[0].tolist(), "final": P[-1].tolist(), "height_change_from_authored_m": dz,
                "horizontal_drift_from_authored_m": drift, "max_tilt_deg": float(tilt.max()), "max_rotation_from_authored_deg": float(rot_dev.max()),
                "final_speed_m_s": float(speed[last].mean()), "peak_speed_m_s": float(speed.max()), "peak_angular_speed_rad_s": float(wang.max()),
                "peak_acceleration_m_s2": float(acc.max())}
        if k in inst_paths:
            inst = insts[k]
            pl = inst["placement"]
            ainfo = al.asset_info(inst["asset"])
            mass = ainfo["mass_properties"]["mass_kg"]
            fz = np.array([r[3][2] for r in R])
            mg = mass * env["physics"]["gravity_m_s2"]
            info.update(weight_N=mg, mean_normal_force_last_0_5s_N=float(np.nanmean(fz[last])))
            g = f"physics:{k}"
            if pl["surface"] == "on_instance":
                sup = stage.GetPrimAtPath(f"{root}/{pl['support']}")
                SM = UsdGeom.Xformable(sup).ComputeLocalToWorldTransform(0)
                sspec = specs[insts[pl["support"]]["asset"]]
                ss = al.support_surface(sspec, pl.get("support_surface"))
                Rf, pf = rot(R[-1][2]), P[-1]
                pts = np.array([Rf @ np.array(q) + pf for pc in al.collider_pieces(specs[inst["asset"]]) for q in pc["points"]])
                L = to_frame(pts, SM)
                floor_pen = float(ss["z"] - L[:, 2].min())
                if sspec["geometry"]["method"] == "open_container":
                    wall = max(float(np.max(np.abs(L[:, 0]) - np.array([al.container_inner_half(sspec, z)[0] for z in L[:, 2]]))),
                               float(np.max(np.abs(L[:, 1]) - np.array([al.container_inner_half(sspec, z)[1] for z in L[:, 2]]))))
                else:
                    wall = float(max(np.abs(L[:, 0]).max() - ss["half"][0], np.abs(L[:, 1]).max() - ss["half"][1]))
                H = al.nominal_size(sspec)[2]
                info.update(final_lowest_collider_above_support_m=-floor_pen, max_wall_intrusion_m=wall, final_top_local_z=float(L[:, 2].max()))
                check(g, "settled_on_support", abs(dz + env["objects"]["clearance"]) <= v["settle_max_height_change_m"]
                      and abs(floor_pen) <= v["penetration_tolerance_m"],
                      height_change_from_authored_mm=round(dz * 1000, 4), expected_drop_mm=env["objects"]["clearance"] * 1000,
                      final_gap_to_support_mm=round(-floor_pen * 1000, 4), support=pl["support"])
                check(g, "inside_support_no_penetration", wall <= v["penetration_tolerance_m"] and floor_pen <= v["penetration_tolerance_m"]
                      and L[:, 2].max() < H, max_wall_intrusion_mm=round(wall * 1000, 3), floor_penetration_mm=round(floor_pen * 1000, 4),
                      top_below_rim=bool(L[:, 2].max() < H),
                      note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)")
                check(g, "orientation_stable", info["max_rotation_from_authored_deg"] <= v["settle_max_tilt_deg"],
                      max_rotation_from_authored_deg=round(info["max_rotation_from_authored_deg"], 4))
            elif pl.get("pose") == "lying":  # lying on the tabletop: lowest collider vertex, rotation from the authored pose
                Rf, pf = rot(R[-1][2]), P[-1]
                zmin = float(min((Rf @ np.array(q) + pf)[2] for pc in al.collider_pieces(specs[inst["asset"]]) for q in pc["points"]))
                info.update(final_lowest_collider_z_m=zmin, final_bottom_gap_m=zmin - top_z)
                check(g, "settled_on_tabletop", abs(info["final_bottom_gap_m"]) <= v["penetration_tolerance_m"]
                      and abs(dz + env["objects"]["clearance"]) <= v["settle_max_height_change_m"],
                      final_bottom_gap_mm=round(info["final_bottom_gap_m"] * 1000, 4), height_change_from_authored_mm=round(dz * 1000, 4),
                      expected_drop_mm=env["objects"]["clearance"] * 1000, pose="lying")
                check(g, "orientation_stable", info["max_rotation_from_authored_deg"] <= v["settle_max_tilt_deg"],
                      max_rotation_from_authored_deg=round(info["max_rotation_from_authored_deg"], 4))
            else:
                info.update(final_bottom_z_m=float(P[-1, 2]), final_bottom_gap_m=float(P[-1, 2] - top_z))
                check(g, "settled_on_tabletop", abs(info["final_bottom_gap_m"]) <= v["penetration_tolerance_m"]
                      and abs(dz + env["objects"]["clearance"]) <= v["settle_max_height_change_m"],
                      final_bottom_gap_mm=round(info["final_bottom_gap_m"] * 1000, 4), height_change_from_authored_mm=round(dz * 1000, 4),
                      expected_drop_mm=env["objects"]["clearance"] * 1000)
                check(g, "remains_upright", info["max_tilt_deg"] <= v["settle_max_tilt_deg"], max_tilt_deg=round(info["max_tilt_deg"], 4))
            check(g, "no_horizontal_drift", drift <= v["settle_max_horizontal_drift_m"], drift_mm=round(drift * 1000, 3))
            check(g, "at_rest", info["final_speed_m_s"] <= v["settle_max_speed_m_s"], mean_speed_last_0_5s=f"{info['final_speed_m_s']:.2e}")
            if pl["surface"] == "on_instance":
                check(g, "no_extreme_motion", info["peak_speed_m_s"] <= 0.3 and info["peak_angular_speed_rad_s"] <= 5.0,
                      peak_speed_m_s=round(info["peak_speed_m_s"], 4), peak_angular_speed_rad_s=round(info["peak_angular_speed_rad_s"], 4),
                      peak_acceleration_m_s2=round(info["peak_acceleration_m_s2"], 2),
                      note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)")
            sup_name = "support" if pl["surface"] == "on_instance" else "tabletop"
            check(g, f"supported_by_{sup_name}_force", abs(info["mean_normal_force_last_0_5s_N"] - mg) <= 0.1 * mg,
                  normal_force_N=round(info["mean_normal_force_last_0_5s_N"], 5), weight_N=round(mg, 5))
        else:
            check("physics:base_objects", f"{k}_undisturbed", drift <= v["settle_max_horizontal_drift_m"]
                  and info["max_tilt_deg"] <= v["settle_max_tilt_deg"] and abs(dz) <= v["settle_max_height_change_m"],
                  drift_from_authored_mm=round(drift * 1000, 4), max_tilt_deg=round(info["max_tilt_deg"], 4),
                  height_change_from_authored_mm=round(dz * 1000, 4))
        res["bodies"][k] = info
    for k, R in crec.items():  # Test B: hollow containers
        d = drop[k]
        s = cube["object_size"]
        hs = s / 2
        P = np.array([r[1] for r in R])
        F = np.array([np.linalg.norm(r[3]) for r in R])
        T = np.array([r[0] for r in R])
        L = to_frame(P, d["M"])
        cdim = al.container_dims(d["spec"]["geometry"])
        H, tf = cdim["H"], cdim["tf"]
        hx_top, hy_top = al.container_inner_half(d["spec"], H)
        cross = np.nonzero(L[:, 2] - hs <= H)[0]
        ic = int(cross[0]) if len(cross) else None
        corner = hs * math.sqrt(2)
        inside_at_cross = ic is not None and abs(L[ic, 0]) <= hx_top - corner and abs(L[ic, 1]) <= hy_top - corner
        fin = L[-1]
        hx_f, hy_f = al.container_inner_half(d["spec"], tf)
        contained = abs(fin[0]) <= hx_f and abs(fin[1]) <= hy_f and fin[2] + hs <= H
        on_floor = abs((fin[2] - hs) - tf) <= 0.003
        last = T >= T[-1] - 0.3
        vfd = float(np.linalg.norm(np.diff(P[-30:], axis=0) / np.diff(T[-30:])[:, None], axis=1).mean())
        mg = cube["object_mass"] * env["physics"]["gravity_m_s2"]
        force = float(np.nanmean(F[last]))
        min_bottom = float((L[:, 2] - hs).min())
        im = int(np.argmin(L[:, 2]))
        info = {"t_min_bottom_s": float(T[im]), "bottom_z_around_min": (L[max(0, im - 3):im + 4, 2] - hs).round(5).tolist(),
                "speed_before_impact_m_s": float(np.linalg.norm(P[max(1, im - 1)] - P[max(0, im - 2)]) / (T[1] - T[0])),
                **{"start_world": d["start"], "final_local": fin.tolist(), "xy_local_at_rim_crossing": L[ic, :2].tolist() if ic is not None else None,
                "rim_local_z": H, "floor_top_local_z": tf, "min_cube_bottom_local_z": min_bottom, "final_speed_m_s": vfd,
                "floor_contact_force_N": force, "weight_N": mg}}
        res["drop_test"][k] = info
        g = f"physics:drop_test_{k}"
        check(g, "enters_through_open_top", inside_at_cross, xy_local_at_rim=info["xy_local_at_rim_crossing"],
              opening_half_m=[hx_top, hy_top], note="cube footprint (incl. its diagonal) inside the opening when crossing the rim")
        check(g, "contacts_floor", on_floor and abs(force - mg) <= 0.15 * mg, rest_bottom_local_z=round(fin[2] - hs, 5), floor_top_local_z=tf,
              floor_contact_force_N=round(force, 4), weight_N=round(mg, 4))
        check(g, "remains_inside", contained and vfd <= 0.01, final_local=fin.round(4).tolist(), final_speed=f"{vfd:.2e}")
        check(g, "no_floor_penetration", min_bottom >= tf - v["penetration_tolerance_m"], min_cube_bottom_local_z=round(min_bottom, 5),
              floor_top_local_z=tf)
    if move:
        g = f"physics:move_test_{move['instance']}"
        tgt, after = np.array(move["teleport_target"]), np.array(move["pose_after_teleport"])
        check(g, "moved_independently", np.linalg.norm(after[:2] - tgt[:2]) <= 0.002 and after[2] > np.array(move["start"])[2] + 0.04
              and move["others_max_displacement_m"] <= 0.001, pose_after_teleport=after.round(5).tolist(), target=tgt.round(5).tolist(),
              others_max_displacement_mm=round(move["others_max_displacement_m"] * 1000, 4))
        check(g, "resettled_after_move", move["final"][2] - move["start"][2] <= 0.003 and move["final_speed_m_s"] <= 0.01
              and abs(move["yaw_change_deg"] - 45.0) <= 5.0, final=np.round(move["final"], 5).tolist(), start=np.round(move["start"], 5).tolist(),
              yaw_change_deg=round(move["yaw_change_deg"], 3), final_speed=f"{move['final_speed_m_s']:.2e}")
        check(g, "visual_and_colliders_follow_rigid_body", move["visual_mesh_offset_from_root"] is not None
              and move["visual_mesh_offset_from_root"] <= 1e-9 and not move["reset_xform_stack"] and move["colliders"] > 0,
              visual_mesh_offset_from_root=move["visual_mesh_offset_from_root"], reset_xform_stack=move["reset_xform_stack"],
              usd_root_after_teleport=np.round(move["usd_root_after_teleport"], 5).tolist(),
              note="visual mesh and colliders are children of the rigid-body root with identity / asset-local transforms and no "
                   "resetXformStack, so they move with the body; usd_root_after_teleport shows whether PhysX wrote the pose back to USD")
    return res


def write_report(out_dir, res):
    o = [f"# Derived scene validation: `{res['scene_id']}`\n", f"- Generated: {res['generated']}",
         f"- Scene config: `{res['scene_config']}`; derived layer: `{res['output']}`; base scene: `{res['base_scene']}`",
         f"- **Result: {'PASS' if res['passed'] else 'FAIL'}** ({res['summary']})", f"- Physics test: {res['physics_run']}\n",
         "| Group | Check | Result | Key values |", "|---|---|---|---|"]
    for g, v in res["checks"].items():
        for k, c in v.items():
            det = "; ".join(f"{a}={json.dumps(b, default=str)}" for a, b in c.items() if a != "passed" and len(json.dumps(b, default=str)) < 110)
            o.append(f"| {g} | `{k}` | {'PASS' if c['passed'] else '**FAIL**'} | {det.replace('|', '/')} |")
    o.append("\nScope: these checks cover the added instances and the integrity of the base scene. They do not re-run the "
             "workstation's own 94 static / 39 dynamic checks (run those with a config copy that points paths.scene at the "
             "derived layer; scripts/assets/add_asset.py --base-suites does this) and do not imply physical realism beyond "
             "the modelled rigid-body approximation.")
    for w in res["warnings"]:
        o.append(f"- warning: {w}")
    with open(os.path.join(out_dir, "validation_report.md"), "w") as f:
        f.write("\n".join(o) + "\n")


def main():
    import datetime as dt

    scene = al.load_scene(args.scene)
    env = al.load_json(scene["environment_config"])
    out_dir = al.abspath(f"logs/assets/{scene['scene_id']}")
    os.makedirs(out_dir, exist_ok=True)
    stage = structure_checks(scene, scene["output"])
    physics = None
    if stage is not None:
        registry_checks(scene)
        poses = al.scene_poses(scene, env, al.specs_for(scene))
        boxes = instance_checks(stage, scene, env, poses)
        placement_checks(stage, scene, env, boxes)
        preservation_checks(stage, scene)
        scene_checks(stage, scene)
        if not args.no_physics and all(al.asset_info(i["asset"])["spec"].get("validation", {}).get("settle_test", True)
                                       for i in scene["instances"]):
            physics = physics_checks(scene, env)
    flat = [(g, k, c) for g, v in CHECKS.items() for k, c in v.items()]
    failed = [f"{g}.{k}" for g, k, c in flat if not c["passed"]]
    res = {"scene_id": scene["scene_id"], "scene_config": args.scene, "output": scene["output"], "base_scene": scene["base_scene"],
           "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "passed": not failed,
           "summary": f"{len(flat) - len(failed)}/{len(flat)} checks passed", "failed": failed,
           "physics_run": "yes" if physics else "no (--no-physics or disabled by spec)", "physics": physics,
           "checks": CHECKS, "warnings": WARN}
    with open(os.path.join(out_dir, "validation_results.json"), "w") as f:
        json.dump(res, f, indent=2, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x))
    write_report(out_dir, res)
    print(f"[validate-asset] {res['summary']}; failed: {failed}", flush=True)
    return 0 if not failed else 1


code = 1
try:
    t_start = time.time()
    code = main()
    print(f"[validate-asset] done in {time.time() - t_start:.1f}s", flush=True)
except Exception:
    traceback.print_exc()
    code = 2
finally:
    simulation_app.close(exit_code=code)
    sys.exit(code)
