import pytest
import sys
import importlib.util
import csv
import io
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import requests

spec = importlib.util.spec_from_file_location('worker_under_test', Path(__file__).with_name('worker.py'))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_exact_repetition():
    job = dict(species='GCR_He', phase='min', bin_index=7, offset_x_m=3., repeticion=2, n_events=100)
    cmd = worker.build_command(job)
    assert cmd[cmd.index('--repetition-start')+1] == '2'
    assert cmd[cmd.index('--repeats')+1] == '1'
    assert cmd[cmd.index('--only-bins')+1] == '7'
    assert '--no-resume' in cmd


def test_header_only_is_not_result(tmp_path):
    (tmp_path/'resultados_organo_sweep.csv').write_text(','.join(worker.RESULTS_FIELDNAMES)+'\n')
    job = dict(species='SEP_p', bin_index=1, offset_x_m=1., repeticion=0)
    assert worker.filter_results_csv(job, tmp_path) == ''


def test_build_command_includes_n_bins_when_present():
    # jobs_v2 (2026-09-20): un job que trae n_bins debe pasarlo como
    # --n-bins a run_organ_sweep.py -- ver db_v2.py.
    job = dict(species='GCR_H', phase='min', bin_index=3, n_bins=16, offset_x_m=0., repeticion=0, n_events=200)
    cmd = worker.build_command(job)
    assert cmd[cmd.index('--n-bins')+1] == '16'


def test_build_command_omits_n_bins_when_absent():
    # Un job v1 (sin la key 'n_bins') NUNCA debe agregar --n-bins -- el
    # comando construido para v1 no cambia en absoluto (protege
    # test_exact_repetition, que no espera --n-bins en el comando).
    job = dict(species='GCR_H', phase='min', bin_index=3, offset_x_m=0., repeticion=0, n_events=200)
    cmd = worker.build_command(job)
    assert '--n-bins' not in cmd


def test_results_fieldnames_v2_includes_stat_columns():
    for col in ('n_bins', 's1_j', 's2_j2', 'n', 'se_run_j'):
        assert col in worker.RESULTS_FIELDNAMES_V2


def test_filter_results_csv_v2_filters_by_n_bins(tmp_path):
    # bin_index=3 de una grilla de 8 y bin_index=3 de una grilla de 16 NO
    # son el mismo job -- filter_results_csv debe distinguirlos cuando el
    # job trae n_bins (ver db_v2.py, UNIQUE incluye n_bins).
    header = ','.join(worker.RESULTS_FIELDNAMES_V2)
    rows = [
        'GCR_H,min,3,8,100.0,0.0,0,1,1e-10,1e-12,200,1e-10,1e-20,100,1e-19',
        'GCR_H,min,3,16,100.0,0.0,0,1,2e-10,2e-12,200,2e-10,2e-20,200,2e-19',
    ]
    (tmp_path/'resultados_organo_sweep.csv').write_text(header + '\n' + '\n'.join(rows) + '\n')

    job = dict(species='GCR_H', phase='min', bin_index=3, n_bins=16, offset_x_m=0., repeticion=0)
    result = worker.filter_results_csv(job, tmp_path, worker.RESULTS_FIELDNAMES_V2)
    lines = [l for l in result.splitlines() if l]
    assert len(lines) == 2  # header + 1 fila (solo la de n_bins=16)
    assert ',16,' in lines[1]


def test_filter_results_csv_tolerates_extra_columns_for_v1(tmp_path):
    # Bug real encontrado 2026-09-20: resultados_organo_sweep.csv ahora
    # SIEMPRE trae n_bins/s1_j/s2_j2/n/se_run_j (ver run_organ_sweep.py) --
    # un job v1 (fieldnames=RESULTS_FIELDNAMES, sin esas columnas) no debe
    # fallar por eso (extrasaction='ignore').
    header = ','.join(worker.RESULTS_FIELDNAMES_V2)
    row = 'GCR_H,min,0,8,10.0,0.0,0,1,1e-10,1e-12,200,1e-10,1e-20,100,1e-19'
    (tmp_path/'resultados_organo_sweep.csv').write_text(header + '\n' + row + '\n')

    job = dict(species='GCR_H', phase='min', bin_index=0, offset_x_m=0., repeticion=0)  # sin n_bins -- job v1
    result = worker.filter_results_csv(job, tmp_path)  # fieldnames default = RESULTS_FIELDNAMES (v1)
    lines = [l for l in result.splitlines() if l]
    assert len(lines) == 2
    assert 's1_j' not in lines[0]  # header v1, sin las columnas nuevas


def test_cleanup_orphaned_simulations_kills_only_job_dir_processes(tmp_path, monkeypatch):
    # Bug real de produccion (2026-09-20, ver infra/OPERATIONS_LOG.md):
    # procesos ICRP110phantoms huerfanos en tania, hasta 24h vivos.
    # Verifica las DOS correcciones de diseño discutidas con el equipo:
    # (a) el filtro es por cwd dentro de geant4-job-*, NO por nombre de
    # binario solo -- un proceso con el mismo nombre en cualquier OTRO
    # directorio (ej. una corrida manual del usuario en bryam-local)
    # nunca se toca.
    import subprocess
    monkeypatch.setattr(worker, '_ORPHAN_BINARY_NAME', 'sleep')  # sustituto de ICRP110phantoms para el test

    job_dir = tmp_path / 'geant4-job-abc123'
    job_dir.mkdir()
    orphan = subprocess.Popen(['sleep', '30'], cwd=job_dir, start_new_session=True)

    normal_dir = tmp_path / 'manual-run'
    normal_dir.mkdir()
    manual = subprocess.Popen(['sleep', '30'], cwd=normal_dir, start_new_session=True)

    try:
        time.sleep(0.3)
        killed = worker.cleanup_orphaned_simulations()
        time.sleep(0.3)

        assert orphan.pid in killed
        assert manual.pid not in killed
        assert orphan.poll() is not None, 'el huerfano en geant4-job-* debe matarse'
        assert manual.poll() is None, 'una corrida en un directorio normal NUNCA debe tocarse'
    finally:
        for p in (orphan, manual):
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=5)


