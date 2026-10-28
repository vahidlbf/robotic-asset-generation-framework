#!/bin/bash
# Read-only environment check for a fresh checkout: tool versions, GPU, network access to the robot asset, and the
# stdlib self-test. Installs nothing and starts no simulation.
#   scripts/check_environment.sh
# Uses BLENDER (default: blender) and ISAACSIM_PYTHON (default: $ISAACSIM_PATH/python.sh, else ~/isaacsim/python.sh).
set -u
cd "$(dirname "$0")/.."
BLENDER=${BLENDER:-blender}
ISAAC=${ISAACSIM_PYTHON:-${ISAACSIM_PATH:-$HOME/isaacsim}/python.sh}
ROBOT_URL=https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.2/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd
FAIL=0
ok()   { printf '  [ ok ] %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*"; FAIL=1; }

echo "OS: $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") (tested: Ubuntu 22.04)"
if python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then ok "python3 $(python3 -V 2>&1 | cut -d' ' -f2)"; else bad "python3 >= 3.10 not found"; fi
if command -v "$BLENDER" >/dev/null 2>&1; then
  V=$("$BLENDER" --version 2>/dev/null | head -1)
  case "$V" in "Blender 5.2"*) ok "$V ($BLENDER)";; *) warn "$V ($BLENDER) - tested with Blender 5.2.2";; esac
else bad "Blender not found: set BLENDER=/path/to/blender (needed to generate assets)"; fi
if [ -x "$ISAAC" ]; then
  VF="$(dirname "$ISAAC")/VERSION"
  IV=$([ -f "$VF" ] && head -1 "$VF" || echo "unknown version")
  case "$IV" in 6.2*) ok "Isaac Sim $IV ($ISAAC)";; *) warn "Isaac Sim $IV ($ISAAC) - tested with 6.2.0";; esac
else bad "Isaac Sim python.sh not found at $ISAAC: set ISAACSIM_PYTHON or ISAACSIM_PATH (needed for scenes, validation, GUI)"; fi
# FreeCAD is OPTIONAL (only the freecad / STEP-import backends need it). Discovery never starts the GUI.
FC=$(python3 -c 'import sys; sys.path.insert(0, "scripts/assets"); import backends; print(backends.find_freecad() or "")')
if [ -n "$FC" ]; then
  T=$(mktemp -d)
  printf 'import FreeCAD, os\nopen(os.environ["FC_OUT"], "w").write(".".join(FreeCAD.Version()[:3]))\n' > "$T/v.py"
  CMD=$(python3 -c 'import sys; sys.path.insert(0, "scripts/assets"); import backends; print("\0".join(backends.freecad_command(sys.argv[1], sys.argv[2])))' "$FC" "$T/v.py" | tr '\0' '\n')
  mapfile -t ARGV <<< "$CMD"
  FC_OUT="$T/version" timeout 120 env -u PYTHONPATH -u PYTHONHOME "${ARGV[@]}" >/dev/null 2>&1
  FV=$(cat "$T/version" 2>/dev/null); rm -rf "$T"
  case "$FV" in 1.1*) ok "FreeCAD $FV ($(basename "$FC")) - optional CAD backend";;
                "") warn "FreeCAD found ($(basename "$FC")) but its console mode did not run - CAD backend unavailable";;
                *) warn "FreeCAD $FV ($(basename "$FC")) - tested with 1.1.4 (optional CAD backend)";; esac
else warn "FreeCAD not found (optional): set FREECAD_EXECUTABLE to use the freecad / STEP-import backends"; fi
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader 2>/dev/null | sed 's/^/  [ ok ] GPU /'
else warn "nvidia-smi not found (Isaac Sim needs an NVIDIA RTX GPU; GPU memory sampling is skipped without it)"; fi
if command -v curl >/dev/null 2>&1; then
  C=$(curl -s -o /dev/null -m 15 -w '%{http_code}' -I "$ROBOT_URL")
  if [ "$C" = "200" ]; then ok "robot asset reachable (NVIDIA asset server)"; else warn "robot asset not reachable (HTTP $C): scenes open without the Franka offline"; fi
else warn "curl not found: robot asset reachability not checked"; fi
for f in assets/scenes/waste_sorting_workstation.usd assets/scenes/derived/industrial_brass_sorting.usda \
         assets/scenes/derived/workstation_test_spacer.usda assets/library/registry.json config/waste_sorting_environment.json; do
  [ -f "$f" ] && ok "present: $f" || bad "missing: $f"
done
if python3 scripts/assets/asset_lib.py selftest >/dev/null 2>&1; then ok "asset_lib.py selftest PASS"; else bad "asset_lib.py selftest FAILED (run it directly for details)"; fi
for s in $(python3 -c 'import json; print(" ".join(json.load(open("assets/library/registry.json"))["assets"]))'); do
  st=$(python3 scripts/assets/asset_lib.py list | awk -v a="$s" '$1==a {for(i=1;i<=NF;i++) if ($i ~ /^status=/) print substr($i,8)}')
  [ "$st" = "current" ] && ok "library asset $s current" || bad "library asset $s status=$st"
done
[ $FAIL -eq 0 ] && echo "environment check: OK" || echo "environment check: problems found (see FAIL lines)"
exit $FAIL
