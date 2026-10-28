#!/bin/bash
# Industrial brass-sorting derived scene: (re)write config/scenes/industrial_brass_sorting.json with the documented
# asset_lib.py CLI only (no hand-edited placements), then generate + compose + validate + preview with add_asset.py.
#   scripts/assets/build_industrial_scene.sh [--config-only]
# Needs Blender (BLENDER) and Isaac Sim (ISAACSIM_PYTHON / ISAACSIM_PATH) unless --config-only; see docs/INSTALLATION.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python3 scripts/assets/asset_lib.py"
SC=config/scenes/industrial_brass_sorting.json
SPECS="config/assets/industrial_gray_tray.json config/assets/industrial_blue_crate.json config/assets/label_bin_a.json
       config/assets/label_bin_b.json config/assets/brass_adapter_male.json config/assets/brass_adapter_female.json"

$L selftest
for s in $SPECS; do $L validate-spec "$s"; done
# assets must exist before instances can be checked against their colliders (current assets are not rebuilt)
if [ "${1:-}" != "--config-only" ]; then
  for s in $SPECS; do
    "${BLENDER:-blender}" -b --factory-startup --python-exit-code 1 --python scripts/assets/generate_asset.py -- --spec "$s" \
      2>&1 | grep "\[asset\]"
  done
fi

$L new-scene $SC --scene-id industrial_brass_sorting --overwrite \
   --description "Industrial brass-fitting sorting workstation: gray input tray with 7 brass fittings (4 Type A male, 3 Type B female) in front of the Franka, two blue sorting crates (A: Type A, B: Type B) on the tabletop. The waste-sorting objects, bins/crate/platform and their target frames are deactivated in this derived layer only."
# the waste-sorting content of the base scene is made inactive in the derived layer (base file unchanged)
$L deactivate-base-prim $SC --path /World/Objects
$L deactivate-base-prim $SC --path /World/Workstation/SortingZone
$L deactivate-base-prim $SC --path /World/Targets
# containers (static: resting exactly on the tabletop)
$L add-instance $SC --name InputTray     --asset industrial_gray_tray  --xy 0.42 -0.215
$L add-instance $SC --name sorting_bin_A --asset industrial_blue_crate --xy -0.03 -0.20
$L add-instance $SC --name sorting_bin_B --asset industrial_blue_crate --xy -0.03 0.20
# role labels (visual only) on the crates' +x label holders, facing the tray / robot side
$L add-instance $SC --name label_A --asset label_bin_a --surface attached --support sorting_bin_A --mount label_+x
$L add-instance $SC --name label_B --asset label_bin_b --surface attached --support sorting_bin_B --mount label_+x
# fittings: seeded, collider-checked rest poses on the tray floor (spins put a hex flat down)
$L scatter $SC --support InputTray --asset brass_adapter_male   --count 4 --prefix FittingA_ --seed 11 --spins 30 90 150 210 270 330
$L scatter $SC --support InputTray --asset brass_adapter_female --count 3 --prefix FittingB_ --seed 23 --spins 30 90 150 210 270 330
# preview cameras (/World/Cameras/Industrial*)
$L set-preview-camera $SC --name industrial_overview --position 1.55 -1.45 1.65 --target 0.18 -0.02 0.82 --focal-length 22
$L set-preview-camera $SC --name industrial_tray     --position 0.56 -0.60 1.30 --target 0.42 -0.215 0.76 --focal-length 30
$L set-preview-camera $SC --name industrial_fittings --position 0.45 -0.45 0.95 --target 0.37 -0.215 0.765 --focal-length 34
$L set-preview-camera $SC --name industrial_crates   --position 0.75 -0.85 1.35 --target -0.03 0.0 0.86 --focal-length 26
# targeted tests: cube drops into both (empty) crates, one fitting moved independently, A/B geometry distinct, 7 bodies in the tray
$L set-validation $SC --json '{"drop_test": ["sorting_bin_A", "sorting_bin_B"], "move_test": "FittingA_0",
  "distinct_assets": [["brass_adapter_male", "brass_adapter_female"]], "rigid_bodies_on": {"InputTray": 7}, "settle_duration_s": 3.0}'
$L validate-scene $SC
[ "${1:-}" = "--config-only" ] && exit 0

ARGS=""
for s in $SPECS; do ARGS="$ARGS --spec $s"; done
python3 scripts/assets/add_asset.py $ARGS --scene $SC --preview
# geometric reachability of the pickup / drop poses (Lula IK + endpoint clearance; no motion)
"${ISAACSIM_PYTHON:-${ISAACSIM_PATH:-$HOME/isaacsim}/python.sh}" scripts/assets/reachability_check.py --scene $SC \
  --pick-support InputTray --drop FittingA_=sorting_bin_A FittingB_=sorting_bin_B 2>&1 | grep "\[reach\]"
