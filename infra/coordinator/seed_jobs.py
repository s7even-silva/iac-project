#!/usr/bin/env python3
"""Puebla la cola de jobs del coordinator. Escribe directo a la SQLite
(no expuesto por HTTP a proposito -- ver AGENTS.md, riesgo de superficie
de ataque si poblar la cola fuera un endpoint publico).

Uso:
    # Job(es) explicitos, ej. las 3 corridas urgentes de GCR_He bin7:
    python3 seed_jobs.py --species GCR_He --bin-index 7 --offset-x-m 2,3,4 --n-events 10000

    # Un job barato de prueba (valor por defecto de n-events bajo a proposito
    # para el primer corte end-to-end, ver AGENTS.md):
    python3 seed_jobs.py --species SEP_p --bin-index 0 --offset-x-m 0.0 --n-events 100
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

VALID_SPECIES = {"GCR_H", "GCR_He", "SEP_p"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--species", required=True, choices=sorted(VALID_SPECIES))
    parser.add_argument("--bin-index", type=int, required=True, help="0..7")
    parser.add_argument("--offset-x-m", type=str, required=True,
                         help="Lista separada por comas, ej. '2,3,4' (uno de 0.0,1.0,2.0,3.0,4.0)")
    parser.add_argument("--n-events", type=int, required=True)
    parser.add_argument("--repeticion", type=int, default=0)
    parser.add_argument("--priority", type=int, default=0,
                         help="Mayor = se sirve antes. Usar valor alto para jobs urgentes (ej. bin7 diferido).")
    args = parser.parse_args()

    db.init_db()
    offsets = [float(x) for x in args.offset_x_m.split(",")]
    created = []
    for offset_x_m in offsets:
        job_id = db.insert_job(
            species=args.species, bin_index=args.bin_index, offset_x_m=offset_x_m,
            repeticion=args.repeticion, n_events=args.n_events, priority=args.priority,
        )
        created.append((job_id, offset_x_m))

    for job_id, offset_x_m in created:
        if job_id:
            print(f"job {job_id}: {args.species} bin{args.bin_index} offset_x_m={offset_x_m} n_events={args.n_events}")
        else:
            print(f"(ya existia) {args.species} bin{args.bin_index} offset_x_m={offset_x_m} -- omitido (UNIQUE constraint)")


if __name__ == "__main__":
    main()
