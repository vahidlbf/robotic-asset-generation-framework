"""Generate ONE library asset from its specification, headless in Blender. Other assets are never touched.

    blender -b --factory-startup --python-exit-code 1 --python scripts/assets/generate_asset.py -- \
        --spec config/assets/test_spacer.json [--force]

Writes into assets/library/<asset_id>/ (built in a temporary directory, then moved into place):
    <asset_id>_visual.usd   render mesh + UsdPreviewSurface material (Blender USD export, no physics)
    <asset_id>.usd          the reusable asset: references the visual file, adds guide-purpose colliders, a
                            UsdPhysics material and (dynamic bodies) RigidBodyAPI + MassAPI
    asset_info.json         spec copy + hash, file hashes, measured bounds, mesh/mass checks
and rebuilds assets/library/registry.json. Skips the build when the asset is already current (same spec hash and
unmodified files) unless --force is given. Geometry, collider and USD helpers are reused from
scripts/workstation/generate_assets.py (lathe, mesh_object, box_object, material, mass_properties, export_visual,
write_asset), so library assets follow exactly the same conventions as the workstation assets.
"""

import argparse
import datetime as dt
import math
import os
import shutil
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "workstation"))
import asset_lib as al  # noqa: E402
import generate_assets as ga  # noqa: E402  (guarded: importing does not rebuild the workstation)

import bmesh  # noqa: E402
import bpy  # noqa: E402


def build_geometry(spec, mat, vm):
    """Visual Blender objects for the spec's geometry method (origin bottom centre, Z up)."""
    g, name = spec["geometry"], al.camel(spec["asset_id"])
    if g["method"] == "box":
        sx, sy, sz = g["size"]
        return [ga.box_object(name, (sx, sy, sz), (0, 0, sz / 2), mat, g.get("bevel", 0.0))]
    if g["method"] == "open_container":
        return [container_object(name, g, mat)]
    if g["method"] == "fitting":
        ob = raw_mesh_object(name, *fitting_mesh(g), mat)
        sharpen(ob, 30.0)
        return [ob]
    if g["method"] == "label_plate":
        return label_objects(name, g, mat, ga.material(f"{name}Text", g.get("text_color", [0.02, 0.02, 0.02]), 0.6))
    n = g.get("segments", 48)
    if g["method"] == "cylinder":
        r, h = g["diameter"] / 2, g["height"]
        v, f = ga.lathe([(0, 0), (r, 0), (r, h), (0, h)], n)
    else:  # tube: closed (r, z) loop outer wall -> top annulus -> bore -> bottom annulus; remove_doubles closes it
        ro, ri, h = g["outer_diameter"] / 2, g["inner_diameter"] / 2, g["height"]
        v, f = ga.lathe([(ro, 0), (ro, h), (ri, h), (ri, 0), (ro, 0)], n)
    ob = ga.mesh_object(name, v, f, mat, smooth_angle=30.0)
    sharpen(ob, 30.0)
    return [ob]


