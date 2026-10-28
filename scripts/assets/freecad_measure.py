"""FreeCAD side of the backend comparison (scripts/assets/compare_backends.py): exact B-rep measurements of a STEP solid.

    FCM_MODE=reference FCM_STEP=<abs .step> FCM_OUT=<dir> FCM_RESULT=<json> <freecad> [freecadcmd] freecad_measure.py
    FCM_MODE=distances FCM_STEP=<abs .step> FCM_POINTS=<json: {name: [[x,y,z] m ...]}> FCM_RESULT=<json> ...

reference: exact volume / area / COM / inertia, the B-rep faces (type, radius, z range; planar face normals and
           distances, which give the hex across-flats exactly) and a very fine reference tessellation (STL, chord error
           1 micrometre) that stands in for the exact CAD surface in the sampled distance computation.
distances: exact point-to-solid-surface distances (Shape.distToShape) for given points, used to quantify the error of
           that tessellated reference.
Lengths in the result are millimetres (FreeCAD units). Read-only: nothing in the project is written.
"""

import json
import math
import os
import traceback

import FreeCAD as App  # noqa: F401
import MeshPart
import Part

RESULT = {"ok": False}


def faces_summary(shape):
    out = []
    for f in shape.Faces:
        s = f.Surface
        bb = f.BoundBox
        rec = {"type": s.__class__.__name__, "area_mm2": f.Area, "z_mm": [bb.ZMin, bb.ZMax]}
        if hasattr(s, "Radius"):
            rec["radius_mm"] = s.Radius
        if rec["type"] == "Plane":
            n = f.normalAt(*f.Surface.parameter(f.CenterOfMass))
            rec["normal"] = [n.x, n.y, n.z]
            rec["distance_from_axis_mm"] = abs(n.x * f.CenterOfMass.x + n.y * f.CenterOfMass.y) if abs(n.z) < 1e-9 else None
        if rec["type"] == "Cone":
            rec["semi_angle_deg"] = math.degrees(s.SemiAngle)
        out.append(rec)
    return out


def main():
    shape = Part.Shape()
    shape.read(os.environ["FCM_STEP"])
    solid = shape.Solids[0]
    mode = os.environ["FCM_MODE"]
    if mode == "reference":
        out = os.environ["FCM_OUT"]
        mesh = MeshPart.meshFromShape(Shape=solid, LinearDeflection=0.001, AngularDeflection=math.radians(1.0), Relative=False)
        stl = os.path.join(out, "cad_reference_fine.stl")
        mesh.write(stl)
        M = solid.MatrixOfInertia
        bb = solid.optimalBoundingBox(False, False)
        RESULT.update(volume_mm3=solid.Volume, area_mm2=solid.Area, center_of_mass_mm=list(solid.CenterOfMass),
                      inertia_unit_density_mm5=[[M.A[4 * i + j] for j in range(3)] for i in range(3)],
                      bbox_mm=[[bb.XMin, bb.YMin, bb.ZMin], [bb.XMax, bb.YMax, bb.ZMax]], valid=solid.isValid(),
                      closed=solid.isClosed(), faces=faces_summary(solid), n_faces=len(solid.Faces), n_edges=len(solid.Edges),
                      reference_stl=stl, reference_facets=mesh.CountFacets, reference_points=mesh.CountPoints,
                      reference_volume_mm3=mesh.Volume, reference_linear_deflection_mm=0.001)
    else:
        pts = json.load(open(os.environ["FCM_POINTS"]))
        shell = solid.Shells[0]
        RESULT["distances_mm"] = {k: [shell.distToShape(Part.Vertex(App.Vector(*(c * 1000.0 for c in p))))[0] for p in v]
                                  for k, v in pts.items()}
    RESULT["ok"] = True


try:
    main()
except Exception:
    RESULT["error"] = traceback.format_exc()
with open(os.environ["FCM_RESULT"], "w") as f:
    json.dump(RESULT, f, indent=1)
