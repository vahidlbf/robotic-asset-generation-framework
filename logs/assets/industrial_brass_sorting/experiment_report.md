# Experiment report: industrial brass-fitting sorting workstation

Date: 2026-10-27. Scene `industrial_brass_sorting`. This scene was built with the existing incremental asset framework,
extended where the new shapes required it. Every number below comes from the files in this directory and in
`assets/library/<id>/asset_info.json`.

**Result: the asset-generation and scene-composition goals are met. Top-down pickup is not accessible.**
- 6 assets were generated and 12 instances composed.
- Targeted validation passed 238/238 and the GUI self-test passed.
- The previews were inspected, and the original workstation is unchanged by hash and mtime.
- None of the seven top-down grasp poses meets the 20 mm hand-clearance rule; see Reachability.

No reference photographs were available (`references/industrial_parts_sorting/` does not exist). The assets were
built from the written specification only. They are representative, not replicas of real products.

## Generated assets

| Asset | Method | Envelope (m, measured) | Mass | Visual mesh | Colliders |
|---|---|---|---|---|---|
| `industrial_blue_crate` | `open_container` | 0.400 × 0.300 × 0.220 | static | 772 verts / 1480 tris | `container_walls`: floor box + 4 convex walls; contact offset 0.02 m |
| `industrial_gray_tray` | `open_container` | 0.350 × 0.300 × 0.100 | static | 420 / 836 | `container_walls`; contact offset 0.02 m |
| `brass_adapter_male` (Type A) | `fitting` | 0.02483 × 0.0215 × 0.045 | 0.045 kg | 4320 / 8640 | 42 convex sectors (4 zones) |
| `brass_adapter_female` (Type B) | `fitting` | 0.032 × 0.032 × 0.055 | 0.075 kg | 9408 / 18816 | 54 convex sectors (5 zones) |
| `label_bin_a`, `label_bin_b` | `label_plate` | 0.130 × 0.003 × 0.050 | static | 964 / 1000, 1724 / 1768 | none (visual only) |

**Crate** (PP blue, roughness 0.55):
- 4 mm walls with 2.5° draft and a 26 mm reinforced rim (8 mm overhang, rounded).
- 12 mm stacking foot and a horizontal band.
- 18 vertical ribs: 5 per long side, 2 per short side and 4 at the corners.
- Hand holes in both short walls, with label holders below them.

**Tray** (grey plastic, roughness 0.62): 5 mm walls with 4° draft, a 10 mm rounded rim and a flat floor 5 mm above
the bottom.

**Type A (male):**
- G1/2-like visual helix thread, 20.96 mm major diameter, 1.814 mm pitch.
- Relief groove, then a 21.5 mm hex with 30° chamfers.
- Grooved 18.5 mm body, cone, and a chamfered 17 mm spigot.
- 16 / 13 mm stepped bore.

**Type B (female):**
- G3/8-like male spigot thread, relief, collar and cone.
- 22.5 mm hex and 25 mm neck.
- 32 mm socket with two grooves and an internal visual thread (27.5 mm minor diameter).
- 12 / 20 mm stepped passage.

**Masses:** the masses are the task's 0.045 / 0.075 kg. The implied densities of 8196 and 8482 kg/m³ fall inside the
brass band of 8000–8800 enforced by the spec. The geometry was adjusted until they did.

**Inertia (kg·m², about the COM):**
- Type A: 7.975e-6, 7.976e-6 and 3.486e-6; COM 21.74 mm above the bottom.
- Type B: 2.018e-5, 2.018e-5 and 1.043e-5; COM 29.45 mm above the bottom.
- The COM offset from the axis is ≤ 5.1 µm (a consequence of the helical threads), and the off-diagonal inertia is
  ≤ 3.9e-4 of the diagonal.

**Generation self-checks:** all six assets pass every check. Dimensions are within 0.5 mm. The meshes are closed and
manifold. The fitting mesh volume matches the ring-loft integral to 3.5e-5. The reopened USD is correct, and so are
the mass properties.

**Registry:** `assets/library/registry.json` holds 7 assets: these 6 plus `test_spacer`, all `current`.

