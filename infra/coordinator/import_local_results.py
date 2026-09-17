#!/usr/bin/env python3
"""Marca como 'done' en la cola del coordinator los jobs que ya se
corrieron LOCALMENTE (fuera del sistema de workers), a partir de un CSV
de resultados por organo + su manifiesto -- mismo formato que produce
run_organ_sweep.py y que ya sube worker.py (resultados_organo_sweep.csv/
organ_sweep_manifest.csv), no un formato nuevo.

Por que hace falta: bin0-5 (offsets 0,1) de la repeticion 0 los corrio
Joel en su maquina, y offsets 2,3,4 los corrio Bryam en la suya (ver
resultados/organ_sweep_manifest_bryam.csv) -- ninguno de los dos paso
por el coordinator. Para que replicate_repeats.py pueda clonar una
plantilla COMPLETA de 120 combinaciones hacia las repeticiones 1-4 (el
plan acordado: las 4 repeticiones adicionales SI van completas a la cola
distribuida, no solo bin6/7), la repeticion 0 en la base de datos del
coordinator necesita las 120 filas, no solo las de bin6/7 -- este script
llena esos huecos con el trabajo YA HECHO, sin que nadie lo vuelva a
correr, en vez de sembrar bin0-5 como 'pending' y duplicar computo real.

Reusa el mismo db.record_result() que llama submit_result() en app.py --
misma validacion (las filas deben coincidir con el job: especie, bin,
offset, repeticion, n_events), mismos archivos guardados en
results/job_{id}/{uuid}/, mismo efecto sobre el status del job. La unica
diferencia es que aqui el "worker" es una persona identificada
explicitamente (--worker-label), no un proceso Docker real -- se
registra un worker_id determinista local-<label> si no existe.

Uso:
    # 1) Sembrar primero las 120 combinaciones completas de repeticion 0
    #    (bin6/7 puede que ya estuvieran; bin0-5 quedan 'pending' hasta
    #    que este script las marque 'done' con el trabajo real):
    python3 seed_full_sweep.py --n-events 10000

    # 2) Importar el trabajo de Bryam (offsets 2,3,4, ya versionado):
    python3 import_local_results.py --worker-label bryam \
        --results-csv ../../geant4/ActiveShield_Sim/resultados/resultados_organo_sweep_bryam.csv \
        --manifest-csv ../../geant4/ActiveShield_Sim/resultados/organ_sweep_manifest_bryam.csv

    # 3) Importar el trabajo de Joel (offsets 0,1, cuando suba sus CSV):
    python3 import_local_results.py --worker-label joel \
        --results-csv /ruta/a/resultados_organo_sweep_joel.csv \
        --manifest-csv /ruta/a/organ_sweep_manifest_joel.csv

    # 4) Recien ahora replicar a las 4 repeticiones adicionales:
    python3 replicate_repeats.py --repeats 4
"""
import argparse
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

# Mismo directorio que usa app.py (RESULTS_DIR = db.DB_PATH.parent / "results")
# -- no importado de ahi porque app.py no expone la constante como
# reutilizable fuera de si mismo; se deriva aqui de la misma forma.
RESULTS_DIR = db.DB_PATH.parent / "results"

RESULTS_FIELDNAMES = ["especie", "fase", "bin_index", "energy_mev", "offset_x_m", "repeticion",
                       "organo_id", "edep_J", "dose_gy_run", "n_eventos"]


