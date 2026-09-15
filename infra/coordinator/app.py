"""Coordinator FastAPI: cola de jobs para el barrido distribuido de
ActiveShield_Sim. Ver AGENTS.md, seccion "Computo distribuido", para el
diseno completo (por que el grano de un job es una sola combinacion
species/bin_index/offset_x_m, por que no hay S3, etc).

Correr localmente:
    cd infra/coordinator
    pip install -r requirements.txt
    uvicorn app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import os
import uuid
import shutil
import csv
import io
import math
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import db
from models import FailIn, HeartbeatIn, JobLogIn, JobOut, WorkerRegister, WorkerRef

RESULTS_DIR = db.DB_PATH.parent / "results"
DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"

# Token compartido simple: sin esto, cualquiera con la URL puede
# registrarse como worker o leer/escribir jobs -- ver AGENTS.md, riesgo
# aceptado explicitamente mientras el coordinator solo se comparte con
# companeros conocidos. WORKER_TOKEN vacio (default) desactiva la
# validacion por completo, para no romper el desarrollo/tests locales
# que no lo configuran -- en produccion real se fija por variable de
# entorno (ver infra/deploy/cloud-init-coordinator.yaml).
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")
_PUBLIC_PATHS = {"/api/v1/health", "/docs", "/openapi.json", "/redoc", "/dashboard"}

# Cada cuanto corre el barrido de reencolado de jobs con heartbeat vencido.
# No necesita ser frecuente: el timeout mismo (db.STALE_JOB_TIMEOUT_S) ya es
# de horas, así que barrer cada 5 min es más que suficiente resolución.
REQUEUE_SWEEP_INTERVAL_S = float(os.environ.get("REQUEUE_SWEEP_INTERVAL_S", "300"))


async def _requeue_sweep_loop():
    while True:
        await asyncio.sleep(REQUEUE_SWEEP_INTERVAL_S)
        try:
            requeued = db.requeue_stale_jobs()
            if requeued:
                print(f"[requeue] jobs reencolados por heartbeat vencido: {requeued}")
        except Exception as exc:  # nunca tumbar el loop de fondo por un error transitorio
            print(f"[requeue] error en barrido: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(_requeue_sweep_loop())
    yield
    task.cancel()


app = FastAPI(title="ActiveShield_Sim compute coordinator", lifespan=lifespan)


@app.middleware("http")
async def require_worker_token(request: Request, call_next):
    if not WORKER_TOKEN or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    if request.headers.get("X-Worker-Token") != WORKER_TOKEN:
        return JSONResponse(status_code=401, content={"detail": "missing or invalid X-Worker-Token"})
    return await call_next(request)


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row is not None else None


@app.get("/dashboard")
def dashboard():
    # Servido desde el mismo origen a proposito: un Artifact de Claude no
    # puede hacer fetch() cross-origin hacia este dominio (la CSP del
    # sandbox solo admite un allowlist fijo de CDNs, ver
    # infra/DASHBOARD_PLAN.md) -- este endpoint reemplaza ese enfoque
    # sirviendo la misma pagina desde aqui, donde /api/v1/* es same-origin
    # sin necesitar CORS.
    return FileResponse(DASHBOARD_PATH, media_type="text/html")


@app.post("/api/v1/workers/register")
def register_worker(body: WorkerRegister):
    db.upsert_worker(body.worker_id, body.hostname, body.cpu_count, body.ram_gb, body.label,
                      body.ram_free_gb, body.cpu_load_pct, body.cpu_score, body.image_digest)
    return {"worker_id": body.worker_id, "status": "registered"}


@app.post("/api/v1/workers/{worker_id}/heartbeat")
def heartbeat(worker_id: str, body: HeartbeatIn = HeartbeatIn()):
    result = db.touch_heartbeat(worker_id, body.ram_free_gb, body.cpu_load_pct, body.image_digest, body.active_job_id)
    if result is None:
        raise HTTPException(404, f"worker {worker_id} no registrado")
    # cancel_job_id/request_log viajan aqui (no en un endpoint de polling
    # aparte) porque el worker ya manda heartbeat cada 30s desde su propio
    # hilo, en paralelo al subprocess de Geant4 -- ver
    # heartbeat_loop()/run_job() en worker.py. request_log (2026-09-16,
    # "log bajo demanda"): un worker detras de NAT no puede recibir un
    # pedido directo del coordinator, asi que la solicitud viaja igual que
    # cancel_job_id -- el worker sube el tail con un POST aparte a
    # /jobs/{id}/log cuando ve este flag en true.
    return {"ok": True, **result}


@app.post("/api/v1/jobs/next", response_model=JobOut | None)
def next_job(body: dict):
    worker_id = body.get("worker_id")
    if not worker_id:
        raise HTTPException(422, "worker_id requerido")
    row = db.claim_next_job(worker_id)
    if row is None:
        return JSONResponse(status_code=204, content=None)
    return JobOut(**row_to_dict(row))


@app.post("/api/v1/jobs/{job_id}/start")
def start_job(job_id: int, body: WorkerRef):
    ok = db.mark_running(job_id, body.worker_id)
    if not ok:
        raise HTTPException(409, f"job {job_id} no esta en estado 'claimed'")
    return {"job_id": job_id, "status": "running"}


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    # Accion administrativa (ver cancel_job.py) -- ningun worker llama esto,
    # y a proposito NO se expone en dashboard.html (ver AGENTS.md). No mata
    # el subprocess aqui mismo -- solo marca la senal, que el worker
    # asignado recoge en su propio heartbeat (cada 30s, ya corriendo en
    # paralelo al subprocess via heartbeat_loop()) y actua desde ahi.
    try:
        claimed_by = db.request_job_cancel(job_id)
    except KeyError:
        raise HTTPException(404, f"job {job_id} no existe")
    if claimed_by is None:
        raise HTTPException(409, f"job {job_id} no esta 'claimed'/'running' con un worker asignado")
    return {"job_id": job_id, "claimed_by": claimed_by, "status": "cancel_requested"}


@app.post("/api/v1/jobs/{job_id}/request-log")
def request_job_log(job_id: int):
    # Accion administrativa/diagnostico (2026-09-16, ver AGENTS.md "los
    # logs no ayudan porque no muestran nada") -- mismo patron que
    # cancel_job(): no lee nada aqui mismo, solo marca la senal, que el
    # worker asignado recoge en su propio heartbeat y sube con un POST
    # aparte a /jobs/{id}/log.
    try:
        claimed_by = db.request_job_log(job_id, detailed=True)
    except KeyError:
        raise HTTPException(404, f"job {job_id} no existe")
    if claimed_by is None:
        raise HTTPException(409, f"job {job_id} no esta 'claimed'/'running' con un worker asignado")
    return {**claimed_by, "status": "log_requested"}


@app.post("/api/v1/jobs/{job_id}/log")
def submit_job_log(job_id: int, body: JobLogIn):
    # El worker sube esto en respuesta a request_log=true en su heartbeat
    # (ver heartbeat()/report_log() en worker.py) -- rechaza si el job ya
    # no le pertenece a ese worker (mismo criterio de propiedad que
    # submit_result()), para que una subida tardia de un worker reasignado
    # por timeout no pise el log de un intento mas reciente.
    ok = db.save_job_log_tail(job_id, body.worker_id, body.log_tail, body.request_id, body.attempt)
    if not ok:
        raise HTTPException(409, f"job {job_id} no esta 'claimed'/'running' con claimed_by={body.worker_id}")
    return {"job_id": job_id, "status": "log_saved"}


@app.post("/api/v1/jobs/{job_id}/result")
async def submit_result(
    job_id: int,
    worker_id: str = Form(...),
    exit_code: int = Form(...),
    duration_s: float = Form(...),
    results_csv: UploadFile = File(...),
    manifest_csv: UploadFile = File(...),
):
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job")
    results_bytes = await results_csv.read()
    manifest_bytes = await manifest_csv.read()
    try:
        rows = list(csv.DictReader(io.StringIO(results_bytes.decode("utf-8"))))
        manifest = list(csv.DictReader(io.StringIO(manifest_bytes.decode("utf-8"))))
        if not rows or len(manifest) != 1:
            raise ValueError("Require organ rows and exactly one manifest row")
        for row in rows + manifest:
            if (row["especie"] != job["species"] or int(row["bin_index"]) != job["bin_index"]
                    or int(row["repeticion"]) != job["repeticion"]
                    or not math.isclose(float(row["offset_x_m"]), job["offset_x_m"], abs_tol=1e-6)
                    or int(row.get("n_eventos", row.get("n_events", ""))) != job["n_events"]):
                raise ValueError("Result does not match assigned job")
        if int(manifest[0]["exit_code"]) != exit_code:
            raise ValueError("Exit code disagrees with manifest")
    except (UnicodeError, KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    # Each delivery gets distinct files: a rejected stale worker cannot
    # overwrite the files belonging to a successfully completed attempt.
    job_dir = RESULTS_DIR / f"job_{job_id}" / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    results_path = job_dir / "results.csv"
    manifest_path = job_dir / "manifest.csv"
    results_path.write_bytes(results_bytes)
    manifest_path.write_bytes(manifest_bytes)

    n_rows = max(0, sum(1 for _ in csv.reader(io.StringIO(results_bytes.decode("utf-8")))) - 1)

    try:
        status = db.record_result(
            job_id, worker_id, duration_s, exit_code, n_rows,
            str(results_path), str(manifest_path),
        )
    except KeyError:
        shutil.rmtree(job_dir)
        raise HTTPException(404, f"job {job_id} no existe")
    except PermissionError as exc:
        shutil.rmtree(job_dir)
        raise HTTPException(409, str(exc))

    return {"job_id": job_id, "status": status, "n_rows": n_rows}


@app.post("/api/v1/jobs/{job_id}/fail")
def fail_job(job_id: int, body: FailIn):
    try:
        status = db.record_failure(job_id, body.worker_id, body.error, body.duration_s)
    except KeyError:
        raise HTTPException(404, f"job {job_id} no existe")
    except PermissionError as exc:
        raise HTTPException(409, str(exc))
    return {"job_id": job_id, "status": status}


@app.get("/api/v1/jobs")
def get_jobs(status: str | None = None):
    rows = db.list_jobs(status)
    jobs = [row_to_dict(r) for r in rows]
    # estimated_duration_s solo tiene sentido para un job que ya tiene (o
    # tuvo) un worker asignado -- claimed/running (para saber cuanto
    # falta) y tambien done (para comparar contra actual_duration_s y ver
    # que tan buena fue la estimacion, pedido explicito del usuario
    # 2026-09-14: antes desaparecia justo al terminar el job, el momento
    # en que mas interesa compararla). None para pending/failed (nunca
    # tuvieron un worker real corriendolo), y tambien None si el worker
    # asignado no tiene cpu_score (version vieja del worker, o el
    # benchmark de arranque fallo, ver estimate_job_duration_s()) o no
    # hay referencia para esa especie/bin. claimed_by se conserva en la
    # fila incluso despues de 'done' (record_result() no lo limpia), asi
    # que sigue disponible para recalcular con el cpu_score ACTUAL de ese
    # worker -- no el que tenia en el momento exacto de la corrida, que
    # no se guarda por separado.
    worker_scores = {w["worker_id"]: w["cpu_score"] for w in db.list_workers()}
    for job in jobs:
        if job["status"] in ("claimed", "running", "done") and job["claimed_by"]:
            job["estimated_duration_s"] = db.estimate_job_duration_s(
                job["species"], job["bin_index"], worker_scores.get(job["claimed_by"])
            )
        else:
            job["estimated_duration_s"] = None
    return jobs


# Mismo umbral que count_workers_online() en db.py -- un worker con
# heartbeat mas viejo que esto se reporta offline aqui tambien, en vez de
# depender de la columna 'status' guardada (que nunca se pone a
# 'offline' por si sola, ver el bug documentado en AGENTS.md).
ONLINE_THRESHOLD_S = 300


@app.get("/api/v1/workers")
def get_workers():
    now = datetime.now(timezone.utc)
    out = []
    for r in db.list_workers():
        d = row_to_dict(r)
        # Calculado con el reloj del SERVIDOR, no el del cliente que
        # consulta este endpoint -- un instalador de Windows corriendo en
        # la PC de un voluntario no debe decidir "reciente" comparando el
        # timestamp del Coordinator contra su propio reloj local, que
        # puede estar desfasado (adelantado, atrasado, zona horaria mal
        # configurada). seconds_since_heartbeat/online ya vienen resueltos
        # aqui; quien consuma este endpoint solo debe leer ese campo.
        if d["last_heartbeat"]:
            heartbeat_dt = datetime.fromisoformat(d["last_heartbeat"])
            age_s = (now - heartbeat_dt).total_seconds()
        else:
            age_s = None
        d["seconds_since_heartbeat"] = age_s
        d["online"] = age_s is not None and age_s <= ONLINE_THRESHOLD_S
        out.append(d)
    return out


@app.get("/api/v1/health")
def health():
    counts = db.counts_by_status()
    return {
        "status": "ok",
        "jobs_pending": counts.get("pending", 0),
        "jobs_claimed": counts.get("claimed", 0),
        "jobs_running": counts.get("running", 0),
        "jobs_done": counts.get("done", 0),
        "jobs_failed": counts.get("failed", 0),
        "workers_online": db.count_workers_online(),
        # Expuesto para que el worker sepa hasta cuando vale la pena
        # seguir reintentando subir un resultado que quedo pendiente por
        # un corte de red (ver retry_pending_results() en worker.py) --
        # pasado este umbral desde el ultimo heartbeat exitoso, el
        # coordinator ya reencolo el job a otro worker, asi que insistir
        # en subirlo solo arriesgaria pisar un resultado ya aceptado.
        # Consultado en vivo en vez de duplicar el valor como una env var
        # separada en cada worker -- si alguien cambia
        # STALE_JOB_TIMEOUT_S en el coordinator, todos los workers lo ven
        # sin tener que reconfigurarse uno por uno.
        "stale_job_timeout_s": db.STALE_JOB_TIMEOUT_S,
        # Digest de imagen que el equipo quiere que TODOS los workers
        # Docker corran ahora mismo -- null si nunca se fijo (comportamiento
        # de siempre: cada worker se queda con la imagen que ya tiene).
        # Un worker Docker (ver auto_update() en worker.py) lo compara
        # contra su propio digest antes de pedir el siguiente job y se
        # auto-actualiza si difieren -- nunca a mitad de una simulacion.
        # Fijado con infra/coordinator/set_worker_image.py, no por HTTP
        # publico (mismo criterio que seed_jobs.py: no abrir esta
        # superficie sin autenticacion, ver AGENTS.md riesgos aceptados).
        "worker_image_digest": db.get_config("worker_image_digest") or None,
    }