def test_cleanup_orphaned_simulations_increments_counter_and_logs_diagnostics(tmp_path, monkeypatch, capsys):
    # Pedido explicito del equipo tras el incidente de tania (2026-09-20):
    # si el problema reaparece, el dato que faltó esa vez (pid/ppid/pgid/
    # sid/cwd reales del huerfano) debe quedar registrado sin que nadie
    # tenga que entrar a la maquina a sacarlo a mano -- y el conteo
    # acumulado debe quedar visible sin acceso directo (ver heartbeat()).
    import subprocess
    monkeypatch.setattr(worker, '_ORPHAN_BINARY_NAME', 'sleep')
    monkeypatch.setattr(worker, '_orphans_killed_total', 0)

    job_dir = tmp_path / 'geant4-job-diag'
    job_dir.mkdir()
    orphan = subprocess.Popen(['sleep', '30'], cwd=job_dir, start_new_session=True)
    try:
        time.sleep(0.3)
        killed = worker.cleanup_orphaned_simulations()
        assert orphan.pid in killed
        assert worker._orphans_killed_total == 1

        out = capsys.readouterr().out
        assert f'pid={orphan.pid}' in out
        assert 'ppid=' in out and 'pgid=' in out and 'sid=' in out
        assert str(job_dir) in out
        assert 'total acumulado en este proceso: 1' in out
    finally:
        if orphan.poll() is None:
            orphan.terminate()
            orphan.wait(timeout=5)


def test_heartbeat_reports_orphans_killed_total(monkeypatch):
    # El contador debe viajar en el payload del heartbeat -- ver
    # db.touch_heartbeat()/GET /api/v1/workers del lado del coordinator.
    monkeypatch.setattr(worker, '_orphans_killed_total', 3)
    monkeypatch.setattr(worker, 'ram_free_gb', lambda: None)
    monkeypatch.setattr(worker, 'cpu_load_pct', lambda: None)
    monkeypatch.setattr(worker, 'self_image_digest', lambda: None)

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured['json'] = json
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {}
        return resp

    with patch.object(worker.SESSION, 'post', side_effect=fake_post):
        worker.heartbeat('w1')

    assert captured['json']['orphans_killed_total'] == 3


