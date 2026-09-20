#!/usr/bin/env python3
"""Puebla jobs_v2 (ver db_v2.py) con combinaciones del barrido de
ActiveShield_Sim -- version 2026-09-20 de seed_full_sweep.py, con
--n-bins como argumento EXPLICITO (a diferencia de seed_full_sweep.py,
que copia N_BINS_PER_SPECIES=8 fijo) -- justo el parametro que motivo
crear jobs_v2: poder sembrar la grilla de energia definitiva que el
equipo decida para produccion (ej. 16 bins), no solo la de 8 ya fija en
el barrido v1.

No pisa nada ya sembrado en jobs_v2 (ON CONFLICT DO NOTHING, mismo
criterio que seed_full_sweep.py) y NO TOCA jobs/results v1 en absoluto --
modulo completamente separado (db_v2, no db), tabla completamente
separada (jobs_v2, no jobs).

Uso:
    python3 seed_full_sweep_v2.py --n-events 5000 --n-bins 16
    python3 seed_full_sweep_v2.py --n-events 5000 --n-bins 16 --bins 6,7  # subconjunto
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import db_v2  # noqa: E402

# Mismos valores que geant4/ActiveShield_Sim/scripts/run_organ_sweep.py
# (SPECIES_PHASE, OFFSET_X_VALUES_M) -- copiados aqui en vez de
# importados, mismo motivo que seed_full_sweep.py ya documenta: ese
# script vive en un proyecto Geant4 que no es un paquete Python
# instalable desde infra/.
SPECIES_PHASE = [("GCR_H", "min"), ("GCR_He", "min"), ("SEP_p", "max")]
OFFSET_X_VALUES_M = [0.0, 1.0, 2.0, 3.0, 4.0]

# Mismos umbrales/criterio de prioridad que seed_full_sweep.py (ver ese
# archivo para el razonamiento completo, con cifras reales de produccion)
# -- SEP_p con prioridad invertida (bin_index bajo = mas caro), GCR_H/He
# con bin_index alto = mas caro. Los umbrales de recursos (MIN_RAM_GB,
# etc.) NO se copian aqui: son ajustes finos calibrados con datos reales
# de la grilla de 8 bins en produccion v1 (ver AGENTS.md) -- no hay
# evidencia todavia de que apliquen igual a una grilla de n_bins distinto,
# asi que jobs_v2 arranca sin min_ram_gb/min_cpu_count/min_cpu_score
# (0 = cualquier worker califica) hasta que haya datos reales propios.
MIN_RAM_BIN_THRESHOLD_HIGH_ENERGY_FRAC = 0.75  # ultimo cuarto de bins = "caro" para GCR
MIN_RAM_BIN_THRESHOLD_LOW_ENERGY_SEP_FRAC = 0.25  # primer cuarto de bins = "caro" para SEP_p


def job_priority(species: str, bin_index: int, n_bins: int) -> int:
    """Mismo signo que seed_full_sweep.py: GCR_H/GCR_He caro a bin_index
    alto (prioridad = bin_index), SEP_p invertido (prioridad = n_bins-1-
    bin_index) -- ver ese script para las cifras reales que motivan el
    signo. Escalado a n_bins arbitrario en vez del 8 fijo de v1."""
    if species == "SEP_p":
        return n_bins - 1 - bin_index
    return bin_index


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-events", type=int, required=True)
    parser.add_argument("--n-bins", type=int, required=True,
                         help="Grilla de energia a sembrar -- SIN default: a diferencia de v1, jobs_v2 "
                              "no asume 8 bins, el equipo debe decidirlo explicitamente.")
    parser.add_argument("--repeticion", type=int, default=0)
    parser.add_argument("--bins", type=str, default=None,
                         help="Lista separada por comas de bin_index a sembrar. Default: todos (0..n_bins-1).")
    args = parser.parse_args()

    if args.n_bins < 1 or args.n_events < 1 or args.repeticion < 0:
        parser.error("n-bins/n-events deben ser positivos y repeticion no negativa")
    if args.bins:
        bin_indices = [int(b) for b in args.bins.split(",")]
        for b in bin_indices:
            if not (0 <= b < args.n_bins):
                parser.error(f"bin_index {b} fuera de rango (0..{args.n_bins - 1})")
    else:
        bin_indices = list(range(args.n_bins))

    # db.init_db() PRIMERO: jobs_v2.claimed_by referencia workers(worker_id)
    # (FK) -- esa tabla solo la crea db.SCHEMA (ver db.py), no db_v2.SCHEMA_V2.
    # En produccion real esto nunca falta (app.py:lifespan() ya llama ambos
    # en orden), pero un script standalone como este si puede correr contra
    # una DB nueva antes de que el coordinator la haya inicializado -- bug
    # real encontrado probando este script (2026-09-20): sqlite3.OperationalError
    # "no such table: main.workers" sin este init_db() explicito primero.
    db.init_db()
    db_v2.init_db_v2()
    created, skipped = 0, 0
    for species, phase in SPECIES_PHASE:
        for bin_index in bin_indices:
            priority = job_priority(species, bin_index, args.n_bins)
            for offset_x_m in OFFSET_X_VALUES_M:
                job_id = db_v2.insert_job_v2(
                    species=species, phase=phase, bin_index=bin_index, n_bins=args.n_bins,
                    offset_x_m=offset_x_m, repeticion=args.repeticion, n_events=args.n_events,
                    priority=priority,
                )
                if job_id:
                    created += 1
                else:
                    skipped += 1

    total = len(SPECIES_PHASE) * len(bin_indices) * len(OFFSET_X_VALUES_M)
    print(f"Sembrado (jobs_v2): {total} combinaciones ({len(SPECIES_PHASE)} especie/fase x "
          f"bins {bin_indices} de {args.n_bins} x {len(OFFSET_X_VALUES_M)} posiciones), "
          f"n_events={args.n_events}, repeticion={args.repeticion}.")
    print(f"{created} jobs_v2 nuevos creados, {skipped} ya existian (sin tocar).")


if __name__ == "__main__":
    main()
