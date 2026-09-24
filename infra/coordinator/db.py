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
import uuid
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
    status          TEXT NOT NULL DEFAULT 'online',
    orphans_killed_total INTEGER
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

-- "phase" (min/max, ver SPECIES_PHASE en run_organ_sweep.py) se agrego
-- DESPUES de que la produccion real ya tenia 600 filas con un UNIQUE de
-- 4 columnas (species, bin_index, offset_x_m, repeticion) -- hasta
-- 2026-09-16 cada especie corria en una sola fase fija (GCR_H/GCR_He=min,
-- SEP_p=max), asi que phase era 1:1 con species y no hacia falta como
-- columna propia. Expandir a los 6 casos (GCR_H/He en min Y max, SEP_p en
-- max Y min) exige que el UNIQUE incluya phase -- si no, GCR_H-min-bin3-
-- offset0-rep0 y GCR_H-max-bin3-offset0-rep0 colisionarian como "el mismo
-- job" (mismo species/bin_index/offset_x_m/repeticion, el UNIQUE viejo no
-- los distinguia). SQLite no permite ALTER TABLE para modificar un UNIQUE
-- existente -- CREATE TABLE aqui ya incluye phase en el UNIQUE para una
-- base de datos nueva; _migrate_jobs_add_phase() en init_db() maneja la
-- migracion real (rename+recreate+copy+backfill) para una base de datos
-- que ya tenia jobs con el esquema viejo, ver esa funcion.
CREATE TABLE IF NOT EXISTS jobs (
    job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    species         TEXT NOT NULL,
    phase           TEXT NOT NULL DEFAULT '',
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
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    log_request_id TEXT,
    log_received_id TEXT,
    log_attempt INTEGER,
    log_requested INTEGER NOT NULL DEFAULT 0,
    log_tail TEXT,
    log_tail_updated_at TEXT,
    UNIQUE(species, phase, bin_index, offset_x_m, repeticion)
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
    "ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE workers ADD COLUMN active_job_id INTEGER",
    "ALTER TABLE workers ADD COLUMN active_job_reported_at TEXT",
    "ALTER TABLE jobs ADD COLUMN log_request_id TEXT",
    "ALTER TABLE jobs ADD COLUMN log_received_id TEXT",
    "ALTER TABLE jobs ADD COLUMN log_attempt INTEGER",
    "ALTER TABLE jobs ADD COLUMN log_requested INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN log_tail TEXT",
    "ALTER TABLE jobs ADD COLUMN log_tail_updated_at TEXT",
    "ALTER TABLE workers ADD COLUMN orphans_killed_total INTEGER",
]


# Especie -> fase que ya tenia CADA job existente en produccion antes de
# este cambio (SPECIES_PHASE en run_organ_sweep.py era 1:1 species->phase
# hasta 2026-09-16) -- usado SOLO para el backfill de _migrate_jobs_add_phase(),
# nunca para decidir que fase corre un job nuevo (eso ya lo controla
# run_organ_sweep.py/seed_full_sweep.py). Copiado aqui (no importado) por
# el mismo motivo que seed_full_sweep.py ya copia SPECIES/OFFSET_X_VALUES_M:
# ese script vive en un proyecto Geant4 que no es un paquete Python
# instalable desde infra/.
_LEGACY_SPECIES_PHASE = {"GCR_H": "min", "GCR_He": "min", "SEP_p": "max"}


