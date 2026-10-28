"""Compose a derived workstation scene: the untouched base scene + instances of library assets.

    "$ISAACSIM_PYTHON" scripts/assets/compose_scene.py --scene config/scenes/workstation_test_spacer.json
    # also works with Blender's bundled USD (no Isaac Sim needed for this step):
    blender -b --factory-startup --python scripts/assets/compose_scene.py -- --scene config/scenes/workstation_test_spacer.json

Writes the scene config's `output` (assets/scenes/derived/<scene_id>.usda), a thin layer that
  * sublayers the base scene by relative path (the base file is only read, never opened for editing),
  * defines <instances_root> (kind=group) with one Xform per instance that references
    assets/library/<asset>/<asset>.usd by relative path (geometry is shared, never copied),
  * places each instance with the same xformOp convention as build_scene.py (translate + orient, double precision);
    the pose comes from asset_lib.scene_poses (lowest collider point on the tabletop / floor / a support instance's
    surface, + objects.clearance for dynamic bodies; lying rest poses; attached labels on mount points),
  * adds the scene-level PhysX combine modes to each instance's physics material (as build_scene.py does for all
    base materials) and, for `"static": true` instances only, physics:rigidBodyEnabled = false,
  * optionally defines /World/Cameras/AssetPreview from `preview_camera` and /World/Cameras/<CamelName> for every
    entry of `preview_cameras`,
  * optionally makes base prims inactive (`deactivate_base_prims`: an `over` with active = false, nothing else).
The layer is regenerated from the JSON every time, so add / move / remove is: edit the JSON (asset_lib.py CLI),
re-run this script. Uses only the Sdf API: the composed stage (and the hosted robot asset) is not needed here.
Writes logs/assets/<scene_id>/compose.json.
"""

import argparse
import json
import math
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asset_lib as al  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
ap = argparse.ArgumentParser()
ap.add_argument("--scene", required=True, help="scene config, e.g. config/scenes/workstation_test_spacer.json")
args, _ = ap.parse_known_args(argv)

app = None
try:
    from pxr import Gf, Sdf, UsdGeom, UsdPhysics  # noqa: F401  (Blender, or any USD build with UsdPhysics)
except ImportError:  # Isaac Sim's python.sh only exposes pxr once Kit is running
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    from pxr import Gf, Sdf, UsdGeom, UsdPhysics  # noqa: F401


