#!/usr/bin/env python3
"""Asset specifications, the asset registry and derived-scene instance lists (standard library only).

Importable from system python3, Blender and Isaac Sim's python.sh. Also a CLI:

    python3 scripts/assets/asset_lib.py validate-spec config/assets/test_spacer.json
    python3 scripts/assets/asset_lib.py list
    python3 scripts/assets/asset_lib.py new-scene config/scenes/my_scene.json --scene-id my_scene
    python3 scripts/assets/asset_lib.py add-instance config/scenes/my_scene.json --name Spacer_0 --asset test_spacer --xy -0.5 -0.25
    python3 scripts/assets/asset_lib.py move-instance config/scenes/my_scene.json --name Spacer_0 --xy -0.45 -0.25 --yaw 30
    python3 scripts/assets/asset_lib.py remove-instance config/scenes/my_scene.json --name Spacer_0
    python3 scripts/assets/asset_lib.py add-instance config/scenes/my_scene.json --name Part_0 --asset brass_adapter_male \
        --surface on_instance --support InputTray --xy 0.40 -0.20 --lying --spin 30
    python3 scripts/assets/asset_lib.py add-instance config/scenes/my_scene.json --name Label_A --asset label_bin_a \
        --surface attached --support Crate_A --mount label_+x
    python3 scripts/assets/asset_lib.py scatter config/scenes/my_scene.json --support InputTray --asset brass_adapter_male \
        --count 4 --prefix FittingA_ --seed 11 --spins 30 90 150
    python3 scripts/assets/asset_lib.py deactivate-base-prim config/scenes/my_scene.json --path /World/Objects
    python3 scripts/assets/asset_lib.py set-preview-camera config/scenes/my_scene.json --name close_up --position .. --target ..
    python3 scripts/assets/asset_lib.py set-validation config/scenes/my_scene.json --json '{"drop_test": ["Crate_A"]}'
    python3 scripts/assets/asset_lib.py validate-scene config/scenes/my_scene.json
    python3 scripts/assets/asset_lib.py selftest

Data model (kept separate on purpose):
  A. asset definition   config/assets/<asset_id>.json            (geometry, material, collision, mass; no placement)
  B. generated asset    assets/library/<asset_id>/                (<id>.usd, <id>_visual.usd, asset_info.json)
     registry           assets/library/registry.json             (derived from every asset_info.json)
  C. instances          config/scenes/<scene_id>.json "instances" (name, asset, placement, per-instance overrides)
  D. scene config       config/scenes/<scene_id>.json             (base scene, output layer, instances root)
Editing C/D never touches A/B; only scripts/assets/compose_scene.py turns C/D into a USD layer.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIBRARY_DIR = "assets/library"
REGISTRY = f"{LIBRARY_DIR}/registry.json"
ENV_CONFIG = "config/waste_sorting_environment.json"
SCHEMAS = {"asset": "config/schemas/asset_spec.schema.json", "scene": "config/schemas/scene_instances.schema.json"}
DEFAULT_TOL = 0.0005


# ---------------------------------------------------------------------------
# paths and tools
# ---------------------------------------------------------------------------

def abspath(rel):
    """Project-relative path -> absolute path; refuses anything that leaves the project root."""
    p = os.path.normpath(rel if os.path.isabs(rel) else os.path.join(ROOT, rel))
    if os.path.commonpath([p, ROOT]) != ROOT:
        raise ValueError(f"path outside the project: {rel}")
    return p


def relpath(p):
    return os.path.relpath(os.path.abspath(p), ROOT)


def isaac_python():
    """Isaac Sim interpreter: $ISAACSIM_PYTHON, else $ISAACSIM_PATH/python.sh, else ~/isaacsim/python.sh."""
    if os.environ.get("ISAACSIM_PYTHON"):
        return os.environ["ISAACSIM_PYTHON"]
    return os.path.join(os.environ.get("ISAACSIM_PATH", os.path.expanduser("~/isaacsim")), "python.sh")


def blender_bin():
    return os.environ.get("BLENDER", "blender")


def load_json(rel):
    with open(abspath(rel)) as f:
        return json.load(f)


def write_json(rel, data):
    p = abspath(rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, p)


def sha256_file(p):
    h = hashlib.sha256()
    with open(abspath(p), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def hash_tree(rel_dirs, exclude=()):
    """{relative file path: sha256} for every file under the given project-relative paths."""
    out = {}
    for rd in rel_dirs:
        base = abspath(rd)
        if os.path.isfile(base):
            out[rd] = sha256_file(rd)
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = sorted(d for d in dns if d != "__pycache__")
            for fn in sorted(fns):
                r = relpath(os.path.join(dp, fn))
                if not any(r == e or r.startswith(e.rstrip("/") + "/") for e in exclude):
                    out[r] = sha256_file(r)
    return out


def camel(asset_id):
    return "".join(w.capitalize() for w in asset_id.split("_"))


# ---------------------------------------------------------------------------
# minimal JSON-Schema subset validator (no third-party dependency)
# ---------------------------------------------------------------------------

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is_type(v, t):
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def schema_errors(v, s, at="$"):
    errs = []
    types = s.get("type")
    if types is not None:
        types = types if isinstance(types, list) else [types]
        if not any(_is_type(v, t) for t in types):
            return [f"{at}: expected {'/'.join(types)}, got {type(v).__name__}"]
    if "enum" in s and v not in s["enum"]:
        errs.append(f"{at}: {v!r} not in {s['enum']}")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errs.append(f"{at}: {v} < minimum {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            errs.append(f"{at}: {v} > maximum {s['maximum']}")
        if "exclusiveMinimum" in s and v <= s["exclusiveMinimum"]:
            errs.append(f"{at}: {v} must be > {s['exclusiveMinimum']}")
    if isinstance(v, str) and "pattern" in s and not re.search(s["pattern"], v):
        errs.append(f"{at}: {v!r} does not match {s['pattern']}")
    if isinstance(v, str) and len(v) < s.get("minLength", 0):
        errs.append(f"{at}: shorter than {s['minLength']}")
    if isinstance(v, list):
        if "minItems" in s and len(v) < s["minItems"]:
            errs.append(f"{at}: needs at least {s['minItems']} items")
        if "maxItems" in s and len(v) > s["maxItems"]:
            errs.append(f"{at}: at most {s['maxItems']} items")
        if "items" in s:
            for i, x in enumerate(v):
                errs += schema_errors(x, s["items"], f"{at}[{i}]")
    if isinstance(v, dict):
        for k in s.get("required", []):
            if k not in v:
                errs.append(f"{at}: missing required '{k}'")
        props = s.get("properties", {})
        for k, x in v.items():
            if k in props:
                errs += schema_errors(x, props[k], f"{at}.{k}")
            elif s.get("additionalProperties") is False:
                errs.append(f"{at}: unknown property '{k}'")
            elif isinstance(s.get("additionalProperties"), dict):
                errs += schema_errors(x, s["additionalProperties"], f"{at}.{k}")
    return errs


# ---------------------------------------------------------------------------
# A. asset definitions
# ---------------------------------------------------------------------------

METHOD_PARAMS = {"box": ["size"], "cylinder": ["diameter", "height"], "tube": ["outer_diameter", "inner_diameter", "height"],
                 "open_container": ["size", "wall_thickness", "floor_thickness"], "fitting": ["outer", "bore"],
                 "label_plate": ["size", "text"]}
METHOD_OPTIONAL = {"box": ["bevel"], "cylinder": ["segments"], "tube": ["segments"],
                   "open_container": ["draft_deg", "corner_radius", "corner_segments", "rim", "foot", "band", "ribs", "handles",
                                      "label_holder"],
                   "fitting": ["segments"], "label_plate": ["text_color", "text_height", "text_relief", "bevel"]}
COLLISION_METHODS = {"ring_segments": ["tube"], "container_walls": ["open_container"], "fitting_sections": ["fitting"]}
SECTION_KEYS = {"cylinder": (["diameter"], ["chamfer_start", "chamfer_end", "grooves"]),
                "cone": (["d0", "d1"], ["chamfer_start", "chamfer_end"]),
                "hex": (["across_flats"], ["chamfer"]),
                "thread": (["pitch", "depth"], ["major_diameter", "minor_diameter", "chamfer_start", "chamfer_end"])}
MIN_WALL = 0.0005  # thinnest wall (visual and collider) accepted for turned parts


def spec_errors(spec, env_cfg=None):
    errs = schema_errors(spec, load_json(SCHEMAS["asset"]))
    if errs:
        return errs
    g, col, ph = spec["geometry"], spec["collision"], spec["physics"]
    m = g["method"]
    rep = col["representation"]
    for k in METHOD_PARAMS[m]:
        if k not in g:
            errs.append(f"$.geometry: method '{m}' requires '{k}'")
    for k in g:
        if k != "method" and k not in METHOD_PARAMS[m] + METHOD_OPTIONAL[m]:
            errs.append(f"$.geometry: '{k}' is not a parameter of method '{m}'")
    if errs:
        return errs
    if m == "tube" and g["inner_diameter"] >= g["outer_diameter"]:
        errs.append("$.geometry: inner_diameter must be smaller than outer_diameter")
    if rep in COLLISION_METHODS and m not in COLLISION_METHODS[rep]:
        errs.append(f"$.collision: {rep} is only defined for method(s) {COLLISION_METHODS[rep]}")
    if rep == "ring_segments" and not errs:
        n = col.get("segments", 12)
        if g["outer_diameter"] / 2 * math.cos(math.pi / n) <= g["inner_diameter"] / 2:
            errs.append(f"$.collision: {n} ring segments cannot fit between the diameters; use more segments")
        if n % 4:
            errs.append("$.collision: ring segment count must be a multiple of 4 (keeps the collider bounds equal to the diameter)")
    if "segments" in col and rep not in ("ring_segments", "fitting_sections"):
        errs.append("$.collision: 'segments' only applies to ring_segments / fitting_sections")
    if "zones" in col and rep != "fitting_sections":
        errs.append("$.collision: 'zones' only applies to fitting_sections")
    if m in ("cylinder", "tube") and g.get("segments", 48) % 4:
        errs.append("$.geometry: segments must be a multiple of 4 (keeps the visual bounds equal to the diameter)")
    if m == "open_container":
        errs += _container_errors(g)
    if m == "fitting":
        errs += _fitting_errors(g, col)
    if m == "label_plate" and g.get("text_relief", 0.0006) >= g["size"][1]:
        errs.append("$.geometry: text_relief must be smaller than the plate thickness size[1]")
    has_m, has_d = "mass_kg" in ph, "density_kg_m3" in ph
    if ph["body"] == "dynamic" and has_m == has_d:
        errs.append("$.physics: a dynamic body needs exactly one of mass_kg / density_kg_m3")
    if ph["body"] == "static" and (has_m or has_d):
        errs.append("$.physics: a static body has no mass_kg / density_kg_m3")
    if rep == "none" and ph["body"] != "static":
        errs.append("$.physics: a visual-only asset (collision 'none') must be static")
    if "density_range_kg_m3" in spec.get("validation", {}) and ph["body"] != "dynamic":
        errs.append("$.validation.density_range_kg_m3 only applies to dynamic bodies")
    mat = ph.get("material")
    if mat is None:
        if rep != "none":
            errs.append("$.physics: 'material' is required unless collision.representation is 'none'")
    elif isinstance(mat, str):
        env_cfg = env_cfg or load_json(ENV_CONFIG)
        if mat not in env_cfg["physics"]["materials"]:
            errs.append(f"$.physics.material: '{mat}' is not in {ENV_CONFIG} physics.materials "
                        f"({sorted(env_cfg['physics']['materials'])}); define it inline instead")
    elif mat["dynamic_friction"] > mat["static_friction"]:
        errs.append("$.physics.material: dynamic_friction > static_friction")
    od = spec.get("output_dir", default_output_dir(spec["asset_id"]))
    if od != default_output_dir(spec["asset_id"]):
        errs.append(f"$.output_dir: must be {default_output_dir(spec['asset_id'])} (asset directory = asset id)")
    return errs


def _container_errors(g):
    errs = []
    c = container_dims(g)
    if c["tf"] <= c["fh"]:
        errs.append("$.geometry: floor_thickness must exceed foot.height (the inner floor sits above the stacking foot)")
    if min(c["L"], c["W"]) / 2 - c["d_in"](c["tf"]) <= 0.01:
        errs.append("$.geometry: no inner floor left (wall_thickness / draft / rim overhang too large)")
    if c["rh"] >= c["H"] - c["tf"]:
        errs.append("$.geometry: rim.height must be smaller than the inner depth")
    if c["rc"] < c["t"] + c["ro"] + 0.001:
        errs.append("$.geometry: corner_radius must exceed wall_thickness + rim.overhang + 1 mm (inner corners stay rounded)")
    if "ribs" in g and g["ribs"]["depth"] > c["ro"]:
        errs.append("$.geometry: ribs.depth must not exceed rim.overhang (ribs stay inside the rim outline)")
    if "band" in g and g["band"]["depth"] > c["ro"]:
        errs.append("$.geometry: band.depth must not exceed rim.overhang")
    lh = g.get("label_holder")
    if lh and not (c["fh"] < lh["z_center"] - lh["height"] / 2 and lh["z_center"] + lh["height"] / 2 < c["H"] - c["rh"]):
        errs.append("$.geometry: label_holder must lie between the foot and the rim")
    h = g.get("handles")
    if h and (h["width"] >= c["W"] - 2 * c["rc"] or c["H"] - c["rh"] - h.get("below_rim", 0.0) - h["height"] < c["tf"]):
        errs.append("$.geometry: handles do not fit in the short walls")
    if h and lh and lh["z_center"] + lh["height"] / 2 > c["H"] - c["rh"] - h.get("below_rim", 0.0) - h["height"]:
        errs.append("$.geometry: label_holder overlaps the hand holes")
    return errs


def fitting_sections(g, which):
    """Outer or bore sections with absolute z0 / z1 (z from 0 at the asset bottom)."""
    out, z = [], 0.0
    for s in g[which]:
        out.append({**s, "z0": z, "z1": z + s["length"]})
        z += s["length"]
    return out


def section_radius_range(s, bore=False):
    """(min, max) radius of a section's surface (chamfers, grooves and thread depth included)."""
    t, c = s["type"], max(s.get("chamfer_start", 0.0), s.get("chamfer_end", 0.0))
    if t == "hex":
        return 0.475 * s["across_flats"] if s.get("chamfer", True) else s["across_flats"] / 2, s["across_flats"] / math.sqrt(3)
    if t == "thread":
        base = s["minor_diameter"] / 2 if bore else s["major_diameter"] / 2
        return (base, base + s["depth"] + c) if bore else (base - max(s["depth"], c), base)
    r = [s["diameter"] / 2] if t == "cylinder" else [s["d0"] / 2, s["d1"] / 2]
    g = max((gr["depth"] for gr in s.get("grooves", [])), default=0.0)
    return (min(r), max(r) + c + g) if bore else (min(r) - max(c, g), max(r))


