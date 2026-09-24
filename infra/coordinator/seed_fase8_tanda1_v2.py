#!/usr/bin/env python3
"""Siembra en jobs_v2 la tanda 1 de Fase 8 produccion (ver
docs/bitacora/plan_estadistico.md) -- SEP_p/max + GCR_H/min, n_bins in
{8,16,32}, offset_x_m=0.0 (Fase 8 no barre posicion, a diferencia del
barrido de seed_full_sweep_v2.py), n_events=10000, repeticion=0 -- y
marca como 'done' las combinaciones que Bryam ya corrio localmente
(fuera del sistema de jobs, con run_fase8_binning.py standalone en su
propia maquina) segun el manifest real en origin/results/fase8-prod. El
resto queda 'pending' para que el coordinator las reparta a workers
voluntarios va jobs_v2, sin duplicar el computo ya hecho.

Por que no usar seed_full_sweep_v2.py: ese script siembra los 3 combos
fijos de produccion (incluye GCR_He/min, bloqueado hasta que se confirme
explicitamente -- ver AGENTS.md/plan_estadistico.md) x TODAS las
posiciones del eje (OFFSET_X_VALUES_M) -- Fase 8 es un piloto de
convergencia de binning con offset fijo en 0.0, sembrar con ese script
habria creado 5x el trabajo real y adelantado GCR_He/min sin
autorizacion.

Usa el worker_id YA EXISTENTE de la maquina real de Bryam
(ba49a04b-c669-4011-a5b5-a2803825f6af, label "bryam-local",
bryam-VirtualBox, registrado desde 2026-09-13) para dejar trazabilidad
honesta de que esas filas se retro-registran -- no pasaron por el ciclo
normal claim/result de worker.py. NO crea un worker_id sintetico nuevo
(version anterior de este script lo hizo por error -- worker_id literal
"bryam-local", corregido 2026-09-24, ver infra/OPERATIONS_LOG.md: la
maquina real ya tenia una identidad registrada, crear una segunda
duplicaba al mismo worker con dos nombres distintos en el dashboard).
results_csv_path/manifest_csv_path en results_v2 apuntan a la referencia
git real (rama results/fase8-prod), no a un CSV filtrado local, porque
ese archivo no existe (el trabajo no paso por el protocolo HTTP del
worker).

No pisa nada ya sembrado (ON CONFLICT DO NOTHING via insert_job_v2(), ni
retoca el estado de un job_id que ya existiera de una corrida anterior
de este mismo script) y NO TOCA jobs/results v1.

Uso:
    python3 seed_fase8_tanda1_v2.py --dry-run   # solo cuenta, no escribe
    python3 seed_fase8_tanda1_v2.py             # siembra de verdad

Requiere correrse con el working tree en un checkout que tenga acceso a
`git show origin/results/fase8-prod:...` (osea, con ese remoto
fetcheado) para leer el manifest real.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402
import db_v2  # noqa: E402

N_EVENTS = 10000
OFFSET_X_M = 0.0
REPETICION = 0
COMBOS = [("SEP_p", "max"), ("GCR_H", "min")]
N_BINS_GRID = [8, 16, 32]
WORKER_ID = "ba49a04b-c669-4011-a5b5-a2803825f6af"  # worker real "bryam-local" (bryam-VirtualBox)
RESULTS_BRANCH = "results/fase8-prod"
MANIFEST_PATH_IN_BRANCH = "geant4/ActiveShield_Sim/scripts/pilots/results/fase8_binning_prod/manifest.csv"


def job_priority(species: str, bin_index: int, n_bins: int) -> int:
    """Mismo criterio de signo que seed_full_sweep_v2.py: SEP_p caro en
    bin_index bajo (invertido), GCR_H caro en bin_index alto."""
    if species == "SEP_p":
        return n_bins - 1 - bin_index
    return bin_index


def load_done_from_manifest(repo_root: Path) -> set[tuple[str, str, int, int]]:
    """(species, phase, n_bins, bin_index) con exit_code==0 en el
    manifest real de la corrida standalone de Bryam, leido via `git show`
    (sin necesidad de checkout local de la rama)."""
    out = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"origin/{RESULTS_BRANCH}:{MANIFEST_PATH_IN_BRANCH}"],
        capture_output=True, text=True, check=True,
    )
    done = set()
    for row in csv.DictReader(out.stdout.splitlines()):
        if int(row["exit_code"]) == 0:
            done.add((row["species"], row["phase"], int(row["n_bins"]), int(row["bin_index"])))
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime que haria, no escribe nada.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    done_set = load_done_from_manifest(args.repo_root)
    print(f"Corridas ya hechas por Bryam local (manifest de origin/{RESULTS_BRANCH}): {len(done_set)}")

    if not args.dry_run:
        db.init_db()
        db_v2.init_db_v2()
        with db.get_conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM workers WHERE worker_id=?", (WORKER_ID,)
            ).fetchone()
        if not existing:
            print(f"ADVERTENCIA: worker {WORKER_ID} (bryam-local) no existe todavia en "
                  f"esta DB -- registrandolo con datos minimos, pero lo esperado es que ya "
                  f"exista en produccion real (se registro solo cuando su worker.py corrio "
                  f"por primera vez, 2026-09-13).")
            db.upsert_worker(
                worker_id=WORKER_ID, hostname="bryam-VirtualBox", cpu_count=0, ram_gb=0,
                label="bryam-local",
            )

    total = 0
    ya_marcados_done = 0
    pendientes_creados = 0
    ya_existian = 0
    for species, phase in COMBOS:
        for n_bins in N_BINS_GRID:
            for bin_index in range(n_bins):
                total += 1
                is_done = (species, phase, n_bins, bin_index) in done_set
                priority = job_priority(species, bin_index, n_bins)
                if args.dry_run:
                    if is_done:
                        ya_marcados_done += 1
                    else:
                        pendientes_creados += 1
                    continue
                job_id = db_v2.insert_job_v2(
                    species=species, phase=phase, bin_index=bin_index, n_bins=n_bins,
                    offset_x_m=OFFSET_X_M, repeticion=REPETICION, n_events=N_EVENTS, priority=priority,
                )
                if job_id is None:
                    ya_existian += 1
                    continue  # ya existia (ON CONFLICT DO NOTHING) -- no se retoca su estado
                if is_done:
                    ya_marcados_done += 1
                    with db.get_conn() as conn:
                        conn.execute(
                            "UPDATE jobs_v2 SET status='done', claimed_by=?, claimed_at=?, attempt=1, "
                            "updated_at=? WHERE job_id=?",
                            (WORKER_ID, db.now_iso(), db.now_iso(), job_id),
                        )
                        conn.execute(
                            "INSERT INTO results_v2 (job_id, worker_id, duration_s, exit_code, n_rows, "
                            "results_csv_path, manifest_csv_path, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (job_id, WORKER_ID, None, 0, 1,
                             f"git:origin/{RESULTS_BRANCH}:"
                             f"{MANIFEST_PATH_IN_BRANCH.replace('manifest.csv', 'resultados.csv')}",
                             f"git:origin/{RESULTS_BRANCH}:{MANIFEST_PATH_IN_BRANCH}", db.now_iso()),
                        )
                else:
                    pendientes_creados += 1

    print(f"Total combinaciones tanda 1: {total}")
    print(f"Marcadas 'done' (bryam-local, ya corridas): {ya_marcados_done}")
    print(f"Sembradas 'pending' (para workers voluntarios): {pendientes_creados}")
    if ya_existian:
        print(f"Ya existian de una corrida previa de este script, sin tocar: {ya_existian}")
    if not args.dry_run:
        print(f"DB: {db.DB_PATH}")


if __name__ == "__main__":
    main()
