#!/usr/bin/env python3
"""Mesh a parameterized .geo with pinned single-thread settings and provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
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
                'Mesh.Algorithm': 6, 'Mesh.Algorithm3D': 1,
                'Mesh.MshFileVersion': 4.1, 'Mesh.Binary': 0, 'Mesh.SaveAll': 1}
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.open(str(source))
        for name, value in settings.items():
            gmsh.option.setNumber(name, value)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(output))
    finally:
        gmsh.finalize()
    report = {'sources_sha256': hashes, 'generator_sha256': digest(Path(__file__)),
              'mesh_sha256': digest(output), 'gmsh': gmsh.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'settings': settings}
    output.with_suffix('.mesh-manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--dependency', action='append', type=Path, default=[],
                   help='Record each imported STEP/Include/parameter file (repeat as needed)')
    a = p.parse_args()
    generate(a.source, a.output, a.dependency)
