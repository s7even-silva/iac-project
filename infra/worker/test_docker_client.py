"""Real HTTP over a temporary Unix socket; never uses the host Docker daemon."""
import http.server
import importlib.util
import json
from pathlib import Path
import socketserver
import threading
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location('docker_api_test', Path(__file__).with_name('docker_client.py'))
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


@pytest.fixture
def engine(tmp_path):
    requests = []
    replies = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def handle_request(self):
            data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            requests.append((self.command, self.path, json.loads(data) if data else None))
            status, body = replies.pop(0)
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = do_DELETE = handle_request
        def log_message(self, *_):
            pass
    class Server(socketserver.UnixStreamServer):
        pass
    path = str(tmp_path / 'docker.sock')
    server = Server(path, Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield client.DockerClient(path), replies, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_engine_pull_create_start_rename_policy_remove(engine):
    docker, replies, requests = engine
    replies.extend([(200, b'{"status":"done"}\n'), (201, b'{"Id":"child"}'),
                    (204, b''), (204, b''), (200, b'{}'), (204, b'')])
    docker.pull_image('localhost:5000/repo', 'sha256:'+'a'*64)
    assert docker.create_container('candidate', 'repo@sha256:x', ['X=y'],
                                   {'RestartPolicy': {'Name': 'no'}}, {'keep': 'yes'}) == 'child'
    docker.start_container('child')
    docker.rename_container('child', 'geant4-worker')
    docker.set_restart_policy('child', {'Name': 'unless-stopped'})
    docker.remove_container('parent')
    assert 'localhost%3A5000%2Frepo' in requests[0][1]
    assert requests[1][2]['Labels'] == {'keep': 'yes'}
    assert requests[4][2]['RestartPolicy']['Name'] == 'unless-stopped'
    assert requests[5][1].endswith('force=false')


def test_pull_200_with_stream_error_is_failure(engine):
    docker, replies, _ = engine
    replies.append((200, b'{"status":"pulling"}\n{"errorDetail":{"message":"denied"}}\n'))
    with pytest.raises(client.DockerAPIError):
        docker.pull_image('repo', 'sha256:x')


def test_transport_failure_is_normalized(tmp_path):
    docker = client.DockerClient(str(tmp_path / 'missing.sock'))
    assert docker.available() is False
    with pytest.raises(client.DockerAPIError):
        docker.start_container('child')
