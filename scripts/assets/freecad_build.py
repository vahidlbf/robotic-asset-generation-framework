"""FreeCAD side of the CAD routes: build a parametric solid from an asset spec, or read a STEP file; export STEP + STL.

Runs inside FreeCAD's console interpreter (freecadcmd), launched by generate_asset.py through backends.freecad_command:
    FCB_MODE=build  FCB_SPEC=<abs spec.json> FCB_OUT_DIR=<dir> FCB_RESULT=<result.json> <freecad> [freecadcmd] freecad_build.py
    FCB_MODE=import FCB_SOURCE=<abs model.step> FCB_SPEC=... FCB_OUT_DIR=... FCB_RESULT=...    <freecad> [freecadcmd] freecad_build.py
Inputs come through environment variables (freecadcmd treats extra arguments as files to open); the result JSON's
"ok" field is authoritative (freecadcmd's exit code is not reliable). All FreeCAD lengths are mm.

build: method "fitting" only (backends.FREECAD_METHODS), from the SAME section parameters the Blender builder uses
(asset_lib.fitting_sections), with real CAD operations (see backends.FREECAD_FITTING_FEATURES):
  round sections  Part.makeCylinder / Part.makeCone; chamfers with Shape.makeChamfer on the actual end edge;
                  grooves as a boolean cut of a ring
  hex             extruded hexagon (corners on +-x, as in the Blender builder) intersected with 30 deg chamfer cones
  bore            revolved (r, z) profile with countersink chamfers, removed with a boolean cut
  threads         cosmetic: a plain cylinder at the major (outer) / minor (bore) diameter; the helix is not modelled
Checks: valid single closed solid, bounding box vs. the spec envelope, STEP round trip (volume), watertight
tessellation (MeshPart) with its volume vs. the exact solid volume. Mass properties are for unit density (mm^3,
mm^5, about the centre of mass); generate_asset.py scales them and cross-checks them against the mesh.
"""

import json
import math
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asset_lib as al  # noqa: E402  (stdlib only; same section maths as the Blender builder)

import FreeCAD as App  # noqa: E402
import Mesh  # noqa: E402
import MeshPart  # noqa: E402
import Part  # noqa: E402

V = App.Vector
MM = 1000.0
RESULT = {"ok": False, "checks": {}, "features": []}


def check(name, passed, **detail):
    RESULT["checks"][name] = {"passed": bool(passed), **detail}
    return passed


def end_edge(shape, z, r, tol=1e-6):
    """The circular edge of `shape` at height z with radius r (chamfer target)."""
    for e in shape.Edges:
        c = e.Curve
        if c.__class__.__name__ == "Circle" and abs(c.Center.z - z) < tol and abs(c.Radius - r) < 1e-5:
            return e
    raise RuntimeError(f"no circular edge r={r} at z={z}")


def round_section(s):
    z0, z1 = s["z0"] * MM, s["z1"] * MM
    t = s["type"]
    if t == "cone":
        r0, r1 = s["d0"] / 2 * MM, s["d1"] / 2 * MM
        sol = Part.makeCone(r0, r1, z1 - z0, V(0, 0, z0))
    else:
        r0 = r1 = (s["diameter"] if t == "cylinder" else s["major_diameter"]) / 2 * MM
        sol = Part.makeCylinder(r0, z1 - z0, V(0, 0, z0))
    if t == "thread":
        RESULT["features"].append(f"cosmetic thread {s['major_diameter'] * 1000:.2f} x {s['pitch'] * 1000:.3f} mm at z {z0:.2f}-{z1:.2f} "
                                  f"(plain cylinder at the major diameter)")
    for key, z, r in (("chamfer_start", z0, r0), ("chamfer_end", z1, r1)):
        c = s.get(key, 0.0)
        if c:
            sol = sol.makeChamfer(c * MM, [end_edge(sol, z, r)])
            RESULT["features"].append(f"chamfer {c * 1000:.2f} mm (makeChamfer) on {t} edge at z {z:.2f}")
    for gr in s.get("grooves", []):
        za = z0 + (gr["at"] - gr["width"] / 2) * MM
        w = gr["width"] * MM
        ring = Part.makeCylinder(r0 + 1.0, w, V(0, 0, za)).cut(Part.makeCylinder(r0 - gr["depth"] * MM, w, V(0, 0, za)))
        sol = sol.cut(ring)
        RESULT["features"].append(f"groove {gr['width'] * 1000:.2f} x {gr['depth'] * 1000:.2f} mm (boolean cut) at z {za:.2f}")
    return sol


