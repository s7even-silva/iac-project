#!/usr/bin/env python3
"""Replica los jobs ya sembrados (repeticion=0) a repeticiones adicionales,
para poder calcular media/std/IC95% entre repeticiones (ver
aggregate_organ_doses.py --repeats en ActiveShield_Sim, y
resultados_riesgo_estocastico_repeticiones.csv). No recalcula nada --
copia species/bin_index/offset_x_m/n_events/priority/min_ram_gb/
min_cpu_count/min_cpu_score de cada job de la repeticion base tal cual,
cambiando solo `repeticion`. Idempotente via el mismo UNIQUE constraint
que ya usa insert_job() -- correrlo dos veces con el mismo --repeats no
duplica nada.

Las semillas NO se guardan aqui ni se copian de la repeticion base --
la tabla `jobs` solo tiene species/bin_index/offset_x_m/repeticion/
n_events, nunca seed1/seed2. `run_organ_sweep.py` calcula la semilla en
el momento de ejecutar, a partir de `repeticion` (BASE_SEED + 1000*rep +
2*indice, ver seed1/seed2 ahi) -- cada repeticion nueva creada por este
script obtiene automaticamente una semilla distinta de la 0 (y de
cualquier otra repeticion), sin que este script tenga que calcular ni
propagar nada. Es lo mismo que ya hacia --repeats en ese script para una
corrida local; este script solo hace lo equivalente contra la cola del
coordinator en vez de un bucle local.

Requiere sembrar la repeticion base PRIMERO -- para el barrido completo
de ActiveShield_Sim (120 combinaciones, no solo los jobs sembrados a
mano hasta ahora), usar seed_full_sweep.py antes de este script.

Uso:
    # 1) Siembra las 120 combinaciones de la repeticion 0 (una sola vez):
    python3 seed_full_sweep.py --n-events 10000

    # 2) Agrega repeticiones 1,2,3,4 para cada combinacion que ya exista con
    # repeticion=0 (lo tipico: ejecutar una vez que la primera pasada esta
    # sembrada, sin esperar a que termine de correr):
    python3 replicate_repeats.py --repeats 4

    # Explicito sobre cuantas repeticiones totales quieres en la cola
    # (1 = solo la que ya existe, sin crear nada nuevo):
    python3 replicate_repeats.py --repeats 4 --base-repeticion 0
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeats", type=int, required=True,
                         help="Repeticiones adicionales a crear (ej. 4 crea repeticion=base+1..base+4).")
    parser.add_argument("--base-repeticion", type=int, default=0,
                         help="Repeticion ya sembrada que se usa como plantilla. Default 0.")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats debe ser >= 1")

    db.init_db()
    base_jobs = [j for j in db.list_jobs() if j["repeticion"] == args.base_repeticion]
    if not base_jobs:
        print(f"No hay ningun job con repeticion={args.base_repeticion} todavia -- siembra la primera pasada "
              "con seed_jobs.py antes de replicar.")
        return

    created, skipped = 0, 0
    for job in base_jobs:
        for rep in range(args.base_repeticion + 1, args.base_repeticion + 1 + args.repeats):
            job_id = db.insert_job(
                species=job["species"], phase=job["phase"], bin_index=job["bin_index"],
                offset_x_m=job["offset_x_m"], repeticion=rep, n_events=job["n_events"],
                priority=job["priority"], min_ram_gb=job["min_ram_gb"],
                min_cpu_count=job["min_cpu_count"], min_cpu_score=job["min_cpu_score"],
            )
            if job_id:
                created += 1
            else:
                skipped += 1  # ya existia (UNIQUE constraint) -- correr dos veces es seguro

    print(f"{len(base_jobs)} combinaciones de repeticion={args.base_repeticion} usadas como plantilla.")
    print(f"{created} jobs nuevos creados, {skipped} ya existian (sin duplicar).")


if __name__ == "__main__":
    main()
