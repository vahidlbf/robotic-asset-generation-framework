# Add assets `industrial_gray_tray+industrial_blue_crate+label_bin_a+label_bin_b+brass_adapter_male+brass_adapter_female` -> `assets/scenes/derived/industrial_brass_sorting.usda`

- Generated: 2026-10-27T19:27:53+01:00
- **Result: PASS**
- `industrial_gray_tray`: status before/after current / current (already current, not rebuilt)
- `industrial_blue_crate`: status before/after current / current (already current, not rebuilt)
- `label_bin_a`: status before/after current / current (already current, not rebuilt)
- `label_bin_b`: status before/after current / current (already current, not rebuilt)
- `brass_adapter_male`: status before/after current / current (already current, not rebuilt)
- `brass_adapter_female`: status before/after current / current (already current, not rebuilt)
- Targeted validation: 238/238 checks passed (physics: yes)
- Protected files: 27 hashed before/after; content changed: none; mtime changed: none
- Parent ramp project: 51 files; changed: none

| Stage | Exit | Time (s) | Log |
|---|---|---|---|
| generate_asset (industrial_gray_tray) | 0 | 1.2 | `logs/assets/industrial_brass_sorting/generate_industrial_gray_tray.log` |
| generate_asset (industrial_blue_crate) | 0 | 1.3 | `logs/assets/industrial_brass_sorting/generate_industrial_blue_crate.log` |
| generate_asset (label_bin_a) | 0 | 1.3 | `logs/assets/industrial_brass_sorting/generate_label_bin_a.log` |
| generate_asset (label_bin_b) | 0 | 1.3 | `logs/assets/industrial_brass_sorting/generate_label_bin_b.log` |
| generate_asset (brass_adapter_male) | 0 | 1.3 | `logs/assets/industrial_brass_sorting/generate_brass_adapter_male.log` |
| generate_asset (brass_adapter_female) | 0 | 1.3 | `logs/assets/industrial_brass_sorting/generate_brass_adapter_female.log` |
| compose_scene | 0 | 1.3 | `logs/assets/industrial_brass_sorting/compose.log` |
| validate_asset_scene | 0 | 14.2 | `logs/assets/industrial_brass_sorting/validate.log` |
| preview | 0 | 25.5 | `logs/assets/industrial_brass_sorting/base_suites/render.log` |

| Instance | Prim | Position (m) | Yaw (deg) | Reference |
|---|---|---|---|---|
| InputTray | `/World/UserObjects/InputTray` | [0.42, -0.215, 0.75] | 0.0 | `../../library/industrial_gray_tray/industrial_gray_tray.usd` |
| sorting_bin_A | `/World/UserObjects/sorting_bin_A` | [-0.03, -0.2, 0.75] | 0.0 | `../../library/industrial_blue_crate/industrial_blue_crate.usd` |
| sorting_bin_B | `/World/UserObjects/sorting_bin_B` | [-0.03, 0.2, 0.75] | 0.0 | `../../library/industrial_blue_crate/industrial_blue_crate.usd` |
| label_A | `/World/UserObjects/label_A` | [0.16444, -0.2, 0.845] | 90.0 | `../../library/label_bin_a/label_bin_a.usd` |
| label_B | `/World/UserObjects/label_B` | [0.16444, 0.2, 0.845] | 90.0 | `../../library/label_bin_b/label_bin_b.usd` |
| FittingA_0 | `/World/UserObjects/FittingA_0` | [0.4048, -0.1989, 0.76725] | -117.3 | `../../library/brass_adapter_male/brass_adapter_male.usd` |
| FittingA_1 | `/World/UserObjects/FittingA_1` | [0.4691, -0.1839, 0.76725] | 146.7 | `../../library/brass_adapter_male/brass_adapter_male.usd` |
| FittingA_2 | `/World/UserObjects/FittingA_2` | [0.5291, -0.2099, 0.76725] | 140.5 | `../../library/brass_adapter_male/brass_adapter_male.usd` |
| FittingA_3 | `/World/UserObjects/FittingA_3` | [0.3416, -0.1457, 0.76725] | -85.4 | `../../library/brass_adapter_male/brass_adapter_male.usd` |
| FittingB_0 | `/World/UserObjects/FittingB_0` | [0.3783, -0.3032, 0.76502] | 7.747 | `../../library/brass_adapter_female/brass_adapter_female.usd` |
| FittingB_1 | `/World/UserObjects/FittingB_1` | [0.3173, -0.2195, 0.76502] | -145.153 | `../../library/brass_adapter_female/brass_adapter_female.usd` |
| FittingB_2 | `/World/UserObjects/FittingB_2` | [0.4903, -0.3016, 0.76502] | -58.353 | `../../library/brass_adapter_female/brass_adapter_female.usd` |

`industrial_gray_tray` files: {'industrial_gray_tray.usd': '3e8bfcade4df6732a102d64cd0a045af5a43bcd287a679d5b4cf742d8c3fe78b', 'industrial_gray_tray_visual.usd': '6732d5dd92e67a606929f6a5a365422cdf60cacd6c8e95d9c0c141267b54c5e3'}; mass static kg; colliders 5.

`industrial_blue_crate` files: {'industrial_blue_crate.usd': '72fb290640b4a801d9893ea62d548c6cdd56583eaea7f026d146ef37d58efff8', 'industrial_blue_crate_visual.usd': '00f3777502ed5ed35cf3ea42f7380cf1edf60e252202ed098095d52adc3bd584'}; mass static kg; colliders 5.

`label_bin_a` files: {'label_bin_a.usd': 'fc74a6472cd18c741fd5a42c965acdda9ddcd5faad35cd03ebc9571186bbda28', 'label_bin_a_visual.usd': '449e58f393fab0eb3a38a6362e65361ae5d4dfb1be9a51ae27f3834dcde70922'}; mass static kg; colliders 0.

`label_bin_b` files: {'label_bin_b.usd': 'd29d478374494cb67ad982e74b4484cc63614357dec1a20a9162ccca91cad5ed', 'label_bin_b_visual.usd': 'f21c918d3e77d1ea90bebf04d81a0ef2b8f73bd8738b3cadbce468387504b828'}; mass static kg; colliders 0.

`brass_adapter_male` files: {'brass_adapter_male.usd': '47cb105b95afa452813892a0253ece7a6593aa89218a00a655d0d5427a07bd07', 'brass_adapter_male_visual.usd': '8f77456cb22b3a2391d86202e3b2c23929fa6046eedd80592cad8e193036e0df'}; mass 0.045 kg (mass_kg); colliders 42.

`brass_adapter_female` files: {'brass_adapter_female.usd': '0726906d8c2666dc659b9ee3f7eae223626b50ae65a694fe4d96c05cfb60b2e6', 'brass_adapter_female_visual.usd': 'd4df1311b36f29616d857b41fda79500fa3f96e6b9cd52bcee7494d72b5c82e6'}; mass 0.075 kg (mass_kg); colliders 54.

Details: `validation_report.md` (targeted checks), `compose.json`, `base_suites/` (if run).
