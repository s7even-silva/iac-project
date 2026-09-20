"""Esquema y acceso a jobs_v2/results_v2 -- SEGUNDA generacion de jobs del
coordinator, en la MISMA base de datos que db.py (mismo archivo DB_PATH,
misma instancia del coordinator), agregada 2026-09-20 sin tocar jobs/
results (600 filas reales de produccion, 72 tests existentes en
test_coordinator.py) para poder:

  1. Parametrizar n_bins por job (jobs.bin_index de v1 SIEMPRE asume la
     grilla de 8 bins hardcodeada en energy_bins.py/run_organ_sweep.py --
     no hay forma de pedir una grilla distinta). Necesario para cuando el
     equipo decida los parametros finales de produccion (ej. 16 bins).
  2. Subir los estadisticos intra-run S1/S2/N/SE_run que el scorer ya
     calcula (ver ICRP110UserScoreWriter.cc) -- viajan por fila en el CSV
     de resultados (resultados_organo_sweep.csv, ver run_organ_sweep.py),
     asi que results_v2 NO cambia de forma respecto a results (sigue
     siendo solo metadatos de la entrega: duration_s/exit_code/paths a
     CSV), la diferencia vive en el contenido de esos CSV, no en el
     esquema SQL.

DISEnO DELIBERADAMENTE MAS SIMPLE que db.py para las partes de estado de
jobs (ver claim_next_job_v2() abajo): v1 tiene emparejamiento fino por
cpu_score, workers "elite" que saltan el orden de repeticion, etc. --
afinamiento que solo se justifico con 600 jobs reales en produccion. v2
arranca sin nada de eso (orden simple priority DESC, job_id ASC) -- si
algun dia jobs_v2 alcanza un volumen similar, portar ese refinamiento
aqui, no antes.

MODULO SEPARADO A PROPOSITO (decision de equipo 2026-09-20, no
parametrizar db.py por nombre de tabla): aisla completamente el codigo
que sirve los 600 jobs reales de produccion de este trabajo nuevo -- cero
riesgo de que un cambio aqui rompa ese camino. Se acepta duplicar la
LOGICA DE ESTADO real (claim/record_result/requeue) a cambio de ese
aislamiento; lo que NO depende del esquema de jobs (workers/config, y
utilidades puras como now_iso()) se REUSA de db.py sin copiar, ver los
imports abajo.

Cancelacion remota y log-bajo-demanda (request_job_cancel/request_job_log
en db.py) quedan FUERA DE ALCANCE de este primer corte -- son features de
operacion de una flota real en produccion, no bloqueantes para correr
pilotos o producir con parametros definitivos localmente. Agregar cuando
jobs_v2 los necesite de verdad.
"""
import sqlite3
from contextlib import contextmanager

import db  # noqa: E402 -- reuso deliberado, ver docstring. Importa el MODULO,
# no "from db import DB_PATH": DB_PATH se lee en vivo via db.DB_PATH en
# get_conn()/init_db_v2() de este archivo -- "from db import DB_PATH"
# copiaria el valor de Path en el momento del import y quedaria
# desincronizado si algo (tipicamente un test) reasigna db.DB_PATH
# despues (bug real encontrado probando seed_full_sweep_v2.py contra una
# DB temporal). STALE_JOB_TIMEOUT_S/now_iso() si se importan directo --
# no son mutables en caliente de la misma forma.
from db import STALE_JOB_TIMEOUT_S, now_iso

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS jobs_v2 (
    job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    species         TEXT NOT NULL,
    phase           TEXT NOT NULL,
    bin_index       INTEGER NOT NULL,
    n_bins          INTEGER NOT NULL,
    offset_x_m      REAL NOT NULL,
    repeticion      INTEGER NOT NULL DEFAULT 0,
    n_events        INTEGER NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 0,
    min_ram_gb      REAL NOT NULL DEFAULT 0,
    min_cpu_count   INTEGER NOT NULL DEFAULT 0,
    min_cpu_score   REAL NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    claimed_by      TEXT REFERENCES workers(worker_id),
    claimed_at      TEXT,
    attempt         INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    connected_s     REAL NOT NULL DEFAULT 0,
    UNIQUE(species, phase, bin_index, n_bins, offset_x_m, repeticion)
);

-- n_bins en el UNIQUE (a diferencia de jobs.UNIQUE, que no lo tiene): sin
-- esto, bin_index=3 de una grilla de 8 y bin_index=3 de una grilla de 16
-- colisionarian como "el mismo job" -- mismo tipo de bug que ya se
-- corrigio una vez al agregar `phase` al UNIQUE de jobs (ver db.py,
-- _migrate_jobs_add_phase()). jobs_v2 nace limpio, sin necesitar esa
-- migracion retroactiva.

