"""Tests basicos del coordinator: schema, claim atomico, ciclo pending->done,
y el timeout de heartbeat. Usa una DB SQLite temporal por test (no la de
produccion) via monkeypatch de db.DB_PATH.

Correr:
    cd infra/coordinator
    pip install -r requirements.txt pytest
    pytest test_coordinator.py -v
"""
import concurrent.futures
import time

import pytest

import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


def test_register_and_claim_single_job():
    db.upsert_worker("w1", "host1", 8, 16.0, "test")
    job_id = db.insert_job("SEP_p", 0, 0.0, 0, 100)
    assert job_id

    claimed = db.claim_next_job("w1")
    assert claimed is not None
    assert claimed["job_id"] == job_id
    assert claimed["status"] == "claimed"
    assert claimed["claimed_by"] == "w1"

    # ya no queda nada pendiente
    assert db.claim_next_job("w2") is None


def test_claim_is_atomic_under_concurrency():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    db.upsert_worker("w2", "h2", 8, 16.0, "")
    job_id = db.insert_job("SEP_p", 0, 0.0, 0, 100)
    assert job_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(db.claim_next_job, ["w1", "w2"]))

    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1, "exactamente un worker debe haber reclamado el job"


def test_full_cycle_pending_to_done():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    job_id = db.insert_job("GCR_He", 7, 3.0, 0, 10000, priority=10)

    job = db.claim_next_job("w1")
    assert job["job_id"] == job_id

    assert db.mark_running(job_id)

    status = db.record_result(job_id, "w1", duration_s=42.5, exit_code=0, n_rows=142,
                               results_csv_path="/tmp/r.csv", manifest_csv_path="/tmp/m.csv")
    assert status == "done"

    jobs_done = db.list_jobs(status="done")
    assert len(jobs_done) == 1
    assert jobs_done[0]["job_id"] == job_id


def test_failed_result_requeues_until_max_attempts():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    job_id = db.insert_job("SEP_p", 0, 0.0, 0, 100)

    for _ in range(3):  # max_attempts default = 3
        job = db.claim_next_job("w1")
        assert job is not None
        status = db.record_result(job_id, "w1", duration_s=1.0, exit_code=1, n_rows=0,
                                   results_csv_path="/tmp/r.csv", manifest_csv_path="/tmp/m.csv")

    assert status == "failed"
    assert db.claim_next_job("w1") is None  # ya no se reencola mas


def test_result_rejected_if_not_claimed_by_that_worker():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    db.upsert_worker("w2", "h2", 8, 16.0, "")
    job_id = db.insert_job("SEP_p", 0, 0.0, 0, 100)
    db.claim_next_job("w1")

    with pytest.raises(PermissionError):
        db.record_result(job_id, "w2", duration_s=1.0, exit_code=0, n_rows=1,
                          results_csv_path="/tmp/r.csv", manifest_csv_path="/tmp/m.csv")


def test_requeue_stale_jobs_without_heartbeat():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    job_id = db.insert_job("SEP_p", 0, 0.0, 0, 100)
    db.claim_next_job("w1")

    # Heartbeat "vencido": se fuerza escribiendo un valor viejo directo en DB
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='w1'", ("2000-01-01T00:00:00+00:00",))

    requeued = db.requeue_stale_jobs()
    assert job_id in requeued

    job = db.get_job(job_id)
    assert job["status"] == "pending"
    assert job["claimed_by"] is None


def test_unique_constraint_prevents_duplicate_job():
    first = db.insert_job("GCR_H", 2, 1.0, 0, 10000)
    second = db.insert_job("GCR_H", 2, 1.0, 0, 10000)  # misma combinacion exacta
    assert first
    assert second is None or second == 0  # lastrowid no cambia si ON CONFLICT DO NOTHING no inserto
    assert len(db.list_jobs()) == 1


def test_expired_job_exhausts_attempts():
    db.upsert_worker('w', 'host', 1, 1, '')
    job = db.insert_job('SEP_p', 1, 1., 0, 100)
    for attempt in range(3):
        assert db.claim_next_job('w')['job_id'] == job
        with db.get_conn() as conn:
            conn.execute("UPDATE workers SET last_heartbeat='2000-01-01T00:00:00+00:00'")
        db.requeue_stale_jobs()
    assert db.get_job(job)['status'] == 'failed'


def test_late_upload_cannot_overwrite_accepted_result(tmp_path, monkeypatch):
    import asyncio
    import io
    from fastapi import UploadFile, HTTPException
    import app
    monkeypatch.setattr(app, 'RESULTS_DIR', tmp_path/'results')
    db.upsert_worker('winner', 'host', 1, 1, '')
    job = db.insert_job('SEP_p', 1, 1., 0, 100)
    db.claim_next_job('winner')
    results = b'especie,bin_index,offset_x_m,repeticion,n_eventos\nSEP_p,1,1,0,100\n'
    manifest = b'especie,bin_index,offset_x_m,repeticion,n_events,exit_code\nSEP_p,1,1,0,100,0\n'
    def upload(data):
        file = io.BytesIO(data)
        file._rolled = False  # same in-memory path as Starlette's spooled HTTP upload
        return UploadFile(file=file)
    def send(worker):
        return asyncio.run(app.submit_result(job, worker, 0, 1.,
            upload(results), upload(manifest)))
    assert send('winner')['status'] == 'done'
    original = list((tmp_path/'results').rglob('results.csv'))
    with pytest.raises(HTTPException) as error:
        send('late-worker')
    assert error.value.status_code == 409
    assert list((tmp_path/'results').rglob('results.csv')) == original
    assert original[0].read_bytes() == results


def test_start_requires_assigned_worker():
    db.upsert_worker('owner', 'host', 1, 1, '')
    job = db.insert_job('SEP_p', 1, 1., 0, 100)
    db.claim_next_job('owner')
    assert not db.mark_running(job, 'someone-else')
    assert db.mark_running(job, 'owner')
