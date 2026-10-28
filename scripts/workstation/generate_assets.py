"""Generate all reusable workstation assets (visual + collision + physics) headless in Blender.

Run from the waste-sorting-workstation directory:
    blender -b --factory-startup --python-exit-code 1 \
        --python scripts/workstation/generate_assets.py -- --config config/waste_sorting_environment.json

For every asset this writes, under assets/workstation/<asset>/:
    <asset>_visual.usd   Blender-exported render mesh + UsdPreviewSurface materials (no physics)
    <asset>.usd          the reusable asset: references the visual file, adds collider prims
                         (purpose=guide, separate from the visual mesh), a UsdPhysics material,
                         and for dynamic objects RigidBodyAPI + MassAPI (mass, COM, inertia
                         computed from the closed visual mesh)
and a manifest (assets/workstation/asset_manifest.json) with dimensions and mass properties.

Local frames: every object/bin/crate/leg asset has its origin at the bottom centre, Z up.
The tabletop asset has its origin at its geometric centre. No world coordinates are baked in.
PhysX-specific attributes (combine modes) are authored later in build_scene.py because
Blender's bundled USD does not include PhysxSchema.
"""

import argparse
import json
import math
import os
import sys
import traceback

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT = {"assets": {}, "warnings": [], "ok": False}


# ---------------------------------------------------------------------------
# Generic geometry helpers
# ---------------------------------------------------------------------------

def lathe(profile, segments):
    """Revolve an (r, z) profile around Z. r == 0 points become single pole vertices.
    Returns (verts, faces) of a closed surface if both ends are poles."""
    verts, rings = [], []
    for r, z in profile:
        if r <= 1e-9:
            rings.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            ring = []
            for k in range(segments):
                a = 2 * math.pi * k / segments
                ring.append(len(verts))
                verts.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(ring)
    faces = []
    for ra, rb in zip(rings[:-1], rings[1:]):
        if len(ra) == 1 and len(rb) == 1:
            continue
        for k in range(segments):
            k2 = (k + 1) % segments
            if len(ra) == 1:
                faces.append((ra[0], rb[k], rb[k2]))
            elif len(rb) == 1:
                faces.append((ra[k], rb[0], ra[k2]))
            else:
                faces.append((ra[k], ra[k2], rb[k2], rb[k]))
    return verts, faces


def mesh_object(name, verts, faces, material, smooth_angle=35.0):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material:
        me.materials.append(material)
    for poly in me.polygons:
        poly.use_smooth = True
    try:
        mod = ob.modifiers.new("Smooth", "SMOOTH_BY_ANGLE")
        mod["Input_1"] = math.radians(smooth_angle)
    except Exception:
        pass
    return ob