CREATE TABLE IF NOT EXISTS results_v2 (
    result_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id               INTEGER NOT NULL REFERENCES jobs_v2(job_id),
    worker_id            TEXT NOT NULL REFERENCES workers(worker_id),
    duration_s           REAL,
    exit_code            INTEGER,
    n_rows               INTEGER,
    results_csv_path     TEXT NOT NULL,
    manifest_csv_path    TEXT NOT NULL,
    submitted_at          TEXT NOT NULL
);
"""


def init_db_v2() -> None:
    """Sin migracion (a diferencia de db.init_db(), que migra jobs desde
    un esquema anterior sin `phase`) -- jobs_v2 es una tabla nueva, sin
    filas legadas que backfillear."""
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_V2)


@contextmanager
def get_conn():
    # Mismo archivo DB_PATH que db.py (mismo coordinator.db) -- WAL ya
    # activado por db.init_db() para el mismo archivo, pero se repite
    # aqui por si get_conn() de este modulo se usa antes de que
    # db.init_db() haya corrido en el proceso actual (ej. tests aislados
    # de db_v2.py).
    conn = sqlite3.connect(db.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_job_v2(species: str, phase: str, bin_index: int, n_bins: int, offset_x_m: float,
                   repeticion: int, n_events: int, priority: int = 0, min_ram_gb: float = 0,
                   min_cpu_count: int = 0, min_cpu_score: float = 0) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs_v2 (species, phase, bin_index, n_bins, offset_x_m, repeticion, n_events,
                                  priority, min_ram_gb, min_cpu_count, min_cpu_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(species, phase, bin_index, n_bins, offset_x_m, repeticion) DO NOTHING
            """,
            (species, phase, bin_index, n_bins, offset_x_m, repeticion, n_events, priority,
             min_ram_gb, min_cpu_count, min_cpu_score, now_iso(), now_iso()),
        )
        return cur.lastrowid