def raw_mesh_object(name, verts, faces, mat):
    """Like generate_assets.mesh_object but without remove_doubles: ring meshes may have coincident-radius vertices
    on purpose (steps), and merging them would break the topology."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = True
    return ob


def ring_faces(a, b, n):
    return [(a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]) for k in range(n)]


# ---------------- fitting: rings of N radii at fixed angles (hex flats, helical thread, chamfers, grooves) -------------

def _thread_f(phase):
    """Thread profile 0 (crest) .. 1 (root) over one pitch; flat crest/root, straight flanks."""
    s = 2 * abs(phase - 0.5)
    return min(1.0, max(0.0, (s - 0.15) / 0.7))


def section_rings(s, th, bore):
    """(z, radii) stations of one section. The chamfers / grooves move the surface into the material."""
    z0, z1, t = s["z0"], s["z1"], s["type"]
    c0, c1 = s.get("chamfer_start", 0.0), s.get("chamfer_end", 0.0)
    sg = 1.0 if bore else -1.0
    if t == "hex":
        af = s["across_flats"]
        hexr = [af / 2 / math.cos((a % (math.pi / 3)) - math.pi / 6) for a in th]
        if not s.get("chamfer", True):
            return [(z0, hexr), (z1, hexr)]
        dc = (af / math.sqrt(3) - 0.475 * af) / math.tan(math.radians(60))
        zs = sorted({z0 + f * dc for f in (0, 0.2, 0.45, 0.7, 1.0)} | {z1 - f * dc for f in (0, 0.2, 0.45, 0.7, 1.0)})
        return [(z, [min(h, 0.475 * af + min(z - z0, z1 - z) * math.tan(math.radians(60))) for h in hexr]) for z in zs]
    if t == "thread":
        base = s["minor_diameter"] / 2 if bore else s["major_diameter"] / 2
        p, h = s["pitch"], s["depth"]
        n = max(2, int(round(s["length"] / (p / 8))))
        out = []
        for i in range(n + 1):
            z = z0 + s["length"] * i / n
            rr = []
            for a in th:
                f = _thread_f(((z - z0) / p - a / (2 * math.pi)) % 1.0)
                r = base + h * f if bore else base - h * f
                if c0:
                    r = max(r, base + h + c0 - (z - z0)) if bore else min(r, base - c0 + (z - z0))
                if c1:
                    r = max(r, base + h + c1 - (z1 - z)) if bore else min(r, base - c1 + (z1 - z))
                rr.append(r)
            out.append((z, rr))
        return out
    r0, r1 = (s["diameter"] / 2,) * 2 if t == "cylinder" else (s["d0"] / 2, s["d1"] / 2)
    rad = lambda z: r0 + (r1 - r0) * (z - z0) / s["length"]
    st = []
    if c0:
        st += [(z0, rad(z0) + sg * c0), (z0 + c0, rad(z0 + c0))]
    else:
        st.append((z0, rad(z0)))
    for gr in sorted(s.get("grooves", []), key=lambda x: x["at"]):
        za, zb = z0 + gr["at"] - gr["width"] / 2, z0 + gr["at"] + gr["width"] / 2
        st += [(za, rad(za)), (za, rad(za) + sg * gr["depth"]), (zb, rad(zb) + sg * gr["depth"]), (zb, rad(zb))]
    if c1:
        st += [(z1 - c1, rad(z1 - c1)), (z1, rad(z1) + sg * c1)]
    else:
        st.append((z1, rad(z1)))
    return [(z, [r] * len(th)) for z, r in st]


def fitting_rings(g, which):
    n = g.get("segments", 48)
    th = [2 * math.pi * k / n for k in range(n)]
    rings = []
    for s in al.fitting_sections(g, which):
        for z, rr in section_rings(s, th, which == "bore"):
            if rings and abs(rings[-1][0] - z) < 1e-12 and max(abs(a - b) for a, b in zip(rings[-1][1], rr)) < 1e-12:
                continue  # identical ring (section boundary without a step)
            rings.append((z, rr))
    return th, rings


def fitting_mesh(g):
    th, outer = fitting_rings(g, "outer")
    _, inner = fitting_rings(g, "bore")
    n = len(th)
    verts, O, I = [], [], []
    for rings, idx in ((outer, O), (inner, I)):
        for z, rr in rings:
            idx.append(list(range(len(verts), len(verts) + n)))
            verts += [(r * math.cos(a), r * math.sin(a), z) for r, a in zip(rr, th)]
    faces = []
    for a, b in zip(O[:-1], O[1:]):
        faces += ring_faces(a, b, n)
    faces += ring_faces(O[-1], I[-1], n)
    for a, b in zip(I[:-1], I[1:]):
        faces += ring_faces(b, a, n)
    faces += ring_faces(I[0], O[0], n)
    return verts, faces


def fitting_volume(g):
    """Exact volume of the lofted ring solid (prismatoid rule; ring vertices interpolate linearly)."""
    def area(rr, dth):
        return 0.5 * sum(rr[k] * rr[(k + 1) % len(rr)] for k in range(len(rr))) * math.sin(dth)

    vol = 0.0
    for which, sgn in (("outer", 1.0), ("bore", -1.0)):
        th, rings = fitting_rings(g, which)
        dth = th[1] - th[0]
        for (za, ra), (zb, rb) in zip(rings[:-1], rings[1:]):
            mid = [(x + y) / 2 for x, y in zip(ra, rb)]
            vol += sgn * (zb - za) / 6 * (area(ra, dth) + 4 * area(mid, dth) + area(rb, dth))
    return vol


# ---------------- open container: loft of rounded-rectangle rings (offsets of the envelope) --------------------------

def rr_ring(c, d, m):
    """Rounded rectangle offset d inside the envelope; corner radius shrinks with the offset."""
    hx, hy, rc = c["L"] / 2 - d, c["W"] / 2 - d, max(c["rc"] - d, 0.0015)
    pts = []
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        cx, cy = sx * (hx - rc), sy * (hy - rc)
        pts += [(cx + rc * math.cos(math.radians(a0 + 90 * j / m)), cy + rc * math.sin(math.radians(a0 + 90 * j / m))) for j in range(m + 1)]
    return pts


def container_stations(g):
    c = al.container_dims(g)
    do, di, H, tf, rr = c["d_out"], c["d_in"], c["H"], c["tf"], c["rr"]
    st = [(0.0, do(c["fh"]) + c["fi"]), (c["fh"], do(c["fh"]) + c["fi"]), (c["fh"], do(c["fh"]))] if c["fh"] > 0 else [(0.0, do(0.0))]
    if "band" in g:
        b = g["band"]
        za, zb, e = b["z"] - b["height"] / 2, b["z"] + b["height"] / 2, min(0.0015, b["height"] / 4)
        st += [(za, do(za)), (za + e, do(za + e) - b["depth"]), (zb - e, do(zb - e) - b["depth"]), (zb, do(zb))]
    zr = H - c["rh"]
    st += [(zr, do(zr)), (zr + min(0.003, c["rh"] / 4), 0.0)]
    for j in range(4):  # rounded outer top edge of the rim
        a = math.radians(90 * j / 3)
        st.append((H - rr + rr * math.sin(a), rr - rr * math.cos(a)))
    ri = min(0.0015, c["t"] / 2)
    for j in range(4):  # rounded inner top edge
        a = math.radians(90 * j / 3)
        st.append((H - ri + ri * math.cos(a), di(H) - ri + ri * math.sin(a)))
    f = min(0.004, (H - tf) / 4)
    for j in range(4):  # inner floor fillet
        a = math.radians(90 * j / 3)
        z = tf + f - f * math.sin(a)
        st.append((z, di(z) + f - f * math.cos(a)))
    out = []
    for z, d in st:
        if not out or abs(out[-1][0] - z) > 1e-12 or abs(out[-1][1] - d) > 1e-12:
            out.append((z, d))
    return c, out


def prism(name, quad_lo, z_lo, quad_hi, z_hi, mat):
    v = [(x, y, z_lo) for x, y in quad_lo] + [(x, y, z_hi) for x, y in quad_hi]
    f = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return raw_mesh_object(name, v, f, mat)


def container_object(name, g, mat):
    c, st = container_stations(g)
    m = g.get("corner_segments", 6)
    verts, rings = [], []
    for z, d in st:
        rings.append(list(range(len(verts), len(verts) + 4 * (m + 1))))
        verts += [(x, y, z) for x, y in rr_ring(c, d, m)]
    n = 4 * (m + 1)
    faces = [tuple(reversed(rings[0]))]
    for a, b in zip(rings[:-1], rings[1:]):
        faces += ring_faces(a, b, n)
    faces.append(tuple(rings[-1]))
    shell = raw_mesh_object(name, verts, faces, mat)
    parts = [shell]
    do, L, W, zr = c["d_out"], c["L"], c["W"], c["H"] - c["rh"]
    emb = 0.0008  # ribs / holders reach this far into the wall (closed, overlapping parts)

    def side_rib(tag, axis, sign, u, z_lo, z_hi, width, depth):
        def quad(z):
            n_ = (L if axis == 0 else W) / 2 - do(z)
            q = [(n_ - emb, u - width / 2), (n_ + depth, u - width / 2), (n_ + depth, u + width / 2), (n_ - emb, u + width / 2)]
            return [((sign * a, b) if axis == 0 else (b, sign * a)) for a, b in q]
        return prism(f"{name}_{tag}", quad(z_lo), z_lo, quad(z_hi), z_hi, mat)

    rb = g.get("ribs")
    if rb:
        zlo = c["fh"]
        sl = L / 2 - c["rc"] - 0.01
        xs = [(-sl + 2 * sl * i / (rb["long"] - 1)) if rb["long"] > 1 else 0.0 for i in range(rb["long"])]
        for sign in (1, -1):
            for i, x in enumerate(xs):
                parts.append(side_rib(f"RibY{'P' if sign > 0 else 'N'}{i}", 1, sign, x, zlo, zr, rb["width"], rb["depth"]))
        lh = g.get("label_holder")
        y_min = (lh["width"] / 2 + rb["width"]) if lh else 0.0
        y_max = W / 2 - c["rc"] - rb["width"]
        half = rb["short"] // 2
        ys = [y_min + (j + 0.5) * (y_max - y_min) / half for j in range(half)]
        ys = [s * y for y in ys for s in (1, -1)] + ([0.0] if rb["short"] % 2 and not lh else [])
        for sign in (1, -1):
            for i, y in enumerate(ys):
                parts.append(side_rib(f"RibX{'P' if sign > 0 else 'N'}{i}", 0, sign, y, zlo, zr, rb["width"], rb["depth"]))
        if rb.get("corners"):
            for k, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
                def quad(z, sx=sx, sy=sy):
                    rc = max(c["rc"] - do(z), 0.0015)
                    cx, cy = sx * (L / 2 - do(z) - rc), sy * (W / 2 - do(z) - rc)
                    nx, ny = sx * math.sqrt(0.5), sy * math.sqrt(0.5)
                    tx, ty = -ny, nx
                    w2 = rb["width"] / 2
                    return [(cx + nx * (rc + a) + tx * b, cy + ny * (rc + a) + ty * b)
                            for a, b in ((-emb, -w2), (rb["depth"], -w2), (rb["depth"], w2), (-emb, w2))]
                parts.append(prism(f"{name}_RibCorner{k}", quad(zlo), zlo, quad(zr), zr, mat))
    lh = g.get("label_holder")
    if lh:
        za, zb = lh["z_center"] - lh["height"] / 2, lh["z_center"] + lh["height"] / 2
        xo = L / 2 - do(zb) + lh["depth"]  # vertical front face (mount point label_+x / label_-x)
        for sign in (1, -1):
            q = lambda z: [(sign * (L / 2 - do(z) - emb), -lh["width"] / 2), (sign * xo, -lh["width"] / 2),
                           (sign * xo, lh["width"] / 2), (sign * (L / 2 - do(z) - emb), lh["width"] / 2)]
            parts.append(prism(f"{name}_LabelHolder{'P' if sign > 0 else 'N'}", q(za), za, q(zb), zb, mat))
    ob = join(parts)
    h = g.get("handles")
    if h:  # hand holes through the short walls, just under the rim (Boolean difference, exact solver)
        hz1 = zr - h.get("below_rim", 0.0)
        hz0 = hz1 - h["height"]
        cutters = []
        for sign in (1, -1):
            x = sign * (L / 2 - do((hz0 + hz1) / 2))
            cu = ga.box_object(f"HandleCut{sign}", (0.06, h["width"], h["height"]), (x, 0, (hz0 + hz1) / 2), None,
                               bevel=min(h["height"] / 2 - 0.001, 0.012))
            cutters.append(cu)
        cut = join(cutters)
        mod = ob.modifiers.new("Handles", "BOOLEAN")
        mod.operation, mod.solver, mod.object = "DIFFERENCE", "EXACT", cut
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cut, do_unlink=True)
    # Hydra/RTX fan-triangulates n-gons, which fills the non-convex wall faces around the hand holes: triangulate here
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(ob.data)
    bm.free()
    sharpen(ob, 30.0)
    return ob


def join(objs):
    for o in bpy.context.scene.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def label_objects(name, g, mat, text_mat):
    w, t, h = g["size"]
    e = g.get("text_relief", 0.0006)
    plate = ga.box_object(name, (w, t - e, h), (0, e / 2, h / 2), mat, g.get("bevel", 0.0))
    txt = ga.text_object(f"{name}Text", g["text"], g.get("text_height", 0.6 * h / max(1, g["text"].count("\n") + 1)),
                         (0, -t / 2 + e / 2, h / 2), (0, -1, 0), text_mat, extrude=e / 2)
    lo, hi = ga.bounds([txt])
    s = min(1.0, 0.88 * w / (hi[0] - lo[0]), 0.85 * h / (hi[2] - lo[2]))
    txt.scale = (s, 1.0, s)
    bpy.context.view_layer.objects.active = txt
    for o in bpy.context.scene.objects:
        o.select_set(o is txt)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    lo, hi = ga.bounds([txt])
    txt.location = (txt.location[0] - (lo[0] + hi[0]) / 2, txt.location[1], txt.location[2] + h / 2 - (lo[2] + hi[2]) / 2)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    return [plate, txt]


def sharpen(ob, angle_deg):
    """Flat planar faces + sharp edges above angle_deg, baked into the mesh (export-safe). mesh_object's
    Smooth-by-Angle modifier is a bundled node-group asset that is unavailable with --factory-startup."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(angle_deg):
            e.smooth = False
    for fc in bm.faces:
        if abs(fc.normal.z) > 0.999:
            fc.smooth = False
    bm.to_mesh(ob.data)
    bm.free()
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)