def box_object(name, size, center, material, bevel=0.0, rotation_z_deg=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.name = ob.data.name = name
    ob.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = ob.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.rotation_euler = (0, 0, math.radians(rotation_z_deg))
    ob.location = center
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
    if material:
        ob.data.materials.append(material)
    return ob


def text_object(name, text, size, center, face_normal, material, extrude=0.0008):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = text
    curve.size = size
    curve.extrude = extrude
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    ob = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(ob)
    # Text lies in XY facing +Z. Rx(90) makes it face -Y; Rz(atan2(n)+90) turns it to the face normal.
    yaw = math.atan2(face_normal[1], face_normal[0]) + math.pi / 2
    ob.rotation_euler = Euler((math.pi / 2, 0, yaw), "XYZ")
    ob.location = center
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.convert(target="MESH")
    ob = bpy.context.active_object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.data.materials.clear()
    ob.data.materials.append(material)
    return ob


def material(name, color, roughness=0.5, metallic=0.0, alpha=1.0, ior=1.45):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    bsdf.inputs["IOR"].default_value = ior
    m.diffuse_color = (*color, alpha)
    return m


def world_triangles(objs):
    tris = []
    for ob in objs:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        mw = ob.matrix_world
        co = [mw @ v.co for v in me.vertices]
        for t in me.loop_triangles:
            tris.append([tuple(co[i]) for i in t.vertices])
        ev.to_mesh_clear()
    return np.array(tris, dtype=float)


def mass_properties(tris, mass):
    """Uniform-density mass properties of a closed triangle mesh, scaled to the given mass."""
    canon = np.array([[2, 1, 1], [1, 2, 1], [1, 1, 2]], float) / 120.0
    vol, first, cov = 0.0, np.zeros(3), np.zeros((3, 3))
    for a, b, c in tris:
        A = np.column_stack([a, b, c])
        d = np.linalg.det(A)
        vol += d / 6.0
        first += d / 24.0 * (a + b + c)
        cov += d * A @ canon @ A.T
    com = first / vol
    rho = mass / vol
    C = rho * cov - mass * np.outer(com, com)
    inertia = np.trace(C) * np.eye(3) - C
    return {"volume_m3": float(vol), "density_kg_m3": float(rho), "center_of_mass": com.tolist(),
            "inertia_tensor": inertia.tolist(), "diagonal_inertia": np.diag(inertia).tolist(),
            "max_offdiag_ratio": float(np.abs(inertia - np.diag(np.diag(inertia))).max() / np.diag(inertia).max())}


def combine_mass(parts):
    """Combine (mass, com, inertia_about_com) parts into one rigid body."""
    m = sum(p[0] for p in parts)
    com = sum(p[0] * np.array(p[1]) for p in parts) / m
    I = np.zeros((3, 3))
    for pm, pc, pi in parts:
        d = np.array(pc) - com
        I += np.array(pi) + pm * (np.dot(d, d) * np.eye(3) - np.outer(d, d))
    return m, com, I


def bounds(objs):
    pts = np.array([list(ob.matrix_world @ v.co) for ob in objs for v in ob.data.vertices])
    return pts.min(axis=0).tolist(), pts.max(axis=0).tolist()


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0


def export_visual(objs, path):
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.wm.usd_export(filepath=path, selected_objects_only=True, export_materials=True,
                          export_normals=True, export_uvmaps=True)
    if not os.path.isfile(path):
        raise RuntimeError(f"visual export failed: {path}")


# ---------------------------------------------------------------------------
# USD asset assembly (UsdPhysics only)
# ---------------------------------------------------------------------------

def write_asset(path, root_name, visual_file, colliders, phys_mat, dynamic=None, info=None, sub_refs=None):
    from pxr import Gf, Kind, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt

    if os.path.exists(path):
        os.remove(path)
    layer = Sdf.Layer.CreateNew(path, args={"format": "usda"})
    stage = Usd.Stage.Open(layer)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, f"/{root_name}")
    stage.SetDefaultPrim(root.GetPrim())
    Usd.ModelAPI(root.GetPrim()).SetKind(Kind.Tokens.component)
    if info:
        root.GetPrim().SetCustomDataByKey("robot_agent_lab_json", json.dumps(info))

    if visual_file:
        vis = UsdGeom.Xform.Define(stage, f"/{root_name}/Visual")
        vis.GetPrim().GetReferences().AddReference(f"./{os.path.basename(visual_file)}")
    for ref in sub_refs or []:
        xf = UsdGeom.Xform.Define(stage, f"/{root_name}/{ref['name']}")
        xf.GetPrim().GetReferences().AddReference(ref["file"])
        xf.AddTranslateOp().Set(Gf.Vec3d(*ref["translate"]))

    mat = None
    if phys_mat:
        mat = UsdShade.Material.Define(stage, f"/{root_name}/PhysicsMaterial")
        api = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
        api.CreateStaticFrictionAttr(float(phys_mat["static_friction"]))
        api.CreateDynamicFrictionAttr(float(phys_mat["dynamic_friction"]))
        api.CreateRestitutionAttr(float(phys_mat["restitution"]))
        mat.GetPrim().SetCustomDataByKey("robot_agent_lab:material_id", phys_mat["id"])

    if colliders:
        UsdGeom.Scope.Define(stage, f"/{root_name}/Collision")
    for c in colliders:
        base = f"/{root_name}/Collision/{c['name']}"
        if c["type"] == "box":
            xf = UsdGeom.Xform.Define(stage, base)
            xf.AddTranslateOp().Set(Gf.Vec3d(*c["center"]))
            if "rotate_xyz_deg" in c:
                xf.AddRotateXYZOp().Set(Gf.Vec3f(*c["rotate_xyz_deg"]))
            cube = UsdGeom.Cube.Define(stage, base + "/Shape")
            cube.CreateSizeAttr(1.0)
            cube.AddScaleOp().Set(Gf.Vec3f(*c["size"]))
            prim = cube.GetPrim()
        elif c["type"] == "cylinder":
            xf = UsdGeom.Xform.Define(stage, base)
            xf.AddTranslateOp().Set(Gf.Vec3d(*c["center"]))
            cyl = UsdGeom.Cylinder.Define(stage, base + "/Shape")
            cyl.CreateAxisAttr("Z")
            cyl.CreateRadiusAttr(float(c["radius"]))
            cyl.CreateHeightAttr(float(c["height"]))
            prim = cyl.GetPrim()
        elif c["type"] == "convex":
            mesh = UsdGeom.Mesh.Define(stage, base)
            mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in c["verts"]]))
            mesh.CreateFaceVertexCountsAttr([len(f) for f in c["faces"]])
            mesh.CreateFaceVertexIndicesAttr([i for f in c["faces"] for i in f])
            mesh.CreateSubdivisionSchemeAttr("none")
            prim = mesh.GetPrim()
            UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr("convexHull")
        else:
            raise ValueError(c["type"])
        UsdGeom.Imageable(prim).CreatePurposeAttr(UsdGeom.Tokens.guide)
        UsdPhysics.CollisionAPI.Apply(prim)
        if mat:
            UsdShade.MaterialBindingAPI.Apply(prim)
            UsdShade.MaterialBindingAPI(prim).Bind(mat, UsdShade.Tokens.weakerThanDescendants, "physics")

    if dynamic:
        UsdPhysics.RigidBodyAPI.Apply(root.GetPrim())
        m = UsdPhysics.MassAPI.Apply(root.GetPrim())
        m.CreateMassAttr(float(dynamic["mass"]))
        m.CreateCenterOfMassAttr(Gf.Vec3f(*dynamic["center_of_mass"]))
        m.CreateDiagonalInertiaAttr(Gf.Vec3f(*dynamic["diagonal_inertia"]))
        m.CreatePrincipalAxesAttr(Gf.Quatf(1, 0, 0, 0))
    layer.Save()


