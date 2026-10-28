# Geometry backends: Blender, FreeCAD, CAD import

Every library asset is built by one **geometry backend**. The backend is chosen deterministically from the asset spec
and the installed tools (`scripts/assets/backends.py`). Downstream of the geometry everything is shared: materials,
colliders (`asset_lib.collider_pieces`), the physics USD (`generate_assets.write_asset`), the registry, scene
composition and Isaac Sim validation. **FreeCAD is optional.** Only the `freecad` backend and STEP imports need it.

```
spec ──► backends.select_backend ──┬─ blender : generate_asset.build_geometry (procedural mesh) ─────────────────┐
                                   ├─ freecad : freecad_build.py (FreeCAD solid) ─► STEP + STL ─► Blender import ─┤
                                   └─ import  : STL ─► Blender import  |  STEP ─► FreeCAD read/validate ─► STL ─► ─┤
                                                                                                                  ▼
              material, colliders, mass (exact CAD solid when available), <id>.usd + <id>_visual.usd [+ <id>.step], registry
```
There is no direct CAD-to-USD path. Blender's USD exporter is the only validated mesh-to-USD writer here, so every
route ends in Blender.

## Spec fields (`geometry`)

| Field | Values | Meaning |
|---|---|---|
| `backend` | `blender` (default when absent), `auto`, `freecad`, `import` | absent means `blender`, so every spec written before backends existed keeps its validated route |
| `accuracy` | `visual` (default), `engineering` | input to `auto` |
| `require_step` | bool | a STEP file must exist at the end (FreeCAD builder or STEP source); otherwise the spec / selection fails |
| `cad` | `{linear_deflection_mm (0.01), angular_deflection_deg (5)}` | FreeCAD tessellation of the solid for the visual mesh |
| method `mesh_import` | `source` (project-relative `.stl` / `.step` / `.stp`), `size` (expected envelope, m), `source_units` (`mm` default / `m`), `recenter` (default true) | an existing model |

The geometry parameters are **not** duplicated per backend: the FreeCAD fitting builder reads the same `outer` /
`bore` sections, through `asset_lib.fitting_sections`, as the Blender builder.

## Capabilities (what is actually implemented)

| Method | blender | freecad | import |
|---|---|---|---|
| `box`, `cylinder`, `tube`, `open_container`, `label_plate` | yes | **no builder** | — |
| `fitting` (stepped turned parts, hex, chamfers, grooves, bore, threads) | yes (visual helical threads) | yes (cosmetic threads) | — |
| `mesh_import` | — | — | STL (Blender), STEP (FreeCAD → STL) |

FreeCAD fitting builder (`freecad_build.py`, all solids made with real FreeCAD operations):

| Feature | CAD operation |
|---|---|
| cylinder / cone sections | `Part.makeCylinder` / `Part.makeCone` |
| section chamfers | `Shape.makeChamfer` on the actual circular end edge |
| grooves | boolean cut of a ring |
| hex section | extruded hexagon (`Face.extrude`) ∩ two 30° chamfer cones (`common`) |
| bore | revolved (r, z) profile (`Face.revolve`, 360°) with countersink chamfers, removed with a boolean cut |
| assembly | `multiFuse` + `removeSplitter`, then validity / single closed solid checks |
| threads | **cosmetic only**: plain cylinder at the major (outer) / minor (bore) diameter. The helix is not modelled, so a CAD part has more volume and mass than the Blender part with cut threads. |
| fillets | the API works (`makeFillet`, probed on FreeCAD 1.1.4), but no spec field uses it yet |

Not supported, and rejected with a validation error rather than replaced by another shape:
- FreeCAD builders for containers, labels, boxes and tubes;
- STEP output from the Blender route;
- `require_step` with an STL source;
- non-solid colliders for imports.

## Selection rules (`backends.select_backend`, first match wins)

1. **Explicit backend:** that backend; it fails if its tool is missing.
2. **`auto` + `mesh_import`:** `import` (an existing model is preferred).
3. **`auto` + (`require_step` or `accuracy: engineering`):** `freecad`, if a FreeCAD builder exists for the method
   and FreeCAD is installed.
4. **`auto` + `require_step`, when rule 3 is impossible:** an error. The STEP requirement is never dropped silently.
5. **`auto` + `engineering`, CAD route unavailable:** `blender`, with the reason recorded.
6. **`auto`, otherwise:** `blender`.

