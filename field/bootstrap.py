#!/usr/bin/env python3
"""Create the isolated mesh/conversion environment without modifying Geant4 conda."""
from pathlib import Path
import subprocess
import sys
import venv

root = Path(__file__).resolve().parent
if sys.version_info[:2] != (3, 13):
    sys.exit('Use Python 3.13 (validated patch: 3.13.5, recorded in .python-version).')
venv.EnvBuilder(with_pip=True, symlinks=sys.platform != 'win32').create(root / '.venv')
python = root / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                '-r', str(root / 'requirements.txt')], check=True)
subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
subprocess.run([str(python), '-c',
    'import gmsh, numpy; print("Gmsh", gmsh.__version__, "NumPy", numpy.__version__)'], check=True)
print('Environment ready:', python)