# ---------------------------------------------------------------------------
# Asset builders
# ---------------------------------------------------------------------------

def out_dir(cfg, name):
    d = os.path.join(ROOT, cfg["paths"]["assets_dir"], name)
    os.makedirs(d, exist_ok=True)
    return d


def phys(cfg, key):
    return {"id": key, **cfg["physics"]["materials"][key]}


def build_table(cfg):
    t = cfg["table"]
    d = out_dir(cfg, "table")
    L, W, H, T = t["length"], t["width"], t["height"], t["top_thickness"]
    s, lh = t["leg_size"], t["leg_height"]
    if abs(lh + T - H) > 1e-9:
        raise ValueError(f"leg_height + top_thickness ({lh + T}) != table height ({H})")
    # Tabletop (origin at its geometric centre)
    clear_scene()
    top_mat = material("TabletopMaterial", t["top_color"], t["top_roughness"])
    top = box_object("Tabletop", (L, W, T), (0, 0, 0), top_mat, t["top_bevel"])
    vis_top = os.path.join(d, "tabletop_visual.usd")
    bmin, bmax = bounds([top])
    export_visual([top], vis_top)
    write_asset(os.path.join(d, "tabletop.usd"), "Tabletop", vis_top,
                [{"type": "box", "name": "TopSlab", "size": [L, W, T], "center": [0, 0, 0]}],
                phys(cfg, t["physics_material"]), info={"frame": "geometric centre", "size": [L, W, T]})
    # Leg (origin at bottom centre)
    clear_scene()
    leg_mat = material("LegMaterial", t["leg_color"], t["leg_roughness"], t["leg_metallic"])
    leg = box_object("Leg", (s, s, lh), (0, 0, lh / 2), leg_mat, t["leg_bevel"])
    vis_leg = os.path.join(d, "table_leg_visual.usd")
    lmin, lmax = bounds([leg])
    export_visual([leg], vis_leg)
    write_asset(os.path.join(d, "table_leg.usd"), "TableLeg", vis_leg,
                [{"type": "box", "name": "LegBox", "size": [s, s, lh], "center": [0, 0, lh / 2]}],
                phys(cfg, t["physics_material"]), info={"frame": "bottom centre", "size": [s, s, lh]})
    # Assembled table (origin on the floor under the table centre)
    if t["leg_inset_reference"] == "leg_outer_face":
        lx, ly = L / 2 - t["leg_inset"] - s / 2, W / 2 - t["leg_inset"] - s / 2
    else:
        lx, ly = L / 2 - t["leg_inset"], W / 2 - t["leg_inset"]
    legs = [{"name": f"Leg_{n}", "file": "./table_leg.usd", "translate": [sx * lx, sy * ly, 0.0]}
            for n, sx, sy in (("FL", 1, -1), ("FR", 1, 1), ("BL", -1, -1), ("BR", -1, 1))]
    subs = [{"name": "Tabletop", "file": "./tabletop.usd", "translate": [0, 0, H - T / 2]}] + legs
    write_asset(os.path.join(d, "table.usd"), "Table", None, [], None, sub_refs=subs,
                info={"frame": "floor under table centre", "length": L, "width": W, "height": H,
                      "leg_centres_xy": [[sx * lx, sy * ly] for _, sx, sy in (("", 1, -1), ("", 1, 1), ("", -1, -1), ("", -1, 1))]})
    return {"tabletop_bounds": [bmin, bmax], "leg_bounds": [lmin, lmax], "leg_centre_offset": [lx, ly],
            "files": ["table.usd", "tabletop.usd", "table_leg.usd", "tabletop_visual.usd", "table_leg_visual.usd"]}


