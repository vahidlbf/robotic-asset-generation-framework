#!/bin/bash
# Incremental-asset demonstration: one new asset, one derived scene, nothing else regenerated.
#   scripts/assets/run_demo.sh
# Needs Blender (BLENDER, default "blender") and Isaac Sim (ISAACSIM_PYTHON or ISAACSIM_PATH); see docs/INSTALLATION.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python3 scripts/assets/asset_lib.py"
SPEC=config/assets/test_spacer.json
SC=config/scenes/workstation_test_spacer.json

$L selftest
$L validate-spec $SPEC
# scene config: instances only (the asset definition is not touched by any of these edits)
$L new-scene $SC --scene-id workstation_test_spacer --overwrite \
   --description "Base workstation + test_spacer instances (incremental-asset infrastructure demo)"
$L add-instance $SC --name TestSpacer_0 --asset test_spacer --xy -0.55 -0.25
$L add-instance $SC --name TestSpacer_1 --asset test_spacer --xy -0.45 -0.25 --yaw 15
$L add-instance $SC --name TestSpacer_2 --asset test_spacer --xy -0.55 0.20
$L move-instance $SC --name TestSpacer_1 --xy -0.45 -0.22 --yaw 30
$L remove-instance $SC --name TestSpacer_2
$L set-preview-camera $SC --position -0.32 -0.48 0.92 --target -0.50 -0.235 0.762
# generate (forced, to demonstrate a real rebuild of exactly one asset) -> compose -> validate (+ base suites, preview)
python3 scripts/assets/add_asset.py --spec $SPEC --scene $SC --force --base-suites --preview
# the targeted validator must reject a tampered layer
python3 scripts/assets/negative_control.py
