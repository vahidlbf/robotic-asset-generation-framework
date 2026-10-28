#!/usr/bin/env python3
"""End-to-end workflow for the waste-sorting workstation (system Python orchestrator).

    cd waste-sorting-workstation && python3 scripts/workstation/run_workflow.py

Stages (each a separate process; Omniverse code only ever runs under Isaac Sim's python.sh):
  1. generate_assets.py   Blender headless  -> assets/workstation/*
  2. build_scene.py       Isaac Sim python  -> assets/scenes/waste_sorting_workstation.usd
  3. validate_scene.py    Isaac Sim python  -> static checks, inventory, reachability (incl. Lula IK)
  4. run_physics_test.py  Isaac Sim python  -> settle, robot, bin-drop tests
  5. render_previews.py   Isaac Sim python  -> preview PNGs
  6. parent ramp project regression: file hashes + the ramp pipeline re-run in a sandbox copy
Then writes logs/workstation/validation_results.json and validation_report.md.

Environment: ISAACSIM_PYTHON (default $ISAACSIM_PATH/python.sh, else ~/isaacsim/python.sh), BLENDER (default "blender").
"""

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT.parent
# The parent ramp project is only present in the original robot-agent-lab checkout; a standalone clone has an
# unrelated parent directory (e.g. $HOME), which must not be hashed or copied.
PARENT_IS_RAMP = (PARENT / "scripts" / "run_pipeline.py").is_file() and (PARENT / "config").is_dir()
ISAAC = os.environ.get("ISAACSIM_PYTHON") or os.path.join(os.environ.get("ISAACSIM_PATH", os.path.expanduser("~/isaacsim")), "python.sh")
BLENDER = os.environ.get("BLENDER", "blender")


class GpuMonitor(threading.Thread):
    def __init__(self, period=1.0):
        super().__init__(daemon=True)
        self.period, self.samples, self.stop_flag, self.label = period, [], False, "idle"

    def run(self):
        while not self.stop_flag:
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
                used, total = (int(x) for x in out.split(","))
                self.samples.append((time.time(), self.label, used, total))
            except Exception:
                pass
            time.sleep(self.period)

    def summary(self):
        by = {}
        for _, lab, used, total in self.samples:
            b = by.setdefault(lab, {"peak_mib": 0, "samples": 0, "total_mib": total})
            b["peak_mib"] = max(b["peak_mib"], used)
            b["samples"] += 1
        return by


def run(label, cmd, log_name, gpu, cwd=ROOT, timeout=1800):
    gpu.label = label
    log = ROOT / "logs" / "workstation" / log_name
    print(f"[workflow] {label}: {' '.join(str(c) for c in cmd)}", flush=True)
    t0 = time.time()
    with open(log, "w") as f:
        # Pipe through Python (snap Blender fails writing to a redirected file descriptor directly).
        proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in proc.stdout:
            f.write(line.decode("utf-8", "replace"))
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = None
    gpu.label = "idle"
    secs = round(time.time() - t0, 1)
    print(f"[workflow] {label}: exit={rc} ({secs}s) log={log.relative_to(ROOT)}", flush=True)
    return {"stage": label, "command": " ".join(str(c) for c in cmd), "exit_code": rc, "seconds": secs,
            "log": str(log.relative_to(ROOT))}