def hex_section(s):
    z0, z1 = s["z0"] * MM, s["z1"] * MM
    af = s["across_flats"] * MM
    rc = af / math.sqrt(3)
    face = Part.Face(Part.makePolygon([V(rc * math.cos(math.radians(60 * k)), rc * math.sin(math.radians(60 * k)), z0) for k in range(7)]))
    sol = face.extrude(V(0, 0, z1 - z0))
    RESULT["features"].append(f"hex AF {af:.2f} mm (extruded hexagon) at z {z0:.2f}-{z1:.2f}")
    if s.get("chamfer", True):
        L, r0, k = z1 - z0, 0.475 * af, math.tan(math.radians(60))
        sol = sol.common(Part.makeCone(r0, r0 + L * k, L, V(0, 0, z0))).common(Part.makeCone(r0 + L * k, r0, L, V(0, 0, z0)))
        RESULT["features"].append("hex 30 deg corner chamfers at both ends (common with chamfer cones)")
    return sol


def bore_solid(g):
    """Revolved (r, z) profile of the whole bore, extended 1 mm beyond both ends so the cut is clean."""
    secs = al.fitting_sections(g, "bore")
    pts = []
    for i, s in enumerate(secs):
        z0, z1 = s["z0"] * MM, s["z1"] * MM
        t = s["type"]
        if t == "cone":
            r0, r1 = s["d0"] / 2 * MM, s["d1"] / 2 * MM
        else:
            r0 = r1 = (s["diameter"] if t == "cylinder" else s["minor_diameter"]) / 2 * MM
        if t == "thread":
            RESULT["features"].append(f"cosmetic internal thread, bore at the minor diameter {2 * r0:.2f} mm at z {z0:.2f}-{z1:.2f}")
        c0, c1 = s.get("chamfer_start", 0.0) * MM, s.get("chamfer_end", 0.0) * MM
        if i == 0:
            pts.append((r0 + c0, z0 - 1.0))
        pts += [(r0 + c0, z0)] + ([(r0, z0 + c0)] if c0 else [])
        pts += ([(r1, z1 - c1)] if c1 else []) + [(r1 + c1, z1)]
        if i == len(secs) - 1:
            pts.append((r1 + c1, z1 + 1.0))
        if c0 or c1:
            RESULT["features"].append(f"bore countersink chamfers {c0:.2f}/{c1:.2f} mm (revolved profile) at z {z0:.2f}-{z1:.2f}")
    clean = []
    for p in pts:
        if not clean or abs(clean[-1][0] - p[0]) > 1e-9 or abs(clean[-1][1] - p[1]) > 1e-9:
            clean.append(p)
    ring = [V(0, 0, clean[0][1])] + [V(r, 0, z) for r, z in clean] + [V(0, 0, clean[-1][1])]
    ring.append(ring[0])
    RESULT["features"].append("bore: revolved profile (Face.revolve 360 deg), removed with a boolean cut")
    return Part.Face(Part.makePolygon(ring)).revolve(V(0, 0, 0), V(0, 0, 1), 360)


def build_fitting(spec):
    g = spec["geometry"]
    parts = [hex_section(s) if s["type"] == "hex" else round_section(s) for s in al.fitting_sections(g, "outer")]
    outer = parts[0].multiFuse(parts[1:]).removeSplitter() if len(parts) > 1 else parts[0]
    RESULT["features"].append(f"{len(parts)} outer sections fused (multiFuse + removeSplitter)")
    return outer.cut(bore_solid(g)).removeSplitter()


