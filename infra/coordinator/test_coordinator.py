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
from datetime import datetime, timezone

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
    assert jobs_done[0]["actual_duration_s"] == pytest.approx(42.5)


def test_list_jobs_actual_duration_uses_most_recent_result():
    # Un job puede tener varios intentos (results tiene una fila por
    # intento, exitoso o no) -- actual_duration_s debe ser el de la
    # subida MAS RECIENTE (submitted_at), que es la que corresponde al
    # estado actual del job, no la primera fila insertada.
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    job_id = db.insert_job("SEP_p", 2, 0.0, 0, 100)

    db.claim_next_job("w1")
    db.record_result(job_id, "w1", duration_s=5.0, exit_code=1, n_rows=0,
                      results_csv_path="/tmp/r1.csv", manifest_csv_path="/tmp/m1.csv")  # falla, vuelve a pending

    db.claim_next_job("w1")
    db.record_result(job_id, "w1", duration_s=9.7, exit_code=0, n_rows=142,
                      results_csv_path="/tmp/r2.csv", manifest_csv_path="/tmp/m2.csv")  # exito

    job = db.list_jobs(status="done")[0]
    assert job["actual_duration_s"] == pytest.approx(9.7)


def test_list_jobs_actual_duration_none_without_any_result():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    db.insert_job("SEP_p", 2, 0.0, 0, 100)
    job = db.list_jobs(status="pending")[0]
    assert job["actual_duration_s"] is None


def test_claim_prefers_lower_repetition_over_higher_priority():
    # Repeticiones en serie (decision de equipo, 2026-09-14): un job de
    # repeticion 1 con prioridad alta NO debe ganarle a uno de repeticion
    # 0 con prioridad baja -- la serie completa. Reproduce el bug real
    # encontrado en produccion: repeticiones 1-4 arrancaban en paralelo
    # mientras la 0 seguia con trabajo pendiente.
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    low_rep_low_priority = db.insert_job("GCR_H", 0, 0.0, 0, 10000, priority=0)
    db.insert_job("GCR_He", 7, 0.0, 1, 10000, priority=20)

    job = db.claim_next_job("w1")
    assert job["job_id"] == low_rep_low_priority
    assert job["repeticion"] == 0


def test_claim_still_orders_by_priority_within_same_repetition():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    db.insert_job("GCR_H", 0, 0.0, 0, 10000, priority=0)
    high_priority_same_rep = db.insert_job("GCR_He", 7, 0.0, 0, 10000, priority=20)

    job = db.claim_next_job("w1")
    assert job["job_id"] == high_priority_same_rep


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


def test_estimate_job_duration_scales_by_cpu_score():
    reference_s = db.REFERENCE_TIMINGS_S[("GCR_H", 3)]
    # Worker con la mitad de cpu_score que la referencia -> tarda el doble.
    half_score = db.REFERENCE_CPU_SCORE / 2
    estimated = db.estimate_job_duration_s("GCR_H", 3, half_score)
    assert estimated == pytest.approx(reference_s * 2, rel=1e-6)


def test_estimate_job_duration_none_without_cpu_score():
    assert db.estimate_job_duration_s("GCR_H", 3, None) is None
    assert db.estimate_job_duration_s("GCR_H", 3, 0) is None


def test_estimate_job_duration_none_for_unknown_combo():
    assert db.estimate_job_duration_s("GCR_H", 99, db.REFERENCE_CPU_SCORE) is None