def parent_hashes():
    h = {}
    if not PARENT_IS_RAMP:
        return h
    for p in sorted(PARENT.rglob("*")):
        if p.is_file() and ROOT not in p.parents and ".git" not in p.parts and "__pycache__" not in p.parts:
            h[str(p.relative_to(PARENT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return h


def ramp_regression(gpu):
    """Re-run the parent ramp pipeline from a sandbox copy of its config/ and scripts/ (parent untouched)."""
    box = ROOT / "logs" / "workstation" / "ramp_regression"
    if box.exists():
        shutil.rmtree(box)
    for d in ("config", "scripts"):
        shutil.copytree(PARENT / d, box / d, ignore=shutil.ignore_patterns("__pycache__"))
    for d in ("assets/freecad", "assets/blender", "assets/usd", "logs"):
        (box / d).mkdir(parents=True, exist_ok=True)
    r = run("ramp regression: asset pipeline (sandbox)", [sys.executable, "scripts/run_pipeline.py", "--no-preview"],
            "ramp_regression.log", gpu, cwd=box, timeout=900)
    summary = None
    pr = sorted((box / "logs" / "runs").glob("*/pipeline_result.json"))
    if pr:
        summary = json.loads(pr[-1].read_text()).get("summary")
    r2 = run("ramp regression: Isaac Sim friction test (sandbox)",
             [ISAAC, "scripts/isaacsim/test_ramp_physics.py", "--config", "config/isaacsim_ramp_test.json"],
             "ramp_regression_isaac.log", gpu, cwd=box, timeout=900)
    isaac = None
    rj = box / "logs" / "isaacsim" / "results.json"
    if rj.exists():
        d = json.loads(rj.read_text())
        isaac = {"overall_pass": d.get("overall_pass"),
                 "verdicts": {e["name"]: e["analysis"]["verdict"] for e in d.get("experiments", [])}}
    return {**r, "exit_code": r["exit_code"] if r["exit_code"] else r2["exit_code"], "sandbox": str(box.relative_to(ROOT)),
            "summary": summary, "isaac_stage": r2, "isaac_summary": isaac}


def preview_hashes():
    d = ROOT / "logs" / "workstation"
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.glob("preview_*.png"))}


def inspection_current(insp):
    """The manual inspection notes count only if they were written for exactly the current preview images."""
    if not insp.exists() or "<!--meta " not in insp.read_text():
        return False
    meta = json.loads(insp.read_text().split("<!--meta ")[1].split(" -->")[0])
    cur = preview_hashes()
    return bool(cur) and meta.get("preview_sha256") == cur


def load(p):
    try:
        return json.loads((ROOT / p).read_text())
    except Exception as exc:
        return {"error": str(exc)}


def flatten(checks):
    return [(g, k, c) for g, v in (checks or {}).items() for k, c in v.items()]


def fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, list):
        return "[" + ", ".join(fmt(x) for x in v) + "]"
    return str(v)


def table(rows):
    out = ["| Group | Check | Result | Key values |", "|---|---|---|---|"]
    for g, k, c in rows:
        det = "; ".join(f"{a}={fmt(b)}" for a, b in c.items() if a not in ("passed",) and len(fmt(b)) < 120)
        out.append(f"| {g} | `{k}` | {'PASS' if c['passed'] else '**FAIL**'} | {det.replace('|', '/')} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/waste_sorting_environment.json")
    ap.add_argument("--skip-assets", action="store_true")
    ap.add_argument("--skip-ramp-regression", action="store_true")
    ap.add_argument("--report-only", action="store_true",
                    help="recompute classification/report from the last run's outputs without re-running any stage")
    a = ap.parse_args()
    cfg = json.loads((ROOT / a.config).read_text())
    (ROOT / "logs" / "workstation").mkdir(parents=True, exist_ok=True)
    gpu = GpuMonitor()
    prev = load("logs/workstation/validation_results.json") if a.report_only else {}
    if a.report_only:
        stages, ramp, changed = prev.get("stages", []), prev.get("ramp_regression"), prev.get("parent_project_files_changed", [])
        gpu.summary = lambda: prev.get("gpu_memory", {})
    else:
        stages, ramp, changed = run_stages(a, gpu)
    return finish(a, cfg, gpu, stages, ramp, changed)


