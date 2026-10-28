# Portability and Git

## Stages and their requirements

| Stage | Tools | GPU | Network | Output |
|---|---|---|---|---|
| 1. Generate assets | Blender 5.2 (+ FreeCAD 1.1, optional, for the `freecad` backend and STEP imports) | no | no | `assets/workstation/*`, `assets/library/<id>/*` (+ `<id>.step`) |
| 2a. Build the base scene | Isaac Sim 6.2 | needs the Isaac runtime (RTX GPU) | **yes** (Franka URL), unless a local asset root is set | `assets/scenes/waste_sorting_workstation.usd` |
| 2b. Compose derived scenes | Blender **or** Isaac (`pxr` only) | no | no | `assets/scenes/derived/*.usda` |
| 3. Open/run in Isaac Sim (GUI, previews) | Isaac Sim 6.2 | RTX GPU (+ display for GUI) | yes (robot) | — |
| 4. Physics validation | Isaac Sim 6.2, PhysX on the CPU | Isaac needs a GPU to start, but the physics runs on the CPU | yes (robot) | logs |
| Motion experiment | Isaac Sim 6.2 + cuMotion extension | yes (~1.4–2.4 GB peak measured) | yes | `logs/motion_planning/` |

Stages 1 and 2b need no NVIDIA software, so assets and derived scenes can be produced on a machine without a GPU and
validated elsewhere.

## Cloning onto another machine

```bash
git clone git@github.com:vahidlbf/robotic-asset-generation-framework.git
cd robotic-asset-generation-framework
scripts/check_environment.sh                       # read-only dependency check
export ISAACSIM_PYTHON=/opt/isaacsim/python.sh     # wherever Isaac Sim 6.2 is installed
export BLENDER=blender
python3 scripts/assets/asset_lib.py selftest       # no Omniverse needed
scripts/motion_planning/run_regression.sh          # reproduce 94/94 + 39/39 + GUI self-test on the tracked scene
```
The tracked USD files make a clone usable without regenerating anything. To regenerate everything, run
`python3 scripts/workstation/run_workflow.py`. Expect visual-USD byte differences (see below); geometry and validation
results should be unchanged.

## Environment variables

| Variable | Default | Used by |
|---|---|---|
| `ISAACSIM_PYTHON` | `$ISAACSIM_PATH/python.sh`, else `~/isaacsim/python.sh` | `run_workflow.py`, `run_regression.sh`, `add_asset.py`, `negative_control.py` |
| `ISAACSIM_PATH` | `~/isaacsim` | same (fallback) |
| `BLENDER` | `blender` | `run_workflow.py`, `add_asset.py` |
| `FREECAD_EXECUTABLE` | `freecadcmd` on PATH, else the newest `~/Applications/FreeCAD*.AppImage` | `backends.py` (`generate_asset.py`, `check_environment.sh`); optional |

## Tracked vs. generated files

| Tracked (needed to reproduce or open) | Generated, git-ignored |
|---|---|
| `scripts/`, `config/` (incl. schemas, asset specs, scene configs), `docs/`, `AGENTS.md`, `CLAUDE.md`, `README.md` | `__pycache__/`, `assets/library/*.tmp/` |
| `assets/workstation/**`, `assets/library/**`, `assets/scenes/**` (generated, but tracked: ~1.1 MB, needed to open the scene, not byte-reproducible) | raw `*.log`, CSV trajectories, `logs/workstation/*` except the reports, `logs/assets/*/base_suites/*` except the previews, the ramp-regression sandbox |
| reports: `logs/workstation/validation_report.md`, `validation_results.json`, `scene_inventory.json`, `visual_inspection.md`, `preview_*.png`; `logs/motion_planning/**/*.{md,json,png}`; `logs/assets/**/*.{md,json}` | |

The total tracked size is about 10 MB (142 files, measured with `git ls-files --others --exclude-standard` on
2026-10-27 after the industrial brass-sorting scene was added). The largest files are the preview PNGs
(0.4–0.75 MB) and the Type B fitting visual mesh (0.57 MB). The library assets total 1.3 MB.

**Why the generated USD is tracked.** Regenerating all workstation assets into a scratch directory (2026-10-27)
reproduced the physics USD and the manifest byte for byte. Five of the nine Blender visual files differed in bytes,
although their mesh points were identical: the UVs differed by at most 1.2e-7 and the prim order differed. Tracking
the files pins exactly what was validated.

**Git LFS:** not needed at the current size (no file is larger than 1 MB, measured again for the 10 MB state; `git lfs` is not installed here). Consider
it if textures, `.blend` files, path-traced renders or larger meshes are added: `*.usdc`, `*.png`, `*.blend` and
`*.glb` above a few MB. `_visual.usd` files are binary but small.

## Repository layout

Since 2026-10-28 this directory is an **independent Git repository** (`main`, remote
`origin = git@github.com:vahidlbf/robotic-asset-generation-framework.git`, private). On the original machine it
still sits inside `robot-agent-lab/`, whose own repository (no commits, no remote) was not changed. Implications of
the nested layout:
- **Two separate repositories:** Git commands run inside this directory only affect this repository. Commands run
  in `robot-agent-lab/` see `waste-sorting-workstation/` as an untracked nested repository.