def glass_bottle_profile(o):
    H, R, rn = o["height"], o["body_diameter"] / 2, o["neck_diameter"] / 2
    rl, t, tb = o["lip_diameter"] / 2, o["wall_thickness"], o["base_thickness"]
    zb, zs = o["body_top_z"], o["shoulder_top_z"]
    ri = rn - 0.0035
    sh = lambda u: rn + (R - rn) * (1 + math.cos(math.pi * u)) / 2
    outer = [(0, 0), (R - 0.004, 0), (R - 0.0012, 0.0008), (R, 0.004), (R, zb)]
    outer += [(sh(u), zb + (zs - zb) * u) for u in np.linspace(0.1, 1.0, 10)]
    outer += [(rn, H - 0.014), (rl, H - 0.012), (rl, H - 0.003), (rl - 0.0008, H - 0.0003), (rl - 0.0018, H)]
    inner = [(ri, H), (ri, zs + 0.004)]
    inner += [(max(sh(u) - t, ri), zb + (zs - zb) * u) for u in np.linspace(1.0, 0.0, 11)[1:]]
    inner += [(R - t, tb + 0.004), (R - t - 0.004, tb), (0, tb + 0.002)]
    return outer + inner


def build_glass_bottle(cfg):
    o = cfg["objects"]["glass_bottle"]
    d = out_dir(cfg, "glass_bottle")
    clear_scene()
    m = material("BlueGlass", o["color"], o["roughness"], 0.0, o["opacity"], o["ior"])
    v, f = lathe(glass_bottle_profile(o), 48)
    ob = mesh_object("GlassBottle", v, f, m)
    tris = world_triangles([ob])
    mp = mass_properties(tris, o["mass"])
    bmin, bmax = bounds([ob])
    vis = os.path.join(d, "glass_bottle_visual.usd")
    export_visual([ob], vis)
    R, rn, rl = o["body_diameter"] / 2, o["neck_diameter"] / 2, o["lip_diameter"] / 2
    zb, zs, H = o["body_top_z"], o["shoulder_top_z"], o["height"]
    sv, sf = lathe([(0, zb)] + [(rn + (R - rn) * (1 + math.cos(math.pi * u)) / 2, zb + (zs - zb) * u)
                                for u in np.linspace(0, 1, 6)] + [(0, zs)], 16)
    colliders = [
        {"type": "cylinder", "name": "Body", "radius": R, "height": zb, "center": [0, 0, zb / 2]},
        {"type": "convex", "name": "Shoulder", "verts": sv, "faces": sf},
        {"type": "cylinder", "name": "Neck", "radius": rl, "height": H - zs, "center": [0, 0, (zs + H) / 2]},
    ]
    write_asset(os.path.join(d, "glass_bottle.usd"), "GlassBottle", vis, colliders, phys(cfg, o["physics_material"]),
                dynamic={"mass": o["mass"], **mp},
                info={"frame": "bottom centre", "collision": "compound: body cylinder + shoulder convex hull + neck cylinder (solid, not hollow)"})
    return {"bounds": [bmin, bmax], "mass_properties": mp, "triangles": len(tris), "colliders": [c["name"] for c in colliders],
            "files": ["glass_bottle.usd", "glass_bottle_visual.usd"]}


