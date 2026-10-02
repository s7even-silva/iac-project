#!/usr/bin/env python3
"""Pruebas 2026-09-30: (T1) malla de scoring vs offset, (T2) Biot-Savart vs Elmer,
ambas con muestreo angular ley coseno. Uso:
  validation_runs.py <etiqueta> <E_MeV> <offset_m> <field_scale> <mapa: elmer|bs> <seed> <n_events> <threads>
Escribe una linea JSON en build/verificacion_fuente/results.jsonl."""
import json, subprocess, sys, time, resource
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import run_organ_sweep as ros

REPO = Path(__file__).resolve().parents[4]
BUILD = REPO / "geant4/ActiveShield_Sim/build"
OUT = BUILD / "verificacion_fuente" / "runs"
MAPS = {"elmer": REPO / "field/production/crewhat_elmer_fullscale.map",
        "bs": REPO / "field/production/crewhat_niac_max.map"}

# Plantilla de una corrida, copiada de scripts/pilots/pilot_common.py (v1,
# tag v1-archivo) al sacar los pilotos de main.
MACRO_TEMPLATE = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full

/spacecraft/shipRadius {ship_radius_m} m
/spacecraft/shipHalfLength {ship_half_length_m} m
/spacecraft/worldHalfSize {world_half_size_m} m
{coil_geometry_line}/spacecraft/fieldMap {field_map}
/spacecraft/fieldScale {field_scale}
/spacecraft/phantomOffsetX {offset_x_m} m
/spacecraft/phantomOffsetY 0 m

/run/numberOfThreads {n_threads}
/run/initialize
/random/setSeeds {seed1} {seed2}

/control/verbose 1
/tracking/verbose 0
/run/verbose 0
/event/verbose 0
/run/printProgress {print_progress_every}

/gun/species {species}
/gun/phase {phase}
/gun/fixedEnergyMeV {energy_mev}

/score/create/boxMesh PhantomMesh
/score/mesh/boxSize 271.399 135.6995 888. mm
/score/mesh/nBin 254 127 222
/score/mesh/translate/xyz {offset_x_mm} 0. 0. mm
/score/quantity/energyDeposit energyDeposit
/score/close

/run/beamOn {n_events}
/score/dumpQuantityToFile PhantomMesh energyDeposit PhantomMesh_Edep.txt
/control/shell cp ICRP110.out {out_path}
"""


def build_macro(combo, offset_x_m, seed1, seed2, n_threads, print_progress_every,
                 field_map, coil_geometry, n_events, out_path, field_scale=1.0):
    """Una sola corrida (un solo /run/beamOn) de n_events eventos.
    field_scale=1.0 es el caso con blindaje activo; 0.0, el control."""
    coil_geometry_line = (
        f"/spacecraft/coilGeometry {coil_geometry}\n" if coil_geometry is not None else ""
    )
    return MACRO_TEMPLATE.format(
        ship_radius_m=ros.SHIP_RADIUS_M, ship_half_length_m=ros.SHIP_HALF_LENGTH_M,
        world_half_size_m=ros.WORLD_HALF_SIZE_M, coil_geometry_line=coil_geometry_line,
        field_map=field_map, field_scale=field_scale, offset_x_m=offset_x_m,
        offset_x_mm=f"{float(offset_x_m) * 1000:.1f}", n_threads=n_threads,
        seed1=seed1, seed2=seed2, print_progress_every=print_progress_every,
        species=combo["species"], phase=combo["phase"], energy_mev=combo["energy_mev"],
        n_events=n_events, out_path=out_path,
    )


label, e_mev, offset, fscale, mapname, seed, n_events, threads = sys.argv[1:9]
angular = sys.argv[9] if len(sys.argv) > 9 else "cosine"
OUT.mkdir(parents=True, exist_ok=True)
tag = f"{label}_{angular}_E{e_mev}_x{offset}_f{fscale}_{mapname}_s{seed}_n{n_events}"
out_path = OUT / f"{tag}.out"
combo = {"species": "GCR_H", "phase": "min", "energy_mev": e_mev}
macro = build_macro(combo, offset_x_m=offset, seed1=int(seed), seed2=int(seed) + 1,
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
