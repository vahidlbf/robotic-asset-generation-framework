"""Blender side of the backend comparison (scripts/assets/compare_backends.py). READ-ONLY on the asset library.

    blender -b --factory-startup --python scripts/assets/mesh_compare.py -- <job.json>

job.json: {"assets": [{"id", "label"}], "nominal_spec", "reference_stl" (fine CAD tessellation, mm), "out_json",
           "points_out", "render_dir" (or null), "n_samples", "seed"}
For every asset it reads the COMMITTED files (assets/library/<id>/<id>_visual.usd and <id>.usd) through pxr and
measures, in the asset frame (metres, bottom centre, Z axis):
  mesh       vertices / faces / triangles, area, closed-mesh volume, boundary and non-manifold edges
  features   length; max OD (hex corners); section diameters (outer samples); hex across flats (max projection on the six
             flat normals) and corner diameter; hex corner-chamfer length; bore diameters (inner samples); planar
             axial faces (exact z of step / end / groove planes); chamfers at both ends (radius at the face and length)
  deviation  sampled two-sided surface distances to the CAD surface (fine tessellation of the STEP; its own chord
             error is <= 1 um): mesh -> CAD and CAD -> mesh, max / mean / p95 / p99, also outside the thread zone
  colliders  count, types, smallest distance from the axis (open / blocked bore), collider-vs-mesh zone check
Surface samples: area-weighted random points (seeded) for distances; barycentric grids (every triangle) for the
profile measurements, because CAD tessellations have long triangles with vertices only at the section ends.
Optionally renders the comparison images (Blender EEVEE, identical camera / lights / orientation for all variants).
"""

import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asset_lib as al  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from pxr import Usd, UsdGeom, UsdPhysics  # noqa: E402


