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
    DOCKER_SOCK_PATH  default /var/run/docker.sock (ver docker_client.py)
    WORKER_AUTO_UPDATE  default "1" -- "0" desactiva la auto-actualizacion
                      (ver auto_update()) sin tocar codigo. Solo aplica
                      dentro de Docker con el socket del host montado
                      (-v /var/run/docker.sock:/var/run/docker.sock); sin
                      eso, self_image_digest() da None y auto_update()
                      es no-op de todos modos.

Uso local (sin Docker, contra un build ya compilado):
    COORDINATOR_URL=http://localhost:8000 python3 infra/worker/worker.py
"""
import copy
import re
import fcntl
from contextlib import contextmanager

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

import docker_client

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

# Socket del host montado dentro del contenedor -- ver docker_client.py
# y auto_update() mas abajo. Ausente en la via sin Docker
# (GUIA_WORKER_LOCAL.md, donde no hay "propio contenedor" que recrear),
# asi que toda esta funcionalidad se vuelve no-op ahi, no un error.
DOCKER_SOCK_PATH = os.environ.get("DOCKER_SOCK_PATH", "/var/run/docker.sock")
DOCKER = docker_client.DockerClient(DOCKER_SOCK_PATH)


DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
UPDATE_PROTOCOL_LABEL = "org.iac.worker-update-protocol"
_UPDATE_RETRY_AFTER = 0.0

# Un contexto por invocacion, no un Event global reutilizado. Se captura ANTES
# de mandar cada heartbeat y se valida al recibirlo: una respuesta tardia no
# puede cancelar otro job ni un nuevo intento del mismo job_id.
_cancel_lock = threading.Lock()
_active_cancel = None
_CANCEL_GRACE_S = 2.0

# Log en vivo del job activo (2026-09-16, ver AGENTS.md "los logs no ayudan
# porque no muestran nada"): _active_log_path es la ruta REAL en disco del
# log de la corrida de Geant4 en curso (dentro del tempfile.TemporaryDirectory
# de _run_job(), sigue existiendo mientras el subprocess corre). Mismo
# patron de contexto por invocacion que _active_cancel -- se limpia al
# terminar cada job para que un heartbeat tardio nunca intente leer el log
# de una corrida ya finalizada/borrada.
_log_lock = threading.Lock()
_active_log_path = None
_LOG_TAIL_LINES = 40
_STALL_CHECK_INTERVAL_S = 30.0
# Cuanto tiempo sin que el log de Geant4 crezca ni un byte antes de asumir
# que el subprocess esta genuinamente colgado, no solo procesando un evento
# lento. Con /run/printProgress (ver run_organ_sweep.py) el log crece
# periodicamente durante una corrida normal, incluso las mas caras del
# barrido (GCR_He bin7, ~85min/corrida en la maquina de referencia) --
# 20 min sin ningun crecimiento es muchisimo mas generoso que el intervalo
# de progreso esperado, pero mucho mas corto que las horas que tardo en
# detectarse el caso real (tania, 10.1h) antes de este fix.
_STALL_TIMEOUT_S = 20.0 * 60.0


def deliver_cancellation(context, job_id):
    with _cancel_lock:
        if context is not None and context is _active_cancel and type(job_id) is int and job_id == context[0]:
            context[1].set()


def tail_log(path, n_lines=_LOG_TAIL_LINES):
    """Ultimas n_lines de un archivo de log, tolerante a que no exista
    todavia (el subprocess puede no haber escrito nada aun) o a que
    desaparezca a mitad de lectura (el TemporaryDirectory se borra al
    terminar el job -- una carrera real, no hipotetica, entre esta
    funcion y el cleanup de _run_job())."""
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n_lines:])
    except (FileNotFoundError, OSError):
        return None


def get_active_log_tail():
    """Ultimas lineas del log del job actualmente en ejecucion, o None si
    no hay ninguno activo -- usado tanto por el watchdog de progreso como
    por report_log() bajo demanda del coordinator (misma fuente, dos
    consumidores)."""
    with _log_lock:
        path = _active_log_path
    if path is None:
        return None
    return tail_log(path)


def terminate_process_group(process, grace_s):
    """Terminar tambien descendientes que conservan stdout abierto o ignoran TERM."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(min(.05, max(0, deadline - time.monotonic())))
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return True