@pytest.mark.parametrize("ignore_term", [False, True])
def test_run_job_kills_subprocess_when_cancel_event_set(tmp_path, monkeypatch, ignore_term):
    # Reproduce el mecanismo de remote-kill de punta a punta: un
    # subprocess real de larga duracion (sleep, no Geant4) que
    # run_job() debe matar en cuanto _cancel_event se activa -- no una
    # simulacion de la logica, el subprocess de verdad corre y se mata.
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    monkeypatch.setattr(worker, 'REPO_ROOT', tmp_path)
    (tmp_path / 'geant4/ActiveShield_Sim/data/sources/oltaris').mkdir(parents=True)
    command = [sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'] if ignore_term else ['sleep', '30']
    monkeypatch.setattr(worker, 'build_command', lambda job, work=None: command)

    start_response = MagicMock()
    start_response.raise_for_status.return_value = None
    with patch.object(worker.SESSION, 'post', return_value=start_response):
        failure = {}

        def fake_report_failure(worker_id, job_id, error, duration_s, api_version='v1'):
            failure.update(worker_id=worker_id, job_id=job_id, error=error, duration_s=duration_s)

        monkeypatch.setattr(worker, 'report_failure', fake_report_failure)
        result_called = []
        monkeypatch.setattr(worker, 'report_result', lambda *a, **k: result_called.append(a))

        timer = worker.threading.Timer(0.3, lambda: worker.deliver_cancellation(worker._active_cancel, 42))
        timer.start()
        try:
            started = time.monotonic()
            worker.run_job('w1', dict(job_id=42, species='GCR_He', bin_index=7, offset_x_m=3.0))
            elapsed = time.monotonic() - started
        finally:
            timer.cancel()

    # Si el subprocess de verdad se hubiera dejado correr, esto tardaria
    # ~30s (el sleep completo) -- matarlo bien debe terminar en segundos.
    assert elapsed < 10, f"el subprocess no se mato a tiempo (tardo {elapsed:.1f}s)"
    assert not result_called, "un job cancelado no debe reportarse como exitoso"
    assert failure.get('job_id') == 42
    assert 'cancelado' in failure.get('error', '')
    assert worker._active_cancel is None


def test_filter_excludes_other_repetitions(tmp_path):
    job = dict(species='SEP_p', phase='max', bin_index=1, offset_x_m=1., repeticion=2)
    with (tmp_path/'resultados_organo_sweep.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=worker.RESULTS_FIELDNAMES)
        w.writeheader()
        for rep in [0, 2]:
            w.writerow(dict(especie='SEP_p',fase='max',bin_index=1,offset_x_m=1.,repeticion=rep))
    assert len(list(csv.DictReader(io.StringIO(worker.filter_results_csv(job, tmp_path))))) == 1


def test_tail_log_returns_last_n_lines(tmp_path):
    log_path = tmp_path / 'run.log'
    log_path.write_text('\n'.join(f'line {i}' for i in range(100)) + '\n')
    tail = worker.tail_log(log_path, n_lines=5)
    assert tail == '\n'.join(f'line {i}' for i in range(95, 100)) + '\n'


def test_tail_log_missing_file_returns_none(tmp_path):
    assert worker.tail_log(tmp_path / 'nope.log') is None


def test_get_active_log_tail_none_when_no_job_active(monkeypatch):
    monkeypatch.setattr(worker, '_active_log_path', None)
    assert worker.get_active_log_tail() is None


def test_get_active_log_tail_reads_from_active_path(tmp_path, monkeypatch):
    log_path = tmp_path / 'active.log'
    log_path.write_text('Event 4200 of 10000\n')
    monkeypatch.setattr(worker, '_active_log_path', log_path)
    assert worker.get_active_log_tail() == 'Event 4200 of 10000\n'


def test_heartbeat_uploads_log_when_coordinator_requests_it(monkeypatch, tmp_path):
    # Mismo patron que el remote-kill: la solicitud viaja en la respuesta
    # del heartbeat (request_log=true), y el worker sube el tail con un
    # POST aparte a /jobs/{id}/log -- no en el mismo request del
    # heartbeat, para no inflar el caso comun (nadie lo pidio).
    context = (42, worker.threading.Event(), 1)
    monkeypatch.setattr(worker, '_active_cancel', context)
    monkeypatch.setattr(worker, '_active_log_context', context)
    path = tmp_path / 'log'
    path.write_text('Event 100 of 10000\n')
    monkeypatch.setattr(worker, '_active_log_path', path)

    heartbeat_resp = MagicMock()
    heartbeat_resp.raise_for_status.return_value = None
    heartbeat_resp.json.return_value = {'cancel_job_id': None, 'request_log': True, 'log_request': {'job_id':42, 'attempt':1, 'request_id':'a'*32}}

    log_upload_calls = []

    def fake_post(url, **kwargs):
        if url.endswith('/heartbeat'):
            return heartbeat_resp
        if url.endswith('/log'):
            log_upload_calls.append(kwargs.get('json'))
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            return resp
        raise AssertionError(f'unexpected POST to {url}')

    with patch.object(worker.SESSION, 'post', side_effect=fake_post):
        worker.heartbeat('w1')

    assert len(log_upload_calls) == 1
    # job_id va en la URL (/jobs/{job_id}/log), no en el body -- solo
    # worker_id y log_tail viajan como payload.
    assert log_upload_calls[0] == {'worker_id': 'w1', 'log_tail': 'Event 100 of 10000\n', 'attempt':1, 'request_id':'a'*32}


def test_heartbeat_does_not_upload_log_when_not_requested(monkeypatch):
    monkeypatch.setattr(worker, '_active_cancel', (42, worker.threading.Event()))

    heartbeat_resp = MagicMock()
    heartbeat_resp.raise_for_status.return_value = None
    heartbeat_resp.json.return_value = {'cancel_job_id': None, 'request_log': False}

    with patch.object(worker.SESSION, 'post', return_value=heartbeat_resp) as mock_post:
        worker.heartbeat('w1')

    assert mock_post.call_count == 1  # solo el propio heartbeat, ningun POST a /log


def test_report_log_noop_without_active_job(monkeypatch):
    monkeypatch.setattr(worker, 'get_active_log_tail', lambda: None)
    with patch.object(worker.SESSION, 'post') as mock_post:
        worker.report_log('w1', 42)
    mock_post.assert_not_called()


def test_run_job_kills_stalled_subprocess_via_watchdog(tmp_path, monkeypatch):
    # Watchdog de progreso (2026-09-16, ver AGENTS.md "el job de tania
    # perdio 10.1h sin ningun reencolado"): un subprocess real que corre
    # de verdad pero nunca escribe nada a su log (equivalente a un
    # colgado genuino de Geant4, sin progreso). El watchdog debe matarlo
    # solo, sin depender de cancel_event ni de que el coordinator lo
    # detecte por connected_s -- esa es justamente la deteccion que
    # faltaba y motivo este cambio.
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    monkeypatch.setattr(worker, 'REPO_ROOT', tmp_path)
    (tmp_path / 'geant4/ActiveShield_Sim/data/sources/oltaris').mkdir(parents=True)
    # Umbrales de prueba MUCHO mas cortos que los reales (20min/30s) --
    # solo se valida el MECANISMO (mata un proceso sin progreso), no el
    # valor de produccion en si.
    monkeypatch.setattr(worker, '_STALL_CHECK_INTERVAL_S', 1.0)
    monkeypatch.setattr(worker, '_STALL_TIMEOUT_S', 2.0)
    monkeypatch.setattr(worker, '_STALL_ACTION', 'kill')
    # 'sleep 30' nunca escribe a logs_organ/ -- cae al fallback
    # stdout_path (worker_stdout.log), que tampoco crece porque el
    # comando no imprime nada. Simula el caso real: un subprocess vivo,
    # consumiendo CPU o no, pero sin ningun progreso observable.
    monkeypatch.setattr(worker, 'build_command', lambda job, work=None: ['sleep', '30'])

    start_response = MagicMock()
    start_response.raise_for_status.return_value = None
    with patch.object(worker.SESSION, 'post', return_value=start_response):
        failure = {}
        monkeypatch.setattr(worker, 'report_failure',
                             lambda worker_id, job_id, error, duration_s, api_version='v1': failure.update(error=error))
        monkeypatch.setattr(worker, 'report_result', lambda *a, **k: pytest.fail('no debe reportarse como exitoso'))

        started = time.monotonic()
        worker.run_job('w1', dict(job_id=99, species='GCR_He', bin_index=7, offset_x_m=0.0))
        elapsed = time.monotonic() - started

    # Si el watchdog no actuara, esto tardaria ~30s (el sleep completo).
    assert elapsed < 15, f"el subprocess estancado no se mato a tiempo (tardo {elapsed:.1f}s)"
    assert 'sin progreso' in failure.get('error', '')


def _reset_pending_results(tmp_path, monkeypatch):
    # PENDING_RESULTS_DIR/get_stale_job_timeout_s se calculan una sola
    # vez a nivel de modulo -- redirigidos aqui a un tmp_path por test y
    # con la cache de timeout limpia, para que los tests no compartan
    # estado ni toquen el filesystem real.
    monkeypatch.setattr(worker, 'PENDING_RESULTS_DIR', tmp_path / 'pending_results')
    monkeypatch.setattr(worker, '_stale_job_timeout_s', None)


def test_report_result_retries_then_succeeds_and_cleans_up(tmp_path, monkeypatch):
    _reset_pending_results(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, '_REPORT_RESULT_BACKOFF_S', 0)  # no dormir de verdad en el test
    monkeypatch.setattr(worker, 'get_stale_job_timeout_s', lambda: 3600.0)

    responses = [requests.ConnectionError('red caida'), requests.ConnectionError('red caida'), MagicMock()]
    responses[2].json.return_value = {'job_id': 5, 'status': 'done', 'n_rows': 142}
    responses[2].raise_for_status.return_value = None

    def fake_post(url, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch.object(worker.SESSION, 'post', side_effect=fake_post):
        worker.report_result('w1', 5, 0, 12.3, 'especie,bin_index\nGCR_H,0\n', 'manifest\n')

    assert not (worker.PENDING_RESULTS_DIR / '5').exists()


def test_report_result_discards_on_http_error_without_retrying(tmp_path, monkeypatch):
    # Reproduce el caso real: el coordinator ya reasigno el job a otro
    # worker (409) mientras el nuestro no tenia conexion -- no es un
    # problema de red, no debe reintentar, y el resultado NO debe quedar
    # persistido para siempre en PENDING_RESULTS_DIR (a diferencia del
    # caso de deadline vencido, donde si se conserva para revision).
    _reset_pending_results(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, '_REPORT_RESULT_BACKOFF_S', 0)
    monkeypatch.setattr(worker, 'get_stale_job_timeout_s', lambda: 3600.0)

    response = MagicMock()
    response.status_code = 409
    response.raise_for_status.side_effect = requests.HTTPError('409 Conflict', response=response)

    with patch.object(worker.SESSION, 'post', return_value=response):
        worker.report_result('w1', 9, 0, 7.0, 'especie,bin_index\nGCR_H,0\n', 'manifest\n')

    assert not (worker.PENDING_RESULTS_DIR / '9').exists()


def test_report_result_gives_up_after_deadline_keeps_file(tmp_path, monkeypatch):
    _reset_pending_results(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, '_REPORT_RESULT_BACKOFF_S', 0)
    # Deadline ya vencido desde el momento en que se guarda (timeout 0)
    # -- el primer fallo de red ya debe rendirse, sin loop infinito.
    monkeypatch.setattr(worker, 'get_stale_job_timeout_s', lambda: 0.0)

    with patch.object(worker.SESSION, 'post', side_effect=requests.ConnectionError('red caida')):
        worker.report_result('w1', 7, 0, 5.0, 'especie,bin_index\nSEP_p,1\n', 'manifest\n')

    job_dir = worker.PENDING_RESULTS_DIR / '7'
    assert job_dir.is_dir()  # el resultado real sigue a salvo en disco
    assert (job_dir / 'results.csv').read_text() == 'especie,bin_index\nSEP_p,1\n'


def test_retry_pending_results_uploads_and_cleans_up(tmp_path, monkeypatch):
    _reset_pending_results(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, 'get_stale_job_timeout_s', lambda: 3600.0)

    job_dir = worker.PENDING_RESULTS_DIR / '9'
    job_dir.mkdir(parents=True)
    (job_dir / 'data.json').write_text(json.dumps({
        'worker_id': 'w1', 'exit_code': '0', 'duration_s': '1.0', 'created_at': time.time(),
    }))
    (job_dir / 'results.csv').write_text('especie,bin_index\nGCR_He,3\n')
    (job_dir / 'manifest.csv').write_text('manifest\n')

    resp = MagicMock()
    resp.json.return_value = {'job_id': 9, 'status': 'done', 'n_rows': 1}
    resp.raise_for_status.return_value = None
    with patch.object(worker.SESSION, 'post', return_value=resp):
        worker.retry_pending_results()

    assert not job_dir.exists()


def test_retry_pending_results_discards_past_deadline_without_uploading(tmp_path, monkeypatch):
    _reset_pending_results(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, 'get_stale_job_timeout_s', lambda: 3600.0)

    job_dir = worker.PENDING_RESULTS_DIR / '11'
    job_dir.mkdir(parents=True)
    (job_dir / 'data.json').write_text(json.dumps({
        'worker_id': 'w1', 'exit_code': '0', 'duration_s': '1.0',
        'created_at': time.time() - 7200,  # hace 2h, con timeout de 1h ya vencio
    }))
    (job_dir / 'results.csv').write_text('especie,bin_index\nGCR_H,4\n')
    (job_dir / 'manifest.csv').write_text('manifest\n')

    with patch.object(worker.SESSION, 'post') as mock_post:
        worker.retry_pending_results()
        mock_post.assert_not_called()  # ya es tarde, ni se intenta -- el coordinator ya lo reencolo

    assert not job_dir.exists()  # se descarta, no queda ocupando espacio para siempre


def _fake_container_info(image, name='geant4-worker', env=None, host_config=None):
    return {
        'Image': image,
        'Config': {'Image': f'{image.split("@")[0]}:latest', 'Env': env or ['FOO=bar']},
        'HostConfig': host_config or {'RestartPolicy': {'Name': 'unless-stopped'}},
        'Name': f'/{name}',
    }


def test_self_image_digest_none_without_docker(monkeypatch):
    monkeypatch.setattr(worker.DOCKER, 'available', lambda: False)
    assert worker.self_image_digest() is None


def test_auto_update_noop_without_docker(monkeypatch):
    monkeypatch.setattr(worker, 'self_image_digest', lambda: None)
    assert worker.auto_update('w1') is False


def test_auto_update_noop_when_digest_matches(monkeypatch):
    digest = 'sha256:' + 'a' * 64
    monkeypatch.setattr(worker, 'self_image_digest', lambda: digest)
    monkeypatch.setattr(worker, 'get_desired_image_digest', lambda: digest)
    assert worker.auto_update('w1') is False


def test_auto_update_noop_when_coordinator_has_no_digest(monkeypatch):
    monkeypatch.setattr(worker, 'self_image_digest', lambda: 'sha256:' + 'a' * 64)
    monkeypatch.setattr(worker, 'get_desired_image_digest', lambda: None)
    assert worker.auto_update('w1') is False


import pytest

OLD = 'sha256:' + 'a' * 64
NEW = 'sha256:' + 'b' * 64
REPO = 'localhost:5000/org/worker'


@pytest.fixture
def update_case(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'WORKER_ID_FILE', tmp_path / 'worker_id')
    worker.WORKER_ID_FILE.write_text('w1')
    monkeypatch.setattr(worker, '_UPDATE_RETRY_AFTER', 0)
    monkeypatch.setattr(worker, 'self_image_digest', lambda: OLD)
    monkeypatch.setattr(worker, 'get_desired_image_digest', lambda: NEW)
    monkeypatch.setattr(worker.platform, 'node', lambda: 'parent')
    monkeypatch.setattr(worker, 'self_container_id', lambda: 'parent')
    monkeypatch.setattr(worker, '_AUTO_UPDATE_VERIFY_POLL_S', 0)
    monkeypatch.setattr(worker, '_AUTO_UPDATE_VERIFY_TIMEOUT_S', .05)
    docker = MagicMock()
    info = {
        'Id': 'parent', 'Image': 'config-id-not-registry-digest', 'Name': '/geant4-worker',
        'Config': {'Image': f'{REPO}@{OLD}', 'Env': ['WORKER_LABEL=test', 'WORKER_UPDATE_TOKEN=obsolete'],
                   'Labels': {'custom': 'preserve'}},
        'HostConfig': {'NetworkMode': 'bridge', 'RestartPolicy': {'Name': 'unless-stopped'},
                       'Binds': [f'data:{tmp_path}', '/var/run/docker.sock:/var/run/docker.sock'],
                       'NanoCpus': 2000000000, 'Memory': 4000000000},
        'Mounts': [{'Type': 'volume', 'Destination': str(tmp_path), 'RW': True}],
    }
    docker.inspect_container.return_value = info
    docker.inspect_image.return_value = {'Config': {'Labels': {worker.UPDATE_PROTOCOL_LABEL: '1'}}}
    docker.create_container.return_value = 'b' * 64
    docker.is_running.return_value = True
    monkeypatch.setattr(worker, 'DOCKER', docker)
    return docker, info


def acknowledge_candidate(docker):
    def start(container):
        env = docker.create_container.call_args.args[2]
        token = next(e.split('=', 1)[1] for e in env if e.startswith('WORKER_UPDATE_TOKEN='))
        worker.write_update_state(worker.update_path(token, 'ready'), {
            'token': token, 'worker_id': 'w1', 'digest': NEW, 'container': container[:12]})
    docker.start_container.side_effect = start


def test_update_commit_preserves_identity_name_limits_labels(update_case):
    docker, info = update_case
    acknowledge_candidate(docker)
    assert worker.auto_update('w1') is True
    docker.pull_image.assert_called_once_with(REPO, NEW)
    args, kwargs = docker.create_container.call_args
    assert args[1] == f'{REPO}@{NEW}'
    assert args[3]['NanoCpus'] == 2000000000
    assert args[3]['Memory'] == 4000000000
    assert args[3]['Binds'] == info['HostConfig']['Binds']
    assert args[3]['RestartPolicy'] == {'Name': 'no'}
    assert info['HostConfig']['RestartPolicy'] == {'Name': 'unless-stopped'}
    assert kwargs['labels'] == {'custom': 'preserve'}
    assert sum(e.startswith('WORKER_UPDATE_TOKEN=') for e in args[2]) == 1
    docker.rename_container.assert_any_call('b' * 64, 'geant4-worker')
    docker.set_restart_policy.assert_any_call('parent', {'Name': 'no'})
    docker.remove_container.assert_not_called()  # no self-SIGKILL!
    assert len(list(worker.WORKER_ID_FILE.parent.glob('*.commit'))) == 1


def test_old_heartbeat_never_confirms_candidate(update_case):
    docker, _ = update_case
    with patch.object(worker.SESSION, 'get') as get:
        get.return_value.json.return_value = [{'worker_id': 'w1', 'seconds_since_heartbeat': 0}]
        assert worker.auto_update('w1') is False
    docker.remove_container.assert_called_once_with('b' * 64, force=True)
    docker.rename_container.assert_not_called()


def test_start_failure_cleans_created_candidate(update_case):
    docker, _ = update_case
    docker.start_container.side_effect = worker.docker_client.DockerAPIError('connection lost')
    assert worker.auto_update('w1') is False
    docker.remove_container.assert_called_once_with('b' * 64, force=True)


def test_rename_failure_restores_old_name_and_policy(update_case):
    docker, _ = update_case
    acknowledge_candidate(docker)
    docker.rename_container.side_effect = [None, worker.docker_client.DockerAPIError('conflict'), None]
    assert worker.auto_update('w1') is False
    docker.remove_container.assert_called_once_with('b' * 64, force=True)
    assert docker.rename_container.call_args.args == ('parent', 'geant4-worker')
    docker.set_restart_policy.assert_not_called()  # padre mantiene su politica hasta commit
    assert not list(worker.WORKER_ID_FILE.parent.glob('*.commit'))


def test_missing_protocol_does_not_start_legacy_image(update_case):
    docker, _ = update_case
    docker.inspect_image.return_value = {'Config': {}}
    assert worker.auto_update('w1') is False
    docker.create_container.assert_not_called()


def test_missing_persistence_does_not_update(update_case):
    docker, info = update_case
    info['Mounts'] = []
    assert worker.auto_update('w1') is False
    docker.pull_image.assert_not_called()


def test_update_failure_has_cooldown(update_case):
    docker, _ = update_case
    docker.pull_image.side_effect = worker.docker_client.DockerAPIError('offline')
    assert worker.auto_update('w1') is False
    assert worker.auto_update('w1') is False
    docker.pull_image.assert_called_once()


def test_update_disabled(update_case, monkeypatch):
    docker, _ = update_case
    monkeypatch.setenv('WORKER_AUTO_UPDATE', '0')
    assert worker.auto_update('w1') is False
    docker.create_container.assert_not_called()


def test_registry_digest_not_config_id(update_case, monkeypatch):
    docker, info = update_case
    # fixture replaces self_image_digest, load original function for this check
    fn = spec.loader.get_code('worker_under_test')  # use isolated module, no main
    namespace = {'__file__': worker.__file__, '__name__': 'digest_test'}
    exec(fn, namespace)
    namespace['DOCKER'] = docker
    namespace['self_container_id'] = lambda: 'parent'
    assert namespace['self_image_digest']() == OLD
    info['Config']['Image'] = REPO + ':latest'
    docker.inspect_image.return_value = {'RepoDigests': [REPO + '@' + NEW]}
    assert namespace['self_image_digest']() == NEW


def test_standby_heartbeat_failure_never_readies(update_case, monkeypatch):
    token = 'a' * 32
    monkeypatch.setenv('WORKER_UPDATE_TOKEN', token)
    monkeypatch.setattr(worker, 'self_image_digest', lambda: NEW)
    worker.write_update_state(worker.update_path(token, 'request'), {'digest': NEW, 'worker_id': 'w1', 'parent': 'parent'})
    with patch.object(worker.SESSION, 'post') as post:
        post.return_value.raise_for_status.side_effect = requests.HTTPError('401')
        with pytest.raises(requests.HTTPError):
            worker.prepare_replacement()
    assert not worker.update_path(token, 'ready').exists()


def test_standby_waits_for_commit_after_own_heartbeat(update_case, monkeypatch):
    token = 'a' * 32
    monkeypatch.setenv('WORKER_UPDATE_TOKEN', token)
    monkeypatch.setattr(worker, 'self_image_digest', lambda: NEW)
    worker.write_update_state(worker.update_path(token, 'request'), {'digest': NEW, 'worker_id': 'w1', 'parent': 'parent'})
    def commit(_):
        assert worker.update_path(token, 'ready').exists()
        worker.write_update_state(worker.update_path(token, 'commit'), {'committed': True})
    monkeypatch.setattr(worker.time, 'sleep', commit)
    with patch.object(worker.SESSION, 'post') as post, patch.object(worker, 'poll_next_job') as poll:
        worker.prepare_replacement()
        post.return_value.raise_for_status.assert_called_once()
        poll.assert_not_called()


def test_volume_lock_excludes_second_process(tmp_path, monkeypatch):
    import subprocess
    import sys
    monkeypatch.setattr(worker, 'WORKER_ID_FILE', tmp_path / 'worker_id')
    code = '''import fcntl, sys
f=open(sys.argv[1], 'a')
try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError: sys.exit(3)
'''
    with worker.worker_lock():
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path / 'worker.lock')])
        assert result.returncode == 3
    assert subprocess.run([sys.executable, '-c', code, str(tmp_path / 'worker.lock')]).returncode == 0