def _overlap(a, b):
    return a["z0"] < b["z1"] - 1e-12 and b["z0"] < a["z1"] - 1e-12


def _fitting_errors(g, col):
    errs = []
    for which in ("outer", "bore"):
        for i, s in enumerate(g[which]):
            req, opt = SECTION_KEYS[s["type"]]
            req = req + (["major_diameter"] if s["type"] == "thread" and which == "outer" else [])
            req = req + (["minor_diameter"] if s["type"] == "thread" and which == "bore" else [])
            for k in req:
                if k not in s:
                    errs.append(f"$.geometry.{which}[{i}]: a {s['type']} section requires '{k}'")
            for k in s:
                if k not in ["type", "length"] + req + [o for o in opt if o not in ("major_diameter", "minor_diameter")]:
                    errs.append(f"$.geometry.{which}[{i}]: '{k}' is not a parameter of a {which} {s['type']} section")
            if which == "bore" and s["type"] == "hex":
                errs.append(f"$.geometry.bore[{i}]: hex bores are not supported")
            for gr in s.get("grooves", []):
                if not (gr["width"] / 2 < gr["at"] < s["length"] - gr["width"] / 2):
                    errs.append(f"$.geometry.{which}[{i}]: groove at {gr['at']} lies outside the section")
            if s.get("chamfer_start", 0.0) + s.get("chamfer_end", 0.0) >= s["length"]:
                errs.append(f"$.geometry.{which}[{i}]: chamfers longer than the section")
            if s["type"] == "thread" and s["pitch"] > s["length"]:
                errs.append(f"$.geometry.{which}[{i}]: thread shorter than one pitch")
    if errs:
        return errs
    lo, lb = sum(s["length"] for s in g["outer"]), sum(s["length"] for s in g["bore"])
    if abs(lo - lb) > 1e-9:
        errs.append(f"$.geometry: outer length {lo} != bore length {lb}")
    if g.get("segments", 48) % 12:
        errs.append("$.geometry: fitting segments must be a multiple of 12 (hex corners and quarter angles on vertices)")
    outer, bore = fitting_sections(g, "outer"), fitting_sections(g, "bore")
    for o in outer:
        for b in bore:
            if _overlap(o, b) and section_radius_range(o)[0] - section_radius_range(b, True)[1] < MIN_WALL:
                errs.append(f"$.geometry: wall thinner than {MIN_WALL} m between outer {o['type']} at z={o['z0']:.4f} and bore "
                            f"{b['type']} at z={b['z0']:.4f}")
    if col["representation"] == "fitting_sections":
        zones = col.get("zones", [[i] for i in range(len(outer))])
        flat = [i for z in zones for i in z]
        if flat != list(range(len(outer))):
            errs.append(f"$.collision.zones: must list every outer section index once, in order (got {flat})")
        elif col.get("segments", 12) % 12:
            errs.append("$.collision.segments: must be a multiple of 12 (flats line up with the hex flats)")
        else:
            for zn in fitting_zones({"geometry": g, "collision": col}):
                if zn["apothem"] - zn["bore_radius"] < MIN_WALL:
                    errs.append(f"$.collision.zones[{zn['index']}]: collider wall {zn['apothem'] - zn['bore_radius']:.5f} m thinner "
                                f"than {MIN_WALL} m")
    return errs


