#!/usr/bin/env python3
"""Engineering comparison of the brass-adapter variants built by the different geometry backends (system python3).

    python3 scripts/assets/compare_backends.py [--no-render]

Read-only on the asset library: it measures the COMMITTED asset files, regenerates nothing.
  1. FreeCAD  freecad_measure.py reference  exact B-rep volume / area / faces of the CAD STEP + a 1 um reference tessellation
  2. Blender  mesh_compare.py               mesh metrics, feature measurements, sampled two-sided distances to the CAD
                                            surface, collider analysis, comparison renders (docs/images/cad_comparison/)
  3. FreeCAD  freecad_measure.py distances  exact point-to-solid distances for 300 samples per mesh (proxy error)
  4. here     controlled physics (one density for all), settle results of the brass_backend_comparison scene
Writes logs/assets/backend_comparison/comparison.json and comparison_tables.md. Needs Blender and FreeCAD.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asset_lib as al  # noqa: E402
import backends  # noqa: E402

ASSETS = [("brass_adapter_male", "Blender"), ("brass_adapter_male_cad", "FreeCAD"),
          ("brass_adapter_male_step_import", "STEP import (hull)"), ("brass_adapter_male_step_import_open", "STEP import (open bore)")]
CAD = "brass_adapter_male_cad"
NOMINAL = "config/assets/brass_adapter_male_cad.json"  # the same sections as brass_adapter_male (dimensions identical)
OUT = "logs/assets/backend_comparison"
RENDERS = "docs/images/cad_comparison"
RHO = 8470.0  # controlled comparison density (brass CW617N nominal), kg/m3


def freecad(mode, env, tmp):
    exe = backends.find_freecad()
    if not exe:
        raise SystemExit("FreeCAD not found (set FREECAD_EXECUTABLE)")
    res = os.path.join(tmp, f"fcm_{mode}.json")
    e = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    e.update(FCM_MODE=mode, FCM_STEP=al.abspath(al.asset_paths(CAD)["dir"] + f"/{CAD}.step"), FCM_RESULT=res, **env)
    with open(os.path.join(tmp, f"freecad_{mode}.log"), "w") as log:
        subprocess.run(backends.freecad_command(exe, os.path.join(HERE, "freecad_measure.py")), env=e, stdout=log,
                       stderr=subprocess.STDOUT, timeout=3600, cwd=al.ROOT)
    r = json.load(open(res))
    if not r.get("ok"):
        raise SystemExit(f"freecad_measure {mode} failed: {r.get('error')}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=20000)
    a = ap.parse_args()
    os.makedirs(al.abspath(OUT), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="backend_cmp_")
    print("[compare] 1/3 FreeCAD reference (exact B-rep + 1 um tessellation)", flush=True)
    ref = freecad("reference", {"FCM_OUT": tmp}, tmp)
    job = {"assets": [{"id": i, "label": l} for i, l in ASSETS], "nominal_spec": NOMINAL, "reference_stl": ref["reference_stl"],
           "out_json": os.path.join(tmp, "mesh.json"), "points_out": os.path.join(tmp, "points.json"),
           "render_dir": None if a.no_render else al.abspath(RENDERS), "n_samples": a.samples, "seed": 0}
    json.dump(job, open(os.path.join(tmp, "job.json"), "w"))
    print("[compare] 2/3 Blender measurements" + ("" if a.no_render else " + renders"), flush=True)
    with open(os.path.join(tmp, "blender.log"), "w") as log:
        p = subprocess.Popen([al.blender_bin(), "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                              os.path.join(HERE, "mesh_compare.py"), "--", os.path.join(tmp, "job.json")], cwd=al.ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in p.stdout:
            s = line.decode("utf-8", "replace")
            log.write(s)
            if s.startswith("[compare]"):
                print(s.rstrip(), flush=True)
        if p.wait() != 0:
            raise SystemExit(f"mesh_compare failed; see {tmp}/blender.log")
    mesh = json.load(open(job["out_json"]))
    print("[compare] 3/3 FreeCAD exact distances for the proxy check", flush=True)
    exact = freecad("distances", {"FCM_POINTS": job["points_out"]}, tmp)["distances_mm"]
    for aid, d in exact.items():
        proxy = mesh["assets"][aid]["deviation"].pop("exact_check_points_proxy_mm")
        mesh["assets"][aid]["deviation"]["exact_check"] = {
            "points": len(d), "exact_max_mm": max(d), "exact_mean_mm": sum(d) / len(d),
            "max_abs_proxy_error_mm": max(abs(x - y) for x, y in zip(d, proxy)),
            "note": "Shape.distToShape (exact B-rep) vs. the 1 um reference tessellation for the same points"}
    # controlled physics: every variant at the same density (unit-density inertia scaled to RHO x its own volume)
    for aid, rec in mesh["assets"].items():
        mp = rec["mass_properties"]
        v = mp["volume_m3"]
        rec["controlled_physics"] = {"density_kg_m3": RHO, "volume_m3": v, "mass_kg": RHO * v,
                                     "diagonal_inertia_kg_m2": [x / mp["mass_kg"] * RHO * v for x in mp["diagonal_inertia"]],
                                     "center_of_mass_m": mp["center_of_mass"]}
    vr = al.abspath("logs/assets/brass_backend_comparison/validation_results.json")
    if os.path.isfile(vr):
        val = json.load(open(vr))
        names = {"brass_adapter_male": "AdapterBlender", "brass_adapter_male_cad": "AdapterFreeCAD",
                 "brass_adapter_male_step_import": "AdapterStepImport", "brass_adapter_male_step_import_open": "AdapterStepImportOpen"}
        for aid, inst in names.items():
            b = (val.get("physics") or {}).get("bodies", {}).get(inst)
            if b:
                mesh["assets"][aid]["settle"] = {k: b[k] for k in ("height_change_from_authored_m", "horizontal_drift_from_authored_m",
                                                                    "max_tilt_deg", "final_speed_m_s", "mean_normal_force_last_0_5s_N", "weight_N")}
                mesh["assets"][aid]["settle"]["checks_passed"] = all(c["passed"] for c in val["checks"].get(f"physics:{inst}", {}).values())
        mesh["scene_validation"] = {"scene": "brass_backend_comparison", "summary": val["summary"], "generated": val["generated"]}
    mesh["cad_exact"] = {k: ref[k] for k in ("volume_mm3", "area_mm2", "center_of_mass_mm", "bbox_mm", "valid", "closed", "n_faces",
                                             "n_edges", "faces", "reference_facets", "reference_volume_mm3", "reference_linear_deflection_mm")}
    al.write_json(f"{OUT}/comparison.json", mesh)
    write_tables(mesh)
    print(f"[compare] wrote {OUT}/comparison.json, {OUT}/comparison_tables.md" + ("" if a.no_render else f", renders in {RENDERS}/"), flush=True)


def write_tables(m):
    A = list(m["assets"])
    lab = [m["assets"][a]["label"] for a in A]
    f = lambda x, n=3: "–" if x is None else (f"{x:.{n}f}" if isinstance(x, float) else str(x))
    row = lambda name, vals: f"| {name} | " + " | ".join(vals) + " |"
    o = ["# Backend comparison tables (generated by scripts/assets/compare_backends.py)\n",
         "| Quantity | " + " | ".join(lab) + " |", "|---|" + "---|" * len(A)]
    feat = lambda a: m["assets"][a]["features"]
    o.append(row("backend", [m["assets"][a]["backend"] for a in A]))
    o.append(row("length (mm), nominal 45", [f(feat(a)["length_mm"], 4) for a in A]))
    o.append(row("max OD = hex corners (mm), nominal 24.826", [f(feat(a)["max_od_mm"], 4) for a in A]))
    for i, s in enumerate(feat(A[0])["sections"]):
        if s["type"] == "hex":
            o.append(row(f"hex across flats (mm), nominal {s['nominal_across_flats_mm']:.3f}",
                         [f(min(feat(a)["sections"][i]["across_flats_mm"]), 4) + "–" + f(max(feat(a)["sections"][i]["across_flats_mm"]), 4) for a in A]))
            o.append(row(f"hex corner chamfer length (mm), nominal {s['nominal_corner_chamfer_length_mm']:.3f}",
                         [f(feat(a)["sections"][i]["corner_chamfer_length_mm"], 3) for a in A]))
        else:
            nom = s["nominal_diameter_mm"]
            if s["type"] == "cone":
                o.append(row(f"cone z {s['z_mm'][0]:.0f}–{s['z_mm'][1]:.0f} end diameters, line fit (mm), nominal {nom[0]:.2f} → {nom[1]:.2f}",
                             [" → ".join(f(x, 3) for x in feat(a)["sections"][i]["fitted_end_diameters_mm"]) for a in A]))
            else:
                o.append(row(f"{s['type']} z {s['z_mm'][0]:.0f}–{s['z_mm'][1]:.0f} OD max/min (mm), nominal {nom}",
                             [f(feat(a)["sections"][i].get("outer_diameter_max_mm"), 3) + " / " + f(feat(a)["sections"][i].get("outer_diameter_min_mm"), 3) for a in A]))
            for j, gr in enumerate(s.get("grooves", [])):
                o.append(row(f"groove z {gr['z_mm']:.2f} depth (mm), nominal {gr['nominal_depth_mm']:.2f}",
                             [f(feat(a)["sections"][i]["grooves"][j]["depth_mm"], 3) for a in A]))
    for i, s in enumerate(feat(A[0])["bore"]):
        if s["type"] == "cone":
            o.append(row(f"bore cone z {s['z_mm'][0]:.0f}–{s['z_mm'][1]:.0f} end diameters, line fit (mm), nominal "
                         f"{s['nominal_diameter_mm'][0]:.2f} → {s['nominal_diameter_mm'][1]:.2f}",
                         [" → ".join(f(x, 3) for x in (feat(a)["bore"][i].get("fitted_end_diameters_mm") or [])) or "–" for a in A]))
            continue
        o.append(row(f"bore {s['type']} z {s['z_mm'][0]:.0f}–{s['z_mm'][1]:.0f} diameter min/max (mm), nominal {s['nominal_diameter_mm']}",
                     [f(feat(a)["bore"][i].get("diameter_min_mm"), 3) + " / " + f(feat(a)["bore"][i].get("diameter_max_mm"), 3) for a in A]))
    for end in ("bottom", "top"):
        c0 = feat(A[0])[f"{end}_chamfers"]
        o.append(row(f"{end} outer chamfer length (mm), nominal {c0['outer_nominal_chamfer_mm']:.2f}",
                     [f(feat(a)[f"{end}_chamfers"]["outer_chamfer_length_mm"], 3) for a in A]))
        o.append(row(f"{end} bore chamfer length (mm), nominal {c0['bore_nominal_chamfer_mm']:.2f}",
                     [f(feat(a)[f"{end}_chamfers"]["bore_chamfer_length_mm"], 3) for a in A]))
    o.append(row("axial planes (mm)", [", ".join(f"{z:.2f}" for z in feat(a)["axial_planes_mm"]) for a in A]))
    o.append(row("mesh vertices / triangles", [f"{m['assets'][a]['welded_vertices']} / {m['assets'][a]['triangles']}" for a in A]))
    o.append(row("mesh volume (mm³)", [f(m["assets"][a]["volume_m3"] * 1e9, 2) for a in A]))
    o.append(row("mesh area (mm²)", [f(m["assets"][a]["area_m2"] * 1e6, 2) for a in A]))
    o.append(row("boundary / non-manifold edges", [f"{m['assets'][a]['boundary_edges']} / {m['assets'][a]['non_manifold_edges']}" for a in A]))
    for k, name in (("mesh_to_cad", "mesh → CAD"), ("cad_to_mesh", "CAD → mesh")):
        o.append(row(f"{name} max / mean / p99 (mm), all", [
            f"{f(m['assets'][a]['deviation'][k]['all']['max_mm'], 4)} / {f(m['assets'][a]['deviation'][k]['all']['mean_mm'], 4)} / {f(m['assets'][a]['deviation'][k]['all']['p99_mm'], 4)}" for a in A]))
        o.append(row(f"{name} max / mean (mm), outside thread zone", [
            f"{f(m['assets'][a]['deviation'][k]['outside_thread_zone']['max_mm'], 4)} / {f(m['assets'][a]['deviation'][k]['outside_thread_zone']['mean_mm'], 4)}" for a in A]))
    o.append(row("exact check: max proxy error (mm)", [f(m["assets"][a]["deviation"]["exact_check"]["max_abs_proxy_error_mm"], 5) for a in A]))
    o.append(row("stored mass (g) / density (kg/m³)", [f"{m['assets'][a]['mass_properties']['mass_kg'] * 1e3:.2f} / {m['assets'][a]['mass_properties']['density_kg_m3']:.0f}" for a in A]))
    o.append(row(f"controlled mass at {RHO:.0f} kg/m³ (g)", [f(m["assets"][a]["controlled_physics"]["mass_kg"] * 1e3, 2) for a in A]))
    o.append(row(f"controlled Ixx, Izz at {RHO:.0f} (kg·m²)", [f"{m['assets'][a]['controlled_physics']['diagonal_inertia_kg_m2'][0]:.4e}, {m['assets'][a]['controlled_physics']['diagonal_inertia_kg_m2'][2]:.4e}" for a in A]))
    o.append(row("COM z (mm)", [f(m["assets"][a]["mass_properties"]["center_of_mass"][2] * 1e3, 3) for a in A]))
    o.append(row("colliders", [f"{m['assets'][a]['colliders']['count']} {m['assets'][a]['colliders']['kinds']}" for a in A]))
    o.append(row("collider distance from axis (mm) / bore", [f"{m['assets'][a]['colliders']['min_distance_from_axis_mm']:.3f} / {'open' if m['assets'][a]['colliders']['bore_open'] else 'BLOCKED'}" for a in A]))
    if "settle" in m["assets"][A[0]]:
        o.append(row("settle: Δz (mm) / drift (mm) / force = weight", [
            f"{m['assets'][a]['settle']['height_change_from_authored_m'] * 1e3:.3f} / {m['assets'][a]['settle']['horizontal_drift_from_authored_m'] * 1e3:.3f} / "
            f"{m['assets'][a]['settle']['mean_normal_force_last_0_5s_N']:.4f}={m['assets'][a]['settle']['weight_N']:.4f}" for a in A]))
    c = m["cad_exact"]
    o.append(f"\nExact CAD solid: volume {c['volume_mm3']:.3f} mm³, area {c['area_mm2']:.3f} mm², {c['n_faces']} faces, valid {c['valid']}, "
             f"closed {c['closed']}; reference tessellation {c['reference_facets']} facets (chord error {c['reference_linear_deflection_mm']} mm), "
             f"volume {c['reference_volume_mm3']:.3f} mm³.")
    with open(al.abspath(f"{OUT}/comparison_tables.md"), "w") as fo:
        fo.write("\n".join(o) + "\n")


if __name__ == "__main__":
    main()
