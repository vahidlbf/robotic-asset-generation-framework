#!/usr/bin/env python3
"""Geometry backend selection and tool discovery for library assets (standard library only).

Backends (spec field geometry.backend):
  blender   procedural mesh generation in Blender (generate_asset.py builders). DEFAULT when the field is absent, so
            every asset defined before backends existed keeps exactly its validated route.
  freecad   parametric CAD solids in FreeCAD (freecad_build.py), exported as STEP + a tessellated mesh that Blender
            imports for the visual. Only for methods that have a FreeCAD builder (FREECAD_METHODS).
  import    an existing CAD/mesh file (method mesh_import): STL directly in Blender, STEP through FreeCAD.
  auto      deterministic choice from the spec and the installed tools; see select_backend().

    python3 scripts/assets/backends.py tools                       # what is installed (never starts a GUI)
    python3 scripts/assets/backends.py select config/assets/brass_adapter_male_cad.json

FreeCAD is optional: nothing outside the freecad / import(STEP) routes needs it.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import sys

BACKENDS = ["auto", "blender", "freecad", "import"]
# What each backend can actually build (capabilities, not wishes). A method missing here is unsupported by that backend.
BLENDER_METHODS = ["box", "cylinder", "tube", "open_container", "fitting", "label_plate"]
FREECAD_METHODS = ["fitting"]
IMPORT_METHODS = ["mesh_import"]
IMPORT_FORMATS = {".stl": "blender", ".step": "freecad", ".stp": "freecad"}  # format -> tool that reads it
# FreeCAD fitting builder: which section features become real CAD features, and how the rest is represented.
FREECAD_FITTING_FEATURES = {
    "cylinder": "Part.makeCylinder; chamfer_start/end -> Shape.makeChamfer on the end edge; grooves -> boolean cut of a ring",
    "cone": "Part.makeCone; chamfers -> Shape.makeChamfer",
    "hex": "extruded hexagon (Face.extrude) intersected (common) with 30 deg chamfer cones at both ends",
    "thread": "cosmetic thread: plain cylinder at the major (outer) / minor (bore) diameter with its chamfers; "
              "the helix is NOT modelled",
    "bore": "bore sections fused and removed with a boolean cut; bore chamfers -> countersink cones",
}


# ---------------------------------------------------------------------------
# tool discovery
# ---------------------------------------------------------------------------

def find_freecad():
    """FreeCAD executable usable headless, or None. Order: $FREECAD_EXECUTABLE, freecadcmd / FreeCADCmd on PATH,
    the newest ~/Applications/FreeCAD*.AppImage. Only checks files; never runs FreeCAD (an AppImage started with
    --version opens the GUI)."""
    env = os.environ.get("FREECAD_EXECUTABLE")
    if env:
        return env if os.path.isfile(env) and os.access(env, os.X_OK) else None
    for name in ("freecadcmd", "FreeCADCmd"):
        p = shutil.which(name)
        if p:
            return p
    images = sorted(glob.glob(os.path.expanduser("~/Applications/FreeCAD*.AppImage")))
    images = [p for p in images if os.access(p, os.X_OK)]
    return images[-1] if images else None


def freecad_command(exe, script):
    """Command line that runs `script` in FreeCAD's console interpreter. An AppImage needs the `freecadcmd` applet
    argument; freecadcmd itself takes the script directly. Inputs go through environment variables because
    freecadcmd treats extra arguments as files to open."""
    if exe.endswith(".AppImage") or os.path.basename(exe) == "AppRun":
        return [exe, "freecadcmd", script]
    return [exe, script]


def blender_available():
    b = os.environ.get("BLENDER", "blender")
    return bool(shutil.which(b) or (os.path.isfile(b) and os.access(b, os.X_OK)))


def tools():
    fc = find_freecad()
    return {"blender": blender_available(), "freecad": fc is not None,
            "freecad_executable": os.path.basename(fc) if fc else None}


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------

def spec_backend_errors(spec):
    """Combinations that can never work, independent of the installed tools (used by asset_lib.spec_errors)."""
    g = spec["geometry"]
    m, b = g["method"], g.get("backend", "blender")
    errs = []
    if b == "blender" and m not in BLENDER_METHODS:
        errs.append(f"$.geometry.backend: blender has no builder for method '{m}' (supported: {BLENDER_METHODS})")
    if b == "freecad" and m not in FREECAD_METHODS:
        errs.append(f"$.geometry.backend: freecad has no builder for method '{m}' (implemented FreeCAD builders: {FREECAD_METHODS})")
    if b == "import" and m not in IMPORT_METHODS:
        errs.append(f"$.geometry.backend: import needs method 'mesh_import' (got '{m}')")
    if m in IMPORT_METHODS and b not in ("import", "auto"):
        errs.append(f"$.geometry.backend: method mesh_import uses backend 'import' (or 'auto'), not '{b}'")
    if g.get("require_step") and (b == "blender" or (m not in FREECAD_METHODS and m not in IMPORT_METHODS)):
        errs.append(f"$.geometry.require_step: STEP is produced only by the FreeCAD builders ({FREECAD_METHODS}) or by a "
                    f"STEP source (mesh_import); not possible for method '{m}' with backend '{b}'")
    if g.get("require_step") and m in IMPORT_METHODS and os.path.splitext(g.get("source", ""))[1].lower() not in (".step", ".stp"):
        errs.append("$.geometry.require_step: an imported STL has no STEP to keep; import a STEP source instead")
    if m in IMPORT_METHODS and os.path.splitext(g.get("source", ""))[1].lower() not in IMPORT_FORMATS:
        errs.append(f"$.geometry.source: unsupported format (supported: {sorted(IMPORT_FORMATS)})")
    return errs


def select_backend(spec, available=None):
    """Deterministic backend decision for a spec and a tool configuration.
    Returns {"backend", "requested", "reason", "rules", "tools", "ok", "error"}. Rules (first match wins):
      1. explicit backend (blender / freecad / import)            -> that backend, if its tool is installed
      2. auto + method mesh_import                                -> import (an existing model is preferred)
      3. auto + (require_step or accuracy == engineering)
         + a FreeCAD builder exists for the method + FreeCAD installed -> freecad
      4. auto + require_step but rule 3 impossible                -> error (STEP cannot be produced; never silently dropped)
      5. auto + accuracy engineering, FreeCAD missing / no builder -> blender, with the reason recorded
      6. auto otherwise                                           -> blender (procedural mesh is sufficient)
    The asset category is deliberately NOT a rule input: an 'industrial' label does not imply CAD."""
    g = spec["geometry"]
    m = g["method"]
    req = g.get("backend", "blender")
    t = dict(available) if available is not None else tools()
    out = {"requested": req, "method": m, "accuracy": g.get("accuracy", "visual"), "require_step": bool(g.get("require_step")),
           "tools": t, "rules": [], "ok": True, "error": None, "backend": None, "reason": ""}

    def need(tool, why):
        if not t.get(tool):
            out.update(ok=False, error=f"{why} needs {tool}, which is not installed"
                       + (" (set FREECAD_EXECUTABLE)" if tool == "freecad" else " (set BLENDER)"))
        return out

    errs = spec_backend_errors(spec)
    if errs:
        out.update(ok=False, error="; ".join(errs))
        return out
    if req in ("blender", "freecad", "import"):
        out["rules"].append("1: explicit backend")
        out.update(backend=req, reason=f"explicitly requested backend '{req}'"
                   + (" (default for specs without geometry.backend)" if "backend" not in g else ""))
        if req == "freecad":
            return need("freecad", "the FreeCAD route")
        if req == "import":
            tool = IMPORT_FORMATS[os.path.splitext(g["source"])[1].lower()]
            need("blender", "importing a mesh")
            return need(tool, f"reading {os.path.splitext(g['source'])[1]}") if out["ok"] else out
        return need("blender", "the Blender route")
    # auto
    if m in IMPORT_METHODS:
        out["rules"].append("2: auto + mesh_import -> import")
        tool = IMPORT_FORMATS[os.path.splitext(g["source"])[1].lower()]
        out.update(backend="import", reason=f"an existing model is given ({g['source']}); {os.path.splitext(g['source'])[1]} is read by {tool}")
        need("blender", "importing a mesh")
        return need(tool, f"reading {os.path.splitext(g['source'])[1]}") if out["ok"] else out
    wants_cad = out["require_step"] or out["accuracy"] == "engineering"
    has_builder = m in FREECAD_METHODS
    if wants_cad and has_builder and t.get("freecad"):
        out["rules"].append("3: auto + engineering/STEP + FreeCAD builder + FreeCAD installed -> freecad")
        why = "a STEP file is required" if out["require_step"] else "engineering accuracy requested"
        out.update(backend="freecad", reason=f"{why}, a FreeCAD builder exists for '{m}' and FreeCAD is installed")
        return out
    if out["require_step"]:
        out["rules"].append("4: auto + require_step impossible -> error")
        out.update(ok=False, error=f"STEP required but " + ("FreeCAD is not installed" if has_builder else f"no FreeCAD builder for '{m}'"))
        return out
    if wants_cad:
        out["rules"].append("5: auto + engineering, CAD route unavailable -> blender")
        out.update(backend="blender", reason=f"engineering accuracy requested, but " + (
            "FreeCAD is not installed" if has_builder else f"there is no FreeCAD builder for '{m}'")
                   + "; the Blender builder uses the same dimensions (mesh, no STEP)")
        return need("blender", "the Blender route")
    out["rules"].append("6: auto, visual accuracy -> blender")
    out.update(backend="blender", reason="visual accuracy, no STEP required: the procedural Blender builder is sufficient")
    return need("blender", "the Blender route")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["tools"]:
        print(json.dumps(tools(), indent=1))
        return 0
    if argv[:1] == ["select"] and len(argv) == 2:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import asset_lib as al
        r = select_backend(al.load_json(argv[1]))
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
