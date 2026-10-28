# Asset formats

## Blender source files

No `.blend` files are kept. **CAD:** the FreeCAD route keeps `<id>.step` (AP214, mm), the solid, next to the USD files.
FreeCAD builds from 2026-10-28 on also keep `<id>.FCStd`: a native document with the solid as a `Part::Feature` and
the generating spec in the `AssetSpecJSON` property. It holds no feature history, since the parametric source is the
spec plus `freecad_build.py`. `brass_adapter_male_cad` predates this and has only its STEP. a STEP import references its source file (path + SHA-256 in `asset_info.json` → `import_source`). The
intermediate STL tessellation is deleted after Blender imports it. Both generators build the geometry in an empty Blender scene (`clear_scene()` resets to factory
settings, metric, scale 1) and export it directly. There are no `.blend` or `.glb` files in this sub-project;
`.blend` and `.glb` exist only in the parent ramp project. To regenerate, rerun the generator: the code plus the
config are the source.

## Asset definition parameters

Schema: `config/schemas/asset_spec.schema.json`; method-specific rules in `asset_lib.spec_errors`. Units m, kg, deg.

- **`open_container`** (`asset_lib.container_dims`): `size` [L, W, H] is the outer envelope at the rim;
  `wall_thickness` t; `floor_thickness` (height of the inner floor above the bottom). Optional:
  - `draft_deg` (walls lean outwards towards the top) and `corner_radius` / `corner_segments`;
  - `rim` {`height`, `overhang`, `round`};
  - `foot` {`height`, `inset`} (stacking foot);
  - `band` {`z`, `height`, `depth`};
  - `ribs` {`long`, `short`, `width`, `depth`, `corners`};
  - `handles` {`width`, `height`, `below_rim`} (hand holes in the ±x walls);
  - `label_holder` {`width`, `height`, `depth`, `z_center`}, which provides the mount points `label_+x` / `label_-x`.

  The visual is one mesh: a loft of rounded-rectangle offset rings, plus rib/holder prisms and a Boolean cut for the
  handles, triangulated so Hydra renders the holes. Support surface `inner_floor`.
- **`fitting`** (`asset_lib.fitting_sections`): `outer` and `bore` are lists of sections from z = 0 upwards, each
  with a `length`:
  - `cylinder` {`diameter`, `chamfer_start`, `chamfer_end`, `grooves` [{`at`, `width`, `depth`}]};
  - `cone` {`d0`, `d1`, chamfers};
  - `hex` {`across_flats`, `chamfer`}: 30° corner chamfer at both ends, corners on the ±x axis;
  - `thread` {`major_diameter` (outer) or `minor_diameter` (bore), `pitch`, `depth`, chamfers}: a visual helix,
    8 rings per pitch.

  The mesh is a set of rings with `segments` radii at fixed angles, so steps, hex flats and threads stay watertight.
  `nominal_size` x = largest diameter or hex corner-to-corner, y = largest diameter or hex across flats.
- **`label_plate`**: `size` [width, thickness incl. text relief, height]. The plate stands in the xz-plane with its
  text on the −y face; the attach point is the centre of the back (+y) face. Collision `none`, body `static`, no
  physics material.
- **Collision:**
  - `container_walls`: `Floor` (box) plus `WallPosX/NegX/PosY/NegY`, convex slabs from the inner wall face to the
    rim's outer edge.
  - `fitting_sections`: `zones` groups consecutive outer sections. Each zone is a ring of convex sector prisms: 6 for
    a single hex section, `segments` (multiple of 12) circumscribing the zone's largest radius otherwise. Their
    inner faces are tangent to the largest bore radius in the zone's z range.
  - `contact_offset_m` writes `PhysxCollisionAPI` + `physxCollision:contactOffset` on every collider.

## Mesh export: `<name>_visual.usd`

Written by Blender's USD exporter (`bpy.ops.wm.usd_export`, selected objects, materials, normals, UVs). This is the
binary crate format (`PXR-USDC`), even though the extension is `.usd`. It contains Xform/Mesh prims plus
`UsdPreviewSurface` materials converted from Principled BSDF, and has no physics. Visual-only details live only
here, for example the bin labels and the crate handles.

## Physics asset: `<name>.usd`