def load_spec(rel):
    spec = load_json(rel)
    errs = spec_errors(spec)
    if errs:
        raise ValueError(f"{rel}: invalid asset spec:\n  " + "\n  ".join(errs))
    return spec


def default_output_dir(asset_id):
    return f"{LIBRARY_DIR}/{asset_id}"


def asset_paths(asset_id):
    d = default_output_dir(asset_id)
    return {"dir": d, "usd": f"{d}/{asset_id}.usd", "visual": f"{d}/{asset_id}_visual.usd", "info": f"{d}/asset_info.json"}


def resolve_material(spec, env_cfg=None):
    mat = spec["physics"].get("material")
    if mat is None:
        return None
    if isinstance(mat, str):
        env_cfg = env_cfg or load_json(ENV_CONFIG)
        return {"id": mat, **{k: env_cfg["physics"]["materials"][mat][k] for k in ("static_friction", "dynamic_friction", "restitution")}}
    return dict(mat)


def nominal_size(spec):
    """Outer dimensions [x, y, z] of the asset in its local frame (bottom-centre origin)."""
    g = spec["geometry"]
    m = g["method"]
    if m in ("box", "open_container", "label_plate"):
        return list(g["size"])
    if m == "fitting":
        outer = fitting_sections(g, "outer")
        x = max(section_radius_range(s)[1] for s in outer) * 2  # hex corners lie on the x axis
        y = max(s["across_flats"] if s["type"] == "hex" else 2 * section_radius_range(s)[1] for s in outer)
        return [x, y, outer[-1]["z1"]]
    d = g["diameter"] if m == "cylinder" else g["outer_diameter"]
    return [d, d, g["height"]]


def nominal_bounds(spec):
    sx, sy, sz = nominal_size(spec)
    return [[-sx / 2, -sy / 2, 0.0], [sx / 2, sy / 2, sz]]


def expected_colliders(spec):
    c = spec["collision"]
    rep = c["representation"]
    if rep == "ring_segments":
        return c.get("segments", 12)
    if rep == "container_walls":
        return 5
    if rep == "fitting_sections":
        return sum(z["n"] for z in fitting_zones(spec))
    return 0 if rep == "none" else 1


def footprint_radius(spec):
    pts = [p for piece in collider_pieces(spec) for p in piece["points"]] or \
        [(x, y, 0) for x in nominal_bounds(spec)[0][:1] + nominal_bounds(spec)[1][:1] for y in (nominal_bounds(spec)[0][1], nominal_bounds(spec)[1][1])]
    return max(math.hypot(p[0], p[1]) for p in pts)


# ---------------------------------------------------------------------------
# A2. analytic geometry of the methods (shared by the Blender generator, placement and validation)
# ---------------------------------------------------------------------------

def container_dims(g):
    """Open container profile. Offsets d from the envelope (|x| = L/2 - d, |y| = W/2 - d): outer wall d_out(z) tapers
    outwards towards the top, the rim's outer face is at d = 0, the inner wall d_in(z) = d_out(z) + t."""
    L, W, H = g["size"]
    rim, foot = g.get("rim", {}), g.get("foot", {})
    td = math.tan(math.radians(g.get("draft_deg", 0.0)))
    ro = rim.get("overhang", 0.0)
    t = g["wall_thickness"]
    return {"L": L, "W": W, "H": H, "t": t, "tf": g["floor_thickness"], "rh": rim.get("height", 0.0), "ro": ro,
            "rr": rim.get("round", 0.0), "fh": foot.get("height", 0.0), "fi": foot.get("inset", 0.0), "td": td,
            "rc": g.get("corner_radius", 0.01), "d_out": lambda z: ro + (H - z) * td, "d_in": lambda z: ro + (H - z) * td + t}


def container_inner_half(spec, z):
    """Half extents of the collider interior (sharp corners) at height z in the container frame."""
    c = container_dims(spec["geometry"])
    return c["L"] / 2 - c["d_in"](z), c["W"] / 2 - c["d_in"](z)


def _rect(hx, hy, z):
    return [(hx, hy, z), (-hx, hy, z), (-hx, -hy, z), (hx, -hy, z)]


def fitting_zones(spec):
    """Collider zones: consecutive outer sections merged; hex zone = the hex, round zone = circumscribed n-gon of the zone's
    largest radius. Inner faces are tangent to the largest bore radius found in the zone's z range (bore stays open)."""
    g, c = spec["geometry"], spec["collision"]
    outer, bore = fitting_sections(g, "outer"), fitting_sections(g, "bore")
    n_round = c.get("segments", 12)
    zones = []
    for k, idx in enumerate(c.get("zones", [[i] for i in range(len(outer))])):
        secs = [outer[i] for i in idx]
        z = {"index": k, "sections": idx, "z0": secs[0]["z0"], "z1": secs[-1]["z1"]}
        if len(secs) == 1 and secs[0]["type"] == "hex":
            z.update(shape="hex", n=6, apothem=secs[0]["across_flats"] / 2, vertex_offset=0.0)
        else:
            z.update(shape="round", n=n_round, apothem=max(section_radius_range(s)[1] for s in secs), vertex_offset=0.5)
        z["bore_radius"] = max(section_radius_range(b, True)[1] for b in bore if _overlap(b, z))
        zones.append(z)
    return zones