def combo_key(row: dict) -> tuple:
    # Incluye "fase" (2026-09-16, antes solo especie/bin/offset/repeticion)
    # -- mismo UNIQUE de 5 columnas que ahora tiene jobs (ver db.py). Los
    # CSV reales (resultados_organo_sweep_*.csv) ya traen columna "fase"
    # desde siempre (la escribe run_organ_sweep.py), asi que este cambio
    # no requiere ningun dato nuevo, solo usar el que ya estaba en el CSV.
    return (row["especie"], row["fase"], int(row["bin_index"]), round(float(row["offset_x_m"]), 6), int(row["repeticion"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker-label", required=True,
                         help="Identifica a la persona cuyo trabajo local se importa (ej. 'bryam', 'joel'). "
                              "Se usa para el worker_id determinista local-<label>.")
    parser.add_argument("--results-csv", required=True, type=Path,
                         help="resultados_organo_sweep_<x>.csv (filas por organo, formato de run_organ_sweep.py).")
    parser.add_argument("--manifest-csv", required=True, type=Path,
                         help="organ_sweep_manifest_<x>.csv (una fila por corrida, con exit_code/duration_s).")
    parser.add_argument("--dry-run", action="store_true",
                         help="Solo muestra que se importaria, sin escribir nada en la base de datos.")
    args = parser.parse_args()

    worker_id = f"local-{args.worker_label}"
    if not args.dry_run:
        db.upsert_worker(worker_id, hostname=f"local-{args.worker_label}", cpu_count=0, ram_gb=0.0,
                          label=f"local:{args.worker_label}")

    with open(args.results_csv, newline="") as f:
        all_rows = list(csv.DictReader(f))
    with open(args.manifest_csv, newline="") as f:
        all_manifest_rows = list(csv.DictReader(f))

    rows_by_combo = {}
    for row in all_rows:
        rows_by_combo.setdefault(combo_key(row), []).append(row)

    manifest_by_combo = {}
    for row in all_manifest_rows:
        # Misma clave de 5 elementos que combo_key() (fase incluida,
        # 2026-09-16) -- organ_sweep_manifest.csv ya trae columna "fase"
        # desde siempre (run_organ_sweep.py la escribe), no un dato nuevo.
        key = (row["especie"], row["fase"], int(row["bin_index"]), round(float(row["offset_x_m"]), 6), int(row["repeticion"]))
        manifest_by_combo[key] = row

    imported, already_done, no_match, mismatched = 0, 0, 0, 0
    for key, manifest_row in manifest_by_combo.items():
        if int(manifest_row["exit_code"]) != 0:
            print(f"  omitido {key}: exit_code={manifest_row['exit_code']} en el manifiesto (no fue exitoso)")
            continue

        species, phase, bin_index, offset_x_m, repeticion = key
        job = db.get_job_by_combo(species, phase, bin_index, offset_x_m, repeticion)
        if job is None:
            no_match += 1
            print(f"  sin job en la cola para {key} -- corre seed_full_sweep.py primero, o revisa el offset")
            continue
        if job["status"] == "done":
            already_done += 1
            continue

        organ_rows = rows_by_combo.get(key, [])
        if not organ_rows:
            print(f"  sin filas de organo para {key} en {args.results_csv.name} -- omitido")
            continue

        n_events = int(manifest_row["n_events"])
        if job["n_events"] != n_events:
            mismatched += 1
            print(f"  {key}: n_events del job ({job['n_events']}) no coincide con el manifiesto ({n_events}) "
                  "-- omitido, revisar antes de forzar")
            continue

        if args.dry_run:
            print(f"  [dry-run] importaria job {job['job_id']} {key}: {len(organ_rows)} filas de organo")
            imported += 1
            continue

        results_buf = io.StringIO()
        writer = csv.DictWriter(results_buf, fieldnames=RESULTS_FIELDNAMES)
        writer.writeheader()
        writer.writerows(organ_rows)

        manifest_buf = io.StringIO()
        writer = csv.DictWriter(manifest_buf, fieldnames=list(manifest_row.keys()))
        writer.writeheader()
        writer.writerow(manifest_row)

        # record_result() exige que el job este 'claimed'/'running' y
        # asignado a este worker_id (proteccion normal contra que
        # cualquiera reporte resultados de un job ajeno) -- aqui se
        # fuerza esa asignacion primero, ya que se conoce exactamente que
        # job corresponde (no se esta pidiendo "el siguiente pendiente").
        if not db.force_claim_job(job["job_id"], worker_id):
            print(f"  job {job['job_id']} {key}: no se pudo reclamar (ya no esta 'pending', "
                  "puede que otro worker lo tome en paralelo) -- omitido, revisar")
            continue
        db.mark_running(job["job_id"], worker_id)

        job_dir = RESULTS_DIR / f"job_{job['job_id']}" / f"local-import-{args.worker_label}"
        job_dir.mkdir(parents=True, exist_ok=True)
        results_path = job_dir / "results.csv"
        manifest_path = job_dir / "manifest.csv"
        results_path.write_text(results_buf.getvalue())
        manifest_path.write_text(manifest_buf.getvalue())

        status = db.record_result(
            job["job_id"], worker_id, float(manifest_row.get("duration_s", 0) or 0), 0, len(organ_rows),
            str(results_path), str(manifest_path),
        )
        print(f"  job {job['job_id']} {key}: {len(organ_rows)} filas importadas -> status={status}")
        imported += 1

    print()
    print(f"Importados: {imported}. Ya estaban done: {already_done}. "
          f"Sin job en la cola: {no_match}. n_events no coincide: {mismatched}.")


if __name__ == "__main__":
    main()
