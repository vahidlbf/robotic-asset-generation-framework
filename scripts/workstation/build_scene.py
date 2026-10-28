"""Assemble the waste-sorting workstation scene USD from the generated assets + official Franka Panda.

Run with Isaac Sim's interpreter (needed for PhysxSchema and NVIDIA asset-root resolution):
    "$ISAACSIM_PYTHON" scripts/workstation/build_scene.py [--config config/waste_sorting_environment.json]

Everything placed in the scene comes from the JSON config. Local assets are referenced by relative
paths; the robot is referenced from the NVIDIA Isaac Sim asset root resolved at build time.
Scene-level overrides (never written into the assets themselves):
  - robot home joint state + equal drive targets (a valid, non-singular initial configuration)
  - FilteredPairsAPI between the robot base link and the tabletop collider (mounting contact)
  - PhysxMaterialAPI combine modes on every physics material
  - static (rigidBodyEnabled = false) override for the decorative bottles inside the crate
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
from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade  # noqa: E402
from isaacsim.storage.native import get_assets_root_path, path_join  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_geometry as lg  # noqa: E402


import omni.client  # noqa: E402


def log(*a):
    print("[build]", *a, flush=True)


def yaw_quat(deg):
    h = math.radians(deg) / 2
    return Gf.Quatd(math.cos(h), 0, 0, math.sin(h))


def place(prim, pos, yaw_deg=0.0):
    xf = UsdGeom.Xformable(prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*pos))
    xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(yaw_quat(yaw_deg))


def look_at_matrix(pos, target, up=(0, 0, 1)):
    """Camera/light frame looking along its -Z at target, +Y as up."""
    p, t = np.array(pos, float), np.array(target, float)
    f = t - p
    f /= np.linalg.norm(f)
    upv = np.array(up, float)
    if abs(np.dot(f, upv)) > 0.999:
        upv = np.array([0, 1, 0], float)
    r = np.cross(f, upv)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    m = Gf.Matrix4d(1)
    m.SetRow(0, Gf.Vec4d(*r, 0))
    m.SetRow(1, Gf.Vec4d(*u, 0))
    m.SetRow(2, Gf.Vec4d(*(-f), 0))
    m.SetRow(3, Gf.Vec4d(*p, 1))
    return m


def preview_material(stage, path, color, roughness=0.5, metallic=0.0):
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def physics_material(stage, path, m, phys):
    mat = UsdShade.Material.Define(stage, path)
    api = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    api.CreateStaticFrictionAttr(float(m["static_friction"]))
    api.CreateDynamicFrictionAttr(float(m["dynamic_friction"]))
    api.CreateRestitutionAttr(float(m["restitution"]))
    return mat


def find_named(stage, root_path, name):
    root = stage.GetPrimAtPath(root_path)
    for p in Usd.PrimRange(root, Usd.TraverseInstanceProxies()):
        if p.GetName() == name:
            return p
    return None


def main():
    cfg_path = args.config if os.path.isabs(args.config) else os.path.join(ROOT, args.config)
    cfg = json.load(open(cfg_path))
    scene_path = os.path.join(ROOT, cfg["paths"]["scene"])
    scene_dir = os.path.dirname(scene_path)
    assets_dir = os.path.join(ROOT, cfg["paths"]["assets_dir"])
    os.makedirs(scene_dir, exist_ok=True)
    rel = lambda *p: "./" + os.path.relpath(os.path.join(assets_dir, *p), scene_dir)
    built = {"transforms": {}, "warnings": []}

    for a in ("table/table.usd", "glass_bottle/glass_bottle.usd", "plastic_bottle/plastic_bottle.usd",
              "paper_cup/paper_cup.usd", "paper_bin/paper_bin.usd", "plastic_bin/plastic_bin.usd",
              "glass_crate/glass_crate.usd"):
        if not os.path.isfile(os.path.join(assets_dir, a)):
            raise FileNotFoundError(f"missing generated asset {a}; run generate_assets.py first")

    # Robot asset through NVIDIA's asset-root API
    rcfg = cfg["robot"]
    asset_root = get_assets_root_path()
    robot_url = path_join(asset_root, rcfg["asset_relpath"])
    res, _ = omni.client.stat(robot_url)
    if res != omni.client.Result.OK:
        raise RuntimeError(f"robot asset not reachable: {robot_url} ({res})")
    log("robot asset", robot_url)
    built["robot_url"] = robot_url

    if os.path.exists(scene_path):
        os.remove(scene_path)
    layer = Sdf.Layer.CreateNew(scene_path, args={"format": "usda"})
    stage = Usd.Stage.Open(layer)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    layer.customLayerData = {"robot_agent_lab": {
        "scene": "waste_sorting_workstation", "generator": "scripts/workstation/build_scene.py",
        "config": os.path.relpath(cfg_path, scene_dir), "robot_asset": robot_url,
        "rendering_mode": cfg["rendering"]["mode"],
        "note": "Physics coefficients are illustrative simulation parameters."}}

    # --- Physics scene ---------------------------------------------------------
    ph = cfg["physics"]
    scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    scene.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
    scene.CreateGravityMagnitudeAttr(float(ph["gravity_m_s2"]))
    px = PhysxSchema.PhysxSceneAPI.Apply(scene.GetPrim())
    px.CreateTimeStepsPerSecondAttr(int(ph["steps_per_second"]))
    px.CreateSolverTypeAttr(ph["solver_type"])
    px.CreateEnableGPUDynamicsAttr(bool(ph["gpu_dynamics"]))
    px.CreateBroadphaseTypeAttr("GPU" if ph["gpu_dynamics"] else "MBP")
    px.CreateEnableCCDAttr(bool(ph["enable_ccd"]))

    # --- Environment: ground + lights -------------------------------------------
    g = cfg["ground"]
    UsdGeom.Xform.Define(stage, "/World/Environment")
    looks = "/World/Environment/Looks"
    UsdGeom.Scope.Define(stage, looks)
    gx = UsdGeom.Xform.Define(stage, "/World/Environment/Ground")
    gx.AddTranslateOp().Set(Gf.Vec3d(0, 0, -g["thickness"] / 2))
    gcube = UsdGeom.Cube.Define(stage, "/World/Environment/Ground/Floor")
    gcube.CreateSizeAttr(1.0)
    gcube.AddScaleOp().Set(Gf.Vec3f(g["size"][0], g["size"][1], g["thickness"]))
    UsdPhysics.CollisionAPI.Apply(gcube.GetPrim())
    vis = preview_material(stage, f"{looks}/FloorVisual", g["color"], g["roughness"])
    pm = physics_material(stage, f"{looks}/FloorPhysics", ph["materials"][g["physics_material"]], ph)
    UsdShade.MaterialBindingAPI.Apply(gcube.GetPrim())
    UsdShade.MaterialBindingAPI(gcube.GetPrim()).Bind(vis)
    UsdShade.MaterialBindingAPI(gcube.GetPrim()).Bind(pm, UsdShade.Tokens.weakerThanDescendants, "physics")

    lt = cfg["lighting"]
    UsdGeom.Xform.Define(stage, "/World/Environment/Lights")
    dome = UsdLux.DomeLight.Define(stage, "/World/Environment/Lights/Dome")
    dome.CreateIntensityAttr(float(lt["dome"]["intensity"]))
    dome.CreateColorAttr(Gf.Vec3f(*lt["dome"]["color"]))
    for al in lt["area_lights"]:
        rl = UsdLux.RectLight.Define(stage, f"/World/Environment/Lights/{al['name']}")
        rl.CreateWidthAttr(float(al["size"][0]))
        rl.CreateHeightAttr(float(al["size"][1]))
        rl.CreateIntensityAttr(float(al["intensity"]))
        UsdGeom.Xformable(rl).AddTransformOp().Set(look_at_matrix(al["position"], al["target"]))

    # --- Workstation: table, bins, crate --------------------------------------
    UsdGeom.Xform.Define(stage, "/World/Workstation")
    t = cfg["table"]
    table = stage.DefinePrim("/World/Workstation/Table", "Xform")
    table.GetReferences().AddReference(rel("table", "table.usd"))
    place(table, t["position"], t["yaw_deg"])
    built["transforms"]["/World/Workstation/Table"] = {"position": t["position"], "yaw_deg": t["yaw_deg"]}
    top_z = t["position"][2] + t["height"]

    sp = lg.scene_paths(cfg)
    UsdGeom.Xform.Define(stage, sp["sorting_zone"])
    for key in ("paper_bin", "plastic_bin"):
        b = cfg["bins"][key]
        prim = stage.DefinePrim(sp[key], "Xform")
        prim.GetReferences().AddReference(rel(b["asset"], f"{b['asset']}.usd"))
        place(prim, b["position"], b["yaw_deg"])
        built["transforms"][str(prim.GetPath())] = {"position": b["position"], "yaw_deg": b["yaw_deg"]}

    c = cfg["crate"]
    pf = cfg.get("crate_platform")
    if pf and c.get("support") == "crate_platform":
        plat = stage.DefinePrim(sp["crate_platform"], "Xform")
        plat.GetReferences().AddReference(rel(pf["asset"], f"{pf['asset']}.usd"))
        place(plat, pf["position"], pf["yaw_deg"])
        built["transforms"][sp["crate_platform"]] = {"position": pf["position"], "yaw_deg": pf["yaw_deg"], "height": pf["height"]}
        if abs(c["position"][2] - pf["height"]) > 1e-9 or c["position"][:2] != pf["position"][:2]:
            raise ValueError(f"crate position {c['position']} must sit centred on the platform top {pf['position'][:2]} z={pf['height']}")
    crate = stage.DefinePrim(sp["crate"], "Xform")
    crate.GetReferences().AddReference(rel(c["asset"], f"{c['asset']}.usd"))
    place(crate, c["position"], c["yaw_deg"])
    built["transforms"][str(crate.GetPath())] = {"position": c["position"], "yaw_deg": c["yaw_deg"]}
    if c["bottles"]["enabled"]:
        UsdGeom.Xform.Define(stage, sp["crate_bottles"])
        occupied = [cell for cell in lg.crate_cells(cfg) if cell["occupied"]]
        for k, cell in enumerate(occupied):
            pos = [cell["centre"][0], cell["centre"][1], cell["floor_z"] + 0.0005]
            bp = stage.DefinePrim(f"{sp['crate_bottles']}/Bottle_{k}", "Xform")
            bp.GetReferences().AddReference(rel("glass_bottle", "glass_bottle.usd"))
            place(bp, pos, 0.0)
            if c["bottles"]["static"]:
                bp.CreateAttribute("physics:rigidBodyEnabled", Sdf.ValueTypeNames.Bool).Set(False)
            built["transforms"][str(bp.GetPath())] = {"position": pos, "yaw_deg": 0.0, "static": c["bottles"]["static"],
                                                      "compartment": cell["index"]}

    # --- Dynamic tabletop objects ---------------------------------------------
    UsdGeom.Xform.Define(stage, "/World/Objects")
    clearance = cfg["objects"]["clearance"]
    for key, name in (("glass_bottle", "GlassBottle"), ("plastic_bottle", "PlasticBottle"), ("paper_cup", "PaperCup")):
        o = cfg["objects"][key]
        prim = stage.DefinePrim(f"/World/Objects/{name}", "Xform")
        prim.GetReferences().AddReference(rel(o["asset"], f"{o['asset']}.usd"))
        # Bottom-origin assets: Z = tabletop surface + clearance (no half-height term).
        pos = [o["position"][0], o["position"][1], top_z + clearance]
        place(prim, pos, o["yaw_deg"])
        built["transforms"][str(prim.GetPath())] = {"position": pos, "yaw_deg": o["yaw_deg"],
                                                    "z_rule": "bottom-origin: tabletop_z + clearance"}

    # --- Render-material overrides (scene layer only) ----------------------------
    targets = {"glass_bottle": ["/World/Objects/GlassBottle"] + [str(x.GetPath()) for x in
               stage.GetPrimAtPath(sp["crate_bottles"]).GetChildren()] if c["bottles"]["enabled"] else ["/World/Objects/GlassBottle"],
               "plastic_bottle": ["/World/Objects/PlasticBottle"]}
    built["render_material_overrides"] = {}
    for key, prims in targets.items():
        rm = cfg["objects"][key].get("render_material")
        if not rm or rm["type"] != "OmniGlass":
            continue
        mpath = f"/World/Looks/{key}_OmniGlass"
        UsdGeom.Scope.Define(stage, "/World/Looks")
        mat = UsdShade.Material.Define(stage, mpath)
        sh = UsdShade.Shader.Define(stage, mpath + "/Shader")
        sh.SetSourceAsset(Sdf.AssetPath("OmniGlass.mdl"), "mdl")
        sh.SetSourceAssetSubIdentifier("OmniGlass", "mdl")
        sh.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rm["glass_color"]))
        sh.CreateInput("glass_ior", Sdf.ValueTypeNames.Float).Set(float(rm["glass_ior"]))
        sh.CreateInput("frosting_roughness", Sdf.ValueTypeNames.Float).Set(float(rm["frosting_roughness"]))
        sh.CreateInput("thin_walled", Sdf.ValueTypeNames.Bool).Set(bool(rm["thin_walled"]))
        sh.CreateInput("depth", Sdf.ValueTypeNames.Float).Set(float(rm["depth"]))
        mat.CreateSurfaceOutput("mdl").ConnectToSource(sh.ConnectableAPI(), "out")
        bound = []
        for root_path in prims:
            for mp in Usd.PrimRange(stage.GetPrimAtPath(root_path + "/Visual")):
                if mp.IsA(UsdGeom.Mesh) and mp.GetName() == rm["mesh"]:
                    UsdShade.MaterialBindingAPI.Apply(mp)
                    UsdShade.MaterialBindingAPI(mp).Bind(mat, UsdShade.Tokens.strongerThanDescendants)
                    bound.append(str(mp.GetPath()))
        if len(bound) != len(prims):
            raise RuntimeError(f"OmniGlass override for {key}: bound {bound}, expected one mesh per {prims}")
        built["render_material_overrides"][key] = bound

    # --- Robot ------------------------------------------------------------------
    mount = UsdGeom.Xform.Define(stage, rcfg["mount_prim"])
    place(mount.GetPrim(), rcfg["base_position"], rcfg["base_yaw_deg"])
    robot_path = f"{rcfg['mount_prim']}/{rcfg['prim_name']}"
    robot = stage.DefinePrim(robot_path, "Xform")
    robot.GetReferences().AddReference(robot_url)
    for vset, sel in rcfg["variants"].items():
        vs = robot.GetVariantSets().GetVariantSet(vset)
        if sel not in vs.GetVariantNames():
            raise RuntimeError(f"robot variant {vset}={sel} not in {vs.GetVariantNames()}")
        vs.SetVariantSelection(sel)
    built["transforms"][rcfg["mount_prim"]] = {"position": rcfg["base_position"], "yaw_deg": rcfg["base_yaw_deg"]}
    joint_overrides = {}
    for jn, val in {**rcfg["home_joint_positions_deg"], **rcfg["home_finger_positions_m"]}.items():
        jp = find_named(stage, robot_path, jn)
        if jp is None:
            raise RuntimeError(f"joint {jn} not found in robot asset")
        kind = "angular" if jp.IsA(UsdPhysics.RevoluteJoint) else "linear"
        lo, hi = (UsdPhysics.RevoluteJoint(jp) if kind == "angular" else UsdPhysics.PrismaticJoint(jp)).GetLowerLimitAttr().Get(), \
                 (UsdPhysics.RevoluteJoint(jp) if kind == "angular" else UsdPhysics.PrismaticJoint(jp)).GetUpperLimitAttr().Get()
        if not (lo - 1e-6 <= val <= hi + 1e-6):
            raise ValueError(f"home position {jn}={val} outside limits [{lo}, {hi}]")
        js = PhysxSchema.JointStateAPI.Apply(jp, kind)
        js.CreatePositionAttr().Set(float(val))
        js.CreateVelocityAttr().Set(0.0)
        if jp.HasAPI(UsdPhysics.DriveAPI, kind):
            UsdPhysics.DriveAPI(jp, kind).GetTargetPositionAttr().Set(float(val))
        joint_overrides[str(jp.GetPath())] = {"kind": kind, "position": val, "limits": [lo, hi],
                                              "drive": jp.HasAPI(UsdPhysics.DriveAPI, kind)}
    built["robot_joint_overrides"] = joint_overrides
    if rcfg["filter_base_collision_with_tabletop"]:
        link0 = find_named(stage, robot_path, "panda_link0")
        top_col = "/World/Workstation/Table/Tabletop/Collision/TopSlab/Shape"
        if not stage.GetPrimAtPath(top_col).IsValid():
            raise RuntimeError(f"tabletop collider {top_col} not found")
        UsdPhysics.FilteredPairsAPI.Apply(link0).CreateFilteredPairsRel().AddTarget(top_col)
        built["robot_filtered_pairs"] = [str(link0.GetPath()), top_col]

    # --- PhysX combine modes on every physics material --------------------------
    n_mat = 0
    for p in Usd.PrimRange(stage.GetPseudoRoot()):
        if p.HasAPI(UsdPhysics.MaterialAPI) and not p.IsInstanceProxy():
            pxm = PhysxSchema.PhysxMaterialAPI.Apply(p)
            pxm.CreateFrictionCombineModeAttr().Set(ph["friction_combine_mode"])
            pxm.CreateRestitutionCombineModeAttr().Set(ph["restitution_combine_mode"])
            n_mat += 1
    built["physx_material_overrides"] = n_mat

    # --- Manipulation target frames (TCP poses chosen by optimize_layout.py; no geometry) -------
    sel = cfg.get("manipulation_targets", {}).get("selected", {})
    if sel:
        UsdGeom.Xform.Define(stage, sp["targets"])
        for dest, d in sel.items():
            UsdGeom.Xform.Define(stage, f"{sp['targets']}/{dest}")
            for pname, pose in d["poses"].items():
                tp = UsdGeom.Xform.Define(stage, f"{sp['targets']}/{dest}/{pname}")
                w, x, y, z = pose["tcp_orientation_wxyz"]
                tp.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*pose["tcp_position"]))
                tp.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Quatd(w, x, y, z))
                tp.GetPrim().SetCustomDataByKey("tcp_frame", cfg["gripper"]["tcp_frame"])
                tp.GetPrim().SetCustomDataByKey("finger_opening_m", float(pose["finger_opening_m"]))
        built["target_frames"] = {k: list(v["poses"]) for k, v in sel.items()}

    # --- Cameras ------------------------------------------------------------------
    UsdGeom.Xform.Define(stage, "/World/Cameras")
    for name, cam in cfg["cameras"].items():
        cp = UsdGeom.Camera.Define(stage, f"/World/Cameras/{''.join(w.capitalize() for w in name.split('_'))}")
        cp.CreateFocalLengthAttr(float(cam["focal_length"]))
        cp.CreateHorizontalApertureAttr(20.955)
        cp.CreateVerticalApertureAttr(20.955 * cfg["rendering"]["resolution"][1] / cfg["rendering"]["resolution"][0])
        cp.CreateClippingRangeAttr(Gf.Vec2f(0.05, 100.0))
        UsdGeom.Xformable(cp).AddTransformOp().Set(look_at_matrix(cam["position"], cam["target"], cam.get("up", (0, 0, 1))))
        built["transforms"][str(cp.GetPath())] = {"position": cam["position"], "target": cam["target"]}

    # --- Model hierarchy (kind) ---------------------------------------------------
    # Asset roots are kind=component. Their ancestors must be group/assembly for USD to treat them as models,
    # which lets the viewport's "select by Models" mode pick the rigid-body root instead of its render mesh.
    from pxr import Kind
    Usd.ModelAPI(world.GetPrim()).SetKind(Kind.Tokens.assembly)
    for gp in ("/World/Objects", "/World/Workstation", sp["sorting_zone"], sp["crate_bottles"], "/World/Environment",
               rcfg["mount_prim"], sp["targets"]):
        if stage.GetPrimAtPath(gp).IsValid():
            Usd.ModelAPI(stage.GetPrimAtPath(gp)).SetKind(Kind.Tokens.group)
    built["model_roots"] = [str(p.GetPath()) for p in stage.Traverse() if Usd.ModelAPI(p).IsModel()
                            and Usd.ModelAPI(p).GetKind() == Kind.Tokens.component]

    layer.Save()
    log("saved", os.path.relpath(scene_path, ROOT), f"({os.path.getsize(scene_path)} bytes)")
    out = os.path.join(ROOT, cfg["paths"]["logs_dir"], "scene_build.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(built, open(out, "w"), indent=2, default=str)
    return 0


code = 1
try:
    t0 = time.time()
    code = main()
    log(f"done in {time.time() - t0:.1f}s")
except Exception:
    traceback.print_exc()
    code = 2
finally:
    simulation_app.close(exit_code=code)
    sys.exit(code)