## Scene: `assets/scenes/derived/industrial_brass_sorting.usda`

The scene is a 17 KB layer that sublayers the unchanged base scene. All 12 instances reference
`../../library/<id>/<id>.usd`.

Robot, table, ground, physics scene, lights and base cameras are reused unchanged. These base prims are deactivated
in this layer only (`active = false`, 335 prims): `/World/Objects` (bottles and cup), `/World/Workstation/SortingZone`
(bins, glass crate and platform) and `/World/Targets`.

| Instance | Asset | Placement | Position (m) | Yaw (°) | Axis tilt from vertical (°) |
|---|---|---|---|---|---|
| `InputTray` | `industrial_gray_tray` | tabletop | [0.42, -0.215, 0.75] | 0.0 | 0.0 |
| `sorting_bin_A` | `industrial_blue_crate` | tabletop | [-0.03, -0.2, 0.75] | 0.0 | 0.0 |
| `sorting_bin_B` | `industrial_blue_crate` | tabletop | [-0.03, 0.2, 0.75] | 0.0 | 0.0 |
| `label_A` | `label_bin_a` | attached to sorting_bin_A, mount `label_+x` | [0.1644, -0.2, 0.845] | 90.0 | 0.0 |
| `label_B` | `label_bin_b` | attached to sorting_bin_B, mount `label_+x` | [0.1644, 0.2, 0.845] | 90.0 | 0.0 |
| `FittingA_0` | `brass_adapter_male` | lying in InputTray | [0.4048, -0.1989, 0.7672] | -117.3 | 90.0 |
| `FittingA_1` | `brass_adapter_male` | lying in InputTray | [0.4691, -0.1839, 0.7672] | 146.7 | 90.0 |
| `FittingA_2` | `brass_adapter_male` | lying in InputTray | [0.5291, -0.2099, 0.7672] | 140.5 | 90.0 |
| `FittingA_3` | `brass_adapter_male` | lying in InputTray | [0.3416, -0.1457, 0.7672] | -85.4 | 90.0 |
| `FittingB_0` | `brass_adapter_female` | lying in InputTray | [0.3783, -0.3032, 0.7650] | 7.7 | 77.9 |
| `FittingB_1` | `brass_adapter_female` | lying in InputTray | [0.3173, -0.2195, 0.7650] | -145.2 | 77.9 |
| `FittingB_2` | `brass_adapter_female` | lying in InputTray | [0.4903, -0.3016, 0.7650] | -58.4 | 77.9 |

**Layout checks:**
- **Crates fit on the table:** the 1.60 × 0.80 m tabletop is reachable around the robot base at (0.45, 0.15); with
  the waste-sorting content deactivated, both crates fit there, so no side stands were needed.
- **Clearances:** every container is at least 0.02 m from the others and from `panda_link0`. The crate-to-crate gap
  is 0.10 m and the crate-to-tray gap 0.075 m.
- **Support:** the static containers rest exactly on the tabletop.
- **Fitting placements:** produced by `asset_lib.py scatter` with seeds 11 and 23. Each was accepted only if the
  piece-based collider check passed: ≥ 0.02 m between fittings and to the tray walls.
- **Rest poses:** computed from the colliders. Type A lies on a hex flat; Type B tilts 12.1° onto its spigot end and
  socket edge.
- **Sorting assignment:** Type A → `sorting_bin_A` (yellow label "BIN A / TYPE A"), Type B → `sorting_bin_B` (white
  label "BIN B / TYPE B"). The roles differ by text as well as colour.

## Validation (`validation_report.md`: 238/238)

**Test A, fitting stability** (3 s PhysX CPU run at 120 Hz, from the authored pose). For all 7 fittings:
- Height change −1.500 mm, i.e. exactly the 1.5 mm placement clearance.
- Horizontal drift ≤ 0.003 mm and rotation ≤ 0.033°.
- Peak speed 0.006 m/s and peak angular speed ≤ 0.072 rad/s.
- Floor normal force 0.4414–0.4415 N (weight 0.4415 N) and 0.7357–0.7358 N (weight 0.7358 N).
- Final collider gap to the tray floor within ±0.003 mm.
- No wall intrusion: the closest final collider vertex is 22 mm inside the inner wall plane.

