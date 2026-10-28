# Validation

Passing these checks means the scene is internally consistent and behaves plausibly under the modelled rigid-body
approximation. It does **not** prove physical realism: friction values are illustrative, there is no deformation,
the bottles are solid, collision checking is discrete, and no grasping has been tested.

## Overview

| Script | Kind | Checks | Output |
|---|---|---|---|
| `scripts/workstation/validate_scene.py` | structural + geometric + physics config + robot + layout + reachability | 94 | `logs/workstation/static_validation.json`, `scene_inventory.json` |
| `scripts/workstation/run_physics_test.py` | dynamic (PhysX CPU, 120 Hz) | 39 | `logs/workstation/physics_results.json`, `trajectories/*.csv` |
| `scripts/workstation/open_scene.py --self-test` | GUI physics | 1 (PASS/FAIL) | console |
| `scripts/workstation/diagnose_gui_physics.py` | GUI vs. headless reproduction (7 scenarios) | report table | `logs/workstation/gui_diagnosis/*.json` |
| `scripts/workstation/render_previews.py` + `logs/workstation/visual_inspection.md` | visual inspection | mean RGB > 5 + manual notes tied to the image hashes | `preview_*.png` |
| `scripts/workstation/run_workflow.py` | aggregation → classification | 17 success criteria | `validation_report.md`, `validation_results.json` |
| `scripts/motion_planning/*` | motion planning + execution | 14 motion checks + regression | `logs/motion_planning/` |
| `scripts/assets/generate_asset.py` | per-asset self-checks | 5 | `assets/library/<id>/asset_info.json` |
| `scripts/assets/validate_asset_scene.py` | derived scene (targeted) | 54 for the spacer demo, 238 for `industrial_brass_sorting` | `logs/assets/<scene_id>/validation_*.{json,md}` |
| `scripts/assets/reachability_check.py` | Lula IK + endpoint clearance of pickup / drop poses | per pose | `logs/assets/<scene_id>/reachability.{json,md}` |
| `scripts/assets/negative_control.py` | the validator must fail on a tampered layer | 3 expected failures | `logs/assets/negative_control/` |
| `scripts/assets/asset_lib.py selftest` | spec/scene/placement/backend-selection unit cases | 48 cases | console |

## Static validation (`validate_scene.py`): groups and counts

- **`usd` (8):** the scene opens; no composition errors; every reference resolves (`UsdUtils.ComputeAllDependencies`);
  units (m, kg, Z up); default prim; required hierarchy; render and physics material bindings resolve.
- **`geometry` (32):** table dimensions, ground contact, tabletop surfaces, exactly 4 legs, leg size/inset/contact;
  per object: dimensions, position, upright, not penetrating, footprint on the table; object separation; bins/crate
  dimensions and support; crate bottles inside; no static AABB intersections; within the ground.
- **`physics` (15):** one physics scene with gravity and rate; static colliders without rigid bodies; open-top
  compounds; dynamic bodies with mass equal to the config and positive inertia; static crate bottles.
- **`robot` (12):** reference resolves, single articulation root, 7 revolute + 2 prismatic joints, base fixed,
  gripper links, rigid-body count, no extra robot physics schemas in the scene layer, home pose within limits and
  equal to the drive targets, base on the tabletop, filtered pair, objects clear of the base.
- **`layout` (10):** the analytic model matches the USD colliders, platform support/stability, destinations, gaps,
  free compartment, bottle fit, unobstructed bin openings.
- **`reachability` (17):** robot reachability. Lula FK matches the USD robot; for each destination, poses match
  the config, Lula IK is feasible, joint limits hold and endpoint collision clearance holds (PhysX hulls vs.
  scene boxes); 1 cm sampled crate insertion/retreat; pickups. These are **IK + endpoint** checks only, not
  trajectories.

## Dynamic validation (`run_physics_test.py`)

- **`settle_*` (3 × 6):** no fall-through, settled on the tabletop, upright, no drift, at rest, contact normal force
  equal to the weight within 10 %. This runs on the unchanged scene for 3 s, with session-layer instrumentation only.
- **`robot` (6):** the articulation initializes, the initial state is the home pose, the home pose is held, the
  base is fixed, there is no initial collision, and link contact readback passes a positive control.
- **`bin_drop_*` (2 × 5):** in a temporary stage, a 6 cm cube enters through the open top, falls inside, hits the
  bottom, doesn't pass through and stays contained.
- **`glass_placement` (4):** a bottle copy in the target crate compartment stays upright, is supported by the floor,
  touches no wall or separator and doesn't drift.
- **`integrity` (1):** the scene file is unchanged by the test.

## Derived scenes (`validate_asset_scene.py`)

- **`structure`:** the layer exists and opens; all dependencies resolve; local asset paths are relative (remote URLs
  are listed); units and default prim; the only sublayer is the base scene; the base scene hash equals the one
  recorded at composition; the layer authors nothing outside the instances root and the preview camera.
