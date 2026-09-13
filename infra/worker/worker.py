#!/usr/bin/env python3
"""Worker de computo distribuido para el barrido de ActiveShield_Sim.

Hace poll al coordinator (infra/coordinator/), y por cada job recibido
--una sola combinacion (species, bin_index, offset_x_m, repeticion), ver
AGENTS.md "Computo distribuido"-- traduce sus columnas a una invocacion de
run_organ_sweep.py que aisla exactamente esa combinacion, corre el binario
ya compilado, filtra el CSV de resultados a solo las filas de este job (el
CSV se acumula entre jobs por el resume propio del script -- nunca subir
el archivo completo) y sube el resultado al coordinator.

Variables de entorno:
    COORDINATOR_URL   default http://localhost:8000
    BUILD_DIR         default <repo>/geant4/ActiveShield_Sim/build
    WORKER_LABEL      texto libre para identificar el worker en logs/DB
    WORKER_ID_FILE    default /var/lib/geant4-worker/worker_id (persistente
                      si esta ruta esta en un volumen montado; si no, se
                      genera un id nuevo en cada arranque -- aceptable, ver
                      AGENTS.md)
    POLL_INTERVAL_S   default 30 (segundos entre polls cuando no hay job)

Uso local (sin Docker, contra un build ya compilado):
    COORDINATOR_URL=http://localhost:8000 python3 infra/worker/worker.py
"""
import csv
import io
import json
import math
import multiprocessing
import os
import platform
import shutil
import subprocess
import threading
import tempfile
import signal
import sys
import time
import uuid
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_ORGAN_SWEEP = REPO_ROOT / "geant4" / "ActiveShield_Sim" / "scripts" / "run_organ_sweep.py"

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://localhost:8000").rstrip("/")
BUILD_DIR = Path(os.environ.get("BUILD_DIR", REPO_ROOT / "geant4" / "ActiveShield_Sim" / "build"))
WORKER_LABEL = os.environ.get("WORKER_LABEL", "")
WORKER_ID_FILE = Path(os.environ.get("WORKER_ID_FILE", "/var/lib/geant4-worker/worker_id"))
# Mismo directorio persistente que WORKER_ID_FILE (montado como volumen
# en Docker, ver GUIA_VOLUNTARIOS.md/GUIA_WORKER_LOCAL.md) -- resultados
# ya generados por una simulacion real se guardan aqui ANTES de intentar
# subirlos, y solo se borran despues de una subida confirmada. Bug real
# encontrado en produccion (2026-09-13): una corrida de horas termino
# exitosamente pero el resultado se perdio por completo porque vivia
# solo en un directorio temporal que se autoborraba al salir del "with",
# y una caida de red de varios minutos justo al momento de subir agoto
# los reintentos en memoria sin dejar nada recuperable. Este directorio
# sobrevive cualquier duracion de corte de red (y un reinicio del propio
# worker) -- ver retry_pending_results() en main(), que reintenta al
# arrancar cualquier resultado que quedo sin confirmar de una sesion
# anterior.
PENDING_RESULTS_DIR = WORKER_ID_FILE.parent / "pending_results"
HEARTBEAT_INTERVAL_S = float(os.environ.get("HEARTBEAT_INTERVAL_S", "30"))