def build_plastic_bottle(cfg):
    o = cfg["objects"]["plastic_bottle"]
    d = out_dir(cfg, "plastic_bottle")
    clear_scene()
    H, R, rn, t = o["height"], o["body_diameter"] / 2, o["neck_diameter"] / 2, o["wall_thickness"]
    zb, zs, ch, rc = o["body_top_z"], o["shoulder_top_z"], o["cap_height"], o["cap_diameter"] / 2
    zc = H - ch
    body_r = lambda z: R - 0.0025 * (math.exp(-((z - 0.070) / 0.006) ** 2) + math.exp(-((z - 0.105) / 0.006) ** 2))
    sh = lambda u: rn + (R - rn) * (1 + math.cos(math.pi * u)) / 2
    outer = [(0, 0.004), (R - 0.008, 0.0), (R - 0.001, 0.002), (R, 0.008)]
    outer += [(body_r(z), z) for z in np.linspace(0.012, zb, 26)]
    outer += [(sh(u), zb + (zs - zb) * u) for u in np.linspace(0.1, 1.0, 10)]
    outer += [(rn, zs + 0.004), (rn + 0.0035, zs + 0.004), (rn + 0.0035, zs + 0.0065), (rn, zs + 0.0065), (rn, zc + 0.001)]
    inner = [(rn - 0.0015, zc + 0.001), (rn - 0.0015, zs + 0.002)]
    inner += [(max(sh(u) - t, rn - 0.0015), zb + (zs - zb) * u) for u in np.linspace(1.0, 0.0, 11)[1:]]
    inner += [(body_r(z) - t, z) for z in np.linspace(zb, 0.012, 26)[1:]]
    inner += [(R - t, 0.008), (R - 0.008, t), (0, 0.004 + t)]
    pet = material("PET", o["color"], o["roughness"], 0.0, o["opacity"], 1.57)
    capm = material("Cap", o["cap_color"], 0.5)
    vb, fb = lathe(outer + inner, 48)
    body = mesh_object("PlasticBottle", vb, fb, pet)
    vc, fc = lathe([(0, zc), (rc, zc), (rc, H - 0.0015), (rc - 0.0015, H), (0, H)], 32)
    cap = mesh_object("Cap", vc, fc, capm, smooth_angle=30)
    mp_b = mass_properties(world_triangles([body]), o["mass"] - o["cap_mass"])
    mp_c = mass_properties(world_triangles([cap]), o["cap_mass"])
    m, com, I = combine_mass([(o["mass"] - o["cap_mass"], mp_b["center_of_mass"], mp_b["inertia_tensor"]),
                              (o["cap_mass"], mp_c["center_of_mass"], mp_c["inertia_tensor"])])
    mp = {"center_of_mass": com.tolist(), "diagonal_inertia": np.diag(I).tolist(), "inertia_tensor": I.tolist(),
          "body_shell": mp_b, "cap": mp_c}
    bmin, bmax = bounds([body, cap])
    vis = os.path.join(d, "plastic_bottle_visual.usd")
    export_visual([body, cap], vis)
    sv, sf = lathe([(0, zb)] + [(sh(u), zb + (zs - zb) * u) for u in np.linspace(0, 1, 6)] + [(0, zs)], 16)
    colliders = [
        {"type": "cylinder", "name": "Body", "radius": R, "height": zb, "center": [0, 0, zb / 2]},
        {"type": "convex", "name": "Shoulder", "verts": sv, "faces": sf},
        {"type": "cylinder", "name": "Neck", "radius": rn + 0.0035, "height": zc - zs, "center": [0, 0, (zs + zc) / 2]},
        {"type": "cylinder", "name": "Cap", "radius": rc, "height": ch, "center": [0, 0, zc + ch / 2]},
    ]
    write_asset(os.path.join(d, "plastic_bottle.usd"), "PlasticBottle", vis, colliders, phys(cfg, o["physics_material"]),
                dynamic={"mass": o["mass"], **mp},
                info={"frame": "bottom centre", "deformation": "not modelled (rigid body)",
                      "collision": "compound: body cylinder + shoulder convex hull + neck/ring cylinder + cap cylinder"})
    return {"bounds": [bmin, bmax], "mass_properties": mp, "colliders": [c["name"] for c in colliders],
            "files": ["plastic_bottle.usd", "plastic_bottle_visual.usd"]}