def test_create_timeout_cleans_by_candidate_name(update_case):
    docker, _ = update_case
    docker.create_container.side_effect = worker.docker_client.DockerAPIError('timeout after create')
    assert worker.auto_update('w1') is False
    assert docker.remove_container.call_args.args[0].startswith('geant4-worker-update-')


def test_restart_after_commit_retires_parent_without_claiming(update_case):
    docker, _ = update_case
    acknowledge_candidate(docker)
    assert worker.auto_update('w1') is True
    assert worker.recover_interrupted_update() is False
    docker.set_restart_policy.assert_called_with('parent', {'Name': 'no'})


def test_restart_before_commit_restores_canonical_parent(update_case):
    docker, _ = update_case
    token = 'a' * 32
    worker.write_update_state(worker.update_path(token, 'request'), {
        'parent': 'parent', 'candidate_name': 'geant4-worker-update-123',
        'replacement': 'child', 'original_name': 'geant4-worker'})
    assert worker.recover_interrupted_update() is True
    docker.remove_container.assert_called_once_with('child', force=True)
    docker.rename_container.assert_called_once_with('parent', 'geant4-worker')
    assert json.loads(worker.update_path(token, 'request').read_text())['aborted'] is True


def test_target_with_null_labels_is_rejected_without_crash(update_case):
    docker, _ = update_case
    docker.inspect_image.return_value = {'Config': {'Labels': None}}
    assert worker.auto_update('w1') is False
    docker.create_container.assert_not_called()