**Test B, hollow crates** (a 6 cm, 0.1 kg session-layer cube, 0.15 m above each rim). In both crates the cube:
- entered through the opening (local xy at the rim (0.03, −0.02));
- came to rest on the floor (local bottom z 0.016 m, floor force 0.981 N against a weight of 0.981 N);
- stayed inside;
- did not penetrate the floor (minimum 0.0159998 m against a floor top of 0.016 m).

The test cubes exist only in the session layer.

**Test C, individual rigid bodies** (`FittingA_0`):
- Teleported +5 cm and +45° yaw, it resettled at its start height with a 45.0006° yaw change.
- The other six bodies moved at most 0.003 mm.
- PhysX wrote the new pose to the USD root, which the visual mesh hangs from (visual-to-root offset 2.2e-16). There
  is no `resetXformStack`, so the visual and its 42 colliders move with the body.

**Test D, preservation:**
- All 448 active base prims are identical, with 4215 attributes compared. This includes all 366 robot prims.
- The deactivated subtrees are exactly the configured three.
- New prims exist only under `/World/UserObjects` and the four preview cameras.
- The base-scene hash equals the one recorded at composition.
- All dependencies resolve, and all local paths are relative; the only URL is the Franka's.

**Test E, geometry:**
- **Dimensions:** visual and collider bounds of every instance match the specification within 0.5 mm.
- **Open tops:** the open-top check passes for the tray and both crates; no wall piece reaches into the column above
  the floor.
- **Open bores:** every fitting collider clears the narrowest bore circle (6.5 / 6.0 mm radius).
- **Distinct types:** Type A and Type B differ in mesh hash, size, volume (5.49 vs 8.84 cm³) and section layout.
- **Rigid bodies:** there are 7 individual rigid bodies in the tray.
- **Masses and densities:** as listed above.

**Independently verified vs. visually judged.** Dimensions, masses, colliders, poses and physics are verified
numerically. Visual similarity is judged only by looking at the renders.

**GUI:** `open_scene.py --scene assets/scenes/derived/industrial_brass_sorting.usda --self-test` passes. The 7
fittings were raised 0.30 m and resettled within 1.5 mm of their start height.

## Reachability (`reachability.md`): geometric only, no motion

| Poses | Result |
|---|---|
| 16 poses evaluated (7 pre-grasp, 7 grasp, 2 pre-drop) | all have Lula IK solutions within joint limits |
| 7 pre-grasp poses (TCP 0.10 m above the COM, top-down) | feasible; robot clearance ≥ 51 mm |
| 2 pre-drop poses (TCP 0.15 m above the crate rims) | feasible; robot clearance 130 mm |
| 7 top-down grasp poses | **infeasible** under the 20 mm hand-clearance rule |

The grasp failures break down as follows:
- **Hand–wall intersections:** 4 grasps (FittingA_2, A_3, B_1, B_2) put the hand into a tray wall by 2.6–4.1 mm,
  computed against the exact wall faces; the true overlap is at least this.
- **Margins below 20 mm:** 3 grasps keep the hand only 10.1–10.8 mm away. For FittingA_1 the obstacle is a wall; for
  FittingA_0 and B_0 it is a neighbouring fitting.
- **Finger shortfalls:**
  - FittingB_0's fingers overlap FittingB_1's collider by 0.5 mm.
  - FittingB_1's fingers come within 3.6 mm of a neighbour, short of the 5 mm required.
  - FittingB_2's finger hulls reach 3.7 mm below the tray floor; raising the TCP changed the IK solution.

The cause: the Franka hand is about 0.2 m long along the finger axis. At a grasp it sits about 40 mm below the rim of
the 0.10 m-deep tray, and parts lie closer than about 0.1 m to a wall along that axis. With 7 parts at 20 mm gaps this
cannot be avoided by rearranging them. A shallower tray, tilted grasps, a smaller clearance margin inside containers,
or a narrower gripper would be needed. No pick-and-place execution is claimed.

## Screenshots (inspected)

All are in `base_suites/`:
- **`preview_industrial_overview.png`:** the full workstation. Table, Franka, grey tray with brass parts in front of
  the robot, and two ribbed blue crates with rims, hand holes and labels.