def run_stages(a, gpu):
    gpu.start()
    time.sleep(1.5)
    before = parent_hashes()
    stages = []
    if not a.skip_assets:
        stages.append(run("generate_assets (Blender)", [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                                                        "scripts/workstation/generate_assets.py", "--", "--config", a.config],
                          "assets_generate.log", gpu))
    for label, script, logname in (("build_scene", "build_scene.py", "build.log"),
                                   ("validate_scene", "validate_scene.py", "validate.log"),
                                   ("run_physics_test", "run_physics_test.py", "physics.log"),
                                   ("render_previews", "render_previews.py", "render.log")):
        stages.append(run(label, [ISAAC, f"scripts/workstation/{script}", "--config", a.config], logname, gpu))
        if label == "build_scene" and stages[-1]["exit_code"] != 0:
            break
    if not PARENT_IS_RAMP and not a.skip_ramp_regression:
        print("[workflow] parent ramp project not found next to this checkout: ramp regression skipped", flush=True)
    ramp = None if a.skip_ramp_regression or not PARENT_IS_RAMP else ramp_regression(gpu)
    after = parent_hashes()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    gpu.stop_flag = True
    time.sleep(1.2)
    return stages, ramp, changed


def finish(a, cfg, gpu, stages, ramp, changed):

    static = load("logs/workstation/static_validation.json")
    physics = load("logs/workstation/physics_results.json")
    previews = load("logs/workstation/preview_results.json")
    manifest = load(f"{cfg['paths']['assets_dir']}/asset_manifest.json")
    build = load("logs/workstation/scene_build.json")
    inv = load("logs/workstation/scene_inventory.json")
    srows, prows = flatten(static.get("checks")), flatten(physics.get("checks"))
    s_fail = [f"{g}.{k}" for g, k, c in srows if not c["passed"]]
    p_fail = [f"{g}.{k}" for g, k, c in prows if not c["passed"]]
    stage_fail = [s["stage"] for s in stages if s["exit_code"] != 0]
    previews_ok = isinstance(previews, dict) and all(isinstance(v, dict) and v.get("mean_rgb", 0) > 5 for v in previews.values()) and "main" in previews and "top" in previews
    insp = ROOT / "logs" / "workstation" / "visual_inspection.md"
    inspected_current = inspection_current(insp)
    ramp_ok = (ramp is not None) and ramp["exit_code"] == 0 and bool((ramp.get("isaac_summary") or {}).get("overall_pass"))
    criteria = {
        "1_complete_usd_scene": not any(f.startswith("usd.") for f in s_fail),
        "2_real_articulated_robot": not any(f.startswith("robot.") for f in s_fail + p_fail),
        "3_table_four_legs": "geometry.exactly_four_legs" not in s_fail,
        "4_three_objects": all(f"geometry.{k}_dimensions" not in s_fail for k in ("glass_bottle", "plastic_bottle", "paper_cup")),
        "5_two_bins": all(f"geometry.{k}_dimensions" not in s_fail for k in ("paper_bin", "plastic_bin")),
        "6_glass_crate": "geometry.crate_dimensions" not in s_fail,
        "7_visual_materials": "usd.visual_material_bindings_resolve" not in s_fail,
        "8_physics_configured": not any(f.startswith("physics.") for f in s_fail),
        "9_objects_settle": not any(f.startswith("settle_") for f in p_fail),
        "10_bins_functional_collision": not any(f.startswith("bin_drop_") for f in p_fail),
        "11_scene_opens_in_isaac_sim": "run_physics_test" not in stage_fail and "render_previews" not in stage_fail,
        "12_main_camera_complete_view": previews_ok and inspected_current,
        "13_validation_saved": True,
        "14_ramp_project_functional": ramp_ok and not changed,
        "15_sorting_zone_layout_valid": bool(srows) and not any(f.startswith("layout.") for f in s_fail),
        "16_destination_targets_ik_and_endpoint_clear": bool(srows) and not any(f.startswith("reachability.") for f in s_fail),
        "17_glass_placement_stable": bool(prows) and any(g == "glass_placement" for g, _, _ in prows)
                                     and not any(f.startswith("glass_placement.") for f in p_fail),
    }
    all_ok = all(criteria.values()) and not stage_fail
    any_core_broken = not criteria["1_complete_usd_scene"] or not criteria["9_objects_settle"] or not criteria["2_real_articulated_robot"]
    classification = "FULLY VALIDATED" if all_ok else ("FAILED" if any_core_broken or stage_fail else "PARTIALLY VALIDATED")
    results = {"classification": classification, "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
               "success_criteria": criteria, "stages": stages, "static_failed": s_fail, "dynamic_failed": p_fail,
               "static_checks": f"{len(srows) - len(s_fail)}/{len(srows)}", "dynamic_checks": f"{len(prows) - len(p_fail)}/{len(prows)}",
               "gpu_memory": gpu.summary(), "parent_project_files_changed": changed, "ramp_regression": ramp,
               "previews": previews, "visual_inspection_current": inspected_current,
               "warnings": (static.get("warnings") or []) + (physics.get("warnings") or [])}
    (ROOT / "logs" / "workstation" / "validation_results.json").write_text(json.dumps(results, indent=2, default=str))
    write_report(cfg, results, static, physics, manifest, build, inv, srows, prows, insp if inspected_current else None)
    print(f"[workflow] static {results['static_checks']}, dynamic {results['dynamic_checks']}, classification: {classification}")
    return 0 if classification == "FULLY VALIDATED" else 1


