# Derived scene validation: `brass_cad_comparison`

- Generated: 2026-10-28T18:19:47+01:00
- Scene config: `config/scenes/brass_cad_comparison.json`; derived layer: `assets/scenes/derived/brass_cad_comparison.usda`; base scene: `assets/scenes/waste_sorting_workstation.usd`
- **Result: PASS** (76/76 checks passed)
- Physics test: yes

| Group | Check | Result | Key values |
|---|---|---|---|
| structure | `derived_layer_exists` | PASS | path="assets/scenes/derived/brass_cad_comparison.usda" |
| structure | `stage_opens` | PASS |  |
| structure | `all_dependencies_resolve` | PASS | unresolved=[]; layers=66 |
| structure | `local_asset_paths_relative` | PASS | absolute=[]; note="remote URLs are reported, not rejected (the robot is NVIDIA-hosted)" |
| structure | `units_and_default_prim` | PASS |  |
| structure | `sublayers_only_base_scene` | PASS | sublayers=["../waste_sorting_workstation.usd"] |
| structure | `base_scene_unchanged_since_compose` | PASS | composed_against="b7916b35ab719a18c9cf675faf372f00ec1d6cafd297c36d21b43388689443ff"; current="b7916b35ab719a18c9cf675faf372f00ec1d6cafd297c36d21b43388689443ff" |
| structure | `derived_layer_scope` | PASS | authored_outside_allowed_roots=[]; deactivations_with_extra_opinions=[]; allowed_roots=["/World/UserObjects", "/World/Cameras/CadComparison"]; deactivated=[] |
| registry | `brass_adapter_male_current` | PASS | status="current"; spec_file="config/assets/brass_adapter_male.json"; generated_utc="2026-10-27T18:00:01+00:00" |
| registry | `brass_adapter_male_cad_current` | PASS | status="current"; spec_file="config/assets/brass_adapter_male_cad.json"; generated_utc="2026-10-28T17:10:50+00:00" |
| registry | `brass_adapter_male_step_import_current` | PASS | status="current"; spec_file="config/assets/brass_adapter_male_step_import.json"; generated_utc="2026-10-28T17:12:12+00:00" |
| instance:AdapterBlender | `prim_exists` | PASS | path="/World/UserObjects/AdapterBlender" |
| instance:AdapterBlender | `references_library_asset` | PASS | references=["../../library/brass_adapter_male/brass_adapter_male.usd"]; expected="../../library/brass_adapter_male/brass_adapter_male.usd" |
| instance:AdapterBlender | `pose` | PASS | position=[-0.55, -0.12, 0.76225]; expected=[-0.55, -0.12, 0.76225]; rotation_matrix_max_error=1.1102230246251565e-16; rotation_error_deg=0.0; yaw_deg=180.0; tilt_deg=89.99999999999999; pose="lying" |
| instance:AdapterBlender | `visual_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.0215000007301569, 0.04500000178813934]; tolerance_m=0.0005 |
| instance:AdapterBlender | `collider_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.0215000007301569, 0.04500000178813934] |
| instance:AdapterBlender | `colliders` | PASS | count=42; expected=42; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:AdapterBlender | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:AdapterBlender | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:AdapterBlender | `bore_open` | PASS | collider_distance_from_axis_min_m=0.0071000000461936; narrowest_visual_bore_radius_m=0.0065; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:AdapterBlender | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:AdapterBlender | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.04500000178813934; expected_mass_kg=0.045; implied_density_kg_m3=8196.323719995135; diagonal_inertia=[7.97540087660309e-06, 7.975947482918855e-06, 3.485756678855978e-06]; center_of_mass=[-2.1216289951553335e-06, 4.704106686403975e-06, 0.021743351593613625]; nested_rigid_bodies=[] |
| instance:AdapterBlender | `resting_on_tabletop` | PASS | collider_bottom_z=0.7514999999461944; tabletop_z=0.75; gap_m=0.0014999999461944302; expected_gap_m=0.0015 |
| instance:AdapterBlender | `footprint_on_tabletop` | PASS | collider_xy=[[-0.5624130310294198, -0.12], [-0.5375869689705803, -0.07499999821186065]] |
| instance:AdapterBlender | `clearance_to_scene` | PASS | min_gap_m=0.05499999821186065; closest="instance:AdapterFreeCAD"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:AdapterFreeCAD | `prim_exists` | PASS | path="/World/UserObjects/AdapterFreeCAD" |
| instance:AdapterFreeCAD | `references_library_asset` | PASS | references=["../../library/brass_adapter_male_cad/brass_adapter_male_cad.usd"]; expected="../../library/brass_adapter_male_cad/brass_adapter_male_cad.usd" |
| instance:AdapterFreeCAD | `pose` | PASS | position=[-0.55, -0.02, 0.76225]; expected=[-0.55, -0.02, 0.76225]; rotation_matrix_max_error=1.1102230246251565e-16; rotation_error_deg=0.0; yaw_deg=180.0; tilt_deg=89.99999999999999; pose="lying" |
| instance:AdapterFreeCAD | `visual_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826062843203545, 0.0215000007301569, 0.04500000178813934]; tolerance_m=0.0005 |
| instance:AdapterFreeCAD | `collider_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.0215000007301569, 0.04500000178813934] |
| instance:AdapterFreeCAD | `colliders` | PASS | count=42; expected=42; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:AdapterFreeCAD | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:AdapterFreeCAD | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:AdapterFreeCAD | `bore_open` | PASS | collider_distance_from_axis_min_m=0.0071000000461936; narrowest_visual_bore_radius_m=0.0065; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:AdapterFreeCAD | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:AdapterFreeCAD | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.050249695777893066; expected_mass_kg=0.05024969607292468; implied_density_kg_m3=8470.0; diagonal_inertia=[9.259882972401101e-06, 9.259882972401101e-06, 3.988540811405983e-06]; center_of_mass=[-2.7877724000785475e-12, -9.19790265009362e-18, 0.02065603993833065]; nested_rigid_bodies=[] |
| instance:AdapterFreeCAD | `resting_on_tabletop` | PASS | collider_bottom_z=0.7514999999461944; tabletop_z=0.75; gap_m=0.0014999999461944302; expected_gap_m=0.0015 |
| instance:AdapterFreeCAD | `footprint_on_tabletop` | PASS | collider_xy=[[-0.5624130310294198, -0.020000000000000004], [-0.5375869689705803, 0.025000001788139343]] |
| instance:AdapterFreeCAD | `clearance_to_scene` | PASS | min_gap_m=0.05424999784678221; closest="instance:AdapterStepImport"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:AdapterStepImport | `prim_exists` | PASS | path="/World/UserObjects/AdapterStepImport" |
| instance:AdapterStepImport | `references_library_asset` | PASS | references=["../../library/brass_adapter_male_step_import/brass_adapter_male_step_import.usd"]; expected="../../library/brass_adapter_male_step_import/brass_adapter_male_step_import.usd" |
| instance:AdapterStepImport | `pose` | PASS | position=[-0.55, 0.09, 0.7515]; expected=[-0.55, 0.09, 0.7515]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=0.0; tilt_deg=0.0; pose="upright" |
| instance:AdapterStepImport | `visual_dimensions` | PASS | nominal=[[-0.012413, -0.01075, 0.0], [0.012413, 0.01075, 0.045]]; size=[0.024826062843203545, 0.0215000007301569, 0.04500000178813934]; tolerance_m=0.0005 |
| instance:AdapterStepImport | `collider_dimensions` | PASS | nominal=[[-0.012413, -0.01075, 0.0], [0.012413, 0.01075, 0.045]]; size=[0.024826062843203545, 0.0215000007301569, 0.04500000178813934] |
| instance:AdapterStepImport | `colliders` | PASS | count=1; expected=1; representation="convex_hull"; contact_offset_m="PhysX default" |
| instance:AdapterStepImport | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:AdapterStepImport | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:AdapterStepImport | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:AdapterStepImport | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.050249695777893066; expected_mass_kg=0.050249695688834445; implied_density_kg_m3=8470.0; diagonal_inertia=[9.259882972401101e-06, 9.259882972401101e-06, 3.988540811405983e-06]; center_of_mass=[-1.3693972171491264e-12, 2.8577629031873092e-16, 0.02065603993833065]; nested_rigid_bodies=[] |
| instance:AdapterStepImport | `resting_on_tabletop` | PASS | collider_bottom_z=0.7515; tabletop_z=0.75; gap_m=0.0014999999999999458; expected_gap_m=0.0015 |
| instance:AdapterStepImport | `footprint_on_tabletop` | PASS | collider_xy=[[-0.5624130314216018, 0.07924999963492155], [-0.5375869685783983, 0.10075000036507845]] |
| instance:AdapterStepImport | `clearance_to_scene` | PASS | min_gap_m=0.05424999784678221; closest="instance:AdapterFreeCAD"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| preservation | `all_base_prims_present` | PASS | base_prims=783; missing_unexpected=[]; deactivated_roots=[]; deactivated_prims=0; deactivated_roots_inactive=true; note="prims under deactivate_base_prims are intentionally inactive in the derived scene (base file unchanged)" |
| preservation | `base_prims_unchanged` | PASS | prims_compared=783; attributes_compared=7639; differing={}; note="type, world transform, every attribute value, relationships, applied schemas" |
| preservation | `new_prims_only_under_allowed_roots` | PASS | new_prims=114; outside=[]; allowed_roots=["/World/UserObjects", "/World/Cameras/CadComparison"] |
| preservation | `robot_unchanged` | PASS | robot_prims=366 |
| scene | `same_envelope_brass_adapter_male_vs_brass_adapter_male_cad` | PASS | nominal_max_diff_m=0.0; measured_max_diff_m=9.313225746154785e-10; tolerance_m=0.0005; backends=["blender", "freecad"]; volume_m3=[5.490266311739419e-06, 5.9313724847185e-06]; volume_rel_diff=0.08034331085832706; mass_kg=[0.045, 0.05024969607292468]; mass_rel_diff=0.11665991273165953; inertia_rel_diff=[0.1610554607575542, 0.16097586077407164, 0.14423957304023674]; triangles=[8640, 9960]; note="variants of one part: the envelope must match; volume / mass / inertia differences are reported, not judged" |
| scene | `same_envelope_brass_adapter_male_cad_vs_brass_adapter_male_step_import` | PASS | nominal_max_diff_m=3.0787576953128504e-08; measured_max_diff_m=0.0; tolerance_m=0.0005; backends=["freecad", "import"]; volume_m3=[5.9313724847185e-06, 5.931372483898831e-06]; volume_rel_diff=-1.3819222279582586e-10; mass_kg=[0.05024969607292468, 0.050249695688834445]; mass_rel_diff=-7.643632934307277e-09; inertia_rel_diff=[-1.9432716281181017e-09, -1.8503922857677719e-09, -6.456424423628207e-09]; triangles=[9960, 9960]; note="variants of one part: the envelope must match; volume / mass / inertia differences are reported, not judged" |
| physics:AdapterBlender | `settled_on_tabletop` | PASS | final_bottom_gap_mm=-0.0004; height_change_from_authored_mm=-1.4995; expected_drop_mm=1.5; pose="lying" |
| physics:AdapterBlender | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0267 |
| physics:AdapterBlender | `no_horizontal_drift` | PASS | drift_mm=0.0 |
| physics:AdapterBlender | `at_rest` | PASS | mean_speed_last_0_5s="6.89e-05" |
| physics:AdapterBlender | `supported_by_tabletop_force` | PASS | normal_force_N=0.44146; weight_N=0.44145 |
| physics:AdapterFreeCAD | `settled_on_tabletop` | PASS | final_bottom_gap_mm=-0.0004; height_change_from_authored_mm=-1.4991; expected_drop_mm=1.5; pose="lying" |
| physics:AdapterFreeCAD | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0273 |
| physics:AdapterFreeCAD | `no_horizontal_drift` | PASS | drift_mm=0.001 |
| physics:AdapterFreeCAD | `at_rest` | PASS | mean_speed_last_0_5s="1.06e-04" |
| physics:AdapterFreeCAD | `supported_by_tabletop_force` | PASS | normal_force_N=0.4929; weight_N=0.49295 |
| physics:AdapterStepImport | `settled_on_tabletop` | PASS | final_bottom_gap_mm=-0.0001; height_change_from_authored_mm=-1.5001; expected_drop_mm=1.5 |
| physics:AdapterStepImport | `remains_upright` | PASS | max_tilt_deg=0.0087 |
| physics:AdapterStepImport | `no_horizontal_drift` | PASS | drift_mm=0.001 |
| physics:AdapterStepImport | `at_rest` | PASS | mean_speed_last_0_5s="2.93e-07" |
| physics:AdapterStepImport | `supported_by_tabletop_force` | PASS | normal_force_N=0.49295; weight_N=0.49295 |
| physics:base_objects | `GlassBottle_undisturbed` | PASS | drift_from_authored_mm=0.0011; max_tilt_deg=0.0097; height_change_from_authored_mm=-1.4976 |
| physics:base_objects | `PlasticBottle_undisturbed` | PASS | drift_from_authored_mm=0.0013; max_tilt_deg=0.0066; height_change_from_authored_mm=-1.4991 |
| physics:base_objects | `PaperCup_undisturbed` | PASS | drift_from_authored_mm=0.0001; max_tilt_deg=0.0007; height_change_from_authored_mm=-1.387 |

Scope: these checks cover the added instances and the integrity of the base scene. They do not re-run the workstation's own 94 static / 39 dynamic checks (run those with a config copy that points paths.scene at the derived layer; scripts/assets/add_asset.py --base-suites does this) and do not imply physical realism beyond the modelled rigid-body approximation.
