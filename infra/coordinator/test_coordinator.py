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
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
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
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    assert job_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(db.claim_next_job, ["w1", "w2"]))

    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1, "exactamente un worker debe haber reclamado el job"


def test_full_cycle_pending_to_done():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    job_id = db.insert_job("GCR_He", "min", 7, 3.0, 0, 10000, priority=10)

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
    job_id = db.insert_job("SEP_p", "min", 2, 0.0, 0, 100)

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
    db.insert_job("SEP_p", "min", 2, 0.0, 0, 100)
    job = db.list_jobs(status="pending")[0]
    assert job["actual_duration_s"] is None


def test_claim_prefers_lower_repetition_over_higher_priority():
    # Repeticiones en serie (decision de equipo, 2026-09-14): un job de
    # repeticion 1 con prioridad alta NO debe ganarle a uno de repeticion
    # 0 con prioridad baja -- la serie completa. Reproduce el bug real
    # encontrado en produccion: repeticiones 1-4 arrancaban en paralelo
    # mientras la 0 seguia con trabajo pendiente.
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    low_rep_low_priority = db.insert_job("GCR_H", "min", 0, 0.0, 0, 10000, priority=0)
    db.insert_job("GCR_He", "min", 7, 0.0, 1, 10000, priority=20)

    job = db.claim_next_job("w1")
    assert job["job_id"] == low_rep_low_priority
    assert job["repeticion"] == 0


def test_claim_still_orders_by_priority_within_same_repetition():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    db.insert_job("GCR_H", "min", 0, 0.0, 0, 10000, priority=0)
    high_priority_same_rep = db.insert_job("GCR_He", "min", 7, 0.0, 0, 10000, priority=20)

    job = db.claim_next_job("w1")
    assert job["job_id"] == high_priority_same_rep


def test_claim_fast_worker_prefers_heaviest_job_in_same_group():
    # Emparejamiento por cpu_score (2026-09-14): dentro del mismo
    # (repeticion, priority) -- aqui, GCR_H y GCR_He bin7 comparten
    # priority=7 en produccion real -- un worker rapido debe recibir el
    # mas pesado del grupo (GCR_He bin7, referencia ~18780s) en vez del
    # primero por job_id (GCR_H bin7, referencia ~4669.7s).
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    light_job = db.insert_job("GCR_H", "min", 7, 0.0, 0, 10000, priority=7)
    heavy_job = db.insert_job("GCR_He", "min", 7, 0.0, 0, 10000, priority=7)

    job = db.claim_next_job("fast")
    assert job["job_id"] == heavy_job
    assert light_job != heavy_job  # sanity: son jobs distintos


def test_claim_slow_worker_prefers_lightest_job_in_same_group():
    db.upsert_worker("slow", "h1", 8, 16.0, "", cpu_score=1.0)
    light_job = db.insert_job("GCR_H", "min", 7, 0.0, 0, 10000, priority=7)
    db.insert_job("GCR_He", "min", 7, 0.0, 0, 10000, priority=7)

    job = db.claim_next_job("slow")
    assert job["job_id"] == light_job


def test_claim_pairing_never_crosses_repetition_or_priority_group():
    # El emparejamiento por cpu_score no debe poder saltar a un
    # (repeticion, priority) distinto solo porque tenga un job mejor
    # emparejado -- eso reintroduciria el bug de repeticiones en
    # paralelo. Un worker muy rapido (pero NO elite, cpu_score ==
    # REFERENCE_CPU_SCORE, muy por debajo de ELITE_WORKER_CPU_SCORE_THRESHOLD)
    # con un job pesado disponible en repeticion 1 igual debe recibir el
    # (unico) job de repeticion 0, aunque sea liviano.
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    light_rep0 = db.insert_job("GCR_H", "min", 0, 0.0, 0, 10000, priority=0)
    db.insert_job("GCR_He", "min", 7, 0.0, 1, 10000, priority=20)

    job = db.claim_next_job("fast")
    assert job["job_id"] == light_rep0