def collider_pieces(spec):
    """Collider pieces in the asset frame: [{"name", "kind": "box"|"convex", "points": [(x,y,z), ...]}] (convex: 8-point
    prisms, bottom quad then top quad). Authoritative for container_walls / fitting_sections (written by generate_asset.py);
    a conservative point envelope for the older representations (used for placement only)."""
    g, rep = spec["geometry"], spec["collision"]["representation"]
    m = g["method"]
    if rep == "none":
        return []
    if rep == "container_walls":
        c = container_dims(g)
        L, W, H, tf, do, di = c["L"], c["W"], c["H"], c["tf"], c["d_out"], c["d_in"]
        # floor: a box (box-convex contacts resolve impacts like the base bins' box floors); walls: convex slabs
        out = [{"name": "Floor", "kind": "box", "points": _rect(L / 2 - do(tf), W / 2 - do(tf), 0.0) + _rect(L / 2 - do(tf), W / 2 - do(tf), tf)}]
        for name, ax in (("WallPosX", 0), ("WallNegX", 0), ("WallPosY", 1), ("WallNegY", 1)):
            sgn = -1.0 if "Neg" in name else 1.0
            half = (L / 2, W / 2)
            n_in_b, n_out_b, n_in_t, n_out_t = half[ax] - di(tf), half[ax] - do(tf), half[ax] - di(H), half[ax]
            s_b, s_t = half[1 - ax] - do(tf), half[1 - ax]
            pts = []
            for z, ni, no, s in ((tf, n_in_b, n_out_b, s_b), (H, n_in_t, n_out_t, s_t)):
                quad = [(ni, -s), (no, -s), (no, s), (ni, s)]
                pts += [((sgn * a, b, z) if ax == 0 else (b, sgn * a, z)) for a, b in quad]
            out.append({"name": name, "kind": "convex", "points": pts})
        return out
    if rep == "fitting_sections":
        out = []
        for zn in fitting_zones(spec):
            n, off = zn["n"], zn["vertex_offset"]
            ro, ri = zn["apothem"] / math.cos(math.pi / n), zn["bore_radius"] / math.cos(math.pi / n)
            for k in range(n):
                a0, a1 = 2 * math.pi * (k + off) / n, 2 * math.pi * (k + 1 + off) / n
                quad = [(ri * math.cos(a0), ri * math.sin(a0)), (ro * math.cos(a0), ro * math.sin(a0)),
                        (ro * math.cos(a1), ro * math.sin(a1)), (ri * math.cos(a1), ri * math.sin(a1))]
                out.append({"name": f"Zone{zn['index']}_{k:02d}", "kind": "convex",
                            "points": [(x, y, zn["z0"]) for x, y in quad] + [(x, y, zn["z1"]) for x, y in quad]})
        return out
    (x0, y0, z0), (x1, y1, z1) = nominal_bounds(spec)
    if m in ("cylinder", "tube"):  # circumscribed 16-gon envelope of the round collider(s)
        r = (x1 - x0) / 2 / math.cos(math.pi / 16)
        ring = [(r * math.cos(2 * math.pi * k / 16), r * math.sin(2 * math.pi * k / 16)) for k in range(16)]
        return [{"name": "Envelope", "kind": "envelope", "points": [(x, y, z) for z in (z0, z1) for x, y in ring]}]
    return [{"name": "Envelope", "kind": "envelope", "points": [(x, y, z) for z in (z0, z1) for x in (x0, x1) for y in (y0, y1)]}]


def support_surface(spec, name=None):
    """Named support surface of an asset: {"z": height in the asset frame, "half": (hx, hy) usable rectangle, "pieces": collider
    pieces that form the surface (exempt from the clearance rule for objects resting on it)}."""
    g = spec["geometry"]
    if g["method"] == "open_container" and name in (None, "inner_floor"):
        c = container_dims(g)
        return {"name": "inner_floor", "z": c["tf"], "half": container_inner_half(spec, c["tf"]), "pieces": ["Floor"]}
    if name in (None, "top") and g["method"] == "box":
        return {"name": "top", "z": g["size"][2], "half": (g["size"][0] / 2, g["size"][1] / 2), "pieces": ["Box", "Envelope"]}
    raise ValueError(f"asset '{spec['asset_id']}' ({g['method']}) has no support surface '{name or 'default'}'")


def mount_frames(spec):
    """Mount points for attached (visual-only) assets: {name: (position in the asset frame, yaw_deg)}; the mounted asset's
    attach_point lands on the position, its local -y (front) facing outwards."""
    g = spec["geometry"]
    out = {}
    if g["method"] == "open_container" and "label_holder" in g:
        c, lh = container_dims(g), g["label_holder"]
        x = c["L"] / 2 - c["d_out"](lh["z_center"] + lh["height"] / 2) + lh["depth"]
        out["label_+x"] = ((x, 0.0, lh["z_center"]), 90.0)
        out["label_-x"] = ((-x, 0.0, lh["z_center"]), -90.0)
    return out


def attach_point(spec):
    """Point of an attachable asset that sits on a mount point (label_plate: centre of its back face)."""
    if spec["geometry"]["method"] == "label_plate":
        w, t, h = spec["geometry"]["size"]
        return (0.0, t / 2, h / 2)
    return (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# B. registry (derived from the per-asset asset_info.json files)
# ---------------------------------------------------------------------------

def asset_info(asset_id):
    p = asset_paths(asset_id)["info"]
    return load_json(p) if os.path.isfile(abspath(p)) else None


def asset_status(asset_id, spec_rel=None):
    """'missing' | 'stale' (spec changed) | 'modified' (files differ from the recorded hashes) | 'failed' | 'current'."""
    info = asset_info(asset_id)
    if info is None:
        return "missing", None
    if not info.get("ok"):
        return "failed", info
    spec_rel = spec_rel or info.get("spec_file")
    if spec_rel and os.path.isfile(abspath(spec_rel)) and canonical_sha256(load_json(spec_rel)) != info.get("spec_sha256"):
        return "stale", info
    d = asset_paths(asset_id)["dir"]
    for name, h in info.get("file_sha256", {}).items():
        f = f"{d}/{name}"
        if not os.path.isfile(abspath(f)) or sha256_file(f) != h:
            return "modified", info
    return "current", info


def rebuild_registry():
    """Rewrite assets/library/registry.json from the asset_info.json files (deterministic, sorted)."""
    entries = {}
    lib = abspath(LIBRARY_DIR)
    if os.path.isdir(lib):
        for name in sorted(os.listdir(lib)):
            ip = os.path.join(lib, name, "asset_info.json")
            if os.path.isfile(ip):
                info = json.load(open(ip))
                entries[info["asset_id"]] = {
                    "category": info["spec"]["category"], "description": info["spec"].get("description", ""),
                    "spec_file": info["spec_file"], "spec_sha256": info["spec_sha256"], "ok": info["ok"],
                    "usd": asset_paths(info["asset_id"])["usd"], "visual": asset_paths(info["asset_id"])["visual"],
                    "body": info["spec"]["physics"]["body"], "mass_kg": (info.get("mass_properties") or {}).get("mass_kg"),
                    "nominal_size_m": nominal_size(info["spec"]), "collision": info["spec"]["collision"]["representation"],
                    "generated_utc": info.get("generated_utc")}
    reg = {"_doc": "Generated by scripts/assets/asset_lib.py rebuild_registry() from assets/library/*/asset_info.json. "
                   "Do not edit by hand; regenerate one asset with scripts/assets/generate_asset.py.",
           "schema_version": 1, "assets": entries}
    if registry() != reg:  # leave the file (and its mtime) alone when nothing changed
        write_json(REGISTRY, reg)
    return reg


def registry():
    return load_json(REGISTRY) if os.path.isfile(abspath(REGISTRY)) else {"assets": {}}


# ---------------------------------------------------------------------------
# C/D. scene configs and instances
# ---------------------------------------------------------------------------

def new_scene(scene_id, env_cfg_rel=ENV_CONFIG, instances_root="/World/UserObjects", description=""):
    env = load_json(env_cfg_rel)
    return {"schema_version": 1, "scene_id": scene_id, "description": description, "base_scene": env["paths"]["scene"],
            "environment_config": env_cfg_rel, "output": f"assets/scenes/derived/{scene_id}.usda",
            "instances_root": instances_root, "instances": []}


# quaternions are (w, x, y, z); rotations act on column vectors
def q_axis(axis, deg):
    h = math.radians(deg) / 2
    u = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}[axis]
    return (math.cos(h), *(math.sin(h) * c for c in u))


