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
    connected_s     REAL NOT NULL DEFAULT 0,
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

# Red de seguridad SOLO para cuando no hay estimacion disponible (worker
# sin cpu_score, o combinacion especie/bin sin referencia) -- con
# estimacion disponible, el umbral real lo decide ABANDON_FACTOR/
# ABANDON_FLOOR_S/ABANDON_CEILING_S de mas abajo (decision 2026-09-14: ya
# no domina siempre como antes). 5h, no 6h -- ajustado tras el mismo
# cambio.
STALE_JOB_TIMEOUT_S = float(os.environ.get("STALE_JOB_TIMEOUT_S", 5 * 3600))

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
# min/max hasta ~15% de dispersion en el mismo bin/maquina). Comparado
# contra CONNECTED_S (tiempo real conectado acumulado, ver abajo), no
# contra tiempo de pared -- un worker que se apaga no gasta presupuesto de
# progreso mientras esta apagado.
ESTIMATE_SAFETY_FACTOR = 2.5

# Umbral de heartbeat vencido = "probablemente abandonado", una condicion
# SEPARADA del progreso de arriba (connected_s vs estimacion). Un worker
# puede estar perfectamente al dia en progreso y aun asi llevar mucho
# tiempo de pared sin dar senales -- eso es lo que este umbral detecta,
# no cuanto ha avanzado el computo en si.
#
# Decision de equipo (2026-09-14), reemplaza el STALE_JOB_TIMEOUT_S fijo
# de 6h que antes dominaba casi siempre sobre la estimacion (bug real
# encontrado en produccion: un job de ~2h de referencia esperaba las 6h
# completas antes de reencolarse, sin importar que la estimacion dijera
# mucho menos). Ahora escala con la estimacion cuando existe:
#   umbral_abandono = clamp(estimacion * ABANDON_FACTOR, ABANDON_FLOOR_S, ABANDON_CEILING_S)
# ABANDON_FACTOR=2 (no el mismo 2.5 de progreso -- este numero da margen
# para que alguien reconecte su PC, no margen de computo, un proposito
# distinto). ABANDON_FLOOR_S=1h protege un job barato de reencolarse por
# un simple lag de red breve. ABANDON_CEILING_S=10h ("irse a dormir 8h +
# 2h de buffer para reconectar", razonamiento explicito del usuario) evita
# que un job muy pesado en un worker lento de un umbral absurdamente largo
# sin limite. Sin estimacion disponible (worker sin cpu_score, o
# combinacion sin referencia), cae directo a STALE_JOB_TIMEOUT_S (6h) --
# ese valor sigue siendo la red de seguridad para ese caso, sin cambios.
ABANDON_FACTOR = 2.0
ABANDON_FLOOR_S = 1 * 3600
ABANDON_CEILING_S = 10 * 3600

# Tope del intervalo individual que un solo heartbeat puede sumar a
# jobs.connected_s (ver touch_heartbeat()) -- protege contra sumar un
# hueco de desconexion real como si fuera tiempo conectado: si el gap
# desde el heartbeat anterior es mayor a esto, algo interrumpio la
# conexion en el medio (red caida, PC suspendida, worker reiniciado) y
# ese tiempo NO cuenta como progreso real. 4x HEARTBEAT_INTERVAL_S
# (worker.py, default 30s) da margen de jitter de red normal sin abrir
# la puerta a sumar gaps largos.
MAX_HEARTBEAT_ACCRUAL_S = 120.0


# Las runs reales tienden a tardar mas que la referencia pura, no menos
# -- observado por el usuario (2026-09-14): una run de GCR_He bin7
# estimada en ~5.2h tomo ~5.7h reales, ~10% mas. DISPLAY_OVERESTIMATE_FACTOR
# aplica ese margen directamente sobre el numero que ve todo el mundo
# (dashboard, y el criterio de progreso/abandono de requeue_stale_jobs(),
# que usan el mismo estimate_job_duration_s()) -- separado de
# ESTIMATE_SAFETY_FACTOR (tolerancia antes de reencolar, no cambia el
# numero mostrado) y de ABANDON_FACTOR (margen para reconectar, no de
# computo). 1.15x, redondeado un poco por encima del ~10% observado en
# el unico caso medido hasta ahora -- ajustar si se observan mas casos
# reales con un patron distinto.
DISPLAY_OVERESTIMATE_FACTOR = 1.15


