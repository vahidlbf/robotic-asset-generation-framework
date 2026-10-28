"""Analytic layout geometry shared by the layout optimiser and the validators (pure numpy, no Omniverse).

Everything is derived from config/waste_sorting_environment.json with the same rules the asset
generator uses, so the optimiser can evaluate candidate layouts before any USD is built. The final
validation (validate_scene.py) re-checks the chosen layout against the colliders in the built USD.

Conventions: world Z up, metres. Containers/platforms have their origin at the bottom centre; a
container's local X is its length (crate) / width (bin), rotated by its yaw about world Z.
"""

from __future__ import annotations

import math

import numpy as np


def scene_paths(cfg):
    """Prim paths of the sorting-zone destinations (config scene_paths overrides the defaults)."""
    zone = cfg.get("scene_paths", {}).get("sorting_zone", "/World/Workstation/SortingZone")
    d = {"sorting_zone": zone, "paper_bin": f"{zone}/PaperBin", "plastic_bin": f"{zone}/PlasticBin",
         "crate_platform": f"{zone}/CratePlatform", "crate": f"{zone}/GlassCrate", "crate_bottles": f"{zone}/CrateBottles",
         "targets": "/World/Targets"}
    d.update({k: v for k, v in cfg.get("scene_paths", {}).items() if not k.startswith("_")})
    return d


def rotz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


class OBB:
    """Oriented box: centre (3,), rotation R (3x3, columns = box axes), half extents (3,)."""

    def __init__(self, name, center, half, R=None, group=""):
        self.name, self.group = name, group
        self.c = np.asarray(center, float)
        self.h = np.asarray(half, float)
        self.R = np.eye(3) if R is None else np.asarray(R, float)

    def aabb(self):
        e = np.abs(self.R) @ self.h
        return self.c - e, self.c + e

    def signed_distance(self, pts):
        """Signed distance of points (N,3) to the box surface (negative inside)."""
        q = (np.asarray(pts, float) - self.c) @ self.R
        d = np.abs(q) - self.h
        outside = np.linalg.norm(np.maximum(d, 0.0), axis=1)
        inside = np.minimum(d.max(axis=1), 0.0)
        return outside + inside

    def as_dict(self):
        lo, hi = self.aabb()
        return {"name": self.name, "group": self.group, "center": self.c.round(5).tolist(),
                "size": (2 * self.h).round(5).tolist(), "aabb": [lo.round(5).tolist(), hi.round(5).tolist()]}


def _local_box(name, size, center_local, pos, yaw, group):
    R = rotz(yaw)
    return OBB(name, np.asarray(pos, float) + R @ np.asarray(center_local, float), np.asarray(size, float) / 2, R, group)


def open_box_parts(W, D, H, t, tb):
    """Same rule as generate_assets.open_box_parts: bottom + 4 walls, origin at bottom centre."""
    wh = H - tb
    return {
        "Bottom": ([W, D, tb], [0, 0, tb / 2]),
        "WallPosX": ([t, D, wh], [W / 2 - t / 2, 0, tb + wh / 2]),
        "WallNegX": ([t, D, wh], [-W / 2 + t / 2, 0, tb + wh / 2]),
        "WallPosY": ([W - 2 * t, t, wh], [0, D / 2 - t / 2, tb + wh / 2]),
        "WallNegY": ([W - 2 * t, t, wh], [0, -D / 2 + t / 2, tb + wh / 2]),
    }


def crate_parts(c):
    L, W, H, t, tb = c["length"], c["width"], c["height"], c["wall_thickness"], c["bottom_thickness"]
    st, sh = c["separator_thickness"], c["separator_height"]
    nx, ny = c["cells"]
    parts = open_box_parts(L, W, H, t, tb)
    il, iw = L - 2 * t, W - 2 * t
    for i in range(1, nx):
        parts[f"SeparatorX{i}"] = ([st, iw, sh], [-il / 2 + il * i / nx, 0, tb + sh / 2])
    for j in range(1, ny):
        parts[f"SeparatorY{j}"] = ([il, st, sh], [0, -iw / 2 + iw * j / ny, tb + sh / 2])
    return parts