def q_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def q_rot(q, v):
    w, x, y, z = q
    cx, cy, cz = y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0]
    return (v[0] + 2 * (w * cx + y * cz - z * cy), v[1] + 2 * (w * cy + z * cx - x * cz), v[2] + 2 * (w * cz + x * cy - y * cx))


def q_yaw_deg(q):
    w, x, y, z = q
    return math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def table_top_z(env_cfg):
    return env_cfg["table"]["position"][2] + env_cfg["table"]["height"]


def _lower_hull(pts):
    pts = sorted(set(pts))
    hull = []
    for p in pts:
        while len(hull) >= 2 and (hull[-1][0] - hull[-2][0]) * (p[1] - hull[-2][1]) - (hull[-1][1] - hull[-2][1]) * (p[0] - hull[-2][0]) <= 0:
            hull.pop()
        hull.append(p)
    return hull


def rest_orientation(spec, placement, com):
    """Orientation of the asset in a yaw-free frame. upright: identity. lying: spin about the own axis, lay the axis along +x,
    then tilt about y so that the lower convex hull edge of the colliders under the centre of mass is horizontal."""
    if placement.get("pose", "upright") == "upright":
        return (1.0, 0.0, 0.0, 0.0)
    q0 = q_mul(q_axis("y", 90.0), q_axis("z", placement.get("spin_deg", 0.0)))
    pts = [q_rot(q0, p) for piece in collider_pieces(spec) for p in piece["points"]]
    c = q_rot(q0, com)
    hull = _lower_hull([(round(p[0], 12), round(p[2], 12)) for p in pts])
    for (x0, z0), (x1, z1) in zip(hull[:-1], hull[1:]):
        if x0 - 1e-12 <= c[0] <= x1 + 1e-12:
            return q_mul(q_axis("y", math.degrees(math.atan2(z1 - z0, x1 - x0))), q0)
    raise ValueError(f"{spec['asset_id']}: centre of mass outside the collider hull")


def asset_com(asset_id, spec):
    info = asset_info(asset_id)
    mp = (info or {}).get("mass_properties")
    if mp:
        return tuple(mp["center_of_mass"])
    return (0.0, 0.0, nominal_size(spec)[2] / 2)  # before generation: geometric estimate (pre-checks only)


def scene_poses(scene, env_cfg, specs):
    """World pose of every instance, in config order (supports first):
    {name: {"position", "orientation" (w,x,y,z), "yaw_deg", "surface_z", "support", "support_surface"}}.
    The lowest collider point rests on the surface (+ objects.clearance for dynamic, non-static instances); attached
    instances sit on a mount point of their support. compose_scene.py writes exactly these poses."""
    poses, by_name = {}, {}
    for inst in scene["instances"]:
        name, pl = inst["name"], inst["placement"]
        spec = specs[inst["asset"]]
        surf = pl["surface"]
        yaw = float(pl.get("yaw_deg", 0.0))
        rec = {"support": pl.get("support"), "support_surface": None}
        if surf in ("on_instance", "attached"):
            if pl.get("support") not in poses:
                raise ValueError(f"{name}: support '{pl.get('support')}' must be an earlier instance")
            sp, sspec = poses[pl["support"]], specs[by_name[pl["support"]]["asset"]]
            if abs(abs(sp["orientation"][0]) ** 2 + sp["orientation"][3] ** 2 - 1) > 1e-9:
                raise ValueError(f"{name}: support '{pl['support']}' must be upright")
        if surf == "attached":
            frames = mount_frames(sspec)
            if pl.get("mount") not in frames:
                raise ValueError(f"{name}: '{pl['support']}' ({sspec['asset_id']}) has no mount '{pl.get('mount')}' ({sorted(frames)})")
            mpos, myaw = frames[pl["mount"]]
            q = q_mul(sp["orientation"], q_axis("z", myaw + yaw))
            ap = q_rot(q, attach_point(spec))
            mw = q_rot(sp["orientation"], mpos)
            pos = [sp["position"][i] + mw[i] - ap[i] for i in range(3)]
            poses[name] = {**rec, "position": pos, "orientation": list(q), "yaw_deg": q_yaw_deg(q), "surface_z": None}
            by_name[name] = inst
            continue
        if surf == "tabletop":
            z_surf = table_top_z(env_cfg)
        elif surf == "floor":
            z_surf = 0.0
        else:
            ss = support_surface(sspec, pl.get("support_surface"))
            z_surf = sp["position"][2] + ss["z"]
            rec["support_surface"] = ss["name"]
        q = q_mul(q_axis("z", yaw), rest_orientation(spec, pl, asset_com(inst["asset"], spec)))
        pts = [q_rot(q, p) for piece in collider_pieces(spec) for p in piece["points"]] or [(0.0, 0.0, 0.0)]
        dyn = spec["physics"]["body"] == "dynamic" and not inst.get("static")
        z = z_surf + (env_cfg["objects"]["clearance"] if dyn else 0.0) - min(p[2] for p in pts)
        poses[name] = {**rec, "position": [float(pl["xy"][0]), float(pl["xy"][1]), z], "orientation": list(q), "yaw_deg": q_yaw_deg(q),
                       "surface_z": z_surf}
        by_name[name] = inst
    return poses


def instance_pose(inst, env_cfg):
    """Upright tabletop/floor instance: bottom-centre position and yaw (kept for callers of the original API)."""
    pl = inst["placement"]
    surface_z = table_top_z(env_cfg) if pl["surface"] == "tabletop" else 0.0
    return [float(pl["xy"][0]), float(pl["xy"][1]), surface_z + env_cfg["objects"]["clearance"]], float(pl.get("yaw_deg", 0.0))


def world_pieces(spec, pose):
    """Collider pieces transformed to the world: [(name, [points])]."""
    q, t = pose["orientation"], pose["position"]
    return [(pc["name"], [tuple(a + b for a, b in zip(q_rot(q, p), t)) for p in pc["points"]]) for pc in collider_pieces(spec)]


def aabb(points):
    return [min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]


def aabb_gap3(a, b):
    """Separation of two AABBs (largest per-axis gap; < 0 = overlapping). A lower bound on the true distance."""
    return max(max(a[0][i] - b[1][i], b[0][i] - a[1][i]) for i in range(3))


def _deactivated(scene, path):
    return any(path == d or path.startswith(d + "/") for d in scene.get("deactivate_base_prims", []))


def _keepouts(env_cfg, scene=None):
    """Analytic footprints (centre xy, radius) of what already stands on the tabletop (skipping deactivated base prims)."""
    out = {}
    if scene is None or not _deactivated(scene, "/World/Objects"):
        for k, o in env_cfg["objects"].items():
            if isinstance(o, dict) and "position" in o:
                out[k] = (o["position"][:2], max(o.get("body_diameter", 0), o.get("top_diameter", 0), o.get("cap_diameter", 0)) / 2)
    out["robot_base"] = (env_cfg["robot"]["base_position"][:2], 0.15)  # panda_link0 casting + margin
    return out