# ---------------------------------------------------------------- geometry input
def usd_triangles(path):
    """All Mesh prims of a USD file as world-space triangles (N,3,3) + unique vertex / face counts."""
    st = Usd.Stage.Open(path)
    tris, nv, nf = [], 0, 0
    for p in st.Traverse():
        if not p.IsA(UsdGeom.Mesh):
            continue
        m = UsdGeom.Mesh(p)
        M = np.array(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
        P = np.array(m.GetPointsAttr().Get(), float)
        P = P @ M[:3, :3] + M[3, :3]
        cnt, idx = m.GetFaceVertexCountsAttr().Get(), m.GetFaceVertexIndicesAttr().Get()
        k = 0
        for c in cnt:
            f = idx[k:k + c]
            tris += [(P[f[0]], P[f[i]], P[f[i + 1]]) for i in range(1, c - 1)]
            k += c
        nv += len(P)
        nf += len(cnt)
    T = np.array(tris, float)
    return T, nv, nf


def read_stl(path, scale):
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack("<I", data[80:84])[0]
    rec = np.frombuffer(data[84:84 + 50 * n], dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    return rec["v"].astype(float) * scale


def mesh_stats(T):
    a = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    area = 0.5 * np.linalg.norm(a, axis=1).sum()
    vol = np.einsum("ij,ij->i", T[:, 0], np.cross(T[:, 1], T[:, 2])).sum() / 6.0
    keys = np.round(T.reshape(-1, 3) * 1e7).astype(np.int64)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    tri = inv.reshape(-1, 3)
    e = np.sort(np.vstack([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return {"triangles": len(T), "area_m2": float(area), "volume_m3": float(vol), "welded_vertices": int(inv.max() + 1),
            "boundary_edges": int((cnt == 1).sum()), "non_manifold_edges": int((cnt > 2).sum())}


def grid_samples(T, k=10):
    """Barycentric grid on every triangle + per-sample triangle normal (unit)."""
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-30)[:, None]
    b = np.array([(i / k, j / k) for i in range(k + 1) for j in range(k + 1 - i)])
    S = T[:, None, 0] + b[None, :, 0, None] * (T[:, None, 1] - T[:, None, 0]) + b[None, :, 1, None] * (T[:, None, 2] - T[:, None, 0])
    return S.reshape(-1, 3), np.repeat(n, len(b), axis=0)


def random_samples(T, n, rng):
    a = 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
    i = rng.choice(len(T), size=n, p=a / a.sum())
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    t = T[i]
    return t[:, 0] + u[:, None] * (t[:, 1] - t[:, 0]) + v[:, None] * (t[:, 2] - t[:, 0])


def bvh(T):
    verts = [Vector(p) for p in T.reshape(-1, 3)]
    return BVHTree.FromPolygons(verts, [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(T))], epsilon=0.0)


def distances(tree, P):
    return np.array([tree.find_nearest(Vector(p))[3] for p in P], float)


def dist_stats(d, z, thread_z):
    out = {}
    for name, m in (("all", np.ones(len(d), bool)), ("outside_thread_zone", z > thread_z)):
        x = d[m]
        out[name] = {"n": int(m.sum()), "max_mm": float(x.max() * 1e3), "mean_mm": float(x.mean() * 1e3),
                     "p95_mm": float(np.percentile(x, 95) * 1e3), "p99_mm": float(np.percentile(x, 99) * 1e3)}
    return out


# ---------------------------------------------------------------- features
def cone_fit(S, r, z, mask, z0, z1):
    """Diameters at the ends of a tapered section from a straight-line fit of the upper / lower radius envelope
    (band edges are not sampled exactly on long triangles, so a band maximum is not an end diameter)."""
    zz, rr = z[mask], r[mask]
    if len(zz) < 10:
        return None
    bins = np.round(zz * 1e4)
    ub = np.unique(bins)
    env = np.array([[zz[bins == b].mean(), rr[bins == b].max()] for b in ub])
    k, c = np.polyfit(env[:, 0], env[:, 1], 1)
    return [float(2 * (c + k * z0) * 1e3), float(2 * (c + k * z1) * 1e3)]


def features(T, g):
    S, N = grid_samples(T, k=16)
    r = np.hypot(S[:, 0], S[:, 1])
    z = S[:, 2]
    radial = (N[:, 0] * S[:, 0] + N[:, 1] * S[:, 1]) / np.maximum(r, 1e-12)
    outer, inner, axial = radial > 0.5, radial < -0.5, np.abs(N[:, 2]) > 0.999
    V = T.reshape(-1, 3)
    mm = 1e3
    out = {"length_mm": float((V[:, 2].max() - V[:, 2].min()) * mm), "bottom_z_mm": float(V[:, 2].min() * mm),
           "max_od_mm": float(2 * np.hypot(V[:, 0], V[:, 1]).max() * mm), "sections": [], "bore": []}

    def band(mask, z0, z1):
        return mask & (z > z0) & (z < z1)

    for s in al.fitting_sections(g, "outer"):
        z0, z1 = s["z0"], s["z1"]
        e = min(0.6e-3, (z1 - z0) / 4) + max(s.get("chamfer_start", 0), s.get("chamfer_end", 0))
        m = band(outer, z0 + e, z1 - e)
        for gr in s.get("grooves", []):
            zc = z0 + gr["at"]
            m &= np.abs(z - zc) > gr["width"] / 2 + 0.3e-3
        rec = {"type": s["type"], "z_mm": [z0 * mm, z1 * mm]}
        if s["type"] == "hex":
            dc = (s["across_flats"] / math.sqrt(3) - 0.475 * s["across_flats"]) / math.tan(math.radians(60))
            mh = band(outer, z0 + dc + 0.2e-3, z1 - dc - 0.2e-3)
            proj = [float((S[mh, 0] * math.cos(math.radians(30 + 60 * k)) + S[mh, 1] * math.sin(math.radians(30 + 60 * k))).max())
                    for k in range(6)]
            af = [(proj[k] + proj[k + 3]) * mm for k in range(3)]
            rc = r[band(outer, z0, z1)].max()
            near = band(outer, z0, z0 + 3e-3) & (r > rc - 0.01e-3)
            rec.update(nominal_across_flats_mm=s["across_flats"] * mm, across_flats_mm=af, corner_diameter_mm=float(2 * rc * mm),
                       nominal_corner_diameter_mm=s["across_flats"] / math.sqrt(3) * 2 * mm,
                       corner_chamfer_length_mm=float((z[near].min() - z0) * mm) if near.any() else None,
                       nominal_corner_chamfer_length_mm=dc * mm,
                       end_face_radius_mm=float(r[band(outer | axial, z0 - 1e-6, z0 + 0.03e-3)].max() * mm) if s.get("chamfer", True) else None,
                       nominal_end_face_radius_mm=0.475 * s["across_flats"] * mm)
        else:
            nom = (s["major_diameter"] if s["type"] == "thread" else s.get("diameter", None))
            if s["type"] == "cone":
                rec["fitted_end_diameters_mm"] = cone_fit(S, r, z, m, z0, z1)
            elif m.any():
                rec.update(outer_diameter_max_mm=float(2 * r[m].max() * mm), outer_diameter_min_mm=float(2 * r[m].min() * mm))
            rec["nominal_diameter_mm"] = nom * mm if nom else [s["d0"] * mm, s["d1"] * mm]
            if s["type"] == "thread":
                rec["thread_depth_visible_mm"] = float((r[m].max() - r[m].min()) * mm) if m.any() else None
            for gr in s.get("grooves", []):
                zc = z0 + gr["at"]
                mg = band(outer, zc - gr["width"] / 2 + 0.05e-3, zc + gr["width"] / 2 - 0.05e-3)
                rec.setdefault("grooves", []).append({"z_mm": zc * mm, "nominal_depth_mm": gr["depth"] * mm,
                                                      "depth_mm": float((s["diameter"] / 2 - r[mg].min()) * mm) if mg.any() else None})
        out["sections"].append(rec)
    for s in al.fitting_sections(g, "bore"):
        z0, z1 = s["z0"], s["z1"]
        e = min(1e-3, (z1 - z0) / 4) + max(s.get("chamfer_start", 0), s.get("chamfer_end", 0))
        m = band(inner, z0 + e, z1 - e)
        nom = s.get("diameter") or s.get("minor_diameter")
        rec = {"type": s["type"], "z_mm": [z0 * mm, z1 * mm], "nominal_diameter_mm": nom * mm if nom else [s["d0"] * mm, s["d1"] * mm]}
        if s["type"] == "cone":
            rr = -r  # lower envelope of the bore = upper envelope of -r
            f = cone_fit(S, rr, z, m, z0, z1)
            rec["fitted_end_diameters_mm"] = [-x for x in f] if f else None
        elif m.any():
            rec.update(diameter_min_mm=float(2 * r[m].min() * mm), diameter_max_mm=float(2 * r[m].max() * mm))
        out["bore"].append(rec)
    # planar axial faces: exact z of the end / step / groove planes (area per plane)
    za = np.round(z[axial] * 1e5) / 1e5
    planes = {}
    for zz in za:
        planes[zz] = planes.get(zz, 0) + 1
    out["axial_planes_mm"] = sorted(float(k * mm) for k, c in planes.items() if c > 20)
    # chamfers at the part ends (outer and bore), from the profile at the end faces
    L = V[:, 2].max()
    for name, zface, sgn in (("bottom", 0.0, 1), ("top", L, -1)):
        sec_o = al.fitting_sections(g, "outer")[0 if sgn > 0 else -1]
        sec_b = al.fitting_sections(g, "bore")[0 if sgn > 0 else -1]
        ro = (sec_o.get("major_diameter") or sec_o.get("diameter") or (sec_o["d0"] if sgn > 0 else sec_o["d1"])) / 2
        rb = (sec_b.get("diameter") or sec_b.get("minor_diameter") or (sec_b["d0"] if sgn > 0 else sec_b["d1"])) / 2
        mo = band(outer, -1, 9) & (np.abs(z - zface) < 3e-3)
        mi = band(inner, -1, 9) & (np.abs(z - zface) < 3e-3)
        face_o = mo & (np.abs(z - zface) < 0.02e-3)
        face_i = mi & (np.abs(z - zface) < 0.02e-3)
        full_o = mo & (r > ro - 0.01e-3)
        full_i = mi & (r < rb + 0.01e-3)
        out[f"{name}_chamfers"] = {
            "outer_radius_at_face_mm": float(r[face_o].max() * mm) if face_o.any() else None, "outer_nominal_radius_mm": ro * mm,
            "outer_chamfer_length_mm": float(abs(z[full_o] - zface).min() * mm) if full_o.any() else None,
            "outer_nominal_chamfer_mm": (sec_o.get("chamfer_start", 0) if sgn > 0 else sec_o.get("chamfer_end", 0)) * mm,
            "bore_radius_at_face_mm": float(r[face_i].max() * mm) if face_i.any() else None, "bore_nominal_radius_mm": rb * mm,
            "bore_chamfer_length_mm": float(abs(z[full_i] - zface).min() * mm) if full_i.any() else None,
            "bore_nominal_chamfer_mm": (sec_b.get("chamfer_start", 0) if sgn > 0 else sec_b.get("chamfer_end", 0)) * mm}
    return out


# ---------------------------------------------------------------- colliders
def colliders(usd_path, narrowest_bore):
    st = Usd.Stage.Open(usd_path)
    root = st.GetDefaultPrim()
    inv = np.linalg.inv(np.array(UsdGeom.Xformable(root).ComputeLocalToWorldTransform(0)))
    pieces = []
    for p in Usd.PrimRange(root):
        if not p.HasAPI(UsdPhysics.CollisionAPI):
            continue
        M = np.array(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(0)) @ inv
        if p.IsA(UsdGeom.Cube):
            h = UsdGeom.Cube(p).GetSizeAttr().Get() / 2
            L = np.array([[x, y, zz] for x in (-h, h) for y in (-h, h) for zz in (-h, h)])
            kind = "box"
        else:
            L = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), float)
            api = p.GetAttribute("physics:approximation").Get()
            kind = f"mesh({api})"
        W = np.hstack([L, np.ones((len(L), 1))]) @ M
        pieces.append((kind, W[:, :3]))

    def axis_dist(P):
        xy = P[:, :2]
        # convex hull of the projection (monotone chain) -> distance from the origin
        pts = sorted(set(map(tuple, np.round(xy, 12))))
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lo, hi = [], []
        for q in pts:
            while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
                lo.pop()
            lo.append(q)
        for q in reversed(pts):
            while len(hi) >= 2 and cross(hi[-2], hi[-1], q) <= 0:
                hi.pop()
            hi.append(q)
        hull = np.array(lo[:-1] + hi[:-1])
        n = len(hull)
        if all(cross(hull[i], hull[(i + 1) % n], (0.0, 0.0)) >= -1e-15 for i in range(n)):
            return 0.0
        d = []
        for i in range(n):
            a, b = hull[i], hull[(i + 1) % n]
            t = np.clip(np.dot(-a, b - a) / max(np.dot(b - a, b - a), 1e-30), 0, 1)
            d.append(np.linalg.norm(a + t * (b - a)))
        return float(min(d))

    dmin = min(axis_dist(P) for _, P in pieces)
    kinds = {}
    for k, _ in pieces:
        kinds[k] = kinds.get(k, 0) + 1
    return {"count": len(pieces), "kinds": kinds, "min_distance_from_axis_mm": dmin * 1e3,
            "narrowest_bore_radius_mm": narrowest_bore * 1e3, "bore_open": dmin >= narrowest_bore - 1e-6,
            "hull_points": int(sum(len(P) for k, P in pieces if k.startswith("mesh(convexHull)") and len(pieces) == 1))}


# ---------------------------------------------------------------- renders
def render_all(job, assets, g):
    import bmesh  # noqa: F401
    rd = job["render_dir"]
    os.makedirs(rd, exist_ok=True)
    spacing = 0.04

    def setup(neutral, wire):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        objs = []
        for i, a in enumerate(assets):
            before = set(bpy.data.objects)
            bpy.ops.wm.usd_import(filepath=al.abspath(al.asset_paths(a["id"])["visual"]))
            new = [o for o in bpy.data.objects if o not in before]
            for o in new:
                if o.parent is None:
                    o.location.x += (i - (len(assets) - 1) / 2) * spacing
            meshes = [o for o in new if o.type == "MESH"]
            objs.append(meshes)
            if neutral:
                m = bpy.data.materials.new(f"neutral{i}")
                m.use_nodes = True
                bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                bsdf.inputs["Base Color"].default_value = (0.42, 0.42, 0.43, 1)
                bsdf.inputs["Roughness"].default_value = 0.55
                bsdf.inputs["Metallic"].default_value = 0.0
                for o in meshes:
                    o.data.materials.clear()
                    o.data.materials.append(m)
            if wire:
                wm = bpy.data.materials.new(f"wire{i}")
                wm.use_nodes = True
                wb = next(n for n in wm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                wb.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
                for o in meshes:
                    w = o.copy()
                    w.data = o.data.copy()
                    sc.collection.objects.link(w)
                    w.data.materials.clear()
                    w.data.materials.append(wm)
                    mod = w.modifiers.new("wire", "WIREFRAME")
                    mod.thickness = 0.00004
                    mod.use_replace = True
            # label
            cu = bpy.data.curves.new(f"lab{i}", "FONT")
            cu.body = a["label"]
            cu.size = 0.0042
            cu.align_x = "CENTER"
            t = bpy.data.objects.new(f"lab{i}", cu)
            sc.collection.objects.link(t)
            t.location = ((i - (len(assets) - 1) / 2) * spacing, 0.0, 0.0495)  # standing just above each part
            t.rotation_euler = (math.pi / 2, 0, 0)
            lm = bpy.data.materials.new(f"labm{i}")
            lm.use_nodes = True
            lb = next(n for n in lm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            lb.inputs["Base Color"].default_value = (0.03, 0.03, 0.03, 1)
            lb.inputs["Roughness"].default_value = 0.9
            cu.materials.append(lm)
        # ground + lights + world
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 0))
        gm = bpy.data.materials.new("ground")
        gm.use_nodes = True
        next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (0.75, 0.75, 0.75, 1)
        bpy.context.active_object.data.materials.append(gm)
        for k, (loc, e) in enumerate([((0.3, -0.4, 0.5), 14), ((-0.4, -0.2, 0.3), 5), ((0.0, 0.4, 0.4), 4)]):
            L = bpy.data.objects.new(f"L{k}", bpy.data.lights.new(f"L{k}", "AREA"))
            L.data.energy, L.data.size = e, 0.4
            L.location = loc
            L.rotation_euler = (Vector((0, 0, 0.02)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
            sc.collection.objects.link(L)
        w = bpy.data.worlds.new("w")
        sc.world = w
        w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.82, 0.85, 1)
        w.node_tree.nodes["Background"].inputs[1].default_value = 0.25
        sc.render.engine = "BLENDER_EEVEE"
        return sc

    def shot(sc, name, loc, target, lens=None, ortho=None, res=(1600, 700)):
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        if ortho:
            cam.data.type, cam.data.ortho_scale = "ORTHO", ortho
        else:
            cam.data.lens = lens
        cam.data.clip_start = 0.001
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.filepath = os.path.join(rd, name)
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(cam, do_unlink=True)

    hex_s = next(s for s in al.fitting_sections(g, "outer") if s["type"] == "hex")
    zh = (hex_s["z0"] + hex_s["z1"]) / 2
    sc = setup(neutral=False, wire=False)
    shot(sc, "01_overall_brass.png", (0.0, -0.34, 0.13), (0, 0, 0.026), lens=75)
    sc = setup(neutral=True, wire=False)
    shot(sc, "02_neutral_geometry_front.png", (0.0, -0.5, 0.027), (0, 0, 0.027), ortho=0.185)
    shot(sc, "03_hex_closeup.png", (0.0, -0.9, 0.30), (0, 0, zh), lens=200, res=(1600, 520))
    shot(sc, "04_bore_and_top_chamfer.png", (0.0, -0.15, 0.85), (0, 0, 0.045), lens=200, res=(1600, 520))
    shot(sc, "05_thread_end_and_bottom_chamfer.png", (0.0, -0.9, 0.09), (0, 0, 0.0065), lens=200, res=(1600, 520))
    sc = setup(neutral=True, wire=True)
    shot(sc, "06_wireframe_tessellation.png", (0.0, -0.5, 0.027), (0, 0, 0.027), ortho=0.185)
    shot(sc, "07_wireframe_hex_closeup.png", (0.0, -0.9, 0.30), (0, 0, zh), lens=200, res=(1600, 520))
    return sorted(f for f in os.listdir(rd) if f.endswith(".png"))


def main():
    job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
    nominal = al.load_json(job["nominal_spec"])
    g = nominal["geometry"]
    thread = al.fitting_sections(g, "outer")[0]
    thread_z = thread["z1"] + al.fitting_sections(g, "outer")[1]["length"]  # beyond thread + relief
    narrowest = min(al.section_radius_range(b, True)[0] for b in al.fitting_sections(g, "bore"))
    rng = np.random.default_rng(job.get("seed", 0))
    ref = read_stl(job["reference_stl"], 1e-3)
    ref_tree = bvh(ref)
    ref_pts = random_samples(ref, job["n_samples"], rng)
    res = {"reference": {"triangles": len(ref), **mesh_stats(ref)}, "assets": {}, "sampling": {
        "n_samples": job["n_samples"], "seed": job.get("seed", 0), "thread_zone_upper_z_mm": thread_z * 1e3,
        "note": "area-weighted random surface samples; distances to the nearest point of the other surface (BVH). "
                "Sampled, so the maxima are lower bounds of the true Hausdorff distances."}}
    points_out = {}
    for a in job["assets"]:
        aid = a["id"]
        p = al.asset_paths(aid)
        T, nv, nf = usd_triangles(al.abspath(p["visual"]))
        st = mesh_stats(T)
        P = random_samples(T, job["n_samples"], rng)
        tree = bvh(T)
        d_m2c = distances(ref_tree, P)
        d_c2m = distances(tree, ref_pts)
        info = al.asset_info(aid)
        sel = np.random.default_rng(1).choice(len(P), 300, replace=False)
        points_out[aid] = P[sel].tolist()
        res["assets"][aid] = {
            "label": a["label"], "backend": (info.get("geometry_backend") or {}).get("backend", "blender"),
            "files_sha256": info["file_sha256"], "usd_vertices": nv, "usd_faces": nf, **st,
            "features": features(T, g),
            "deviation": {"mesh_to_cad": dist_stats(d_m2c, P[:, 2], thread_z), "cad_to_mesh": dist_stats(d_c2m, ref_pts[:, 2], thread_z),
                          "exact_check_points_proxy_mm": (d_m2c[sel] * 1e3).tolist()},
            "colliders": colliders(al.abspath(p["usd"]), narrowest),
            "mass_properties": info.get("mass_properties"), "collision": info["spec"]["collision"],
            "generation_checks": {k: v["passed"] for k, v in info["checks"].items()}}
        print(f"[compare] {aid}: {st['triangles']} tris, deviation mesh->CAD max {res['assets'][aid]['deviation']['mesh_to_cad']['all']['max_mm']:.4f} mm", flush=True)
    json.dump(points_out, open(job["points_out"], "w"))
    if job.get("render_dir"):
        res["renders"] = render_all(job, job["assets"], g)
    json.dump(res, open(job["out_json"], "w"), indent=1, default=float)
    print("[compare] done", flush=True)


main()