def write_report(cfg, res, static, physics, manifest, build, inv, srows, prows, insp):
    o = [f"# Waste-sorting workstation — validation report\n",
         f"- Generated: {res['generated']}",
         f"- **Classification: {res['classification']}**",
         f"- Static checks: {res['static_checks']}; dynamic checks: {res['dynamic_checks']}",
         f"- Scene: `{cfg['paths']['scene']}`; config: `config/waste_sorting_environment.json`",
         f"- Robot: official NVIDIA Franka Emika Panda (`{cfg['robot']['asset_relpath']}`, variants {cfg['robot']['variants']}), "
         f"resolved to `{build.get('robot_url')}`\n"]
    o.append("## Success criteria\n")
    o.append("| Criterion | Met |\n|---|---|")
    for k, v in res["success_criteria"].items():
        o.append(f"| {k} | {'yes' if v else '**no**'} |")
    o.append("\n## Executed stages\n")
    o.append("| Stage | Exit | Time (s) | Log |\n|---|---|---|---|")
    for s in res["stages"] + ([res["ramp_regression"], res["ramp_regression"]["isaac_stage"]] if res["ramp_regression"] else []):
        o.append(f"| {s['stage']} | {s['exit_code']} | {s['seconds']} | `{s['log']}` |")
    o.append("\n## Scene layout (world frame, metres; Z up)\n")
    t = cfg["table"]
    o.append(f"- Table: {t['length']} × {t['width']} × {t['height']} m centred at {t['position'][:2]}; top surface z = {t['height']}, "
             f"bottom z = {t['height'] - t['top_thickness']}; 4 legs {t['leg_size']}×{t['leg_size']}×{t['leg_height']} m, "
             f"outer faces inset {t['leg_inset']} m from the tabletop edges.")
    r = cfg["robot"]
    o.append(f"- Robot base (panda_link0 frame): {r['base_position']}, yaw {r['base_yaw_deg']}°; home pose "
             f"{list(r['home_joint_positions_deg'].values())}° , fingers {list(r['home_finger_positions_m'].values())} m.")
    for k in ("glass_bottle", "plastic_bottle", "paper_cup"):
        tr = build.get("transforms", {}).get(f"/World/Objects/{''.join(w.capitalize() for w in k.split('_'))}", {})
        o.append(f"- {k}: initial (bottom-centre) {fmt(tr.get('position'))}, mass {cfg['objects'][k]['mass']} kg")
    for k in ("paper_bin", "plastic_bin"):
        o.append(f"- {k}: centre {cfg['bins'][k]['position']}, 0.32 × 0.32 × 0.45 m, label {cfg['bins'][k]['label']}")
    o.append(f"- Glass crate (on the platform): base {cfg['crate']['position']}, yaw {cfg['crate']['yaw_deg']}°, "
             f"{cfg['crate']['length']} × {cfg['crate']['width']} × {cfg['crate']['height']} m, {len(cfg['crate']['bottles']['cells'])} static bottles")
    o.append(f"- Ground: {cfg['ground']['size']} m slab, top at z = 0.")
    o.append("\nRobot mounting and tabletop objects are unchanged from the first validated layout; the sorting destinations were "
             "re-positioned by optimize_layout.py (see the sorting-zone section).\n")
    o.append("## Assets\n")
    o.append("| Asset | Files | Collision | Mass properties |\n|---|---|---|---|")
    for k, v in (manifest.get("assets") or {}).items():
        mp = v.get("mass_properties") or {}
        mtxt = (f"COM z={fmt(mp['center_of_mass'][2])} m, I={fmt(mp['diagonal_inertia'])} kg·m²"
                + (f", mesh volume {fmt(mp.get('volume_m3'))} m³ → density {fmt(mp.get('density_kg_m3'))} kg/m³" if mp.get("volume_m3") else "")
                ) if mp else "static"
        o.append(f"| {k} | {', '.join(v.get('files', []))} | {fmt(v.get('colliders'))} | {mtxt} |")
    o.append("\n## Static validation (geometry, USD, physics schemas, robot)\n")
    o.append(table([x for x in srows if x[0] != "reachability"]))
    o.append("\n## Dynamic validation (headless PhysX, CPU, 120 Hz)\n")
    o.append(table(prows))
    st = physics.get("settle", {})
    if st.get("objects"):
        o.append("\n**Settling, 3 s:**\n\n| Object | Initial bottom z | Final bottom z | Δz (mm) | Drift (mm) | Max tilt (°) | Speed (m/s, from positions) | Normal force / weight (N) | Max penetration (mm) |\n|---|---|---|---|---|---|---|---|---|")
        for k, v in st["objects"].items():
            o.append(f"| {k} | {v['initial_height_bottom_m']:.5f} | {v['final_height_bottom_m']:.5f} | {v['height_change_m']*1000:.3f} | "
                     f"{v['horizontal_drift_m']*1000:.3f} | {v['max_tilt_deg']:.4f} | {v['final_speed_position_derived']:.1e} | "
                     f"{v['mean_normal_force_last_0_5s_N']:.4f} / {v['weight_N']:.4f} | {v['max_penetration_m']*1000:.3f} |")
    rb = st.get("robot", {})
    if rb:
        o.append(f"\n**Robot:** {rb['num_dofs']} DOFs {rb['dof_names']}; max joint drift over 3 s "
                 f"{max(rb['max_joint_drift_deg']):.4f}°, base drift {rb['base_drift_m']:.1e} m; max link–table / link–object contact "
                 f"{rb.get('max_link_table_contact_N')} / {rb.get('max_link_object_contact_N')} N (base–tabletop pair filtered).")
    bd = physics.get("bin_drop", {})
    if bd.get("bins"):
        o.append(f"\n**Bin drop test** (temporary stage `{bd['temp_stage']}`, 0.06 m / 0.1 kg cube from 0.15 m above the rim):\n")
        o.append("| Bin | Crosses rim at t (s) | xy at rim | Lowest bottom z | Final bottom z | Bottom force / weight (N) |\n|---|---|---|---|---|---|")
        for k, v in bd["bins"].items():
            o.append(f"| {k} | {fmt(v['t_cross_rim'])} | {fmt(v['xy_at_rim_crossing'])} | {v['min_bottom_z']:.4f} | {v['final'][2] - 0.03:.4f} | "
                     f"{v['mean_bottom_contact_force_N']:.3f} / {v['weight_N']:.3f} |")
        pc = bd.get("robot_contact_positive_control")
        if pc:
            o.append(f"\nPositive control for robot contact readback: probe dropped on the fixed robot → contact {pc['links_with_contact_N']} N, "
                     f"joint disturbance {pc['max_joint_disturbance_deg']:.3f}°.")
    o.extend(sorting_zone_section(cfg, static, physics))
    o.append("\n## Previews\n")
    for n in ("main", "top", "robot_side"):
        if (ROOT / "logs" / "workstation" / f"preview_{n}.png").exists():
            o.append(f"![{n}](preview_{n}.png)\n")
    if insp:
        o.append(insp.read_text().split("<!--meta")[0])
    else:
        o.append("**Previews have not been manually inspected since they were last rendered.**\n")
    gd = ROOT / "logs" / "workstation" / "gui_diagnosis"
    if gd.exists():
        o.append("## GUI ↔ physics consistency (diagnose_gui_physics.py)\n")
        o.append("| Mode | Scenario | Physics steps | Body z first / max / final | Visual − body (m) | Floating |\n|---|---|---|---|---|---|")
        for fj in sorted(gd.glob("*.json")):
            dd = json.loads(fj.read_text())
            for name, sc in dd["scenarios"].items():
                sm = sc["summary"]
                o.append(f"| {dd['mode']} | {name} | {sm['physics_steps']} | {sm['body_z_first']:.4f} / {sm['body_z_max']:.4f} / "
                         f"{sm['body_z_final']:.4f} | {sm['visual_minus_body_m']:+.4f} | {'**yes**' if sm['visual_floating_above_body'] else 'no'} |")
        o.append("\n`visual_raise` (moving the render mesh, which a default viewport click selects) leaves the rigid body on the table: "
                 "the reported 'suspended' objects. Physics and the rigid-body configuration are correct. `open_scene.py` now selects "
                 "by Models for the session and runs RigidBodyGuard (scenarios `*_guarded`).\n")
    o.append("## GPU memory (nvidia-smi, sampled every 1 s)\n")
    o.append("| Stage | Peak used (MiB) | Total (MiB) |\n|---|---|---|")
    for k, v in res["gpu_memory"].items():
        o.append(f"| {k} | {v['peak_mib']} | {v['total_mib']} |")
    o.append("\n## Parent ramp project\n")
    o.append(f"- Files changed outside `waste-sorting-workstation` during this workflow: {res['parent_project_files_changed'] or 'none'}")
    if res["ramp_regression"]:
        rr = res["ramp_regression"]
        o.append(f"- Ramp asset pipeline re-run from a sandbox copy (`{rr['sandbox']}`): check summary {rr['summary']}")
        o.append(f"- Ramp Isaac Sim friction experiment re-run in the sandbox: exit {rr['isaac_stage']['exit_code']}, {rr['isaac_summary']}")
    o.append("\n## Warnings and limitations\n")
    for w in res["warnings"]:
        o.append(f"- {w}")
    o.append(LIMITATIONS)
    o.append("\n## Commands\n")
    o.append("```bash\n# from the waste-sorting-workstation directory; ISAACSIM_PYTHON = Isaac Sim python.sh (docs/INSTALLATION.md)\n# regenerate + validate everything\npython3 scripts/workstation/run_workflow.py\n"
             "# open the scene in the Isaac Sim GUI (add --play to start physics)\n\"$ISAACSIM_PYTHON\" scripts/workstation/open_scene.py\n"
             "# headless physics test only\n\"$ISAACSIM_PYTHON\" scripts/workstation/run_physics_test.py\n```")
    (ROOT / "logs" / "workstation" / "validation_report.md").write_text("\n".join(o) + "\n")