def solid_props(shape):
    s = shape.Solids[0]
    M = s.MatrixOfInertia
    I = [[M.A[4 * i + j] for j in range(3)] for i in range(3)]
    bb = shape.optimalBoundingBox(False, False)
    return {"volume_mm3": shape.Volume, "area_mm2": shape.Area, "center_of_mass_mm": list(s.CenterOfMass),
            "inertia_unit_density_mm5": I, "bbox_mm": [[bb.XMin, bb.YMin, bb.ZMin], [bb.XMax, bb.YMax, bb.ZMax]],
            "faces": len(shape.Faces), "edges": len(shape.Edges), "solids": len(shape.Solids)}


def export(shape, out_dir, stem, cad):
    step = os.path.join(out_dir, stem + ".step")
    shape.exportStep(step)
    rt = Part.Shape()
    rt.read(step)
    check("step_roundtrip", rt.isValid() and len(rt.Solids) == 1 and abs(rt.Volume - shape.Volume) <= 1e-6 * shape.Volume,
          volume_mm3=rt.Volume, solids=len(rt.Solids))
    lin = cad.get("linear_deflection_mm", 0.01)
    ang = math.radians(cad.get("angular_deflection_deg", 5.0))
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=lin, AngularDeflection=ang, Relative=False)
    stl = os.path.join(out_dir, stem + ".stl")
    mesh.write(stl)
    m = Mesh.Mesh(stl)
    rel = abs(m.Volume - shape.Volume) / shape.Volume
    check("tessellation_watertight", m.isSolid() and not m.hasNonManifolds() and m.CountFacets > 0,
          facets=m.CountFacets, points=m.CountPoints)
    check("tessellation_volume", rel < 5e-3, mesh_volume_mm3=m.Volume, cad_volume_mm3=shape.Volume, relative_error=rel,
          linear_deflection_mm=lin, angular_deflection_deg=math.degrees(ang))
    RESULT.update(step=os.path.basename(step), stl=os.path.basename(stl), mesh={"facets": m.CountFacets, "points": m.CountPoints})


def main():
    mode = os.environ["FCB_MODE"]
    with open(os.environ["FCB_SPEC"]) as f:
        spec = json.load(f)
    out_dir = os.environ["FCB_OUT_DIR"]
    RESULT.update(mode=mode, freecad_version=".".join(App.Version()[:3]), freecad_build=App.Version()[3] if len(App.Version()) > 3 else "",
                  python=sys.version.split()[0], units="mm", asset_id=spec["asset_id"])
    g = spec["geometry"]
    cad = g.get("cad", {})
    if mode == "build":
        if g["method"] != "fitting":
            raise ValueError(f"no FreeCAD builder for method '{g['method']}'")
        shape = build_fitting(spec)
        nb = al.nominal_bounds(spec)
        bb = shape.optimalBoundingBox(False, False)  # Shape.BoundBox is loose on cones / circles
        meas = [[bb.XMin, bb.YMin, bb.ZMin], [bb.XMax, bb.YMax, bb.ZMax]]
        err = max(abs(meas[i][k] - nb[i][k] * MM) for i in range(2) for k in range(3))
        tol = spec.get("validation", {}).get("dimension_tolerance_m", al.DEFAULT_TOL) * MM
        check("bounding_box_vs_spec", err <= tol, measured_mm=meas, nominal_mm=[[x * MM for x in r] for r in nb], max_error_mm=err, tolerance_mm=tol)
    else:
        shape = Part.Shape()
        shape.read(os.environ["FCB_SOURCE"])
        RESULT["features"].append(f"read {os.path.basename(os.environ['FCB_SOURCE'])} (Part.Shape.read)")
    check("valid_closed_solid", shape.isValid() and len(shape.Solids) == 1 and shape.Solids[0].isClosed() and shape.Volume > 0,
          valid=shape.isValid(), solids=len(shape.Solids), shape_type=shape.ShapeType)
    if len(shape.Solids) == 1:
        shape = shape.Solids[0]
    RESULT["solid"] = solid_props(shape)
    export(shape, out_dir, spec["asset_id"], cad)
    RESULT["ok"] = all(c["passed"] for c in RESULT["checks"].values())


try:
    main()
except Exception:
    RESULT["error"] = traceback.format_exc()
with open(os.environ["FCB_RESULT"], "w") as f:
    json.dump(RESULT, f, indent=1)