def test_container_identity_with_host_network(monkeypatch):
    container = 'c' * 64
    monkeypatch.setattr(worker.platform, 'node', lambda: 'shared-hostname')
    with patch.object(Path, 'read_text', return_value=f'42 1 0:1 /var/lib/docker/containers/{container}/hostname /etc/hostname rw - ext4 /dev/test rw'):
        assert worker.self_container_id() == container


def test_unknown_container_identity_does_not_guess(monkeypatch):
    monkeypatch.setattr(worker.platform, 'node', lambda: 'shared-hostname')
    with patch.object(Path, 'read_text', return_value='0::/'):
        assert worker.self_container_id() is None


def test_empty_user_and_missing_image_user_are_same_default(update_case):
    docker, info = update_case
    info['Config']['User'] = ''
    acknowledge_candidate(docker)
    assert worker.auto_update('w1') is True


def test_late_heartbeat_cannot_cancel_another_attempt(monkeypatch):
    old = (42, worker.threading.Event())
    current = (42, worker.threading.Event())
    monkeypatch.setattr(worker, '_active_cancel', current)
    worker.deliver_cancellation(old, 42)
    worker.deliver_cancellation(current, 43)
    assert not current[1].is_set()
    worker.deliver_cancellation(current, 42)
    assert current[1].is_set()


