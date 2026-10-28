# Agent handoff

State as of 2026-10-28. This directory is an independent Git repository (`main`, remote
`git@github.com:vahidlbf/robotic-asset-generation-framework.git`, private). The first commit contains the state
described here; `git log` shows later changes. The parent `robot-agent-lab/` repository (no commits) was not
changed.

## Project state

| Area | State | Where to look |
|---|---|---|
| Workstation scene | FULLY VALIDATED, 94/94 static and 39/39 dynamic; unchanged since 2026-10-26 (hash-verified) | `logs/workstation/validation_report.md` |
| Sorting-zone layout + target poses | final; written into the config by `optimize_layout.py --apply` | config `manipulation_targets.selected`, `/World/Targets/*` |
| GUI physics tooling | PASS (base and derived scenes) | `open_scene.py --self-test` |
| Motion home → PET pre-grasp → home | FULL SUCCESS (rerun 2026-10-27) | `logs/motion_planning/planning_report.md` |
| Incremental assets | working; demo asset `test_spacer`, scene `workstation_test_spacer` (54/54 with the current validator) | `logs/assets/workstation_test_spacer/add_asset_report.md` |
| Geometry backends | Blender (default) / FreeCAD / import; `brass_adapter_male_cad` (FreeCAD, STEP) and `brass_adapter_male_step_import`; scene `brass_cad_comparison` 76/76 + 94/94 + 39/39 | `docs/GEOMETRY_BACKENDS.md`, `logs/assets/brass_cad_comparison/` |
| Industrial brass sorting | 6 library assets, scene `industrial_brass_sorting` (12 instances); 238/238 targeted checks, GUI self-test PASS, previews inspected; top-down grasps 0/7 feasible (hand vs. 0.10 m tray walls / neighbours) | `logs/assets/industrial_brass_sorting/experiment_report.md`, `reachability.md` |

## Entry points

- **Start here:** `AGENTS.md` (rules, commands) → `docs/ARCHITECTURE.md`.
- **New objects:** `scripts/assets/add_asset.py`, `scripts/assets/asset_lib.py` (CLI), `config/assets/*.json`,
  `config/scenes/*.json` → `docs/ADD_NEW_ASSET.md`. A multi-asset example is `scripts/assets/build_industrial_scene.sh`.
- **Workstation changes:** `config/waste_sorting_environment.json` + `scripts/workstation/run_workflow.py`. This
  regenerates **all** assets and the scene.
- **Regression without rebuilding:** `scripts/motion_planning/run_regression.sh`.
- **Motion:** `scripts/motion_planning/run_motion_experiment.py [--headless]`.

## Safe modification boundaries

| Freely | With care (rerun the listed checks) | Not without explicit instruction |
|---|---|---|
| new `config/assets/*.json`, `config/scenes/*.json`, library assets, derived scenes, docs | generator/composer/validator code in `scripts/assets/` (`asset_lib.py selftest`, `run_demo.sh`); shared helpers in `generate_assets.py` (scratch regeneration + byte compare, as in VALIDATION.md) | the base scene, `assets/workstation/*`, robot mounting, home pose, sorting-zone layout, physics values in the environment config, the Franka reference, the parent `robot-agent-lab/` project, git commits/pushes, installs/sudo |

## Resuming after cloning onto a new machine

```bash
git clone git@github.com:vahidlbf/robotic-asset-generation-framework.git && cd robotic-asset-generation-framework
export ISAACSIM_PYTHON=/path/to/isaacsim/python.sh BLENDER=/path/to/blender
scripts/check_environment.sh                                  # tools, GPU, robot URL, files, selftest, asset status
"$ISAACSIM_PYTHON" scripts/assets/validate_asset_scene.py --scene config/scenes/industrial_brass_sorting.json   # 238 checks
scripts/motion_planning/run_regression.sh                     # original workstation: 94 + 39 + GUI self-test (display)
```
- **Unchanged clone:** the validation should reproduce the recorded results. A difference means the environment
  differs (versions, GPU, network); record it before changing code.
