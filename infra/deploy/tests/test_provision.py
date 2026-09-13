"""Provisioning regressions with fake CLIs; never create cloud resources."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

DEPLOY = Path(__file__).resolve().parents[1]

class ProvisionTests(unittest.TestCase):
    def run_script(self, script, args=(), fail_firewall=False, unset=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'calls'
            cli = '''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
  'config get-value project') echo "${PROJECT_TEST:-test-project}" ;;
  'billing projects describe '*) echo True ;;
  'compute firewall-rules describe '*) exit 1 ;;
  'compute firewall-rules create '*) exit "${FAIL_FIREWALL:-0}" ;;
esac
'''
            for name in ('az', 'gcloud'):
                path = root / name
                path.write_text(cli)
                path.chmod(0o755)
            env = dict(os.environ, PATH=f'{root}:/usr/bin:/bin', HOME=directory,
                       CALLS=str(log), FAIL_FIREWALL=str(int(fail_firewall)),
                       PROJECT_TEST='(unset)' if unset else 'test-project')
            result = subprocess.run(['bash', str(DEPLOY / script), *args], env=env,
                                    text=True, capture_output=True, timeout=10)
            return result, log.read_text() if log.exists() else ''

    def test_azure_documented_arguments(self):
        result, calls = self.run_script('provision_azure_coordinator.sh',
                                       ['--location', 'westus', '--vm-size', 'Standard_B2s'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--location westus', calls)
        self.assertIn('--size Standard_B2s', calls)

    def test_azure_missing_value(self):
        result, calls = self.run_script('provision_azure_coordinator.sh', ['--location'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, '')

    def test_firewall_failure_stops_vm_creation(self):
        result, calls = self.run_script('provision_gcp_coordinator.sh', fail_firewall=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('compute instances create', calls)

    def test_unset_project(self):
        result, calls = self.run_script('provision_gcp_coordinator.sh', unset=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('compute instances create', calls)

if __name__ == '__main__':
    unittest.main()
