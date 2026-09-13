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
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

import db
from models import FailIn, JobOut, WorkerRegister, WorkerRef

RESULTS_DIR = db.DB_PATH.parent / "results"

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


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row is not None else None


@app.post("/api/v1/workers/register")
def register_worker(body: WorkerRegister):
    db.upsert_worker(body.worker_id, body.hostname, body.cpu_count, body.ram_gb, body.label)
    return {"worker_id": body.worker_id, "status": "registered"}


@app.post("/api/v1/workers/{worker_id}/heartbeat")
def heartbeat(worker_id: str):
    ok = db.touch_heartbeat(worker_id)
    if not ok:
        raise HTTPException(404, f"worker {worker_id} no registrado")
    return {"ok": True}


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
    return [row_to_dict(r) for r in rows]


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
    }
