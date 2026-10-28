# Installation and environment

Nothing in this project installs software. It uses three external tools, located through environment variables.
All commands below run from the repository root (the directory containing `AGENTS.md`). Every script finds the
project from its own location, so they also work from other directories.

## 1. Clone

The repository is private. You need an SSH key registered with a GitHub account that has access to it.
```bash
ssh -T git@github.com                       # should greet your GitHub user
git clone git@github.com:vahidlbf/robotic-asset-generation-framework.git
cd robotic-asset-generation-framework
```
The clone already contains every generated USD asset and scene, so nothing has to be regenerated to open the
scenes. Empty leftover directories from an earlier layout (`assets/glass_bottle/`, …) are not tracked, so they do
not exist in a clone. Nothing uses them.

## 2. Tested configuration

| Component | Tested version | Needed for |
|---|---|---|
| OS | Ubuntu 22.04.5 (Linux 6.8) | everything (other Linux distributions are untested) |
| System Python | 3.10, **standard library only** | orchestration (`run_workflow.py`, `add_asset.py`), `asset_lib.py`, `check_environment.sh` |
| Blender | 5.2.2 LTS (snap, `/snap/bin/blender`) | asset geometry + asset USD; Isaac-free scene composition |
| FreeCAD (**optional**) | 1.1.4 AppImage (`FreeCAD_1.1.4-Linux-x86_64-py311.AppImage`, Python 3.11) | only the `freecad` geometry backend and STEP imports ([GEOMETRY_BACKENDS.md](GEOMETRY_BACKENDS.md)) |
| NVIDIA Isaac Sim | 6.2.0 (`6.2.0-rc.14+release.52805`), standalone install with `python.sh` | scene build, validation, physics, previews, GUI, motion planning |
| GPU / driver | 1 × RTX A2000 12 GB, driver 595.99 | Isaac Sim (RTX rendering); physics runs on the CPU (`gpu_dynamics: false`) |
| Network | access to `omniverse-content-production.s3-us-west-2.amazonaws.com` | the Franka robot asset (unless a local Isaac asset root is configured) |
| Git | 2.34 | cloning / updating; Git LFS is **not** needed |

- **Blender:** install 5.2.x yourself, for example `sudo snap install blender --classic` or the official tarball,
  so that `blender --version` prints `Blender 5.2.x`. The scripts use Blender's bundled `pxr`, `numpy` and
  `bmesh`; other major versions may change the USD exporter options and the Principled BSDF input names.
- **Isaac Sim:** install Isaac Sim **6.2.0** (standalone/workstation install) with NVIDIA's own instructions and
  accept its licence. Only 6.2 is supported: the scripts use 6.2 APIs (`isaacsim.core.experimental.*`,
  `isaacsim.core.simulation_manager`, cuMotion) and the 6.2 robot asset path.
- **Python packages:** system Python needs none. Blender ships `numpy` and `pxr`; Isaac Sim ships `numpy`, `pxr`,
  `scipy`, `warp` and the `isaacsim.*` extensions. `jsonschema` is not required: `asset_lib.py` has its own
  schema-subset validator.
- **Other hardware:**
  - **2 × RTX 3090 (untested):** physics runs on the CPU and the previews render with RTX real-time, so one GPU is
    used. `CUDA_VISIBLE_DEVICES=0` (the standard CUDA variable) restricts the visible GPUs if needed. This has not
    been tested with this project.
  - **Optional tools:** a display (GUI only) and `nvidia-smi` (GPU memory sampling; the scripts tolerate its
    absence).

## 3. Environment variables

```bash
export ISAACSIM_PYTHON=/path/to/isaacsim/python.sh   # or: export ISAACSIM_PATH=/path/to/isaacsim
export BLENDER=/path/to/blender                      # default: "blender" on PATH
export FREECAD_EXECUTABLE=/path/to/FreeCAD.AppImage  # optional; default: freecadcmd on PATH, else ~/Applications/FreeCAD*.AppImage
```
FreeCAD is only needed for assets whose backend resolves to `freecad` or that import a STEP file. Never run
`<FreeCAD AppImage> --version`: it starts the GUI. `scripts/check_environment.sh` reports the version through
`freecadcmd`. Without FreeCAD, every Blender-route asset works unchanged, and a spec that needs FreeCAD fails its
backend selection with a clear message. Nothing is silently replaced.
- **Resolution order** (`scripts/assets/asset_lib.py:isaac_python`, `run_workflow.py`, `run_regression.sh`,
  `check_environment.sh`): `$ISAACSIM_PYTHON` → `$ISAACSIM_PATH/python.sh` → `~/isaacsim/python.sh`. Script
  docstrings write `"$ISAACSIM_PYTHON"`.
- **Making them permanent:** put the two `export` lines in `~/.bashrc`.
- **No other variables:** no project path, user name or machine name is configured anywhere.

## 4. Check the installation

```bash
scripts/check_environment.sh                                 # read-only: versions, GPU, robot URL, files, selftest
"$ISAACSIM_PYTHON" -c "print('isaac python ok')"             # the interpreter starts
```
`check_environment.sh` exits non-zero if a required tool or file is missing; version differences are only
warnings. Expected output on the tested machine: `environment check: OK`.

## 5. Asset generation