def test_claim_elite_worker_crosses_repetition_boundary():
    # Pedido explicito del usuario (2026-09-14): un worker "elite"
    # (cpu_score >= ELITE_WORKER_CPU_SCORE_THRESHOLD, ej. "tania" con
    # 18.07 en produccion) debe recibir el job MAS PESADO de todo el
    # sistema sin importar la repeticion -- a diferencia de un worker
    # rapido normal (test de arriba), este SI puede saltar a una
    # repeticion mas alta si ahi esta el trabajo mas caro.
    db.upsert_worker("elite", "h1", 8, 32.0, "", cpu_score=db.ELITE_WORKER_CPU_SCORE_THRESHOLD)
    light_rep0 = db.insert_job("GCR_H", "min", 0, 0.0, 0, 10000, priority=0)
    heavy_rep1 = db.insert_job("GCR_He", "min", 7, 0.0, 1, 10000, priority=20)

    job = db.claim_next_job("elite")
    assert job["job_id"] == heavy_rep1
    assert light_rep0 != heavy_rep1  # sanity: son jobs distintos


def test_claim_elite_worker_picks_heaviest_among_multiple_repetitions():
    # El job mas pesado puede estar en cualquier repeticion, no solo la
    # mas alta -- el criterio es REFERENCE_TIMINGS_S real, no el numero
    # de repeticion ni el orden de insercion.
    db.upsert_worker("elite", "h1", 8, 32.0, "", cpu_score=db.ELITE_WORKER_CPU_SCORE_THRESHOLD)
    db.insert_job("SEP_p", "min", 0, 0.0, 3, 10000, priority=5)  # liviano, rep alta
    heaviest = db.insert_job("GCR_He", "min", 7, 0.0, 0, 10000, priority=20)  # pesado, rep baja
    db.insert_job("GCR_H", "min", 3, 0.0, 2, 10000, priority=3)  # intermedio

    job = db.claim_next_job("elite")
    assert job["job_id"] == heaviest


def test_claim_worker_without_cpu_score_is_never_treated_as_elite():
    # worker["cpu_score"] ausente (None) cae a "infinito" para no
    # bloquear min_cpu_score (ver claim_next_job()) -- pero "infinito"
    # nunca debe calificar como elite por accidente solo por ser
    # matematicamente >= ELITE_WORKER_CPU_SCORE_THRESHOLD. Sin
    # cpu_score real medido, el worker sigue el camino normal
    # (repeticion ASC), igual que antes de este cambio.
    db.upsert_worker("no_score", "h1", 8, 32.0, "")  # cpu_score=None
    low_rep = db.insert_job("GCR_H", "min", 0, 0.0, 0, 10000, priority=0)
    db.insert_job("GCR_He", "min", 7, 0.0, 1, 10000, priority=20)

    job = db.claim_next_job("no_score")
    assert job["job_id"] == low_rep


def test_claim_elite_worker_still_respects_resource_thresholds():
    # Un worker elite no se salta min_ram_gb/min_cpu_count/min_cpu_score
    # del job -- solo se salta el orden por repeticion. Aqui el job mas
    # pesado exige mas RAM de la que el worker tiene libre, asi que debe
    # recibir el siguiente mas pesado que si pueda satisfacer.
    db.upsert_worker("elite", "h1", 8, 32.0, "", cpu_score=db.ELITE_WORKER_CPU_SCORE_THRESHOLD, ram_free_gb=4.0)
    db.insert_job("GCR_He", "min", 7, 0.0, 0, 10000, priority=20, min_ram_gb=8.0)  # inalcanzable
    reachable = db.insert_job("GCR_H", "min", 6, 0.0, 1, 10000, priority=6, min_ram_gb=2.0)

    job = db.claim_next_job("elite")
    assert job["job_id"] == reachable


def test_failed_result_requeues_until_max_attempts():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)

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
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    db.claim_next_job("w1")

    with pytest.raises(PermissionError):
        db.record_result(job_id, "w2", duration_s=1.0, exit_code=0, n_rows=1,
                          results_csv_path="/tmp/r.csv", manifest_csv_path="/tmp/m.csv")


def test_estimate_job_duration_scales_by_cpu_score():
    reference_s = db.REFERENCE_TIMINGS_S[("GCR_H", 3)]
    # Worker con la mitad de cpu_score que la referencia -> tarda el doble,
    # mas DISPLAY_OVERESTIMATE_FACTOR (las runs reales tienden a tardar
    # mas que la referencia pura, ver comentario en db.py).
    half_score = db.REFERENCE_CPU_SCORE / 2
    estimated = db.estimate_job_duration_s("GCR_H", 3, half_score)
    assert estimated == pytest.approx(reference_s * 2 * db.DISPLAY_OVERESTIMATE_FACTOR, rel=1e-6)


