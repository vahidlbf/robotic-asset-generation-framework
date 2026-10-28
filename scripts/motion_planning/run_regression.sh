#!/bin/bash
# Workstation regression against the EXISTING scene (no asset or scene regeneration).
set -u
cd "$(dirname "$0")/../.."
ISAAC=${ISAACSIM_PYTHON:-${ISAACSIM_PATH:-$HOME/isaacsim}/python.sh}
OUT=logs/motion_planning
# the parent ramp project (../) is included only when it is present (original robot-agent-lab checkout)
PARENT_DIRS=""; [ -f ../scripts/run_pipeline.py ] && PARENT_DIRS="../config ../scripts ../assets"
hash_all() { find assets config $PARENT_DIRS -type f 2>/dev/null | grep -v __pycache__ | sort | xargs sha256sum | sha256sum | cut -c1-16; }
H0=$(hash_all)
$ISAAC scripts/workstation/validate_scene.py > $OUT/regression_validate.log 2>&1; V=$?
$ISAAC scripts/workstation/run_physics_test.py > $OUT/regression_physics.log 2>&1; P=$?
$ISAAC scripts/workstation/open_scene.py --self-test > $OUT/regression_gui_selftest.log 2>&1; G=$?
H1=$(hash_all)
VS=$(grep -oE "[0-9]+/[0-9]+ static checks passed" $OUT/regression_validate.log | tail -1)
PS=$(grep -oE "[0-9]+/[0-9]+ dynamic checks passed" $OUT/regression_physics.log | tail -1)
GS=$(grep -oE "self-test (PASS|FAIL)" $OUT/regression_gui_selftest.log | tail -1)
OK=false; [ $V -eq 0 ] && [ $P -eq 0 ] && [ $G -eq 0 ] && [ "$H0" = "$H1" ] && OK=true
printf '{"ok": %s, "detail": "validate_scene exit %s (%s), run_physics_test exit %s (%s), GUI %s, files unchanged %s", "hash_before": "%s", "hash_after": "%s"}\n' \
  $OK $V "$VS" $P "$PS" "$GS" "$([ "$H0" = "$H1" ] && echo yes || echo NO)" $H0 $H1 > $OUT/regression.json
cat $OUT/regression.json