def _rect_circle_gap(lo, hi, c, r):
    dx = max(lo[0] - c[0], 0.0, c[0] - hi[0])
    dy = max(lo[1] - c[1], 0.0, c[1] - hi[1])
    return math.hypot(dx, dy) - r


def placement_issues(scene, env_cfg, specs):
    """Pre-check before any USD is written, from the analytic collider pieces (collider_pieces): tabletop footprint,
    containment in the support surface, gaps to existing objects / the robot base / other instances. Pieces of a support
    surface (e.g. a container floor) are exempt for the objects resting on it. AABB per piece = conservative gaps.
    The authoritative check is validate_asset_scene.py on the composed USD."""
    issues = []
    for inst in scene["instances"]:
        if inst["asset"] not in specs:
            issues.append(f"{inst['name']}: asset '{inst['asset']}' has no spec/registry entry")
    if issues:
        return issues
    try:
        poses = scene_poses(scene, env_cfg, specs)
    except (KeyError, ValueError) as e:
        return [f"pose: {e}"]
    t, gap = env_cfg["table"], env_cfg["validation"]["min_object_gap_m"]
    keep = _keepouts(env_cfg, scene)
    boxes, insts = {}, {i["name"]: i for i in scene["instances"]}
    for inst in scene["instances"]:
        name, pl, spec = inst["name"], inst["placement"], specs[inst["asset"]]
        pieces = world_pieces(spec, poses[name])
        if not pieces:
            continue
        allp = [p for _, pts in pieces for p in pts]
        if pl["surface"] == "tabletop":
            cx, cy = t["position"][:2]
            if max(abs(p[0] - cx) for p in allp) > t["length"] / 2 or max(abs(p[1] - cy) for p in allp) > t["width"] / 2:
                issues.append(f"{name}: footprint leaves the tabletop at xy={pl['xy']}")
        if pl["surface"] == "on_instance":
            sp = poses[pl["support"]]
            sspec = specs[insts[pl["support"]]["asset"]]
            hx, hy = support_surface(sspec, pl.get("support_surface"))["half"]
            qi = (sp["orientation"][0], *(-c for c in sp["orientation"][1:]))
            loc = [q_rot(qi, tuple(p[i] - sp["position"][i] for i in range(3))) for p in allp]
            out = max(max(abs(p[0]) - hx, abs(p[1]) - hy) for p in loc)
            if out > -gap:
                issues.append(f"{name}: {-out:.4f} m from the edge of {pl['support']}'s support surface (minimum gap {gap} m)")
        pb = [(pn, aabb(pts)) for pn, pts in pieces]
        for k, (c, rk) in keep.items():
            d = min(_rect_circle_gap(b[0], b[1], c, rk) for _, b in pb)
            if d < gap:
                issues.append(f"{name}: {d:.4f} m from {k} (minimum gap {gap} m)")
        for other, ob in boxes.items():
            exempt = set()
            for a, b in ((name, other), (other, name)):
                ai = insts[a]
                if ai["placement"].get("support") == b and ai["placement"]["surface"] == "on_instance":
                    exempt |= {(b, pn) for pn in support_surface(specs[insts[b]["asset"]], ai["placement"].get("support_surface"))["pieces"]}
            d = min((aabb_gap3(x, y) for px, x in pb for py, y in ob
                     if (name, px) not in exempt and (other, py) not in exempt), default=float("inf"))
            if d < gap:
                issues.append(f"{name}: {d:.4f} m from instance {other} (minimum gap {gap} m)")
        boxes[name] = pb
    return issues


PROTECTED_BASE_PRIMS = ["/World/PhysicsScene", "/World/Environment", "/World/Workstation/Table", "/World/RobotMount", "/World/Cameras"]


def scene_errors(scene, check_assets=True):
    errs = schema_errors(scene, load_json(SCHEMAS["scene"]))
    if errs:
        return errs
    names = [i["name"] for i in scene["instances"]]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        errs.append(f"$.instances: duplicate names {dup}")
    if scene["output"] == scene["base_scene"]:
        errs.append("$.output must differ from base_scene (the base scene is never overwritten)")
    for rel in (scene["base_scene"], scene["environment_config"]):
        if not os.path.isfile(abspath(rel)):
            errs.append(f"missing file {rel}")
    for d in scene.get("deactivate_base_prims", []):
        if any(p == d or p.startswith(d + "/") or d.startswith(p + "/") for p in PROTECTED_BASE_PRIMS + [scene["instances_root"]]):
            errs.append(f"$.deactivate_base_prims: {d} may not be deactivated (protected: {PROTECTED_BASE_PRIMS})")
    if "preview_camera" in scene and "asset_preview" in scene.get("preview_cameras", {}):
        errs.append("$.preview_cameras: 'asset_preview' is reserved for preview_camera")
    if os.path.isfile(abspath(scene["environment_config"])):
        base_cams = set(load_json(scene["environment_config"]).get("cameras", {}))
        clash = sorted(base_cams & set(scene.get("preview_cameras", {})))
        if clash:
            errs.append(f"$.preview_cameras: {clash} would override base-scene cameras")
    seen = set()
    for i in scene["instances"]:
        pl = i["placement"]
        if pl["surface"] in ("on_instance", "attached"):
            if pl.get("support") not in seen:
                errs.append(f"{i['name']}: placement.support must name an earlier instance")
        elif "support" in pl or "mount" in pl:
            errs.append(f"{i['name']}: support/mount only apply to on_instance/attached placements")
        if pl["surface"] == "attached":
            if "mount" not in pl:
                errs.append(f"{i['name']}: attached placement needs 'mount'")
            if "xy" in pl or "pose" in pl:
                errs.append(f"{i['name']}: attached placement takes no xy / pose")
        elif "xy" not in pl:
            errs.append(f"{i['name']}: placement.xy is required")
        if "spin_deg" in pl and pl.get("pose") != "lying":
            errs.append(f"{i['name']}: spin_deg only applies to pose 'lying'")
        seen.add(i["name"])
    if check_assets:
        reg = registry()["assets"]
        for i in scene["instances"]:
            if i["asset"] not in reg:
                errs.append(f"{i['name']}: asset '{i['asset']}' is not registered (generate it first)")
            elif i.get("static") and reg[i["asset"]]["body"] == "static":
                errs.append(f"{i['name']}: 'static' override is redundant for a static asset")
            elif i["placement"]["surface"] == "attached" and reg[i["asset"]]["collision"] != "none":
                errs.append(f"{i['name']}: only visual-only assets (collision 'none') can be attached")
    return errs


def load_scene(rel, check_assets=True):
    scene = load_json(rel)
    errs = scene_errors(scene, check_assets)
    if errs:
        raise ValueError(f"{rel}: invalid scene config:\n  " + "\n  ".join(errs))
    return scene


def specs_for(scene):
    out = {}
    for i in scene["instances"]:
        info = asset_info(i["asset"])
        if info:
            out[i["asset"]] = info["spec"]
    return out


