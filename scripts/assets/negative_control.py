#!/usr/bin/env python3
"""Negative control for validate_asset_scene.py: it must FAIL on a tampered derived layer.

    python3 scripts/assets/negative_control.py [--source-scene config/scenes/workstation_test_spacer.json]

Copies the composed source layer to assets/scenes/derived/negative_control.usda, moves the first instance onto the
PET bottle (bypassing the asset_lib / compose_scene placement gates) and adds an override that shifts the base
scene's PET bottle by 5 cm. Expects exactly these failures: structure.derived_layer_scope,
preservation.base_prims_unchanged and a clearance failure for the moved instance. The temporary scene config and
layer are removed afterwards; the evidence stays in logs/assets/negative_control/.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asset_lib as al  # noqa: E402

TMP_SCENE, TMP_LAYER = "config/scenes/negative_control.json", "assets/scenes/derived/negative_control.usda"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-scene", default="config/scenes/workstation_test_spacer.json")
    a = ap.parse_args()
    src = al.load_scene(a.source_scene)
    env = al.load_json(src["environment_config"])
    first = src["instances"][0]
    pos, _ = al.instance_pose(first, env)
    pet = env["objects"]["plastic_bottle"]["position"]
    text = open(al.abspath(src["output"])).read()
    old = f"double3 xformOp:translate = ({pos[0]:g}, {pos[1]:g}, {pos[2]:g})"
    if old not in text:
        raise SystemExit(f"cannot find {old!r} in {src['output']}")
    text = text.replace(old, f"double3 xformOp:translate = ({pet[0]:g}, {pet[1]:g}, {pos[2]:g})")
    tamper = ('    over "Objects"\n    {\n        over "PlasticBottle"\n        {\n'
              f'            double3 xformOp:translate = ({pet[0] + 0.05:g}, {pet[1]:g}, {pos[2]:g})\n        }}\n    }}\n\n')
    text = text.replace('over "World"\n{\n', 'over "World"\n{\n' + tamper, 1)
    scene = dict(src, scene_id="negative_control", output=TMP_LAYER,
                 instances=[dict(first, placement=dict(first["placement"], xy=pet))] + src["instances"][1:])
    al.write_json(TMP_SCENE, scene)
    with open(al.abspath(TMP_LAYER), "w") as f:
        f.write(text)
    try:
        rc = subprocess.run([al.isaac_python(), "scripts/assets/validate_asset_scene.py", "--scene", TMP_SCENE, "--no-physics"],
                            cwd=al.ROOT, capture_output=True, text=True).returncode
        res = al.load_json("logs/assets/negative_control/validation_results.json")
    finally:
        for p in (TMP_SCENE, TMP_LAYER):
            if os.path.exists(al.abspath(p)):
                os.remove(al.abspath(p))
    failed = set(res["failed"])
    expected = {"structure.derived_layer_scope", "preservation.base_prims_unchanged", f"instance:{first['name']}.clearance_to_scene"}
    ok = rc == 1 and failed == expected
    out = {"passed": ok, "validator_exit_code": rc, "expected_failures": sorted(expected), "actual_failures": sorted(failed),
           "summary": res["summary"]}
    al.write_json("logs/assets/negative_control/negative_control.json", out)
    print(json.dumps(out, indent=1))
    print("negative control", "PASS (validator rejected the tampered layer)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
