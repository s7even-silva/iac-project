#!/usr/bin/env python3
"""Pruebas 2026-09-30: (T1) malla de scoring vs offset, (T2) Biot-Savart vs Elmer,
ambas con muestreo angular ley coseno. Uso:
  validation_runs.py <etiqueta> <E_MeV> <offset_m> <field_scale> <mapa: elmer|bs> <seed> <n_events> <threads>
Escribe una linea JSON en build/verificacion_fuente/results.jsonl."""
import json, subprocess, sys, time, resource
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SCRIPTS / "pilots"))
import run_organ_sweep as ros
import pilot_common as pc

REPO = Path(__file__).resolve().parents[4]
BUILD = REPO / "geant4/ActiveShield_Sim/build"
OUT = BUILD / "verificacion_fuente" / "runs"
MAPS = {"elmer": REPO / "field/production/crewhat_elmer_fullscale.map",
        "bs": REPO / "field/production/crewhat_niac_max.map"}

label, e_mev, offset, fscale, mapname, seed, n_events, threads = sys.argv[1:9]
angular = sys.argv[9] if len(sys.argv) > 9 else "cosine"
OUT.mkdir(parents=True, exist_ok=True)
tag = f"{label}_{angular}_E{e_mev}_x{offset}_f{fscale}_{mapname}_s{seed}_n{n_events}"
out_path = OUT / f"{tag}.out"
combo = {"species": "GCR_H", "phase": "min", "energy_mev": e_mev}
macro = pc.build_macro(combo, offset_x_m=offset, seed1=int(seed), seed2=int(seed) + 1,
                       n_threads=int(threads), print_progress_every=max(1, int(n_events) // 10),
                       field_map=MAPS[mapname], coil_geometry=ros.DEFAULT_COIL_GEOMETRY,
                       n_events=int(n_events), out_path=out_path, field_scale=float(fscale))
macro = macro.replace("/gun/fixedEnergyMeV", f"/gun/angularDistribution {angular}\n/gun/fixedEnergyMeV")
assert f"/gun/angularDistribution {angular}" in macro and f"translate/xyz {float(offset)*1000:.1f}" in macro
mac = OUT / f"{tag}.mac"; mac.write_text(macro)
t0 = time.time()
with open(OUT / f"{tag}.log", "w") as log:
    r = subprocess.run([str(BUILD / "ICRP110phantoms"), str(mac)], cwd=BUILD, stdout=log, stderr=subprocess.STDOUT)
dt = time.time() - t0
rows = ros.parse_icrp110_out(out_path)
total_edep = sum(v["edep_J"] for k, v in rows.items() if k != 140) if isinstance(rows, dict) else None
rec = {"tag": tag, "rc": r.returncode, "seconds": round(dt, 1),
       "maxrss_children_MB": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024,
       "total_edep_J": total_edep}
with open(OUT.parent / "results.jsonl", "a") as f:
    f.write(json.dumps(rec) + "\n")
print(json.dumps(rec))
