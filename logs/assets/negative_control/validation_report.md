# Derived scene validation: `negative_control`

- Generated: 2026-10-28T18:58:40+01:00
- Scene config: `config/scenes/negative_control.json`; derived layer: `assets/scenes/derived/negative_control.usda`; base scene: `assets/scenes/waste_sorting_workstation.usd`
- **Result: FAIL** (38/41 checks passed)
- Physics test: no (--no-physics or disabled by spec)

| Group | Check | Result | Key values |
|---|---|---|---|
| structure | `derived_layer_exists` | PASS | path="assets/scenes/derived/negative_control.usda" |
| structure | `stage_opens` | PASS |  |
| structure | `all_dependencies_resolve` | PASS | unresolved=[]; layers=62 |
| structure | `local_asset_paths_relative` | PASS | absolute=[]; note="remote URLs are reported, not rejected (the robot is NVIDIA-hosted)" |
| structure | `units_and_default_prim` | PASS |  |
| structure | `sublayers_only_base_scene` | PASS | sublayers=["../waste_sorting_workstation.usd"] |
| structure | `base_scene_unchanged_since_compose` | PASS | composed_against="b7916b35ab719a18c9cf675faf372f00ec1d6cafd297c36d21b43388689443ff"; current="b7916b35ab719a18c9cf675faf372f00ec1d6cafd297c36d21b43388689443ff" |
| structure | `derived_layer_scope` | **FAIL** | authored_outside_allowed_roots=["/World/Objects/PlasticBottle", "/World/Objects"]; deactivations_with_extra_opinions=[]; allowed_roots=["/World/UserObjects", "/World/Cameras/AssetPreview"]; deactivated=[] |
| registry | `test_spacer_current` | PASS | status="current"; spec_file="config/assets/test_spacer.json"; generated_utc="2026-10-27T16:25:47+00:00" |
| instance:TestSpacer_0 | `prim_exists` | PASS | path="/World/UserObjects/TestSpacer_0" |
| instance:TestSpacer_0 | `references_library_asset` | PASS | references=["../../library/test_spacer/test_spacer.usd"]; expected="../../library/test_spacer/test_spacer.usd" |
| instance:TestSpacer_0 | `pose` | PASS | position=[-0.12, 0.1, 0.7515]; expected=[-0.12, 0.1, 0.7515]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=0.0; tilt_deg=0.0; pose="upright" |
| instance:TestSpacer_0 | `visual_dimensions` | PASS | nominal=[[-0.015, -0.015, 0.0], [0.015, 0.015, 0.025]]; size=[0.029999999329447746, 0.029999999329447746, 0.02500000037252903]; tolerance_m=0.0005 |
| instance:TestSpacer_0 | `collider_dimensions` | PASS | nominal=[[-0.015, -0.015, 0.0], [0.015, 0.015, 0.025]]; size=[0.02999999960736368, 0.029999999607363676, 0.02500000037252903] |
| instance:TestSpacer_0 | `colliders` | PASS | count=12; expected=12; representation="ring_segments"; contact_offset_m="PhysX default" |
| instance:TestSpacer_0 | `physics_material` | PASS | bound=true; values=[[0.6, 0.5, 0.1]]; expected=[[0.6, 0.5, 0.1]] |
| instance:TestSpacer_0 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:TestSpacer_0 | `bore_open` | PASS | collider_distance_from_axis_m=0.006000000202341451; bore_radius_m=0.006 |
| instance:TestSpacer_0 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:TestSpacer_0 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.11619310826063156; expected_mass_kg=0.1161931081556839; implied_density_kg_m3=7850.0; diagonal_inertia=[1.3611704162030946e-05, 1.3611704162030946e-05, 1.5119959243747871e-05]; center_of_mass=[6.374300329243087e-20, 1.030038902963415e-18, 0.012500000186264515]; nested_rigid_bodies=[] |
| instance:TestSpacer_0 | `resting_on_tabletop` | PASS | collider_bottom_z=0.7514999998137354; tabletop_z=0.75; gap_m=0.0014999998137353865; expected_gap_m=0.0015 |
| instance:TestSpacer_0 | `footprint_on_tabletop` | PASS | collider_xy=[[-0.13499999980368182, 0.08500000019631816], [-0.10500000019631815, 0.11499999980368185]] |
| instance:TestSpacer_0 | `clearance_to_scene` | **FAIL** | min_gap_m=0.002500001388411041; closest="PlasticBottle"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:TestSpacer_1 | `prim_exists` | PASS | path="/World/UserObjects/TestSpacer_1" |
| instance:TestSpacer_1 | `references_library_asset` | PASS | references=["../../library/test_spacer/test_spacer.usd"]; expected="../../library/test_spacer/test_spacer.usd" |
| instance:TestSpacer_1 | `pose` | PASS | position=[-0.45, -0.22, 0.7515]; expected=[-0.45, -0.22, 0.7515]; rotation_matrix_max_error=5.551115123125783e-17; rotation_error_deg=0.0; yaw_deg=29.999999999999993; tilt_deg=0.0; pose="upright" |
| instance:TestSpacer_1 | `visual_dimensions` | PASS | nominal=[[-0.015, -0.015, 0.0], [0.015, 0.015, 0.025]]; size=[0.029999999329447746, 0.029999999329447746, 0.02500000037252903]; tolerance_m=0.0005 |
| instance:TestSpacer_1 | `collider_dimensions` | PASS | nominal=[[-0.015, -0.015, 0.0], [0.015, 0.015, 0.025]]; size=[0.029999999607363624, 0.029999999607363704, 0.02500000037252903] |
| instance:TestSpacer_1 | `colliders` | PASS | count=12; expected=12; representation="ring_segments"; contact_offset_m="PhysX default" |
| instance:TestSpacer_1 | `physics_material` | PASS | bound=true; values=[[0.6, 0.5, 0.1]]; expected=[[0.6, 0.5, 0.1]] |
| instance:TestSpacer_1 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:TestSpacer_1 | `bore_open` | PASS | collider_distance_from_axis_m=0.006000000202341397; bore_radius_m=0.006 |
| instance:TestSpacer_1 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:TestSpacer_1 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.11619310826063156; expected_mass_kg=0.1161931081556839; implied_density_kg_m3=7850.0; diagonal_inertia=[1.3611704162030946e-05, 1.3611704162030946e-05, 1.5119959243747871e-05]; center_of_mass=[6.374300329243087e-20, 1.030038902963415e-18, 0.012500000186264515]; nested_rigid_bodies=[] |
| instance:TestSpacer_1 | `resting_on_tabletop` | PASS | collider_bottom_z=0.7514999998137354; tabletop_z=0.75; gap_m=0.0014999998137353865; expected_gap_m=0.0015 |
| instance:TestSpacer_1 | `footprint_on_tabletop` | PASS | collider_xy=[[-0.46499999980368184, -0.23499999980368183], [-0.4350000001963182, -0.20500000019631817]] |
| instance:TestSpacer_1 | `clearance_to_scene` | PASS | min_gap_m=0.30200961928500913; closest="instance:TestSpacer_0"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| preservation | `all_base_prims_present` | PASS | base_prims=783; missing_unexpected=[]; deactivated_roots=[]; deactivated_prims=0; deactivated_roots_inactive=true; note="prims under deactivate_base_prims are intentionally inactive in the derived scene (base file unchanged)" |
| preservation | `base_prims_unchanged` | **FAIL** | prims_compared=783; attributes_compared=7639; note="type, world transform, every attribute value, relationships, applied schemas" |
| preservation | `new_prims_only_under_allowed_roots` | PASS | new_prims=68; outside=[]; allowed_roots=["/World/UserObjects", "/World/Cameras/AssetPreview"] |
| preservation | `robot_unchanged` | PASS | robot_prims=366 |

Scope: these checks cover the added instances and the integrity of the base scene. They do not re-run the workstation's own 94 static / 39 dynamic checks (run those with a config copy that points paths.scene at the derived layer; scripts/assets/add_asset.py --base-suites does this) and do not imply physical realism beyond the modelled rigid-body approximation.
