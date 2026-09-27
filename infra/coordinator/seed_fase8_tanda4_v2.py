#!/usr/bin/env python3
"""Siembra en jobs_v2 la tanda 4 de Fase 8 produccion (ver
docs/bitacora/plan_estadistico.md) -- SEP_p/max, n_bins=128 UNICAMENTE
(no repite 8/16/32/64, que ya estan completos), offset_x_m=0.0,
n_events=10000, repeticion=0. 128 combinaciones nuevas.

Motivo (2026-09-26, con la tanda 3 ya completa y consolidada en
resultados_organo_sweep_fase8_binning.csv): epsilon_binning de SEP_p
mejoro mas rapido de lo extrapolado -- 36.2% (8->16), 18.5% (16->32),
4.22% (32->64), ya cerca del presupuesto de 2.5pp. Esta tanda confirma
si una vuelta mas de refinamiento uniforme ya alcanza (evitaria tener que
disenar un binning no uniforme concentrado en 65-300 MeV, que era la
alternativa mas eficiente pero con mas trabajo de ingenieria).

No pisa nada ya sembrado (ON CONFLICT DO NOTHING via insert_job_v2()) y
NO TOCA jobs/results v1 ni las combinaciones de GCR_H/GCR_He/SEP_p en
n_bins=8/16/32/64 ya sembradas.

Uso:
    python3 seed_fase8_tanda4_v2.py --dry-run   # solo cuenta, no escribe
    python3 seed_fase8_tanda4_v2.py             # siembra de verdad
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
SPECIES = "SEP_p"
PHASE = "max"
N_BINS = 128


def job_priority(bin_index: int, n_bins: int) -> int:
    """Mismo criterio que seed_full_sweep_v2.py/tandas anteriores para
    SEP_p: caro en bin_index bajo (invertido) -> prioridad = n_bins-1-bin_index."""
    return n_bins - 1 - bin_index


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime que haria, no escribe nada.")
    args = parser.parse_args()

    print(f"Tanda 4 Fase 8: {SPECIES}/{PHASE}, n_bins={N_BINS} -> {N_BINS} combinaciones nuevas, "
          f"todas 'pending' (sin trabajo previo que retro-registrar).")

    if args.dry_run:
        for bin_index in range(N_BINS):
            print(f"  {SPECIES}/{PHASE} n_bins={N_BINS} bin={bin_index} "
                  f"priority={job_priority(bin_index, N_BINS)} (dry-run, no escrito)")
        return

    db.init_db()
    db_v2.init_db_v2()

    creados, ya_existian = 0, 0
    for bin_index in range(N_BINS):
        job_id = db_v2.insert_job_v2(
            species=SPECIES, phase=PHASE, bin_index=bin_index, n_bins=N_BINS,
            offset_x_m=OFFSET_X_M, repeticion=REPETICION, n_events=N_EVENTS,
            priority=job_priority(bin_index, N_BINS),
        )
        if job_id:
            creados += 1
        else:
            ya_existian += 1

    print(f"{creados} jobs_v2 nuevos creados, {ya_existian} ya existian (sin tocar).")
    print(f"DB: {db.DB_PATH}")


if __name__ == "__main__":
    main()
