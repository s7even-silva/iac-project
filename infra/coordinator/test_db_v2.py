"""Tests de jobs_v2/results_v2 (ver db_v2.py) -- archivo SEPARADO de
test_coordinator.py a proposito, mismo criterio que llevo a que db_v2.py
sea un modulo separado de db.py: deja evidente que esto cubre codigo
aislado del que ya sirve los 600 jobs reales de produccion.

Correr:
    cd infra/coordinator
    pytest test_db_v2.py -v
"""
import pytest

import db
import db_v2


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    # Mismo archivo fisico para ambos modulos -- replica que en produccion
    # jobs_v2/results_v2 viven en el MISMO coordinator.db que jobs/results
    # (ver docstring de db_v2.py). db_v2.py lee db.DB_PATH en vivo (no una
    # copia propia, ver ese modulo), asi que monkeypatchear solo db.DB_PATH
    # alcanza para ambos.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    db_v2.init_db_v2()
    yield


def test_jobs_v2_unique_includes_n_bins():
    """bin_index=3 de una grilla de 8 y bin_index=3 de una grilla de 16
    NO deben colisionar como 'el mismo job' -- ver comentario del UNIQUE
    en db_v2.py."""
    id_8 = db_v2.insert_job_v2("GCR_H", "min", 3, 8, 0.0, 0, 200)
    id_16 = db_v2.insert_job_v2("GCR_H", "min", 3, 16, 0.0, 0, 200)
    assert id_8 and id_16 and id_8 != id_16

    # Duplicado EXACTO (mismo n_bins tambien) si colisiona (ON CONFLICT DO NOTHING).
    id_dup = db_v2.insert_job_v2("GCR_H", "min", 3, 8, 0.0, 0, 200)
    assert not id_dup


def test_claim_and_record_result_v2_full_cycle():
    db.upsert_worker("w1", "host1", 8, 16.0, "test")
    job_id = db_v2.insert_job_v2("SEP_p", "max", 0, 16, 0.0, 0, 200)
    assert job_id

    claimed = db_v2.claim_next_job_v2("w1")
    assert claimed is not None
    assert claimed["job_id"] == job_id
    assert claimed["n_bins"] == 16
    assert claimed["status"] == "claimed"

    # ya no queda nada pendiente
    assert db_v2.claim_next_job_v2("w2") is None

    assert db_v2.mark_running_v2(job_id, "w1")
    status = db_v2.record_result_v2(job_id, "w1", 12.3, 0, 5, "/tmp/r.csv", "/tmp/m.csv")
    assert status == "done"

    row = db_v2.get_job_v2(job_id)
    assert row["status"] == "done"


def test_record_result_v2_rejects_wrong_worker():
    """Mismo criterio de propiedad que db.record_result() -- un resultado
    de un worker que ya no tiene el job asignado (ej. reencolado por
    timeout, otro worker lo retomo) se rechaza."""
    db.upsert_worker("w1", "host1", 8, 16.0, "test")
    db.upsert_worker("w2", "host2", 8, 16.0, "test")
    job_id = db_v2.insert_job_v2("GCR_H", "min", 0, 8, 0.0, 0, 200)
    db_v2.claim_next_job_v2("w1")

    with pytest.raises(PermissionError):
        db_v2.record_result_v2(job_id, "w2", 1.0, 0, 1, "/tmp/r.csv", "/tmp/m.csv")


def test_record_failure_v2_requeues_until_max_attempts():
    db.upsert_worker("w1", "host1", 8, 16.0, "test")
    job_id = db_v2.insert_job_v2("GCR_H", "min", 0, 8, 0.0, 0, 200)

    for _ in range(3):  # max_attempts default = 3
        claimed = db_v2.claim_next_job_v2("w1")
        assert claimed is not None
        status = db_v2.record_failure_v2(job_id, "w1", "boom")
    # tercer intento agotado -> failed, no vuelve a 'pending'
    assert status == "failed"
    assert db_v2.claim_next_job_v2("w1") is None


def test_list_and_counts_v2():
    db_v2.insert_job_v2("GCR_H", "min", 0, 8, 0.0, 0, 200)
    db_v2.insert_job_v2("GCR_He", "min", 1, 8, 0.0, 0, 200)
    assert len(db_v2.list_jobs_v2()) == 2
    assert len(db_v2.list_jobs_v2(status="pending")) == 2
    assert db_v2.counts_by_status_v2() == {"pending": 2}


def test_jobs_v1_untouched_by_v2_operations():
    """Cero acoplamiento real: insertar/operar en jobs_v2 no debe afectar
    en nada la tabla jobs (v1) -- verifica el aislamiento que motivo tener
    un modulo separado en primer lugar."""
    v1_job_id = db.insert_job("GCR_H", "min", 0, 0.0, 0, 200)
    db_v2.insert_job_v2("GCR_H", "min", 0, 16, 0.0, 0, 200)  # mismo bin_index, otro n_bins

    v1_row = db.get_job(v1_job_id)
    assert v1_row is not None
    assert v1_row["status"] == "pending"
    assert db.counts_by_status() == {"pending": 1}


def test_timeout_requires_dead_worker_and_respects_attempt_limit():
    db.upsert_worker('w', 'host', 8, 16, 'test')
    job = db_v2.insert_job_v2('SEP_p', 'max', 0, 8, 0, 0, 1)
    db_v2.claim_next_job_v2('w')
    with db_v2.get_conn() as conn:
        conn.execute("UPDATE jobs_v2 SET updated_at='2000-01-01', attempt=max_attempts")
    assert db_v2.requeue_stale_jobs_v2() == []
    with db_v2.get_conn() as conn:
        conn.execute("UPDATE workers SET last_heartbeat='2000-01-01'")
    assert db_v2.requeue_stale_jobs_v2() == [job]
    assert db_v2.get_job_v2(job)['status'] == 'failed'
