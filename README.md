# Waste-sorting workstation (Isaac Sim 6.2)

Physics-enabled robotics workstation, generated procedurally. It contains:
- a lab table and the official NVIDIA Franka Panda;
- a glass bottle, a PET bottle and a paper cup;
- PAPER and PLASTIC bins, and a glass crate on a cabinet platform;
- an asset library for adding new objects to derived scenes without rebuilding anything else.

Validated state:
- workstation: 94/94 static and 39/39 dynamic checks;
- first robot motion (home → PET pre-grasp → home with cuMotion): FULL SUCCESS;
- incremental-asset demo: 53/53 targeted checks (54/54 with the current validator);
- industrial brass-sorting scene: 238/238 targeted checks (see below).

**Agents start at [AGENTS.md](AGENTS.md).** Documentation: [architecture](docs/ARCHITECTURE.md) ·
[installation](docs/INSTALLATION.md) · [add a new asset](docs/ADD_NEW_ASSET.md) · [asset formats](docs/ASSET_FORMATS.md) ·
[physics & collision](docs/PHYSICS_AND_COLLISION.md) · [validation](docs/VALIDATION.md) · [portability & Git](docs/PORTABILITY.md) ·
[agent handoff](docs/AGENT_HANDOFF.md) · [geometry backends](docs/GEOMETRY_BACKENDS.md).

## Setup

Ubuntu 22.04, Blender 5.2 and NVIDIA Isaac Sim 6.2 are required; system Python only needs the standard library.
Full instructions: [INSTALLATION.md](docs/INSTALLATION.md).
```bash
git clone git@github.com:vahidlbf/robotic-asset-generation-framework.git    # private repository (SSH access needed)
cd robotic-asset-generation-framework                                         # all commands below run from here
export ISAACSIM_PYTHON=~/isaacsim/python.sh   # Isaac Sim interpreter (or set ISAACSIM_PATH)
export BLENDER=blender
scripts/check_environment.sh                  # read-only check of tools, GPU, robot URL, files, selftest
```
The clone contains all generated USD assets and scenes, so it can open the scenes without regenerating anything.
The Franka robot is loaded from NVIDIA's asset server, so network access is needed for it.

## Workstation pipeline

All workstation parameters live in `config/waste_sorting_environment.json` (single source of truth).

| Script | Runs in | Purpose |
|---|---|---|
| `scripts/workstation/run_workflow.py` | `python3` | runs every stage below (regenerates **all** assets and the scene), samples GPU memory, writes the report |
| `scripts/workstation/generate_assets.py` | Blender | visual meshes + collider/physics/mass USD assets → `assets/workstation/` |
| `scripts/workstation/build_scene.py` | Isaac | assembles `assets/scenes/waste_sorting_workstation.usd` |
| `scripts/workstation/validate_scene.py` | Isaac | geometry / USD / physics-schema / robot / layout checks + reachability (Lula IK) |
| `scripts/workstation/run_physics_test.py` | Isaac | settle test, robot stability, bin drops, glass placement |
| `scripts/workstation/render_previews.py` | Isaac | preview PNGs from the scene cameras |
| `scripts/workstation/open_scene.py` | Isaac | GUI (`--play`, `--scene <derived scene>`, `--self-test`) |
| `scripts/workstation/optimize_layout.py` | Isaac | sorting-zone layout search; `--apply` writes it into the config |

```bash
python3 scripts/workstation/run_workflow.py                  # regenerate + validate everything
scripts/motion_planning/run_regression.sh                     # re-validate the existing scene without rebuilding
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py          # open in the Isaac Sim GUI
```
After previews are re-rendered, the classification stays PARTIALLY VALIDATED until the new images have been
inspected and `logs/workstation/visual_inspection.md` updated for their hashes; then run `run_workflow.py --report-only`.

## Adding assets without rebuilding the workstation

