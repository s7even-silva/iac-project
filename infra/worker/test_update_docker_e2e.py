"""Opt-in local Docker handoff test. No Geant4 jobs, registry pushes or production API.

RUN_DOCKER_UPDATE_E2E=1 pytest -q infra/worker/test_update_docker_e2e.py
Uses an existing local worker image as base (UPDATE_TEST_BASE_IMAGE can override).
Registry resolution/pull is replaced with local fixture tags; the handoff, worker
main loop, Docker create/start/rename/restart-policy/remove and data lock are real.
"""
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.getenv('RUN_DOCKER_UPDATE_E2E') != '1', reason='Opt-in Docker fixture')
SOURCE = Path(__file__).parent


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.STDOUT, timeout=120).strip()


@pytest.mark.parametrize('reject_candidate', [False, True])
def test_real_handoff(tmp_path, reject_candidate):
    prefix = 'iac-update-test-' + uuid.uuid4().hex[:10]
    name = prefix + '-worker'
    volume = prefix + '-data'
    tags = [prefix + ':old', prefix + ':new']
    desired = 'sha256:' + 'b' * 64
    registrations, polls, heartbeats = [], [], []
    class API(http.server.BaseHTTPRequestHandler):
        def respond(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            assert self.path == '/api/v1/health'
            self.respond(200, {'worker_image_digest': desired, 'stale_job_timeout_s': 3600})
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            instance = self.headers['X-Fixture-Instance']
            if self.path.endswith('/register'):
                registrations.append((instance, data))
                self.respond(200, {})
            elif self.path.endswith('/heartbeat'):
                heartbeats.append(instance)
                self.respond(503 if reject_candidate and instance != registrations[0][0] else 200, {})
            elif self.path.endswith('/jobs/next'):
                polls.append(instance)
                self.respond(200, None)
            else:
                self.respond(404, {})
        def log_message(self, *_):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), API)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    harness = '''import os, platform
from pathlib import Path
import worker
worker.REPO_ROOT = Path('/opt/iac-project')
worker.RUN_ORGAN_SWEEP = worker.REPO_ROOT / 'geant4/ActiveShield_Sim/scripts/run_organ_sweep.py'
worker._AUTO_UPDATE_VERIFY_TIMEOUT_S = 8
worker._AUTO_UPDATE_VERIFY_POLL_S = .1
worker.self_image_digest = lambda: Path('/fixture/digest').read_text().strip()
worker.cpu_score = lambda: 1.0
worker.SESSION.headers['X-Fixture-Instance'] = worker.self_container_id()
worker.DOCKER.pull_image = lambda *args: None
inspect = worker.DOCKER.inspect_image
create = worker.DOCKER.create_container
worker.DOCKER.inspect_image = lambda ref: inspect(os.environ['FIXTURE_NEW_TAG'] if '@' in ref else ref)
worker.DOCKER.create_container = lambda name, image, env, host_config, labels=None: create(name, os.environ['FIXTURE_NEW_TAG'], env, host_config, labels)
worker.main()
'''
    for filename in ('worker.py', 'docker_client.py'):
        (tmp_path / filename).write_text((SOURCE / filename).read_text())
    (tmp_path / 'harness.py').write_text(harness)
    base = os.getenv('UPDATE_TEST_BASE_IMAGE', 'ghcr.io/s7even-silva/iac-project/geant4-worker:latest')
    (tmp_path / 'Dockerfile').write_text(f'''FROM {base}
COPY worker.py docker_client.py harness.py digest /fixture/
LABEL org.iac.worker-update-protocol="1"
CMD ["python3", "/fixture/harness.py"]
''')
    try:
        for tag, character in zip(tags, ('a', 'b')):
            (tmp_path / 'digest').write_text('sha256:' + character * 64)
            docker('build', '--pull=false', '--network=none', '-t', tag, str(tmp_path))
        docker('volume', 'create', volume)
        docker('run', '-d', '--name', name, '--network', 'host', '--restart', 'unless-stopped',
               '--cpus', '1', '--memory', '2g',
               '-v', f'{volume}:/var/lib/geant4-worker', '-v', '/var/run/docker.sock:/var/run/docker.sock',
               '-e', f'FIXTURE_NEW_TAG={tags[1]}', '-e', f'COORDINATOR_URL=http://127.0.0.1:{server.server_port}',
               '-e', 'POLL_INTERVAL_S=0.2', '-e', 'HEARTBEAT_INTERVAL_S=1',
               '-e', 'WORKER_LABEL=isolated-fixture', tags[0])
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and not polls:
            time.sleep(.2)
        assert polls, docker('logs', name)
        info = json.loads(docker('inspect', name))[0]
        assert info['State']['Running']
        assert info['Config']['Image'] == tags[0 if reject_candidate else 1], docker('logs', name)
        assert info['HostConfig']['NanoCpus'] == 1000000000
        assert info['HostConfig']['Memory'] == 2 * 1024**3
        assert info['HostConfig']['RestartPolicy']['Name'] == 'unless-stopped'
        assert len(registrations) == (1 if reject_candidate else 2)
        assert any(instance != registrations[0][0] for instance in heartbeats), 'Candidate never attempted its own heartbeat'
        assert all(instance == info['Id'] for instance in polls)
        if not reject_candidate:
            assert registrations[0][1]['worker_id'] == registrations[1][1]['worker_id']
            assert registrations[0][0] != registrations[1][0]
        instances = docker('ps', '-a', '--filter', f'name={prefix}', '--format', '{{.Names}}').splitlines()
        assert instances == [name], instances
    finally:
        # Only our random prefix, never docker prune or any shared service.
        for container in docker('ps', '-a', '--filter', f'name={prefix}', '--format', '{{.Names}}').splitlines():
            docker('rm', '-f', container)
        for tag in tags:
            subprocess.run(['docker', 'image', 'rm', tag], capture_output=True)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)
        server.shutdown()
        server.server_close()
        thread.join()