Text USD (`#usda 1.0`), written by `generate_assets.write_asset` with Blender's `pxr`:
```
/<Root>                 Xform, kind=component, defaultPrim; dynamic: RigidBodyAPI + MassAPI (mass, centerOfMass,
                        diagonalInertia, principalAxes = identity); customData robot_agent_lab_json (frame, notes)
  Visual                Xform, references @./<name>_visual.usd@
  PhysicsMaterial       UsdShade.Material + UsdPhysics.MaterialAPI (static/dynamic friction, restitution)
  Collision/<Part>      Xform (translate [+ rotateXYZ]) / Shape: Cube (size 1 + scale) or Cylinder (axis Z); or a
                        Mesh with MeshCollisionAPI convexHull. All have purpose=guide, CollisionAPI, physics material binding.
```
Stage metadata: `upAxis = "Z"`, `metersPerUnit = 1`, `kilogramsPerUnit = 1`. Origin at the bottom centre; the
tabletop is the exception, with its origin at the geometric centre. `table.usd` only composes `tabletop.usd` and
four `table_leg.usd` references.

## Manifests

| File | Writer | Contents |
|---|---|---|
| `assets/workstation/asset_manifest.json` | `generate_assets.py` (whole file, every run) | per workstation asset: bounds, mass properties, colliders, files; Blender version; `ok` |
| `assets/library/<id>/asset_info.json` | `generate_asset.py` | spec copy + `spec_sha256`, file SHA-256s, resolved physics material, bounds, mesh checks, mass properties, collider names, self-checks, `ok`, Blender version, UTC time; `geometry_backend` (decision, rule, reason, tools); `cad` (FreeCAD version, solid properties, features, CAD checks) and `import_source` for the CAD routes |
| `assets/library/registry.json` | `asset_lib.rebuild_registry()` | one entry per `asset_info.json`. It is derived, so don't edit it by hand. It is rewritten only when its content changes. |

## Scene files

| File | Writer | Notes |
|---|---|---|
| `assets/scenes/waste_sorting_workstation.usd` | `build_scene.py` | text USD; references `./../workstation/<asset>/<asset>.usd` and the Franka by https URL; holds all scene-level overrides; `customLayerData.robot_agent_lab` (config, robot URL, rendering mode) |
| `assets/scenes/derived/<scene>.usda` | `compose_scene.py` | see below |
| `logs/workstation/*_test_scene.usda`, `logs/assets/*/base_suites/*_test_scene.usda` | `run_physics_test.py` | temporary test stages that sublayer the scene; git-ignored |

### Derived scene layer

```usda
#usda 1.0
( customLayerData = { dictionary robot_agent_lab = { base_scene_sha256, instances_json, robot_asset, scene_config, … } }
  defaultPrim = "World"  metersPerUnit = 1  kilogramsPerUnit = 1  upAxis = "Z"
  subLayers = [ @../waste_sorting_workstation.usd@ ] )
over "World" {
    def Xform "UserObjects" ( kind = "group" ) {
        def Xform "TestSpacer_0" ( prepend references = @../../library/test_spacer/test_spacer.usd@ ) {
            quatd xformOp:orient = (1, 0, 0, 0)
            double3 xformOp:translate = (-0.55, -0.25, 0.7515)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]
            over "PhysicsMaterial" ( prepend apiSchemas = ["PhysxMaterialAPI"] ) {
                uniform token physxMaterial:frictionCombineMode = "average"
                uniform token physxMaterial:restitutionCombineMode = "average" } } }
    over "Cameras" { def Camera "AssetPreview" { … } } }
```
- **Instances:** several instances share one referenced asset layer, so geometry is not duplicated. Instanceable
  prims are not used, so the validators and the GUI tooling can address each instance directly.
- **Static instances:** a `"static": true` instance gets `bool physics:rigidBodyEnabled = 0` on that instance only.
- **Regeneration:** the layer is always regenerated from the scene config, so don't edit it by hand.
  `validate_asset_scene.py` rejects anything authored outside the instances root, the preview cameras
  (`/World/Cameras/AssetPreview`, `/World/Cameras/<CamelName>` for `preview_cameras`) and `over <prim> (active = false)`
  for the configured `deactivate_base_prims`.
- **Poses:** `xformOp:orient` is a full quaternion from `asset_lib.scene_poses`: lying parts and attached labels are
  not yaw-only. The placement mode, support and orientation of every instance are recorded in `instances_json`.
- **Deactivation:** `deactivate_base_prims` writes `over "<prim>" (active = false)` and nothing else. The robot, the
  table, the ground/environment, the physics scene and the cameras are protected (`asset_lib.PROTECTED_BASE_PRIMS`).

## Relative references

All local asset paths are relative to the layer that contains them (`./`, `../`). `UsdUtils.ComputeAllDependencies`
resolves all of them (`usd.all_references_resolve`, `structure.all_dependencies_resolve`), and
`structure.local_asset_paths_relative` rejects absolute paths. The only non-relative path is the hosted robot URL
`https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.2/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd`.
`OmniGlass.mdl` is resolved through Kit's MDL search path, so it only works in Kit/Isaac Sim.