def scatter(scene, env_cfg, support, asset, count, prefix, seed, spins=(0.0,), pose="lying", attempts=4000):
    """Deterministic rejection sampling (random.Random(seed)) of `count` new instances on `support`'s support surface;
    every accepted candidate passes placement_issues (real collider pieces, minimum gaps). Returns the new instances."""
    rng = random.Random(seed)
    specs = specs_for(scene)
    sup = next(i for i in scene["instances"] if i["name"] == support)
    ainfo = asset_info(asset)
    if ainfo is None:
        raise ValueError(f"asset '{asset}' is not generated")
    specs[asset] = ainfo["spec"]
    sp = scene_poses(scene, env_cfg, specs)[support]
    hx, hy = support_surface(specs[sup["asset"]])["half"]
    added = []
    for k in range(count):
        for _ in range(attempts):
            lx, ly = rng.uniform(-hx, hx), rng.uniform(-hy, hy)
            w = q_rot(sp["orientation"], (lx, ly, 0.0))
            inst = {"name": f"{prefix}{k}", "asset": asset,
                    "placement": {"surface": "on_instance", "support": support, "xy": [round(sp["position"][0] + w[0], 4),
                                  round(sp["position"][1] + w[1], 4)], "yaw_deg": round(rng.uniform(0.0, 360.0), 1)}}
            if pose == "lying":
                inst["placement"].update(pose="lying", spin_deg=float(rng.choice(list(spins))))
            trial = {**scene, "instances": scene["instances"] + [inst]}
            if not [i for i in placement_issues(trial, env_cfg, specs) if i.startswith(inst["name"] + ":")]:
                scene = trial
                added.append(inst)
                break
        else:
            raise ValueError(f"could not place {prefix}{k} without overlap after {attempts} attempts (seed {seed})")
    return added


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _edit_scene(a, fn):
    scene = load_scene(a.scene, check_assets=False)
    fn(scene)
    errs = scene_errors(scene)
    env = load_json(scene["environment_config"])
    issues = placement_issues(scene, env, specs_for(scene))
    if errs or (issues and not a.allow_overlap):
        print("refused (scene config unchanged):\n  " + "\n  ".join(errs + issues))
        return 1
    write_json(a.scene, scene)
    for w in issues:
        print(f"warning: {w}")
    print(f"{a.scene}: {len(scene['instances'])} instance(s) {[i['name'] for i in scene['instances']]}. "
          f"Run compose_scene.py to update {scene['output']}.")
    return 0


def _find(scene, name):
    for i in scene["instances"]:
        if i["name"] == name:
            return i
    raise SystemExit(f"no instance named {name!r}")


