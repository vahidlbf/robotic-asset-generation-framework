# Add asset `test_spacer` -> `assets/scenes/derived/workstation_test_spacer.usda`

- Generated: 2026-10-27T17:27:22+01:00
- **Result: PASS**
- Asset status before/after: current / current (rebuilt)
- Targeted validation: 53/53 checks passed (physics: yes)
- Workstation suites on the derived scene: [validate] 94/94 static checks passed; failed: []; [physics] 39/39 dynamic checks passed; failed: []
- Protected files: 23 hashed before/after; content changed: none; mtime changed: none
- Parent ramp project: 51 files; changed: none

| Stage | Exit | Time (s) | Log |
|---|---|---|---|
| generate_asset (test_spacer) | 0 | 1.8 | `logs/assets/workstation_test_spacer/generate_test_spacer.log` |
| compose_scene | 0 | 1.5 | `logs/assets/workstation_test_spacer/compose.log` |
| validate_asset_scene | 0 | 14.8 | `logs/assets/workstation_test_spacer/validate.log` |
| base suite: validate_scene | 0 | 39.4 | `logs/assets/workstation_test_spacer/base_suites/validate_scene.log` |
| base suite: run_physics_test | 0 | 16.3 | `logs/assets/workstation_test_spacer/base_suites/run_physics_test.log` |
| preview | 0 | 23.2 | `logs/assets/workstation_test_spacer/base_suites/render.log` |

| Instance | Prim | Position (m) | Yaw (deg) | Reference |
|---|---|---|---|---|
| TestSpacer_0 | `/World/UserObjects/TestSpacer_0` | [-0.55, -0.25, 0.7515] | 0.0 | `../../library/test_spacer/test_spacer.usd` |
| TestSpacer_1 | `/World/UserObjects/TestSpacer_1` | [-0.45, -0.22, 0.7515] | 30.0 | `../../library/test_spacer/test_spacer.usd` |

Asset files: {'test_spacer.usd': '804a1ed1193e3548703333e8aca7c4b27916d7dc76108b80743fe726ecfd7269', 'test_spacer_visual.usd': 'eedd446fab04cc6df9a25d314d5473e7dd7f66c9f04231569b1a2a364b095aa4'}; mass 0.1161931081556839 kg (density_kg_m3 x mesh volume); colliders 12.

Details: `validation_report.md` (targeted checks), `compose.json`, `base_suites/` (if run).
