#!/usr/bin/env python3
"""Mesh a parameterized .geo with pinned single-thread settings and provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import gmsh


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(source, output, dependencies=()):
    source, output = Path(source), Path(output)
    inputs = [source, *map(Path, dependencies)]
    if source.suffix != '.geo' or output.suffix != '.msh':
        raise ValueError('Require .geo input and .msh output')
    if output.resolve() in {p.resolve() for p in inputs}:
        raise ValueError('Output must not overwrite input')
    hashes = {str(p): digest(p) for p in inputs}
    output.parent.mkdir(parents=True, exist_ok=True)
    settings = {'General.NumThreads': 1, 'Mesh.MaxNumThreads1D': 1,
                'Mesh.MaxNumThreads2D': 1, 'Mesh.MaxNumThreads3D': 1,
                'Mesh.RandomSeed': 1, 'Mesh.ElementOrder': 1,
                'Mesh.Algorithm': 6,
                # Retain the project's HXT choice. A stall in 1D/2D or in
                # OCC boolean operations is not evidence of an HXT failure.
                'Mesh.Algorithm3D': 10,
                'Mesh.MshFileVersion': 4.1, 'Mesh.Binary': 0, 'Mesh.SaveAll': 1}
    gmsh.initialize([], readConfigFiles=False)
    timings = {}
    try:
        start = time.monotonic()
        print(f'[mesh] Reading {source}', flush=True)
        gmsh.open(str(source))
        timings['read_s'] = time.monotonic()-start
        for name, value in settings.items():
            gmsh.option.setNumber(name, value)
        for dim in (1, 2, 3):
            print(f'[mesh] Starting {dim}D', flush=True)
            start = time.monotonic()
            gmsh.model.mesh.generate(dim)
            timings[f'mesh_{dim}d_s'] = time.monotonic()-start
            print(f'[mesh] Finished {dim}D in {timings[f"mesh_{dim}d_s"]:.3f} s', flush=True)
        gmsh.write(str(output))
    finally:
        gmsh.finalize()
    report = {'sources_sha256': hashes, 'generator_sha256': digest(Path(__file__)),
              'mesh_sha256': digest(output), 'gmsh': gmsh.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'settings': settings, 'timings': timings}
    output.with_suffix('.mesh-manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--dependency', action='append', type=Path, default=[],
                   help='Record each imported STEP/Include/parameter file (repeat as needed)')
    p.add_argument('--timeout', type=float, help='Wall-clock limit in seconds, enforced by a parent process')
    a = p.parse_args()
    if a.timeout is None:
        generate(a.source, a.output, a.dependency)
    else:
        if not (0 < a.timeout < float('inf')):
            p.error('--timeout must be finite and positive')
        command = [sys.executable, '-u', str(Path(__file__).resolve()), str(a.source), str(a.output)]
        for dependency in a.dependency:
            command.extend(['--dependency', str(dependency)])
        try:
            result = subprocess.run(command, timeout=a.timeout)
        except subprocess.TimeoutExpired:
            p.exit(124, f'[mesh] Stopped after {a.timeout:g} s; see last stage in log. Output is not validated.\n')
        raise SystemExit(result.returncode)