PRISM_FACES = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def colliders_for(spec, ob):
    g, c = spec["geometry"], spec["collision"]
    sx, sy, sz = al.nominal_size(spec)
    rep = c["representation"]
    if rep == "none":
        return []
    if rep in ("container_walls", "fitting_sections"):  # analytic boxes / convex prisms shared with placement/validation
        out = []
        for p in al.collider_pieces(spec):
            if p["kind"] == "box":
                lo = [min(q[i] for q in p["points"]) for i in range(3)]
                hi = [max(q[i] for q in p["points"]) for i in range(3)]
                out.append({"type": "box", "name": p["name"], "size": [b - a for a, b in zip(lo, hi)],
                            "center": [(a + b) / 2 for a, b in zip(lo, hi)]})
            else:
                out.append({"type": "convex", "name": p["name"], "verts": p["points"], "faces": PRISM_FACES})
        return out
    if rep == "primitive":
        if g["method"] == "box":
            return [{"type": "box", "name": "Box", "size": [sx, sy, sz], "center": [0, 0, sz / 2]}]
        return [{"type": "cylinder", "name": "Body", "radius": sx / 2, "height": sz, "center": [0, 0, sz / 2]}]
    if rep == "convex_hull":
        me = ob.data
        return [{"type": "convex", "name": "Hull", "verts": [tuple(ob.matrix_world @ v.co) for v in me.vertices],
                 "faces": [tuple(p.vertices) for p in me.polygons]}]
    # ring_segments: N boxes forming a regular N-gon inscribed in the outer circle (vertices at angles k*360/N, so the
    # collider bounds equal the outer diameter for N % 4 == 0); inner faces at the bore radius keep the hole open.
    n = c.get("segments", 12)
    ro, ri, h = g["outer_diameter"] / 2, g["inner_diameter"] / 2, g["height"]
    a_out = ro * math.cos(math.pi / n)
    width, depth, rmid = 2 * ro * math.sin(math.pi / n), a_out - ri, (a_out + ri) / 2
    out = []
    for k in range(n):
        a = (k + 0.5) * 360.0 / n
        out.append({"type": "box", "name": f"Ring_{k:02d}", "size": [depth, width, h],
                    "center": [rmid * math.cos(math.radians(a)), rmid * math.sin(math.radians(a)), h / 2],
                    "rotate_xyz_deg": [0.0, 0.0, a]})
    return out