- **Ramp project absent:** the clone has no parent ramp project, so its checks are skipped (see PORTABILITY.md).

## Recommended workflow

1. Run `python3 scripts/assets/asset_lib.py selftest` and `python3 scripts/assets/asset_lib.py list` to see the state.
2. Make the change in the smallest layer that can hold it (asset spec → scene config → generator code).
3. Run the targeted pipeline (`add_asset.py … --base-suites`) and read the reports, not just the exit codes.
4. If shared code changed, run `run_regression.sh`, and the motion experiment if motion-related code changed.
5. Compare protected files by hash, as `add_asset.py` does.
6. Report the numbers, failures and untested parts. Commit and push only when the user asks; never force-push.

## Known issues

- **FreeCAD backend (optional):**
  - builders exist for `fitting` only;
  - threads are cosmetic (plain cylinders), so CAD parts are heavier than Blender parts;
  - STEP imports get solid colliders;
  - `<AppImage> --version` opens the FreeCAD GUI, so never use it for detection;
  - tested only with FreeCAD 1.1.4. See `docs/GEOMETRY_BACKENDS.md`.

- **Asset status covers the spec only:** status is `current` as long as the spec hash and files match. A change to
  the generator code is not detected, so rebuild the affected assets with `generate_asset.py --force`, as was done
  for the containers after the triangulation and floor-box changes.
- **Industrial scene, not validated:** the workstation suites (`--base-suites`) were not run on it, because it
  deactivates the waste-sorting objects they check. Its top-down grasps are infeasible for the Franka hand in the
  0.10 m-deep tray; see `reachability.md`.
- **Container colliders:** interior corners are sharp while the visual is rounded; the hand holes are visual only;
  a 2 cm contact offset is set on the crate and tray colliders.

- **Settle start point:** `run_physics_test.py` settle checks measure Δz from a sample taken after `play()` has
  already advanced physics. The check is weaker than intended but its result is valid. See VALIDATION.md.
- **Smooth-by-Angle:** `generate_assets.mesh_object`'s modifier is unavailable under `--factory-startup` and
  silently skipped, so workstation meshes are smooth-shaded everywhere. This is visual only. Library assets use
  `generate_asset.sharpen()` instead. Changing the workstation helper would change validated visual files.
- **Not byte-reproducible:** regenerating workstation visual USD is not byte-identical (UV float noise, prim order),
  which is why the generated files are tracked.
- **Empty leftover directories:** `assets/glass_bottle`, `assets/glass_crate`, `assets/paper_bin`, `assets/paper_cup`,
  `assets/plastic_bin`, `assets/plastic_bottle` and `assets/table` (directly under `assets/`) are empty and
  unused. They are left in place; remove them with `rmdir` if wanted.
- **Robot asset:** it is fetched over https from NVIDIA's Isaac Sim 6.2 asset root (network needed) and its
  redistribution terms were not verified, so it is referenced, never copied.
- **Discrete collision checks only:** no swept collision checking anywhere. PhysX self-collision is disabled in the
  official Franka asset, so self-collision is checked only by cuMotion's sphere model.
- **Rigid approximations:** solid bottle colliders, no deformation, illustrative friction.
- **Not built:** grasping, pick-and-place, perception and ROS 2 are not implemented.

## Detailed reports

| Report | Path |
|---|---|
| Workstation | `logs/workstation/validation_report.md`, `validation_results.json`, `visual_inspection.md`, `preview_*.png` |
| Motion | `logs/motion_planning/planning_report.md`, `validation_results.json`, `collision_report.json`, `gui/` |
| Incremental assets | `logs/assets/<scene_id>/add_asset_report.md`, `validation_report.md`, `compose.json`, `base_suites/preview_*.png`; `logs/assets/negative_control/` |
| Asset metadata | `assets/library/<id>/asset_info.json`, `assets/library/registry.json`, `assets/workstation/asset_manifest.json` |