def available_cpu_count() -> int:
    """CPUs realmente disponibles para este proceso -- a diferencia de
    os.cpu_count() (que siempre ve TODOS los CPUs del host, sin importar
    ninguna cuota de Docker), esto respeta un limite --cpus/-Cpus si
    existe. Verificado en vivo: con --cpus=2 sobre un host de 8 nucleos,
    os.cpu_count() seguia reportando 8 -- --cpus es una cuota de TIEMPO
    de CPU via cgroups, no una reduccion del numero de CPUs visibles al
    proceso, asi que hay que leer el cgroup mismo, no confiar en
    os.cpu_count(). Soporta cgroups v2 (cpu.max, la mayoria de Docker
    Desktop/hosts Linux modernos) y v1 (cfs_quota_us/cfs_period_us,
    hosts mas viejos) -- cae a os.cpu_count() si no hay limite
    ("max") o no se puede leer ningun cgroup (ej. corriendo sin Docker,
    ver GUIA_WORKER_LOCAL.md)."""
    try:
        cpu_max = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if cpu_max[0] != "max":
            quota, period = int(cpu_max[0]), int(cpu_max[1])
            return max(1, quota // period)
    except (FileNotFoundError, ValueError, IndexError):
        pass
    try:
        quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
        if quota > 0:
            return max(1, quota // period)
    except (FileNotFoundError, ValueError):
        pass
    return os.cpu_count() or 1


# Sin WORKER_THREADS explicito, usar los CPUs que este worker realmente
# tiene disponibles (ver available_cpu_count() arriba) -- no un numero
# fijo. Bug real corregido aqui (2026-09-13): el default anterior era
# "1" a secas, asi que cualquier voluntario que instalara sin pasar
# -WorkerThreads corria Geant4 en un solo nucleo sin importar cuantos
# tuviera la maquina -- confirmado en vivo con una PC de 16 nucleos al
# 100% en solo uno.
WORKER_THREADS = int(os.environ.get("WORKER_THREADS") or available_cpu_count())

# Numero de operaciones que hace CADA proceso del benchmark -- fijo, no
# depende del reloj, para que el trabajo realizado sea identico entre
# maquinas (lo unico que varia es cuanto tardan en hacerlo). Elegido
# para que el benchmark completo tome ~1-2s en una maquina tipica --
# ni tan corto que el ruido de arranque de multiprocessing.Pool domine
# la medicion, ni tan largo que retrase el registro del worker de forma
# notoria.
_BENCHMARK_ITERATIONS_PER_PROC = 3_000_000
# Score de una maquina de referencia (1 core, medido en esta sesion de
# Throughput de UN SOLO proceso (medido, no supuesto: ~4,77M ops/s con
# exactamente esta operacion, en la maquina donde se escribio este
# benchmark) -- normaliza el score reportado a un numero relativo, en
# vez de iteraciones/segundo crudas sin contexto. El score AGREGADO
# (todos los procesos, ver cpu_score()) de esa misma maquina de
# referencia dio ~5,7 con 8 cores, no ~8,0 -- procesos compitiendo por
# cache/scheduler no escalan 1:1 con el conteo de nucleos, ni deberian:
# esa perdida real de eficiencia bajo carga es precisamente lo que el
# benchmark multi-proceso existe para capturar (ver cpu_score()). No es
# una unidad fisica real ("N core-equivalentes"), solo una escala
# relativa pensada para comparar el score agregado de un worker contra
# el de otro, no para leerse como cores efectivos.
_BENCHMARK_REFERENCE_OPS_PER_SEC = 4_770_000.0


def _benchmark_worker_proc(n_iterations: int) -> int:
    """Trabajo de un solo proceso del benchmark -- aritmetica de punto
    flotante pura (sqrt/sin encadenados), sin numpy ni dependencias
    nuevas. Corre en un proceso hijo real (ver cpu_score() mas abajo,
    multiprocessing.Pool, NO threading) porque el GIL de Python
    serializaria cualquier intento de paralelismo con hilos en codigo
    Python puro -- el mismo tipo de bug que WORKER_THREADS tenia con
    Geant4, ahora evitado a proposito en el propio script de medicion."""
    x = 0.5
    for _ in range(n_iterations):
        x = math.sqrt(math.sin(x) ** 2 + 1.0)
    return n_iterations


def cpu_score() -> float | None:
    """Mide capacidad de computo real bajo carga MULTI-PROCESO (no solo
    un core aislado) -- corre WORKER_THREADS procesos simultaneos
    (multiprocessing.Pool, procesos reales sin GIL compartido) haciendo
    el mismo trabajo aritmetico fijo cada uno, y mide el throughput
    agregado real. Deliberadamente NO es single-thread: bajo carga
    sostenida con todos los nucleos ocupados a la vez (el escenario real
    de una corrida de Geant4 MT) entran en juego contencion de cache/
    memoria compartida y throttling termico que un benchmark de 1 solo
    core no capturaria -- justo lo que se necesita para comparar
    maquinas de forma representativa del uso real, no solo su pico
    teorico de un nucleo.

    Se corre UNA VEZ al arrancar el worker (no en cada heartbeat -- el
    hardware no cambia en caliente, repetirlo seria costo sin
    beneficio). Normalizado contra _BENCHMARK_REFERENCE_OPS_PER_SEC para
    dar un numero legible (~1.0 por core tipico), no iteraciones/segundo
    crudas sin contexto. None si el benchmark falla por cualquier razon
    (nunca debe impedir que el worker se registre y empiece a trabajar)."""
    try:
        n_procs = max(1, WORKER_THREADS)
        started = time.perf_counter()
        with multiprocessing.Pool(processes=n_procs) as pool:
            pool.map(_benchmark_worker_proc, [_BENCHMARK_ITERATIONS_PER_PROC] * n_procs)
        elapsed_s = time.perf_counter() - started
        if elapsed_s <= 0:
            return None
        total_ops = n_procs * _BENCHMARK_ITERATIONS_PER_PROC
        ops_per_sec = total_ops / elapsed_s
        return round(ops_per_sec / _BENCHMARK_REFERENCE_OPS_PER_SEC, 3)
    except Exception as exc:  # nunca bloquear el registro del worker por esto
        print(f"[worker] cpu_score() fallo, se registra sin score ({exc})")
        return None
POLL_INTERVAL_S = float(os.environ.get("POLL_INTERVAL_S", "30"))

# Sesion compartida: si el coordinator exige WORKER_TOKEN (ver app.py),
# el header se manda en TODAS las llamadas sin tener que acordarse de
# agregarlo a cada una por separado -- vacio por defecto, coherente con
# que el coordinator tampoco lo exige si no esta configurado.
SESSION = requests.Session()
if os.environ.get("WORKER_TOKEN"):
    SESSION.headers["X-Worker-Token"] = os.environ["WORKER_TOKEN"]

RESULTS_FIELDNAMES = ["especie", "fase", "bin_index", "energy_mev", "offset_x_m", "repeticion",
                       "organo_id", "edep_J", "dose_gy_run", "n_eventos"]


def get_or_create_worker_id() -> str:
    if WORKER_ID_FILE.is_file():
        return WORKER_ID_FILE.read_text().strip()
    worker_id = str(uuid.uuid4())
    try:
        WORKER_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKER_ID_FILE.write_text(worker_id)
    except OSError:
        print(f"[worker] no se pudo persistir worker_id en {WORKER_ID_FILE} -- se generara uno nuevo si se reinicia")
    return worker_id


def ram_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 2)
    except OSError:
        pass
    return 0.0


def ram_free_gb() -> float | None:
    # MemAvailable (no MemFree): es la estimacion del kernel de cuanta RAM
    # se puede dar a un proceso nuevo sin entrar a swap, contando cache/
    # buffers reclamables -- MemFree solo cuenta memoria totalmente sin
    # usar y subestima mucho lo realmente disponible en una maquina que
    # ya tiene cache de disco acumulado.
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 2)
    except OSError:
        pass
    return None