def estimate_job_duration_s(species: str, bin_index: int, worker_cpu_score: float | None) -> float | None:
    """Estima cuanto deberia tardar un job en un worker dado, escalando
    REFERENCE_TIMINGS_S por cpu_score y aplicando DISPLAY_OVERESTIMATE_FACTOR
    (las runs reales tienden a tardar mas que la referencia pura). None si
    no hay referencia para esa combinacion o el worker no tiene cpu_score
    (version vieja del worker, o el benchmark fallo al arrancar) -- en
    ambos casos el llamador debe caer al timeout fijo, nunca tratar None
    como cero."""
    reference_s = REFERENCE_TIMINGS_S.get((species, bin_index))
    if reference_s is None or not worker_cpu_score or worker_cpu_score <= 0:
        return None
    return reference_s * (REFERENCE_CPU_SCORE / worker_cpu_score) * DISPLAY_OVERESTIMATE_FACTOR


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
    "ALTER TABLE jobs ADD COLUMN connected_s REAL NOT NULL DEFAULT 0",
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


def _accrue_connected_time(conn, worker_id: str, previous_heartbeat_iso: str | None) -> None:
    """Suma al job claimed/running de este worker (si tiene uno) el tiempo
    real transcurrido desde su heartbeat anterior -- ver jobs.connected_s,
    usado por requeue_stale_jobs() para medir progreso real en vez de
    tiempo de pared (un worker apagado no gasta presupuesto de progreso
    mientras esta apagado). Sin heartbeat anterior (primer heartbeat tras
    registrarse) no hay intervalo que sumar. El intervalo se recorta a
    MAX_HEARTBEAT_ACCRUAL_S -- un gap mas largo que eso indica una
    desconexion real en el medio (red caida, PC suspendida), y ese hueco
    no debe contar como tiempo conectado."""
    if previous_heartbeat_iso is None:
        return
    interval_s = (datetime.now(timezone.utc) - datetime.fromisoformat(previous_heartbeat_iso)).total_seconds()
    if interval_s <= 0:
        return
    interval_s = min(interval_s, MAX_HEARTBEAT_ACCRUAL_S)
    conn.execute(
        "UPDATE jobs SET connected_s = connected_s + ? WHERE claimed_by=? AND status IN ('claimed', 'running')",
        (interval_s, worker_id),
    )


def touch_heartbeat(worker_id: str, ram_free_gb: float = None, cpu_load_pct: float = None,
                     image_digest: str = None) -> bool:
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT last_heartbeat FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
        if previous is None:
            return False
        _accrue_connected_time(conn, worker_id, previous["last_heartbeat"])
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


# Umbral de cpu_score para considerar un worker "rapido" al emparejar
# (ver pick_job_for_worker()) -- REFERENCE_CPU_SCORE (4.461) es la
# maquina de referencia real (bryam-local); un worker igual o mejor que
# eso recibe preferentemente el job MAS pesado disponible dentro de su
# (repeticion, priority), uno por debajo recibe el MAS liviano. No hay
# una categoria "media" a proposito -- con solo un puñado de workers
# reales activos, una tercera categoria fragmentaria no aportaria mejor
# emparejamiento, solo mas casos que razonar.
FAST_WORKER_CPU_SCORE_THRESHOLD = REFERENCE_CPU_SCORE


