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
    cpu_score       REAL,
    image_digest    TEXT,
    label           TEXT,
    registered_at   TEXT NOT NULL,
    last_heartbeat  TEXT,
    status          TEXT NOT NULL DEFAULT 'online'
);

-- Clave/valor generico para config global de despliegue -- pensado para
-- crecer sin agregar una columna nueva a "workers" cada vez que se
-- necesita un valor global (empieza con worker_image_digest, el digest
-- que el equipo quiere que todos los workers Docker corran; ver
-- auto-actualizacion en worker.py y AGENTS.md, "Computo distribuido").
CREATE TABLE IF NOT EXISTS config (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TEXT NOT NULL
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
    min_cpu_score   REAL NOT NULL DEFAULT 0,
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
# falso timeout en vez de solo esperar de mas. Sigue siendo el PISO minimo
# de cualquier job, incluso con la estimacion dinamica de abajo -- ver
# requeue_stale_jobs().
STALE_JOB_TIMEOUT_S = float(os.environ.get("STALE_JOB_TIMEOUT_S", 6 * 3600))

# Tiempo real (segundos, promedio de 3 repeticiones) por (especie, bin_index),
# medido en bryam-local -- misma maquina y mismo WORKER_THREADS que reporta
# cpu_score, asi que estos valores son la base valida para escalar por
# cpu_score de cualquier otro worker (ver estimate_job_duration_s() abajo).
# Derivado de datos reales
# (geant4/ActiveShield_Sim/resultados/organ_sweep_manifest_bryam.csv,
# ofsets 2/3/4, promedio de 3 repeticiones por combinacion), no inventado.
# GCR_He bin7 es la unica excepcion: bryam-local nunca lo corrio (ver
# AGENTS.md, "bin7 de GCR_He se salta por ahora") -- extrapolado aplicando
# el mismo factor de crecimiento bin6->bin7 medido en GCR_H (4669.7/1820.4
# =~2.565x) sobre el bin6 real de GCR_He (7321.2s), dando ~18780s (~5.2h) --
# coherente con la proyeccion de "5-6h por corrida" ya documentada en
# AGENTS.md a partir del mismo patron de crecimiento. Marcado explicitamente
# como extrapolado, no medido, para quien lea esta tabla despues.
REFERENCE_TIMINGS_S = {
    ("GCR_H", 0): 20.9, ("GCR_H", 1): 23.0, ("GCR_H", 2): 32.9, ("GCR_H", 3): 86.7,
    ("GCR_H", 4): 314.7, ("GCR_H", 5): 776.4, ("GCR_H", 6): 1820.4, ("GCR_H", 7): 4669.7,
    ("GCR_He", 0): 21.4, ("GCR_He", 1): 22.7, ("GCR_He", 2): 117.1, ("GCR_He", 3): 438.4,
    ("GCR_He", 4): 1221.5, ("GCR_He", 5): 2694.7, ("GCR_He", 6): 7321.2,
    ("GCR_He", 7): 18780.4,  # extrapolado, ver comentario arriba -- no medido
    ("SEP_p", 0): 832.4, ("SEP_p", 1): 368.5, ("SEP_p", 2): 139.0, ("SEP_p", 3): 51.0,
    ("SEP_p", 4): 27.1, ("SEP_p", 5): 23.2, ("SEP_p", 6): 21.8, ("SEP_p", 7): 36.1,
}

# cpu_score de bryam-local en el momento de medir REFERENCE_TIMINGS_S arriba
# (confirmado via GET /api/v1/workers, 2026-09-14) -- la base de la que se
# escala cualquier otro worker: estimacion = referencia * (este valor /
# cpu_score_del_worker).
REFERENCE_CPU_SCORE = 4.461

# Cuanto margen extra sobre la estimacion antes de considerar un job
# realmente perdido -- deliberadamente generoso (no 1.0x): cpu_score es un
# benchmark corrido una sola vez al arrancar el worker, no captura
# throttling termico sostenido, contencion real de un host compartido, ni
# variacion entre repeticiones (la propia tabla de arriba ya tiene
# min/max hasta ~15% de dispersion en el mismo bin/maquina). Multiplicar
# en vez de reemplazar el timeout fijo: un job barato en un worker rapido
# sigue con el piso de STALE_JOB_TIMEOUT_S (6h) como proteccion base; uno
# caro en un worker lento gana MAS margen que el fijo le daria hoy, en vez
# de arriesgarse a reencolar cuando en realidad iba a terminar bien.
ESTIMATE_SAFETY_FACTOR = 2.5


def estimate_job_duration_s(species: str, bin_index: int, worker_cpu_score: float | None) -> float | None:
    """Estima cuanto deberia tardar un job en un worker dado, escalando
    REFERENCE_TIMINGS_S por cpu_score. None si no hay referencia para esa
    combinacion o el worker no tiene cpu_score (version vieja del worker,
    o el benchmark fallo al arrancar) -- en ambos casos el llamador debe
    caer al timeout fijo, nunca tratar None como cero."""
    reference_s = REFERENCE_TIMINGS_S.get((species, bin_index))
    if reference_s is None or not worker_cpu_score or worker_cpu_score <= 0:
        return None
    return reference_s * (REFERENCE_CPU_SCORE / worker_cpu_score)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Columnas agregadas DESPUES de que la base de datos de produccion ya
# tenia filas reales -- "CREATE TABLE IF NOT EXISTS" en SCHEMA no las
# agrega a una tabla que ya existia antes de este cambio (esa clausula
# solo evita recrear la tabla, no la altera). _MIGRATIONS corre un
# "ALTER TABLE ... ADD COLUMN" idempotente (con manejo de "duplicate
# column" para poder llamarse en cada init_db() sin fallar) por cada
# columna nueva -- alternativa a borrar y recrear la DB, que en la VM
# real habria perdido 97 jobs done y sus resultados.
_MIGRATIONS = [
    "ALTER TABLE workers ADD COLUMN cpu_score REAL",
    "ALTER TABLE jobs ADD COLUMN min_cpu_score REAL NOT NULL DEFAULT 0",
    "ALTER TABLE workers ADD COLUMN image_digest TEXT",
]


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    (DB_PATH.parent / "results").mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc):
                    raise


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
                   ram_free_gb: float = None, cpu_load_pct: float = None, cpu_score: float = None,
                   image_digest: str = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO workers (worker_id, hostname, cpu_count, ram_gb, ram_free_gb, cpu_load_pct,
                                  cpu_score, image_digest, label, registered_at, last_heartbeat, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'online')
            ON CONFLICT(worker_id) DO UPDATE SET
                hostname=excluded.hostname, cpu_count=excluded.cpu_count, ram_gb=excluded.ram_gb,
                ram_free_gb=excluded.ram_free_gb, cpu_load_pct=excluded.cpu_load_pct,
                cpu_score=excluded.cpu_score, image_digest=excluded.image_digest,
                label=excluded.label, last_heartbeat=excluded.last_heartbeat, status='online'
            """,
            (worker_id, hostname, cpu_count, ram_gb, ram_free_gb, cpu_load_pct, cpu_score, image_digest, label,
             now_iso(), now_iso()),
        )


def touch_heartbeat(worker_id: str, ram_free_gb: float = None, cpu_load_pct: float = None,
                     image_digest: str = None) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE workers SET last_heartbeat=?, status='online',
                   ram_free_gb=COALESCE(?, ram_free_gb), cpu_load_pct=COALESCE(?, cpu_load_pct),
                   image_digest=COALESCE(?, image_digest)
            WHERE worker_id=?
            """,
            (now_iso(), ram_free_gb, cpu_load_pct, image_digest, worker_id),
        )
        return cur.rowcount > 0


