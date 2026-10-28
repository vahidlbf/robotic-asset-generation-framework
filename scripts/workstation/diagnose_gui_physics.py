"""Controlled reproduction of "objects stay suspended after being raised in the GUI".

    "$ISAACSIM_PYTHON" scripts/workstation/diagnose_gui_physics.py --mode gui|headless

Runs the same scenarios in either mode, each on a freshly opened scene, and records every app update:
physics state (RigidPrim tensor API), the authored USD transform of the rigid-body root, the USD world
transform of the visual mesh and of a collider, sim time and physics step count.

Stepping deliberately uses the GUI path (timeline playing + app.update()), i.e. what pressing Play does.

Scenarios (glass bottle; the other objects are audited the same way):
  S0 baseline           no edit
  S1 root_raise         +0.30 m on the rigid-body root's xform, while stopped (Stage-tree / Property panel edit)
  S2 visual_raise       +0.30 m on the render mesh, while stopped (what a viewport click + gizmo drag edits
                        when picking resolves to the leaf mesh)
  S3 root_raise_playing +0.30 m USD xform edit on the root while the simulation is playing
  S4 teleport_playing   +0.30 m via RigidPrim.set_world_poses + zero velocity while playing
  S5 visual_raise_guarded          S2 with RigidBodyGuard active (as in open_scene.py), edit while stopped
  S6 visual_raise_playing_guarded  render-mesh edit while playing, with RigidBodyGuard active
Writes logs/workstation/gui_diagnosis/<mode>.json.
"""

import argparse
import json
import os
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["gui", "headless"], required=True)
parser.add_argument("--config", default="config/waste_sorting_environment.json")
parser.add_argument("--updates", type=int, default=90)
args, _ = parser.parse_known_args()
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
cfg = json.load(open(os.path.join(ROOT, args.config)))

from isaacsim import SimulationApp  # noqa: E402

app = SimulationApp({"headless": args.mode == "headless", "renderer": cfg["rendering"]["renderer"],
                     "width": 960, "height": 540})

import carb.settings  # noqa: E402
import numpy as np  # noqa: E402
import omni.timeline  # noqa: E402
from pxr import Gf, PhysxSchema, Usd, UsdGeom, UsdPhysics  # noqa: E402
import isaacsim.core.experimental.utils.app as app_utils  # noqa: E402
import isaacsim.core.experimental.utils.stage as stage_utils  # noqa: E402
from isaacsim.core.experimental.prims import RigidPrim  # noqa: E402
from isaacsim.core.simulation_manager import SimulationManager  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui_physics_guard import RigidBodyGuard  # noqa: E402

SCENE = os.path.join(ROOT, cfg["paths"]["scene"])
OBJ = {"glass_bottle": ("/World/Objects/GlassBottle", "GlassBottle"),
       "plastic_bottle": ("/World/Objects/PlasticBottle", "PlasticBottle"),
       "paper_cup": ("/World/Objects/PaperCup", "PaperCup")}
RAISE = 0.30


def open_fresh():
    if not omni.timeline.get_timeline_interface().is_stopped():
        app_utils.stop(commit=True)
        app.update()
    ok, stage = stage_utils.open_stage(SCENE)
    while stage_utils.is_stage_loading():
        app.update()
    for _ in range(5):
        app.update()
    return stage_utils.get_current_stage()


def mesh_of(stage, root, name):
    for p in Usd.PrimRange(stage.GetPrimAtPath(root + "/Visual")):
        if p.IsA(UsdGeom.Mesh) and p.GetName() == name:
            return p
    return None


def world_z(stage, path):
    return float(UsdGeom.Xformable(stage.GetPrimAtPath(path)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation()[2])


def raise_prim_usd(prim, dz):
    """Equivalent of moving the prim with the gizmo / Property panel: edit its local translate op."""
    xf = UsdGeom.Xformable(prim)
    ops = {op.GetOpName(): op for op in xf.GetOrderedXformOps()}
    if "xformOp:translate" in ops:
        v = ops["xformOp:translate"].Get()
        ops["xformOp:translate"].Set(type(v)(v[0], v[1], v[2] + dz))
    else:
        # Kit's transform gizmo adds translate/orient/scale ops to a prim that has none
        xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0, 0, dz))