def build_paper_cup(cfg):
    o = cfg["objects"]["paper_cup"]
    d = out_dir(cfg, "paper_cup")
    clear_scene()
    H, Rt, Rb, t = o["height"], o["top_diameter"] / 2, o["bottom_diameter"] / 2, o["wall_thickness"]
    rec, rr = o["bottom_recess"], o["rim_radius"]
    r_out = lambda z: Rb + (Rt - Rb) * z / H
    cr, cz = Rt - rr, H - rr  # rolled rim stays inside the nominal top diameter
    rim = [(cr + rr * math.cos(math.radians(a)), cz + rr * math.sin(math.radians(a))) for a in range(-60, 241, 20)]
    outer = [(0, rec), (Rb - t - 0.0005, rec), (Rb - t, 0.0006), (Rb - t * 0.4, 0.0), (Rb, 0.0006)]
    outer += [(r_out(z), z) for z in np.linspace(0.002, rim[0][1] - 0.0005, 8)]
    inner = [(r_out(z) - t, z) for z in np.linspace(rim[-1][1] - 0.0005, rec + t + 0.001, 8)]
    inner += [(0, rec + t)]
    paper = material("Paper", o["color"], o["roughness"])
    v, f = lathe(outer + rim + inner, 48)
    ob = mesh_object("PaperCup", v, f, paper, smooth_angle=50)
    mp = mass_properties(world_triangles([ob]), o["mass"])
    bmin, bmax = bounds([ob])
    vis = os.path.join(d, "paper_cup_visual.usd")
    export_visual([ob], vis)
    n, tc = o["collision_wall_segments"], o["collision_wall_thickness"]
    slant = math.hypot(H, Rt - Rb)
    tilt = math.degrees(math.atan2(Rt - Rb, H))
    width = 2 * Rt * math.sin(math.pi / n) * 1.08
    rmid = (Rt + Rb) / 2 - tc / 2
    colliders = [{"type": "cylinder", "name": "Bottom", "radius": Rb - 0.0005, "height": rec + t,
                  "center": [0, 0, (rec + t) / 2]}]
    for k in range(n):
        a = 360.0 * k / n
        colliders.append({"type": "box", "name": f"Wall_{k:02d}", "size": [tc, width, slant],
                          "center": [rmid * math.cos(math.radians(a)), rmid * math.sin(math.radians(a)), H / 2],
                          "rotate_xyz_deg": [0.0, tilt, a]})
    write_asset(os.path.join(d, "paper_cup.usd"), "PaperCup", vis, colliders, phys(cfg, o["physics_material"]),
                dynamic={"mass": o["mass"], **mp},
                info={"frame": "bottom centre", "collision": f"compound: base cylinder + {n} tilted wall boxes (open top, hollow)",
                      "deformation": "not modelled"})
    return {"bounds": [bmin, bmax], "mass_properties": mp, "colliders": len(colliders),
            "files": ["paper_cup.usd", "paper_cup_visual.usd"]}


FACE_NORMALS = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}


def open_box_parts(W, D, H, t, tb):
    """Bottom + 4 walls of an open-top container, origin bottom centre. Returns name -> (size, centre)."""
    wh = H - tb
    return {
        "Bottom": ([W, D, tb], [0, 0, tb / 2]),
        "WallPosX": ([t, D, wh], [W / 2 - t / 2, 0, tb + wh / 2]),
        "WallNegX": ([t, D, wh], [-W / 2 + t / 2, 0, tb + wh / 2]),
        "WallPosY": ([W - 2 * t, t, wh], [0, D / 2 - t / 2, tb + wh / 2]),
        "WallNegY": ([W - 2 * t, t, wh], [0, -D / 2 + t / 2, tb + wh / 2]),
    }


