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
import os
import platform
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
HEARTBEAT_INTERVAL_S = float(os.environ.get("HEARTBEAT_INTERVAL_S", "30"))
# Sin WORKER_THREADS explicito, usar TODOS los CPUs que este proceso ve
# -- os.cpu_count() dentro de un contenedor Docker refleja los CPUs que
# el propio Docker le asigno (todo el host, salvo que install-worker.ps1
# haya pasado --cpus), no un numero fijo. Bug real corregido aqui
# (2026-09-13): el default anterior era "1" a secas, asi que cualquier
# voluntario que instalara sin pasar -WorkerThreads corria Geant4 en un
# solo nucleo sin importar cuantos tuviera la maquina -- confirmado en
# vivo con una PC de 16 nucleos al 100% en solo uno.
WORKER_THREADS = int(os.environ.get("WORKER_THREADS") or (os.cpu_count() or 1))
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
    resp = SESSION.post(
        f"{COORDINATOR_URL}/api/v1/workers/register",
        json={
            "worker_id": worker_id,
            "hostname": platform.node(),
            "cpu_count": os.cpu_count() or 0,
            "ram_gb": ram_gb(),
            "label": WORKER_LABEL,
            "ram_free_gb": ram_free_gb(),
            "cpu_load_pct": cpu_load_pct(),
        },
        timeout=15,
    )
    resp.raise_for_status()
    print(f"[worker] registrado como {worker_id} ({platform.node()}, {os.cpu_count()} cpu, {ram_gb()} GB RAM)")


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


def report_result(worker_id: str, job_id: int, exit_code: int, duration_s: float,
                   results_csv_text: str, manifest_csv_text: str) -> None:
    files = {
        "results_csv": ("results.csv", results_csv_text.encode("utf-8"), "text/csv"),
        "manifest_csv": ("manifest.csv", manifest_csv_text.encode("utf-8"), "text/csv"),
    }
    data = {"worker_id": worker_id, "exit_code": str(exit_code), "duration_s": str(duration_s)}
    resp = SESSION.post(f"{COORDINATOR_URL}/api/v1/jobs/{job_id}/result", data=data, files=files, timeout=60)
    resp.raise_for_status()
    print(f"[worker] job {job_id} reportado: {resp.json()}")


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
            time.sleep(POLL_INTERVAL_S)
            continue

        run_job(worker_id, job)
        if os.environ.get("WORKER_ONCE") == "1":
            stop.set()
            return


if __name__ == "__main__":
    main()
