#!/usr/bin/env python3
"""Add one or more assets to a derived workstation scene, end to end, without regenerating anything else (system python3).

    python3 scripts/assets/add_asset.py --spec config/assets/test_spacer.json \
        --scene config/scenes/workstation_test_spacer.json [--force] [--no-physics] [--base-suites] [--preview]
    python3 scripts/assets/add_asset.py --spec config/assets/a.json --spec config/assets/b.json --scene ... (several assets)

Stages (each its own process; same tools as the main workflow):
  1. spec check            asset_lib.spec_errors (stdlib)
  2. generate_asset.py     Blender, once per --spec: builds ONLY assets/library/<asset_id>/ (skipped when already current;
                           --force rebuilds)
  3. scene check           asset_lib.scene_errors + analytic placement pre-check (stdlib)
  4. compose_scene.py      Blender's USD: writes the thin derived layer (base scene is sublayered, not edited)
  5. validate_asset_scene  Isaac Sim: structure / registry / instance / placement / preservation (+ PhysX settle)
  6. --base-suites         Isaac Sim: the workstation's own validate_scene.py + run_physics_test.py on the derived
                           scene, via a config copy whose paths point at the derived layer and logs/assets/<scene_id>/
  7. --preview             Isaac Sim: render_previews.py for the derived scene's preview camera(s) (+ the base main camera)
Protected files (workstation assets, base scene, configs, other library assets, other derived scenes, the parent ramp
project) are hashed before and after; any change fails the run. Report: logs/assets/<scene_id>/add_asset_report.md.
Environment: ISAACSIM_PYTHON (or ISAACSIM_PATH), BLENDER - see docs/INSTALLATION.md.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "workstation"))
import asset_lib as al  # noqa: E402
from run_workflow import GpuMonitor, parent_hashes  # noqa: E402


def run(label, cmd, log_rel, gpu, timeout=1800):
    gpu.label = label
    print(f"[add-asset] {label}: {' '.join(cmd)}", flush=True)
    t0 = time.time()
    with open(al.abspath(log_rel), "w") as f:
        proc = subprocess.Popen(cmd, cwd=al.ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in proc.stdout:  # piped (snap Blender cannot write to a redirected file descriptor)
            f.write(line.decode("utf-8", "replace"))
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = None
    gpu.label = "idle"
    r = {"stage": label, "command": " ".join(cmd), "exit_code": rc, "seconds": round(time.time() - t0, 1), "log": log_rel}
    print(f"[add-asset] {label}: exit={rc} ({r['seconds']}s) log={log_rel}", flush=True)
    return r


def protected(scene, asset_ids):
    keep_out = [al.asset_paths(a)["dir"] for a in asset_ids] + [al.REGISTRY, scene["output"]]
    rel = ["assets/workstation", scene["base_scene"], "config/waste_sorting_environment.json", "config/motion_planning.json"]
    if os.path.isdir(al.abspath(al.LIBRARY_DIR)):
        rel.append(al.LIBRARY_DIR)
    if os.path.isdir(al.abspath("assets/scenes/derived")):
        rel.append("assets/scenes/derived")
    files = al.hash_tree([r for r in rel if os.path.exists(al.abspath(r))], exclude=keep_out)
    mtimes = {f: os.path.getmtime(al.abspath(f)) for f in files}
    return files, mtimes


def tail_line(log_rel, needle):
    try:
        lines = [l for l in open(al.abspath(log_rel)).read().splitlines() if needle in l]
        return lines[-1].strip() if lines else None
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, action="append", help="asset spec; repeat for several assets")
    ap.add_argument("--scene", required=True)
    ap.add_argument("--force", action="store_true", help="rebuild the asset even if it is current")
    ap.add_argument("--no-physics", action="store_true", help="skip the PhysX settle test of the instances")
    ap.add_argument("--base-suites", action="store_true", help="also run validate_scene.py + run_physics_test.py on the derived scene")
    ap.add_argument("--preview", action="store_true", help="render the derived scene's preview cameras")
    a = ap.parse_args()

    for sp in a.spec:
        errs = al.spec_errors(al.load_json(sp))
        if errs:
            print(f"invalid spec {sp}:\n  " + "\n  ".join(errs))
            return 1
    aids = [al.load_json(sp)["asset_id"] for sp in a.spec]
    aid = aids[0] if len(aids) == 1 else "+".join(aids)
    scene0 = al.load_scene(a.scene, check_assets=False)
    sid = scene0["scene_id"]
    out_rel = f"logs/assets/{sid}"
    os.makedirs(al.abspath(out_rel), exist_ok=True)
    gpu = GpuMonitor()
    gpu.start()
    status_before = {x: al.asset_status(x, sp)[0] for x, sp in zip(aids, a.spec)}
    files0, mt0 = protected(scene0, aids)
    parent0 = parent_hashes()
    stages = []

    ok = True
    for x, sp in zip(aids, a.spec):
        cmd = [al.blender_bin(), "-b", "--factory-startup", "--python-exit-code", "1", "--python", "scripts/assets/generate_asset.py",
               "--", "--spec", sp] + (["--force"] if a.force else [])
        stages.append(run(f"generate_asset ({x})", cmd, f"{out_rel}/generate_{x}.log", gpu))
        ok = ok and stages[-1]["exit_code"] == 0
    status_after = {x: al.asset_status(x, sp)[0] for x, sp in zip(aids, a.spec)}
    infos = {x: al.asset_info(x) for x in aids}
    ok = ok and all(v == "current" for v in status_after.values())
    scene = None
    if ok:
        serr = al.scene_errors(al.load_json(a.scene))
        issues = al.placement_issues(al.load_json(a.scene), al.load_json(scene0["environment_config"]), al.specs_for(al.load_json(a.scene)))
        if serr or issues:
            print("scene config rejected:\n  " + "\n  ".join(serr + issues))
            ok = False
        else:
            scene = al.load_scene(a.scene)
            for x in aids:
                if not any(i["asset"] == x for i in scene["instances"]):
                    print(f"warning: {a.scene} has no instance of {x}; add one with asset_lib.py add-instance")
    if ok:
        stages.append(run("compose_scene", [al.blender_bin(), "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                                            "scripts/assets/compose_scene.py", "--", "--scene", a.scene], f"{out_rel}/compose.log", gpu))
        ok = stages[-1]["exit_code"] == 0
    if ok:
        stages.append(run("validate_asset_scene", [al.isaac_python(), "scripts/assets/validate_asset_scene.py", "--scene", a.scene]
                          + (["--no-physics"] if a.no_physics else []), f"{out_rel}/validate.log", gpu))
        ok = stages[-1]["exit_code"] == 0
    base = {}
    if (a.base_suites or a.preview) and scene:
        env = al.load_json(scene["environment_config"])
        env["paths"] = dict(env["paths"], scene=scene["output"], logs_dir=f"{out_rel}/base_suites")
        env["_doc"] = f"GENERATED COPY for {sid} by scripts/assets/add_asset.py: paths point at the derived scene. Do not edit."
        cfg_rel = f"{out_rel}/base_suites/environment_config.json"
        al.write_json(cfg_rel, env)
        if a.base_suites:
            for label, script, log in (("base suite: validate_scene", "validate_scene.py", "validate_scene.log"),
                                       ("base suite: run_physics_test", "run_physics_test.py", "run_physics_test.log")):
                stages.append(run(label, [al.isaac_python(), f"scripts/workstation/{script}", "--config", cfg_rel],
                                  f"{out_rel}/base_suites/{log}", gpu))
            base = {"static": tail_line(f"{out_rel}/base_suites/validate_scene.log", "static checks passed"),
                    "dynamic": tail_line(f"{out_rel}/base_suites/run_physics_test.log", "dynamic checks passed")}
            ok = ok and all(s["exit_code"] == 0 for s in stages[-2:])
        if a.preview:
            cams = (["asset_preview"] if scene.get("preview_camera") else []) + list(scene.get("preview_cameras", {})) + ["main"]
            stages.append(run("preview", [al.isaac_python(), "scripts/workstation/render_previews.py", "--config", cfg_rel,
                                          "--cameras", *cams], f"{out_rel}/base_suites/render.log", gpu))
    gpu.stop_flag = True
    files1, mt1 = protected(scene0, aids)
    parent1 = parent_hashes()
    changed = sorted(k for k in set(files0) | set(files1) if files0.get(k) != files1.get(k))
    touched = sorted(k for k in mt0 if mt1.get(k) != mt0[k])
    parent_changed = sorted(k for k in set(parent0) | set(parent1) if parent0.get(k) != parent1.get(k))
    val = al.load_json(f"{out_rel}/validation_results.json") if os.path.isfile(al.abspath(f"{out_rel}/validation_results.json")) else {}
    comp = al.load_json(f"{out_rel}/compose.json") if os.path.isfile(al.abspath(f"{out_rel}/compose.json")) else {}
    ok = ok and not changed and not touched and not parent_changed
    one = len(aids) == 1
    pick = lambda info: {k: (info or {}).get(k) for k in ("file_sha256", "mass_properties", "bounds_visual_m", "colliders", "generated_utc")}
    rep = {"passed": ok, "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "spec": a.spec[0] if one else a.spec,
           "asset_id": aid, "asset_ids": aids,
           "scene_config": a.scene, "derived_scene": scene0["output"],
           "asset_status_before": status_before[aid] if one else status_before,
           "asset_status_after": status_after[aid] if one else status_after,
           "asset_rebuilt": (status_before[aid] != "current" or a.force) if one else {x: status_before[x] != "current" or a.force for x in aids},
           "stages": stages,
           "asset_info": pick(infos[aid]) if one else {x: pick(infos[x]) for x in aids},
           "instances": comp.get("instances"), "validation": {k: val.get(k) for k in ("passed", "summary", "failed", "physics_run")},
           "base_suites_on_derived_scene": base or None,
           "protected_files": {"count": len(files0), "content_changed": changed, "mtime_changed": touched},
           "parent_project": {"files": len(parent0), "changed": parent_changed}, "gpu_memory": gpu.summary()}
    al.write_json(f"{out_rel}/add_asset_report.json", rep)
    write_md(f"{out_rel}/add_asset_report.md", rep)
    print(f"[add-asset] {'PASS' if ok else 'FAIL'}: validation {rep['validation'].get('summary')}; protected files "
          f"{len(files0)} unchanged={not changed and not touched}; parent unchanged={not parent_changed}; report {out_rel}/add_asset_report.md")
    return 0 if ok else 1


def write_md(rel, r):
    multi = len(r["asset_ids"]) > 1
    o = [f"# Add asset{'s' if multi else ''} `{r['asset_id']}` -> `{r['derived_scene']}`\n", f"- Generated: {r['generated']}",
         f"- **Result: {'PASS' if r['passed'] else 'FAIL'}**"]
    if multi:
        for x in r["asset_ids"]:
            o.append(f"- `{x}`: status before/after {r['asset_status_before'][x]} / {r['asset_status_after'][x]} "
                     f"({'rebuilt' if r['asset_rebuilt'][x] else 'already current, not rebuilt'})")
    else:
        o.append(f"- Asset status before/after: {r['asset_status_before']} / {r['asset_status_after']} "
                 f"({'rebuilt' if r['asset_rebuilt'] else 'already current, not rebuilt'})")
    o.append(f"- Targeted validation: {r['validation'].get('summary')} (physics: {r['validation'].get('physics_run')})")
    if r["base_suites_on_derived_scene"]:
        o.append(f"- Workstation suites on the derived scene: {r['base_suites_on_derived_scene']['static']}; "
                 f"{r['base_suites_on_derived_scene']['dynamic']}")
    pf = r["protected_files"]
    o.append(f"- Protected files: {pf['count']} hashed before/after; content changed: {pf['content_changed'] or 'none'}; "
             f"mtime changed: {pf['mtime_changed'] or 'none'}")
    o.append(f"- Parent ramp project: {r['parent_project']['files']} files; changed: {r['parent_project']['changed'] or 'none'}\n")
    o.append("| Stage | Exit | Time (s) | Log |\n|---|---|---|---|")
    for s in r["stages"]:
        o.append(f"| {s['stage']} | {s['exit_code']} | {s['seconds']} | `{s['log']}` |")
    o.append("\n| Instance | Prim | Position (m) | Yaw (deg) | Reference |\n|---|---|---|---|---|")
    for i in r["instances"] or []:
        o.append(f"| {i['name']} | `{i['prim']}` | {[round(x, 5) for x in i['position']]} | {round(i['yaw_deg'], 3)} | `{i['reference']}` |")
    for x, ai in (r["asset_info"].items() if multi else [(r["asset_id"], r["asset_info"])]):
        mp = ai.get("mass_properties") or {}
        o.append(f"\n`{x}` files: {ai.get('file_sha256')}; mass {mp.get('mass_kg', 'static')} kg"
                 f"{' (' + mp['mass_source'] + ')' if mp else ''}; colliders {len(ai.get('colliders') or [])}.")
    o.append("\nDetails: `validation_report.md` (targeted checks), `compose.json`, `base_suites/` (if run).")
    with open(al.abspath(rel), "w") as f:
        f.write("\n".join(o) + "\n")


if __name__ == "__main__":
    sys.exit(main())
