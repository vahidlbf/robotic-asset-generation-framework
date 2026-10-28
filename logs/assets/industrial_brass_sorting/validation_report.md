# Derived scene validation: `industrial_brass_sorting`

- Generated: 2026-10-28T18:21:07+01:00
- Scene config: `config/scenes/industrial_brass_sorting.json`; derived layer: `assets/scenes/derived/industrial_brass_sorting.usda`; base scene: `assets/scenes/waste_sorting_workstation.usd`
- **Result: PASS** (238/238 checks passed)
- Physics test: yes

| Group | Check | Result | Key values |
|---|---|---|---|
| structure | `derived_layer_exists` | PASS | path="assets/scenes/derived/industrial_brass_sorting.usda" |
| structure | `stage_opens` | PASS |  |
| structure | `all_dependencies_resolve` | PASS | unresolved=[]; layers=72 |
| structure | `local_asset_paths_relative` | PASS | absolute=[]; note="remote URLs are reported, not rejected (the robot is NVIDIA-hosted)" |
| structure | `units_and_default_prim` | PASS |  |
| structure | `sublayers_only_base_scene` | PASS | sublayers=["../waste_sorting_workstation.usd"] |
| structure | `base_scene_unchanged_since_compose` | PASS | composed_against="b7916b35ab719a18c9cf675faf372f00ec1d6cafd297c36d21b43388689443ff"; current="b7916b35ab719a18c9cf675faf372f00ec1d6cafd297c36d21b43388689443ff" |
| structure | `derived_layer_scope` | PASS | authored_outside_allowed_roots=[]; deactivations_with_extra_opinions=[]; deactivated=["/World/Objects", "/World/Targets", "/World/Workstation/SortingZone"] |
| registry | `brass_adapter_female_current` | PASS | status="current"; spec_file="config/assets/brass_adapter_female.json"; generated_utc="2026-10-27T18:03:43+00:00" |
| registry | `brass_adapter_male_current` | PASS | status="current"; spec_file="config/assets/brass_adapter_male.json"; generated_utc="2026-10-27T18:00:01+00:00" |
| registry | `industrial_blue_crate_current` | PASS | status="current"; spec_file="config/assets/industrial_blue_crate.json"; generated_utc="2026-10-27T18:15:46+00:00"; generation_checks={"dimensions": true, "closed_manifold_mesh": true, "mesh_volume_matches_geometry": true, "usd_asset": true} |
| registry | `industrial_gray_tray_current` | PASS | status="current"; spec_file="config/assets/industrial_gray_tray.json"; generated_utc="2026-10-27T18:15:48+00:00"; generation_checks={"dimensions": true, "closed_manifold_mesh": true, "mesh_volume_matches_geometry": true, "usd_asset": true} |
| registry | `label_bin_a_current` | PASS | status="current"; spec_file="config/assets/label_bin_a.json"; generated_utc="2026-10-27T18:00:07+00:00"; generation_checks={"dimensions": true, "closed_manifold_mesh": true, "mesh_volume_matches_geometry": true, "usd_asset": true} |
| registry | `label_bin_b_current` | PASS | status="current"; spec_file="config/assets/label_bin_b.json"; generated_utc="2026-10-27T18:00:09+00:00"; generation_checks={"dimensions": true, "closed_manifold_mesh": true, "mesh_volume_matches_geometry": true, "usd_asset": true} |
| instance:InputTray | `prim_exists` | PASS | path="/World/UserObjects/InputTray" |
| instance:InputTray | `references_library_asset` | PASS | references=["../../library/industrial_gray_tray/industrial_gray_tray.usd"]; expected="../../library/industrial_gray_tray/industrial_gray_tray.usd" |
| instance:InputTray | `pose` | PASS | position=[0.42, -0.215, 0.75]; expected=[0.42, -0.215, 0.75]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=0.0; tilt_deg=0.0; pose="upright" |
| instance:InputTray | `visual_dimensions` | PASS | nominal=[[-0.175, -0.15, 0.0], [0.175, 0.15, 0.1]]; size=[0.3499999940395355, 0.30000001192092896, 0.10000000149011612]; tolerance_m=0.0005 |
| instance:InputTray | `collider_dimensions` | PASS | nominal=[[-0.175, -0.15, 0.0], [0.175, 0.15, 0.1]]; size=[0.3499999940395355, 0.30000001192092896, 0.10000000143423682] |
| instance:InputTray | `colliders` | PASS | count=5; expected=5; representation="container_walls"; contact_offset_m=[0.02] |
| instance:InputTray | `physics_material` | PASS | bound=true; values=[[0.4, 0.35, 0.05]]; expected=[[0.4, 0.35, 0.05]] |
| instance:InputTray | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:InputTray | `open_top` | PASS | max_intrusion_into_floor_column_m=7.112268995967952e-09; walls=["WallNegX", "WallNegY", "WallPosX", "WallPosY"]; floor_top_local_z=0.004999999944120592; inner_floor_half_m=[0.1593569528653665, 0.1343569528653665]; note="no collider above the floor reaches into the vertical column over the inner floor (no lid, opening clear)" |
| instance:InputTray | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:InputTray | `static_body` | PASS |  |
| instance:InputTray | `resting_on_tabletop` | PASS | collider_bottom_z=0.7500000000558793; tabletop_z=0.75; gap_m=5.587930118622353e-11; expected_gap_m=0.0 |
| instance:InputTray | `footprint_on_tabletop` | PASS | collider_xy=[[0.24500000298023222, -0.36500000596046445], [0.5949999970197677, -0.06499999403953552]] |
| instance:InputTray | `clearance_to_scene` | PASS | min_gap_m=0.02100149344985519; closest="instance:FittingB_2"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:sorting_bin_A | `prim_exists` | PASS | path="/World/UserObjects/sorting_bin_A" |
| instance:sorting_bin_A | `references_library_asset` | PASS | references=["../../library/industrial_blue_crate/industrial_blue_crate.usd"]; expected="../../library/industrial_blue_crate/industrial_blue_crate.usd" |
| instance:sorting_bin_A | `pose` | PASS | position=[-0.03, -0.2, 0.75]; expected=[-0.03, -0.2, 0.75]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=0.0; tilt_deg=0.0; pose="upright" |
| instance:sorting_bin_A | `visual_dimensions` | PASS | nominal=[[-0.2, -0.15, 0.0], [0.2, 0.15, 0.22]]; size=[0.4000000059604645, 0.30000001192092896, 0.2199999988079071]; tolerance_m=0.0005 |
| instance:sorting_bin_A | `collider_dimensions` | PASS | nominal=[[-0.2, -0.15, 0.0], [0.2, 0.15, 0.22]]; size=[0.4000000059604645, 0.30000001192092896, 0.2199999991878867] |
| instance:sorting_bin_A | `colliders` | PASS | count=5; expected=5; representation="container_walls"; contact_offset_m=[0.02] |
| instance:sorting_bin_A | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.1]]; expected=[[0.35, 0.3, 0.1]] |
| instance:sorting_bin_A | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:sorting_bin_A | `open_top` | PASS | max_intrusion_into_floor_column_m=4.6088016736334225e-10; walls=["WallNegX", "WallNegY", "WallPosX", "WallPosY"]; floor_top_local_z=0.016000000379979618; inner_floor_half_m=[0.17909316764666355, 0.12909316764666354]; note="no collider above the floor reaches into the vertical column over the inner floor (no lid, opening clear)" |
| instance:sorting_bin_A | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:sorting_bin_A | `static_body` | PASS |  |
| instance:sorting_bin_A | `resting_on_tabletop` | PASS | collider_bottom_z=0.7499999996200204; tabletop_z=0.75; gap_m=-3.799796033376879e-10; expected_gap_m=0.0 |
| instance:sorting_bin_A | `footprint_on_tabletop` | PASS | collider_xy=[[-0.23000000298023224, -0.3500000059604645], [0.17000000298023224, -0.049999994039535534]] |
| instance:sorting_bin_A | `clearance_to_scene` | PASS | min_gap_m=0.07499999999999998; closest="instance:InputTray"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:sorting_bin_B | `prim_exists` | PASS | path="/World/UserObjects/sorting_bin_B" |
| instance:sorting_bin_B | `references_library_asset` | PASS | references=["../../library/industrial_blue_crate/industrial_blue_crate.usd"]; expected="../../library/industrial_blue_crate/industrial_blue_crate.usd" |
| instance:sorting_bin_B | `pose` | PASS | position=[-0.03, 0.2, 0.75]; expected=[-0.03, 0.2, 0.75]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=0.0; tilt_deg=0.0; pose="upright" |
| instance:sorting_bin_B | `visual_dimensions` | PASS | nominal=[[-0.2, -0.15, 0.0], [0.2, 0.15, 0.22]]; size=[0.4000000059604645, 0.30000001192092896, 0.2199999988079071]; tolerance_m=0.0005 |
| instance:sorting_bin_B | `collider_dimensions` | PASS | nominal=[[-0.2, -0.15, 0.0], [0.2, 0.15, 0.22]]; size=[0.4000000059604645, 0.30000001192092896, 0.2199999991878867] |
| instance:sorting_bin_B | `colliders` | PASS | count=5; expected=5; representation="container_walls"; contact_offset_m=[0.02] |
| instance:sorting_bin_B | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.1]]; expected=[[0.35, 0.3, 0.1]] |
| instance:sorting_bin_B | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:sorting_bin_B | `open_top` | PASS | max_intrusion_into_floor_column_m=4.6088016736334225e-10; walls=["WallNegX", "WallNegY", "WallPosX", "WallPosY"]; floor_top_local_z=0.016000000379979618; inner_floor_half_m=[0.17909316764666355, 0.12909316764666354]; note="no collider above the floor reaches into the vertical column over the inner floor (no lid, opening clear)" |
| instance:sorting_bin_B | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:sorting_bin_B | `static_body` | PASS |  |
| instance:sorting_bin_B | `resting_on_tabletop` | PASS | collider_bottom_z=0.7499999996200204; tabletop_z=0.75; gap_m=-3.799796033376879e-10; expected_gap_m=0.0 |
| instance:sorting_bin_B | `footprint_on_tabletop` | PASS | collider_xy=[[-0.23000000298023224, 0.049999994039535534], [0.17000000298023224, 0.3500000059604645]] |
| instance:sorting_bin_B | `clearance_to_scene` | PASS | min_gap_m=0.09999998807907107; closest="instance:sorting_bin_A"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:label_A | `prim_exists` | PASS | path="/World/UserObjects/label_A" |
| instance:label_A | `references_library_asset` | PASS | references=["../../library/label_bin_a/label_bin_a.usd"]; expected="../../library/label_bin_a/label_bin_a.usd" |
| instance:label_A | `pose` | PASS | position=[0.16444373399640416, -0.2, 0.845]; expected=[0.16444373399640416, -0.2, 0.845]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=89.99999999999999; tilt_deg=0.0; pose="upright" |
| instance:label_A | `visual_dimensions` | PASS | nominal=[[-0.065, -0.0015, 0.0], [0.065, 0.0015, 0.05]]; size=[0.12999999523162842, 0.003000000724568963, 0.05000000074505806]; tolerance_m=0.0005 |
| instance:label_A | `colliders` | PASS | count=0; expected=0; representation="none"; contact_offset_m="PhysX default" |
| instance:label_A | `visual_material_bound` | PASS | visual_meshes=2 |
| instance:label_A | `static_body` | PASS |  |
| instance:label_A | `on_mount_point` | PASS | mount="label_+x"; support="sorting_bin_A"; mount_world=[0.16294373399640416, -0.2, 0.87]; attach_point_world=[0.16294373399640416, -0.2, 0.87]; colliders=0; note="visual-only: no colliders, no rigid body; back face on the label holder" |
| instance:label_B | `prim_exists` | PASS | path="/World/UserObjects/label_B" |
| instance:label_B | `references_library_asset` | PASS | references=["../../library/label_bin_b/label_bin_b.usd"]; expected="../../library/label_bin_b/label_bin_b.usd" |
| instance:label_B | `pose` | PASS | position=[0.16444373399640416, 0.2, 0.845]; expected=[0.16444373399640416, 0.2, 0.845]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=89.99999999999999; tilt_deg=0.0; pose="upright" |
| instance:label_B | `visual_dimensions` | PASS | nominal=[[-0.065, -0.0015, 0.0], [0.065, 0.0015, 0.05]]; size=[0.12999999523162842, 0.003000000724568963, 0.05000000074505806]; tolerance_m=0.0005 |
| instance:label_B | `colliders` | PASS | count=0; expected=0; representation="none"; contact_offset_m="PhysX default" |
| instance:label_B | `visual_material_bound` | PASS | visual_meshes=2 |
| instance:label_B | `static_body` | PASS |  |
| instance:label_B | `on_mount_point` | PASS | mount="label_+x"; support="sorting_bin_B"; mount_world=[0.16294373399640416, 0.2, 0.87]; attach_point_world=[0.16294373399640416, 0.2, 0.87]; colliders=0; note="visual-only: no colliders, no rigid body; back face on the label holder" |
| instance:FittingA_0 | `prim_exists` | PASS | path="/World/UserObjects/FittingA_0" |
| instance:FittingA_0 | `references_library_asset` | PASS | references=["../../library/brass_adapter_male/brass_adapter_male.usd"]; expected="../../library/brass_adapter_male/brass_adapter_male.usd" |
| instance:FittingA_0 | `pose` | PASS | position=[0.4048, -0.1989, 0.76725]; expected=[0.4048, -0.1989, 0.76725]; rotation_matrix_max_error=0.0; rotation_error_deg=0.0; yaw_deg=-117.30000000000001; tilt_deg=90.0; pose="lying" |
| instance:FittingA_0 | `visual_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.0215000007301569, 0.04500000178813934]; tolerance_m=0.0005 |
| instance:FittingA_0 | `collider_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.0215000007301569, 0.04500000178813934] |
| instance:FittingA_0 | `colliders` | PASS | count=42; expected=42; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:FittingA_0 | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:FittingA_0 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:FittingA_0 | `bore_open` | PASS | collider_distance_from_axis_min_m=0.007100000046193544; narrowest_visual_bore_radius_m=0.0065; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:FittingA_0 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:FittingA_0 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.04500000178813934; expected_mass_kg=0.045; implied_density_kg_m3=8196.323719995135; diagonal_inertia=[7.97540087660309e-06, 7.975947482918855e-06, 3.485756678855978e-06]; center_of_mass=[-2.1216289951553335e-06, 4.704106686403975e-06, 0.021743351593613625]; nested_rigid_bodies=[] |
| instance:FittingA_0 | `resting_on_support` | PASS | collider_bottom_z=0.7564999999461944; support_surface_z=0.7549999999441206; gap_m=0.0015000000020738424; expected_gap_m=0.0015; support="InputTray" |
| instance:FittingA_0 | `inside_support` | PASS | margin_to_support_edge_m=0.10894424404906655; required_m=0.02; support="InputTray"; note="every collider vertex inside the support surface, at least min_object_gap_m from its edge" |
| instance:FittingA_0 | `clearance_to_scene` | PASS | min_gap_m=0.021244328374462523; closest="instance:FittingA_1"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:FittingA_1 | `prim_exists` | PASS | path="/World/UserObjects/FittingA_1" |
| instance:FittingA_1 | `references_library_asset` | PASS | references=["../../library/brass_adapter_male/brass_adapter_male.usd"]; expected="../../library/brass_adapter_male/brass_adapter_male.usd" |
| instance:FittingA_1 | `pose` | PASS | position=[0.4691, -0.1839, 0.76725]; expected=[0.4691, -0.1839, 0.76725]; rotation_matrix_max_error=2.220446049250313e-16; rotation_error_deg=0.0; yaw_deg=146.7; tilt_deg=89.99999999999999; pose="lying" |
| instance:FittingA_1 | `visual_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.0248260609805584, 0.021500000730156916, 0.04500000178813934]; tolerance_m=0.0005 |
| instance:FittingA_1 | `collider_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.021500000730156912, 0.04500000178813934] |
| instance:FittingA_1 | `colliders` | PASS | count=42; expected=42; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:FittingA_1 | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:FittingA_1 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:FittingA_1 | `bore_open` | PASS | collider_distance_from_axis_min_m=0.007100000046193489; narrowest_visual_bore_radius_m=0.0065; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:FittingA_1 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:FittingA_1 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.04500000178813934; expected_mass_kg=0.045; implied_density_kg_m3=8196.323719995135; diagonal_inertia=[7.97540087660309e-06, 7.975947482918855e-06, 3.485756678855978e-06]; center_of_mass=[-2.1216289951553335e-06, 4.704106686403975e-06, 0.021743351593613625]; nested_rigid_bodies=[] |
| instance:FittingA_1 | `resting_on_support` | PASS | collider_bottom_z=0.7564999999461944; support_surface_z=0.7549999999441206; gap_m=0.0015000000020738424; expected_gap_m=0.0015; support="InputTray" |
| instance:FittingA_1 | `inside_support` | PASS | margin_to_support_edge_m=0.060978925914717624; required_m=0.02; support="InputTray"; note="every collider vertex inside the support surface, at least min_object_gap_m from its edge" |
| instance:FittingA_1 | `clearance_to_scene` | PASS | min_gap_m=0.021244328374462523; closest="instance:FittingA_0"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:FittingA_2 | `prim_exists` | PASS | path="/World/UserObjects/FittingA_2" |
| instance:FittingA_2 | `references_library_asset` | PASS | references=["../../library/brass_adapter_male/brass_adapter_male.usd"]; expected="../../library/brass_adapter_male/brass_adapter_male.usd" |
| instance:FittingA_2 | `pose` | PASS | position=[0.5291, -0.2099, 0.76725]; expected=[0.5291, -0.2099, 0.76725]; rotation_matrix_max_error=4.440892098500626e-16; rotation_error_deg=0.0; yaw_deg=140.50000000000003; tilt_deg=90.00000000000003; pose="lying" |
| instance:FittingA_2 | `visual_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.0248260609805584, 0.021500000730156902, 0.04500000178813934]; tolerance_m=0.0005 |
| instance:FittingA_2 | `collider_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.021500000730156902, 0.04500000178813934] |
| instance:FittingA_2 | `colliders` | PASS | count=42; expected=42; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:FittingA_2 | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:FittingA_2 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:FittingA_2 | `bore_open` | PASS | collider_distance_from_axis_min_m=0.007100000046193489; narrowest_visual_bore_radius_m=0.0065; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:FittingA_2 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:FittingA_2 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.04500000178813934; expected_mass_kg=0.045; implied_density_kg_m3=8196.323719995135; diagonal_inertia=[7.97540087660309e-06, 7.975947482918855e-06, 3.485756678855978e-06]; center_of_mass=[-2.1216289951553335e-06, 4.704106686403975e-06, 0.021743351593613625]; nested_rigid_bodies=[] |
| instance:FittingA_2 | `resting_on_support` | PASS | collider_bottom_z=0.7564999999461944; support_surface_z=0.7549999999441206; gap_m=0.0015000000020738424; expected_gap_m=0.0015; support="InputTray" |
| instance:FittingA_2 | `inside_support` | PASS | margin_to_support_edge_m=0.04217032704209833; required_m=0.02; support="InputTray"; note="every collider vertex inside the support surface, at least min_object_gap_m from its edge" |
| instance:FittingA_2 | `clearance_to_scene` | PASS | min_gap_m=0.0239249505393061; closest="instance:FittingA_1"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:FittingA_3 | `prim_exists` | PASS | path="/World/UserObjects/FittingA_3" |
| instance:FittingA_3 | `references_library_asset` | PASS | references=["../../library/brass_adapter_male/brass_adapter_male.usd"]; expected="../../library/brass_adapter_male/brass_adapter_male.usd" |
| instance:FittingA_3 | `pose` | PASS | position=[0.3416, -0.1457, 0.76725]; expected=[0.3416, -0.1457, 0.76725]; rotation_matrix_max_error=4.718447854656915e-16; rotation_error_deg=0.0; yaw_deg=-85.40000000000006; tilt_deg=89.99999999999997; pose="lying" |
| instance:FittingA_3 | `visual_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.0215000007301569, 0.04500000178813934]; tolerance_m=0.0005 |
| instance:FittingA_3 | `collider_dimensions` | PASS | nominal=[[-0.012413030787576954, -0.01075, 0.0], [0.012413030787576954, 0.01075, 0.045]]; size=[0.024826060980558395, 0.0215000007301569, 0.04500000178813934] |
| instance:FittingA_3 | `colliders` | PASS | count=42; expected=42; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:FittingA_3 | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:FittingA_3 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:FittingA_3 | `bore_open` | PASS | collider_distance_from_axis_min_m=0.007100000046193544; narrowest_visual_bore_radius_m=0.0065; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:FittingA_3 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:FittingA_3 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.04500000178813934; expected_mass_kg=0.045; implied_density_kg_m3=8196.323719995135; diagonal_inertia=[7.97540087660309e-06, 7.975947482918855e-06, 3.485756678855978e-06]; center_of_mass=[-2.1216289951553335e-06, 4.704106686403975e-06, 0.021743351593613625]; nested_rigid_bodies=[] |
| instance:FittingA_3 | `resting_on_support` | PASS | collider_bottom_z=0.7564999999461944; support_surface_z=0.7549999999441206; gap_m=0.0015000000020738424; expected_gap_m=0.0015; support="InputTray" |
| instance:FittingA_3 | `inside_support` | PASS | margin_to_support_edge_m=0.035420210660375595; required_m=0.02; support="InputTray"; note="every collider vertex inside the support surface, at least min_object_gap_m from its edge" |
| instance:FittingA_3 | `clearance_to_scene` | PASS | min_gap_m=0.03542020950857111; closest="instance:InputTray"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:FittingB_0 | `prim_exists` | PASS | path="/World/UserObjects/FittingB_0" |
| instance:FittingB_0 | `references_library_asset` | PASS | references=["../../library/brass_adapter_female/brass_adapter_female.usd"]; expected="../../library/brass_adapter_female/brass_adapter_female.usd" |
| instance:FittingB_0 | `pose` | PASS | position=[0.3783, -0.3032, 0.7650208496083888]; expected=[0.3783, -0.3032, 0.7650208496083888]; rotation_matrix_max_error=3.3306690738754696e-16; rotation_error_deg=0.0; yaw_deg=7.746595349066883; tilt_deg=77.9052429229879; pose="lying" |
| instance:FittingB_0 | `visual_dimensions` | PASS | nominal=[[-0.016, -0.016, 0.0], [0.016, 0.016, 0.05500000000000001]]; size=[0.03200000151991844, 0.03200000151991844, 0.054999999701976776]; tolerance_m=0.0005 |
| instance:FittingB_0 | `collider_dimensions` | PASS | nominal=[[-0.016, -0.016, 0.0], [0.016, 0.016, 0.05500000000000001]]; size=[0.03200000151991844, 0.03200000151991844, 0.054999999701976776] |
| instance:FittingB_0 | `colliders` | PASS | count=54; expected=54; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:FittingB_0 | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:FittingB_0 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:FittingB_0 | `bore_open` | PASS | collider_distance_from_axis_min_m=0.006599999952221499; narrowest_visual_bore_radius_m=0.006; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:FittingB_0 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:FittingB_0 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.07500000298023224; expected_mass_kg=0.075; implied_density_kg_m3=8482.250060807057; diagonal_inertia=[2.0182251319056377e-05, 2.018201666942332e-05, 1.0432720955577679e-05]; center_of_mass=[-5.120389687363058e-06, -3.175144229317084e-06, 0.02944529801607132]; nested_rigid_bodies=[] |
| instance:FittingB_0 | `resting_on_support` | PASS | collider_bottom_z=0.7564999997772812; support_surface_z=0.7549999999441206; gap_m=0.0014999998331606257; expected_gap_m=0.0015; support="InputTray" |
| instance:FittingB_0 | `inside_support` | PASS | margin_to_support_edge_m=0.04361944885972879; required_m=0.02; support="InputTray"; note="every collider vertex inside the support surface, at least min_object_gap_m from its edge" |
| instance:FittingB_0 | `clearance_to_scene` | PASS | min_gap_m=0.022675691279384458; closest="instance:FittingB_1"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:FittingB_1 | `prim_exists` | PASS | path="/World/UserObjects/FittingB_1" |
| instance:FittingB_1 | `references_library_asset` | PASS | references=["../../library/brass_adapter_female/brass_adapter_female.usd"]; expected="../../library/brass_adapter_female/brass_adapter_female.usd" |
| instance:FittingB_1 | `pose` | PASS | position=[0.3173, -0.2195, 0.7650208496083888]; expected=[0.3173, -0.2195, 0.7650208496083888]; rotation_matrix_max_error=6.661338147750939e-16; rotation_error_deg=1.2074182697257333e-06; yaw_deg=-145.15340465093314; tilt_deg=77.9052429229879; pose="lying" |
| instance:FittingB_1 | `visual_dimensions` | PASS | nominal=[[-0.016, -0.016, 0.0], [0.016, 0.016, 0.05500000000000001]]; size=[0.03200000151991844, 0.03200000151991844, 0.05499999970197678]; tolerance_m=0.0005 |
| instance:FittingB_1 | `collider_dimensions` | PASS | nominal=[[-0.016, -0.016, 0.0], [0.016, 0.016, 0.05500000000000001]]; size=[0.03200000151991844, 0.03200000151991844, 0.05499999970197678] |
| instance:FittingB_1 | `colliders` | PASS | count=54; expected=54; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:FittingB_1 | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:FittingB_1 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:FittingB_1 | `bore_open` | PASS | collider_distance_from_axis_min_m=0.006599999952221505; narrowest_visual_bore_radius_m=0.006; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:FittingB_1 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:FittingB_1 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.07500000298023224; expected_mass_kg=0.075; implied_density_kg_m3=8482.250060807057; diagonal_inertia=[2.0182251319056377e-05, 2.018201666942332e-05, 1.0432720955577679e-05]; center_of_mass=[-5.120389687363058e-06, -3.175144229317084e-06, 0.02944529801607132]; nested_rigid_bodies=[] |
| instance:FittingB_1 | `resting_on_support` | PASS | collider_bottom_z=0.7564999997772812; support_surface_z=0.7549999999441206; gap_m=0.0014999998331606257; expected_gap_m=0.0015; support="InputTray" |
| instance:FittingB_1 | `inside_support` | PASS | margin_to_support_edge_m=0.048486786525103354; required_m=0.02; support="InputTray"; note="every collider vertex inside the support surface, at least min_object_gap_m from its edge" |
| instance:FittingB_1 | `clearance_to_scene` | PASS | min_gap_m=0.022675691279384458; closest="instance:FittingB_0"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| instance:FittingB_2 | `prim_exists` | PASS | path="/World/UserObjects/FittingB_2" |
| instance:FittingB_2 | `references_library_asset` | PASS | references=["../../library/brass_adapter_female/brass_adapter_female.usd"]; expected="../../library/brass_adapter_female/brass_adapter_female.usd" |
| instance:FittingB_2 | `pose` | PASS | position=[0.4903, -0.3016, 0.7650208496083888]; expected=[0.4903, -0.3016, 0.7650208496083888]; rotation_matrix_max_error=5.551115123125783e-16; rotation_error_deg=0.0; yaw_deg=-58.35340465093303; tilt_deg=77.90524292298785; pose="lying" |
| instance:FittingB_2 | `visual_dimensions` | PASS | nominal=[[-0.016, -0.016, 0.0], [0.016, 0.016, 0.05500000000000001]]; size=[0.03200000151991844, 0.03200000151991844, 0.054999999701976776]; tolerance_m=0.0005 |
| instance:FittingB_2 | `collider_dimensions` | PASS | nominal=[[-0.016, -0.016, 0.0], [0.016, 0.016, 0.05500000000000001]]; size=[0.03200000151991844, 0.03200000151991844, 0.054999999701976776] |
| instance:FittingB_2 | `colliders` | PASS | count=54; expected=54; representation="fitting_sections"; contact_offset_m="PhysX default" |
| instance:FittingB_2 | `physics_material` | PASS | bound=true; values=[[0.35, 0.3, 0.08]]; expected=[[0.35, 0.3, 0.08]] |
| instance:FittingB_2 | `physx_combine_modes` | PASS | combine_modes=[["average", "average"]] |
| instance:FittingB_2 | `bore_open` | PASS | collider_distance_from_axis_min_m=0.006599999952221563; narrowest_visual_bore_radius_m=0.006; note="every collider piece clears the narrowest bore circle along the whole axis" |
| instance:FittingB_2 | `visual_material_bound` | PASS | visual_meshes=1 |
| instance:FittingB_2 | `rigid_body` | PASS | rigid_body_enabled=true; static_override=false; mass_kg=0.07500000298023224; expected_mass_kg=0.075; implied_density_kg_m3=8482.250060807057; diagonal_inertia=[2.0182251319056377e-05, 2.018201666942332e-05, 1.0432720955577679e-05]; center_of_mass=[-5.120389687363058e-06, -3.175144229317084e-06, 0.02944529801607132]; nested_rigid_bodies=[] |
| instance:FittingB_2 | `resting_on_support` | PASS | collider_bottom_z=0.7564999997772812; support_surface_z=0.7549999999441206; gap_m=0.0014999998331606257; expected_gap_m=0.0015; support="InputTray" |
| instance:FittingB_2 | `inside_support` | PASS | margin_to_support_edge_m=0.021001500562124187; required_m=0.02; support="InputTray"; note="every collider vertex inside the support surface, at least min_object_gap_m from its edge" |
| instance:FittingB_2 | `clearance_to_scene` | PASS | min_gap_m=0.02100149344985519; closest="instance:InputTray"; required_m=0.02; note="per-collider AABB lower bound (3D between instances, xy to base objects); support-surface pieces exempt" |
| preservation | `all_base_prims_present` | PASS | base_prims=783; missing_unexpected=[]; deactivated_roots=["/World/Objects", "/World/Targets", "/World/Workstation/SortingZone"]; deactivated_prims=335; deactivated_roots_inactive=true; note="prims under deactivate_base_prims are intentionally inactive in the derived scene (base file unchanged)" |
| preservation | `base_prims_unchanged` | PASS | prims_compared=448; attributes_compared=4215; differing={}; note="type, world transform, every attribute value, relationships, applied schemas" |
| preservation | `new_prims_only_under_allowed_roots` | PASS | new_prims=465; outside=[] |
| preservation | `robot_unchanged` | PASS | robot_prims=366 |
| scene | `distinct_geometry_brass_adapter_male_vs_brass_adapter_female` | PASS | criteria={"visual_mesh_hash": true, "size": true, "volume": true, "section_layout": true}; size_m=[[0.024826061575153907, 0.0215, 0.045], [0.032, 0.032, 0.05500000000000001]]; volume_m3=[5.490266311739419e-06, 8.841993511432038e-06]; triangles=[8640, 18816] |
| scene | `individual_rigid_bodies_on_InputTray` | PASS | count=7; expected=7; bodies=["FittingA_0", "FittingA_1", "FittingA_2", "FittingA_3", "FittingB_0", "FittingB_1", "FittingB_2"]; note="each with its own RigidBodyAPI root (no merged meshes, no nested bodies)" |
| scene | `sorting_bin_A_initially_empty` | PASS | objects_inside=[] |
| scene | `sorting_bin_B_initially_empty` | PASS | objects_inside=[] |
| physics:FittingA_0 | `settled_on_support` | PASS | height_change_from_authored_mm=-1.4998; expected_drop_mm=1.5; final_gap_to_support_mm=0.0002; support="InputTray" |
| physics:FittingA_0 | `inside_support_no_penetration` | PASS | max_wall_intrusion_mm=-109.5; floor_penetration_mm=-0.0002; top_below_rim=true; note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)" |
| physics:FittingA_0 | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0163 |
| physics:FittingA_0 | `no_horizontal_drift` | PASS | drift_mm=0.0 |
| physics:FittingA_0 | `at_rest` | PASS | mean_speed_last_0_5s="0.00e+00" |
| physics:FittingA_0 | `no_extreme_motion` | PASS | peak_speed_m_s=0.006; peak_angular_speed_rad_s=0.0483; peak_acceleration_m_s2=0.68; note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)" |
| physics:FittingA_0 | `supported_by_support_force` | PASS | normal_force_N=0.44145; weight_N=0.44145 |
| physics:FittingA_1 | `settled_on_support` | PASS | height_change_from_authored_mm=-1.4998; expected_drop_mm=1.5; final_gap_to_support_mm=-0.0001; support="InputTray" |
| physics:FittingA_1 | `inside_support_no_penetration` | PASS | max_wall_intrusion_mm=-61.571; floor_penetration_mm=0.0001; top_below_rim=true; note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)" |
| physics:FittingA_1 | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0259 |
| physics:FittingA_1 | `no_horizontal_drift` | PASS | drift_mm=0.001 |
| physics:FittingA_1 | `at_rest` | PASS | mean_speed_last_0_5s="4.49e-05" |
| physics:FittingA_1 | `no_extreme_motion` | PASS | peak_speed_m_s=0.006; peak_angular_speed_rad_s=0.0621; peak_acceleration_m_s2=0.67; note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)" |
| physics:FittingA_1 | `supported_by_support_force` | PASS | normal_force_N=0.44143; weight_N=0.44145 |
| physics:FittingA_2 | `settled_on_support` | PASS | height_change_from_authored_mm=-1.5; expected_drop_mm=1.5; final_gap_to_support_mm=-0.0; support="InputTray" |
| physics:FittingA_2 | `inside_support_no_penetration` | PASS | max_wall_intrusion_mm=-42.726; floor_penetration_mm=0.0; top_below_rim=true; note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)" |
| physics:FittingA_2 | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0271 |
| physics:FittingA_2 | `no_horizontal_drift` | PASS | drift_mm=0.0 |
| physics:FittingA_2 | `at_rest` | PASS | mean_speed_last_0_5s="5.60e-05" |
| physics:FittingA_2 | `no_extreme_motion` | PASS | peak_speed_m_s=0.006; peak_angular_speed_rad_s=0.0704; peak_acceleration_m_s2=0.67; note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)" |
| physics:FittingA_2 | `supported_by_support_force` | PASS | normal_force_N=0.44145; weight_N=0.44145 |
| physics:FittingA_3 | `settled_on_support` | PASS | height_change_from_authored_mm=-1.4998; expected_drop_mm=1.5; final_gap_to_support_mm=0.0001; support="InputTray" |
| physics:FittingA_3 | `inside_support_no_penetration` | PASS | max_wall_intrusion_mm=-35.919; floor_penetration_mm=-0.0001; top_below_rim=true; note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)" |
| physics:FittingA_3 | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0249 |
| physics:FittingA_3 | `no_horizontal_drift` | PASS | drift_mm=0.001 |
| physics:FittingA_3 | `at_rest` | PASS | mean_speed_last_0_5s="7.15e-06" |
| physics:FittingA_3 | `no_extreme_motion` | PASS | peak_speed_m_s=0.006; peak_angular_speed_rad_s=0.0463; peak_acceleration_m_s2=0.68; note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)" |
| physics:FittingA_3 | `supported_by_support_force` | PASS | normal_force_N=0.44145; weight_N=0.44145 |
| physics:FittingB_0 | `settled_on_support` | PASS | height_change_from_authored_mm=-1.5006; expected_drop_mm=1.5; final_gap_to_support_mm=-0.0025; support="InputTray" |
| physics:FittingB_0 | `inside_support_no_penetration` | PASS | max_wall_intrusion_mm=-44.631; floor_penetration_mm=0.0025; top_below_rim=true; note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)" |
| physics:FittingB_0 | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0236 |
| physics:FittingB_0 | `no_horizontal_drift` | PASS | drift_mm=0.003 |
| physics:FittingB_0 | `at_rest` | PASS | mean_speed_last_0_5s="8.00e-06" |
| physics:FittingB_0 | `no_extreme_motion` | PASS | peak_speed_m_s=0.006; peak_angular_speed_rad_s=0.038; peak_acceleration_m_s2=0.68; note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)" |
| physics:FittingB_0 | `supported_by_support_force` | PASS | normal_force_N=0.73575; weight_N=0.73575 |
| physics:FittingB_1 | `settled_on_support` | PASS | height_change_from_authored_mm=-1.5; expected_drop_mm=1.5; final_gap_to_support_mm=-0.0004; support="InputTray" |
| physics:FittingB_1 | `inside_support_no_penetration` | PASS | max_wall_intrusion_mm=-49.172; floor_penetration_mm=0.0004; top_below_rim=true; note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)" |
| physics:FittingB_1 | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0333 |
| physics:FittingB_1 | `no_horizontal_drift` | PASS | drift_mm=0.002 |
| physics:FittingB_1 | `at_rest` | PASS | mean_speed_last_0_5s="9.86e-06" |
| physics:FittingB_1 | `no_extreme_motion` | PASS | peak_speed_m_s=0.006; peak_angular_speed_rad_s=0.0723; peak_acceleration_m_s2=0.68; note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)" |
| physics:FittingB_1 | `supported_by_support_force` | PASS | normal_force_N=0.73575; weight_N=0.73575 |
| physics:FittingB_2 | `settled_on_support` | PASS | height_change_from_authored_mm=-1.4998; expected_drop_mm=1.5; final_gap_to_support_mm=0.0002; support="InputTray" |
| physics:FittingB_2 | `inside_support_no_penetration` | PASS | max_wall_intrusion_mm=-22.11; floor_penetration_mm=-0.0002; top_below_rim=true; note="final collider vertices vs. the container's inner wall planes and floor (negative = inside / above)" |
| physics:FittingB_2 | `orientation_stable` | PASS | max_rotation_from_authored_deg=0.0272 |
| physics:FittingB_2 | `no_horizontal_drift` | PASS | drift_mm=0.0 |
| physics:FittingB_2 | `at_rest` | PASS | mean_speed_last_0_5s="7.59e-05" |
| physics:FittingB_2 | `no_extreme_motion` | PASS | peak_speed_m_s=0.006; peak_angular_speed_rad_s=0.0581; peak_acceleration_m_s2=0.68; note="limits 0.3 m/s, 5 rad/s (a 1.5 mm drop reaches 0.17 m/s); acceleration is reported (contact impulses)" |
| physics:FittingB_2 | `supported_by_support_force` | PASS | normal_force_N=0.73582; weight_N=0.73575 |
| physics:drop_test_sorting_bin_A | `enters_through_open_top` | PASS | xy_local_at_rim=[0.03, -0.019999998807907093]; opening_half_m=[0.188, 0.13799999999999998]; note="cube footprint (incl. its diagonal) inside the opening when crossing the rim" |
| physics:drop_test_sorting_bin_A | `contacts_floor` | PASS | rest_bottom_local_z=0.016; floor_top_local_z=0.016; floor_contact_force_N=0.981; weight_N=0.981 |
| physics:drop_test_sorting_bin_A | `remains_inside` | PASS | final_local=[0.0294, -0.0207, 0.046]; final_speed="7.93e-05" |
| physics:drop_test_sorting_bin_A | `no_floor_penetration` | PASS | min_cube_bottom_local_z=0.016; floor_top_local_z=0.016 |
| physics:drop_test_sorting_bin_B | `enters_through_open_top` | PASS | xy_local_at_rim=[0.03, -0.019999992847442638]; opening_half_m=[0.188, 0.13799999999999998]; note="cube footprint (incl. its diagonal) inside the opening when crossing the rim" |
| physics:drop_test_sorting_bin_B | `contacts_floor` | PASS | rest_bottom_local_z=0.016; floor_top_local_z=0.016; floor_contact_force_N=0.981; weight_N=0.981 |
| physics:drop_test_sorting_bin_B | `remains_inside` | PASS | final_local=[0.0294, -0.0207, 0.046]; final_speed="7.68e-05" |
| physics:drop_test_sorting_bin_B | `no_floor_penetration` | PASS | min_cube_bottom_local_z=0.016; floor_top_local_z=0.016 |
| physics:move_test_FittingA_0 | `moved_independently` | PASS | pose_after_teleport=[0.4048, -0.1989, 0.81507]; target=[0.4048, -0.1989, 0.81575]; others_max_displacement_mm=0.0029 |
| physics:move_test_FittingA_0 | `resettled_after_move` | PASS | final=[0.40446, -0.19899, 0.76575]; start=[0.4048, -0.1989, 0.76575]; yaw_change_deg=45.001; final_speed="7.32e-05" |
| physics:move_test_FittingA_0 | `visual_and_colliders_follow_rigid_body` | PASS | visual_mesh_offset_from_root=2.220446049250313e-16; reset_xform_stack=[]; usd_root_after_teleport=[0.4048, -0.1989, 0.81507] |

Scope: these checks cover the added instances and the integrity of the base scene. They do not re-run the workstation's own 94 static / 39 dynamic checks (run those with a config copy that points paths.scene at the derived layer; scripts/assets/add_asset.py --base-suites does this) and do not imply physical realism beyond the modelled rigid-body approximation.