def platform_parts(p):
    """Lab side cabinet (origin bottom centre): recessed kick plinth, cabinet body, overhanging top plate.
    The same boxes are the visual geometry and the static colliders."""
    L, W, H, tt, ov = p["top_length"], p["top_width"], p["height"], p["top_thickness"], p["top_overhang"]
    kick = p["kick_height"]
    bl, bw = L - 2 * ov, W - 2 * ov
    return {
        "Kick": ([bl - 0.03, bw - 0.03, kick], [0, 0, kick / 2]),
        "Body": ([bl, bw, H - tt - kick], [0, 0, kick + (H - tt - kick) / 2]),
        "Top": ([L, W, tt], [0, 0, H - tt / 2]),
    }


def table_boxes(cfg):
    t = cfg["table"]
    L, W, H, T, s, lh = t["length"], t["width"], t["height"], t["top_thickness"], t["leg_size"], t["leg_height"]
    if t["leg_inset_reference"] == "leg_outer_face":
        lx, ly = L / 2 - t["leg_inset"] - s / 2, W / 2 - t["leg_inset"] - s / 2
    else:
        lx, ly = L / 2 - t["leg_inset"], W / 2 - t["leg_inset"]
    pos, yaw = t["position"], t["yaw_deg"]
    out = [_local_box("Tabletop", [L, W, T], [0, 0, H - T / 2], pos, yaw, "table")]
    for n, sx, sy in (("FL", 1, -1), ("FR", 1, 1), ("BL", -1, -1), ("BR", -1, 1)):
        out.append(_local_box(f"Leg_{n}", [s, s, lh], [sx * lx, sy * ly, lh / 2], pos, yaw, "table"))
    return out


def bin_boxes(cfg, key, position=None):
    b = {**cfg["bins"]["common"], **cfg["bins"][key]}
    pos = position if position is not None else b["position"]
    parts = open_box_parts(b["width"], b["depth"], b["height"], b["wall_thickness"], b["wall_thickness"])
    return [_local_box(f"{key}/{n}", s, c, pos, b["yaw_deg"], key) for n, (s, c) in parts.items()]


def platform_boxes(cfg, xy=None, height=None, yaw=None):
    p = dict(cfg["crate_platform"])
    if height is not None:
        p["height"] = height
    pos = [*(xy if xy is not None else p["position"][:2]), 0.0]
    y = p["yaw_deg"] if yaw is None else yaw
    return [_local_box(f"platform/{n}", s, c, pos, y, "platform") for n, (s, c) in platform_parts(p).items()
            if not n.startswith("_")]


def crate_boxes(cfg, xy=None, base_z=None, yaw=None):
    c = cfg["crate"]
    pos = [*(xy if xy is not None else c["position"][:2]), c["position"][2] if base_z is None else base_z]
    y = c["yaw_deg"] if yaw is None else yaw
    return [_local_box(f"crate/{n}", s, cc, pos, y, "crate") for n, (s, cc) in crate_parts(c).items()]


