"""Esquema y acceso a la base SQLite del coordinator.

Una sola base de datos (`data/coordinator.db`, gitignored) con 3 tablas:
workers, jobs, results. Ver AGENTS.md (seccion "Computo distribuido") para
el porque de este diseno -- en particular, por que el job es una sola
combinacion (species, bin_index, offset_x_m, repeticion) y no una posicion
completa del barrido.

WAL + `BEGIN IMMEDIATE` en claim_next_job() para que dos workers polleando
al mismo tiempo nunca reciban el mismo job -- sqlite3 serializa esa
transaccion, la segunda espera a que la primera libere el lock.
"""
import sqlite3
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("COORDINATOR_DB", Path(__file__).resolve().parent / "data" / "coordinator.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS workers (
    worker_id       TEXT PRIMARY KEY,
    hostname        TEXT,
    cpu_count       INTEGER,
    ram_gb          REAL,
    ram_free_gb     REAL,
    cpu_load_pct    REAL,
    label           TEXT,
    registered_at   TEXT NOT NULL,
    last_heartbeat  TEXT,
    status          TEXT NOT NULL DEFAULT 'online'
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    species         TEXT NOT NULL,
    bin_index       INTEGER NOT NULL,
    offset_x_m      REAL NOT NULL,
    repeticion      INTEGER NOT NULL DEFAULT 0,
    n_events        INTEGER NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 0,
    min_ram_gb      REAL NOT NULL DEFAULT 0,
    min_cpu_count   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    claimed_by      TEXT REFERENCES workers(worker_id),
    claimed_at      TEXT,
    attempt         INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(species, bin_index, offset_x_m, repeticion)
);

CREATE TABLE IF NOT EXISTS results (
    result_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id               INTEGER NOT NULL REFERENCES jobs(job_id),
    worker_id            TEXT NOT NULL REFERENCES workers(worker_id),
    duration_s           REAL,
    exit_code            INTEGER,
    n_rows               INTEGER,
    results_csv_path     TEXT NOT NULL,
    manifest_csv_path    TEXT NOT NULL,
    submitted_at          TEXT NOT NULL
);
"""

# Job en 'claimed'/'running' sin heartbeat de su worker en esta ventana se
# reencola -- generoso a proposito: una corrida legitima de bin6/7 tarda
# horas (ver AGENTS.md), un umbral corto duplicaria computo caro por un
# falso timeout en vez de solo esperar de mas.
STALE_JOB_TIMEOUT_S = float(os.environ.get("STALE_JOB_TIMEOUT_S", 6 * 3600))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    (DB_PATH.parent / "results").mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_worker(worker_id: str, hostname: str, cpu_count: int, ram_gb: float, label: str,
                   ram_free_gb: float = None, cpu_load_pct: float = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO workers (worker_id, hostname, cpu_count, ram_gb, ram_free_gb, cpu_load_pct,
                                  label, registered_at, last_heartbeat, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'online')
            ON CONFLICT(worker_id) DO UPDATE SET
                hostname=excluded.hostname, cpu_count=excluded.cpu_count, ram_gb=excluded.ram_gb,
                ram_free_gb=excluded.ram_free_gb, cpu_load_pct=excluded.cpu_load_pct,
                label=excluded.label, last_heartbeat=excluded.last_heartbeat, status='online'
            """,
            (worker_id, hostname, cpu_count, ram_gb, ram_free_gb, cpu_load_pct, label, now_iso(), now_iso()),
        )


