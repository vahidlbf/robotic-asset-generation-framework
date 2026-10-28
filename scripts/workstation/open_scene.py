"""Open the workstation scene in the Isaac Sim GUI (RTX real-time), optionally playing physics.

    "$ISAACSIM_PYTHON" scripts/workstation/open_scene.py [--play] [--keep-picking-mode] [--no-guard] [--scene <usd>]

GUI/physics consistency (see gui_physics_guard.py for the root cause):
  * Viewport picking is set to "select by Models" for this session, so clicking a bottle selects its
    rigid-body root (/World/Objects/<Name>) rather than its render mesh. The previous picking mode is
    restored on exit (it is a persistent Kit setting). --keep-picking-mode leaves it untouched.
  * RigidBodyGuard: if a render mesh / collider inside a rigid body is moved anyway (e.g. picked via the
    Stage tree), the offset is transferred to the rigid body once the drag ends, so physics follows.
  * A "Workstation physics" window offers physics-safe teleports (raise objects, reset to initial pose).
Close the window to exit. The scene file is not modified unless you save from the GUI.
"""

import argparse
import json
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="config/waste_sorting_environment.json")
parser.add_argument("--scene", default=None,
                    help="scene to open instead of the config's paths.scene, e.g. assets/scenes/derived/<scene_id>.usda")
parser.add_argument("--play", action="store_true", help="start the physics simulation after loading")
parser.add_argument("--keep-picking-mode", action="store_true", help="do not switch viewport picking to Models")
parser.add_argument("--no-guard", action="store_true", help="disable the visual-offset guard")
parser.add_argument("--self-test", action="store_true",
                    help="non-interactive check: play, press 'Raise objects', verify the bodies fall back, exit")
args, _ = parser.parse_known_args()
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(args.config if os.path.isabs(args.config) else os.path.join(ROOT, args.config)))

from isaacsim import SimulationApp  # noqa: E402

app = SimulationApp({"headless": False, "renderer": cfg["rendering"].get("renderer", "RealTimePathTracing"),
                     "width": cfg["rendering"]["resolution"][0], "height": cfg["rendering"]["resolution"][1]})

import carb.settings  # noqa: E402
import omni.timeline  # noqa: E402
import isaacsim.core.experimental.utils.app as app_utils  # noqa: E402
import isaacsim.core.experimental.utils.stage as stage_utils  # noqa: E402
from isaacsim.core.experimental.prims import RigidPrim  # noqa: E402
from pxr import Usd, UsdGeom, UsdPhysics  # noqa: E402

from gui_physics_guard import RigidBodyGuard, teleport  # noqa: E402

OBJECTS = ["/World/Objects/GlassBottle", "/World/Objects/PlasticBottle", "/World/Objects/PaperCup"]
PICK_KEY = "/persistent/app/viewport/pickingMode"
settings = carb.settings.get_settings()

if cfg["rendering"].get("translucency", True):
    settings.set("/rtx/translucency/enabled", True)
stage_utils.open_stage(os.path.join(ROOT, args.scene or cfg["paths"]["scene"]))
while stage_utils.is_stage_loading():
    app.update()
app.reset_render_settings()  # opening a stage resets RTX settings; re-apply the configured renderer
if cfg["rendering"].get("translucency", True):
    settings.set("/rtx/translucency/enabled", True)
stage = stage_utils.get_current_stage()
# Derived scenes may deactivate the base objects (deactivate_base_prims): only active ones are handled.
OBJECTS = [p for p in OBJECTS if stage.GetPrimAtPath(p).IsValid() and stage.GetPrimAtPath(p).IsActive()]
# Derived scenes (scripts/assets/compose_scene.py): dynamic library-asset instances get the same guard / buttons.
user_root = stage.GetPrimAtPath("/World/UserObjects")
if user_root.IsValid():
    OBJECTS += [str(p.GetPath()) for p in user_root.GetChildren()
                if p.HasAPI(UsdPhysics.RigidBodyAPI) and p.GetAttribute("physics:rigidBodyEnabled").Get() is not False]
    print(f"[open_scene] rigid bodies handled: {OBJECTS}", flush=True)