def cpu_load_pct() -> float | None:
    # Load average de 1 minuto normalizado por nucleos, como % -- no es
    # "uso de CPU instantaneo" (eso requeriria muestrear /proc/stat dos
    # veces con una pausa), pero alcanza para decidir si la maquina esta
    # genuinamente ocupada con otra cosa ahora mismo, sin dependencias
    # nuevas (psutil) para un dato que no necesita tanta precision.
    try:
        load1, _, _ = os.getloadavg()
        n_cpus = os.cpu_count() or 1
        return round(100.0 * load1 / n_cpus, 1)
    except OSError:
        return None


def register(worker_id: str) -> None:
    # cpu_count reportado usa available_cpu_count() (respeta --cpus/
    # -Cpus, ver esa funcion) -- bug real corregido junto con
    # WORKER_THREADS (2026-09-13): antes usaba os.cpu_count() a secas,
    # asi que un voluntario que limitara su worker con -Cpus 2 seguia
    # apareciendo en /workers con el total de nucleos de su maquina, no
    # los 2 que realmente le cedio al contenedor -- enganoso para
    # cualquiera decidiendo a quien asignar un job caro segun
    # min_cpu_count.
    cpus = available_cpu_count()
    print(f"[worker] midiendo capacidad de computo real ({cpus} procesos, ~1-2s)...")
    score = cpu_score()
    resp = SESSION.post(
        f"{COORDINATOR_URL}/api/v1/workers/register",
        json={
            "worker_id": worker_id,
            "hostname": platform.node(),
            "cpu_count": cpus,
            "ram_gb": ram_gb(),
            "label": WORKER_LABEL,
            "ram_free_gb": ram_free_gb(),
            "cpu_load_pct": cpu_load_pct(),
            "cpu_score": score,
        },
        timeout=15,
    )
    resp.raise_for_status()
    score_str = f"{score} score" if score is not None else "score no disponible"
    print(f"[worker] registrado como {worker_id} ({platform.node()}, {cpus} cpu, {ram_gb()} GB RAM, {score_str})")