def audit(stage):
    out = {"physics_scenes": [str(p.GetPath()) for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)],
           "active_engine": SimulationManager.get_active_physics_engine(),
           "fabric_enabled": SimulationManager.is_fabric_enabled() if hasattr(SimulationManager, "is_fabric_enabled") else None,
           "picking_mode": carb.settings.get_settings().get("/persistent/app/viewport/pickingMode"),
           "objects": {}}
    for k, (root, mesh_name) in OBJ.items():
        p = stage.GetPrimAtPath(root)
        rb = UsdPhysics.RigidBodyAPI(p)
        prb = PhysxSchema.PhysxRigidBodyAPI(p)
        anc, q = [], p.GetParent()
        while q and not q.IsPseudoRoot():
            if q.HasAPI(UsdPhysics.RigidBodyAPI) or q.HasAPI(UsdPhysics.ArticulationRootAPI):
                anc.append(str(q.GetPath()))
            q = q.GetParent()
        desc_rb = [str(d.GetPath()) for d in Usd.PrimRange(p) if d != p and d.HasAPI(UsdPhysics.RigidBodyAPI)]
        joints = [str(j.GetPath()) for j in stage.Traverse() if j.IsA(UsdPhysics.Joint) and
                  any(str(t) == root for t in UsdPhysics.Joint(j).GetBody0Rel().GetTargets() + UsdPhysics.Joint(j).GetBody1Rel().GetTargets())]
        mesh = mesh_of(stage, root, mesh_name)
        out["objects"][k] = {
            "rigid_body_prim": root, "has_rigid_body_api": p.HasAPI(UsdPhysics.RigidBodyAPI),
            "rigid_body_enabled": rb.GetRigidBodyEnabledAttr().Get(), "kinematic_enabled": rb.GetKinematicEnabledAttr().Get(),
            "starts_asleep": rb.GetStartsAsleepAttr().Get(), "simulation_owner": [str(t) for t in rb.GetSimulationOwnerRel().GetTargets()],
            "physx_disable_gravity": prb.GetDisableGravityAttr().Get() if p.HasAPI(PhysxSchema.PhysxRigidBodyAPI) else "default(False)",
            "physx_sleep_threshold": prb.GetSleepThresholdAttr().Get() if p.HasAPI(PhysxSchema.PhysxRigidBodyAPI) else "default",
            "mass": UsdPhysics.MassAPI(p).GetMassAttr().Get(), "rigid_ancestors": anc, "rigid_descendants": desc_rb,
            "joints_on_body": joints, "colliders": [str(d.GetPath()) for d in Usd.PrimRange(p) if d.HasAPI(UsdPhysics.CollisionAPI)],
            "root_is_model": Usd.ModelAPI(p).IsModel(), "root_kind": Usd.ModelAPI(p).GetKind(),
            "parent_kinds": {str(a.GetPath()): Usd.ModelAPI(a).GetKind() for a in (p.GetParent(), p.GetParent().GetParent())},
            "render_mesh": str(mesh.GetPath()) if mesh else None,
            "render_mesh_has_physics": bool(mesh) and (mesh.HasAPI(UsdPhysics.RigidBodyAPI) or mesh.HasAPI(UsdPhysics.CollisionAPI)),
        }
    return out