def touch_heartbeat(worker_id: str, ram_free_gb: float = None, cpu_load_pct: float = None) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE workers SET last_heartbeat=?, status='online',
                   ram_free_gb=COALESCE(?, ram_free_gb), cpu_load_pct=COALESCE(?, cpu_load_pct)
            WHERE worker_id=?
            """,
            (now_iso(), ram_free_gb, cpu_load_pct, worker_id),
        )
        return cur.rowcount > 0


def claim_next_job(worker_id: str) -> sqlite3.Row | None:
    """Reclama atomicamente el job pendiente de mayor prioridad que el worker
    pueda satisfacer (cpu_count total y ram_free_gb EN VIVO, no ram_gb total --
    un worker con poca RAM libre en este momento no debe recibir un job caro
    aunque su RAM instalada alcance en teoria). None si no hay ninguno elegible
    o el worker no esta registrado."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        worker = conn.execute("SELECT * FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
        if worker is None:
            return None
        # ram_free_gb puede ser NULL si el worker nunca mando telemetria (ej.
        # version vieja) -- en ese caso caer a ram_gb total, no bloquear jobs.
        available_ram = worker["ram_free_gb"] if worker["ram_free_gb"] is not None else worker["ram_gb"]
        row = conn.execute(
            """
            SELECT job_id FROM jobs
            WHERE status='pending' AND min_cpu_count <= ? AND min_ram_gb <= ?
            ORDER BY priority DESC, job_id ASC LIMIT 1
            """,
            (worker["cpu_count"] or 0, available_ram or 0),
        ).fetchone()
        if row is None:
            return None
        job_id = row["job_id"]
        conn.execute(
            """
            UPDATE jobs SET status='claimed', claimed_by=?, claimed_at=?, attempt=attempt+1, updated_at=?
            WHERE job_id=? AND status='pending'
            """,
            (worker_id, now_iso(), now_iso(), job_id),
        )
        touch_heartbeat_in_conn(conn, worker_id)
        return conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()


def touch_heartbeat_in_conn(conn, worker_id: str) -> None:
    conn.execute(
        "UPDATE workers SET last_heartbeat=?, status='online' WHERE worker_id=?",
        (now_iso(), worker_id),
    )


def force_claim_job(job_id: int, worker_id: str) -> bool:
    """Asigna un job_id ESPECIFICO a un worker, saltandose la seleccion por
    prioridad de claim_next_job(). Solo para uso administrativo (ver
    import_local_results.py) -- registrar trabajo ya hecho localmente,
    donde se conoce exactamente que job corresponde, no "el siguiente
    pendiente". Solo funciona si el job sigue 'pending'; no le quita un
    job a un worker real que ya lo tenga en 'claimed'/'running'."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='claimed', claimed_by=?, claimed_at=?, attempt=attempt+1, updated_at=? "
            "WHERE job_id=? AND status='pending'",
            (worker_id, now_iso(), now_iso(), job_id),
        )
        return cur.rowcount > 0


def mark_running(job_id: int, worker_id: str | None = None) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='running', updated_at=? WHERE job_id=? AND status='claimed' "
            "AND (? IS NULL OR claimed_by=?)",
            (now_iso(), job_id, worker_id, worker_id),
        )
        return cur.rowcount > 0


def get_job(job_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()


def get_job_by_combo(species: str, bin_index: int, offset_x_m: float, repeticion: int) -> sqlite3.Row | None:
    """Busca un job por su clave natural (mismo UNIQUE que insert_job()) en
    vez de por job_id -- util para scripts administrativos (ej.
    import_local_results.py) que solo conocen la combinacion, no el id
    interno asignado al sembrarla."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE species=? AND bin_index=? AND ABS(offset_x_m - ?) < 1e-6 AND repeticion=?",
            (species, bin_index, offset_x_m, repeticion),
        ).fetchone()