def set_contact_offset(usd_path, offset):
    """PhysxCollisionAPI contactOffset on every collider (Blender's USD has no PhysxSchema: schema token + attribute)."""
    from pxr import Sdf, Usd, UsdPhysics

    st = Usd.Stage.Open(usd_path)
    for p in Usd.PrimRange(st.GetDefaultPrim()):
        if p.HasAPI(UsdPhysics.CollisionAPI):
            p.AddAppliedSchema("PhysxCollisionAPI")
            p.CreateAttribute("physxCollision:contactOffset", Sdf.ValueTypeNames.Float).Set(float(offset))
    st.GetRootLayer().Save()


def mesh_checks(objs, spec):
    non_manifold = boundary = 0
    for ob in objs:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        non_manifold += sum(1 for e in bm.edges if not e.is_manifold)
        boundary += sum(1 for e in bm.edges if e.is_boundary)
        bm.free()
    g = spec["geometry"]
    sx, sy, sz = al.nominal_size(spec)
    if g["method"] == "fitting":
        v = fitting_volume(g)
        return {"non_manifold_edges": non_manifold, "boundary_edges": boundary, "analytic_volume_m3": v, "polygon_volume_m3": v,
                "reference": "prismatoid integral of the ring polygons"}
    if g["method"] in ("open_container", "label_plate"):
        return {"non_manifold_edges": non_manifold, "boundary_edges": boundary, "analytic_volume_m3": None, "polygon_volume_m3": None,
                "reference": "none (static visual mesh of several closed parts; volume not used)"}
    if g["method"] == "box":
        analytic = sx * sy * sz
    elif g["method"] == "cylinder":
        analytic = math.pi * (sx / 2) ** 2 * sz
    else:
        analytic = math.pi / 4 * (g["outer_diameter"] ** 2 - g["inner_diameter"] ** 2) * g["height"]
    n = g.get("segments", 48)
    polygon_factor = 1.0 if g["method"] == "box" else n / (2 * math.pi) * math.sin(2 * math.pi / n)
    return {"non_manifold_edges": non_manifold, "boundary_edges": boundary, "analytic_volume_m3": analytic,
            "polygon_volume_m3": analytic * polygon_factor}