def test_requeue_respects_estimated_duration_beyond_fixed_timeout(monkeypatch):
    # Timeout fijo corto a proposito para poder probar sin esperar horas
    # reales -- la estimacion (bin7, referencia ~4669.7s) con margen de
    # seguridad debe seguir protegiendo al job aunque ya haya pasado el
    # piso fijo de 100s.
    monkeypatch.setattr(db, "STALE_JOB_TIMEOUT_S", 100.0)
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    job_id = db.insert_job("GCR_H", 7, 0.0, 0, 10000)
    db.claim_next_job("fast")

    # Heartbeat vencido hace 200s -- ya paso el piso fijo (100s) pero no el
    # timeout estimado (referencia ~4669.7s * ESTIMATE_SAFETY_FACTOR).
    stale_at = datetime.fromtimestamp(time.time() - 200, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='fast'", (stale_at,))

    requeued = db.requeue_stale_jobs()
    assert job_id not in requeued
    assert db.get_job(job_id)["status"] == "claimed"


def test_requeue_still_uses_fixed_floor_when_estimate_is_short(monkeypatch):
    # Job barato (bin0) en un worker rapido -- la estimacion con margen es
    # mucho menor que el piso fijo, asi que el piso fijo debe seguir
    # aplicando (no reencolar antes de tiempo solo porque la estimacion es
    # corta).
    monkeypatch.setattr(db, "STALE_JOB_TIMEOUT_S", 5.0)
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    job_id = db.insert_job("GCR_H", 0, 0.0, 0, 10000)
    db.claim_next_job("fast")

    stale_at = datetime.fromtimestamp(time.time() - 2, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='fast'", (stale_at,))

    requeued = db.requeue_stale_jobs()
    assert job_id not in requeued  # 2s de heartbeat vencido < piso fijo de 5s


def test_requeue_falls_back_to_fixed_timeout_without_cpu_score():
    db.upsert_worker("w1", "h1", 8, 16.0, "")  # sin cpu_score
    job_id = db.insert_job("GCR_H", 7, 0.0, 0, 10000)
    db.claim_next_job("w1")

    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='w1'", ("2000-01-01T00:00:00+00:00",))

    requeued = db.requeue_stale_jobs()
    assert job_id in requeued  # sin cpu_score, cae al timeout fijo (ya vencido)


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


def test_worker_below_min_ram_does_not_get_job():
    db.upsert_worker('small', 'host', 8, 4.0, '', ram_free_gb=1.0, cpu_load_pct=5.0)
    job_id = db.insert_job('GCR_He', 7, 3.0, 0, 10000, min_ram_gb=8.0)
    assert db.claim_next_job('small') is None
    assert db.get_job(job_id)['status'] == 'pending'


def test_worker_below_min_cpu_does_not_get_job():
    db.upsert_worker('weak', 'host', 2, 16.0, '', ram_free_gb=16.0)
    db.insert_job('GCR_He', 7, 3.0, 0, 10000, min_cpu_count=4)
    assert db.claim_next_job('weak') is None


def test_worker_meeting_requirements_gets_job():
    db.upsert_worker('strong', 'host', 16, 32.0, '', ram_free_gb=20.0, cpu_load_pct=10.0)
    job_id = db.insert_job('GCR_He', 7, 3.0, 0, 10000, min_ram_gb=8.0, min_cpu_count=4)
    claimed = db.claim_next_job('strong')
    assert claimed is not None
    assert claimed['job_id'] == job_id


def test_worker_without_telemetry_falls_back_to_total_ram():
    # Registrado sin ram_free_gb (worker viejo o metrica no disponible) --
    # no debe bloquear jobs sin requisitos, cae a ram_gb total.
    db.upsert_worker('legacy', 'host', 8, 16.0, '')
    job_id = db.insert_job('SEP_p', 1, 1.0, 0, 100, min_ram_gb=8.0)
    claimed = db.claim_next_job('legacy')
    assert claimed is not None
    assert claimed['job_id'] == job_id


def test_worker_below_min_cpu_score_does_not_get_job():
    # cpu_score mide capacidad de computo REAL (benchmark, ver cpu_score()
    # en worker.py) -- una maquina puede tener muchos nucleos (cpu_count
    # alto) pero ser lenta por core (VM compartida, CPU vieja); esto
    # existe justamente para no confundir "muchos nucleos" con "rapido".
    db.upsert_worker('many_cores_slow', 'host', 16, 16.0, '', ram_free_gb=16.0, cpu_score=0.3)
    db.insert_job('GCR_He', 7, 3.0, 0, 10000, min_cpu_score=1.0)
    assert db.claim_next_job('many_cores_slow') is None


def test_worker_meeting_cpu_score_gets_job():
    db.upsert_worker('fast', 'host', 8, 16.0, '', ram_free_gb=16.0, cpu_score=1.5)
    job_id = db.insert_job('GCR_He', 7, 3.0, 0, 10000, min_cpu_score=1.0)
    claimed = db.claim_next_job('fast')
    assert claimed is not None
    assert claimed['job_id'] == job_id


def test_worker_without_cpu_score_is_not_blocked():
    # Sin cpu_score (worker de antes de este cambio, o el benchmark del
    # propio worker fallo) -- no debe bloquear un job con min_cpu_score,
    # mismo criterio que ram_free_gb ausente cae a ram_gb total.
    db.upsert_worker('no_score', 'host', 8, 16.0, '', ram_free_gb=16.0)
    job_id = db.insert_job('GCR_He', 7, 3.0, 0, 10000, min_cpu_score=1.0)
    claimed = db.claim_next_job('no_score')
    assert claimed is not None
    assert claimed['job_id'] == job_id


def test_heartbeat_updates_live_telemetry():
    db.upsert_worker('w', 'host', 8, 16.0, '', ram_free_gb=10.0, cpu_load_pct=20.0)
    db.touch_heartbeat('w', ram_free_gb=2.0, cpu_load_pct=90.0)
    workers = db.list_workers()
    assert len(workers) == 1
    assert workers[0]['ram_free_gb'] == 2.0
    assert workers[0]['cpu_load_pct'] == 90.0


def test_heartbeat_without_telemetry_keeps_previous_values():
    db.upsert_worker('w', 'host', 8, 16.0, '', ram_free_gb=10.0, cpu_load_pct=20.0)
    db.touch_heartbeat('w')  # sin telemetria nueva -- no debe borrar la anterior
    workers = db.list_workers()
    assert workers[0]['ram_free_gb'] == 10.0
    assert workers[0]['cpu_load_pct'] == 20.0


def test_config_roundtrip():
    assert db.get_config('worker_image_digest') is None
    db.set_config('worker_image_digest', 'sha256:' + 'a' * 64)
    assert db.get_config('worker_image_digest') == 'sha256:' + 'a' * 64


def test_config_overwrite():
    db.set_config('worker_image_digest', 'sha256:' + 'a' * 64)
    db.set_config('worker_image_digest', 'sha256:' + 'b' * 64)
    assert db.get_config('worker_image_digest') == 'sha256:' + 'b' * 64


def test_worker_reports_image_digest_on_register_and_heartbeat():
    db.upsert_worker('w', 'host', 8, 16.0, '', image_digest='sha256:' + 'a' * 64)
    assert db.list_workers()[0]['image_digest'] == 'sha256:' + 'a' * 64
    db.touch_heartbeat('w', image_digest='sha256:' + 'b' * 64)
    assert db.list_workers()[0]['image_digest'] == 'sha256:' + 'b' * 64


def test_heartbeat_without_image_digest_keeps_previous_value():
    db.upsert_worker('w', 'host', 8, 16.0, '', image_digest='sha256:' + 'a' * 64)
    db.touch_heartbeat('w')  # sin image_digest nuevo -- no debe borrar el anterior
    assert db.list_workers()[0]['image_digest'] == 'sha256:' + 'a' * 64


class _FakeRequest:
    def __init__(self, path, headers=None):
        self.url = type('U', (), {'path': path})()
        self.headers = headers or {}


async def _ok(request):
    return 'ok'


def test_token_middleware_disabled_when_token_unset(monkeypatch):
    import asyncio
    import app
    monkeypatch.setattr(app, 'WORKER_TOKEN', '')
    resp = asyncio.run(app.require_worker_token(_FakeRequest('/api/v1/jobs'), _ok))
    assert resp == 'ok'


def test_token_middleware_rejects_missing_header(monkeypatch):
    import asyncio
    import app
    monkeypatch.setattr(app, 'WORKER_TOKEN', 'secret123')
    resp = asyncio.run(app.require_worker_token(_FakeRequest('/api/v1/jobs'), _ok))
    assert resp.status_code == 401


def test_token_middleware_accepts_correct_header(monkeypatch):
    import asyncio
    import app
    monkeypatch.setattr(app, 'WORKER_TOKEN', 'secret123')
    req = _FakeRequest('/api/v1/jobs', headers={'X-Worker-Token': 'secret123'})
    resp = asyncio.run(app.require_worker_token(req, _ok))
    assert resp == 'ok'


def test_token_middleware_health_endpoint_always_public(monkeypatch):
    import asyncio
    import app
    monkeypatch.setattr(app, 'WORKER_TOKEN', 'secret123')
    resp = asyncio.run(app.require_worker_token(_FakeRequest('/api/v1/health'), _ok))
    assert resp == 'ok'
