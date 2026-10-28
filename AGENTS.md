# AGENTS.md — waste-sorting workstation

Entry point for AI coding agents (Claude Code, OpenCode/Qwen, …). Read this first, then the linked docs.
All paths are relative to this directory (`waste-sorting-workstation/`). Units: metres, kilograms, seconds,
degrees for angles in configs. World: Z up. Asset origins: bottom centre (tabletop: geometric centre).

## Project identity

A physics-enabled robotic waste-sorting workstation for NVIDIA Isaac Sim 6.2, generated procedurally:
lab table, the official NVIDIA-hosted Franka Panda, a glass bottle, a PET bottle, a paper cup, PAPER and PLASTIC
bins, a glass crate on a cabinet platform, and a library of add-on assets placed into derived scenes.

| Capability | Status / evidence |
|---|---|
| Workstation assets (Blender) + scene (Isaac USD) | `logs/workstation/validation_report.md`: FULLY VALIDATED, 94/94 static, 39/39 dynamic checks |
| GUI physics consistency (model picking, RigidBodyGuard) | `open_scene.py --self-test` PASS |
| Robot-aware sorting-zone layout (Lula IK + endpoint collision clearance) | static `layout.*` / `reachability.*` checks |
| First robot motion home → PET pre-grasp → home (cuMotion, PhysX) | `logs/motion_planning/planning_report.md`: FULL SUCCESS |
| Incremental assets: spec → one asset → derived scene → targeted validation | `logs/assets/workstation_test_spacer/add_asset_report.md`: PASS (53/53 targeted at the time, 54/54 with the current validator; 94/94 + 39/39 on the derived scene) |
| Industrial brass-sorting scene (crate, tray, 2 brass fittings, labels; 12 instances) | `logs/assets/industrial_brass_sorting/experiment_report.md`: 238/238 targeted checks, GUI self-test PASS, previews inspected; **top-down grasps 0/7 feasible** (geometric reachability) |