def usd_checks(usd_path, spec, n_colliders):
    """Re-open the written asset with Blender's USD and check what was authored."""
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade, UsdUtils

    st = Usd.Stage.Open(usd_path)
    root = st.GetDefaultPrim()
    cols = [p for p in Usd.PrimRange(root) if p.HasAPI(UsdPhysics.CollisionAPI)]
    guide = all(UsdGeom.Imageable(p).ComputePurpose() == UsdGeom.Tokens.guide for p in cols)
    mats = [UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial("physics")[0] for p in cols]
    bound = all(m and m.GetPrim().IsValid() and m.GetPrim().HasAPI(UsdPhysics.MaterialAPI) for m in mats)
    _, _, unresolved = UsdUtils.ComputeAllDependencies(usd_path)
    vis = [p for p in Usd.PrimRange(root) if p.IsA(UsdGeom.Mesh) and UsdGeom.Imageable(p).ComputePurpose() != UsdGeom.Tokens.guide]
    vp = root.GetChild("Visual")
    lo = vp.GetMetadata("references") if vp and vp.HasMetadata("references") else None
    refs = [str(r.assetPath) for r in lo.prependedItems] if lo else []
    rigid = root.HasAPI(UsdPhysics.RigidBodyAPI)
    mass = UsdPhysics.MassAPI(root).GetMassAttr().Get() if root.HasAPI(UsdPhysics.MassAPI) else None
    dyn = spec["physics"]["body"] == "dynamic"
    out = {"default_prim": str(root.GetPath()), "units_ok": UsdGeom.GetStageMetersPerUnit(st) == 1.0 and UsdGeom.GetStageUpAxis(st) == "Z",
           "colliders": len(cols), "colliders_expected": n_colliders, "colliders_guide_purpose": guide,
           "colliders_physics_material_bound": bound, "unresolved_dependencies": [str(u) for u in unresolved],
           "visual_meshes": len(vis), "visual_references": refs, "rigid_body": rigid, "mass_authored_kg": mass}
    out["passed"] = bool(out["units_ok"] and len(cols) == n_colliders and guide and bound and not unresolved and vis
                         and all(not os.path.isabs(r) for r in refs) and rigid == dyn and (mass is not None) == dyn)
    return out