def _migrate_jobs_add_phase(conn) -> None:
    """Agrega la columna `phase` a una tabla `jobs` que ya existia ANTES
    de este cambio (sin phase, UNIQUE de 4 columnas) -- SQLite no permite
    ALTER TABLE para agregar una columna a un UNIQUE existente ni para
    modificar un UNIQUE ya creado, asi que la unica via es: crear una
    tabla nueva con el esquema correcto, copiar las filas backfillando
    `phase` desde `species` (_LEGACY_SPECIES_PHASE, valido porque CUALQUIER
    job existente en produccion hasta ahora fue sembrado bajo el regimen
    1:1 species->phase), borrar la vieja, renombrar. Todo dentro de la
    transaccion que ya abre init_db() (BEGIN/COMMIT implicito de
    get_conn()) -- si algo falla a mitad, sqlite3 hace rollback completo,
    nunca deja la base de datos con una tabla a medio migrar.

    No-op (detectado por PRAGMA table_info) si `phase` ya existe -- ej. en
    una base de datos nueva creada directamente por SCHEMA (que ya incluye
    phase), o si esta funcion ya corrio antes en esta misma base de datos.
    Mismo criterio idempotente que _MIGRATIONS (llamable en cada init_db()
    sin fallar ni duplicar trabajo)."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "phase" in cols:
        return
    if not cols:
        return  # la tabla jobs ni siquiera existe todavia -- SCHEMA la crea ya con phase, nada que migrar

    print("Migrando tabla 'jobs': agregando columna 'phase' (recrea la tabla, ver _migrate_jobs_add_phase)")
    # Bug real de produccion (2026-09-24): con foreign_keys=ON (ver
    # get_conn()), el DROP TABLE jobs_pre_phase_migration de mas abajo
    # fallaba con "FOREIGN KEY constraint failed" -- results.job_id
    # REFERENCES jobs(job_id) sigue resolviendo contra el nombre logico
    # `jobs` mientras la tabla vieja lo ocupa (renombrada), y SQLite no
    # permite dropear una tabla con una FK entrante pendiente de
    # resolver contra el nombre nuevo. El proceso murio a mitad de la
    # transaccion (excepcion sin capturar en init_db()), dejando `jobs`
    # vacia y `jobs_pre_phase_migration` con los datos originales
    # intactos -- recuperado a mano esa vez (ver infra/OPERATIONS_LOG.md).
    # Esta migracion entera ya corre dentro de una sola transaccion
    # (BEGIN/COMMIT implicito de get_conn()), asi que desactivar el
    # chequeo de FK solo aqui es seguro: se re-activa solo al abrir la
    # PROXIMA conexion (get_conn() siempre la pone ON de nuevo), y ninguna
    # fila con una FK realmente invalida puede colarse -- el propio
    # INSERT...SELECT de mas abajo copia los mismos job_id, sin crear
    # ninguna referencia nueva.
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("ALTER TABLE jobs RENAME TO jobs_pre_phase_migration")
    # Definicion explicita e independiente de SCHEMA -- parsear SCHEMA con
    # split(";") es fragil (los comentarios SQL de varias lineas de ese
    # bloque pueden contener texto que confunde un split ingenuo, como se
    # encontro al probar esta migracion contra datos reales) y esta tabla
    # solo necesita existir UNA VEZ para la migracion (no se vuelve a usar
    # despues), asi que mantenerla en sincronia manual con el CREATE TABLE
    # de SCHEMA es aceptable -- si SCHEMA agrega una columna nueva a jobs
    # en el futuro, esta migracion ya no aplica de todos modos (phase ya
    # existiria y _migrate_jobs_add_phase() seria un no-op).
    conn.execute("""
        CREATE TABLE jobs (
            job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            species         TEXT NOT NULL,
            phase           TEXT NOT NULL DEFAULT '',
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
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            log_request_id TEXT,
            log_received_id TEXT,
            log_attempt INTEGER,
            log_requested INTEGER NOT NULL DEFAULT 0,
            log_tail TEXT,
            log_tail_updated_at TEXT,
            UNIQUE(species, phase, bin_index, offset_x_m, repeticion)
        )
    """)

    old_cols = cols  # columnas reales de la tabla vieja, puede no traer log_*/connected_s/etc si es muy antigua
    common_cols = [c for c in old_cols if c != "phase"]
    select_cols = ", ".join(common_cols)
    # CASE por especie -- exactamente _LEGACY_SPECIES_PHASE, expandido a
    # SQL porque no hay forma de pasarle un dict de Python a una
    # sentencia INSERT...SELECT en sqlite3 sin crear una tabla temporal
    # aparte solo para eso.
    phase_case = "CASE species " + " ".join(
        f"WHEN '{species}' THEN '{phase}'" for species, phase in _LEGACY_SPECIES_PHASE.items()
    ) + " ELSE '' END"
    insert_cols = ", ".join(common_cols) + ", phase"
    conn.execute(
        f"INSERT INTO jobs ({insert_cols}) SELECT {select_cols}, {phase_case} FROM jobs_pre_phase_migration"
    )
    n_migrated = conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
    n_unknown_species = conn.execute("SELECT COUNT(*) AS n FROM jobs WHERE phase=''").fetchone()["n"]
    if n_unknown_species:
        # No deberia pasar nunca con datos reales (toda especie sembrada
        # hasta ahora esta en _LEGACY_SPECIES_PHASE) -- si pasa, se
        # imprime pero NO se aborta la migracion: mejor una fila con
        # phase='' visible y corregible a mano que perder la migracion
        # completa por una sola fila inesperada.
        print(f"ADVERTENCIA: {n_unknown_species} job(s) con especie no reconocida en "
              f"_LEGACY_SPECIES_PHASE -- quedaron con phase='' tras la migracion, revisar a mano.")
    conn.execute("DROP TABLE jobs_pre_phase_migration")
    print(f"Migracion completa: {n_migrated} jobs con columna 'phase' agregada (backfill por especie).")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    (DB_PATH.parent / "results").mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _migrate_jobs_add_phase(conn)
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


def _accrue_connected_time(conn, worker_id: str, previous_heartbeat_iso: str | None,
                            active_job_id: int | None) -> None:
    """Suma al job claimed/running de este worker (si tiene uno) el tiempo
    real transcurrido desde su heartbeat anterior -- ver jobs.connected_s,
    usado por requeue_stale_jobs() para medir progreso real en vez de
    tiempo de pared (un worker apagado no gasta presupuesto de progreso
    mientras esta apagado). Sin heartbeat anterior (primer heartbeat tras
    registrarse) no hay intervalo que sumar. El intervalo se recorta a
    MAX_HEARTBEAT_ACCRUAL_S -- un gap mas largo que eso indica una
    desconexion real en el medio (red caida, PC suspendida), y ese hueco
    no debe contar como tiempo conectado.

    Bug real de produccion (2026-09-15, reportado por el usuario): si el
    PROCESO del worker muere y se reinicia (apagado/encendido, crash,
    recreacion del contenedor) sin liberar primero el job que tenia
    activo, el proceso nuevo simplemente pide el siguiente -- dejando el
    job viejo huerfano en 'claimed'/'running' bajo el mismo worker_id. El
    UPDATE de aqui, sin filtrar por job_id, sumaba connected_s a AMBOS
    (el huerfano y el real) en cada heartbeat siguiente, aunque el worker
    solo trabajara en uno -- Geant4 no guarda estados intermedios, asi
    que el progreso del huerfano ya se perdio por completo y no deberia
    seguir "avanzando" en el dashboard. No ocurre con un simple corte de
    red (el mismo proceso sigue vivo y retoma el MISMO job_id al
    reconectar, nunca hay dos jobs activos a la vez bajo ese worker).

    Corregido filtrando por active_job_id -- el worker ya lo manda en
    cada heartbeat (_active_cancel en worker.py, el job que el PROCESO
    ACTUAL cree tener activo, no lo que diga la DB). Solo ese job
    especifico acumula tiempo; cualquier otro job claimed/running del
    mismo worker se reencola de inmediato en la misma transaccion
    (requeue_orphaned_jobs_for_worker(), ver abajo) -- sin heartbeat
    activo() que filtre (worker sin telemetria, version vieja), no se
    reencola nada por este mecanismo, mismo criterio de no bloquear que
    ya usan ram_free_gb/cpu_score ausentes."""
    if previous_heartbeat_iso is None:
        return
    interval_s = (datetime.now(timezone.utc) - datetime.fromisoformat(previous_heartbeat_iso)).total_seconds()
    if interval_s <= 0:
        return
    interval_s = min(interval_s, MAX_HEARTBEAT_ACCRUAL_S)
    if active_job_id is not None:
        conn.execute(
            "UPDATE jobs SET connected_s = connected_s + ? WHERE claimed_by=? AND status IN ('claimed', 'running') AND job_id=?",
            (interval_s, worker_id, active_job_id),
        )
    else:
        conn.execute(
            "UPDATE jobs SET connected_s = connected_s + ? WHERE claimed_by=? AND status IN ('claimed', 'running')",
            (interval_s, worker_id),
        )


def requeue_orphaned_jobs_for_worker(conn, worker_id: str, active_job_id: int | None) -> list[int]:
    """Reencola de inmediato cualquier job claimed/running de este worker
    que NO sea su active_job_id reportado -- computo genuinamente perdido
    (Geant4 no tiene estados intermedios), no algo a preservar esperando
    el timeout normal de abandono. Sin active_job_id (worker sin esa
    telemetria todavia) no se toca nada, mismo criterio conservador que
    _accrue_connected_time(). Devuelve los job_id reencolados, para
    loguear si hace falta."""
    if active_job_id is None:
        return []
    rows = conn.execute(
        "SELECT job_id, attempt, max_attempts FROM jobs WHERE claimed_by=? AND status IN ('claimed','running') AND job_id != ?",
        (worker_id, active_job_id),
    ).fetchall()
    requeued = []
    error = (f"reencolado automaticamente: el worker {worker_id} reclamo otro job ({active_job_id}) "
             "sin liberar este primero (proceso reiniciado) -- computo perdido, Geant4 no guarda estados intermedios")
    for row in rows:
        # Mismo criterio que record_failure(): 'pending' libera la
        # asignacion (claimed_by=NULL) para que cualquier worker lo
        # reclame de nuevo; 'failed' (intentos agotados) CONSERVA
        # claimed_by/claimed_at -- no es un caso especial de esta
        # funcion, es como ya se comporta cualquier job que agota sus
        # intentos en el resto del coordinator.
        new_status = "pending" if row["attempt"] < row["max_attempts"] else "failed"
        conn.execute(
            "UPDATE jobs SET status=?, "
            "claimed_by=CASE WHEN ?='pending' THEN NULL ELSE claimed_by END, "
            "claimed_at=CASE WHEN ?='pending' THEN NULL ELSE claimed_at END, "
            "connected_s=0, cancel_requested=0, log_requested=0, last_error=?, updated_at=? WHERE job_id=?",
            (new_status, new_status, new_status, error, now_iso(), row["job_id"]),
        )
        requeued.append(row["job_id"])
    return requeued


def touch_heartbeat(worker_id: str, ram_free_gb: float = None, cpu_load_pct: float = None,
                     image_digest: str = None, active_job_id: int | None = None,
                     orphans_killed_total: int | None = None) -> dict | None:
    """None si el worker no esta registrado (llamador responde 404).
    Si esta registrado: {"cancel_job_id": int | None, "request_log": bool}
    -- job_id del job activo de este worker si fue marcado para cancelar
    (ver request_job_cancel()/cancelled_job_for_worker()), y si su log
    activo fue pedido (ver request_job_log()/log_requested_for_worker(),
    2026-09-16) -- ambos calculados en la MISMA transaccion para no pagar
    un segundo round-trip a la DB desde app.py en cada heartbeat (cada
    30s, por diseno).

    workers.active_job_id/active_job_reported_at (2026-09-15, nuevo):
    a diferencia de ram_free_gb/cpu_load_pct/image_digest (COALESCE --
    conservan el ultimo valor conocido si el heartbeat no lo trae),
    active_job_id se ESCRIBE TAL CUAL llega, incluyendo NULL explicito --
    el worker ya manda su job activo real en cada heartbeat
    (_active_cancel en worker.py) precisamente para que
    cancelled_job_for_worker() desambigue cual job cancelar; guardarlo
    aqui (antes se usaba y se descartaba en la misma transaccion, sin
    persistir) permite diagnosticar por API el caso real encontrado en
    produccion: un worker con CPU alta y heartbeat vivo pero SIN ningun
    job claimed/running en la tabla jobs -- computo huerfano tras un
    reencolado manual que nunca senalizo al proceso real. Sin esto, la
    unica forma de saber que job cree el worker que tiene activo era
    adivinar o acceder a la maquina.

    orphans_killed_total (2026-09-20, ver cleanup_orphaned_simulations()
    en worker.py): COALESCE, NO escritura directa como active_job_id --
    a diferencia de active_job_id (donde NULL es un dato real, "sin job
    activo ahora"), un heartbeat de un worker VIEJO que todavia no manda
    este campo simplemente no trae informacion sobre orfanos, no dice
    "cero orfanos matados" -- COALESCE conserva el ultimo valor conocido
    en ese caso, igual que ram_free_gb/cpu_load_pct/image_digest. El
    contador en si ya es manejado por el worker para reflejar reinicios
    (vuelve a 0 en cada arranque del proceso, ver worker.py) -- este
    COALESCE es solo para no perder el ultimo valor real ante un
    heartbeat que no lo informa, no para acumular entre reinicios."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT last_heartbeat FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
        if previous is None:
            return None
        _accrue_connected_time(conn, worker_id, previous["last_heartbeat"], active_job_id)
        cur = conn.execute(
            """
            UPDATE workers SET last_heartbeat=?, status='online',
                   ram_free_gb=COALESCE(?, ram_free_gb), cpu_load_pct=COALESCE(?, cpu_load_pct),
                   image_digest=COALESCE(?, image_digest), active_job_id=?, active_job_reported_at=?,
                   orphans_killed_total=COALESCE(?, orphans_killed_total)
            WHERE worker_id=?
            """,
            (now_iso(), ram_free_gb, cpu_load_pct, image_digest, active_job_id, now_iso(),
             orphans_killed_total, worker_id),
        )
        if cur.rowcount == 0:
            return None
        result = {
            "cancel_job_id": cancelled_job_for_worker(conn, worker_id, active_job_id),
            "request_log": log_requested_for_worker(conn, worker_id, active_job_id),
        }
        if result["request_log"]:
            row = conn.execute("SELECT job_id, attempt, log_request_id FROM jobs WHERE claimed_by=? AND status IN ('claimed','running') AND log_requested=1 AND (? IS NULL OR job_id=?) ORDER BY job_id", (worker_id, active_job_id, active_job_id)).fetchone()
            result["log_request"] = {"job_id": row["job_id"], "attempt": row["attempt"], "request_id": row["log_request_id"]}
        # Al final, despues de resolver cancel/log-request sobre el job
        # activo real -- un job huerfano (claimed/running bajo este
        # worker, pero distinto de active_job_id) nunca deberia competir
        # por esas señales, ya se perdio del todo.
        requeued = requeue_orphaned_jobs_for_worker(conn, worker_id, active_job_id)
        if requeued:
            result["requeued_orphan_job_ids"] = requeued
        return result


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

# Umbral de cpu_score para considerar un worker "elite" (2026-09-14,
# pedido explicito del usuario): muy por encima de FAST_WORKER_CPU_SCORE_THRESHOLD
# a proposito -- el unico worker real que hoy lo supera es "tania"
# (cpu_score=18.07, mas de 4x el segundo mejor conocido, bryam-parrot
# con 4.2). Motivo: el usuario confirmo que tania se mantendra conectada
# toda la noche, y quiere asegurar el avance de los jobs mas pesados del
# barrido (GCR_He bin6/7 sobre todo) aprovechando esa ventana, en vez de
# dejarlos sujetos al orden normal por repeticion. Un worker elite se
# salta claim_next_job()'s "repeticion ASC" (ver claim_next_job()) y
# recibe directamente el job pendiente mas pesado de TODO el sistema
# (cualquier repeticion), siempre que sus recursos alcancen los umbrales
# min_* del job -- una excepcion deliberada a "repeticiones en serie"
# para los pocos workers realmente sobresalientes, no un cambio del
# criterio general (ver test_claim_elite_worker_crosses_repetition_boundary
# en test_coordinator.py). Valor elegido por el usuario tras confirmar
# que deja fuera a cualquier worker "rapido" normal conocido (el
# siguiente mejor, bryam-parrot, tiene 4.2 -- muy por debajo).
ELITE_WORKER_CPU_SCORE_THRESHOLD = 10.0


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
    tender a terminar en las maquinas rapidas sin bloquear a las lentas.

    Worker "elite" (cpu_score >= ELITE_WORKER_CPU_SCORE_THRESHOLD,
    2026-09-14): excepcion deliberada a "repeticiones en serie" para el
    puñado de workers realmente sobresalientes (hoy, solo "tania",
    cpu_score=18.07) -- en vez de fijar primero (repeticion, priority)
    como arriba, se busca directamente el job pendiente MAS PESADO de
    TODO el sistema (cualquier repeticion) que el worker pueda
    satisfacer por recursos. Pedido explicito del usuario: aprovechar
    que un worker asi de rapido se mantiene conectado toda la noche para
    asegurar avance en los jobs mas caros del barrido (GCR_He bin6/7),
    en vez de dejarlos sujetos al orden normal por repeticion. Un worker
    no-elite nunca ve este camino, asi que el fix de repeticiones en
    serie sigue intacto para todos los demas."""
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

        # worker["cpu_score"] es None (fallback "infinito" arriba, para no
        # bloquear min_cpu_score) se trata explicitamente como NO-elite --
        # un worker sin telemetria real de cpu_score no debe entrar a la
        # rama que salta el orden de repeticion, solo porque "infinito" es
        # matematicamente >= 10.0. Elite exige un cpu_score real medido.
        worker_is_elite = worker["cpu_score"] is not None and worker["cpu_score"] >= ELITE_WORKER_CPU_SCORE_THRESHOLD
        if worker_is_elite:
            # "Mas pesado" se mide por REFERENCE_TIMINGS_S real (segundos),
            # no por bin_index crudo -- GCR_He bin6 (~7321s) es mas pesado
            # que GCR_H bin7 (~4670s) pese a tener bin_index menor, asi que
            # esto no puede resolverse con un ORDER BY de SQL sobre
            # columnas de la tabla; se trae todo lo elegible (cualquier
            # repeticion) y se elige en Python, mismo criterio de peso que
            # pick_job_for_worker() usa dentro de un grupo.
            elite_candidates = conn.execute(
                """
                SELECT job_id, species, bin_index FROM jobs
                WHERE status='pending' AND min_cpu_count <= ? AND min_ram_gb <= ? AND min_cpu_score <= ?
                """,
                (worker["cpu_count"] or 0, available_ram or 0, worker_cpu_score),
            ).fetchall()
            job_id = pick_job_for_worker(elite_candidates, worker_cpu_score)
            if job_id is None:
                return None
        else:
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
            UPDATE jobs SET status='claimed', cancel_requested=0, log_requested=0, claimed_by=?, claimed_at=?, attempt=attempt+1, updated_at=?
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
            "UPDATE jobs SET status='claimed', cancel_requested=0, log_requested=0, claimed_by=?, claimed_at=?, attempt=attempt+1, updated_at=? "
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


def get_job_by_combo(species: str, phase: str, bin_index: int, offset_x_m: float, repeticion: int) -> sqlite3.Row | None:
    """Busca un job por su clave natural (mismo UNIQUE que insert_job(),
    ahora de 5 columnas con `phase`, 2026-09-16) en vez de por job_id --
    util para scripts administrativos (ej. import_local_results.py) que
    solo conocen la combinacion, no el id interno asignado al sembrarla."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE species=? AND phase=? AND bin_index=? AND ABS(offset_x_m - ?) < 1e-6 AND repeticion=?",
            (species, phase, bin_index, offset_x_m, repeticion),
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
        # cancel_requested tambien se limpia siempre aqui: el resultado ya
        # llego (cancelado o no), asi que la senal no debe seguir viva para
        # un futuro intento de este mismo job_id.
        conn.execute(
            "UPDATE jobs SET status=?, last_error=?, updated_at=?, cancel_requested=0, log_requested=0, "
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
        # cancel_requested se limpia aqui tambien -- un job cancelado
        # reportado como fallo (ver run_job() en worker.py) no debe seguir
        # con la senal encendida para el proximo intento.
        conn.execute(
            "UPDATE jobs SET status=?, last_error=?, updated_at=?, cancel_requested=0, log_requested=0, "
            "connected_s=CASE WHEN ?='pending' THEN 0 ELSE connected_s END WHERE job_id=?",
            (new_status, error, now_iso(), new_status, job_id),
        )
        return new_status


def request_job_cancel(job_id: int) -> str | None:
    """Marca un job para que el worker que lo tiene lo cancele a mitad de
    la corrida (ver auto_update()/heartbeat_loop() en worker.py -- la senal
    viaja en la respuesta del heartbeat, no por polling aparte). Accion
    administrativa (ver cancel_job.py), no algo que un worker llame.

    Devuelve el worker_id que va a recibir la senal, o None si el job no
    esta en un estado cancelable (no asignado, o ya resuelto)."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT status, claimed_by FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError(f"job {job_id} no existe")
        if job["status"] not in ("claimed", "running") or not job["claimed_by"]:
            return None
        conn.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
        return job["claimed_by"]


def cancelled_job_for_worker(conn, worker_id: str, active_job_id: int | None = None) -> int | None:
    """job_id si el job ACTUAL de ese worker (el que tiene
    'claimed'/'running' con claimed_by=worker_id) fue marcado para
    cancelar, None si no. Recibe una conexion existente -- se llama desde
    dentro de la transaccion de touch_heartbeat(), no abre la suya propia
    (evita un segundo round-trip a la DB en cada heartbeat, cada 30s por
    diseno). No limpia el flag (eso lo hace record_result()/
    record_failure() cuando el worker reporta el resultado real de
    haberlo cancelado) -- solo informa, para que heartbeat_loop() en el
    worker pueda avisar al hilo que corre el subprocess. active_job_id permite seleccionar la ejecucion local real aunque la DB
    conserve otra asignacion antigua. Sin el campo se conserva compatibilidad
    con clientes anteriores."""
    row = conn.execute(
        "SELECT job_id FROM jobs WHERE claimed_by=? AND status IN ('claimed','running') AND cancel_requested=1 AND (? IS NULL OR job_id=?) ORDER BY job_id",
        (worker_id, active_job_id, active_job_id),
    ).fetchone()
    return row["job_id"] if row else None


def request_job_log(job_id: int, detailed=False):
    """Marca un job para que el worker que lo tiene suba el tail de su log
    activo (ver "log bajo demanda", AGENTS.md 2026-09-16) -- mismo patron
    que request_job_cancel(): la senal viaja en la respuesta del proximo
    heartbeat, no por polling aparte, porque el worker esta detras de NAT
    sin puerto expuesto al coordinator. Accion administrativa/diagnostico
    (usada por un endpoint de operador o el dashboard), no algo que un
    worker llame.

    Devuelve el worker_id que va a recibir la solicitud, o None si el job
    no esta en un estado con worker activo."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT status, claimed_by, attempt FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError(f"job {job_id} no existe")
        if job["status"] not in ("claimed", "running") or not job["claimed_by"]:
            return None
        request_id = uuid.uuid4().hex
        conn.execute("UPDATE jobs SET log_requested=1, log_request_id=? WHERE job_id=?", (request_id, job_id))
        result = {"job_id": job_id, "claimed_by": job["claimed_by"], "attempt": job["attempt"], "request_id": request_id}
        return result if detailed else job["claimed_by"]


def log_requested_for_worker(conn, worker_id: str, active_job_id: int | None = None) -> bool:
    """True si el job ACTUAL de ese worker tiene un log pedido pendiente.
    Recibe una conexion existente -- se llama DENTRO de la transaccion de
    touch_heartbeat(), mismo motivo que cancelled_job_for_worker(). No
    limpia el flag (eso lo hace save_job_log_tail() cuando el worker
    efectivamente sube el log) -- solo informa."""
    row = conn.execute(
        "SELECT job_id FROM jobs WHERE claimed_by=? AND status IN ('claimed','running') "
        "AND log_requested=1 AND (? IS NULL OR job_id=?) ORDER BY job_id",
        (worker_id, active_job_id, active_job_id),
    ).fetchone()
    return row is not None


def save_job_log_tail(job_id: int, worker_id: str, log_tail: str, request_id=None, attempt=None) -> bool:
    """Guarda el tail de log subido por un worker y limpia log_requested.
    Rechaza (devuelve False) si el job ya no le pertenece a ese worker --
    mismo criterio de propiedad que record_result()/record_failure(), para
    que un worker reasignado por timeout que sube tarde no pueda pisar el
    log de un intento mas reciente."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE jobs SET log_tail=?, log_tail_updated_at=?, log_requested=0, log_received_id=?, log_attempt=? "
            "WHERE job_id=? AND claimed_by=? AND status IN ('claimed','running') AND attempt=? AND log_request_id=? AND log_requested=1",
            (log_tail, now_iso(), request_id, attempt, job_id, worker_id, attempt, request_id),
        )
        return cur.rowcount > 0


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

    Bug real de produccion encontrado 2026-09-16 (job 141 en "tania",
    GCR_He bin7 -- ver AGENTS.md): el WHERE de SQL exigia heartbeat
    VENCIDO (w.last_heartbeat < cutoff) antes de traer una fila a
    Python -- pero progress_exhausted es una condicion sobre
    connected_s, TOTALMENTE INDEPENDIENTE de si el heartbeat sigue
    vivo. heartbeat_loop() corre en su propio hilo daemon (ver
    worker.py) y sigue latiendo con normalidad aunque el hilo principal
    (process.communicate() bloqueando en el subprocess de Geant4) este
    genuinamente colgado -- un heartbeat vivo NO implica que el job
    avanza. Resultado real: ese job acumulo 10.1h conectado (682% del
    estimado, muy por encima de ESTIMATE_SAFETY_FACTOR=2.5x) sin
    reencolarse nunca, porque la fila jamas paso el filtro SQL para
    llegar a evaluarse en Python. Corregido: el WHERE ya NO filtra por
    heartbeat -- trae TODOS los jobs claimed/running (superconjunto
    completo, no acotado por edad de heartbeat) y deja que el filtro
    fino en Python evalue las dos condiciones independientes
    (progress_exhausted, abandoned) sobre cada fila sin excepcion. El
    costo extra de traer mas filas es despreciable (la cola tiene, como
    mucho, unos pocos jobs activos a la vez -- uno por worker
    conectado)."""
    with get_conn() as conn:
        candidates = conn.execute(
            """
            SELECT j.job_id, j.species, j.bin_index, j.connected_s,
                   w.last_heartbeat, w.cpu_score
            FROM jobs j
            LEFT JOIN workers w ON w.worker_id = j.claimed_by
            WHERE j.status IN ('claimed', 'running')
            """
        ).fetchall()
        now = time.time()
        job_ids = []
        reasons = {}
        for row in candidates:
            if row["last_heartbeat"] is None:
                job_ids.append(row["job_id"])
                reasons[row["job_id"]] = "sin worker/heartbeat registrado"
                continue
            last_heartbeat_s = datetime.fromisoformat(row["last_heartbeat"]).timestamp()
            age_s = now - last_heartbeat_s
            estimated_s = estimate_job_duration_s(row["species"], row["bin_index"], row["cpu_score"])
            progress_exhausted = estimated_s is not None and row["connected_s"] >= estimated_s * ESTIMATE_SAFETY_FACTOR
            abandoned = age_s >= _abandon_timeout_s(estimated_s)
            if progress_exhausted or abandoned:
                # Motivo real registrado por separado -- el bug de 2026-09-16
                # (ver arriba) mostro que "heartbeat vencido" generico era
                # enganoso: progress_exhausted puede dispararse con
                # heartbeat COMPLETAMENTE VIVO (heartbeat_loop en hilo
                # separado sigue latiendo aunque el trabajo real este
                # colgado), asi que el mensaje debe decir cual de las dos
                # condiciones independientes fue la que realmente actuo.
                reason = "progreso agotado (connected_s excede estimacion*margen)" if progress_exhausted else "heartbeat vencido (abandonado)"
                job_ids.append(row["job_id"])
                reasons[row["job_id"]] = reason
        for job_id in job_ids:
            # connected_s se resetea a 0: el proximo intento empieza su
            # propio progreso desde cero.
            conn.execute(
                """
                UPDATE jobs SET status=CASE WHEN attempt < max_attempts THEN 'pending' ELSE 'failed' END,
                       claimed_by=NULL, claimed_at=NULL, connected_s=0, cancel_requested=0, log_requested=0,
                       last_error=?, updated_at=?
                WHERE job_id=?
                """,
                (f"requeued: {reasons[job_id]}", now_iso(), job_id),
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


def insert_job(species: str, phase: str, bin_index: int, offset_x_m: float, repeticion: int,
               n_events: int, priority: int = 0, min_ram_gb: float = 0, min_cpu_count: int = 0,
               min_cpu_score: float = 0) -> int:
    """`phase` (min/max, 2026-09-16) es requerido, sin default -- forma
    parte del UNIQUE real (species, phase, bin_index, offset_x_m,
    repeticion), asi que un caller que "se olvide" de pasarlo y dependiera
    de un default silencioso terminaria con jobs de fases distintas
    colisionando bajo el mismo phase='' -- mejor que ese caso sea un
    TypeError inmediato al llamar, no un bug silencioso de datos."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO jobs (species, phase, bin_index, offset_x_m, repeticion, n_events, priority,
                               min_ram_gb, min_cpu_count, min_cpu_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(species, phase, bin_index, offset_x_m, repeticion) DO NOTHING
            """,
            (species, phase, bin_index, offset_x_m, repeticion, n_events, priority, min_ram_gb, min_cpu_count,
             min_cpu_score, now_iso(), now_iso()),
        )
        return cur.lastrowid
