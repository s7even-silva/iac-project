#!/usr/bin/env python3
"""Build a local Elmer CoilSolver fix; leaves the installed Elmer untouched.

The pinned LGPL-2.1-or-later upstream source and its copyright notice are
preserved in generated output. The modification restricts cut construction to
active conductor elements, excluding air tetrahedra that join cut candidates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

COMMIT = '063e7e9f0bd647386f8f3b14e86cd7cff9c7d895'
SOURCE_SHA256 = 'a7c55bdbf214ca1f568da14612b762d188b8654c9d537332a65b5df60cf172f8'
URL = f'https://raw.githubusercontent.com/ElmerCSC/elmerfem/{COMMIT}/fem/src/modules/CoilSolver.F90'


def patched_source(raw):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unsupported upstream source hash: inspect/rebase the patch explicitly')
    source = raw.decode('utf-8')
    for name in ('ChooseFixedBulkNodesNarrow', 'ChooseCoilCut'):
        start = source.index('  SUBROUTINE '+name+'(') if name == 'ChooseCoilCut' else source.index('  SUBROUTINE '+name+'( ')
        end = source.index('  END SUBROUTINE '+name, start)
        part = source[start:end]
        part = part.replace('DO t=1,Mesh % NumberOfBulkElements', 'DO t=1,GetNOFActive()')
        part = part.replace('DO t = 1, Mesh % NumberOfBulkElements', 'DO t = 1, GetNOFActive()')
        part = part.replace('Element => Mesh % Elements(t)', 'Element => GetActiveElement(t)')
        source = source[:start]+part+source[end:]
    return source


def build(output, source=None, elmerf90=None):
    raw = source.read_bytes() if source else urllib.request.urlopen(URL, timeout=30).read()
    patched = patched_source(raw)
    compiler = elmerf90 or shutil.which('elmerf90') or str(Path.home()/'.local/elmerfem/bin/elmerf90')
    if not Path(compiler).is_file():
        raise ValueError('Install Elmer first or supply --elmerf90 /path/to/elmerf90')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    upstream = output/'CoilSolver.upstream.F90'
    upstream.write_bytes(raw)
    target = output/'CoilSolverRestricted.F90'
    target.write_text(patched)
    library = output/'CoilSolverRestricted.so'
    temporary = output/'CoilSolverRestricted.partial.so'
    try:
        subprocess.run([str(Path(compiler).resolve()), str(target), '-o', str(temporary)],
                       cwd=output, check=True, timeout=120)
        temporary.replace(library)
    finally:
        temporary.unlink(missing_ok=True)
    report = {'upstream_commit': COMMIT, 'upstream_url': URL,
              'upstream_sha256': SOURCE_SHA256,
              'patched_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
              'elmerf90': str(Path(compiler).resolve()),
              'scope': 'Restrict closed-coil cut construction/coloring to active conductor elements'}
    (output/'build-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(library)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, help='Optional local, pinned CoilSolver.F90 (offline build)')
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parent/'generated/elmer_plugin')
    p.add_argument('--elmerf90', help='Use the wrapper from the same Elmer installation as ElmerSolver')
    a = p.parse_args()
    build(a.output, a.source, a.elmerf90)