- **`registry`:** every instanced asset is `current` (spec hash and file hashes) and passed its generation checks.
- **`instance:<name>`:** the reference path; the pose (translation 1e-9 m, yaw 1e-6°, no tilt); local visual and
  collider bounds vs. the spec (spec tolerance); collider count and guide purpose; physics material values; PhysX
  combine modes; bore clearance for ring colliders; visual material; rigid body, mass and inertia vs.
  `asset_info.json` (or static); resting gap on the tabletop; footprint on the table; clearance to the base objects,
  `panda_link0`, the sorting zone and the other instances. Clearance is an AABB lower bound, ≥ `min_object_gap_m`.
- **New placement modes and geometry:**
  - `pose` compares the full rotation matrix (1e-9) with `asset_lib.scene_poses`.
  - `resting_on_support`: the lowest collider vertex is above the support floor by the expected gap.
  - `inside_support`: every collider vertex is ≥ `min_object_gap_m` inside the support surface.
  - `on_mount_point`: labels.
  - `bore_open`: for `fitting_sections`, every convex piece clears the narrowest bore circle.
  - `open_top`: for `container_walls`, no wall piece reaches into the column above the inner floor.
  - Collider bounds and gaps come from the collider vertices, because BBoxCache bounds of rotated meshes are loose.
- **`scene`** (from the scene config's `validation` block): distinct geometry of asset pairs (mesh hash, size, volume
  > 10 %, section layout), `compare_assets` variant pairs (same envelope within tolerance; volume / mass / inertia
  differences reported), the number of individual rigid bodies per support, and initially empty drop-test containers.