def test_estimate_job_duration_applies_overestimate_factor_at_reference_score():
    # Al cpu_score de referencia exacto, la estimacion no es igual al
    # numero crudo de la tabla -- ya lleva el margen aplicado.
    reference_s = db.REFERENCE_TIMINGS_S[("SEP_p", 2)]
    estimated = db.estimate_job_duration_s("SEP_p", 2, db.REFERENCE_CPU_SCORE)
    assert estimated == pytest.approx(reference_s * db.DISPLAY_OVERESTIMATE_FACTOR, rel=1e-6)
    assert estimated > reference_s


def test_estimate_job_duration_none_without_cpu_score():
    assert db.estimate_job_duration_s("GCR_H", 3, None) is None
    assert db.estimate_job_duration_s("GCR_H", 3, 0) is None


def test_estimate_job_duration_none_for_unknown_combo():
    assert db.estimate_job_duration_s("GCR_H", 99, db.REFERENCE_CPU_SCORE) is None


def test_requeue_respects_estimated_duration_beyond_fixed_timeout(monkeypatch):
    # STALE_JOB_TIMEOUT_S (usado solo sin estimacion) corto a proposito --
    # con estimacion disponible (bin7, referencia ~4669.7s), el umbral de
    # abandono real (_abandon_timeout_s, ~9339s aqui) sigue protegiendo al
    # job pese a que STALE_JOB_TIMEOUT_S ya haya vencido.
    monkeypatch.setattr(db, "STALE_JOB_TIMEOUT_S", 100.0)
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    job_id = db.insert_job("GCR_H", "min", 7, 0.0, 0, 10000)
    db.claim_next_job("fast")

    stale_at = datetime.fromtimestamp(time.time() - 200, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='fast'", (stale_at,))

    requeued = db.requeue_stale_jobs()
    assert job_id not in requeued
    assert db.get_job(job_id)["status"] == "claimed"


def test_requeue_still_uses_abandon_floor_when_estimate_is_short():
    # Job barato (bin0) en un worker rapido -- el umbral de abandono tiene
    # un PISO (ABANDON_FLOOR_S, 1h) que protege de reencolar por un simple
    # lag de red breve, aunque la estimacion*ABANDON_FACTOR sola diera un
    # numero mas chico.
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    job_id = db.insert_job("GCR_H", "min", 0, 0.0, 0, 10000)
    db.claim_next_job("fast")

    stale_at = datetime.fromtimestamp(time.time() - 2, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='fast'", (stale_at,))

    requeued = db.requeue_stale_jobs()
    assert job_id not in requeued  # 2s de heartbeat vencido << piso de abandono (1h)


def test_requeue_falls_back_to_fixed_timeout_without_cpu_score():
    db.upsert_worker("w1", "h1", 8, 16.0, "")  # sin cpu_score
    job_id = db.insert_job("GCR_H", "min", 7, 0.0, 0, 10000)
    db.claim_next_job("w1")

    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='w1'", ("2000-01-01T00:00:00+00:00",))

    requeued = db.requeue_stale_jobs()
    assert job_id in requeued  # sin cpu_score, cae al timeout fijo (ya vencido)


def test_abandon_timeout_clamped_between_floor_and_ceiling():
    # ABANDON_FLOOR_S=1h, ABANDON_CEILING_S=10h -- un bin muy barato no
    # cae por debajo del piso, un bin/worker que daria un numero enorme no
    # supera el techo.
    assert db._abandon_timeout_s(1.0) == db.ABANDON_FLOOR_S  # 1s*2 << piso
    assert db._abandon_timeout_s(100000.0) == db.ABANDON_CEILING_S  # 100000s*2 >> techo
    mid = db._abandon_timeout_s(3600.0)  # 1h*2=2h, entre piso y techo
    assert mid == pytest.approx(3600.0 * db.ABANDON_FACTOR)


def test_requeue_bug_repro_short_estimate_no_longer_waits_fixed_floor():
    # Reproduce el bug real reportado en produccion (2026-09-14): un job
    # de referencia ~2h esperaba las STALE_JOB_TIMEOUT_S completas (antes
    # 6h) antes de reencolarse, porque el piso fijo dominaba casi siempre
    # sobre la estimacion (2h*2.5=5h < 6h). Con el diseno nuevo, el
    # criterio de abandono ya no depende de STALE_JOB_TIMEOUT_S cuando hay
    # estimacion -- bin6 (referencia 1820.4s=~0.5h) debe reencolarse por
    # abandono mucho antes de que STALE_JOB_TIMEOUT_S (5h) venza.
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    job_id = db.insert_job("GCR_H", "min", 6, 0.0, 0, 10000)
    db.claim_next_job("fast")

    # Umbral de abandono real: clamp(1820.4*2, 3600, 36000) = 3640.8s (~1h).
    # Heartbeat vencido 2h -- mucho mas que el umbral de abandono, pero
    # bastante MENOS que STALE_JOB_TIMEOUT_S (5h, el comportamiento viejo
    # habria seguido esperando).
    stale_at = datetime.fromtimestamp(time.time() - 2 * 3600, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='fast'", (stale_at,))

    requeued = db.requeue_stale_jobs()
    assert job_id in requeued  # ya se reencolo, sin esperar las 5h fijas


def test_requeue_stale_jobs_without_heartbeat():
    db.upsert_worker("w1", "h1", 8, 16.0, "")
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
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
    first = db.insert_job("GCR_H", "min", 2, 1.0, 0, 10000)
    second = db.insert_job("GCR_H", "min", 2, 1.0, 0, 10000)  # misma combinacion exacta
    assert first
    assert second is None or second == 0  # lastrowid no cambia si ON CONFLICT DO NOTHING no inserto
    assert len(db.list_jobs()) == 1


def test_expired_job_exhausts_attempts():
    db.upsert_worker('w', 'host', 1, 1, '')
    job = db.insert_job('SEP_p', "min", 1, 1., 0, 100)
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
    job = db.insert_job('SEP_p', "min", 1, 1., 0, 100)
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
    job = db.insert_job('SEP_p', "min", 1, 1., 0, 100)
    db.claim_next_job('owner')
    assert not db.mark_running(job, 'someone-else')
    assert db.mark_running(job, 'owner')


def test_worker_below_min_ram_does_not_get_job():
    db.upsert_worker('small', 'host', 8, 4.0, '', ram_free_gb=1.0, cpu_load_pct=5.0)
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000, min_ram_gb=8.0)
    assert db.claim_next_job('small') is None
    assert db.get_job(job_id)['status'] == 'pending'


def test_worker_below_min_cpu_does_not_get_job():
    db.upsert_worker('weak', 'host', 2, 16.0, '', ram_free_gb=16.0)
    db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000, min_cpu_count=4)
    assert db.claim_next_job('weak') is None


def test_worker_meeting_requirements_gets_job():
    db.upsert_worker('strong', 'host', 16, 32.0, '', ram_free_gb=20.0, cpu_load_pct=10.0)
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000, min_ram_gb=8.0, min_cpu_count=4)
    claimed = db.claim_next_job('strong')
    assert claimed is not None
    assert claimed['job_id'] == job_id