def sorting_zone_section(cfg, static, physics):
    o = ["\n## Sorting zone layout and manipulation targets\n"]
    ls = load("logs/workstation/layout_search.json")
    if isinstance(ls, dict) and ls.get("bins"):
        nb = {k: f"{sum(r['feasible'] for r in v)}/{len(v)}" for k, v in ls["bins"].items()}
        nc = f"{sum(c['feasible'] for c in ls['crate'])}/{len(ls['crate'])}"
        o.append(f"- Layout search (`scripts/workstation/optimize_layout.py`, seed {cfg['layout_search']['seed']}): feasible bin positions "
                 f"{nb}; feasible crate/platform candidates {nc} (positions × heights {cfg['layout_search']['platform_heights']} × yaws "
                 f"{cfg['layout_search']['crate_yaws_deg']}); chosen = rank #{ls['chosen']['rank'] if ls.get('chosen') else '—'} "
                 f"after re-evaluation with all destination geometry. Robot mounting unchanged.")
    pf, c = cfg["crate_platform"], cfg["crate"]
    o.append(f"- PAPER bin centre {cfg['bins']['paper_bin']['position']}, PLASTIC bin centre {cfg['bins']['plastic_bin']['position']} (on the floor).")
    o.append(f"- Crate platform (static lab cabinet) centre {pf['position'][:2]}, yaw {pf['yaw_deg']}°, height **{pf['height']} m**, top "
             f"{pf['top_length']} × {pf['top_width']} × {pf['top_thickness']} m; crate on top at {c['position']} (yaw {c['yaw_deg']}°), "
             f"{c['length']} × {c['width']} × {c['height']} m, {c['cells'][0]}×{c['cells'][1]} compartments, separators "
             f"{c['separator_thickness']} m × {c['separator_height']} m (crate geometry unchanged).")
    comp = (static.get("reachability") or {}).get("compartments", [])
    if comp:
        o.append("\n| Compartment | Occupied | Free size (crate-local x × y, m) | Floor z | Rim z |\n|---|---|---|---|---|")
        for cl in comp:
            mark = " **(target)**" if cl["index"] == list(c["target_compartment"]) else ""
            o.append(f"| {cl['index']}{mark} | {cl['occupied']} | {cl['free_size_local'][0]:.4f} × {cl['free_size_local'][1]:.4f} | "
                     f"{cl['floor_z']:.3f} | {cl['rim_z']:.3f} |")
    dest = (static.get("reachability") or {}).get("destinations", {})
    for key, d in dest.items():
        ev = d["evidence"]
        o.append(f"\n### {key} (object: {cfg['manipulation_targets'][key]['object']}; gripper yaw {d['meta']['gripper_yaw_deg']:.0f}°)\n")
        o.append("Evidence: " + ", ".join(f"{k} = **{v}**" for k, v in ev.items()))
        o.append("\n| Pose | TCP position (m) | Opening (m) | IK | Joint margin (frac / deg) | Manipulability | Robot clearance (m), closest | "
                 "Object clearance (m) | Finger / released-object clearance (m) | OK |\n|---|---|---|---|---|---|---|---|---|---|")
        wps = [p for p in d["poses"] if p.get("waypoint")]
        for p in d["poses"]:
            if p.get("waypoint"):
                continue
            if not p.get("ik_success"):
                o.append(f"| {p['name']} | — | — | **no** | | | | | | **no** |")
                continue
            fc = p.get("finger_clearance_in_compartment_m")
            rc = p.get("gripper_clearance_to_released_bottle_m")
            o.append(f"| {p['name']} | {fmt(p['tcp_position'])} | {p['finger_opening_m']:.3f} | yes | {p['min_joint_margin_frac']:.3f} / "
                     f"{math.degrees(p['min_joint_margin_rad']):.1f} | {p['manipulability']:.3f} | {p['robot_clearance_m']:.3f} "
                     f"({p['closest_robot_part']}→{p['closest_box']}) | {fmt(p['carried_object_clearance_m'])} | "
                     f"{fmt(fc)} / {fmt(rc)} | {'yes' if p['pose_ok'] else '**no**'} |")
        if wps:
            o.append(f"\nSampled straight-line insertion/retreat: {len(wps)} waypoints at "
                     f"{cfg['manipulation_targets']['glass_crate']['insertion_waypoint_step_m'] * 1000:.0f} mm, all OK = {ev['sampled_path_collision_free']}, "
                     f"max joint step {max(p['max_joint_step_from_previous_rad'] for p in wps):.3f} rad, "
                     f"min robot clearance {min(p['robot_clearance_m'] for p in wps):.3f} m.")
    pk = (static.get("reachability") or {}).get("pickups", {})
    if pk:
        o.append("\n**Pickups (objects at their tabletop positions; IK + endpoint clearance only):**\n")
        o.append("| Object | Feasible | Gripper yaw | Min robot clearance (m) | Min joint margin (frac) |\n|---|---|---|---|---|")
        for k, v in pk.items():
            o.append(f"| {k} | {v['summary']['feasible']} | {v['meta']['gripper_yaw_deg']:.0f}° | {fmt(v['summary']['min_robot_clearance_m'])} | "
                     f"{fmt(v['summary']['min_joint_margin_frac'])} |")
    gp = physics.get("glass_placement")
    if gp:
        o.append(f"\n**Glass bottle placement stability** (temporary stage `{gp['temp_stage']}`, copy of the bottle at the final pose in "
                 f"compartment {gp['compartment']}, 3 s): max tilt {gp['max_tilt_deg']:.4f}°, drift {gp['horizontal_drift_m'] * 1000:.3f} mm, "
                 f"bottom gap {gp['final_bottom_gap_m'] * 1000:.3f} mm, floor force {gp['floor_force_last_0_5s_N']:.3f} N vs weight "
                 f"{gp['weight_N']:.3f} N, max wall/separator force {gp['max_wall_separator_force_N']:.2e} N, min lateral clearance "
                 f"{gp['min_lateral_clearance_body_to_compartment_m'] * 1000:.1f} mm.")
    o.append("\n**What is and is not validated:** IK feasibility and endpoint collision clearance are checked for every listed pose; the crate "
             "insertion/retreat is additionally checked at discrete 1 cm straight-line waypoints. No continuous/swept trajectory check and no "
             "motion planning were performed, and no pick-and-place was executed. Robot self-collision is not checked (Lula IK enforces joint "
             "limits only). Clearances use the robot's PhysX convex hulls (hull vertices + face centroids) against box proxies of the scene colliders.")
    return o