def get_config(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def set_config(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, now_iso()),
        )


def claim_next_job(worker_id: str) -> sqlite3.Row | None:
    """Reclama atomicamente el job pendiente de mayor prioridad que el worker
    pueda satisfacer (cpu_count total, ram_free_gb EN VIVO -- no ram_gb total,
    un worker con poca RAM libre en este momento no debe recibir un job caro
    aunque su RAM instalada alcance en teoria -- y cpu_score, capacidad de
    computo real medida por benchmark en el worker, ver cpu_score() en
    worker.py). None si no hay ninguno elegible o el worker no esta
    registrado.

    Las repeticiones se corren en serie, nunca en paralelo (decision de
    equipo, 2026-09-14): un worker libre siempre recibe primero un job de
    la repeticion MAS BAJA que todavia tenga trabajo pendiente, sin
    importar la prioridad de especie/bin de una repeticion mas alta --
    'repeticion' entra antes que 'priority' en el ORDER BY. Antes de este
    fix, claim_next_job() ordenaba solo por priority/job_id, lo que dejaba
    que jobs de repeticiones 1-4 arrancaran mientras la 0 seguia con
    trabajo pendiente (encontrado en produccion: 4 jobs corriendo en
    paralelo en repeticiones distintas con la 0 sin terminar todavia)."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        worker = conn.execute("SELECT * FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
        if worker is None:
            return None
        # ram_free_gb/cpu_score pueden ser NULL si el worker nunca mando esa
        # telemetria (ej. version vieja, o el benchmark del propio worker
        # fallo) -- en ese caso no bloquear el job: ram_free_gb cae a ram_gb
        # total, cpu_score cae a "infinito" (cualquier min_cpu_score pasa).
        available_ram = worker["ram_free_gb"] if worker["ram_free_gb"] is not None else worker["ram_gb"]
        worker_cpu_score = worker["cpu_score"] if worker["cpu_score"] is not None else float("inf")
        row = conn.execute(
            """
            SELECT job_id FROM jobs
            WHERE status='pending' AND min_cpu_count <= ? AND min_ram_gb <= ? AND min_cpu_score <= ?
            ORDER BY repeticion ASC, priority DESC, job_id ASC LIMIT 1
            """,
            (worker["cpu_count"] or 0, available_ram or 0, worker_cpu_score),
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
    """Reencola jobs claimed/running cuyo worker no dio heartbeat en su
    propio timeout (STALE_JOB_TIMEOUT_S como piso minimo siempre; mas
    margen si hay una estimacion de duracion valida para ese job/worker,
    ver estimate_job_duration_s()). Devuelve los job_id afectados.

    El cutoff ya no es un solo valor para toda la query -- cada job puede
    necesitar un margen distinto segun cuanto se estima que tarda en el
    worker que lo tiene asignado, asi que se trae a Python el set de
    candidatos bajo el cutoff MAS LAXO posible (el piso fijo, el mas
    generoso de los dos) y se filtra fila por fila con su propio timeout
    real -- mas simple y correcto que expresar un timeout dinamico por
    fila dentro del WHERE de SQL."""
    floor_cutoff = time.time() - STALE_JOB_TIMEOUT_S
    with get_conn() as conn:
        candidates = conn.execute(
            """
            SELECT j.job_id, j.species, j.bin_index, j.updated_at,
                   w.last_heartbeat, w.cpu_score
            FROM jobs j
            LEFT JOIN workers w ON w.worker_id = j.claimed_by
            WHERE j.status IN ('claimed', 'running')
              AND (w.last_heartbeat IS NULL OR w.last_heartbeat < ?)
            """,
            (datetime.fromtimestamp(floor_cutoff, tz=timezone.utc).isoformat(),),
        ).fetchall()
        now = time.time()
        job_ids = []
        for row in candidates:
            if row["last_heartbeat"] is None:
                job_ids.append(row["job_id"])
                continue
            last_heartbeat_s = datetime.fromisoformat(row["last_heartbeat"]).timestamp()
            age_s = now - last_heartbeat_s
            estimated_s = estimate_job_duration_s(row["species"], row["bin_index"], row["cpu_score"])
            timeout_s = max(STALE_JOB_TIMEOUT_S, estimated_s * ESTIMATE_SAFETY_FACTOR) \
                if estimated_s is not None else STALE_JOB_TIMEOUT_S
            if age_s >= timeout_s:
                job_ids.append(row["job_id"])
        for job_id in job_ids:
            # El mensaje sigue diciendo "heartbeat vencido" sin distinguir si
            # el timeout que se aplico fue el piso fijo o uno mayor por
            # estimacion -- la causa raiz es la misma (el worker dejo de dar
            # heartbeat), solo cambia CUANTO se esperaba antes de actuar.
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
               n_events: int, priority: int = 0, min_ram_gb: float = 0, min_cpu_count: int = 0,
               min_cpu_score: float = 0) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (species, bin_index, offset_x_m, repeticion, n_events, priority,
                               min_ram_gb, min_cpu_count, min_cpu_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(species, bin_index, offset_x_m, repeticion) DO NOTHING
            """,
            (species, bin_index, offset_x_m, repeticion, n_events, priority, min_ram_gb, min_cpu_count,
             min_cpu_score, now_iso(), now_iso()),
        )
        return cur.lastrowid