- **Category:** the asset category is not an input. An "industrial" label does not make an asset CAD.
- **Determinism:** the decision depends only on the spec and on the tool configuration (`backends.tools()`).
- **Recording:** the decision, the rule and the reason go to `asset_info.json` → `geometry_backend`, and the backend
  to `registry.json`.
- **Commands:**
  - `python3 scripts/assets/backends.py select <spec>` prints the decision without building anything.
  - `python3 scripts/assets/backends.py tools` shows the detected tools.

## FreeCAD invocation

- **Discovery** (`backends.find_freecad`; it only checks files and never runs FreeCAD):
  `$FREECAD_EXECUTABLE` → `freecadcmd` / `FreeCADCmd` on `PATH` → the newest `~/Applications/FreeCAD*.AppImage`.
- **Command:**
  - AppImage: `<AppImage> freecadcmd freecad_build.py`;
  - console binary: `freecadcmd freecad_build.py`.
- **Inputs:** environment variables (`FCB_MODE`, `FCB_SPEC`, `FCB_SOURCE`, `FCB_OUT_DIR`, `FCB_RESULT`), because
  `freecadcmd` treats extra arguments as files to open. Blender's `PYTHONPATH` / `PYTHONHOME` / `LD_LIBRARY_PATH`
  are removed.
- **Result:** a JSON file whose `ok` field is authoritative, because `freecadcmd`'s exit code is not reliable.
- **Log:** `logs/assets/library/<id>/freecad.log` (git-ignored).
- **Do not run `<AppImage> --version`:** it starts the FreeCAD GUI. `scripts/check_environment.sh` reads the version
  through `freecadcmd` instead.
- **Tested:** FreeCAD 1.1.4 AppImage (Python 3.11) on Ubuntu 22.04.

## Checks on the CAD routes

- **In FreeCAD (`cad.checks`):**
  - a valid, closed single solid;
  - the tight bounding box (`optimalBoundingBox`; `BoundBox` is loose on cones) matches the spec envelope;
  - the STEP round trip keeps the volume (1e-6);
  - the tessellation is watertight and its volume is within 0.5 % of the solid.
- **In Blender, the usual checks plus:**
  - the mesh volume against the exact solid volume (2e-3);
  - `cad_mesh_mass_consistency`: mass, COM and inertia are taken from the exact solid and must agree with the mesh
    integral (within 1 % / 0.1 mm);
  - `cad_solid`.
- **Staleness:** an imported asset becomes `stale` when its source file changes (`import_source.sha256`).

## Demonstration (2026-10-28)

| Asset | Route | Result |
|---|---|---|
| `brass_adapter_male` | A, Blender (unchanged; spec has no `backend`) | rebuilt to check: physics and visual USD byte-identical to the committed files (then restored) |
| `brass_adapter_male_cad` | B: `auto` + `engineering` + `require_step` → `freecad` (rule 3) | 34-face solid, 5932.668 mm³; STEP round trip exact; 9960 facets (−0.023 % volume); mass 50.25 g at 8470 kg/m³ |
| `brass_adapter_male_step_import` | C: `auto` + `mesh_import` of the STEP above → `import` | identical solid, mass and inertia to ~1e-8 relative |
| `config/scenes/brass_cad_comparison.json` | all three on the unchanged workstation | 76/76 targeted checks, the workstation's 94/94 + 39/39 on the derived scene; settle: −1.5 mm, ≤ 0.027°, force = weight |

The CAD part has the same envelope as the Blender part (1e-9 m). Its volume is 8.0 % larger, its mass 11.7 % larger
(also because 8470 kg/m³ is used instead of the 45 g target) and its inertia 14–16 % larger. All of this comes from
the cosmetic threads.

## Adding a FreeCAD builder

1. Write `build_<method>(spec)` in `freecad_build.py` with real solids (`Part.*`, booleans, `makeChamfer` /
   `makeFillet`), reading the spec through `asset_lib` helpers, so the Blender and FreeCAD builders share one source
   of parameters.
2. Dispatch it in `main()` and add the method to `backends.FREECAD_METHODS`, with a feature row in
   `FREECAD_FITTING_FEATURES`, or a sibling table.
3. Make sure `asset_lib.nominal_size` / `collider_pieces` cover the method. Colliders stay analytic and do not come
   from the CAD mesh.
4. Add selftest cases (selection and spec errors), a spec with `backend: auto`, and run `generate_asset.py` and the
   targeted validator on a scene.