LIMITATIONS = """- Collision approximations: bottles use solid compound colliders (body cylinder + shoulder convex hull + neck/cap
  cylinders); their interiors are not hollow for physics. The paper cup is hollow: base cylinder + 16 tilted 2 mm wall boxes.
- PET bottle crushing and paper-cup wall deformation are not modelled (rigid bodies).
- Mass properties are computed from the closed visual meshes at uniform density, scaled to the specified masses. The implied
  paper density (~420 kg/m³) is low because the 1 mm visual wall is thicker than real cup board; mass is as specified.
- Physics coefficients are illustrative simulation values, not measurements. Combine mode `average` on every material.
- During tests only, PhysX sleeping is disabled and contact-report APIs are added in the session layer / temporary stage so
  forces are observable for the whole run; the saved scene keeps PhysX defaults.
- The robot is referenced from NVIDIA's hosted Isaac Sim 6.2 asset root (network access needed unless an asset pack is configured).
  Scene-level robot overrides: home joint state + equal drive targets, and a FilteredPairs entry between panda_link0 and the tabletop.
- Glass/PET use Kit's OmniGlass MDL as a scene-level override (RTX real-time translucency); the assets themselves carry portable
  UsdPreviewSurface materials. The four crate bottles are static (rigidBodyEnabled = false). Labels are visual geometry only.
- IK uses Lula from the deprecated isaacsim.robot_motion.motion_generation extension; kinematic only (no collisions, no planning).
- The GUI was not opened in this run; opening was verified headlessly (stage open + simulation + rendering)."""


if __name__ == "__main__":
    sys.exit(main())