| What | Command | Writes |
|---|---|---|
| Spec / scene / placement unit tests (python3 only) | `python3 scripts/assets/asset_lib.py selftest` | nothing |
| Check one spec | `python3 scripts/assets/asset_lib.py validate-spec config/assets/brass_adapter_male.json` | nothing |
| Which backend would build a spec (no build) | `python3 scripts/assets/backends.py select config/assets/brass_adapter_male_cad.json` | nothing |
| Side-by-side comparison scene (4 variants) | `scripts/assets/build_backend_comparison.sh` | `brass_backend_comparison` scene, `logs/assets/brass_backend_comparison/` |
| Measured Blender-vs-CAD comparison + renders (FreeCAD needed) | `python3 scripts/assets/compare_backends.py` | `logs/assets/backend_comparison/`, `docs/images/cad_comparison/` |
| CAD backend comparison scene (FreeCAD needed) | `scripts/assets/build_cad_comparison.sh` | the two CAD variants (if not current), `brass_cad_comparison` scene, `logs/assets/brass_cad_comparison/` |
| Generate one library asset (skipped when current) | `"$BLENDER" -b --factory-startup --python-exit-code 1 --python scripts/assets/generate_asset.py -- --spec config/assets/brass_adapter_male.json` | `assets/library/<id>/` only if not current |
| Rebuild one asset | the same with `--force` | that asset's files (+ `registry.json`) |
| Incremental demo (spacer) | `scripts/assets/run_demo.sh` | `test_spacer` files, its scene config/layer, `logs/assets/` |
| Industrial brass-sorting scene | `scripts/assets/build_industrial_scene.sh` | its scene config/layer, `logs/assets/industrial_brass_sorting/` (assets skipped when current) |
| Whole workstation (all 8 assets + base scene) | `python3 scripts/workstation/run_workflow.py` | **all** workstation assets and the base scene |

- **Rebuilds are not byte-identical:** regenerated visual USD files differ in bytes (UV float noise, prim order;
  see [PORTABILITY.md](PORTABILITY.md)). Review them with `git status` / `git diff --stat`, and discard unwanted
  regenerations with `git restore <path>`.
- **Validated workstation:** `run_workflow.py` rebuilds the validated workstation; use it only when the workstation
  itself changes.

## 6. Open the scenes (Isaac Sim GUI)

```bash
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py                                                          # original workstation
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/industrial_brass_sorting.usda  # brass sorting
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/workstation_test_spacer.usda   # spacer demo
```
- **Options:** `--play` starts the simulation; `--self-test` runs the automated raise/resettle check and exits.
- **Plain USD viewers:** the files are ordinary USD and open in other viewers too, but without the Franka (it
  needs Isaac Sim's asset resolver and network access) and without `OmniGlass`.

## 7. Validation

| Scope | Command | Needs |
|---|---|---|
| Original workstation, no rebuild (94 static + 39 dynamic + GUI self-test) | `scripts/motion_planning/run_regression.sh` | Isaac, display |
| Static only / physics only (headless) | `"$ISAACSIM_PYTHON" scripts/workstation/validate_scene.py` / `run_physics_test.py` | Isaac |
| Derived scene, targeted (238 checks for brass sorting) | `"$ISAACSIM_PYTHON" scripts/assets/validate_asset_scene.py --scene config/scenes/industrial_brass_sorting.json` | Isaac |
| Validator must reject a tampered layer | `python3 scripts/assets/negative_control.py` | Isaac |
| Geometric reachability | `"$ISAACSIM_PYTHON" scripts/assets/reachability_check.py --scene config/scenes/industrial_brass_sorting.json --pick-support InputTray --drop FittingA_=sorting_bin_A FittingB_=sorting_bin_B` | Isaac |
| Motion experiment | `"$ISAACSIM_PYTHON" scripts/motion_planning/run_motion_experiment.py --headless` then `validate_motion.py --finalize` | Isaac + cuMotion |

- **Reports:** validation writes reports under `logs/`. Reports and previews are tracked, so a run shows up in
  `git status`; commit it only if you want to keep it.
- **Without the ramp project:** `run_workflow.py`, `run_regression.sh` and `add_asset.py` check the parent ramp
  project only when it is present (the original `robot-agent-lab/` checkout). In a standalone clone they skip it,
  and `run_workflow.py` then reports criterion 14 ("ramp project functional") as not met.

## 8. Working offline

| Works offline | Does not work offline |
|---|---|
| everything in Blender (asset generation, `compose_scene.py`), `asset_lib.py`, `check_environment.sh` (it warns about the URL) | loading the Franka: it is referenced by `https://omniverse-content-production…/Isaac/6.2/…/franka.usd`. Scenes then open without the robot, and the robot checks, the reachability check, the GUI self-test assumptions and motion planning fail. |
| opening the tray/crate/fitting geometry in Isaac Sim (without the robot) | `build_scene.py` (it resolves the robot through the NVIDIA asset root) |

To work fully offline, download NVIDIA's Isaac Sim 6.2 asset pack (subject to NVIDIA's terms) and point Isaac Sim's
asset root (Kit setting `/persistent/isaac/asset_root/default`) at it **before** running `build_scene.py`.
`build_scene.py` writes the resolved robot path into the scene, so a scene built this way contains that local
absolute path and is machine-specific. Don't commit such a rebuilt base scene unless that is intended.

## 9. Updating the repository with Git

```bash
git pull --ff-only                      # get updates (refuses to create merge commits silently)
git status                              # see what your runs changed
git add <files> && git commit -m "…"    # commit deliberately chosen files
git push                                # to origin/main
```
- **Before committing:** review `git status`. Generated logs and caches are already ignored (`.gitignore`), while
  reports, previews and generated USD are tracked on purpose.
- **Branch:** `main`. Never force-push it.