def record_result(job_id: int, worker_id: str, duration_s: float, exit_code: int, n_rows: int,
                   results_csv_path: str, manifest_csv_path: str) -> str:
    """Inserta el resultado y marca el job. Devuelve el status final ('done'|'pending'|'failed').

    Solo acepta el resultado si el job sigue asignado a este worker (evita que
    un worker "zombi" reencolado por timeout sobreescriba lo que ya reporto el
    worker que realmente lo retomo).
    """
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError(f"job {job_id} no existe")
        if job["claimed_by"] != worker_id or job["status"] not in ("claimed", "running"):
            raise PermissionError(
                f"job {job_id} no esta asignado a {worker_id} en un estado aceptable "
                f"(status={job['status']!r}, claimed_by={job['claimed_by']!r})"
            )
        conn.execute(
            """
            INSERT INTO results (job_id, worker_id, duration_s, exit_code, n_rows,
                                  results_csv_path, manifest_csv_path, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, worker_id, duration_s, exit_code, n_rows, results_csv_path, manifest_csv_path, now_iso()),
        )
        if exit_code == 0 and n_rows > 0:
            new_status = "done"
        else:
            new_status = "pending" if job["attempt"] < job["max_attempts"] else "failed"
        conn.execute(
            "UPDATE jobs SET status=?, last_error=?, updated_at=? WHERE job_id=?",
            (new_status, None if new_status == "done" else f"exit_code={exit_code} n_rows={n_rows}", now_iso(), job_id),
        )
        return new_status


def record_failure(job_id: int, worker_id: str, error: str, duration_s: float | None) -> str:
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError(f"job {job_id} no existe")
        if job["claimed_by"] != worker_id or job["status"] not in ("claimed", "running"):
            raise PermissionError(f"job {job_id} no esta asignado a {worker_id} en un estado aceptable")
        new_status = "pending" if job["attempt"] < job["max_attempts"] else "failed"
        conn.execute(
            "UPDATE jobs SET status=?, last_error=?, updated_at=? WHERE job_id=?",
            (new_status, error, now_iso(), job_id),
        )
        return new_status


def requeue_stale_jobs() -> list[int]:
    """Reencola jobs claimed/running cuyo worker no dio heartbeat reciente. Devuelve los job_id afectados."""
    cutoff = time.time() - STALE_JOB_TIMEOUT_S
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT j.job_id FROM jobs j
            LEFT JOIN workers w ON w.worker_id = j.claimed_by
            WHERE j.status IN ('claimed', 'running')
              AND (w.last_heartbeat IS NULL OR w.last_heartbeat < ?)
            """,
            (datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),),
        ).fetchall()
        job_ids = [r["job_id"] for r in rows]
        for job_id in job_ids:
            conn.execute(
                """
                UPDATE jobs SET status=CASE WHEN attempt < max_attempts THEN 'pending' ELSE 'failed' END, claimed_by=NULL, claimed_at=NULL,
                       last_error='requeued: heartbeat vencido', updated_at=?
                WHERE job_id=?
                """,
                (now_iso(), job_id),
            )
        return job_ids


def list_jobs(status: str | None = None) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if status:
            return conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY job_id", (status,)).fetchall()
        return conn.execute("SELECT * FROM jobs ORDER BY job_id").fetchall()


def counts_by_status() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}


def count_workers_online(within_s: int = 300) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - within_s
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM workers WHERE last_heartbeat >= ?",
            (datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),),
        ).fetchone()
        return rows["n"]


def list_workers() -> list[sqlite3.Row]:
    """Telemetria de todos los workers alguna vez registrados (incluye
    offline) -- lo unico que el coordinator sabe de cada maquina: lo que
    el propio worker le reporto en register()/heartbeat(). Sin acceso
    remoto al host mas alla de eso (ver AGENTS.md)."""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM workers ORDER BY worker_id").fetchall()


def insert_job(species: str, bin_index: int, offset_x_m: float, repeticion: int,
               n_events: int, priority: int = 0, min_ram_gb: float = 0, min_cpu_count: int = 0) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (species, bin_index, offset_x_m, repeticion, n_events, priority,
                               min_ram_gb, min_cpu_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(species, bin_index, offset_x_m, repeticion) DO NOTHING
            """,
            (species, bin_index, offset_x_m, repeticion, n_events, priority, min_ram_gb, min_cpu_count,
             now_iso(), now_iso()),
        )
        return cur.lastrowid