@pytest.mark.parametrize('payload', [[], None, {'cancel_job_id': '42'}, {'cancel_job_id': True}])
def test_malformed_heartbeat_does_not_cancel(payload):
    with patch.object(worker.SESSION, 'post') as post:
        post.return_value.json.return_value = payload
        assert worker.heartbeat('w') is None


def test_process_already_exited_is_not_a_cancellation():
    with patch.object(worker.os, 'killpg', side_effect=ProcessLookupError):
        assert worker.terminate_process_group(MagicMock(pid=123), .01) is False


def test_commit_visible_after_fsync_error_keeps_successor(update_case, monkeypatch):
    docker, _ = update_case
    acknowledge_candidate(docker)
    original = worker.write_update_state
    def write(path, state):
        original(path, state)
        if path.suffix == '.commit':
            raise OSError('directory fsync failed after rename')
    monkeypatch.setattr(worker, 'write_update_state', write)
    assert worker.auto_update('w1') is True
    docker.remove_container.assert_not_called()


def test_failure_survives_network_outage_and_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'WORKER_ID_FILE', tmp_path / 'worker_id')
    with patch.object(worker.SESSION, 'post', side_effect=requests.ConnectionError('offline')):
        worker.report_failure('w', 42, 'cancelado', 1)
        assert worker.retry_pending_failures() is False
    assert (tmp_path / 'pending_failures/42.json').is_file()
    with patch.object(worker.SESSION, 'post') as post:
        post.return_value.status_code = 200
        assert worker.retry_pending_failures() is True
        assert post.call_args.kwargs['json']['worker_id'] == 'w'
    assert not (tmp_path / 'pending_failures/42.json').exists()