- **Don't add it from the parent:** `git add waste-sorting-workstation` in the parent would record a gitlink (a
  submodule-like pointer without a `.gitmodules` entry), not the files. If the parent ever gets committed, add
  `waste-sorting-workstation/` to the parent `.gitignore`, or register it as a proper submodule.
- **Parent checks are conditional:** `run_workflow.py`, `run_regression.sh` and `add_asset.py` check the parent ramp
  project only when `../scripts/run_pipeline.py` exists. A standalone clone, whose parent directory is unrelated,
  skips them; `run_workflow.py` then reports criterion 14 (ramp project functional) as not met. Earlier versions
  would have hashed the whole parent directory.

## Testing on another Isaac Sim version (not supported yet)

Only Isaac Sim 6.2.0 has been validated. A different version would need these rechecked: the robot asset path and
its variants (`Isaac/<version>/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd`, `Gripper`, `Mesh`), the
`isaacsim.core.experimental.*` and `simulation_manager` APIs used by every Isaac script, the Lula robot description
paths in `config/waste_sorting_environment.json` (`robot.ik`), cuMotion (`isaacsim.robot_motion.cumotion`), the
renderer setting (`RealTimePathTracing`), contact-report readback (`RigidPrim.get_contact_force_matrix`), and the
GUI picking-mode setting. Run, in order: `check_environment.sh`, `run_regression.sh`, `validate_asset_scene.py` on
both derived scenes, `open_scene.py --self-test`, and the motion experiment. The base scene would have to be rebuilt
(`build_scene.py`) if the robot asset path changes.

## Remaining absolute and environment-specific references

| Where | Value | Why it stays |
|---|---|---|
| `assets/scenes/waste_sorting_workstation.usd` (robot reference, customLayerData) | `https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.2/…/franka.usd` | the official NVIDIA asset, resolved by `get_assets_root_path()` at build time; tied to Isaac Sim 6.2 and network access |
| derived scenes' `customLayerData.robot_asset` | same URL (informational copy) | read by `validate_scene.py` |
| `logs/motion_planning/gui/validation_results.json` | `/home/mm42/…/gui_hold_*.png` | written before the screenshot paths were made relative; historical result, not rewritten |
| `logs/workstation/validation_results.json`, `validation_report.md`, `logs/motion_planning/*console*` | commands with `/home/mm42/isaacsim/python.sh` | recorded command lines of past runs (the report template now writes `"$ISAACSIM_PYTHON"`) |
| `logs/assets/*/add_asset_report.{json,md}` (stage commands) | the resolved Isaac interpreter path, e.g. `/home/mm42/isaacsim/python.sh` | `add_asset.py` records the command it actually ran; a run on another machine records that machine's path |
| `OmniGlass.mdl` (base scene) | resolved through Kit's MDL search path | only works in Kit/Isaac Sim; other USD viewers fall back to the asset's `UsdPreviewSurface` |

None of the scripts or configs contain a hardcoded user path.

## Version-sensitive APIs

- **Isaac Sim 6.2:**
  - `isaacsim.core.experimental.*` (prims, utils.app, utils.stage)
  - `isaacsim.core.simulation_manager`
  - `isaacsim.storage.native.get_assets_root_path`
  - `isaacsim.robot_motion.cumotion` + `isaacsim.robot_motion.experimental.motion_generation`
  - Lula from the deprecated `isaacsim.robot_motion.motion_generation`, which the IK checks use
- **Robot asset and renderer:** the Franka asset path `Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd` with
  variants `Gripper=Default` and `Mesh=Performance`. The renderer setting is `RealTimePathTracing`.
- **FreeCAD 1.1.4 (optional):** `Part` (makeCylinder/makeCone/makeChamfer/extrude/revolve/booleans,
  `optimalBoundingBox`, `exportStep`), `MeshPart.meshFromShape`, `freecadcmd` console mode of the AppImage.
  Other versions are untested: rerun `build_cad_comparison.sh` and `compare_backends.py` and compare
  `asset_info.json` → `cad` and `logs/assets/backend_comparison/comparison.json`.
- **Blender 5.2:** `bpy.ops.wm.usd_export` options, the Principled BSDF input names and the bundled `pxr`. The
  Smooth-by-Angle modifier is unavailable with `--factory-startup` and is silently skipped by `mesh_object`.
- **Snap Blender:** it can't write to a redirected file descriptor, so the orchestrators pipe its output through Python.

## GPU considerations

- **Physics:** runs on the CPU (`gpu_dynamics: false`), so results don't depend on the GPU model.
- **Isaac Sim still needs an RTX GPU:** it is required to start the app and to render.
- **Memory measured on an RTX A2000 12 GB:** workstation workflow ≈ 1.5 GB peak, motion experiment 1.4–2.4 GB
  (`nvidia-smi` measures the whole GPU).
- **Previews:** these use real-time RTX; offline path tracing is refused by project policy.
- **Not tested:** other GPUs, drivers and headless servers without a display; on those, the GUI self-test and GUI
  modes need a display.
