#!/usr/bin/env python3
"""Siembra en jobs_v2 la tanda 3 de Fase 8 produccion (ver
docs/bitacora/plan_estadistico.md) -- SEP_p/max, n_bins=64 UNICAMENTE
(no repite 8/16/32, que ya estan completos), offset_x_m=0.0, n_events=10000,
repeticion=0. 64 combinaciones nuevas.

Motivo (2026-09-26, analisis ad-hoc de epsilon_binning con los datos
reales ya completos de tanda 1/2): SEP_p no converge entre 8/16/32 bins
(epsilon_binning 36.2% y 18.5%, muy por encima del presupuesto 2.5pp),
a diferencia de GCR_H/GCR_He (que si convergen, con el "empeoramiento"
16->32 de GCR_H explicado como ruido MC, no senal real -- ver
docs/bitacora/plan_estadistico.md). Causa fisica identificada: casi toda
la dosis de SEP_p viene de la franja 65-300 MeV (menos de 1 decada de un
espectro de 4 decadas, 0.01-300 MeV) -- el binning logaritmico uniforme
le da muy pocos bins utiles a esa franja (1 de 8, 2 de 16, ~7 de 32).

Esta tanda (n_bins=64, uniforme, log-espaciado en todo el rango) es una
prueba BARATA para confirmar la tendencia de convergencia extrapolada
(razon ~0.51 entre pares sucesivos, sugiere que podria hacer falta hasta
~128-256 bins para bajar de 2.5pp) -- NO resuelve el problema de fondo
(la mayoria de esos 64 bins seguiran aportando ~0%, energias <10 MeV que
no importan para SEP_p). Un binning no uniforme (mas bins concentrados en
65-300 MeV) seria mas eficiente, pero es un cambio de diseno en
energy_bins.py, no solo este --n-bins -- fuera de alcance de esta tanda.

No pisa nada ya sembrado (ON CONFLICT DO NOTHING via insert_job_v2()) y
NO TOCA jobs/results v1 ni las combinaciones de GCR_H/GCR_He/SEP_p en
n_bins=8/16/32 ya sembradas.

Uso:
    python3 seed_fase8_tanda3_v2.py --dry-run   # solo cuenta, no escribe
    python3 seed_fase8_tanda3_v2.py             # siembra de verdad
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
N_BINS = 64


def job_priority(bin_index: int, n_bins: int) -> int:
    """Mismo criterio que seed_full_sweep_v2.py/seed_fase8_tanda1_v2.py
    para SEP_p: caro en bin_index bajo (invertido) -> prioridad = n_bins-1-bin_index."""
    return n_bins - 1 - bin_index


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime que haria, no escribe nada.")
    args = parser.parse_args()

    print(f"Tanda 3 Fase 8: {SPECIES}/{PHASE}, n_bins={N_BINS} -> {N_BINS} combinaciones nuevas, "
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
