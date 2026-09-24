"""API real en localhost + subprocess real; nunca conecta a produccion."""
import importlib.util
from pathlib import Path
import socket
import sys
import threading
import time

import pytest
import requests
import uvicorn
import app
import db

WORKER_DIR = Path(__file__).resolve().parents[1] / 'worker'
sys.path.insert(0, str(WORKER_DIR))
spec = importlib.util.spec_from_file_location('cancel_integration_worker', WORKER_DIR / 'worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_cancel_over_real_heartbeat_and_requeue(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'coordinator.db')
    monkeypatch.setattr(app, 'WORKER_TOKEN', '')
    db.init_db()
    db.upsert_worker('w', 'fixture', 4, 8, '')
    job_id = db.insert_job('SEP_p', 'min', 0, 0, 0, 10)
    job = dict(db.claim_next_job('w'))
    monkeypatch.setattr(worker, 'WORKER_ID_FILE', tmp_path / 'worker_id')
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    monkeypatch.setattr(worker, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(worker, 'HEARTBEAT_INTERVAL_S', .1)
    monkeypatch.setattr(worker, 'build_command', lambda *args: [sys.executable, '-c',
        'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'])
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{listener.getsockname()[1]}'
    monkeypatch.setattr(worker, 'COORDINATOR_URL', url)
    server = uvicorn.Server(uvicorn.Config(app.app, log_level='error'))
    api_thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    stop = threading.Event()
    heartbeat = threading.Thread(target=worker.heartbeat_loop, args=('w', stop), daemon=True)
    run = threading.Thread(target=worker.run_job, args=('w', job), daemon=True)
    try:
        api_thread.start()
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started
        run.start()
        heartbeat.start()
        deadline = time.monotonic() + 5
        while db.get_job(job_id)['status'] != 'running' and time.monotonic() < deadline:
            time.sleep(.01)
        assert requests.post(f'{url}/api/v1/jobs/{job_id}/cancel', timeout=2).status_code == 200
        run.join(timeout=8)
        assert not run.is_alive(), 'Cancellation failed to terminate a TERM-resistant process'
        row = db.get_job(job_id)
        assert row['status'] == 'pending'
        assert row['cancel_requested'] == 0
        assert 'cancelado' in row['last_error']
        assert worker._active_cancel is None
    finally:
        if run.is_alive():
            worker.deliver_cancellation(worker._active_cancel, job_id)
            run.join(timeout=5)
        stop.set()
        if heartbeat.ident:
            heartbeat.join(timeout=3)
        server.should_exit = True
        api_thread.join(timeout=5)
        listener.close()