```bash
python3 scripts/assets/asset_lib.py validate-spec config/assets/test_spacer.json
python3 scripts/assets/asset_lib.py add-instance config/scenes/workstation_test_spacer.json --name Spacer_A --asset test_spacer --xy -0.35 -0.30
python3 scripts/assets/add_asset.py --spec config/assets/test_spacer.json --scene config/scenes/workstation_test_spacer.json --base-suites --preview
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/workstation_test_spacer.usda
```
- **Asset definition:** `config/assets/<id>.json`.
- **Generated asset:** `assets/library/<id>/`.
- **Instances:** `config/scenes/<scene>.json`.
- **Derived layer:** `assets/scenes/derived/<scene>.usda`. It sublayers the untouched base scene.

Full tutorial: [ADD_NEW_ASSET.md](docs/ADD_NEW_ASSET.md). Reproducible demo: `scripts/assets/run_demo.sh`.

Geometry methods: `box`, `cylinder`, `tube`, `open_container` (crates and trays), `fitting` (turned parts with hex
flats, visual threads and a stepped bore), `label_plate` and `mesh_import` (STL / STEP). Each asset is built by a
**geometry backend**: Blender (default), the optional FreeCAD parametric-CAD builder (STEP output, currently for
`fitting`), or a CAD import. `geometry.backend: auto` chooses deterministically and records why; see
[GEOMETRY_BACKENDS.md](docs/GEOMETRY_BACKENDS.md). `scripts/assets/build_cad_comparison.sh` compares the three routes for
one brass adapter. Instances can stand on the tabletop or floor, rest
inside another instance (`on_instance`, also lying down) or be attached to a mount point. They can be scattered
with a seed.

## Industrial brass-sorting scene

`assets/scenes/derived/industrial_brass_sorting.usda`:
- a grey input tray with seven brass fittings (4 male Type A, 3 female Type B) in front of the Franka;
- two blue crates labelled BIN A / TYPE A and BIN B / TYPE B;
- the waste-sorting objects deactivated in the derived layer only.
```bash
scripts/assets/build_industrial_scene.sh                                                  # rebuild + validate + previews
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/industrial_brass_sorting.usda
```
Results: `logs/assets/industrial_brass_sorting/experiment_report.md`. Asset generation, composition and physics
validation pass; geometric reachability shows that top-down grasps from the 0.10 m-deep tray are not feasible with
the Franka hand.

## Moving objects in the GUI

Each object is a rigid body on its asset root (`/World/Objects/<Name>`, `/World/UserObjects/<Name>`), with its render
mesh (`Visual/...`) and invisible colliders (`Collision/...`) as children. Move the **root**, not the mesh.
`open_scene.py` makes this the default:
- viewport picking is switched to *Models* for the session and restored on exit;
- `RigidBodyGuard` transfers any mesh or collider offset to the rigid body once a drag ends;
- the "Workstation physics" window has physics-safe *Raise* / *Reset* buttons.

Numerical GUI-vs-headless reproduction: `diagnose_gui_physics.py --mode gui|headless`.

## Sorting zone

The PAPER bin, the PLASTIC bin and the glass crate (on a static cabinet platform) sit around the robot's +X end
(`/World/Workstation/SortingZone`). The positions, platform height, target compartment and every target TCP pose
are written by `optimize_layout.py --apply` (seeded, about 10 min). Validated: IK feasibility, joint limits,
endpoint collision clearance, and sampled 1 cm crate insertion/retreat. Not validated: continuous trajectories and
pick-and-place execution.

## Motion planning (first real robot motion)

`scripts/motion_planning/` plans and executes Franka home → PET pre-grasp → home with NVIDIA cuMotion:
collision-free IK, then GraphBasedMotionPlanner RRT, then jerk-limited time parameterisation, then dense
re-validation. It executes in PhysX through `mg.TrajectoryFollower` and the articulation joint drives.
Config: `config/motion_planning.json`. Outputs: `logs/motion_planning/` (headless) and `logs/motion_planning/gui/`.
```bash
"$ISAACSIM_PYTHON" scripts/motion_planning/run_motion_experiment.py --headless   # headless
"$ISAACSIM_PYTHON" scripts/motion_planning/run_motion_experiment.py              # watch in the GUI
"$ISAACSIM_PYTHON" scripts/motion_planning/validate_motion.py --finalize         # final classification
```
