#!/usr/bin/env python3
"""Puebla la cola con combinaciones del barrido de ActiveShield_Sim
(3 especies x hasta 8 bins x 5 posiciones, ver AGENTS.md, "Segundo grupo
de datos" y "Piloto de 8 bins") para la repeticion 0. --bins (default:
0-7, el barrido completo) permite acotar a un subconjunto -- ver el caso
de uso real de 2026-09-13 mas abajo.

No pisa nada ya sembrado: usa el mismo insert_job()/ON CONFLICT DO
NOTHING que seed_jobs.py, asi que cualquier job ya en la cola (running,
done, etc.) queda intacto -- solo se crean los que faltan.

CASO DE USO REAL (2026-09-13): en este momento el trabajo esta repartido
en 3 lugares y solo uno de ellos pasa por el coordinator. Bryam corrio
localmente offsets 2,3,4 para las 3 especies, TODOS los bins salvo
GCR_He bin7 (69 combinaciones, versionadas en resultados/
organ_sweep_manifest_bryam.csv). Joel corrio localmente offsets 0,1,
bins 0-5 de las 3 especies (sin subir a git todavia, por eso no aparece
en ningun CSV del repo) -- se le pidio explicitamente NO tocar bin6/7,
que es justo el trabajo que se reparte por el coordinator. Entre los
dos, bins 0-5 ya estan o van a estar cubiertos en las 5 posiciones SIN
pasar por este sistema -- sembrarlos aqui duplicaria ese computo. Por
eso el sembrado real de este momento es:

    python3 seed_full_sweep.py --n-events 10000 --bins 6,7

(30 combinaciones: 3 especies x 2 bins x 5 posiciones -- de las cuales
11 ya estaban en la cola de antes). Si en el futuro se necesita sembrar
el barrido completo desde cero (ej. un segundo proyecto sin ningun
trabajo local previo), correr sin --bins.

Prioridad y requisitos minimos, mismo criterio ya usado en los jobs
sembrados a mano hasta ahora (ver AGENTS.md, "Cuarto grupo... 5 posiciones
completas de GCR_He bin7... min_ram_gb=8, min_cpu_count=4") mas la
correccion de 2026-09-13 para SEP_p (ver mas abajo):

  - GCR_H/GCR_He: priority = bin_index (0..7) -- energia real =
    MeV/amu * numero_masico (ver AGENTS.md, "GCR_He... resultando MAS
    caro que GCR_H a la misma energia nominal"), asi que bin_index alto
    = mas caro para estas dos especies, medido. bin_index >=
    MIN_RAM_BIN_THRESHOLD_HIGH_ENERGY (6) exige min_ram_gb/min_cpu_count
    -- solo un worker con esos recursos EN VIVO recibe esos jobs (ver
    claim_next_job() en db.py).
  - SEP_p: PRIORIDAD INVERTIDA (priority = N_BINS_PER_SPECIES-1-bin_index)
    -- confirmado en produccion (2026-09-13) que sus corridas de energia
    BAJA (bin_index chico) tardan notablemente mas que las de energia
    alta, patron opuesto al de GCR_H/GCR_He. No hay todavia una medicion
    fina bin-a-bin para SEP_p (a diferencia de la tabla completa de
    GCR_H en AGENTS.md, "Piloto de 8 bins") -- esto solo captura la
    DIRECCION del efecto, no la magnitud exacta. bin_index <=
    MIN_RAM_BIN_THRESHOLD_LOW_ENERGY_SEP (1) exige min_ram_gb/
    min_cpu_count, simetrico al criterio de GCR_H/GCR_He pero en el
    extremo opuesto de la escala de bins.

Uso:
    python3 seed_full_sweep.py --n-events 10000 --bins 6,7   # caso real de hoy
    python3 seed_full_sweep.py --n-events 10000              # barrido completo (0-7)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

# Mismos valores que geant4/ActiveShield_Sim/scripts/run_organ_sweep.py
# (SPECIES_PHASE, OFFSET_X_VALUES_M) y energy_bins.py (N_BINS_PER_SPECIES)
# -- copiados aqui en vez de importados porque ese script vive en un
# proyecto Geant4 que no es un paquete Python instalable desde infra/.
SPECIES = ["GCR_H", "GCR_He", "SEP_p"]
N_BINS_PER_SPECIES = 8
OFFSET_X_VALUES_M = [0.0, 1.0, 2.0, 3.0, 4.0]

MIN_RAM_BIN_THRESHOLD_HIGH_ENERGY = 6   # GCR_H/GCR_He: caro a bin_index alto
MIN_RAM_BIN_THRESHOLD_LOW_ENERGY_SEP = 1  # SEP_p: caro a bin_index bajo
MIN_RAM_GB = 8.0
MIN_CPU_COUNT = 4


def job_priority_and_requirements(species: str, bin_index: int):
    if species == "SEP_p":
        priority = N_BINS_PER_SPECIES - 1 - bin_index
        needs_resources = bin_index <= MIN_RAM_BIN_THRESHOLD_LOW_ENERGY_SEP
    else:
        priority = bin_index
        needs_resources = bin_index >= MIN_RAM_BIN_THRESHOLD_HIGH_ENERGY
    min_ram = MIN_RAM_GB if needs_resources else 0.0
    min_cpu = MIN_CPU_COUNT if needs_resources else 0
    return priority, min_ram, min_cpu


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-events", type=int, required=True)
    parser.add_argument("--repeticion", type=int, default=0)
    parser.add_argument("--bins", type=str, default=None,
                         help="Lista separada por comas de bin_index a sembrar, ej. '6,7'. "
                              "Default: todos (0..N_BINS_PER_SPECIES-1, el barrido completo).")
    args = parser.parse_args()

    if args.bins:
        bin_indices = [int(b) for b in args.bins.split(",")]
        for b in bin_indices:
            if not (0 <= b < N_BINS_PER_SPECIES):
                parser.error(f"bin_index {b} fuera de rango (0..{N_BINS_PER_SPECIES - 1})")
    else:
        bin_indices = list(range(N_BINS_PER_SPECIES))

    db.init_db()
    created, skipped = 0, 0
    for species in SPECIES:
        for bin_index in bin_indices:
            priority, min_ram, min_cpu = job_priority_and_requirements(species, bin_index)
            for offset_x_m in OFFSET_X_VALUES_M:
                job_id = db.insert_job(
                    species=species, bin_index=bin_index, offset_x_m=offset_x_m,
                    repeticion=args.repeticion, n_events=args.n_events, priority=priority,
                    min_ram_gb=min_ram, min_cpu_count=min_cpu,
                )
                if job_id:
                    created += 1
                else:
                    skipped += 1  # ya existia (UNIQUE constraint) -- no se toca

    total = len(SPECIES) * len(bin_indices) * len(OFFSET_X_VALUES_M)
    print(f"Sembrado: {total} combinaciones ({len(SPECIES)} especies x bins {bin_indices} x "
          f"{len(OFFSET_X_VALUES_M)} posiciones), repeticion={args.repeticion}.")
    print(f"{created} jobs nuevos creados, {skipped} ya existian (sin tocar).")


if __name__ == "__main__":
    main()