def look_at(pos, target):
    """Row-major camera matrix looking along -Z at target with +Z world up (same as build_scene.look_at_matrix)."""
    f = [t - p for p, t in zip(pos, target)]
    n = math.sqrt(sum(x * x for x in f))
    f = [x / n for x in f]
    up = [0.0, 0.0, 1.0] if abs(f[2]) < 0.999 else [0.0, 1.0, 0.0]
    r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    n = math.sqrt(sum(x * x for x in r))
    r = [x / n for x in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    return Gf.Matrix4d(r[0], r[1], r[2], 0, u[0], u[1], u[2], 0, -f[0], -f[1], -f[2], 0, pos[0], pos[1], pos[2], 1)


def attr(spec, name, vtype, value, uniform=False):
    a = Sdf.AttributeSpec(spec, name, vtype, Sdf.VariabilityUniform if uniform else Sdf.VariabilityVarying)
    a.default = value
    return a


def compose(scene_rel):
    scene = al.load_scene(scene_rel)
    env = al.load_json(scene["environment_config"])
    out = al.abspath(scene["output"])
    out_dir = os.path.dirname(out)
    base = al.abspath(scene["base_scene"])
    rel = lambda p: os.path.relpath(al.abspath(p), out_dir)
    problems, placed, specs = [], [], {}
    for inst in scene["instances"]:
        status, info = al.asset_status(inst["asset"])
        if status != "current":
            problems.append(f"{inst['name']}: asset '{inst['asset']}' is {status}; run generate_asset.py first")
            continue
        if inst.get("static") and info["spec"]["physics"]["body"] != "dynamic":
            problems.append(f"{inst['name']}: 'static' override needs a dynamic asset")
        placed.append((inst, info))
        specs[inst["asset"]] = info["spec"]
    issues = al.placement_issues(scene, env, specs) if not problems else []
    if problems or issues:
        raise RuntimeError("cannot compose:\n  " + "\n  ".join(problems + issues))

    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    layer = Sdf.Layer.CreateNew(out, args={"format": "usda"})
    layer.subLayerPaths.append(rel(scene["base_scene"]))
    layer.defaultPrim = "World"
    layer.pseudoRoot.SetInfo("upAxis", "Z")
    layer.pseudoRoot.SetInfo("metersPerUnit", 1.0)
    layer.pseudoRoot.SetInfo("kilogramsPerUnit", 1.0)
    world = Sdf.CreatePrimInLayer(layer, "/World")  # an `over`: nothing is authored on /World itself
    root_name = scene["instances_root"].split("/")[-1]
    group = Sdf.PrimSpec(world, root_name, Sdf.SpecifierDef, "Xform")
    group.SetInfo("kind", "group")
    ph = env["physics"]
    record = []
    poses = al.scene_poses(scene, env, specs)
    for inst, info in placed:
        pose = poses[inst["name"]]
        pos, q = pose["position"], pose["orientation"]
        p = Sdf.PrimSpec(group, inst["name"], Sdf.SpecifierDef, "Xform")
        asset_ref = rel(al.asset_paths(inst["asset"])["usd"])
        p.referenceList.Prepend(Sdf.Reference(asset_ref))
        attr(p, "xformOp:translate", Sdf.ValueTypeNames.Double3, Gf.Vec3d(*pos))
        attr(p, "xformOp:orient", Sdf.ValueTypeNames.Quatd, Gf.Quatd(q[0], q[1], q[2], q[3]))
        attr(p, "xformOpOrder", Sdf.ValueTypeNames.TokenArray, ["xformOp:translate", "xformOp:orient"], uniform=True)
        if inst.get("static"):
            attr(p, "physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool, False)
        if info.get("physics_material_prim"):  # visual-only assets have no physics material
            m = Sdf.PrimSpec(p, info["physics_material_prim"], Sdf.SpecifierOver)
            m.SetInfo("apiSchemas", Sdf.TokenListOp.Create(prependedItems=["PhysxMaterialAPI"]))
            attr(m, "physxMaterial:frictionCombineMode", Sdf.ValueTypeNames.Token, ph["friction_combine_mode"], uniform=True)
            attr(m, "physxMaterial:restitutionCombineMode", Sdf.ValueTypeNames.Token, ph["restitution_combine_mode"], uniform=True)
        record.append({"name": inst["name"], "prim": f"{scene['instances_root']}/{inst['name']}", "asset": inst["asset"],
                       "reference": asset_ref, "position": pos, "orientation_wxyz": q, "yaw_deg": pose["yaw_deg"],
                       "surface": inst["placement"]["surface"], "support": pose["support"], "static_override": bool(inst.get("static")),
                       "asset_spec_sha256": info["spec_sha256"]})
    for d in scene.get("deactivate_base_prims", []):
        o = Sdf.CreatePrimInLayer(layer, d)  # `over` chain; only `active` is authored
        o.active = False
    cameras = ([("AssetPreview", scene["preview_camera"])] if scene.get("preview_camera") else []) + \
        [(al.camel(k), v) for k, v in scene.get("preview_cameras", {}).items()]
    for cam_name, cam in cameras:
        cams = Sdf.CreatePrimInLayer(layer, "/World/Cameras")
        c = Sdf.PrimSpec(cams, cam_name, Sdf.SpecifierDef, "Camera")
        res = env["rendering"]["resolution"]
        attr(c, "focalLength", Sdf.ValueTypeNames.Float, float(cam.get("focal_length", 35.0)))
        attr(c, "horizontalAperture", Sdf.ValueTypeNames.Float, 20.955)
        attr(c, "verticalAperture", Sdf.ValueTypeNames.Float, 20.955 * res[1] / res[0])
        attr(c, "clippingRange", Sdf.ValueTypeNames.Float2, Gf.Vec2f(0.01, 100.0))
        attr(c, "xformOp:transform", Sdf.ValueTypeNames.Matrix4d, look_at(cam["position"], cam["target"]))
        attr(c, "xformOpOrder", Sdf.ValueTypeNames.TokenArray, ["xformOp:transform"], uniform=True)
    base_meta = dict(Sdf.Layer.FindOrOpen(base).customLayerData.get("robot_agent_lab", {}))
    layer.customLayerData = {"robot_agent_lab": {
        **{k: base_meta[k] for k in ("robot_asset", "rendering_mode") if k in base_meta},  # read by the workstation validators
        "scene": scene["scene_id"], "generator": "scripts/assets/compose_scene.py", "scene_config": rel(scene_rel),
        "base_scene": rel(scene["base_scene"]), "base_scene_sha256": al.sha256_file(scene["base_scene"]),
        "instances_json": json.dumps(record),
        "note": "Derived layer: sublayers the base scene unchanged; regenerate from the scene config, do not edit."}}
    layer.Save()

    # read back what was written
    check = Sdf.Layer.FindOrOpen(out)
    written = [c.name for c in check.GetPrimAtPath(scene["instances_root"]).nameChildren] if check.GetPrimAtPath(scene["instances_root"]) else []
    ok = written == [i["name"] for i, _ in placed] and list(check.subLayerPaths) == [rel(scene["base_scene"])]
    summary = {"ok": ok, "scene_config": scene_rel, "output": scene["output"], "bytes": os.path.getsize(out),
               "base_scene": scene["base_scene"], "base_scene_sha256": al.sha256_file(scene["base_scene"]),
               "sublayers": list(check.subLayerPaths), "instances": record, "written_instances": written,
               "preview_cameras": [n for n, _ in cameras], "deactivated_base_prims": scene.get("deactivate_base_prims", [])}
    al.write_json(f"logs/assets/{scene['scene_id']}/compose.json", summary)
    print(f"[compose] {'OK' if ok else 'FAILED'}: {scene['output']} ({summary['bytes']} bytes), sublayer {summary['sublayers']}, "
          f"instances {written}", flush=True)
    for r in record:
        print(f"[compose]   {r['prim']} <- @{r['reference']}@ at {[round(x, 5) for x in r['position']]} yaw {r['yaw_deg']:.2f}", flush=True)
    return ok


code = 1
try:
    code = 0 if compose(args.scene) else 1
except Exception:
    traceback.print_exc()
    code = 2
finally:
    if app is not None:
        app.close(exit_code=code)
    sys.exit(code)
