#!/bin/bash
# Backend comparison scene: the four variants of the Type A brass adapter side by side, upright, same orientation and
# spacing, labelled, on the ORIGINAL workstation tabletop (nothing deactivated):
#   brass_adapter_male                   Blender procedural mesh (route A)
#   brass_adapter_male_cad               FreeCAD solid -> STEP + tessellation -> Blender (route B)
#   brass_adapter_male_step_import       that STEP imported (route C), solid convex-hull collider
#   brass_adapter_male_step_import_open  that STEP imported, open-bore sector colliders (sections_from the CAD spec)
#   scripts/assets/build_backend_comparison.sh [--config-only]
# Isaac overview preview: logs/assets/brass_backend_comparison/base_suites/preview_backend_overview.png. The controlled
# close-ups (neutral material, wireframe, hex, bore) and the measurements come from scripts/assets/compare_backends.py.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python3 scripts/assets/asset_lib.py"
SC=config/scenes/brass_backend_comparison.json
SPECS="config/assets/brass_adapter_male.json config/assets/brass_adapter_male_cad.json config/assets/brass_adapter_male_step_import.json
       config/assets/brass_adapter_male_step_import_open.json config/assets/label_cmp_blender.json config/assets/label_cmp_freecad.json
       config/assets/label_cmp_step.json config/assets/label_cmp_step_open.json"

$L selftest
for s in $SPECS; do $L validate-spec "$s" | head -1; done
$L new-scene $SC --scene-id brass_backend_comparison --overwrite \
   --description "Geometry backend comparison: Type A brass adapter from Blender, FreeCAD, STEP import (solid hull) and STEP import (open-bore colliders), upright, same orientation, on the unchanged workstation."
X=(-0.70 -0.62 -0.54 -0.46)
A=(brass_adapter_male brass_adapter_male_cad brass_adapter_male_step_import brass_adapter_male_step_import_open)
N=(AdapterBlender AdapterFreeCAD AdapterStepImport AdapterStepImportOpen)
LB=(label_cmp_blender label_cmp_freecad label_cmp_step label_cmp_step_open)
for i in 0 1 2 3; do
  $L add-instance $SC --name "${N[$i]}" --asset "${A[$i]}" --xy "${X[$i]}" -0.20
  $L add-instance $SC --name "Label_${N[$i]}" --asset "${LB[$i]}" --xy "${X[$i]}" -0.245
done
$L set-preview-camera $SC --name backend_overview --position -0.58 -0.62 1.02 --target -0.58 -0.21 0.775 --focal-length 24
$L set-validation $SC --json '{"compare_assets": [["brass_adapter_male", "brass_adapter_male_cad"], ["brass_adapter_male_cad", "brass_adapter_male_step_import"], ["brass_adapter_male_cad", "brass_adapter_male_step_import_open"]], "settle_duration_s": 3.0}'
$L validate-scene $SC
[ "${1:-}" = "--config-only" ] && exit 0

ARGS=""
for s in $SPECS; do ARGS="$ARGS --spec $s"; done
python3 scripts/assets/add_asset.py $ARGS --scene $SC --base-suites --preview