@pytest.mark.parametrize('status', [401, 429, 500, 503])
def test_transient_http_preserves_outbox_for_restart(tmp_path, monkeypatch, status):
    _reset_pending_results(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, 'get_stale_job_timeout_s', lambda: 3600)
    response = requests.Response()
    response.status_code = status
    error = requests.HTTPError('retry later', response=response)
    with patch.object(worker, '_post_result', side_effect=error):
        worker.report_result('w', 5, 0, 1, 'results', 'manifest')
        worker.retry_pending_results()
    assert (worker.PENDING_RESULTS_DIR / '5/results.csv').read_text() == 'results'
    with patch.object(worker, '_post_result', return_value={'status': 'done'}):
        worker.retry_pending_results()
    assert not (worker.PENDING_RESULTS_DIR / '5').exists()


def test_expired_result_is_archived_not_lost(tmp_path, monkeypatch):
    _reset_pending_results(tmp_path, monkeypatch)
    monkeypatch.setattr(worker, 'get_stale_job_timeout_s', lambda: 1)
    worker._save_pending_result(5, {'worker_id':'w', 'created_at':0}, 'valuable-result', 'manifest')
    worker.retry_pending_results()
    archived = list((tmp_path / 'unconfirmed_results').glob('*/results.csv'))
    assert len(archived) == 1
    assert archived[0].read_text() == 'valuable-result'


def test_late_log_response_does_not_upload_next_jobs_log(monkeypatch, tmp_path):
    old = (42, worker.threading.Event(), 1)
    new = (43, worker.threading.Event(), 1)
    monkeypatch.setattr(worker, '_active_cancel', old)
    monkeypatch.setattr(worker, '_active_log_context', new)
    path = tmp_path / 'new.log'
    path.write_text('next job secret')
    monkeypatch.setattr(worker, '_active_log_path', path)
    response = MagicMock()
    response.json.return_value = {'request_log':True, 'log_request':{'job_id':42,'attempt':1,'request_id':'a'*32}}
    def post(*args, **kwargs):
        worker._active_cancel = new
        return response
    with patch.object(worker.SESSION, 'post', side_effect=post) as mocked:
        worker.heartbeat('w')
    assert mocked.call_count == 1


def test_tail_memory_is_bounded_for_single_huge_line(tmp_path):
    path = tmp_path / 'large.log'
    with path.open('wb') as stream:
        stream.truncate(10_000_000)
        stream.seek(0, 2)
        stream.write(b'last-line')
    result = worker.tail_log(path)
    assert len(result) <= 65536
    assert result.endswith('last-line')