def build_bin(cfg, key):
    c = {**cfg["bins"]["common"], **cfg["bins"][key]}
    d = out_dir(cfg, c["asset"])
    clear_scene()
    W, D, H, t = c["width"], c["depth"], c["height"], c["wall_thickness"]
    body = material(f"{key}_Plastic", c["color"], 0.45)
    rim = material(f"{key}_Rim", c["rim_color"], 0.4)
    white = material("LabelPlate", (0.95, 0.95, 0.95), 0.6)
    ink = material("LabelText", (0.03, 0.03, 0.03), 0.5)
    parts = open_box_parts(W, D, H, t, t)
    objs = []
    rh = c["rim_height"]
    for name, (size, cen) in parts.items():
        if name == "Bottom":
            objs.append(box_object(name, size, cen, body, c["bevel"]))
            continue
        lower = [size[0], size[1], size[2] - rh]
        objs.append(box_object(name, lower, [cen[0], cen[1], t + lower[2] / 2], body, c["bevel"]))
        objs.append(box_object(name + "_Rim", [size[0], size[1], rh], [cen[0], cen[1], H - rh / 2], rim, c["bevel"]))
    lw, lh = c["label_size"]
    faces = list(c["label_faces"]) + ([c["extra_label_face"]] if c.get("extra_label_face") else [])
    for fname in faces:
        nx, ny = FACE_NORMALS[fname]
        half = (W if nx else D) / 2
        plate_size = [0.002, lw, lh] if nx else [lw, 0.002, lh]
        objs.append(box_object(f"LabelPlate{fname}", plate_size,
                               [nx * (half + 0.001), ny * (half + 0.001), c["label_center_z"]], white, 0.0005))
        size = 0.052 if len(c["label"]) <= 5 else 0.040
        objs.append(text_object(f"LabelText{fname}", c["label"], size,
                                (nx * (half + 0.0022), ny * (half + 0.0022), c["label_center_z"]), (nx, ny), ink))
    bmin, bmax = bounds(objs)
    vis = os.path.join(d, f"{c['asset']}_visual.usd")
    export_visual(objs, vis)
    colliders = [{"type": "box", "name": n, "size": s, "center": cen} for n, (s, cen) in parts.items()]
    write_asset(os.path.join(d, f"{c['asset']}.usd"), "".join(w.capitalize() for w in c["asset"].split("_")), vis,
                colliders, phys(cfg, c["physics_material"]),
                info={"frame": "bottom centre", "label": c["label"], "outer_size": [W, D, H], "wall_thickness": t,
                      "collision": "compound open-top: bottom + 4 wall boxes; labels are visual only",
                      "inner_opening": [W - 2 * t, D - 2 * t]})
    return {"bounds": [bmin, bmax], "colliders": list(parts), "label": c["label"], "label_faces": faces,
            "files": [f"{c['asset']}.usd", f"{c['asset']}_visual.usd"]}


def build_crate(cfg):
    c = cfg["crate"]
    d = out_dir(cfg, c["asset"])
    clear_scene()
    L, W, H, t, tb = c["length"], c["width"], c["height"], c["wall_thickness"], c["bottom_thickness"]
    st, sh = c["separator_thickness"], c["separator_height"]
    nx, ny = c["cells"]
    body = material("CratePlastic", c["color"], c["roughness"])
    parts = open_box_parts(L, W, H, t, tb)
    il, iw = L - 2 * t, W - 2 * t
    for i in range(1, nx):
        x = -il / 2 + il * i / nx
        parts[f"SeparatorX{i}"] = ([st, iw, sh], [x, 0, tb + sh / 2])
    for j in range(1, ny):
        y = -iw / 2 + iw * j / ny
        parts[f"SeparatorY{j}"] = ([il, st, sh], [0, y, tb + sh / 2])
    objs = [box_object(n, s, cen, body, 0.002) for n, (s, cen) in parts.items()]
    # Simple hand-hold slots on the short walls, as darker inset plates (visual only)
    dark = material("CrateHandle", [x * 0.5 for x in c["color"]], 0.7)
    for sx in (1, -1):
        objs.append(box_object(f"Handle{'+' if sx > 0 else '-'}", [0.003, 0.11, 0.035],
                               [sx * (L / 2 + 0.0012), 0, H - 0.05], dark, 0.001))
    bmin, bmax = bounds(objs)
    vis = os.path.join(d, f"{c['asset']}_visual.usd")
    export_visual(objs, vis)
    colliders = [{"type": "box", "name": n, "size": s, "center": cen} for n, (s, cen) in parts.items()]
    cells = [[-il / 2 + il * (i + 0.5) / nx, -iw / 2 + iw * (j + 0.5) / ny] for i in range(nx) for j in range(ny)]
    write_asset(os.path.join(d, f"{c['asset']}.usd"), "GlassCrate", vis, colliders, phys(cfg, c["physics_material"]),
                info={"frame": "bottom centre", "outer_size": [L, W, H], "cells": [nx, ny],
                      "collision": "compound open-top: bottom + 4 walls + separators"})
    return {"bounds": [bmin, bmax], "colliders": list(parts), "cell_centres_local": cells,
            "files": [f"{c['asset']}.usd", f"{c['asset']}_visual.usd"]}