def generate(spec_rel, force=False):
    spec = al.load_spec(spec_rel)
    aid = spec["asset_id"]
    status, _ = al.asset_status(aid, spec_rel)
    if status == "current" and not force:
        print(f"[asset] {aid}: current (spec and files unchanged) - nothing to do; use --force to rebuild", flush=True)
        al.rebuild_registry()
        return True
    print(f"[asset] {aid}: status={status} -> building", flush=True)
    paths = al.asset_paths(aid)
    final_dir = al.abspath(paths["dir"])
    tmp_dir = final_dir + ".tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir)
    env = al.load_json(al.ENV_CONFIG)
    vm, ph = spec["visual_material"], spec["physics"]

    ga.clear_scene()
    mat = ga.material(f"{al.camel(aid)}Material", vm["color"], vm.get("roughness", 0.5), vm.get("metallic", 0.0), vm.get("opacity", 1.0))
    objs = build_geometry(spec, mat, vm)
    ob = objs[0]
    tris = ga.world_triangles(objs)
    unit = ga.mass_properties(tris, 1.0)
    volume = unit["volume_m3"]
    mesh = {"triangles": len(tris), "vertices": sum(len(o.data.vertices) for o in objs), "objects": len(objs), "volume_m3": volume,
            **mesh_checks(objs, spec)}
    ref = mesh["polygon_volume_m3"]
    mesh["volume_vs_polygon_rel_error"] = abs(volume - ref) / ref if ref else None
    bmin, bmax = ga.bounds(objs)
    nb = al.nominal_bounds(spec)
    tol = spec.get("validation", {}).get("dimension_tolerance_m", al.DEFAULT_TOL)
    size = [bmax[i] - bmin[i] for i in range(3)]
    dims_ok = all(abs(size[i] - (nb[1][i] - nb[0][i])) <= tol for i in range(3)) and abs(bmin[2]) <= 1e-9

    dynamic = None
    if ph["body"] == "dynamic":
        mass = ph["mass_kg"] if "mass_kg" in ph else ph["density_kg_m3"] * volume
        mp = ga.mass_properties(tris, mass)
        dynamic = {"mass": mass, **mp}
        mass_props = {"mass_kg": mass, "mass_source": "mass_kg" if "mass_kg" in ph else "density_kg_m3 x mesh volume", **mp}
    else:
        mass_props = None

    vis = os.path.join(tmp_dir, os.path.basename(paths["visual"]))
    ga.export_visual(objs, vis)
    colliders = colliders_for(spec, ob)
    pm = al.resolve_material(spec, env)
    info_usd = {"frame": "bottom centre", "mounts": {k: [list(v[0]), v[1]] for k, v in al.mount_frames(spec).items()}, "asset_id": aid, "category": spec["category"], "nominal_size_m": al.nominal_size(spec),
                "collision": spec["collision"]["representation"], "spec": os.path.relpath(al.abspath(spec_rel), final_dir)}
    usd = os.path.join(tmp_dir, os.path.basename(paths["usd"]))
    ga.write_asset(usd, al.camel(aid), vis, colliders, pm, dynamic=dynamic, info=info_usd)
    if "contact_offset_m" in spec["collision"]:
        set_contact_offset(usd, spec["collision"]["contact_offset_m"])
    uc = usd_checks(usd, spec, al.expected_colliders(spec))

    closed_required = spec["geometry"]["method"] not in ("label_plate",)
    method = spec["geometry"]["method"]
    vol_err = mesh["volume_vs_polygon_rel_error"]
    vol_tol = 2e-3 if method == "fitting" else 1e-5
    checks = {"dimensions": {"passed": dims_ok, "measured_size_m": size, "nominal_size_m": al.nominal_size(spec), "tolerance_m": tol,
                             "bottom_z_m": bmin[2]},
              "closed_manifold_mesh": {"passed": (mesh["non_manifold_edges"] == 0 and mesh["boundary_edges"] == 0 and volume > 0)
                                       or not closed_required, "non_manifold_edges": mesh["non_manifold_edges"],
                                       "boundary_edges": mesh["boundary_edges"],
                                       "note": "informational for label plates (font outlines; static, no mass)" if not closed_required else ""},
              "mesh_volume_matches_geometry": {"passed": vol_err is None or vol_err < vol_tol or spec["geometry"].get("bevel", 0) > 0,
                                               "relative_error": vol_err, "tolerance": vol_tol, "reference": mesh.get("reference", "analytic solid"),
                                               "note": "closed-mesh volume vs. the exact volume of the tessellated solid (float32 vertices); "
                                                       "fitting: vs. the ring-loft integral (non-planar thread quads are triangulated); "
                                                       "informational for bevelled boxes and static containers/labels"},
              "usd_asset": uc}
    if mass_props:
        com = mass_props["center_of_mass"]
        sym = method != "fitting"
        rng = spec.get("validation", {}).get("density_range_kg_m3")
        checks["mass_properties"] = {"passed": mass_props["mass_kg"] > 0 and min(mass_props["diagonal_inertia"]) > 0
                                     and (abs(com[2] - al.nominal_size(spec)[2] / 2) < 1e-6 if sym else 0 < com[2] < al.nominal_size(spec)[2])
                                     and max(abs(com[0]), abs(com[1])) < (1e-9 if sym else 2e-4)
                                     and mass_props["max_offdiag_ratio"] < 0.01
                                     and (rng is None or rng[0] <= mass_props["density_kg_m3"] <= rng[1]),
                                     "implied_density_kg_m3": mass_props["density_kg_m3"], "density_range_kg_m3": rng,
                                     "note": "symmetric solid: COM on the axis at half height" if sym else
                                             "turned part: COM within 0.2 mm of the axis (helical threads are not exactly symmetric), "
                                             "inside the length; off-diagonal inertia < 1 % (principal axes = asset axes)"}
    ok = all(c["passed"] for c in checks.values())

    # move into place (only this asset's directory is replaced)
    os.makedirs(final_dir, exist_ok=True)
    for fn in os.listdir(tmp_dir):
        os.replace(os.path.join(tmp_dir, fn), os.path.join(final_dir, fn))
    shutil.rmtree(tmp_dir, ignore_errors=True)
    files = [os.path.basename(paths["usd"]), os.path.basename(paths["visual"])]
    info = {"asset_id": aid, "schema_version": 1, "ok": ok, "spec_file": al.relpath(al.abspath(spec_rel)),
            "spec_sha256": al.canonical_sha256(spec), "spec": spec, "resolved_physics_material": pm,
            "generator": "scripts/assets/generate_asset.py", "blender_version": bpy.app.version_string,
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "files": files, "file_sha256": {f: al.sha256_file(f"{paths['dir']}/{f}") for f in files},
            "usd_root_prim": f"/{al.camel(aid)}", "physics_material_prim": "PhysicsMaterial" if pm else None,
            "bounds_visual_m": [bmin, bmax], "nominal_bounds_m": nb, "mesh": mesh, "mass_properties": mass_props,
            "colliders": [c["name"] for c in colliders], "collider_representation": spec["collision"]["representation"],
            "mounts": {k: [list(v[0]), v[1]] for k, v in al.mount_frames(spec).items()},
            "checks": checks}
    al.write_json(paths["info"], info)
    reg = al.rebuild_registry()
    for k, c in checks.items():
        print(f"[asset] check {k}: {'PASS' if c['passed'] else 'FAIL'}", flush=True)
    print(f"[asset] {aid}: {'OK' if ok else 'FAILED'}; size {[round(s, 6) for s in size]} m, "
          f"mass {mass_props['mass_kg'] if mass_props else 'static'} kg, {len(colliders)} collider(s); "
          f"registry has {len(reg['assets'])} asset(s)", flush=True)
    return ok


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    return 0 if generate(a.spec, a.force) else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 2
    sys.exit(code)
