#!/usr/bin/env python3
"""NumPy-version regression test for the 2-D geometry helpers of validate_asset_scene.py (no Isaac Sim needed).

    "$ISAACSIM_PYTHON" scripts/assets/test_numpy_compat.py       # or any python3 with NumPy (1.x or 2.x)

NumPy 2 rejects 2-D vectors in np.cross, which crashed the `bore_open` check of every fitting_sections asset.
validate_asset_scene.py starts SimulationApp on import, so the functions under test (cross2, axis_distance_convex)
are taken from its source with `ast` and run unchanged. Exit code 0 only if every case passes.
"""

import ast
import math
import os
import sys
import warnings

import numpy as np

SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_asset_scene.py")
FUNCTIONS = ("cross2", "axis_distance_convex")


def load_functions():
    tree = ast.parse(open(SOURCE).read(), SOURCE)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    missing = set(FUNCTIONS) - {n.name for n in nodes}
    if missing:
        raise SystemExit(f"FAIL: {sorted(missing)} not found in {SOURCE}")
    ns = {"np": np}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), SOURCE, "exec"), ns)
    return ns, {n.name: ast.get_source_segment(open(SOURCE).read(), n) for n in nodes}


def legacy_cross2(u, v):
    """np.cross on 2-D vectors where this NumPy still supports it (deprecated in 2.0), else None."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return np.cross(u, v)
    except ValueError:
        return None


def prism(xy, z0=0.0, z1=0.01):
    """Convex z-prism piece (points in the asset frame) from an xy polygon."""
    xy = np.asarray(xy, float)
    return np.vstack([np.column_stack([xy, np.full(len(xy), z0)]), np.column_stack([xy, np.full(len(xy), z1)])])


def main():
    ns, src = load_functions()
    cross2, axis_distance_convex = ns["cross2"], ns["axis_distance_convex"]
    cases = []

    def check(label, ok, detail=""):
        cases.append(bool(ok))
        print(f"{'ok ' if ok else 'FAIL'} {label}{': ' + str(detail) if detail != '' else ''}")

    # cross2: sign and value
    for label, u, v, want in [("positive (counter-clockwise)", (1.0, 0.0), (0.0, 1.0), 1.0),
                              ("negative (clockwise)", (0.0, 1.0), (1.0, 0.0), -1.0),
                              ("positive, general", (2.0, 1.0), (-1.0, 3.0), 7.0),
                              ("negative, general", (0.003, -0.004), (0.002, -0.009), -1.9e-05),
                              ("zero (collinear)", (2.0, 4.0), (1.0, 2.0), 0.0),
                              ("zero (anti-parallel)", (1.5, -0.5), (-3.0, 1.0), 0.0),
                              ("zero (zero vector)", (0.0, 0.0), (0.7, -0.2), 0.0)]:
        got = cross2(np.array(u), np.array(v))
        check(f"cross2 {label}", np.ndim(got) == 0 and math.isclose(got, want, rel_tol=1e-12, abs_tol=1e-18), got)

    # cross2 equals the z component of the 3-D np.cross (valid on every NumPy) bit for bit, and the legacy 2-D
    # np.cross where this NumPy still has it
    rng = np.random.default_rng(0)
    U, V = rng.normal(scale=0.02, size=(2, 1000, 2))
    ours = np.array([cross2(u, v) for u, v in zip(U, V)])
    ref3 = np.cross(np.pad(U, ((0, 0), (0, 1))), np.pad(V, ((0, 0), (0, 1))))[:, 2]
    check("cross2 == np.cross 3-D z component (1000 seeded pairs, exact)", np.array_equal(ours, ref3),
          f"max |diff| {np.abs(ours - ref3).max():.1e}")
    legacy = legacy_cross2(U[0], V[0])
    if legacy is None:
        print(f"info np.cross rejects 2-D vectors on NumPy {np.__version__} (the original failure); legacy comparison skipped")
    else:
        legacy = np.array([legacy_cross2(u, v) for u, v in zip(U, V)])
        check(f"cross2 == legacy 2-D np.cross on NumPy {np.__version__} (exact)", np.array_equal(ours, legacy))

    # axis_distance_convex: the production function, unchanged algorithm
    check("validator no longer passes 2-D vectors to np.cross", "np.cross" not in src["axis_distance_convex"])
    sq = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    check("axis inside a square -> 0", axis_distance_convex(prism(sq)) == 0.0)
    check("axis on an edge (zero cross product) -> 0", axis_distance_convex(prism([(0, -1), (2, -1), (2, 1), (0, 1)])) == 0.0)
    check("axis on a vertex -> 0", axis_distance_convex(prism([(0, 0), (2, 0), (2, 2), (0, 2)])) == 0.0)
    d = axis_distance_convex(prism([(x + 2.0, y) for x, y in sq]))
    check("square offset along +x -> 1.0", math.isclose(d, 1.0, abs_tol=1e-12), d)
    d = axis_distance_convex(prism([(x - 3.0, y + 4.0) for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]]))
    check("square offset diagonally -> distance to the nearest corner", math.isclose(d, math.hypot(2, 4), rel_tol=1e-12), d)
    ri, ro, half = 0.0071, 0.0105, math.radians(15)   # one fitting_sections ring piece (bore radius ~7.1 mm, 12 segments)
    a = np.linspace(-half, half, 5) + math.radians(40)
    wedge = np.vstack([np.column_stack([ri * np.cos(a), ri * np.sin(a)]), np.column_stack([ro * np.cos(a[::-1]), ro * np.sin(a[::-1])])])
    d = axis_distance_convex(prism(wedge))
    # 5 inner-arc points 7.5 deg apart: the nearest chord midpoint is at ri * cos(3.75 deg)
    check("ring-segment piece -> inner chord distance (bore stays open)", math.isclose(d, ri * math.cos(half / 4), rel_tol=1e-9),
          f"{d * 1000:.6f} mm")

    n_ok = sum(cases)
    print(f"numpy-compat test {'PASS' if n_ok == len(cases) else 'FAIL'}: {n_ok}/{len(cases)} cases (Python {sys.version.split()[0]}, NumPy {np.__version__})")
    return 0 if n_ok == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
