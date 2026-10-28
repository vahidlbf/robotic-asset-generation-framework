# Add assets `brass_adapter_male+brass_adapter_male_cad+brass_adapter_male_step_import+brass_adapter_male_step_import_open+label_cmp_blender+label_cmp_freecad+label_cmp_step+label_cmp_step_open` -> `assets/scenes/derived/brass_backend_comparison.usda`

- Generated: 2026-10-28T18:56:53+01:00
- **Result: PASS**
- `brass_adapter_male`: status before/after current / current (already current, not rebuilt)
- `brass_adapter_male_cad`: status before/after current / current (already current, not rebuilt)
- `brass_adapter_male_step_import`: status before/after current / current (already current, not rebuilt)
- `brass_adapter_male_step_import_open`: status before/after current / current (already current, not rebuilt)
- `label_cmp_blender`: status before/after current / current (already current, not rebuilt)
- `label_cmp_freecad`: status before/after current / current (already current, not rebuilt)
- `label_cmp_step`: status before/after current / current (already current, not rebuilt)
- `label_cmp_step_open`: status before/after current / current (already current, not rebuilt)
- Targeted validation: 133/133 checks passed (physics: yes)
- Workstation suites on the derived scene: [validate] 94/94 static checks passed; failed: []; [physics] 39/39 dynamic checks passed; failed: []
- Protected files: 44 hashed before/after; content changed: none; mtime changed: none
- Parent ramp project: 51 files; changed: none

| Stage | Exit | Time (s) | Log |
|---|---|---|---|
| generate_asset (brass_adapter_male) | 0 | 1.6 | `logs/assets/brass_backend_comparison/generate_brass_adapter_male.log` |
| generate_asset (brass_adapter_male_cad) | 0 | 1.7 | `logs/assets/brass_backend_comparison/generate_brass_adapter_male_cad.log` |
| generate_asset (brass_adapter_male_step_import) | 0 | 1.7 | `logs/assets/brass_backend_comparison/generate_brass_adapter_male_step_import.log` |
| generate_asset (brass_adapter_male_step_import_open) | 0 | 1.6 | `logs/assets/brass_backend_comparison/generate_brass_adapter_male_step_import_open.log` |
| generate_asset (label_cmp_blender) | 0 | 1.7 | `logs/assets/brass_backend_comparison/generate_label_cmp_blender.log` |
| generate_asset (label_cmp_freecad) | 0 | 1.6 | `logs/assets/brass_backend_comparison/generate_label_cmp_freecad.log` |
| generate_asset (label_cmp_step) | 0 | 1.6 | `logs/assets/brass_backend_comparison/generate_label_cmp_step.log` |
| generate_asset (label_cmp_step_open) | 0 | 1.6 | `logs/assets/brass_backend_comparison/generate_label_cmp_step_open.log` |
| compose_scene | 0 | 1.5 | `logs/assets/brass_backend_comparison/compose.log` |
| validate_asset_scene | 0 | 15.4 | `logs/assets/brass_backend_comparison/validate.log` |
| base suite: validate_scene | 0 | 36.6 | `logs/assets/brass_backend_comparison/base_suites/validate_scene.log` |
| base suite: run_physics_test | 0 | 16.3 | `logs/assets/brass_backend_comparison/base_suites/run_physics_test.log` |
| preview | 0 | 20.3 | `logs/assets/brass_backend_comparison/base_suites/render.log` |

| Instance | Prim | Position (m) | Yaw (deg) | Reference |
|---|---|---|---|---|
| AdapterBlender | `/World/UserObjects/AdapterBlender` | [-0.7, -0.2, 0.7515] | 0.0 | `../../library/brass_adapter_male/brass_adapter_male.usd` |
| Label_AdapterBlender | `/World/UserObjects/Label_AdapterBlender` | [-0.7, -0.245, 0.75] | 0.0 | `../../library/label_cmp_blender/label_cmp_blender.usd` |
| AdapterFreeCAD | `/World/UserObjects/AdapterFreeCAD` | [-0.62, -0.2, 0.7515] | 0.0 | `../../library/brass_adapter_male_cad/brass_adapter_male_cad.usd` |
| Label_AdapterFreeCAD | `/World/UserObjects/Label_AdapterFreeCAD` | [-0.62, -0.245, 0.75] | 0.0 | `../../library/label_cmp_freecad/label_cmp_freecad.usd` |
| AdapterStepImport | `/World/UserObjects/AdapterStepImport` | [-0.54, -0.2, 0.7515] | 0.0 | `../../library/brass_adapter_male_step_import/brass_adapter_male_step_import.usd` |
| Label_AdapterStepImport | `/World/UserObjects/Label_AdapterStepImport` | [-0.54, -0.245, 0.75] | 0.0 | `../../library/label_cmp_step/label_cmp_step.usd` |
| AdapterStepImportOpen | `/World/UserObjects/AdapterStepImportOpen` | [-0.46, -0.2, 0.7515] | 0.0 | `../../library/brass_adapter_male_step_import_open/brass_adapter_male_step_import_open.usd` |
| Label_AdapterStepImportOpen | `/World/UserObjects/Label_AdapterStepImportOpen` | [-0.46, -0.245, 0.75] | 0.0 | `../../library/label_cmp_step_open/label_cmp_step_open.usd` |