def heartbeat(worker_id: str) -> None:
    try:
        SESSION.post(
            f"{COORDINATOR_URL}/api/v1/workers/{worker_id}/heartbeat",
            json={"ram_free_gb": ram_free_gb(), "cpu_load_pct": cpu_load_pct()},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[worker] heartbeat fallo (no fatal): {exc}")


def poll_next_job(worker_id: str) -> dict | None:
    resp = SESSION.post(f"{COORDINATOR_URL}/api/v1/jobs/next", json={"worker_id": worker_id}, timeout=15)
    if resp.status_code == 204:
        return None
    resp.raise_for_status()
    return resp.json()


def build_command(job: dict, build_dir=None) -> list[str]:
    # --only-bins/--only-species (agregados en run_organ_sweep.py el
    # 2026-09-12, ver AGENTS.md) dejan aislar exactamente una combinacion
    # de forma directa -- --limit 1 sigue como red de seguridad final.
    return [
        sys.executable, str(RUN_ORGAN_SWEEP),
        "--build-dir", str(build_dir or BUILD_DIR),
        "--only-species", job["species"],
        "--only-positions", f"{job['offset_x_m']:.3f}",
        "--only-bins", str(job["bin_index"]),
        "--limit", "1", "--repeats", "1",
        "--repetition-start", str(job["repeticion"]),
        "--threads", str(WORKER_THREADS), "--no-resume",
        "--n-events", str(job["n_events"]),
    ]


def filter_results_csv(job: dict, build_dir=None) -> str:
    """Lee build/resultados_organo_sweep.csv y devuelve solo las filas de
    este job como texto CSV. El archivo se acumula entre jobs (resume del
    propio script), asi que nunca se sube completo."""
    results_path = (build_dir or BUILD_DIR) / "resultados_organo_sweep.csv"
    if not results_path.is_file():
        return ""

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=RESULTS_FIELDNAMES)
    writer.writeheader()
    n_matched = 0
    with open(results_path, newline="") as f:
        for row in csv.DictReader(f):
            if (row["especie"] == job["species"]
                    and int(row["bin_index"]) == job["bin_index"]
                    and abs(float(row["offset_x_m"]) - job["offset_x_m"]) < 1e-6
                    and int(row["repeticion"]) == job["repeticion"]):
                writer.writerow(row)
                n_matched += 1
    print(f"[worker] {n_matched} fila(s) de organo encontradas para este job en {results_path.name}")
    return out.getvalue() if n_matched else ""


def read_manifest_csv(build_dir=None) -> str:
    manifest_path = (build_dir or BUILD_DIR) / "organ_sweep_manifest.csv"
    return manifest_path.read_text() if manifest_path.is_file() else ""


# Bug real encontrado en produccion (2026-09-13): una simulacion de
# GCR_H bin5 de varias horas termino exitosamente (142 filas de organo
# generadas, confirmadas en el log local) pero se PERDIO por completo --
# una caida de red justo al momento de subir el resultado hacia
# report_result() lanzaba requests.RequestException, que run_job()
# capturaba como si la simulacion misma hubiera fallado, sin ningun
# reintento de subida. El resultado real vivia SOLO en un directorio
# temporal (tempfile.TemporaryDirectory) que se borraba solo al salir
# del "with" -- para cuando se intentaba (sin exito, misma red caida)
# report_failure(), el CSV real ya no existia en disco.
#
# Corregido en dos capas, no solo reintentos en memoria (esos alcanzan
# para un corte de segundos, no para uno de varios minutos como el que
# causo esto): (1) el resultado se escribe a PENDING_RESULTS_DIR --
# directorio PERSISTENTE, mismo volumen que WORKER_ID_FILE -- ANTES de
# intentar subir nada, y solo se borra tras una subida confirmada; (2)
# reintentos con backoff cortos aqui mismo para el caso comun (corte
# breve, se resuelve en segundos sin que el resultado pase de "job en
# curso" a "pendiente en disco"). Si los reintentos cortos se agotan, el
# archivo YA esta a salvo en disco -- retry_pending_results() (llamado
# al arrancar el worker, y en cada iteracion del loop principal) lo
# reintenta despues, sin importar cuanto dure el corte ni si el propio
# worker se reinicia entre medio.
_REPORT_RESULT_BACKOFF_S = 15