def test_worker_without_telemetry_falls_back_to_total_ram():
    # Registrado sin ram_free_gb (worker viejo o metrica no disponible) --
    # no debe bloquear jobs sin requisitos, cae a ram_gb total.
    db.upsert_worker('legacy', 'host', 8, 16.0, '')
    job_id = db.insert_job('SEP_p', "min", 1, 1.0, 0, 100, min_ram_gb=8.0)
    claimed = db.claim_next_job('legacy')
    assert claimed is not None
    assert claimed['job_id'] == job_id


def test_worker_below_min_cpu_score_does_not_get_job():
    # cpu_score mide capacidad de computo REAL (benchmark, ver cpu_score()
    # en worker.py) -- una maquina puede tener muchos nucleos (cpu_count
    # alto) pero ser lenta por core (VM compartida, CPU vieja); esto
    # existe justamente para no confundir "muchos nucleos" con "rapido".
    db.upsert_worker('many_cores_slow', 'host', 16, 16.0, '', ram_free_gb=16.0, cpu_score=0.3)
    db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000, min_cpu_score=1.0)
    assert db.claim_next_job('many_cores_slow') is None


def test_worker_meeting_cpu_score_gets_job():
    db.upsert_worker('fast', 'host', 8, 16.0, '', ram_free_gb=16.0, cpu_score=1.5)
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000, min_cpu_score=1.0)
    claimed = db.claim_next_job('fast')
    assert claimed is not None
    assert claimed['job_id'] == job_id