def build_crate_platform(cfg):
    """Static lab side cabinet that raises the glass crate (dimensions from config crate_platform)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import layout_geometry as lg

    p = cfg["crate_platform"]
    d = out_dir(cfg, p["asset"])
    clear_scene()
    mats = {"Kick": material("PlatformKick", p["kick_color"], 0.6), "Body": material("PlatformBody", p["body_color"], 0.45, 0.3),
            "Top": material("PlatformTop", p["top_color"], 0.5)}
    parts = lg.platform_parts(p)
    objs = [box_object(n, s, c, mats[n], 0.003 if n != "Kick" else 0.0015) for n, (s, c) in parts.items()]
    # visual-only door seam and handle on the +X and -X faces
    seam = material("PlatformSeam", [x * 0.55 for x in p["body_color"]], 0.6)
    bl = parts["Body"][0][0]
    zc = parts["Body"][1][2]
    for sx in (1, -1):
        objs.append(box_object(f"Seam{'+' if sx > 0 else '-'}", [0.002, 0.004, parts["Body"][0][2] - 0.04], [sx * (bl / 2 + 0.0008), 0, zc], seam))
        objs.append(box_object(f"Handle{'+' if sx > 0 else '-'}", [0.012, 0.012, 0.10], [sx * (bl / 2 + 0.006), 0.03, zc + 0.08], seam, 0.003))
    bmin, bmax = bounds(objs)
    vis = os.path.join(d, f"{p['asset']}_visual.usd")
    export_visual(objs, vis)
    colliders = [{"type": "box", "name": n, "size": s, "center": c} for n, (s, c) in parts.items()]
    write_asset(os.path.join(d, f"{p['asset']}.usd"), "CratePlatform", vis, colliders, phys(cfg, p["physics_material"]),
                info={"frame": "bottom centre", "height": p["height"], "top_size": [p["top_length"], p["top_width"]],
                      "collision": "static: kick plinth + body + top plate (identical to the visual boxes)"})
    return {"bounds": [bmin, bmax], "colliders": list(parts), "files": [f"{p['asset']}.usd", f"{p['asset']}_visual.usd"]}


def config_path():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/waste_sorting_environment.json")
    args = ap.parse_args(argv)
    return args.config if os.path.isabs(args.config) else os.path.join(ROOT, args.config)


def main():
    with open(config_path()) as f:
        cfg = json.load(f)
    REPORT["blender_version"] = bpy.app.version_string
    builders = [("table", build_table), ("glass_bottle", build_glass_bottle), ("plastic_bottle", build_plastic_bottle),
                ("paper_cup", build_paper_cup), ("paper_bin", lambda c: build_bin(c, "paper_bin")),
                ("plastic_bin", lambda c: build_bin(c, "plastic_bin")), ("glass_crate", build_crate),
                ("crate_platform", build_crate_platform)]
    for name, fn in builders:
        print(f"[assets] building {name}", flush=True)
        REPORT["assets"][name] = fn(cfg)
    REPORT["ok"] = True


def run():
    try:
        main()
    except Exception as exc:
        REPORT["error"] = f"{type(exc).__name__}: {exc}"
        REPORT["traceback"] = traceback.format_exc()
        print(REPORT["traceback"], file=sys.stderr)
    finally:
        try:
            cfgd = json.load(open(config_path()))
            p = os.path.join(ROOT, cfgd["paths"]["assets_dir"], "asset_manifest.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                json.dump(REPORT, f, indent=2, default=str)
        except Exception:
            traceback.print_exc()
        print("[assets] OK" if REPORT["ok"] else "[assets] FAILED", flush=True)
        if not REPORT["ok"]:
            sys.exit(1)


# Blender runs `--python <file>` as __main__; importing this module (scripts/assets/generate_asset.py reuses
# its geometry/USD helpers) must not regenerate the workstation assets.
if __name__ == "__main__":
    run()
