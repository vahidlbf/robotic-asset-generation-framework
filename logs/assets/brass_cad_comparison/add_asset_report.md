# Add assets `brass_adapter_male+brass_adapter_male_cad+brass_adapter_male_step_import` -> `assets/scenes/derived/brass_cad_comparison.usda`

- Generated: 2026-10-28T18:20:53+01:00
- **Result: PASS**
- `brass_adapter_male`: status before/after current / current (already current, not rebuilt)
- `brass_adapter_male_cad`: status before/after current / current (already current, not rebuilt)
- `brass_adapter_male_step_import`: status before/after current / current (already current, not rebuilt)
- Targeted validation: 76/76 checks passed (physics: yes)
- Workstation suites on the derived scene: [validate] 94/94 static checks passed; failed: []; [physics] 39/39 dynamic checks passed; failed: []
- Protected files: 43 hashed before/after; content changed: none; mtime changed: none
- Parent ramp project: 51 files; changed: none

| Stage | Exit | Time (s) | Log |
|---|---|---|---|
| generate_asset (brass_adapter_male) | 0 | 1.3 | `logs/assets/brass_cad_comparison/generate_brass_adapter_male.log` |
| generate_asset (brass_adapter_male_cad) | 0 | 1.3 | `logs/assets/brass_cad_comparison/generate_brass_adapter_male_cad.log` |
| generate_asset (brass_adapter_male_step_import) | 0 | 1.3 | `logs/assets/brass_cad_comparison/generate_brass_adapter_male_step_import.log` |
| compose_scene | 0 | 1.3 | `logs/assets/brass_cad_comparison/compose.log` |
| validate_asset_scene | 0 | 13.7 | `logs/assets/brass_cad_comparison/validate.log` |
| base suite: validate_scene | 0 | 31.2 | `logs/assets/brass_cad_comparison/base_suites/validate_scene.log` |
| base suite: run_physics_test | 0 | 17.3 | `logs/assets/brass_cad_comparison/base_suites/run_physics_test.log` |
| preview | 0 | 16.4 | `logs/assets/brass_cad_comparison/base_suites/render.log` |

| Instance | Prim | Position (m) | Yaw (deg) | Reference |
|---|---|---|---|---|
| AdapterBlender | `/World/UserObjects/AdapterBlender` | [-0.55, -0.12, 0.76225] | 180.0 | `../../library/brass_adapter_male/brass_adapter_male.usd` |
| AdapterFreeCAD | `/World/UserObjects/AdapterFreeCAD` | [-0.55, -0.02, 0.76225] | 180.0 | `../../library/brass_adapter_male_cad/brass_adapter_male_cad.usd` |
| AdapterStepImport | `/World/UserObjects/AdapterStepImport` | [-0.55, 0.09, 0.7515] | 0.0 | `../../library/brass_adapter_male_step_import/brass_adapter_male_step_import.usd` |

`brass_adapter_male` files: {'brass_adapter_male.usd': '47cb105b95afa452813892a0253ece7a6593aa89218a00a655d0d5427a07bd07', 'brass_adapter_male_visual.usd': '8f77456cb22b3a2391d86202e3b2c23929fa6046eedd80592cad8e193036e0df'}; mass 0.045 kg (mass_kg); colliders 42.

`brass_adapter_male_cad` files: {'brass_adapter_male_cad.usd': '49fbceb0d4027633757e77c92620fd9c3bdd4232cb9ecb874126e86f986cc32d', 'brass_adapter_male_cad_visual.usd': '9820c8a1c8ab2d239069768923a71f40d9aabb39b6e242ee82de3a8860131d62', 'brass_adapter_male_cad.step': '51d4cde54919c6a3277d304f73b82c7991a1f96100a29114830d9b5c07ed407f'}; mass 0.05024969607292468 kg (density_kg_m3 x exact CAD volume); colliders 42.

`brass_adapter_male_step_import` files: {'brass_adapter_male_step_import.usd': '17a23808b76727b11f1b124e292fa2f2840da8a540ff3c2c6ef59d752f1d56df', 'brass_adapter_male_step_import_visual.usd': 'ab47bfe0bee48643b8e852303052b9f16696625700f0b6f1f8f58f8c3281d398'}; mass 0.050249695688834445 kg (density_kg_m3 x exact CAD volume); colliders 1.

Details: `validation_report.md` (targeted checks), `compose.json`, `base_suites/` (if run).