try:
    from omni.kit.viewport.utility import get_active_viewport
    get_active_viewport().camera_path = "/World/Cameras/Main"
except Exception as exc:
    print(f"[open_scene] could not switch viewport camera: {exc}")

original_pick = settings.get(PICK_KEY)
if not args.keep_picking_mode:
    settings.set(PICK_KEY, "kind:model.ALL")
    print(f"[open_scene] viewport picking set to Models for this session (was {original_pick!r}; restored on exit)")

initial = {p: UsdGeom.Xformable(stage.GetPrimAtPath(p)).ComputeLocalToWorldTransform(Usd.TimeCode.Default()) for p in OBJECTS}
bodies = {p: RigidPrim(p) for p in OBJECTS}
guard = None if args.no_guard else RigidBodyGuard(stage, OBJECTS, log=lambda m: print(m, flush=True))
timeline = omni.timeline.get_timeline_interface()


def raise_objects(dz=0.30):
    playing = timeline.is_playing()
    for p in OBJECTS:
        if playing:
            pos, _ = bodies[p].get_world_poses()
            target = pos.numpy()[0].tolist()
        else:
            target = list(UsdGeom.Xformable(stage.GetPrimAtPath(p)).ComputeLocalToWorldTransform(0).ExtractTranslation())
        target[2] += dz
        teleport(stage, bodies, p, target, playing=playing)
    print(f"[open_scene] raised objects by {dz} m ({'physics API' if playing else 'USD, applied on Play'})", flush=True)


def reset_objects():
    playing = timeline.is_playing()
    for p, m in initial.items():
        q = m.ExtractRotationQuat()
        teleport(stage, bodies, p, list(m.ExtractTranslation()),
                 [q.GetReal(), *q.GetImaginary()], playing=playing)
    print("[open_scene] objects reset to their initial poses", flush=True)


try:
    import omni.ui as ui
    win = ui.Window("Workstation physics", width=300, height=140)
    with win.frame:
        with ui.VStack(spacing=6):
            ui.Label("Physics-safe object moves (rigid-body roots)")
            ui.Button("Raise objects +0.30 m", clicked_fn=raise_objects)
            ui.Button("Reset objects to initial pose", clicked_fn=reset_objects)
except Exception as exc:
    print(f"[open_scene] UI panel unavailable: {exc}")

def self_test():
    import numpy as np
    app_utils.play()
    for _ in range(30):
        app.update()
    raise_objects()
    zs = []
    for _ in range(120):
        app.update()
        zs.append([float(bodies[p].get_world_poses()[0].numpy()[0][2]) for p in OBJECTS])
    zs = np.array(zs)
    z0 = np.array([initial[p].ExtractTranslation()[2] for p in OBJECTS])  # bodies resettle where they started (table or tray floor)
    ok = bool((zs.max(axis=0) > z0 + 0.25).all() and (np.abs(zs[-1] - z0) < 0.005).all())
    print(f"[open_scene] self-test {'PASS' if ok else 'FAIL'}: {len(OBJECTS)} bodies, max z {zs.max(axis=0).round(4).tolist()}, "
          f"final z {zs[-1].round(4).tolist()} (initial {z0.round(4).tolist()}); picking mode now {settings.get(PICK_KEY)!r}", flush=True)
    app_utils.stop()
    app.update()
    return ok


code = 0
if args.play and not args.self_test:
    app_utils.play()
try:
    if args.self_test:
        code = 0 if self_test() else 1
    else:
        while app.is_running():
            app.update()
            if guard:
                guard.update()
finally:
    if guard:
        guard.close()
    if not args.keep_picking_mode:
        settings.set(PICK_KEY, original_pick)
        print(f"[open_scene] picking mode restored to {settings.get(PICK_KEY)!r}", flush=True)
    app.close(exit_code=code)
    sys.exit(code)