def claim_next_job_v2(worker_id: str) -> sqlite3.Row | None:
    """Version SIMPLIFICADA de claim_next_job() (ver docstring del modulo)
    -- orden priority DESC, job_id ASC entre los candidatos que el worker
    puede satisfacer por recursos (mismos criterios min_ram_gb/
    min_cpu_count/min_cpu_score que v1). Sin emparejamiento por cpu_score
    ni repeticiones-en-serie estrictas -- si jobs_v2 crece a un volumen
    que lo justifique, portar ese refinamiento de db.py aqui, no antes."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        worker = conn.execute("SELECT * FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
        if worker is None:
            return None
        available_ram = worker["ram_free_gb"] if worker["ram_free_gb"] is not None else worker["ram_gb"]
        # float("inf") -- mismo criterio que claim_next_job() en db.py:
        # un worker sin cpu_score real (version vieja del worker, o el
        # benchmark de arranque fallo) NUNCA debe bloquearse por
        # min_cpu_score -- 0.0 aqui era un bug real (encontrado en
        # revision, 2026-09-20): invertia ese criterio, bloqueando
        # exactamente al worker que menos informacion tiene sobre si
        # mismo de cualquier job que pidiera min_cpu_score > 0.
        worker_cpu_score = worker["cpu_score"] if worker["cpu_score"] is not None else float("inf")

        candidate = conn.execute(
            """
            SELECT job_id FROM jobs_v2
            WHERE status='pending' AND min_cpu_count <= ? AND min_ram_gb <= ? AND min_cpu_score <= ?
            ORDER BY priority DESC, job_id ASC LIMIT 1
            """,
            (worker["cpu_count"] or 0, available_ram or 0, worker_cpu_score),
        ).fetchone()
        if candidate is None:
            return None
        job_id = candidate["job_id"]
        conn.execute(
            "UPDATE jobs_v2 SET status='claimed', claimed_by=?, claimed_at=?, attempt=attempt+1, updated_at=? "
            "WHERE job_id=? AND status='pending'",
            (worker_id, now_iso(), now_iso(), job_id),
        )
        conn.execute(
            "UPDATE workers SET last_heartbeat=?, status='online' WHERE worker_id=?",
            (now_iso(), worker_id),
        )
        return conn.execute("SELECT * FROM jobs_v2 WHERE job_id=?", (job_id,)).fetchone()


def mark_running_v2(job_id: int, worker_id: str | None = None) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs_v2 SET status='running', updated_at=? WHERE job_id=? AND status='claimed' "
            "AND (? IS NULL OR claimed_by=?)",
            (now_iso(), job_id, worker_id, worker_id),
        )
        return cur.rowcount > 0


def get_job_v2(job_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM jobs_v2 WHERE job_id=?", (job_id,)).fetchone()


def record_result_v2(job_id: int, worker_id: str, duration_s: float, exit_code: int, n_rows: int,
                      results_csv_path: str, manifest_csv_path: str) -> str:
    """Mismo contrato que db.record_result(): solo acepta el resultado si
    el job sigue asignado a este worker (evita que un worker zombi
    reencolado por timeout pise lo que ya reporto el worker que lo
    retomo). Devuelve el status final ('done'|'pending'|'failed')."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM jobs_v2 WHERE job_id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError(f"job_v2 {job_id} no existe")
        if job["claimed_by"] != worker_id or job["status"] not in ("claimed", "running"):
            raise PermissionError(
                f"job_v2 {job_id} no esta asignado a {worker_id} en un estado aceptable "
                f"(status={job['status']!r}, claimed_by={job['claimed_by']!r})"
            )
        conn.execute(
            """
            INSERT INTO results_v2 (job_id, worker_id, duration_s, exit_code, n_rows,
                                     results_csv_path, manifest_csv_path, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, worker_id, duration_s, exit_code, n_rows, results_csv_path, manifest_csv_path, now_iso()),
        )
        new_status = "done" if (exit_code == 0 and n_rows > 0) else (
            "pending" if job["attempt"] < job["max_attempts"] else "failed")
        conn.execute(
            "UPDATE jobs_v2 SET status=?, last_error=?, updated_at=?, "
            "connected_s=CASE WHEN ?='pending' THEN 0 ELSE connected_s END WHERE job_id=?",
            (new_status, None if new_status == "done" else f"exit_code={exit_code} n_rows={n_rows}",
             now_iso(), new_status, job_id),
        )
        return new_status


def record_failure_v2(job_id: int, worker_id: str, error: str) -> str:
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM jobs_v2 WHERE job_id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError(f"job_v2 {job_id} no existe")
        if job["claimed_by"] != worker_id or job["status"] not in ("claimed", "running"):
            raise PermissionError(f"job_v2 {job_id} no esta asignado a {worker_id} en un estado aceptable")
        new_status = "pending" if job["attempt"] < job["max_attempts"] else "failed"
        conn.execute(
            "UPDATE jobs_v2 SET status=?, last_error=?, updated_at=?, "
            "connected_s=CASE WHEN ?='pending' THEN 0 ELSE connected_s END WHERE job_id=?",
            (new_status, error, now_iso(), new_status, job_id),
        )
        return new_status


def requeue_stale_jobs_v2() -> list[int]:
    """Version simple: solo el timeout fijo (db.STALE_JOB_TIMEOUT_S,
    reusado de db.py) -- sin la estimacion dinamica por cpu_score/
    REFERENCE_TIMINGS_S que db.requeue_stale_jobs() usa (esa tabla es
    especifica de la grilla de 8 bins de produccion v1, no valida sin mas
    para una grilla de n_bins arbitrario)."""
    from datetime import datetime, timezone
    cutoff_iso = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - db.STALE_JOB_TIMEOUT_S, tz=timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT j.job_id FROM jobs_v2 j LEFT JOIN workers w ON w.worker_id=j.claimed_by "
            "WHERE j.status IN ('claimed','running') AND j.updated_at < ? "
            "AND (w.last_heartbeat IS NULL OR w.last_heartbeat < ?)",
            (cutoff_iso, cutoff_iso),
        ).fetchall()
        ids = [r["job_id"] for r in rows]
        conn.executemany(
            "UPDATE jobs_v2 SET status=CASE WHEN attempt < max_attempts THEN 'pending' ELSE 'failed' END, "
            "claimed_by=NULL, claimed_at=NULL, connected_s=0, last_error='heartbeat expired', "
            "updated_at=? WHERE job_id=?", [(now_iso(), i) for i in ids],
        )
        return ids


def list_jobs_v2(status: str | None = None) -> list[sqlite3.Row]:
    query = "SELECT * FROM jobs_v2"
    with get_conn() as conn:
        if status:
            return conn.execute(query + " WHERE status=? ORDER BY job_id", (status,)).fetchall()
        return conn.execute(query + " ORDER BY job_id").fetchall()


def counts_by_status_v2() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs_v2 GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