def image_repository(reference: str) -> str:
    # Un puerto de registro (registry:5000/repo:tag) no es un tag.
    value = reference.split("@", 1)[0]
    head, slash, tail = value.rpartition("/")
    return (head + slash if slash else "") + tail.split(":", 1)[0]


def self_container_id() -> str | None:
    """No asumir hostname=ID: con red host puede ser el nombre de la PC.

    Docker monta sus archivos hostname/hosts/resolv.conf desde el directorio
    del contenedor. cgroup v1 es una alternativa; en v2 privado puede ser 0::/.
    Si no hay evidencia de ID, desactivar auto-update sin adivinar otro container.
    """
    try:
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            fields = line.split()
            if len(fields) > 4 and fields[4] in ('/etc/hostname', '/etc/hosts', '/etc/resolv.conf'):
                match = re.search(r'/containers/([0-9a-f]{64})/(?:hostname|hosts|resolv.conf)$', fields[3])
                if match:
                    return match.group(1)
    except OSError:
        pass
    try:
        match = re.search(r'/docker(?:/|-)([0-9a-f]{64})(?:\.scope)?(?:/|$)',
                          Path('/proc/self/cgroup').read_text(), re.MULTILINE)
        if match:
            return match.group(1)
    except OSError:
        pass
    hostname = platform.node()
    return hostname if re.fullmatch(r'[0-9a-f]{12}|[0-9a-f]{64}', hostname) else None


def self_image_digest() -> str | None:
    """Digest de manifiesto del registro; Docker inspect .Image es un CONFIG ID."""
    if not DOCKER.available():
        return None
    try:
        container_id = self_container_id()
        if container_id is None:
            return None
        info = DOCKER.inspect_container(container_id)
        reference = info["Config"]["Image"]
        # Docker resolvio/verifico esta referencia inmutable al crear el contenedor.
        if "@" in reference and DIGEST_RE.fullmatch(reference.rsplit("@", 1)[1]):
            return reference.rsplit("@", 1)[1]
        repo = image_repository(reference)
        digests = DOCKER.inspect_image(info["Image"]).get("RepoDigests", [])
        return next((ref.rsplit("@", 1)[1] for ref in digests
                     if ref.startswith(repo + "@")), None)
    except (docker_client.DockerAPIError, KeyError, ValueError, TypeError):
        return None


