# Adding a new physics-enabled asset

This tutorial follows exactly what `scripts/assets/run_demo.sh` does for `test_spacer` (a steel spacer, 30 mm OD,
12 mm bore, 25 mm long). Only the new asset and the derived scene are written; the workstation assets and the base
scene are not touched. Every command was run in this repository. A second, larger example (six assets, containers,
parts resting inside a tray, labels, deactivated base content) is [below](#worked-example-industrial-brass-sorting).

## 0. Concepts

| | File | Holds |
|---|---|---|
| A. asset definition | `config/assets/<id>.json` | geometry, visual material, collision representation, body type, mass/density, physics material |
| B. generated asset | `assets/library/<id>/` | `<id>.usd`, `<id>_visual.usd`, `asset_info.json`; listed in `assets/library/registry.json` |
| C. instances | `config/scenes/<scene>.json` → `instances` | name, asset id, placement (surface, xy, yaw, support, mount, pose), per-instance `static` override |
| D. scene config | `config/scenes/<scene>.json` | base scene, environment config, output layer, instances root, preview camera(s), deactivated base prims, scene-level `validation` tests |

An instance never changes its asset, and an asset never knows where it is placed.

## 1. Specify dimensions and properties

`config/assets/test_spacer.json` (schema: `config/schemas/asset_spec.schema.json`):
```json
{
  "schema_version": 1, "asset_id": "test_spacer", "category": "hardware/spacer",
  "geometry": {"method": "tube", "outer_diameter": 0.03, "inner_diameter": 0.012, "height": 0.025, "segments": 48},
  "visual_material": {"color": [0.62, 0.63, 0.65], "roughness": 0.35, "metallic": 1.0},
  "collision": {"representation": "ring_segments", "segments": 12},
  "physics": {"body": "dynamic", "density_kg_m3": 7850,
              "material": {"id": "steel", "static_friction": 0.6, "dynamic_friction": 0.5, "restitution": 0.1}},
  "validation": {"dimension_tolerance_m": 0.0005, "settle_test": true}
}
```
Rules (enforced by `asset_lib.spec_errors`): SI units; `asset_id` is lower_snake_case and names the directory;
geometry `method` is one of

| Method | Required | Optional | Collision representations |
|---|---|---|---|
| `box` | `size` | `bevel` | `primitive`, `convex_hull` |
| `cylinder` | `diameter`, `height` | `segments` | `primitive`, `convex_hull` |
| `tube` | `outer_diameter`, `inner_diameter`, `height` | `segments` | `primitive`, `convex_hull`, `ring_segments` |
| `open_container` | `size`, `wall_thickness`, `floor_thickness` | `draft_deg`, `corner_radius`, `corner_segments`, `rim`, `foot`, `band`, `ribs`, `handles`, `label_holder` | `container_walls` (floor box + 4 convex walls, open top) |
| `fitting` | `outer` (sections), `bore` (sections) | `segments` (multiple of 12) | `fitting_sections` (`zones`, `segments`; bore stays open) |
| `label_plate` | `size`, `text` | `text_color`, `text_height`, `text_relief`, `bevel` | `none` (visual only, static) |
| `mesh_import` | `source` (STL / STEP), `size` (expected envelope) | `source_units`, `recenter` | `primitive`, `convex_hull` (solid) |

**Geometry backend** (`geometry.backend`; absent = `blender`): `auto` picks FreeCAD for `fitting` when
`accuracy: engineering` or `require_step: true` and FreeCAD is installed, picks `import` for `mesh_import`, and
otherwise picks Blender. It records the rule and reason in `asset_info.json`. Check it before building with
`python3 scripts/assets/backends.py select <spec>`. Example: `config/assets/brass_adapter_male_cad.json` (FreeCAD,
STEP) and `config/assets/brass_adapter_male_step_import.json` (STEP import). Details and limits:
[GEOMETRY_BACKENDS.md](GEOMETRY_BACKENDS.md).

`fitting` sections are `cylinder` (`diameter`, `chamfer_start/end`, `grooves`), `cone` (`d0`, `d1`), `hex`
(`across_flats`, `chamfer`) and `thread` (outer: `major_diameter`, bore: `minor_diameter`; `pitch`, `depth`; a visual
helix). Outer and bore lengths must match and every wall must be at least 0.5 mm thick. A dynamic body needs exactly
one of `mass_kg` / `density_kg_m3`, optionally checked against `validation.density_range_kg_m3`. `material` is
either inline or the name of a material in `config/waste_sorting_environment.json` → `physics.materials` (not
needed for `none`). `collision.contact_offset_m` adds a PhysX contact offset to every collider. All parameters:
[ASSET_FORMATS.md](ASSET_FORMATS.md#asset-definition-parameters).

```bash
python3 scripts/assets/asset_lib.py validate-spec config/assets/test_spacer.json
```

## 2–5. Generate geometry, collision, physics properties and USD (one asset)

```bash
"$BLENDER" -b --factory-startup --python-exit-code 1 --python scripts/assets/generate_asset.py -- \
    --spec config/assets/test_spacer.json            # add --force to rebuild an asset that is already current
```
What happens (`generate_asset.py`):
- **Geometry:** `tube` is a lathe of the closed profile outer wall → top → bore → bottom (`generate_assets.lathe` +
  `mesh_object`). Planar faces are flat-shaded and edges sharper than 30° are kept sharp.
- **Collision:** `ring_segments` creates 12 boxes forming a regular 12-gon inscribed in the outer circle, with the
  inner faces at the bore radius, so the hole stays open. `primitive` gives one solid Cube/Cylinder, and
  `convex_hull` gives a solid convex mesh of the visual vertices. Colliders get `purpose = guide`, `CollisionAPI`,
  and the physics material bound with the `physics` purpose.
- **Mass:** `mass_properties` integrates the closed visual mesh. Mass = density × volume (or `mass_kg`), and the
  centre of mass and diagonal inertia are computed from the same mesh. For the spacer this gives 0.11619 kg and
  Izz = 1.512e-5 kg·m², against 1.516e-5 for an ideal hollow cylinder. The 0.3 % difference is the 48-gon.
- **USD:** `export_visual` writes `test_spacer_visual.usd`. `write_asset` writes `test_spacer.usd` with root `/TestSpacer`
  (kind = component, RigidBodyAPI + MassAPI), `Visual` → `@./test_spacer_visual.usd@`, `PhysicsMaterial`, and `Collision/*`.
- **Self-checks** (written to `asset_info.json`): dimensions vs. spec, closed-manifold mesh, mesh volume vs. the
  exact tessellated volume, a reopened USD (units, collider count/purpose/material, unresolved dependencies,
  relative references, mass), and COM on the axis at half height. The script exits non-zero if any check fails.

## 6. Register

Registration is automatic. `asset_info.json` records the spec copy and its SHA-256, the file hashes, the bounds and
the mass properties, and `assets/library/registry.json` is rebuilt from all `asset_info.json` files.
```bash
python3 scripts/assets/asset_lib.py list
# test_spacer  hardware/spacer  dynamic  mass=0.11619… size=[0.03, 0.03, 0.025] status=current usd=assets/library/test_spacer/test_spacer.usd
```
The status is `stale` when the spec has changed since generation and `modified` when a file no longer matches its
hash. Compose refuses any asset that is not `current`.

## 7. Instantiate in a scene (add, move, remove)

```bash
SC=config/scenes/workstation_test_spacer.json
python3 scripts/assets/asset_lib.py new-scene $SC --scene-id workstation_test_spacer --overwrite
python3 scripts/assets/asset_lib.py add-instance $SC --name TestSpacer_0 --asset test_spacer --xy -0.55 -0.25
python3 scripts/assets/asset_lib.py add-instance $SC --name TestSpacer_1 --asset test_spacer --xy -0.45 -0.25 --yaw 15
python3 scripts/assets/asset_lib.py add-instance $SC --name TestSpacer_2 --asset test_spacer --xy -0.55 0.20
python3 scripts/assets/asset_lib.py move-instance $SC --name TestSpacer_1 --xy -0.45 -0.22 --yaw 30
python3 scripts/assets/asset_lib.py remove-instance $SC --name TestSpacer_2
python3 scripts/assets/asset_lib.py set-preview-camera $SC --position -0.32 -0.48 0.92 --target -0.50 -0.235 0.762
"$BLENDER" -b --factory-startup --python scripts/assets/compose_scene.py -- --scene $SC
#   or: "$ISAACSIM_PYTHON" scripts/assets/compose_scene.py --scene $SC    (identical output)
```
- **Placement:** `surface: tabletop` puts the lowest collider point at table top + `objects.clearance` (z = 0.7515 m
  for the spacer), the same rule as `build_scene.py`; `floor` uses z = 0. Static assets get no clearance (they rest
  exactly on the surface). `on_instance` (`--surface on_instance --support <name>`) uses the support's surface
  (`inner_floor` of a container, `top` of a box). `attached` (`--support <name> --mount label_+x`) fixes a visual-only
  asset to a mount point of its support. `--lying [--spin <deg>]` lays a turned part on its side and tilts it onto
  the lower convex hull of its colliders under its centre of mass, so it starts in a stable rest pose.
- **Pre-check:** each edit runs an analytic placement check on the collider pieces (`asset_lib.collider_pieces`):
  the table edge, containment in the support surface, the tabletop objects (unless deactivated), the robot base
  (0.15 m keep-out) and other instances, using `validation.min_object_gap_m` = 0.02 m. A support's floor piece is
  exempt for what rests on it. A failing edit is refused and the file is left unchanged. For example, placing a
  spacer on the PET bottle reports "-0.0325 m from plastic_bottle".
- **Updating the scene:** the derived layer is regenerated from the JSON each time, so re-running
  `compose_scene.py` is the whole "update scene" step.

## 8. Validate

```bash
"$ISAACSIM_PYTHON" scripts/assets/validate_asset_scene.py --scene $SC          # targeted (+ 3 s PhysX settle)
# or everything in one go, with hashing of all protected files:
python3 scripts/assets/add_asset.py --spec config/assets/test_spacer.json --scene $SC --base-suites --preview
```
Result of the demo run: 53/53 targeted checks and, on the derived scene, the workstation's own suites at 94/94
static and 39/39 dynamic. The 23 protected files were unchanged in content and mtime, and the parent project was
unchanged. Read `logs/assets/workstation_test_spacer/add_asset_report.md` and `validation_report.md`.

## 9. Preview in Isaac Sim

```bash
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/workstation_test_spacer.usda          # interactive
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/workstation_test_spacer.usda --self-test
```
Instances under `/World/UserObjects` get the same viewport guard and *Raise* / *Reset* buttons as the built-in objects.
`--preview` renders `logs/assets/<scene_id>/base_suites/preview_asset_preview.png` (close-up) and `preview_main.png`.

## Worked example: industrial brass sorting

`scripts/assets/build_industrial_scene.sh` builds `assets/scenes/derived/industrial_brass_sorting.usda` with the same
tools. Six specs: `industrial_gray_tray`, `industrial_blue_crate` (both `open_container`), `brass_adapter_male`,
`brass_adapter_female` (`fitting`), `label_bin_a`, `label_bin_b` (`label_plate`). The scene config is written by
CLI calls only:
```bash
SC=config/scenes/industrial_brass_sorting.json
L="python3 scripts/assets/asset_lib.py"
$L new-scene $SC --scene-id industrial_brass_sorting --overwrite
$L deactivate-base-prim $SC --path /World/Objects                  # also SortingZone, Targets: derived layer only
$L add-instance $SC --name InputTray     --asset industrial_gray_tray  --xy 0.42 -0.215
$L add-instance $SC --name sorting_bin_A --asset industrial_blue_crate --xy -0.03 -0.20
$L add-instance $SC --name label_A --asset label_bin_a --surface attached --support sorting_bin_A --mount label_+x
$L scatter $SC --support InputTray --asset brass_adapter_male --count 4 --prefix FittingA_ --seed 11 --spins 30 90 150 210 270 330
$L set-preview-camera $SC --name industrial_tray --position 0.56 -0.60 1.30 --target 0.42 -0.215 0.76
$L set-validation $SC --json '{"drop_test": ["sorting_bin_A", "sorting_bin_B"], "move_test": "FittingA_0", ...}'
python3 scripts/assets/add_asset.py --spec config/assets/industrial_gray_tray.json --spec ... --scene $SC --preview
"$ISAACSIM_PYTHON" scripts/assets/reachability_check.py --scene $SC --pick-support InputTray \
    --drop FittingA_=sorting_bin_A FittingB_=sorting_bin_B
```
- `scatter` draws positions, yaw and spin with `random.Random(seed)` and keeps a candidate only if the piece-based
  placement check passes.
- The spin values put a hex flat down.
- The results are in `logs/assets/industrial_brass_sorting/` (`add_asset_report.md`, `validation_report.md`,
  `reachability.md`, `base_suites/preview_industrial_*.png`).
- `--base-suites` is not used for this scene. The workstation's own 94/39 checks expect the waste-sorting objects,
  which this scene deactivates.

## Adding a geometry method, or using an existing one (example: ISO 4032 M8 hex nut)

A plain hex nut needs **no new code** now: it is a `fitting` with one `hex` outer section and a `thread` bore. This
spec passes `validate-spec` (6 hex collider sectors, bore open at 4.33 mm radius); it has not been generated or
simulated:
```json
{"schema_version": 1, "asset_id": "m8_hex_nut", "category": "hardware/fastener",
 "geometry": {"method": "fitting", "segments": 48,
   "outer": [{"type": "hex", "length": 0.0068, "across_flats": 0.013, "chamfer": true}],
   "bore":  [{"type": "thread", "length": 0.0068, "minor_diameter": 0.00665, "pitch": 0.00125, "depth": 0.0006,
              "chamfer_start": 0.0004, "chamfer_end": 0.0004}]},
 "visual_material": {"color": [0.62, 0.63, 0.65], "roughness": 0.35, "metallic": 1.0},
 "collision": {"representation": "fitting_sections"},
 "physics": {"body": "dynamic", "density_kg_m3": 7850,
             "material": {"id": "steel", "static_friction": 0.6, "dynamic_friction": 0.5, "restitution": 0.1}}}
```
Idealised mass: (146.4 − 34.7) mm² × 6.8 mm × 7.85 g/cm³ ≈ 6.0 g without chamfers. Catalogue masses are about 5 g,
so give `mass_kg` if the catalogue value matters more than the idealised volume.

A genuinely new shape (say a flanged or non-turned part) needs:
1. `asset_lib`: the method in `METHOD_PARAMS` / `METHOD_OPTIONAL`, the schema enum, `nominal_size`, the method's
   rules in `spec_errors`, and — if it gets its own collider representation — `collider_pieces` (pure Python, so
   placement and validation use the same pieces as the generator).
2. `generate_asset.build_geometry`: the Blender mesh (closed, outward normals, origin bottom centre).
3. `mesh_checks`: an independent volume reference.
4. A `selftest` case and a spec in `config/assets/`.

Reused unchanged: the material, `mass_properties`, `export_visual`, `write_asset`, the registry, compose, the
validator, placement and the GUI tooling.
