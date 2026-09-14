import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).with_name('set_worker_image.py')
spec = importlib.util.spec_from_file_location('set_image_test', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('invalid', ['junksha256:'+'a'*64, 'sha256:'+'a'*63, 'https://repo@sha256:'+'a'*64+'extra'])
def test_invalid_reference(invalid):
    with pytest.raises(ValueError):
        module.extract_digest(invalid)


def test_explicit_service_db_and_clear(tmp_path):
    path = tmp_path / 'service.db'
    sqlite3.connect(path).close()
    digest = 'sha256:'+'a'*64
    env = dict(os.environ)
    env.pop('COORDINATOR_DB', None)
    invalid = subprocess.run([sys.executable, str(SCRIPT), digest], env=env, capture_output=True)
    assert invalid.returncode != 0
    for args in ([digest], ['--show'], ['--clear']):
        result = subprocess.run([sys.executable, str(SCRIPT), '--db', str(path), *args], env=env, capture_output=True)
        assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT value FROM config WHERE key='worker_image_digest'").fetchone()[0] == ''