@contextmanager
def worker_lock():
    """Un solo proceso puede registrar, tocar el outbox o pedir jobs por volumen.

    flock se libera tambien con SIGKILL/reinicio. Nunca borrar este archivo:
    reemplazar su inode permitiria a dos procesos tener locks distintos.
    """
    WORKER_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with (WORKER_ID_FILE.parent / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def update_path(token: str, suffix: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Invalid update token")
    return WORKER_ID_FILE.parent / f"update-{token}.{suffix}"


def write_update_state(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def prepare_replacement() -> None:
    """Standby: heartbeat confirmado propio, sin register, outbox ni jobs.

    El padre autoriza el relevo en el volumen compartido. Luego worker_lock
    impide actividad hasta que el padre termine, incluso tras reinicios.
    """
    token = os.environ.get("WORKER_UPDATE_TOKEN")
    if not token:
        return
    state = json.loads(update_path(token, "request").read_text())
    if self_image_digest() != state["digest"]:
        raise RuntimeError("Replacement image does not match requested manifest")
    if WORKER_ID_FILE.read_text().strip() != state["worker_id"]:
        raise RuntimeError("Replacement does not share the worker identity volume")
    if update_path(token, "commit").exists():
        return  # reinicio de un reemplazo ya activado
    response = SESSION.post(
        f"{COORDINATOR_URL}/api/v1/workers/{state['worker_id']}/heartbeat",
        json={}, timeout=15)
    response.raise_for_status()
    write_update_state(update_path(token, "ready"), {
        "token": token, "container": self_container_id(),
        "worker_id": state["worker_id"], "digest": state["digest"],
    })
    deadline = time.monotonic() + _AUTO_UPDATE_VERIFY_TIMEOUT_S + 60
    while time.monotonic() < deadline:
        if update_path(token, "commit").exists():
            return
        time.sleep(1)
    raise RuntimeError("Replacement was never authorized; exiting without claiming jobs")


def recover_interrupted_update() -> bool:
    """Padre reiniciado tras un crash: deshacer preparacion o retirarse si hubo commit.

    No iniciar contenedores detenidos por el usuario; respetar su pausa.
    """
    if not DOCKER.available():
        return True
    try:
        container_id = self_container_id()
        if container_id is None:
            return True
        info = DOCKER.inspect_container(container_id)
        for request in WORKER_ID_FILE.parent.glob("update-*.request"):
            state = json.loads(request.read_text())
            if state["parent"] != info["Id"] or state.get("aborted"):
                continue
            token = request.name.removeprefix("update-").removesuffix(".request")
            if update_path(token, "commit").exists():
                DOCKER.set_restart_policy(info["Id"], {"Name": "no"})
                return False  # el candidato autorizado es el unico sucesor
            # Nombre determinista tambien permite limpiar si create dio timeout
            # antes de devolver el ID. Nunca tocar el padre ni borrar el volumen.
            DOCKER.remove_container(state.get("replacement", state["candidate_name"]), force=True)
            DOCKER.rename_container(info["Id"], state["original_name"])
            state["aborted"] = True
            write_update_state(request, state)
        return True
    except (OSError, ValueError, KeyError, docker_client.DockerAPIError) as exc:
        raise RuntimeError(f"Interrupted update needs recovery before claiming jobs: {exc}") from exc


def cleanup_retired_worker() -> None:
    token = os.environ.get("WORKER_UPDATE_TOKEN")
    if not token:
        return
    try:
        state = json.loads(update_path(token, "request").read_text())
        # Lock ya adquirido: el proceso viejo termino, pero Docker puede tardar
        # un instante en registrar exited. No forzar la eliminacion.
        for _ in range(10):
            if not DOCKER.is_running(state["parent"]):
                DOCKER.remove_container(state["parent"])
                return
            time.sleep(1)
    except (OSError, ValueError, docker_client.DockerAPIError) as exc:
        print(f"[worker] contenedor retirado pendiente de limpieza (sin restart): {exc}")


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
    digest = self_image_digest()
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
            "image_digest": digest,
        },
        timeout=15,
    )
    resp.raise_for_status()
    score_str = f"{score} score" if score is not None else "score no disponible"
    print(f"[worker] registrado como {worker_id} ({platform.node()}, {cpus} cpu, {ram_gb()} GB RAM, {score_str})")


def heartbeat(worker_id: str) -> int | None:
    """Devuelve el job_id que el coordinator pide cancelar (ver
    request_job_cancel() en db.py), o None si no hay ninguno / el
    heartbeat fallo. Un fallo de red aqui NO es motivo para cancelar nada
    -- solo se actua sobre una respuesta explicita del coordinator, nunca
    sobre silencio. Ademas, si la respuesta trae request_log=true (ver
    "log bajo demanda", AGENTS.md 2026-09-16), sube el tail del log
    activo con un segundo request aparte -- no en el mismo heartbeat, para
    no inflar cada request cuando nadie lo pidio (el caso comun)."""
    with _cancel_lock:
        active_job_id = _active_cancel[0] if _active_cancel is not None else None
    try:
        resp = SESSION.post(
            f"{COORDINATOR_URL}/api/v1/workers/{worker_id}/heartbeat",
            json={"ram_free_gb": ram_free_gb(), "cpu_load_pct": cpu_load_pct(), "active_job_id": active_job_id},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("request_log") and active_job_id is not None:
            report_log(worker_id, active_job_id)
        cancel_id = payload.get("cancel_job_id") if isinstance(payload, dict) else None
        return cancel_id if type(cancel_id) is int and cancel_id > 0 else None
    except (requests.RequestException, ValueError) as exc:
        print(f"[worker] heartbeat fallo (no fatal): {exc}")
        return None


def report_log(worker_id: str, job_id: int) -> None:
    """Sube el tail del log activo al coordinator, pedido explicitamente
    via el flag request_log del heartbeat -- ver "log bajo demanda",
    AGENTS.md 2026-09-16. Mejor esfuerzo: un fallo aqui no debe tumbar el
    heartbeat_loop ni afectar el job en curso, solo se pierde la
    oportunidad de reportar esta vez (se puede volver a pedir en el
    proximo heartbeat)."""
    tail = get_active_log_tail()
    if tail is None:
        return
    try:
        SESSION.post(
            f"{COORDINATOR_URL}/api/v1/jobs/{job_id}/log",
            json={"worker_id": worker_id, "log_tail": tail},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[worker] no se pudo subir el log del job {job_id} (no fatal): {exc}")


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
    if job_dir.exists():
        archive_pending_result(job_dir, "Entrada anterior preservada antes de guardar otra entrega del mismo job")
    job_dir.mkdir()
    # created_at es un timestamp ABSOLUTO (epoch, time.time()) -- no un
    # contador de intentos ni un backoff relativo. Lo que decide si vale
    # la pena seguir insistiendo es cuanto tiempo de reloj real paso
    # desde que se guardo el resultado, comparado contra el
    # mismo umbral que usa el coordinator (ver get_stale_job_timeout_s())
    # -- eso vale igual si el worker sigue reintentando en el mismo
    # proceso o si se reinicio diez veces entre medio, algo que un
    # "numero de intentos" no puede expresar.
    data = dict(data, created_at=data.get("created_at", time.time()))
    for name, text in (("results.csv", results_csv_text), ("manifest.csv", manifest_csv_text)):
        temporary = job_dir / (name + ".tmp")
        with temporary.open("w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(job_dir / name)
    write_update_state(job_dir / "data.json", data)
    return job_dir


def archive_pending_result(job_dir: Path, reason: str) -> None:
    """Conservar evidencia aunque el intento venza o el servidor lo rechace."""
    archive = PENDING_RESULTS_DIR.parent / "unconfirmed_results"
    archive.mkdir(parents=True, exist_ok=True)
    destination = archive / f"{job_dir.name}-{uuid.uuid4().hex}"
    job_dir.rename(destination)
    (destination / "reason.txt").write_text(reason)
    print(f"[worker] resultado conservado para revision: {destination} ({reason})")


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
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (400, 404, 409, 422):
                archive_pending_result(job_dir, f"HTTP {status}: {exc}")
            else:
                print(f"[worker] entrega pendiente tras HTTP {status}; datos conservados: {exc}")
            return
        except requests.RequestException as exc:
            remaining = deadline - time.time()
            if remaining <= 0:
                print(f"[worker] job {job_id}: paso el umbral de {get_stale_job_timeout_s():.0f}s sin poder "
                      f"subir; el estado remoto no se ha confirmado. El archivo queda en "
                      f"{job_dir} para inspeccion manual, retry_pending_results() ya no insistira con el.")
                return
            sleep_s = min(_REPORT_RESULT_BACKOFF_S, remaining)
            print(f"[worker] job {job_id}: fallo de red al subir el resultado, reintentando en {sleep_s:.0f}s "
                  f"(quedan ~{remaining/60:.0f} min de reintento local): {exc}")
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
            archive_pending_result(job_dir, "Plazo local vencido; estado del intento NO confirmado por el servidor")
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
            status = exc.response.status_code if exc.response is not None else None
            if status in (400, 404, 409, 422):
                archive_pending_result(job_dir, f"HTTP {status}: {exc}")
            else:
                print(f"[worker] HTTP {status}, conservando resultado pendiente para reintentar: {exc}")
        except requests.RequestException as exc:
            print(f"[worker] job {job_id} sigue sin poder subirse ({exc}), se reintentara en la proxima vuelta.")


def retry_pending_failures() -> bool:
    """No pedir otro job hasta confirmar el fallo, incluso tras reinicio/relevo."""
    directory = WORKER_ID_FILE.parent / "pending_failures"
    complete = True
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        job_id = data["job_id"]
        try:
            resp = SESSION.post(f"{COORDINATOR_URL}/api/v1/jobs/{job_id}/fail",
                                json=data["payload"], timeout=15)
            if resp.status_code not in (404, 409):
                resp.raise_for_status()
            # 409: ya no es nuestro intento activo, incluido ACK perdido.
            path.unlink()
        except requests.RequestException as exc:
            complete = False
            print(f"[worker] fallo de job {job_id} pendiente de confirmar: {exc}")
    return complete


def report_failure(worker_id: str, job_id: int, error: str, duration_s: float) -> None:
    directory = WORKER_ID_FILE.parent / "pending_failures"
    directory.mkdir(parents=True, exist_ok=True)
    write_update_state(directory / f"{job_id}.json", {
        "job_id": job_id,
        "payload": {"worker_id": worker_id, "error": error[-2000:], "duration_s": duration_s},
    })
    retry_pending_failures()


# Cuanto esperar a que el contenedor de reemplazo este 'running' segun
# Docker Y a que aparezca un heartbeat REAL de su worker_id en el
# coordinator, antes de dar la actualizacion por exitosa. Ver
# auto_update() -- las dos condiciones importan: 'running' solo confirma
# que el proceso arranco, no que worker.py de adentro no crasheo al
# inicializarse (ej. un bug real en la imagen nueva).
_AUTO_UPDATE_VERIFY_TIMEOUT_S = 120
_AUTO_UPDATE_VERIFY_POLL_S = 3
def get_desired_image_digest() -> str | None:
    """A diferencia de get_stale_job_timeout_s() (cacheado, se consulta
    una sola vez porque ese valor no cambia en la vida del proceso), este
    SI debe consultarse fresco cada vez -- es exactamente el valor que
    puede cambiar en cualquier momento (cuando el equipo publica una
    imagen nueva, ver set_worker_image.py) y que auto_update() necesita
    ver actualizado antes de cada job, no solo al arrancar."""
    try:
        resp = SESSION.get(f"{COORDINATOR_URL}/api/v1/health", timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("worker_image_digest") if isinstance(payload, dict) else None
    except (requests.RequestException, ValueError) as exc:
        print(f"[worker] no se pudo consultar worker_image_digest al coordinator ({exc}) -- se sigue con la imagen actual.")
        return None


def auto_update(worker_id: str) -> bool:
    """Transaccion local entre jobs. True pide salida limpia, nunca auto-SIGKILL.

    Solo imagenes con protocolo standby: el candidato no reclama jobs antes
    de commit + liberacion del lock. Un heartbeat del padre no confirma nada.
    """
    global _UPDATE_RETRY_AFTER
    if os.environ.get("WORKER_AUTO_UPDATE", "1") != "1" or time.monotonic() < _UPDATE_RETRY_AFTER:
        return False
    current_digest = self_image_digest()
    if current_digest is None:
        return False
    desired_digest = get_desired_image_digest()
    if not desired_digest or desired_digest == current_digest:
        return False
    if not isinstance(desired_digest, str) or not DIGEST_RE.fullmatch(desired_digest):
        print("[worker] digest deseado invalido; se conserva imagen actual")
        return False
    # No descargar repetidamente una imagen rota entre cada job/poll.
    _UPDATE_RETRY_AFTER = time.monotonic() + 300
    replacement_id = None
    renamed_parent = False
    committed = False
    token = uuid.uuid4().hex
    try:
        self_id = self_container_id()
        if self_id is None:
            return False
        info = DOCKER.inspect_container(self_id)
        # Exigir persistencia realmente compartida del directorio de identidad/outbox.
        data_path = str(WORKER_ID_FILE.parent)
        if not any(m.get("Type") in ("volume", "bind") and m.get("RW", True)
                   and (data_path == m["Destination"] or data_path.startswith(m["Destination"].rstrip("/") + "/"))
                   for m in info.get("Mounts", [])):
            raise RuntimeError("Auto-update requires a shared persistent worker data mount")
        if info["HostConfig"].get("AutoRemove"):
            raise RuntimeError("Auto-update does not support --rm containers")
        if info["HostConfig"].get("NetworkMode") not in ("default", "bridge", "host"):
            raise RuntimeError("Custom networking needs manual update (endpoints are not cloned)")
        original_image = DOCKER.inspect_image(info["Image"])
        # Engine puede omitir User en la imagen y devolver "" en el contenedor.
        # Normalizar defaults vacios sin aceptar overrides reales.
        if any((info["Config"].get(key) or None) != (original_image.get("Config", {}).get(key) or None)
               for key in ("Cmd", "Entrypoint", "User", "WorkingDir")):
            raise RuntimeError("Custom command/user/workdir requires manual update")
        image_repo = image_repository(info["Config"]["Image"])
        target = f"{image_repo}@{desired_digest}"
        DOCKER.pull_image(image_repo, desired_digest)
        target_info = DOCKER.inspect_image(target)
        target_labels = (target_info.get("Config") or {}).get("Labels") or {}
        if target_labels.get(UPDATE_PROTOCOL_LABEL) != "1":
            raise RuntimeError("Target image lacks standby update protocol 1; manual update required")
        original_name = info["Name"].lstrip("/")
        original_policy = info["HostConfig"].get("RestartPolicy", {"Name": "no"})
        host_config = copy.deepcopy(info["HostConfig"])
        host_config["RestartPolicy"] = {"Name": "no"}
        env = [value for value in info["Config"]["Env"] if not value.startswith("WORKER_UPDATE_")]
        env.append(f"WORKER_UPDATE_TOKEN={token}")
        request_state = {
            "parent": info["Id"], "worker_id": worker_id, "digest": desired_digest,
            "original_name": original_name, "candidate_name": f"{original_name}-update-{token[:8]}"}
        write_update_state(update_path(token, "request"), request_state)
        # Conservar el nombre incluso si create termina remotamente pero pierde su respuesta.
        replacement_id = request_state["candidate_name"]
        replacement_id = DOCKER.create_container(
            replacement_id, target, env, host_config,
            labels=info["Config"].get("Labels", {}))
        request_state["replacement"] = replacement_id
        write_update_state(update_path(token, "request"), request_state)
        DOCKER.start_container(replacement_id)
        deadline = time.monotonic() + _AUTO_UPDATE_VERIFY_TIMEOUT_S
        confirmed = False
        while time.monotonic() < deadline:
            if DOCKER.is_running(replacement_id) and update_path(token, "ready").is_file():
                ready = json.loads(update_path(token, "ready").read_text())
                confirmed = (ready.get("token") == token and ready.get("worker_id") == worker_id
                             and ready.get("digest") == desired_digest
                             and ready.get("container") in (replacement_id, replacement_id[:12]))
                if confirmed:
                    break
            time.sleep(_AUTO_UPDATE_VERIFY_POLL_S)
        if not confirmed:
            raise RuntimeError("Replacement did not acknowledge its own successful heartbeat")
        # Conservar restart del padre HASTA commit para recuperarse de un crash.
        # Conservar el nombre que usan
        # pause/resume/watchdog/uninstall, y luego habilitar al candidato.
        renamed_parent = True
        DOCKER.rename_container(self_id, f"{original_name}-retired-{token[:8]}")
        DOCKER.rename_container(replacement_id, original_name)
        DOCKER.set_restart_policy(replacement_id, original_policy)
        write_update_state(update_path(token, "commit"), {"committed": True})
        committed = True
        DOCKER.set_restart_policy(self_id, {"Name": "no"})
        print("[worker] reemplazo listo; saliendo limpiamente para liberar identidad y outbox")
        return True
    except (docker_client.DockerAPIError, OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        # replace(commit) puede haber tenido exito aunque falle el fsync del directorio.
        # Una vez visible el commit, nunca borrar al sucesor autorizado.
        committed = committed or update_path(token, "commit").exists()
        if committed:
            print(f"[worker] relevo autorizado; limpieza del padre pendiente: {exc}")
            return True
        print(f"[worker] auto-update cancelado: {exc}")
        # Mantener lock y worker viejo si falla la fase de preparacion.
        # Si una API de rollback falla, no seguir simulando en estado ambiguo.
        try:
            if replacement_id:
                DOCKER.remove_container(replacement_id, force=True)
            if renamed_parent:
                DOCKER.rename_container(self_id, original_name)
            if replacement_id:
                request_state["aborted"] = True
                write_update_state(update_path(token, "request"), request_state)
        except docker_client.DockerAPIError as rollback_error:
            raise RuntimeError(f"Update rollback needs operator intervention: {rollback_error}") from exc
        return False


def run_job(worker_id: str, job: dict) -> None:
    global _active_cancel
    context = (job["job_id"], threading.Event())
    with _cancel_lock:
        _active_cancel = context
    try:
        _run_job(worker_id, job, context[1])
    finally:
        with _cancel_lock:
            if _active_cancel is context:
                _active_cancel = None


def _run_job(worker_id: str, job: dict, cancel_event) -> None:
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
            # stdout redirigido a un archivo REAL en disco, no a un pipe
            # capturado en memoria (subprocess.PIPE + communicate() de antes)
            # -- un pipe solo entrega su contenido completo al terminar el
            # proceso, imposible de leer "ahora mismo" mientras sigue vivo.
            # Necesario para el watchdog de progreso y para report_log() bajo
            # demanda del coordinator (ver AGENTS.md "los logs no ayudan
            # porque no muestran nada", 2026-09-16) -- ambos necesitan leer
            # las ultimas lineas de un proceso EN CURSO, no solo al final.
            stdout_path = work / "worker_stdout.log"
            stdout_file = open(stdout_path, "w")
            process = subprocess.Popen(cmd, cwd=work, stdout=stdout_file,
                                       stderr=subprocess.STDOUT, text=True, start_new_session=True)
            cancelled = False
            stalled = False

            def _current_geant4_log_path():
                # El log real de la corrida de Geant4 (progreso por evento,
                # ver /run/printProgress en run_organ_sweep.py) lo escribe
                # run_organ_sweep.py -- no es el stdout de este subprocess
                # (que solo imprime un resumen por combinacion). Con
                # --limit 1 hay a lo sumo un archivo en logs_organ/; se
                # busca por directorio en vez de predecir el nombre exacto
                # (depende del indice interno del barrido, no vale la pena
                # duplicar esa logica aqui).
                candidates = sorted((work / "logs_organ").glob("*.log")) if (work / "logs_organ").is_dir() else []
                return candidates[-1] if candidates else stdout_path

            with _log_lock:
                global _active_log_path
                _active_log_path = _current_geant4_log_path()

            # Hilo watcher separado, mismo patron que heartbeat_loop(): solo
            # asi se puede reaccionar al Event de ESTA ejecucion MIENTRAS
            # process.communicate() bloquea el hilo principal. Se avisa a si
            # mismo con stop_watching cuando el job termina solo, para no
            # quedar corriendo de fondo despues (heartbeat_loop() sigue
            # corriendo entre jobs, pero este watcher es solo por job).
            # Ahora TAMBIEN vigila estancamiento de progreso (2026-09-16):
            # si el log de Geant4 no crece en _STALL_CHECK_INTERVAL_S*N
            # ciclos consecutivos, se asume colgado y se mata -- el worker
            # se auto-corrige sin depender de que el coordinator lo detecte
            # por connected_s (que puede tardar horas, ver el caso real de
            # tania en AGENTS.md) ni de que un operador lo note a mano.
            stop_watching = threading.Event()

            def _watch_for_cancel():
                nonlocal cancelled, stalled
                global _active_log_path
                last_size = -1
                stall_ticks = 0
                stall_ticks_needed = max(1, int(_STALL_TIMEOUT_S / _STALL_CHECK_INTERVAL_S))
                elapsed_ticks = 0
                while not stop_watching.wait(1.0):
                    if cancel_event.is_set():
                        cancelled = True
                        print(f"[worker] job {job_id} cancelado por el operador -- terminando el subprocess")
                        cancelled = terminate_process_group(process, _CANCEL_GRACE_S)
                        return
                    elapsed_ticks += 1
                    if elapsed_ticks % int(_STALL_CHECK_INTERVAL_S) != 0:
                        continue
                    with _log_lock:
                        log_path = _current_geant4_log_path()
                        _active_log_path = log_path
                    try:
                        size = log_path.stat().st_size
                    except (FileNotFoundError, OSError):
                        size = -1
                    if size == last_size and size >= 0:
                        stall_ticks += 1
                        if stall_ticks >= stall_ticks_needed:
                            stalled = True
                            print(f"[worker] job {job_id} sin progreso en el log por "
                                  f"{_STALL_TIMEOUT_S:.0f}s -- asumido colgado, terminando el subprocess")
                            terminate_process_group(process, _CANCEL_GRACE_S)
                            return
                    else:
                        stall_ticks = 0
                    last_size = size

            watcher = threading.Thread(target=_watch_for_cancel, daemon=True)
            watcher.start()
            try:
                process.wait()
            finally:
                stop_watching.set()
                watcher.join()  # watcher termina tras TERM + gracia acotada + KILL
                if process.poll() is None:
                    terminate_process_group(process, _CANCEL_GRACE_S)
                    process.wait()
                stdout_file.close()
                with _log_lock:
                    _active_log_path = None
            duration = time.monotonic()-start
            if cancelled:
                raise RuntimeError(f"cancelado por el operador (exit_code={process.returncode})")
            if stalled:
                tail = tail_log(_current_geant4_log_path()) or ""
                raise RuntimeError(f"sin progreso por {_STALL_TIMEOUT_S:.0f}s, terminado por el watchdog "
                                    f"(exit_code={process.returncode})\n{tail[-2000:]}")
            if process.returncode:
                logs = list((work / "logs_organ").glob("*.log"))
                detail = logs[-1].read_text(errors="replace")[-4000:] if logs else ""
                stdout_tail = tail_log(stdout_path) or ""
                raise RuntimeError(f"exit_code={process.returncode}\n{stdout_tail[-1000:]}\n{detail}")
            results = filter_results_csv(job, work)
            if not results:
                raise RuntimeError("Simulation produced no rows matching this job")
            report_result(worker_id, job_id, 0, duration, results, read_manifest_csv(work))
    except (OSError, RuntimeError, requests.RequestException) as exc:
        report_failure(worker_id, job_id, str(exc), time.monotonic()-start)


def heartbeat_loop(worker_id, stop):
    while not stop.wait(HEARTBEAT_INTERVAL_S):
        with _cancel_lock:
            context = _active_cancel
        cancel_id = heartbeat(worker_id)
        deliver_cancellation(context, cancel_id)


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
    if not recover_interrupted_update():
        return
    prepare_replacement()
    with worker_lock():
        cleanup_retired_worker()
        run_worker_loop()


def run_worker_loop() -> None:
    worker_id = get_or_create_worker_id()
    register(worker_id)
    stop = threading.Event()
    heartbeat_thread = threading.Thread(target=heartbeat_loop, args=(worker_id, stop), daemon=True)
    heartbeat_thread.start()
    try:
        # Antes de pedir trabajo nuevo: si el worker se reinicio (crash,
        # --restart unless-stopped, actualizacion) mientras un resultado
        # seguia pendiente de subir por un corte de red, esta es la primera
        # oportunidad de retomarlo -- ver retry_pending_results().
        retry_pending_results()

        print(f"[worker] escuchando jobs en {COORDINATOR_URL} (poll cada {POLL_INTERVAL_S}s)")
        while True:
            retry_pending_results()
            if not retry_pending_failures():
                time.sleep(POLL_INTERVAL_S)
                continue
            # Siempre ANTES de pedir el siguiente job, nunca a mitad de una
            # simulacion -- ver auto_update(). Si devuelve True, el
            # reemplazo ya esta corriendo y confirmado sano: este proceso
            # cede el puesto ahora mismo, sin pedir mas jobs ni mandar mas
            # heartbeats (seguiria compitiendo con el reemplazo por el mismo
            # worker_id si continuara).
            if os.environ.get("WORKER_AUTO_UPDATE", "1") == "1" and auto_update(worker_id):
                stop.set()
                return

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
    finally:
        stop.set()
        heartbeat_thread.join(timeout=20)


if __name__ == "__main__":
    main()
