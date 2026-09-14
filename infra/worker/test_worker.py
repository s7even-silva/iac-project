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