def selftest():
    """Positive and negative cases for the spec / scene validators (no files written)."""
    good = {"schema_version": 1, "asset_id": "t_tube", "category": "test", "geometry": {"method": "tube", "outer_diameter": 0.03,
            "inner_diameter": 0.012, "height": 0.02}, "visual_material": {"color": [0.5, 0.5, 0.5]},
            "collision": {"representation": "ring_segments", "segments": 12},
            "physics": {"body": "dynamic", "density_kg_m3": 7850, "material": {"id": "steel", "static_friction": 0.6,
                        "dynamic_friction": 0.5, "restitution": 0.1}}}
    cases = []

    def bad(label, mutate):
        s = copy.deepcopy(good)
        mutate(s)
        cases.append((label, s, False))

    cases.append(("valid tube", good, True))
    bad("missing physics", lambda s: s.pop("physics"))
    bad("negative height", lambda s: s["geometry"].update(height=-0.01))
    bad("inner >= outer", lambda s: s["geometry"].update(inner_diameter=0.04))
    bad("box param on tube", lambda s: s["geometry"].update(size=[1, 1, 1]))
    bad("ring on box", lambda s: s.update(geometry={"method": "box", "size": [0.1, 0.1, 0.1]}))
    bad("mass and density", lambda s: s["physics"].update(mass_kg=0.1))
    bad("unknown env material", lambda s: s["physics"].update(material="unobtainium"))
    bad("unknown key", lambda s: s.update(colour="red"))
    bad("bad id", lambda s: s.update(asset_id="Bad-ID"))
    bad("static with mass", lambda s: s["physics"].update(body="static"))
    bad("restitution > 1", lambda s: s["physics"]["material"].update(restitution=1.5))
    bad("segments not /4", lambda s: s["collision"].update(segments=10))
    cases.append(("env material name", {**copy.deepcopy(good), "physics": {"body": "static", "material": "table"}}, True))
    # newer methods: the project's own specs are the positive cases, mutations of them the negative ones
    extra = {n: load_json(f"config/assets/{n}.json") for n in ("brass_adapter_male", "industrial_blue_crate", "label_bin_a")
             if os.path.isfile(abspath(f"config/assets/{n}.json"))}
    for n, s0 in extra.items():
        cases.append((f"{n} (project spec)", s0, True))

    def bad2(label, base, mutate):
        if base in extra:
            s = copy.deepcopy(extra[base])
            mutate(s)
            cases.append((label, s, False))

    bad2("fitting bore longer than body", "brass_adapter_male", lambda s: s["geometry"]["bore"][0].update(length=0.03))
    bad2("fitting wall too thin", "brass_adapter_male", lambda s: s["geometry"]["bore"][0].update(diameter=0.0195))
    bad2("fitting zones skip a section", "brass_adapter_male", lambda s: s["collision"].update(zones=[[0, 1], [3, 4], [5]]))
    bad2("fitting segments not /12", "brass_adapter_male", lambda s: s["geometry"].update(segments=40))
    bad2("thread without major_diameter", "brass_adapter_male", lambda s: s["geometry"]["outer"][0].pop("major_diameter"))
    bad2("container_walls on a fitting", "brass_adapter_male", lambda s: s["collision"].update(representation="container_walls"))
    bad2("container floor below foot", "industrial_blue_crate", lambda s: s["geometry"].update(floor_thickness=0.01))
    bad2("container ribs deeper than rim", "industrial_blue_crate", lambda s: s["geometry"]["ribs"].update(depth=0.01))
    bad2("container label holder in handles", "industrial_blue_crate", lambda s: s["geometry"]["label_holder"].update(z_center=0.16))
    bad2("visual-only asset dynamic", "label_bin_a", lambda s: s["physics"].update(body="dynamic", mass_kg=0.01))
    bad2("collider without material", "industrial_blue_crate", lambda s: s["physics"].pop("material"))
    ok = True
    for label, s, expect in cases:
        errs = spec_errors(s)
        res = (not errs) == expect
        ok &= res
        print(f"{'ok ' if res else 'BAD'} spec: {label}: {'valid' if not errs else errs[0]}")
    sc = new_scene("selftest_scene")
    sc["instances"] = [{"name": "A", "asset": "t_tube", "placement": {"surface": "tabletop", "xy": [0.0, 0.0]}}]
    for label, mut, expect in [("valid scene", lambda s: None, True),
                               ("duplicate names", lambda s: s["instances"].append(copy.deepcopy(s["instances"][0])), False),
                               ("overwrite base", lambda s: s.update(output=s["base_scene"]), False),
                               ("bad surface", lambda s: s["instances"][0]["placement"].update(surface="ceiling"), False),
                               ("absolute output", lambda s: s.update(output="/tmp/x.usda"), False),
                               ("support not earlier", lambda s: s["instances"][0]["placement"].update(surface="on_instance", support="B"), False),
                               ("attached without mount", lambda s: s["instances"].append(
                                   {"name": "L", "asset": "t_tube", "placement": {"surface": "attached", "support": "A"}}), False),
                               ("deactivate the robot", lambda s: s.update(deactivate_base_prims=["/World/RobotMount"]), False),
                               ("deactivate base objects", lambda s: s.update(deactivate_base_prims=["/World/Objects"]), True),
                               ("camera overrides base camera", lambda s: s.update(preview_cameras={"main": {"position": [1, 1, 1],
                                                                                                           "target": [0, 0, 0]}}), False)]:
        s = copy.deepcopy(sc)
        mut(s)
        errs = scene_errors(s, check_assets=False)
        res = (not errs) == expect
        ok &= res
        print(f"{'ok ' if res else 'BAD'} scene: {label}: {'valid' if not errs else errs[0]}")
    env = load_json(ENV_CONFIG)
    s = copy.deepcopy(sc)
    s["instances"][0]["placement"]["xy"] = env["objects"]["plastic_bottle"]["position"]
    hit = placement_issues(s, env, {"t_tube": good})
    s["instances"][0]["placement"]["xy"] = [0.9, 0.0]
    off = placement_issues(s, env, {"t_tube": good})
    s["instances"][0]["placement"]["xy"] = [-0.55, -0.25]
    free = placement_issues(s, env, {"t_tube": good})
    res = bool(hit) and bool(off) and not free
    ok &= res
    print(f"{'ok ' if res else 'BAD'} placement: on PET bottle -> {hit[:1]}, off table -> {off[:1]}, free spot -> {free}")
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate-spec")
    p.add_argument("spec")
    sub.add_parser("list")
    sub.add_parser("rebuild-registry")
    sub.add_parser("selftest")
    p = sub.add_parser("validate-scene")
    p.add_argument("scene")
    p = sub.add_parser("new-scene")
    p.add_argument("scene")
    p.add_argument("--scene-id", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--overwrite", action="store_true")
    for name in ("add-instance", "move-instance"):
        p = sub.add_parser(name)
        p.add_argument("scene")
        p.add_argument("--name", required=True)
        if name == "add-instance":
            p.add_argument("--asset", required=True)
            p.add_argument("--surface", default="tabletop", choices=["tabletop", "floor", "on_instance", "attached"])
            p.add_argument("--support", help="on_instance / attached: name of an earlier instance")
            p.add_argument("--mount", help="attached: mount point of the support, e.g. label_+x")
            p.add_argument("--static", action="store_true", help="instance override: rigid body disabled")
        p.add_argument("--xy", type=float, nargs=2)
        p.add_argument("--yaw", type=float, default=None)
        p.add_argument("--lying", action="store_true", help="pose 'lying' (axis horizontal, rest pose from the colliders)")
        p.add_argument("--spin", type=float, default=None, help="lying: spin about the own axis (deg)")
        p.add_argument("--allow-overlap", action="store_true", help="write even if the analytic placement pre-check warns")
    p = sub.add_parser("scatter", help="seeded, collision-checked placement of N instances on a support instance")
    p.add_argument("scene")
    p.add_argument("--support", required=True)
    p.add_argument("--asset", required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--prefix", required=True, help="instance names <prefix>0 .. <prefix>N-1")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--spins", type=float, nargs="+", default=[0.0], help="allowed spin angles (lying)")
    p.add_argument("--upright", action="store_true", help="place upright instead of lying")
    p.add_argument("--allow-overlap", action="store_true", help=argparse.SUPPRESS)
    p = sub.add_parser("set-validation", help="scene-level targeted tests (schema: scene_instances.schema.json validation)")
    p.add_argument("scene")
    p.add_argument("--json", required=True, help='e.g. \'{"drop_test": ["Crate_A"], "move_test": "Part_0"}\'')
    p.add_argument("--allow-overlap", action="store_true", help=argparse.SUPPRESS)
    p = sub.add_parser("deactivate-base-prim", help="make a base-scene prim inactive in the derived layer only")
    p.add_argument("scene")
    p.add_argument("--path", required=True)
    p.add_argument("--allow-overlap", action="store_true", help=argparse.SUPPRESS)
    p = sub.add_parser("remove-instance")
    p.add_argument("scene")
    p.add_argument("--name", required=True)
    p.add_argument("--allow-overlap", action="store_true", help=argparse.SUPPRESS)
    p = sub.add_parser("set-preview-camera", help="camera /World/Cameras/AssetPreview (or --name: preview_cameras.<name>)")
    p.add_argument("scene")
    p.add_argument("--name", help="named preview camera (render_previews.py --cameras <name>)")
    p.add_argument("--position", type=float, nargs=3, required=True)
    p.add_argument("--target", type=float, nargs=3, required=True)
    p.add_argument("--focal-length", type=float, default=35.0)
    p.add_argument("--allow-overlap", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "validate-spec":
        errs = spec_errors(load_json(a.spec))
        print("valid" if not errs else "invalid:\n  " + "\n  ".join(errs))
        if not errs:
            s = load_json(a.spec)
            print(f"asset_id={s['asset_id']} method={s['geometry']['method']} size={nominal_size(s)} m "
                  f"collision={s['collision']['representation']} ({expected_colliders(s)} collider(s)) body={s['physics']['body']} "
                  f"material={resolve_material(s)} status={asset_status(s['asset_id'], a.spec)[0]}")
        return 0 if not errs else 1
    if a.cmd == "list":
        for k, v in registry()["assets"].items():
            print(f"{k:24s} {v['category']:22s} {v['body']:8s} mass={v['mass_kg']} size={v['nominal_size_m']} "
                  f"status={asset_status(k)[0]} usd={v['usd']}")
        return 0
    if a.cmd == "rebuild-registry":
        print(f"{len(rebuild_registry()['assets'])} asset(s) in {REGISTRY}")
        return 0
    if a.cmd == "validate-scene":
        scene = load_json(a.scene)
        errs = scene_errors(scene)
        issues = placement_issues(scene, load_json(scene["environment_config"]), specs_for(scene)) if not errs else []
        print("valid" if not errs and not issues else "\n".join(errs + [f"placement: {i}" for i in issues]))
        return 0 if not errs and not issues else 1
    if a.cmd == "new-scene":
        if os.path.exists(abspath(a.scene)) and not a.overwrite:
            print(f"{a.scene} exists (use --overwrite)")
            return 1
        write_json(a.scene, new_scene(a.scene_id, description=a.description))
        print(f"wrote {a.scene}")
        return 0
    if a.cmd == "add-instance":
        def fn(s):
            if any(i["name"] == a.name for i in s["instances"]):
                raise SystemExit(f"instance {a.name!r} already exists (use move-instance)")
            pl = {"surface": a.surface}
            if a.surface != "attached":
                if a.xy is None:
                    raise SystemExit("--xy is required")
                pl["xy"] = a.xy
            pl["yaw_deg"] = a.yaw or 0.0
            for k, v in (("support", a.support), ("mount", a.mount)):
                if v:
                    pl[k] = v
            if a.lying:
                pl.update(pose="lying", spin_deg=a.spin or 0.0)
            inst = {"name": a.name, "asset": a.asset, "placement": pl}
            if a.static:
                inst["static"] = True
            s["instances"].append(inst)
        return _edit_scene(a, fn)
    if a.cmd == "move-instance":
        def fn(s):
            pl = _find(s, a.name)["placement"]
            if a.xy is not None:
                pl["xy"] = a.xy
            if a.yaw is not None:
                pl["yaw_deg"] = a.yaw
            if a.lying:
                pl["pose"] = "lying"
            if a.spin is not None:
                pl["spin_deg"] = a.spin
        return _edit_scene(a, fn)
    if a.cmd == "scatter":
        def fn(s):
            if any(i["name"].startswith(a.prefix) for i in s["instances"]):
                raise SystemExit(f"instances with prefix {a.prefix!r} exist already")
            new = scatter(s, load_json(s["environment_config"]), a.support, a.asset, a.count, a.prefix, a.seed, a.spins,
                          "upright" if a.upright else "lying")
            s["instances"] += new
            for i in new:
                print(f"placed {i['name']}: {i['placement']}")
        return _edit_scene(a, fn)
    if a.cmd == "set-validation":
        def fn(s):
            s["validation"] = json.loads(a.json)
        return _edit_scene(a, fn)
    if a.cmd == "deactivate-base-prim":
        def fn(s):
            s["deactivate_base_prims"] = sorted(set(s.get("deactivate_base_prims", [])) | {a.path})
        return _edit_scene(a, fn)
    if a.cmd == "remove-instance":
        def fn(s):
            _find(s, a.name)
            s["instances"] = [i for i in s["instances"] if i["name"] != a.name]
        return _edit_scene(a, fn)
    if a.cmd == "set-preview-camera":
        def fn(s):
            cam = {"position": a.position, "target": a.target, "focal_length": a.focal_length}
            if a.name:
                s.setdefault("preview_cameras", {})[a.name] = cam
            else:
                s["preview_camera"] = cam
        return _edit_scene(a, fn)
    return 2


if __name__ == "__main__":
    sys.exit(main())
