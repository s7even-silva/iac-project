#!/usr/bin/env python3
"""Siembra en jobs_v2 la tanda 2 de Fase 8 produccion (ver
docs/bitacora/plan_estadistico.md) -- GCR_He/min, n_bins in {8,16,32},
offset_x_m=0.0, n_events=10000, repeticion=0. Completa la comparacion de
discretizacion de bins para las 3 especies de produccion (tanda 1 ya
cubrio SEP_p/max + GCR_H/min, ver seed_fase8_tanda1_v2.py).

GCR_He/min estaba deliberadamente excluido de la tanda 1 -- es el combo
mas caro del proyecto (bin 6/7, horas por corrida) y quedo "bloqueado
hasta confirmacion explicita" (ver seed_fase8_tanda1_v2.py, AGENTS.md,
plan_estadistico.md). Autorizado por el equipo el 2026-09-26, aprovechando
4 workers de cpu_score alto (43-50, vs. la referencia de 4.461) conectados
en ese momento.

A diferencia de la tanda 1, aqui NO hay trabajo previo que retro-registrar
-- las 56 combinaciones (3 valores de n_bins x sus bins) nacen 'pending'
para que el coordinator las reparta a los workers voluntarios via jobs_v2.

Por que no usar seed_full_sweep_v2.py: ese script siembra los 3 combos x
TODAS las posiciones del eje (OFFSET_X_VALUES_M) -- Fase 8 es un piloto
de convergencia de binning con offset fijo en 0.0, sembrar con ese script
habria creado 5x el trabajo real (incluyendo offsets que Fase 8 no usa).

No pisa nada ya sembrado (ON CONFLICT DO NOTHING via insert_job_v2()) y
NO TOCA jobs/results v1 en absoluto.

Uso:
    python3 seed_fase8_tanda2_v2.py --dry-run   # solo cuenta, no escribe
    python3 seed_fase8_tanda2_v2.py             # siembra de verdad
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import db_v2  # noqa: E402

N_EVENTS = 10000
OFFSET_X_M = 0.0
REPETICION = 0
SPECIES = "GCR_He"
PHASE = "min"
N_BINS_GRID = [8, 16, 32]


def job_priority(bin_index: int) -> int:
    """Mismo criterio que seed_full_sweep_v2.py/seed_fase8_tanda1_v2.py
    para GCR_H/GCR_He: caro en bin_index alto -> prioridad = bin_index."""
    return bin_index


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime que haria, no escribe nada.")
    args = parser.parse_args()

    combos = [(n_bins, bin_index) for n_bins in N_BINS_GRID for bin_index in range(n_bins)]
    print(f"Tanda 2 Fase 8: {SPECIES}/{PHASE}, n_bins {N_BINS_GRID} -> {len(combos)} combinaciones, "
          f"todas 'pending' (sin trabajo previo que retro-registrar).")

    if args.dry_run:
        for n_bins, bin_index in combos:
            print(f"  {SPECIES}/{PHASE} n_bins={n_bins} bin={bin_index} "
                  f"priority={job_priority(bin_index)} (dry-run, no escrito)")
        return

    db.init_db()
    db_v2.init_db_v2()

    creados, ya_existian = 0, 0
    for n_bins, bin_index in combos:
        job_id = db_v2.insert_job_v2(
            species=SPECIES, phase=PHASE, bin_index=bin_index, n_bins=n_bins,
            offset_x_m=OFFSET_X_M, repeticion=REPETICION, n_events=N_EVENTS,
            priority=job_priority(bin_index),
        )
        if job_id:
            creados += 1
        else:
            ya_existian += 1

    print(f"{creados} jobs_v2 nuevos creados, {ya_existian} ya existian (sin tocar).")
    print(f"DB: {db.DB_PATH}")


if __name__ == "__main__":
    main()