# Umbral REAL de "ya es tarde para insistir" -- debe coincidir con
# STALE_JOB_TIMEOUT_S del coordinator (db.py), que reencola un job
# cuando pasan esas horas SIN HEARTBEAT del worker que lo tenia, no
# desde que el resultado quedo pendiente de subir. Consultado en vivo
# via GET /api/v1/health (nuevo campo stale_job_timeout_s) una sola vez
# al arrancar, en vez de una variable de entorno separada que alguien
# tendria que mantener sincronizada a mano con el coordinator -- si se
# cambia el timeout ahi, todos los workers lo ven solos. Fallback local
# (mismo default que db.py, 6h) solo si el coordinator no responde
# siquiera para esta consulta -- no hay forma de saber el valor real en
# ese caso, y no arrancar el worker por esto seria peor que asumir el
# default razonable.
_DEFAULT_STALE_JOB_TIMEOUT_S = 6 * 3600
_stale_job_timeout_s = None  # cache; ver get_stale_job_timeout_s()


def get_stale_job_timeout_s() -> float:
    global _stale_job_timeout_s
    if _stale_job_timeout_s is None:
        try:
            resp = SESSION.get(f"{COORDINATOR_URL}/api/v1/health", timeout=15)
            resp.raise_for_status()
            _stale_job_timeout_s = float(resp.json()["stale_job_timeout_s"])
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            print(f"[worker] no se pudo consultar stale_job_timeout_s al coordinator ({exc}) -- "
                  f"usando default local de {_DEFAULT_STALE_JOB_TIMEOUT_S}s.")
            _stale_job_timeout_s = float(_DEFAULT_STALE_JOB_TIMEOUT_S)
    return _stale_job_timeout_s