`brass_adapter_male` files: {'brass_adapter_male.usd': '47cb105b95afa452813892a0253ece7a6593aa89218a00a655d0d5427a07bd07', 'brass_adapter_male_visual.usd': '8f77456cb22b3a2391d86202e3b2c23929fa6046eedd80592cad8e193036e0df'}; mass 0.045 kg (mass_kg); colliders 42.

`brass_adapter_male_cad` files: {'brass_adapter_male_cad.usd': '49fbceb0d4027633757e77c92620fd9c3bdd4232cb9ecb874126e86f986cc32d', 'brass_adapter_male_cad_visual.usd': '9820c8a1c8ab2d239069768923a71f40d9aabb39b6e242ee82de3a8860131d62', 'brass_adapter_male_cad.step': '51d4cde54919c6a3277d304f73b82c7991a1f96100a29114830d9b5c07ed407f'}; mass 0.05024969607292468 kg (density_kg_m3 x exact CAD volume); colliders 42.

`brass_adapter_male_step_import` files: {'brass_adapter_male_step_import.usd': '17a23808b76727b11f1b124e292fa2f2840da8a540ff3c2c6ef59d752f1d56df', 'brass_adapter_male_step_import_visual.usd': 'ab47bfe0bee48643b8e852303052b9f16696625700f0b6f1f8f58f8c3281d398'}; mass 0.050249695688834445 kg (density_kg_m3 x exact CAD volume); colliders 1.

`brass_adapter_male_step_import_open` files: {'brass_adapter_male_step_import_open.usd': '7020ab0e5052cd634d82cfff59f2588e7086621bf3e38256c8697c69f9502dab', 'brass_adapter_male_step_import_open_visual.usd': '852a071ad3535bfeff7a0399e31d67ed288bf40e674c6a48cd3072516e53a891'}; mass 0.050249695688834445 kg (density_kg_m3 x exact CAD volume); colliders 42.

`label_cmp_blender` files: {'label_cmp_blender.usd': 'aaaa7247123e1f6d3d9d3bbbd4e28422031586b793f4c807576787e467571217', 'label_cmp_blender_visual.usd': 'b9e350db50007d9d01f7d1780b4e5f70f1df7530988f2ffecfe00620c9f49c59'}; mass static kg; colliders 0.

`label_cmp_freecad` files: {'label_cmp_freecad.usd': '91284215720685013c94373a9e5333c1ffe4c992dbfa20772d3001ade9223ee8', 'label_cmp_freecad_visual.usd': 'c63bb8efd374f35c6ab2e7e256195e4852613c8962c481225d81db19419ceb6e'}; mass static kg; colliders 0.

`label_cmp_step` files: {'label_cmp_step.usd': 'a97513cd1fa5233776604f2b902ce7da0427c4e953816561ed606d68be8299aa', 'label_cmp_step_visual.usd': '48c7f9a2b00704fede52c8d7c46f9ba1a8e767d4aa37b05f55ad5cb4dbf555b1'}; mass static kg; colliders 0.

`label_cmp_step_open` files: {'label_cmp_step_open.usd': '93a3ea52ce181b33d6da1e67ca4aefc628c81702d98f7408596b60005f3ab887', 'label_cmp_step_open_visual.usd': '7b8db93d498a28cc290ff011b955369ba08fe70ad04890cf183d97bb437e6534'}; mass static kg; colliders 0.

Details: `validation_report.md` (targeted checks), `compose.json`, `base_suites/` (if run).