Not implemented / not validated: grasping, pick-and-place, perception, ROS 2 / MoveIt 2, continuous (swept)
collision checking, deformable PET/paper, measured friction values. Known issues: [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md#known-issues).

## Architecture in one picture

```
config/*.json ──► Blender (generate_assets.py | assets/generate_asset.py) ──► assets/workstation/* | assets/library/<id>/*
                                                                              │ relative USD references
config/waste_sorting_environment.json ──► Isaac (build_scene.py) ──────────► assets/scenes/waste_sorting_workstation.usd  (base, validated)
config/scenes/<id>.json ──► compose_scene.py (any pxr: Blender or Isaac) ───► assets/scenes/derived/<id>.usda  (sublayers the base)
validation: validate_scene.py, run_physics_test.py, open_scene.py --self-test, validate_asset_scene.py, motion_planning/*
```
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Formats: [docs/ASSET_FORMATS.md](docs/ASSET_FORMATS.md).
Physics: [docs/PHYSICS_AND_COLLISION.md](docs/PHYSICS_AND_COLLISION.md). Tests: [docs/VALIDATION.md](docs/VALIDATION.md).

## Directory map

| Path | Contents |
|---|---|
| `config/waste_sorting_environment.json` | single source of truth for the workstation (dimensions, poses, physics, cameras, layout, targets) |
| `config/motion_planning.json` | motion experiment parameters |
| `config/assets/<id>.json` | **asset definitions** (A) for library assets, schema `config/schemas/asset_spec.schema.json` |
| `config/scenes/<id>.json` | **derived-scene configs + instances** (C/D), schema `config/schemas/scene_instances.schema.json` |
| `scripts/workstation/` | workstation pipeline: generate, build, validate, physics test, previews, GUI, layout optimiser |
| `scripts/assets/` | incremental-asset tooling (stdlib library/CLI, Blender generator, composer, validator, orchestrator) |
| `scripts/motion_planning/` | cuMotion plan + PhysX execution experiment and its regression wrapper |
| `assets/workstation/<name>/` | generated workstation assets (`<name>.usd` physics asset + `<name>_visual.usd`), `asset_manifest.json` |
| `assets/library/<id>/` | generated library assets (B) + `asset_info.json`; `assets/library/registry.json` (derived) |
| `assets/scenes/waste_sorting_workstation.usd` | the validated base scene (built by `build_scene.py`) |
| `assets/scenes/derived/<id>.usda` | derived scenes (thin layers over the base): `workstation_test_spacer`, `industrial_brass_sorting` |
| `assets/glass_bottle/`, `assets/table/`, … (directly under `assets/`) | **empty leftover directories** from an earlier layout; nothing reads or writes them |
| `logs/workstation/`, `logs/motion_planning/`, `logs/assets/<scene_id>/` | reports, results JSON, previews (raw logs/CSVs are git-ignored) |
| `docs/` | detailed documentation |

## Verified commands

Set the tool locations once ([docs/INSTALLATION.md](docs/INSTALLATION.md)); defaults shown:
```bash
export ISAACSIM_PYTHON=~/isaacsim/python.sh     # or ISAACSIM_PATH=<isaac sim dir>
export BLENDER=blender                          # Blender 5.2 executable
```
| Task | Command | Needs |
|---|---|---|
| Check the environment (read-only) | `scripts/check_environment.sh` | python3 (+ reports Blender / Isaac / GPU) |
| Everything (regenerate + validate + report) | `python3 scripts/workstation/run_workflow.py` | Blender, Isaac, GPU |
| Generate workstation assets only | `$BLENDER -b --factory-startup --python-exit-code 1 --python scripts/workstation/generate_assets.py -- --config config/waste_sorting_environment.json` | Blender |
| Build the base scene | `"$ISAACSIM_PYTHON" scripts/workstation/build_scene.py` | Isaac (+ network for the robot) |
| Static validation (94 checks) | `"$ISAACSIM_PYTHON" scripts/workstation/validate_scene.py` | Isaac |
| Physics tests (39 checks) | `"$ISAACSIM_PYTHON" scripts/workstation/run_physics_test.py` | Isaac |
| Regression without rebuilding | `scripts/motion_planning/run_regression.sh` | Isaac |
| Previews | `"$ISAACSIM_PYTHON" scripts/workstation/render_previews.py [--cameras main top]` | Isaac, RTX GPU |
| Open the GUI | `"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py [--play] [--scene assets/scenes/derived/<id>.usda]` | Isaac, display |
| **Add one asset** | `python3 scripts/assets/add_asset.py --spec config/assets/<id>.json --scene config/scenes/<scene>.json [--base-suites] [--preview]` | Blender, Isaac |
| Add several assets at once | `python3 scripts/assets/add_asset.py --spec <a>.json --spec <b>.json … --scene config/scenes/<scene>.json [--preview]` | Blender, Isaac |
| Edit instances | `python3 scripts/assets/asset_lib.py add-instance\|move-instance\|remove-instance\|scatter\|deactivate-base-prim\|set-preview-camera\|set-validation config/scenes/<scene>.json …` | python3 only |
| Geometric reachability (IK + endpoint clearance) | `"$ISAACSIM_PYTHON" scripts/assets/reachability_check.py --scene <scene>.json --pick-support <tray> --drop <prefix>=<container> …` | Isaac |
| Full incremental demo | `scripts/assets/run_demo.sh` | Blender, Isaac |
| Industrial brass-sorting scene | `scripts/assets/build_industrial_scene.sh`; open: `"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/industrial_brass_sorting.usda` | Blender, Isaac |

Never run Omniverse/pxr code with system `python3` (no `pxr`, no `numpy` there); use `$ISAACSIM_PYTHON` or Blender.

## Rules for agents

1. **Inspect before editing.** Read the script and its config keys; do not infer behaviour from file names.
2. **Reuse** `generate_assets.py` helpers (`lathe`, `box_object`, `mesh_object`, `material`, `mass_properties`,
   `write_asset`), `asset_lib.py` (paths, specs, registry, placement), `layout_geometry.scene_paths`.
3. **Preserve validated state.** Do not change `config/waste_sorting_environment.json` layout/robot/physics values,
   the base scene, the Franka reference, or the sorting-zone layout unless the task is explicitly about them.
4. **Do not regenerate unrelated assets.** Add objects as library assets + derived scenes. `run_workflow.py` and
   `generate_assets.py` rebuild *all* workstation assets — run them only when the workstation itself changes.
5. **USD integrity:** relative asset paths only (`./`, `../`), metric units, Z up, `defaultPrim` set, colliders
   `purpose = guide`, physics material bound with `physics` purpose, one rigid body per asset root.
6. **Validate artefacts** with the matching script and read the numbers; a written file is not a result.
7. **Never fabricate or round up validation results.** Report failures with their log lines.
8. **No system changes:** no sudo, no installs, no driver changes, nothing outside this directory (the parent
   `robot-agent-lab/` ramp project must stay untouched, where it exists). **Never commit or push unless the user
   asks**, never force-push, never rewrite history. This directory is its own Git repository (`main` →
   `origin` = `git@github.com:vahidlbf/robotic-asset-generation-framework.git`, private).

## Safe procedure for a new asset (summary of [docs/ADD_NEW_ASSET.md](docs/ADD_NEW_ASSET.md))

1. Write `config/assets/<id>.json`; check it: `python3 scripts/assets/asset_lib.py validate-spec config/assets/<id>.json`.
2. Prefer an existing method: `box`, `cylinder`, `tube`, `open_container` (crates/trays), `fitting` (turned parts:
   cylinders, cones, hex, visual threads, stepped bore; a hex nut is a fitting) or `label_plate`. A genuinely new
   shape needs a builder in `generate_asset.py:build_geometry`, the parameters in `asset_lib.METHOD_PARAMS`, the
   schema enum, `nominal_size` / `spec_errors` / `collider_pieces` and `mesh_checks` support.
   Generator code changes do not mark assets stale (only spec changes do): rebuild affected assets with `--force`.
3. Create/edit the scene config with `asset_lib.py new-scene / add-instance / scatter` (the collider-based placement
   pre-check runs; parts can rest `on_instance` of a container, labels are `attached` to mount points).
4. `python3 scripts/assets/add_asset.py --spec … --scene … --base-suites --preview` → read
   `logs/assets/<scene_id>/add_asset_report.md` and `validation_report.md`; look at the preview PNG.
5. Optional GUI check: `"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/<id>.usda --self-test`.
6. Report what passed, what failed, and what was not tested. Commit only when the user asks.

## Resuming on a new machine

1. Clone it and set the tool locations as in [docs/INSTALLATION.md](docs/INSTALLATION.md). Then run
   `scripts/check_environment.sh` and read every FAIL/warn line.
2. Read [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md) for the current state and known issues. `git log` shows what
   changed since.
3. Before changing shared code, rerun the cheap checks: `python3 scripts/assets/asset_lib.py selftest` and
   `python3 scripts/assets/asset_lib.py list`, where every asset should be `current`.
4. With Isaac Sim available, rerun the targeted validation of the scene you work on before and after your change.
5. Don't regenerate tracked assets unless the task needs it. Rebuilds are not byte-identical; `git diff --stat`
   shows what changed.

Resuming work: [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md). Cloning elsewhere: [docs/PORTABILITY.md](docs/PORTABILITY.md).