def _post_result(job_id: int, data: dict, files: dict) -> dict:
    resp = SESSION.post(f"{COORDINATOR_URL}/api/v1/jobs/{job_id}/result", data=data, files=files, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _save_pending_result(job_id: int, data: dict, results_csv_text: str, manifest_csv_text: str) -> Path:
    PENDING_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    job_dir = PENDING_RESULTS_DIR / str(job_id)
    job_dir.mkdir(exist_ok=True)
    # created_at es un timestamp ABSOLUTO (epoch, time.time()) -- no un
    # contador de intentos ni un backoff relativo. Lo que decide si vale
    # la pena seguir insistiendo es cuanto tiempo de reloj real paso
    # desde que el job dejo de tener heartbeat, comparado contra el
    # mismo umbral que usa el coordinator (ver get_stale_job_timeout_s())
    # -- eso vale igual si el worker sigue reintentando en el mismo
    # proceso o si se reinicio diez veces entre medio, algo que un
    # "numero de intentos" no puede expresar.
    data = dict(data, created_at=data.get("created_at", time.time()))
    (job_dir / "data.json").write_text(json.dumps(data))
    (job_dir / "results.csv").write_text(results_csv_text)
    (job_dir / "manifest.csv").write_text(manifest_csv_text)
    return job_dir


def report_result(worker_id: str, job_id: int, exit_code: int, duration_s: float,
                   results_csv_text: str, manifest_csv_text: str) -> None:
    data = {"worker_id": worker_id, "exit_code": str(exit_code), "duration_s": str(duration_s)}
    # Persistir PRIMERO, antes de cualquier intento de red -- si el
    # proceso se cae o se corta la luz a mitad de los reintentos de
    # abajo, el resultado ya esta a salvo en disco de todos modos.
    job_dir = _save_pending_result(job_id, data, results_csv_text, manifest_csv_text)
    deadline = json.loads((job_dir / "data.json").read_text())["created_at"] + get_stale_job_timeout_s()
    files = {
        "results_csv": ("results.csv", results_csv_text.encode("utf-8"), "text/csv"),
        "manifest_csv": ("manifest.csv", manifest_csv_text.encode("utf-8"), "text/csv"),
    }
    while True:
        try:
            result = _post_result(job_id, data, files)
            print(f"[worker] job {job_id} reportado: {result}")
            shutil.rmtree(job_dir, ignore_errors=True)
            return
        except (requests.ConnectionError, requests.Timeout) as exc:
            remaining = deadline - time.time()
            if remaining <= 0:
                print(f"[worker] job {job_id}: paso el umbral de {get_stale_job_timeout_s():.0f}s sin poder "
                      f"subir -- el coordinator ya reencolo este job a otro worker. El archivo queda en "
                      f"{job_dir} para inspeccion manual, retry_pending_results() ya no insistira con el.")
                return
            sleep_s = min(_REPORT_RESULT_BACKOFF_S, remaining)
            print(f"[worker] job {job_id}: fallo de red al subir el resultado, reintentando en {sleep_s:.0f}s "
                  f"(quedan ~{remaining/60:.0f} min antes de que el coordinator lo de por perdido): {exc}")
            time.sleep(sleep_s)


def retry_pending_results() -> None:
    """Reintenta subir cualquier resultado que quedo guardado en
    PENDING_RESULTS_DIR por un corte de red que supero los reintentos
    largos de report_result() (mas comun: el propio worker se reinicio a
    mitad de esos reintentos, ej. --restart unless-stopped de Docker
    tras un crash). Se llama al arrancar el worker y en cada vuelta del
    loop principal -- barata cuando el directorio esta vacio (el caso
    normal). El plazo se sigue midiendo desde el created_at ABSOLUTO
    guardado en data.json, no desde que arranca este proceso -- un
    worker que se reinicia varias veces durante el mismo corte de red
    sigue teniendo el plazo correcto, ni mas ni menos tiempo del que ya
    habia consumido antes de reiniciarse."""
    if not PENDING_RESULTS_DIR.is_dir():
        return
    for job_dir in sorted(PENDING_RESULTS_DIR.iterdir()):
        if not job_dir.is_dir():
            continue
        try:
            job_id = int(job_dir.name)
            data = json.loads((job_dir / "data.json").read_text())
            created_at = float(data["created_at"])
            results_csv_text = (job_dir / "results.csv").read_text()
            manifest_csv_text = (job_dir / "manifest.csv").read_text()
        except (ValueError, OSError, KeyError) as exc:
            print(f"[worker] {job_dir} no se pudo leer como resultado pendiente, se deja para revision manual: {exc}")
            continue

        deadline = created_at + get_stale_job_timeout_s()
        if time.time() > deadline:
            print(f"[worker] job {job_id} pendiente lleva mas de {get_stale_job_timeout_s():.0f}s sin poder "
                  "subirse -- el coordinator ya lo reencolo a otro worker, se descarta sin reintentar mas.")
            shutil.rmtree(job_dir, ignore_errors=True)
            continue

        files = {
            "results_csv": ("results.csv", results_csv_text.encode("utf-8"), "text/csv"),
            "manifest_csv": ("manifest.csv", manifest_csv_text.encode("utf-8"), "text/csv"),
        }
        try:
            result = _post_result(job_id, data, files)
            print(f"[worker] job {job_id} (pendiente de una caida de red anterior) reportado: {result}")
            shutil.rmtree(job_dir, ignore_errors=True)
        except requests.HTTPError as exc:
            # El coordinator lo rechaza de verdad (ej. otro worker ya lo
            # completo mientras este no tenia red, o el job ya no existe
            # en ese estado) -- no es un problema de red, reintentar no
            # lo arreglaria. Se descarta con un aviso explicito en vez de
            # reintentar para siempre un resultado que nunca sera aceptado.
            print(f"[worker] job {job_id} pendiente fue rechazado por el coordinator ({exc}) -- se descarta, "
                  "probablemente ya lo completo otro worker mientras este no tenia red.")
            shutil.rmtree(job_dir, ignore_errors=True)
        except requests.RequestException as exc:
            print(f"[worker] job {job_id} sigue sin poder subirse ({exc}), se reintentara en la proxima vuelta.")


def report_failure(worker_id: str, job_id: int, error: str, duration_s: float) -> None:
    try:
        resp = SESSION.post(
            f"{COORDINATOR_URL}/api/v1/jobs/{job_id}/fail",
            json={"worker_id": worker_id, "error": error[-2000:], "duration_s": duration_s},
            timeout=15,
        )
        resp.raise_for_status()
        print(f"[worker] job {job_id} marcado como fallido: {resp.json()}")
    except requests.RequestException as exc:
        print(f"[worker] no se pudo reportar el fallo del job {job_id} al coordinator: {exc}")


def run_job(worker_id: str, job: dict) -> None:
    job_id = job["job_id"]
    label = f"{job['species']} bin{job['bin_index']} offset_x_m={job['offset_x_m']}"
    print(f"[worker] job {job_id} ({label}) -- iniciando")

    try:
        resp = SESSION.post(f"{COORDINATOR_URL}/api/v1/jobs/{job_id}/start", json={"worker_id": worker_id}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[worker] no se pudo marcar 'running' el job {job_id} (se abandona esta asignacion): {exc}")
        return

    start = time.monotonic()
    try:
        # One private working directory per attempt: never overwrite a teammate's
        # CSV or reuse a completed job with a different event count.
        with tempfile.TemporaryDirectory(prefix="geant4-job-") as tmp:
            work = Path(tmp)
            for name in ("ICRP110phantoms", "ICRPdata", "ColourMap.dat", "male.in", "female.in",
                         "male_head.in", "female_head.in", "male_trunk.in", "female_trunk.in"):
                target = BUILD_DIR / name
                if target.exists():
                    (work / name).symlink_to(target.resolve())
            (work / "data").symlink_to(REPO_ROOT / "geant4/ActiveShield_Sim/data/sources/oltaris")
            cmd = build_command(job, work)
            print(f"[worker] comando: {' '.join(cmd)}", flush=True)
            # A process group lets a graceful Docker stop terminate the simulator
            # as well as its launcher. Docker kill removes the whole container.
            process = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, start_new_session=True)
            try:
                output, _ = process.communicate()
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
            duration = time.monotonic()-start
            if process.returncode:
                logs = list((work / "logs_organ").glob("*.log"))
                detail = logs[-1].read_text(errors="replace")[-4000:] if logs else ""
                raise RuntimeError(f"exit_code={process.returncode}\n{output[-1000:]}\n{detail}")
            results = filter_results_csv(job, work)
            if not results:
                raise RuntimeError("Simulation produced no rows matching this job")
            report_result(worker_id, job_id, 0, duration, results, read_manifest_csv(work))
    except (OSError, RuntimeError, requests.RequestException) as exc:
        report_failure(worker_id, job_id, str(exc), time.monotonic()-start)


def heartbeat_loop(worker_id, stop):
    while not stop.wait(HEARTBEAT_INTERVAL_S):
        heartbeat(worker_id)


def stop_worker(signum, frame):
    raise SystemExit(128+signum)


def main() -> None:
    if not RUN_ORGAN_SWEEP.is_file():
        sys.exit(f"ERROR: no se encontro {RUN_ORGAN_SWEEP} -- revisa que el repo este completo.")
    if not (BUILD_DIR / "ICRP110phantoms").is_file():
        sys.exit(f"ERROR: no se encontro el binario compilado en {BUILD_DIR}. "
                  "Compila ActiveShield_Sim primero (ver README.md / scripts/install_compute_node.sh).")

    if HEARTBEAT_INTERVAL_S <= 0 or POLL_INTERVAL_S <= 0 or WORKER_THREADS < 1:
        sys.exit("Intervals and WORKER_THREADS must be positive")
    signal.signal(signal.SIGTERM, stop_worker)
    worker_id = get_or_create_worker_id()
    register(worker_id)
    stop = threading.Event()
    threading.Thread(target=heartbeat_loop, args=(worker_id, stop), daemon=True).start()

    # Antes de pedir trabajo nuevo: si el worker se reinicio (crash,
    # --restart unless-stopped, actualizacion) mientras un resultado
    # seguia pendiente de subir por un corte de red, esta es la primera
    # oportunidad de retomarlo -- ver retry_pending_results().
    retry_pending_results()

    print(f"[worker] escuchando jobs en {COORDINATOR_URL} (poll cada {POLL_INTERVAL_S}s)")
    while True:
        try:
            job = poll_next_job(worker_id)
        except requests.RequestException as exc:
            print(f"[worker] error consultando el coordinator (reintentando): {exc}")
            time.sleep(POLL_INTERVAL_S)
            continue

        if job is None:
            heartbeat(worker_id)
            retry_pending_results()
            time.sleep(POLL_INTERVAL_S)
            continue

        run_job(worker_id, job)
        if os.environ.get("WORKER_ONCE") == "1":
            stop.set()
            return


if __name__ == "__main__":
    main()