def pick_job_for_worker(candidates: list[sqlite3.Row], worker_cpu_score: float) -> int | None:
    """Dentro de un (repeticion, priority) ya fijado (ver claim_next_job()),
    elige que job especifico dar a este worker segun su cpu_score: un
    worker rapido recibe el MAS PESADO disponible (bin caro como GCR_He
    al mismo bin_index que GCR_H, o simplemente el primero si son
    igual de pesados), uno lento recibe el MAS LIVIANO -- asi los bins
    caros tienden a terminar en las maquinas rapidas sin bloquear a las
    lentas, que igual pueden aportar en el trabajo mas barato del mismo
    grupo. Sin REFERENCE_TIMINGS_S para una combinacion (no deberia
    pasar con las especies/bins conocidos, pero por si acaso) se trata
    como el mas liviano posible, para no perder ese candidato del todo.
    None si no hay candidatos."""
    if not candidates:
        return None
    worker_is_fast = worker_cpu_score >= FAST_WORKER_CPU_SCORE_THRESHOLD

    def weight(row: sqlite3.Row) -> float:
        return REFERENCE_TIMINGS_S.get((row["species"], row["bin_index"]), 0.0)

    best = max(candidates, key=weight) if worker_is_fast else min(candidates, key=weight)
    return best["job_id"]


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
    paralelo en repeticiones distintas con la 0 sin terminar todavia).

    Emparejamiento por cpu_score (2026-09-14): una vez fijado el
    (repeticion, priority) a servir, si hay mas de un job candidato ahi
    (offsets distintos del mismo bin, o GCR_H/GCR_He compartiendo el
    mismo bin_index/priority), se elige cual dar segun pick_job_for_worker()
    -- un worker rapido recibe el mas pesado del grupo, uno lento el mas
    liviano. Pedido explicito del usuario: los bins caros (6/7) deben
    tender a terminar en las maquinas rapidas sin bloquear a las lentas."""
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
        # Primero se fija repeticion/priority (el orden ya decidido, sin
        # tocar) tomando el (repeticion, priority) mas alto entre los
        # candidatos elegibles -- despues, DENTRO de ese grupo, se elige
        # cual job especifico dar segun que tan rapido es este worker (ver
        # abajo). No se puede saltar a un (repeticion, priority) distinto
        # solo porque tenga un job mejor emparejado -- eso reintroduciria
        # el bug de repeticiones en paralelo que este ORDER BY ya corrige.
        top = conn.execute(
            """
            SELECT repeticion, priority FROM jobs
            WHERE status='pending' AND min_cpu_count <= ? AND min_ram_gb <= ? AND min_cpu_score <= ?
            ORDER BY repeticion ASC, priority DESC LIMIT 1
            """,
            (worker["cpu_count"] or 0, available_ram or 0, worker_cpu_score),
        ).fetchone()
        if top is None:
            return None
        candidates = conn.execute(
            """
            SELECT job_id, species, bin_index FROM jobs
            WHERE status='pending' AND min_cpu_count <= ? AND min_ram_gb <= ? AND min_cpu_score <= ?
              AND repeticion=? AND priority=?
            ORDER BY job_id ASC
            """,
            (worker["cpu_count"] or 0, available_ram or 0, worker_cpu_score, top["repeticion"], top["priority"]),
        ).fetchall()
        job_id = pick_job_for_worker(candidates, worker_cpu_score)
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
        # connected_s se resetea a 0 al volver a 'pending' -- el proximo
        # intento (mismo u otro worker) empieza su propio progreso desde
        # cero, no arrastra el tiempo conectado del intento fallido.
        conn.execute(
            "UPDATE jobs SET status=?, last_error=?, updated_at=?, "
            "connected_s=CASE WHEN ?='pending' THEN 0 ELSE connected_s END WHERE job_id=?",
            (new_status, None if new_status == "done" else f"exit_code={exit_code} n_rows={n_rows}",
             now_iso(), new_status, job_id),
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
            "UPDATE jobs SET status=?, last_error=?, updated_at=?, "
            "connected_s=CASE WHEN ?='pending' THEN 0 ELSE connected_s END WHERE job_id=?",
            (new_status, error, now_iso(), new_status, job_id),
        )
        return new_status


def _abandon_timeout_s(estimated_s: float | None) -> float:
    """Umbral de heartbeat vencido antes de considerar un job abandonado
    (ver ABANDON_FACTOR/ABANDON_FLOOR_S/ABANDON_CEILING_S). Sin estimacion
    disponible, cae al piso fijo STALE_JOB_TIMEOUT_S -- unica red de
    seguridad para ese caso."""
    if estimated_s is None:
        return STALE_JOB_TIMEOUT_S
    return max(ABANDON_FLOOR_S, min(estimated_s * ABANDON_FACTOR, ABANDON_CEILING_S))


def requeue_stale_jobs() -> list[int]:
    """Reencola jobs claimed/running que cumplen CUALQUIERA de dos
    condiciones independientes (decision 2026-09-14, reemplaza el timeout
    unico anterior):

    1. Progreso agotado: jobs.connected_s (tiempo REAL conectado
       acumulado mientras trabaja este job, ver touch_heartbeat()) ya
       supera la estimacion con margen (ESTIMATE_SAFETY_FACTOR) -- el
       trabajo deberia haber terminado dado el tiempo que realmente
       estuvo corriendo, sin importar cuanto tiempo de PARED paso
       (un worker que se apaga y reconecta no pierde este progreso).
    2. Abandono: tiempo de pared SIN heartbeat (age_s, no connected_s)
       supera _abandon_timeout_s() -- protege contra un worker que se
       fue y nunca vuelve, sin depender de cuanto habia avanzado.

    Sin estimacion disponible (worker sin cpu_score, o combinacion sin
    referencia), ninguna de las dos se puede evaluar por progreso -- solo
    aplica la condicion de abandono con el piso fijo STALE_JOB_TIMEOUT_S,
    igual que el comportamiento original.

    El cutoff de heartbeat en el WHERE de SQL usa el MAS CORTO de los
    pisos posibles (min(STALE_JOB_TIMEOUT_S, ABANDON_FLOOR_S), no el mas
    largo) para no excluir de entrada candidatos que el criterio fino en
    Python si debe evaluar -- trae un superconjunto amplio de la tabla,
    y cada fila se filtra despues con su propio umbral real (que puede
    ser mucho mas corto que STALE_JOB_TIMEOUT_S cuando hay estimacion).
    Mas simple y correcto que expresar el timeout dinamico por fila
    dentro del WHERE."""
    floor_cutoff = time.time() - min(STALE_JOB_TIMEOUT_S, ABANDON_FLOOR_S)
    with get_conn() as conn:
        candidates = conn.execute(
            """
            SELECT j.job_id, j.species, j.bin_index, j.connected_s,
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
            progress_exhausted = estimated_s is not None and row["connected_s"] >= estimated_s * ESTIMATE_SAFETY_FACTOR
            abandoned = age_s >= _abandon_timeout_s(estimated_s)
            if progress_exhausted or abandoned:
                job_ids.append(row["job_id"])
        for job_id in job_ids:
            # El mensaje sigue diciendo "heartbeat vencido" de forma
            # generica -- ambas condiciones (progreso agotado o abandono)
            # comparten la misma causa raiz visible (el worker dejo de dar
            # heartbeat), solo cambia el criterio que decidio actuar ahora.
            # connected_s se resetea a 0: el proximo intento empieza su
            # propio progreso desde cero.
            conn.execute(
                """
                UPDATE jobs SET status=CASE WHEN attempt < max_attempts THEN 'pending' ELSE 'failed' END,
                       claimed_by=NULL, claimed_at=NULL, connected_s=0,
                       last_error='requeued: heartbeat vencido', updated_at=?
                WHERE job_id=?
                """,
                (now_iso(), job_id),
            )
        return job_ids


def list_jobs(status: str | None = None) -> list[sqlite3.Row]:
    """Cada fila trae ademas 'actual_duration_s' -- el duration_s REAL
    reportado por el worker en la subida mas reciente de ese job (tabla
    results, que ya lo guarda desde record_result() pero ningun endpoint
    lo habia expuesto hasta ahora). NULL para un job que nunca subio un
    resultado (pending/failed sin intentos exitosos) -- se toma la fila
    de results mas reciente por submitted_at, no necesariamente la que
    dejo el job en 'done' (un job con reintentos puede tener resultados
    fallidos previos en la tabla, pero la ULTIMA fila siempre corresponde
    al estado actual porque record_result()/record_failure() son lo
    ultimo que corre en cada intento)."""
    query = """
        SELECT j.*, (
            SELECT r.duration_s FROM results r
            WHERE r.job_id = j.job_id
            ORDER BY r.submitted_at DESC LIMIT 1
        ) AS actual_duration_s
        FROM jobs j
    """
    with get_conn() as conn:
        if status:
            return conn.execute(query + " WHERE j.status=? ORDER BY j.job_id", (status,)).fetchall()
        return conn.execute(query + " ORDER BY j.job_id").fetchall()


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