def crate_cells(cfg, xy=None, base_z=None, yaw=None):
    """Compartments with world centre, free (inner) size in crate-local X/Y, floor and rim heights."""
    c = cfg["crate"]
    pos = np.array([*(xy if xy is not None else c["position"][:2]), c["position"][2] if base_z is None else base_z])
    y = c["yaw_deg"] if yaw is None else yaw
    R = rotz(y)
    L, W, t, tb, st = c["length"], c["width"], c["wall_thickness"], c["bottom_thickness"], c["separator_thickness"]
    nx, ny = c["cells"]
    il, iw = L - 2 * t, W - 2 * t
    occupied = {tuple(x) for x in c["bottles"]["cells"]} if c["bottles"]["enabled"] else set()
    cells = []
    for i in range(nx):
        for j in range(ny):
            x0, x1 = -il / 2 + il * i / nx, -il / 2 + il * (i + 1) / nx
            y0, y1 = -iw / 2 + iw * j / ny, -iw / 2 + iw * (j + 1) / ny
            # shrink by half a separator on interior sides
            x0 += st / 2 if i > 0 else 0.0
            x1 -= st / 2 if i < nx - 1 else 0.0
            y0 += st / 2 if j > 0 else 0.0
            y1 -= st / 2 if j < ny - 1 else 0.0
            centre_local = np.array([(x0 + x1) / 2, (y0 + y1) / 2, 0.0])
            cells.append({"index": [i, j], "centre": (pos + R @ centre_local).tolist(), "free_size_local": [x1 - x0, y1 - y0],
                          "floor_z": float(pos[2] + tb), "separator_top_z": float(pos[2] + tb + c["separator_height"]),
                          "rim_z": float(pos[2] + c["height"]), "occupied": (i, j) in occupied,
                          "local_x_axis_world": (R @ np.array([1.0, 0, 0])).tolist()})
    return cells


def bottle_profile_boxes(cfg, name, bottom_xyz, group):
    """Glass bottle collision proxy: body box, shoulder box (mid radius) and neck/lip box (not one full-radius box)."""
    o = cfg["objects"]["glass_bottle"]
    R, zb, zs, H = o["body_diameter"] / 2, o["body_top_z"], o["shoulder_top_z"], o["height"]
    rl = o["lip_diameter"] / 2
    x, y, z = bottom_xyz
    return [OBB(f"{name}/body", [x, y, z + zb / 2], [R, R, zb / 2], group=group),
            OBB(f"{name}/shoulder", [x, y, z + (zb + zs) / 2], [(R + rl) / 2, (R + rl) / 2, (zs - zb) / 2], group=group),
            OBB(f"{name}/neck", [x, y, z + (zs + H) / 2], [rl, rl, (H - zs) / 2], group=group)]


def crate_bottle_boxes(cfg, xy=None, base_z=None, yaw=None):
    out = []
    for cell in crate_cells(cfg, xy, base_z, yaw):
        if cell["occupied"]:
            c = np.array(cell["centre"])
            out += bottle_profile_boxes(cfg, f"crate_bottle{cell['index']}", [c[0], c[1], cell["floor_z"]], "crate_bottles")
    return out


def tabletop_object_boxes(cfg, exclude=()):
    top = cfg["table"]["position"][2] + cfg["table"]["height"] + cfg["objects"]["clearance"]
    out = []
    for k in ("glass_bottle", "plastic_bottle", "paper_cup"):
        if k in exclude:
            continue
        o = cfg["objects"][k]
        r = o.get("body_diameter", o.get("top_diameter")) / 2
        out.append(OBB(f"object/{k}", [o["position"][0], o["position"][1], top + o["height"] / 2], [r, r, o["height"] / 2],
                       group="tabletop_objects"))
    return out


def ground_box(cfg):
    g = cfg["ground"]
    return OBB("ground", [0, 0, -g["thickness"] / 2], [g["size"][0] / 2, g["size"][1] / 2, g["thickness"] / 2], group="ground")


def footprint_overlap(a, b, gap=0.0):
    """True if two boxes' AABBs overlap (with an extra gap) in XY and Z."""
    alo, ahi = a.aabb()
    blo, bhi = b.aabb()
    return bool(np.all(ahi + gap > blo) and np.all(bhi + gap > alo))


def min_aabb_gap(group_a, group_b):
    """Smallest separating distance between two box sets (AABB approximation; negative = overlap)."""
    best = np.inf
    for a in group_a:
        alo, ahi = a.aabb()
        for b in group_b:
            blo, bhi = b.aabb()
            sep = np.maximum(blo - ahi, alo - bhi)  # per-axis separation
            d = sep.max() if (sep > 0).any() else sep.max()
            best = min(best, float(np.linalg.norm(np.maximum(sep, 0))) if (sep > 0).any() else float(d))
    return best