@pytest.mark.parametrize('action', ['warn', 'off'])
def test_silence_does_not_kill_without_opt_in(monkeypatch, tmp_path, action):
    monkeypatch.setattr(worker, 'WORKER_ID_FILE', tmp_path / 'worker_id')
    monkeypatch.setattr(worker, '_STALL_ACTION', action)
    monkeypatch.setattr(worker, '_STALL_TIMEOUT_S', .1)
    monkeypatch.setattr(worker, '_STALL_CHECK_INTERVAL_S', .05)
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    monkeypatch.setattr(worker, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(worker, 'build_command', lambda *a: ['sleep', '1'])
    monkeypatch.setattr(worker, 'filter_results_csv', lambda *a: 'complete')
    monkeypatch.setattr(worker, 'read_manifest_csv', lambda *a: 'manifest')
    with patch.object(worker.SESSION, 'post'), patch.object(worker, 'report_result') as result, patch.object(worker, 'report_failure') as failure:
        worker.run_job('w', {'job_id':42,'species':'SEP_p','bin_index':0,'offset_x_m':0,'attempt':1})
    result.assert_called_once()
    failure.assert_not_called()

    captures = list((tmp_path / 'diagnostics').glob('*.json'))
    assert bool(captures) == (action == 'warn')


def test_heartbeat_refreshes_image_digest(monkeypatch):
    from unittest.mock import Mock
    digest = 'sha256:' + 'a' * 64
    monkeypatch.setattr(worker, 'self_image_digest', lambda: digest)
    response = Mock()
    response.json.return_value = {}
    post = Mock(return_value=response)
    monkeypatch.setattr(worker.SESSION, 'post', post)
    worker.heartbeat('w')
    assert post.call_args.kwargs['json']['image_digest'] == digest
    monkeypatch.setattr(worker, 'self_image_digest', lambda: None)
    worker.heartbeat('w')
    assert post.call_args.kwargs['json']['image_digest'] is None


def test_check_geant4_environment_ok_when_exit_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    completed = MagicMock(returncode=0, stdout='', stderr='')
    with patch.object(worker.subprocess, 'run', return_value=completed) as run:
        assert worker.check_geant4_environment() is None
    run.assert_called_once()


def test_check_geant4_environment_detects_missing_conda_env(monkeypatch, tmp_path):
    # Reproduce la firma real observada en produccion (2026-09-15, ver
    # AGENTS.md): sin 'conda activate geant4_env', el binario SI arranca
    # (RPATH resuelve las .so) pero Geant4 aborta con SIGABRT (134) por
    # no encontrar G4ENSDFSTATEDATA -- no un exit_code cualquiera, uno
    # medido en vivo con el fallo real reproducido a proposito.
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    completed = MagicMock(
        returncode=134, stdout='',
        stderr='G4ENSDFSTATEDATA environment variable must be set\n*** Fatal Exception *** core dump ***')
    with patch.object(worker.subprocess, 'run', return_value=completed):
        error = worker.check_geant4_environment()
    assert error is not None
    assert 'exit_code=134' in error
    assert 'conda activate' in error


def test_check_geant4_environment_reports_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    with patch.object(worker.subprocess, 'run', side_effect=worker.subprocess.TimeoutExpired('cmd', 20)):
        error = worker.check_geant4_environment()
    assert error is not None and 'respondio' in error


def test_main_exits_without_registering_when_env_check_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, 'RUN_ORGAN_SWEEP', tmp_path / 'run_organ_sweep.py')
    worker.RUN_ORGAN_SWEEP.write_text('')
    monkeypatch.setattr(worker, 'BUILD_DIR', tmp_path)
    (tmp_path / 'ICRP110phantoms').write_text('')
    monkeypatch.setattr(worker, 'check_geant4_environment', lambda: 'entorno roto de prueba')
    register = MagicMock()
    monkeypatch.setattr(worker, 'register', register)
    with pytest.raises(SystemExit, match='entorno roto de prueba'):
        worker.main()
    register.assert_not_called()


def test_run_worker_loop_stops_after_consecutive_fast_failures(monkeypatch, tmp_path):
    # Reproduce el patron real de produccion: N jobs seguidos fallando
    # en segundos, sin ningun exito de por medio -- debe detener el
    # worker en vez de seguir quemando intentos de jobs reales
    # indefinidamente (ver AGENTS.md, "Bug real de robustez").
    monkeypatch.setattr(worker, 'WORKER_ID_FILE', tmp_path / 'worker_id')
    monkeypatch.setattr(worker, '_CONSECUTIVE_FAST_FAILURES_LIMIT', 3)
    monkeypatch.setattr(worker, 'get_or_create_worker_id', lambda: 'w1')
    monkeypatch.setattr(worker, 'register', lambda *a: None)
    monkeypatch.setattr(worker, 'retry_pending_results', lambda: None)
    monkeypatch.setattr(worker, 'retry_pending_failures', lambda: True)
    monkeypatch.setattr(worker, 'heartbeat', lambda *a: None)
    jobs = iter([{'job_id': i} for i in range(1, 10)])
    monkeypatch.setattr(worker, 'poll_next_job', lambda *a: next(jobs, None))
    monkeypatch.setattr(worker, 'run_job', lambda *a: (False, 2.0))  # fallo rapido cada vez
    with pytest.raises(SystemExit, match='3 fallos consecutivos'):
        worker.run_worker_loop()


def test_run_worker_loop_resets_streak_after_success(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, 'WORKER_ID_FILE', tmp_path / 'worker_id')
    monkeypatch.setattr(worker, '_CONSECUTIVE_FAST_FAILURES_LIMIT', 3)
    monkeypatch.setattr(worker, 'get_or_create_worker_id', lambda: 'w1')
    monkeypatch.setattr(worker, 'register', lambda *a: None)
    monkeypatch.setattr(worker, 'retry_pending_results', lambda: None)
    monkeypatch.setattr(worker, 'retry_pending_failures', lambda: True)
    monkeypatch.setattr(worker, 'heartbeat', lambda *a: None)
    # 2 fallos rapidos, 1 exito, 2 fallos rapidos mas -- nunca llega a 3
    # SEGUIDOS porque el exito de en medio resetea el contador. Tras
    # consumir los 5, se fuerza la salida del loop real (que de otro modo
    # seguiria haciendo poll indefinidamente con job=None) con una
    # excepcion marcador, no con time.sleep de verdad.
    outcomes = iter([(False, 2.0), (False, 2.0), (True, 500.0), (False, 2.0), (False, 2.0)])
    jobs = iter([{'job_id': i} for i in range(1, 6)])

    class _JobsExhausted(Exception):
        pass

    def fake_poll(*a):
        job = next(jobs, None)
        if job is None:
            raise _JobsExhausted()
        return job
    monkeypatch.setattr(worker, 'poll_next_job', fake_poll)
    monkeypatch.setattr(worker, 'run_job', lambda *a: next(outcomes))
    with pytest.raises(_JobsExhausted):
        worker.run_worker_loop()  # nunca debe salir por SystemExit de la racha
    assert next(jobs, None) is None  # confirma que efectivamente se consumieron los 5
