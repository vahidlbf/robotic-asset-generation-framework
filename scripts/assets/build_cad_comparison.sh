#!/bin/bash
# CAD backend comparison: the same Type A brass adapter built three ways, side by side on the ORIGINAL workstation
# (nothing deactivated):  brass_adapter_male (Blender, route A), brass_adapter_male_cad (FreeCAD -> STEP -> Blender,
# route B), brass_adapter_male_step_import (that STEP imported as an existing CAD model, route C).
#   scripts/assets/build_cad_comparison.sh [--config-only]
# Needs Blender, FreeCAD (FREECAD_EXECUTABLE or auto-discovery) and Isaac Sim unless --config-only.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python3 scripts/assets/asset_lib.py"
SC=config/scenes/brass_cad_comparison.json
SPECS="config/assets/brass_adapter_male.json config/assets/brass_adapter_male_cad.json config/assets/brass_adapter_male_step_import.json"

$L selftest
for s in $SPECS; do $L validate-spec "$s"; python3 scripts/assets/backends.py select "$s" | grep -E '"backend"|"reason"'; done
if [ "${1:-}" != "--config-only" ]; then
  # route C reads route B's STEP, so the CAD variant is generated first (current assets are skipped)
  for s in $SPECS; do
    "${BLENDER:-blender}" -b --factory-startup --python-exit-code 1 --python scripts/assets/generate_asset.py -- --spec "$s" \
      2>&1 | grep "\[asset\]"
  done
fi
$L new-scene $SC --scene-id brass_cad_comparison --overwrite \
   --description "CAD backend comparison on the unchanged waste-sorting workstation: Type A brass adapter from the Blender builder, the FreeCAD builder and a STEP import."
$L add-instance $SC --name AdapterBlender    --asset brass_adapter_male             --xy -0.55 -0.12 --yaw 90 --lying --spin 30
$L add-instance $SC --name AdapterFreeCAD    --asset brass_adapter_male_cad         --xy -0.55 -0.02 --yaw 90 --lying --spin 30
$L add-instance $SC --name AdapterStepImport --asset brass_adapter_male_step_import --xy -0.55  0.09
$L set-preview-camera $SC --name cad_comparison --position -0.33 -0.24 0.92 --target -0.55 -0.015 0.765 --focal-length 30
$L set-validation $SC --json '{"compare_assets": [["brass_adapter_male", "brass_adapter_male_cad"], ["brass_adapter_male_cad", "brass_adapter_male_step_import"]], "settle_duration_s": 3.0}'
$L validate-scene $SC
[ "${1:-}" = "--config-only" ] && exit 0

ARGS=""
for s in $SPECS; do ARGS="$ARGS --spec $s"; done
python3 scripts/assets/add_asset.py $ARGS --scene $SC --base-suites --preview