def run_scenario(name):
    stage = open_fresh()
    root, mesh_name = OBJ["glass_bottle"]
    mesh = mesh_of(stage, root, mesh_name)
    collider = root + "/Collision/Body/Shape"
    rp = RigidPrim(root)
    guard = RigidBodyGuard(stage, [o[0] for o in OBJ.values()], log=lambda m: print(m, flush=True)) if name.endswith("_guarded") else None
    if name == "root_raise":
        raise_prim_usd(stage.GetPrimAtPath(root), RAISE)
    elif name in ("visual_raise", "visual_raise_guarded"):
        raise_prim_usd(mesh, RAISE)
    app.update()
    if guard:  # the user releases the gizmo, a moment passes, then presses Play
        for _ in range(guard.settle + 3):
            app.update()
            guard.update()
    edit_at = 30 if name in ("root_raise_playing", "teleport_playing", "visual_raise_playing_guarded") else None
    tl = omni.timeline.get_timeline_interface()
    app_utils.play(commit=True)
    rows, steps0 = [], None
    for i in range(args.updates):
        if i == edit_at:
            if name == "root_raise_playing":
                raise_prim_usd(stage.GetPrimAtPath(root), RAISE)
            elif name == "visual_raise_playing_guarded":
                raise_prim_usd(mesh, RAISE)
            else:
                p, q = rp.get_world_poses()
                pos = p.numpy()[0].copy()
                pos[2] += RAISE
                rp.set_world_poses(positions=[pos], orientations=[q.numpy()[0]])
                rp.set_velocities(linear_velocities=[[0, 0, 0]], angular_velocities=[[0, 0, 0]])
        app.update()
        if guard:
            guard.update()
        try:
            p, _ = rp.get_world_poses()
            v, _ = rp.get_velocities()
            pz, vz = float(p.numpy()[0][2]), float(v.numpy()[0][2])
        except Exception as exc:
            pz = vz = None
        n = SimulationManager.get_num_physics_steps()
        steps0 = n if steps0 is None else steps0
        rows.append({"update": i, "sim_time": SimulationManager.get_simulation_time(), "physics_steps": n - steps0,
                     "playing": tl.is_playing(), "body_z_physics": pz, "body_vz_physics": vz,
                     "root_z_usd": world_z(stage, root), "visual_mesh_z_usd": world_z(stage, str(mesh.GetPath())),
                     "collider_z_usd": world_z(stage, collider)})
    app_utils.stop(commit=True)
    app.update()
    transfers = guard.transfers if guard else []
    if guard:
        guard.close()
    r0, r1 = rows[0], rows[-1]
    top = cfg["table"]["height"]
    return {"rows": rows, "summary": {
        "physics_steps": r1["physics_steps"], "sim_time_advanced": r1["sim_time"] - r0["sim_time"],
        "body_z_first": r0["body_z_physics"], "body_z_max": max(r["body_z_physics"] for r in rows if r["body_z_physics"] is not None),
        "body_z_final": r1["body_z_physics"], "visual_mesh_z_final_usd": r1["visual_mesh_z_usd"],
        "visual_minus_body_m": r1["visual_mesh_z_usd"] - r1["body_z_physics"],
        "body_on_table_at_end": abs(r1["body_z_physics"] - top) < 0.005,
        "visual_floating_above_body": r1["visual_mesh_z_usd"] - r1["body_z_physics"] > 0.05,
        "guard_transfers": transfers}}


def main():
    out = {"mode": args.mode, "audit": audit(open_fresh()), "scenarios": {}}
    for s in ("baseline", "root_raise", "visual_raise", "root_raise_playing", "teleport_playing",
              "visual_raise_guarded", "visual_raise_playing_guarded"):
        res = run_scenario(s)
        out["scenarios"][s] = res
        print(f"[diag:{args.mode}] {s}: " + json.dumps(res["summary"]), flush=True)
    d = os.path.join(ROOT, cfg["paths"]["logs_dir"], "gui_diagnosis")
    os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, f"{args.mode}.json"), "w"), indent=2, default=str)
    print(f"[diag:{args.mode}] audit: " + json.dumps(out["audit"], default=str), flush=True)
    return 0


code = 1
try:
    code = main()
except Exception:
    traceback.print_exc()
    code = 2
finally:
    app.close(exit_code=code)
    sys.exit(code)