- **CAD routes (generation):** `cad_solid` (FreeCAD: valid closed solid, bounding box, STEP round trip, tessellation)
  and `cad_mesh_mass_consistency`; see [GEOMETRY_BACKENDS.md](GEOMETRY_BACKENDS.md#checks-on-the-cad-routes).
- **`physics:*` for supported parts:**
  - `settled_on_support`, `inside_support_no_penetration` (final collider vertices vs. the container's inner wall
    planes and floor), `orientation_stable`, `no_extreme_motion` (≤ 0.3 m/s, ≤ 5 rad/s) and the support-floor
    normal force equal to the weight.
  - `drop_test_<container>`: a 6 cm session-layer cube enters through the open top, contacts the floor (force =
    weight), stays inside and does not penetrate the floor.
  - `move_test_<instance>`: the body is teleported +5 cm / +45° and resettles; the others move < 1 mm; the visual
    mesh and the colliders are children of the body root with identity / asset-local transforms.
- **`preservation`:** every base prim (783 for the workstation, robot included) is present with identical type,
  world transform, attribute values (7639 compared), relationships and applied schemas; new prims exist only under
  the allowed roots.
- **`physics:*`:** a 3 s PhysX settle of the dynamic instances, measured from the authored pose: settled (gap,
  height change), upright, no drift, at rest, normal force equal to the weight within 10 %. The base objects are
  checked for disturbance.
- **Negative control:** `negative_control.py` moves an instance onto the PET bottle and adds an override that shifts
  the bottle. The validator fails exactly `structure.derived_layer_scope`, `preservation.base_prims_unchanged` and
  `instance:…clearance_to_scene`.
- **Base suites:** `add_asset.py --base-suites` also runs the 94 static and 39 dynamic workstation checks on the
  derived scene. It writes a config copy with `paths.scene` set to the derived layer and `logs_dir` set to
  `logs/assets/<scene_id>/base_suites/`, so the baseline logs are not overwritten.

## Known gaps in the existing checks

- **Settle start point:** `run_physics_test.py` measures height change from its first sample, which is taken after
  `play()` has already advanced physics. The 1.5 mm drop has already happened by then (first sample z ≈ 0.75006,
  authored z = 0.7515), so `settled_on_tabletop`'s `|Δz + clearance| ≤ 4 mm` is weaker than intended. The
  gap/penetration and force checks are unaffected. `validate_asset_scene.py` measures from the authored pose instead.
  The validated base test has not been changed.
- **Derived-scene robot check:** on a derived scene, `robot.no_extra_robot_physics_schemas` only inspects the derived
  root layer, so it passes trivially. The base scene check remains meaningful, and the `preservation` group
  covers the robot instead.
- **Discrete collision checks:** clearances are checked at configurations, not swept volumes. Motion trajectories
  are re-checked densely (every 4 ms), but only at discrete times.

## What was run for the geometry backends (2026-10-28)

| Run | Result |
|---|---|
| `asset_lib.py selftest` | PASS, 48 cases (incl. 7 deterministic backend-selection cases with simulated tool sets and 2 rejected backend combinations) |
| FreeCAD 1.1.4 headless probe | revolve, cut, common, extrude, `makeChamfer`, `makeFillet`, STEP round trip, `meshFromShape`, `MatrixOfInertia` all work; `<AppImage> --version` opens the GUI, so it is not used |
| `generate_asset.py` `brass_adapter_male_cad` (FreeCAD route) | 5/5 CAD checks + 7/7 asset checks; bounding box error 3.6e-15 mm; mesh vs. solid volume 2.2e-4; inertia mesh vs. CAD 2.4e-4 |
| `generate_asset.py` `brass_adapter_male_step_import` (STEP import) | 4/4 CAD checks + 7/7 asset checks; identical to the CAD source to ~1e-8 |
| STL import route (temporary asset, removed after the run) | 5/5 asset checks; mass within tessellation error of the CAD value (50.239 vs 50.250 g) |
| FreeCAD unavailable (`FREECAD_EXECUTABLE=/nonexistent`) | selection fails with "STEP required but FreeCAD is not installed", exit 1, nothing written |
| Blender route regression: `test_spacer`, `brass_adapter_male` forced rebuild | visual USD byte-identical; `brass_adapter_male.usd` byte-identical; `test_spacer.usd` differs only in its informational customData (`"mounts": {}`, added in the industrial work); committed files restored |
| `build_cad_comparison.sh` (`--base-suites --preview`) | PASS: 76/76 targeted, 94/94 static + 39/39 dynamic on the derived scene, 43 protected files + parent unchanged; preview inspected |
| Regression after the change | industrial 238/238, spacer 54/54, negative control PASS, `run_regression.sh` 94/94, 39/39, GUI PASS |

## What was run for the industrial brass-sorting scene (2026-10-27)

| Run | Result |
|---|---|
| `generate_asset.py` × 6 (tray, crate, 2 fittings, 2 labels) | all self-checks PASS (dimensions within 0.5 mm, closed meshes, fitting volume vs. ring-loft integral ≤ 3.5e-5, USD reopen, mass/density 8196 / 8482 kg/m³) |
| `build_industrial_scene.sh` → `add_asset.py` (6 specs, compose, validate, 5 previews) | PASS; 238/238 targeted checks; 27 protected files unchanged (content + mtime); parent project unchanged |
| `reachability_check.py` | 16/16 poses with an IK solution; 9/16 feasible (7 pre-grasp, 2 pre-drop); **0/7 top-down grasps are feasible**: 4 intersect the tray walls by 2.6–4.1 mm (lower bound), 3 keep only 10.1–10.8 mm hand clearance (wall or neighbouring fitting); 3 finger shortfalls (see `reachability.md`) |
| `open_scene.py --scene …industrial_brass_sorting.usda --self-test` | PASS (7 fittings raised 0.30 m, resettled within 1.5 mm of their start height) |
| Preview images (`base_suites/preview_industrial_{overview,tray,fittings,crates}.png`, `preview_main.png`) | inspected; see `logs/assets/industrial_brass_sorting/experiment_report.md` |
| Regression after the shared-code changes | `run_regression.sh` 94/94, 39/39, GUI PASS; spacer scene 54/54 (53 earlier checks + `robot_unchanged`); negative control PASS; `selftest` 39 cases PASS |
| Not run | `--base-suites` on this scene (the workstation suites expect the deactivated waste-sorting objects); motion planning; grasp physics |

Issues found and fixed during this work:
- **Cylinder/cone chamfer sign:** chamfers pushed the surface outward; caught by the dimension check.
- **Loose BBoxCache bounds:** validator bounds now come from the collider vertices.
- **Drop-test floor penetration (5.7 mm):** fixed with a 2 cm contact offset on the containers; see
  PHYSICS_AND_COLLISION.md.
- **Hand holes missing in RTX renders:** non-convex n-gons were being fan-triangulated; the meshes are now
  triangulated before export.

## What was run for the incremental-asset work (2026-10-27)

| Run | Result |
|---|---|
| Baseline before changes: `run_regression.sh` | 94/94, 39/39, GUI PASS |
| Generator refactor check: all 8 workstation assets regenerated into a scratch directory | physics USD + manifest byte-identical; visual USD geometry identical, UV differences ≤ 1.2e-7, prim order differs |
| `run_demo.sh` (spec → asset → scene → 53 targeted + base suites on the derived scene + preview + negative control) | PASS; 53/53; 94/94; 39/39; negative control PASS; 23 protected files unchanged; parent unchanged |
| `open_scene.py --scene <derived> --self-test` | PASS (5 bodies raised 0.3 m and resettled at z = 0.75) |
| After all changes: `run_regression.sh` on the base scene | 94/94, 39/39, GUI PASS |
| After all changes: `run_motion_experiment.py --headless` + `validate_motion.py --finalize` | FULL SUCCESS (target 5.06 mm / 0.45°, home 0.77 mm) |
| Not rerun | `run_workflow.py` (it would regenerate every asset), `build_scene.py`, `optimize_layout.py`, GUI motion mode, ramp regression (parent files were verified by hash instead) |