def test_worker_without_cpu_score_is_not_blocked():
    # Sin cpu_score (worker de antes de este cambio, o el benchmark del
    # propio worker fallo) -- no debe bloquear un job con min_cpu_score,
    # mismo criterio que ram_free_gb ausente cae a ram_gb total.
    db.upsert_worker('no_score', 'host', 8, 16.0, '', ram_free_gb=16.0)
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000, min_cpu_score=1.0)
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


def test_heartbeat_accrues_connected_s_to_claimed_job():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    db.claim_next_job('w')  # primer heartbeat implicito, sin heartbeat previo que acumular

    # Simula que el heartbeat anterior fue hace 10s -- el proximo touch_heartbeat
    # debe sumar ~10s a connected_s del job claimed.
    ten_s_ago = datetime.fromtimestamp(time.time() - 10, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='w'", (ten_s_ago,))

    db.touch_heartbeat('w')
    job = db.get_job(job_id)
    assert job["connected_s"] == pytest.approx(10.0, abs=1.0)


def test_heartbeat_accrual_capped_at_max_interval():
    # Un gap MUY largo desde el heartbeat anterior (ej. worker apagado
    # varias horas) no debe sumarse completo a connected_s -- solo hasta
    # MAX_HEARTBEAT_ACCRUAL_S, porque ese hueco es una desconexion real,
    # no tiempo conectado.
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    db.claim_next_job('w')

    long_ago = datetime.fromtimestamp(time.time() - 5 * 3600, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='w'", (long_ago,))

    db.touch_heartbeat('w')
    job = db.get_job(job_id)
    assert job["connected_s"] == pytest.approx(db.MAX_HEARTBEAT_ACCRUAL_S, abs=1.0)


def test_connected_s_resets_when_job_returns_to_pending():
    db.upsert_worker('w', 'host', 8, 16.0, '', cpu_score=db.REFERENCE_CPU_SCORE)
    job_id = db.insert_job("SEP_p", "min", 7, 0.0, 0, 100)  # max_attempts=3 default
    db.claim_next_job('w')

    with db.get_conn() as conn:
        conn.execute("UPDATE jobs SET connected_s=999 WHERE job_id=?", (job_id,))

    db.record_failure(job_id, 'w', "boom", 1.0)
    job = db.get_job(job_id)
    assert job["status"] == "pending"
    assert job["connected_s"] == 0


def test_requeue_by_progress_exhausted_triggers_even_with_recent_heartbeat():
    # Bug real de produccion (2026-09-16, ver AGENTS.md "job 141 en
    # tania"): el WHERE de SQL exigia heartbeat VENCIDO antes de
    # evaluar cualquiera de las dos condiciones -- pero progress_exhausted
    # es sobre connected_s, independiente de si el heartbeat sigue vivo.
    # heartbeat_loop() corre en su propio hilo daemon y sigue latiendo
    # con normalidad aunque el hilo principal (process.communicate()
    # bloqueando en el subprocess de Geant4) este genuinamente colgado --
    # un heartbeat vivo NO implica que el job avanza. Resultado real: un
    # job acumulo 10.1h conectado (682% del estimado) sin reencolarse
    # nunca porque la fila jamas paso el filtro SQL. Este test antes
    # afirmaba el comportamiento INCORRECTO (que motivo el bug) -- ahora
    # confirma el correcto: progress_exhausted reencola por si solo, sin
    # necesitar que el heartbeat tambien este vencido.
    db.upsert_worker("fast", "h1", 8, 16.0, "", cpu_score=db.REFERENCE_CPU_SCORE)
    job_id = db.insert_job("GCR_H", "min", 0, 0.0, 0, 10000)  # referencia ~20.9s
    db.claim_next_job("fast")

    with db.get_conn() as conn:
        conn.execute("UPDATE jobs SET connected_s=999999 WHERE job_id=?", (job_id,))
        # last_heartbeat sigue reciente (touch_heartbeat_in_conn del propio claim)

    requeued = db.requeue_stale_jobs()
    assert job_id in requeued


def test_heartbeat_does_not_accrue_connected_s_to_orphaned_job():
    # Bug real de produccion (2026-09-15, reportado por el usuario): si el
    # PROCESO del worker muere y se reinicia (apagado/encendido, crash) sin
    # liberar primero el job que tenia activo, el proceso nuevo pide otro
    # job -- dejando el viejo huerfano en claimed/running bajo el mismo
    # worker_id. Antes de este fix, cada heartbeat siguiente sumaba
    # connected_s a AMBOS jobs (el huerfano y el real), aunque el worker
    # solo trabajara en uno. No pasa con un simple corte de red (el mismo
    # proceso retoma el MISMO job_id al reconectar).
    db.upsert_worker('w', 'host', 8, 16.0, '')
    db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    db.claim_next_job('w')  # queda claimed/running bajo 'w'

    real_id = db.insert_job("SEP_p", "min", 1, 0.0, 0, 100)
    with db.get_conn() as conn:
        # Simula el reinicio: el proceso nuevo reclama otro job sin que el
        # coordinator sepa que el anterior murio -- fuerza el estado
        # exacto que produjo el bug real (dos jobs claimed/running bajo el
        # mismo worker_id a la vez).
        conn.execute("UPDATE jobs SET status='running', claimed_by='w', claimed_at=? WHERE job_id=?",
                     (db.now_iso(), real_id))

    ten_s_ago = datetime.fromtimestamp(time.time() - 10, tz=timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat=? WHERE worker_id='w'", (ten_s_ago,))

    db.touch_heartbeat('w', active_job_id=real_id)
    assert db.get_job(real_id)["connected_s"] == pytest.approx(10.0, abs=1.0)


def test_heartbeat_requeues_orphaned_job_when_worker_claims_another():
    # Continuacion del test anterior: el job huerfano no debe quedarse
    # colgado esperando el timeout normal de abandono -- Geant4 no tiene
    # estados intermedios, asi que su progreso ya se perdio por completo
    # en el momento en que el worker reclamo otro job. Se reencola de
    # inmediato, en el mismo heartbeat que revela la orfandad.
    db.upsert_worker('w', 'host', 8, 16.0, '')
    orphan_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    db.claim_next_job('w')

    real_id = db.insert_job("SEP_p", "min", 1, 0.0, 0, 100)
    with db.get_conn() as conn:
        conn.execute("UPDATE jobs SET status='running', claimed_by='w', claimed_at=? WHERE job_id=?",
                     (db.now_iso(), real_id))

    result = db.touch_heartbeat('w', active_job_id=real_id)
    assert result["requeued_orphan_job_ids"] == [orphan_id]

    orphan = db.get_job(orphan_id)
    assert orphan["status"] == "pending"
    assert orphan["claimed_by"] is None
    assert orphan["connected_s"] == 0
    assert "reencolado automaticamente" in orphan["last_error"]

    # El job real (el que el worker de verdad esta trabajando) no se toca.
    real = db.get_job(real_id)
    assert real["status"] == "running"
    assert real["claimed_by"] == "w"


def test_heartbeat_orphan_requeue_respects_max_attempts():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    orphan_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    db.claim_next_job('w')
    with db.get_conn() as conn:
        conn.execute("UPDATE jobs SET attempt=max_attempts WHERE job_id=?", (orphan_id,))

    real_id = db.insert_job("SEP_p", "min", 1, 0.0, 0, 100)
    with db.get_conn() as conn:
        conn.execute("UPDATE jobs SET status='running', claimed_by='w', claimed_at=? WHERE job_id=?",
                     (db.now_iso(), real_id))

    db.touch_heartbeat('w', active_job_id=real_id)
    orphan = db.get_job(orphan_id)
    # failed conserva claimed_by/claimed_at, mismo criterio que
    # record_failure() para cualquier otro job que agota sus intentos.
    assert orphan["status"] == "failed"
    assert orphan["claimed_by"] == "w"


def test_heartbeat_without_active_job_id_does_not_requeue_anything():
    # Un worker sin esa telemetria todavia (version vieja) no debe perder
    # su job real por este mecanismo -- mismo criterio conservador que
    # ram_free_gb/cpu_score ausentes en otras partes del coordinator.
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job("SEP_p", "min", 0, 0.0, 0, 100)
    db.claim_next_job('w')

    result = db.touch_heartbeat('w')  # sin active_job_id
    assert "requeued_orphan_job_ids" not in result
    assert db.get_job(job_id)["status"] in ("claimed", "running")


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


def test_heartbeat_persists_active_job_id():
    # A diferencia de ram_free_gb/cpu_load_pct/image_digest (COALESCE,
    # conservan el valor anterior si no llega uno nuevo), active_job_id
    # se escribe TAL CUAL en cada heartbeat -- incluyendo None explicito,
    # que es exactamente el diagnostico que motivo este campo: un worker
    # sin ningun job real activo debe reflejarse como None, no como "lo
    # que reporto la ultima vez".
    db.upsert_worker('w', 'host', 8, 16.0, '')
    db.touch_heartbeat('w', active_job_id=42)
    row = db.list_workers()[0]
    assert row['active_job_id'] == 42
    assert row['active_job_reported_at'] is not None

    db.touch_heartbeat('w', active_job_id=None)
    row = db.list_workers()[0]
    assert row['active_job_id'] is None


def test_request_job_cancel_marks_running_job():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('w')
    db.mark_running(job_id, 'w')

    claimed_by = db.request_job_cancel(job_id)
    assert claimed_by == 'w'
    job = db.get_job(job_id)
    assert job['cancel_requested'] == 1
    # el status del job NO cambia con solo pedir la cancelacion -- sigue
    # 'running' hasta que el worker reporte el resultado real (ver
    # run_job() en worker.py, que lo reporta como fallo).
    assert job['status'] == 'running'


def test_request_job_cancel_on_pending_job_returns_none():
    # Nada que cancelar si ningun worker lo tiene asignado todavia.
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    assert db.request_job_cancel(job_id) is None
    assert db.get_job(job_id)['cancel_requested'] == 0


def test_request_job_cancel_unknown_job_raises():
    with pytest.raises(KeyError):
        db.request_job_cancel(999999)


def test_heartbeat_reports_cancel_job_id_for_claimed_job():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('w')
    db.request_job_cancel(job_id)

    result = db.touch_heartbeat('w')
    assert result == {'cancel_job_id': job_id, 'request_log': False}


def test_heartbeat_reports_no_cancel_when_not_requested():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('w')

    result = db.touch_heartbeat('w')
    assert result == {'cancel_job_id': None, 'request_log': False}


def test_request_job_log_marks_running_job():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('w')
    db.mark_running(job_id, 'w')

    claimed_by = db.request_job_log(job_id)
    assert claimed_by == 'w'
    job = db.get_job(job_id)
    assert job['log_requested'] == 1
    assert job['status'] == 'running'  # pedir el log no cambia el status


def test_request_job_log_on_pending_job_returns_none():
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    assert db.request_job_log(job_id) is None
    assert db.get_job(job_id)['log_requested'] == 0


def test_request_job_log_unknown_job_raises():
    with pytest.raises(KeyError):
        db.request_job_log(999999)


def test_heartbeat_reports_request_log_true_when_requested():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('w')
    db.request_job_log(job_id)

    result = db.touch_heartbeat('w')
    assert result['request_log'] is True
    assert result['log_request']['attempt'] == 1
    assert result['log_request']['job_id'] == job_id


def test_save_job_log_tail_clears_request_flag():
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('w')
    db.request_job_log(job_id)

    row = db.get_job(job_id)
    ok = db.save_job_log_tail(job_id, 'w', 'Event 4200 of 10000\n', row['log_request_id'], row['attempt'])
    assert ok is True
    job = db.get_job(job_id)
    assert job['log_requested'] == 0
    assert job['log_tail'] == 'Event 4200 of 10000\n'
    assert job['log_tail_updated_at'] is not None

    # log_requested ya en 0 -- el siguiente heartbeat no vuelve a pedirlo.
    result = db.touch_heartbeat('w')
    assert result['request_log'] is False


def test_save_job_log_tail_rejected_from_wrong_worker():
    # Mismo criterio de propiedad que record_result()/record_failure():
    # un worker que ya no es dueño del job (reasignado por timeout) no
    # puede pisar el log de un intento mas reciente con una subida tardia.
    db.upsert_worker('a', 'host', 8, 16.0, '')
    db.upsert_worker('b', 'host', 8, 16.0, '')
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('a')
    db.record_failure(job_id, 'a', 'requeued', 5.0)  # 'a' pierde el job
    db.claim_next_job('b')

    ok = db.save_job_log_tail(job_id, 'a', 'log viejo de a')
    assert ok is False
    job = db.get_job(job_id)
    assert job['log_tail'] is None


def test_cancel_flag_clears_on_result_and_next_attempt_is_not_cancelled():
    # Un job cancelado se reporta como fallo (run_job() en worker.py);
    # record_result()/record_failure() deben limpiar cancel_requested para
    # que el SIGUIENTE intento (mismo job_id, otro worker) no nazca ya
    # marcado para cancelar sin que nadie lo haya pedido para ese intento.
    db.upsert_worker('w', 'host', 8, 16.0, '')
    job_id = db.insert_job('GCR_He', "min", 7, 3.0, 0, 10000)
    db.claim_next_job('w')
    db.mark_running(job_id, 'w')
    db.request_job_cancel(job_id)

    new_status = db.record_failure(job_id, 'w', 'cancelado por el operador', 12.3)
    assert new_status == 'pending'  # attempt < max_attempts
    job = db.get_job(job_id)
    assert job['cancel_requested'] == 0
    assert job['status'] == 'pending'


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


def test_timeout_does_not_transfer_cancel_to_next_attempt():
    db.upsert_worker('w', 'host', 4, 8, '')
    job_id = db.insert_job('SEP_p', "min", 0, 0, 0, 100)
    db.claim_next_job('w')
    db.request_job_cancel(job_id)
    with db.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat='2000-01-01T00:00:00+00:00' WHERE worker_id='w'")
    assert job_id in db.requeue_stale_jobs()
    assert db.get_job(job_id)['cancel_requested'] == 0
    db.claim_next_job('w')
    assert db.touch_heartbeat('w')['cancel_job_id'] is None


def test_cancel_selects_reported_active_job_when_worker_has_multiple_claims():
    db.upsert_worker('w', 'host', 4, 8, '')
    first = db.insert_job('SEP_p', "min", 0, 0, 0, 100)
    second = db.insert_job('SEP_p', "min", 1, 0, 0, 100)
    assert db.force_claim_job(first, 'w')
    assert db.force_claim_job(second, 'w')
    db.request_job_cancel(first)
    db.request_job_cancel(second)
    assert db.touch_heartbeat('w', active_job_id=second)['cancel_job_id'] == second


def test_logs_are_bound_to_request_and_attempt_even_for_same_worker():
    db.upsert_worker('w', 'host', 8, 16, '')
    job_id = db.insert_job('SEP_p', "min", 0, 0, 0, 10)
    db.claim_next_job('w')
    first = db.request_job_log(job_id, detailed=True)
    second = db.request_job_log(job_id, detailed=True)
    assert not db.save_job_log_tail(job_id,'w','stale',first['request_id'],first['attempt'])
    assert db.save_job_log_tail(job_id,'w','',second['request_id'],second['attempt'])
    row = db.get_job(job_id)
    assert row['log_received_id'] == second['request_id']
    assert row['log_tail'] == ''
    db.record_failure(job_id,'w','retry',1)
    db.claim_next_job('w')
    third = db.request_job_log(job_id, detailed=True)
    assert not db.save_job_log_tail(job_id,'w','stale',second['request_id'],second['attempt'])
    assert not db.save_job_log_tail(job_id,'w','wrong attempt',third['request_id'],second['attempt'])
    assert db.save_job_log_tail(job_id,'w','fresh',third['request_id'],third['attempt'])


def test_log_cli_waits_for_matching_empty_response(monkeypatch, capsys):
    import request_job_log as cli
    from unittest.mock import Mock
    token = 'a' * 32
    monkeypatch.setattr('sys.argv', ['request_job_log.py', '42'])
    post = Mock(status_code=200)
    post.json.return_value = dict(job_id=42, claimed_by='w', request_id=token, attempt=2)
    monkeypatch.setattr(cli.requests, 'post', Mock(return_value=post))
    responses = []
    for received, tail in [('old', 'old output'), (token, '')]:
        response = Mock()
        response.json.return_value = [dict(job_id=42, log_received_id=received,
                                          log_attempt=2, log_tail=tail)]
        responses.append(response)
    get = Mock(side_effect=responses)
    monkeypatch.setattr(cli.requests, 'get', get)
    monkeypatch.setattr(cli.time, 'sleep', lambda _: None)
    cli.main()
    assert get.call_count == 2
    output = capsys.readouterr().out
    assert 'log recibido vacío' in output
    assert 'old output' not in output
