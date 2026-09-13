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
    job = dict(species='GCR_He', bin_index=7, offset_x_m=3., repeticion=2, n_events=100)
    cmd = worker.build_command(job)
    assert cmd[cmd.index('--repetition-start')+1] == '2'
    assert cmd[cmd.index('--repeats')+1] == '1'
    assert cmd[cmd.index('--only-bins')+1] == '7'
    assert '--no-resume' in cmd


def test_header_only_is_not_result(tmp_path):
    (tmp_path/'resultados_organo_sweep.csv').write_text(','.join(worker.RESULTS_FIELDNAMES)+'\n')
    job = dict(species='SEP_p', bin_index=1, offset_x_m=1., repeticion=0)
    assert worker.filter_results_csv(job, tmp_path) == ''


def test_filter_excludes_other_repetitions(tmp_path):
    job = dict(species='SEP_p', bin_index=1, offset_x_m=1., repeticion=2)
    with (tmp_path/'resultados_organo_sweep.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=worker.RESULTS_FIELDNAMES)
        w.writeheader()
        for rep in [0, 2]:
            w.writerow(dict(especie='SEP_p',bin_index=1,offset_x_m=1.,repeticion=rep))
    assert len(list(csv.DictReader(io.StringIO(worker.filter_results_csv(job, tmp_path))))) == 1


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