- **`preview_industrial_tray.png`:** all 7 fittings, separate, in different orientations, resting on the tray floor.
- **`preview_industrial_fittings.png`:** two Type A and two Type B side by side. Male threads, hex flats, grooves, the
  socket's internal thread and the open bores are visible; the silhouettes are clearly different.
- **`preview_industrial_crates.png`:** both crates with readable labels, hand holes, ribs, band and foot.
- **`preview_main.png`:** the base `main` camera; the waste-sorting content is absent as intended.

Two visual problems were found in the renders and fixed:
- the hand holes were invisible in RTX until the meshes were triangulated;
- the tray close-up hid one fitting until its camera was raised.

## File preservation

| Comparison | Result |
|---|---|
| `add_asset.py` | 27 protected files hashed before and after; content and mtime unchanged. Parent ramp project: 51 files unchanged. |
| `preservation_check.json` (baseline taken before the first Isaac run) | 29 files unchanged in content and mtime: every workstation asset, the base scene, both configs, `test_spacer` and its derived scene |
| Previous session's baseline | the 23 workstation files, the base scene and the configs are byte-identical |

## Known approximations

- **Assets:** representative dimensions, not reverse-engineered parts. The threads are visual helices; the colliders
  use the major diameter. The friction values are illustrative.
- **Containers:**
  - Collider interior corners are sharp while the visual corners are rounded, a difference of up to about 6 mm.
  - The hand holes are visual only; the wall colliders are solid.
  - The floor box also covers the recessed foot area.
- **Fitting colliders:** each zone is a 12-gon or hex at the zone's largest radius. Grooves, chamfers and thread
  depth are absent from the colliders, which reach 3.5 % beyond the zone radius at their vertices.
- **Contact offset:** 0.02 m on the container colliders, so impacts resolve without penetration. CCD is off.
- **Scene content:** the waste-sorting objects are deactivated in this derived scene, so the workstation's own 94/39
  suites do not apply to it and were not run on it; they pass on the base scene.
- **Reachability:** endpoint IK only. Grasp physics and trajectories were not evaluated.

## Reused vs. newly written code

**Reused unchanged:**
- `generate_assets.py`: `material`, `box_object`, `text_object`, `world_triangles`, `mass_properties`, `bounds`,
  `export_visual`, `write_asset`, `clear_scene`.
- The registry and asset status, spec hashing and the schema validator.
- `compose_scene.py`'s Sdf layer, references, PhysX combine-mode overrides and camera authoring.
- `render_previews.py`.
- `robot_geometry.RobotModel` (Lula IK and hull clearance) and `layout_geometry`.
- `run_workflow.GpuMonitor` / `parent_hashes`.

**New or extended:**
- **Geometry methods** (`generate_asset.py`): `open_container` (lofted shell, ribs, band, foot, label holders, Boolean
  hand holes), `fitting` (ring mesh with helical threads, chamfered hex, grooves, stepped bore) and `label_plate`.
- **Collider representations:** `container_walls`, `fitting_sections`, `none`, and the optional contact offset.
- **Pure-Python geometry in `asset_lib.py`:** sections, zones, collider pieces, support surfaces and mount points,
  shared by the generator, placement and validation.
- **Placement:** `on_instance`, `attached`, the `lying` rest pose, full-quaternion poses, the piece-based placement
  check and the seeded `scatter`.
- **CLI:** `deactivate-base-prim`, named preview cameras, `set-validation` and `scatter`.
- **Validator:** the new geometry checks, the scene-level checks, and the drop and move tests.
- **`add_asset.py`:** several `--spec` arguments.
- **`open_scene.py`:** skips inactive base objects; its self-test compares each body with its own start height.
- **New scripts:** `reachability_check.py` and `build_industrial_scene.sh`.

## Reproduce / open

```bash
scripts/assets/build_industrial_scene.sh          # config (CLI) → generate (skips current) → compose → validate → previews → reachability
"$ISAACSIM_PYTHON" scripts/workstation/open_scene.py --scene assets/scenes/derived/industrial_brass_sorting.usda
```
