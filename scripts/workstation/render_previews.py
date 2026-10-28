"""Render preview images of the workstation scene from the configured cameras (RTX real-time).

    "$ISAACSIM_PYTHON" scripts/workstation/render_previews.py [--config ...] [--cameras main top robot_side]

Physics is initialised and stepped briefly first so the robot's authored home joint state and the
objects' resting poses are what gets rendered (link transforms in the USD are the zero pose until the
articulation is simulated). The scene file on disk is not modified.
"""

import argparse
import json
import os
import sys
import time
import traceback

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="config/waste_sorting_environment.json")
parser.add_argument("--cameras", nargs="*", default=None)
parser.add_argument("--settle-steps", type=int, default=60)
args, _ = parser.parse_known_args()
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from isaacsim import SimulationApp  # noqa: E402

cfg = json.load(open(args.config if os.path.isabs(args.config) else os.path.join(ROOT, args.config)))
res = cfg["rendering"]["resolution"]
simulation_app = SimulationApp({"headless": True, "width": res[0], "height": res[1],
                                "renderer": cfg["rendering"].get("renderer", "RealTimePathTracing")})

import carb.settings  # noqa: E402
import omni.replicator.core as rep  # noqa: E402
from omni.replicator.core.functional import write_image  # noqa: E402
import isaacsim.core.experimental.utils.stage as stage_utils  # noqa: E402
from isaacsim.core.simulation_manager import SimulationManager  # noqa: E402


def main():
    rcfg = cfg["rendering"]
    if rcfg.get("path_tracing") or rcfg.get("renderer", "").lower() == "pathtracing":
        raise RuntimeError("offline path tracing is disabled for previews by project policy (set rendering.renderer)")
    s = carb.settings.get_settings()
    if rcfg.get("translucency", True):
        s.set("/rtx/translucency/enabled", True)
        s.set("/rtx/raytracing/fractionalCutoutOpacity", True)
    s.set("rtx/post/dlss/execMode", 2)
    print(f"[render] active rtx rendermode={s.get('/rtx/rendermode')} requested={rcfg.get('renderer')}", flush=True)
    scene = os.path.join(ROOT, cfg["paths"]["scene"])
    ok, stage = stage_utils.open_stage(scene)
    if not ok:
        raise RuntimeError(f"cannot open {scene}")
    while stage_utils.is_stage_loading():
        simulation_app.update()
    simulation_app.reset_render_settings()  # opening a stage resets RTX settings; re-apply the configured renderer
    if rcfg.get("translucency", True):
        s.set("/rtx/translucency/enabled", True)
        s.set("/rtx/raytracing/fractionalCutoutOpacity", True)
    print(f"[render] active rtx rendermode after stage open={s.get('/rtx/rendermode')}", flush=True)
    active_mode = s.get("/rtx/rendermode")
    if active_mode == "PathTracing":
        raise RuntimeError("offline PathTracing became active; refusing to render previews")
    rep.orchestrator.set_capture_on_play(False)
    cams = args.cameras or list(cfg["cameras"])
    out_dir = os.path.join(ROOT, cfg["paths"]["logs_dir"])
    os.makedirs(out_dir, exist_ok=True)
    SimulationManager.initialize_physics()
    SimulationManager.step(steps=args.settle_steps)
    results = {}
    for name in cams:
        path = f"/World/Cameras/{''.join(w.capitalize() for w in name.split('_'))}"
        rp = rep.create.render_product(path, resolution=tuple(res), name=f"rp_{name}")
        ann = rep.AnnotatorRegistry.get_annotator("rgb")
        ann.attach(rp)
        for _ in range(int(rcfg.get("warmup_frames", 40)) // 8):
            rep.orchestrator.step(rt_subframes=8, delta_time=0.0, pause_timeline=False)
        carb.settings.get_settings().set("/rtx-transient/post/dlss/forceParamReset", True)
        rep.orchestrator.step(rt_subframes=16, delta_time=0.0, pause_timeline=False)
        data = ann.get_data()
        f = os.path.join(out_dir, f"preview_{name}.png")
        write_image(path=f, data=data)
        rep.orchestrator.wait_until_complete()
        mean = float(data[..., :3].mean()) if hasattr(data, "mean") else None
        results[name] = {"file": os.path.relpath(f, ROOT), "shape": list(getattr(data, "shape", [])), "mean_rgb": mean,
                         "renderer_requested": rcfg.get("renderer"), "rtx_rendermode_active": active_mode}
        print(f"[render] {name} -> {f} shape={results[name]['shape']} mean={mean}", flush=True)
        ann.detach()
        rp.destroy()
    json.dump(results, open(os.path.join(out_dir, "preview_results.json"), "w"), indent=2)
    return 0 if all(r["mean_rgb"] and r["mean_rgb"] > 5 for r in results.values()) else 1


code = 1
try:
    t0 = time.time()
    code = main()
    print(f"[render] done in {time.time() - t0:.1f}s", flush=True)
except Exception:
    traceback.print_exc()
    code = 2
finally:
    simulation_app.close(exit_code=code)
    sys.exit(code)
