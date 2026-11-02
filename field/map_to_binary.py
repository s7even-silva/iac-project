#!/usr/bin/env python3
"""Convierte un mapa de campo de texto (.map) al binario .bmap que lee
TabulatedMagneticField.cc: misma grilla y mismo orden, componentes en float32
(compute_field_volumetric.write_binary). El mapa de ±30 m pasa de 609 a
~170 MB, y Geant4 lo lee sin pasar por texto.

Lee el texto por bloques (poca memoria), relee el binario y lo compara con el
texto, y escribe <salida>.bmap-manifest.json: el manifiesto del mapa de texto
(si está al lado) con el sha256 nuevo, el del texto y la diferencia máxima.

Uso, desde field/:
    .venv/bin/python map_to_binary.py ENTRADA.map SALIDA.bmap
"""
import argparse
import itertools
import json
from pathlib import Path

import numpy as np

from compute_field_volumetric import BINARY_MAGIC, manifest_path, read_map, text_header
from provenance import digest

ROWS = 1_000_000


def text_blocks(path):
    """Cabecera del mapa de texto y sus valores en bloques de ROWS nodos (float64)."""
    f = open(path)
    header = text_header(f)

    def blocks():
        with f:
            while lines := list(itertools.islice(f, ROWS)):
                yield np.loadtxt(lines, comments='#', ndmin=2)
    return header, blocks()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    if a.output.suffix != '.bmap':
        p.error('la salida tiene que terminar en .bmap')
    (sizes, origin, steps), blocks = text_blocks(a.source)
    count = int(np.prod(sizes))
    temporary = a.output.with_suffix('.bmap.tmp')
    written = 0
    with temporary.open('wb') as f:
        f.write(BINARY_MAGIC+np.array(sizes, '<u8').tobytes()+np.array([*origin, *steps], '<f8').tobytes())
        for block in blocks:
            f.write(np.ascontiguousarray(block, '<f4').data)
            written += len(block)
    if written != count:
        temporary.unlink()
        raise SystemExit(f'{a.source}: {written} nodos, la cabecera dice {count}')
    temporary.replace(a.output)

    values, origin2, steps2 = read_map(a.output)
    assert np.array_equal(origin2, origin) and np.array_equal(steps2, steps)
    flat, start, worst = values.reshape(-1, 3), 0, 0.0
    for block in text_blocks(a.source)[1]:
        got = flat[start:start+len(block)]
        floor = np.maximum(np.linalg.norm(block, axis=1), 1e-3)  # T
        worst = max(worst, float((np.linalg.norm(got-block, axis=1)/floor).max()))
        start += len(block)
    print(f'{a.output}: {count} nodos, diferencia relativa máxima con el texto {worst:.1e}')

    source_manifest = manifest_path(a.source)
    report = json.loads(source_manifest.read_text()) if source_manifest.is_file() else {}
    if report.get('map_sha256') not in (None, digest(a.source)):
        raise SystemExit(f'{source_manifest} no corresponde a {a.source}')
    report.update(map_sha256=digest(a.output), format='IACBMAP1 float32', source_map_sha256=digest(a.source),
                  converter_sha256=digest(Path(__file__)), max_relative_difference_vs_source=worst)
    manifest_path(a.output).write_text(json.dumps(report, indent=2)+'\n')
    print(f'-> {manifest_path(a.output)}')


if __name__ == '__main__':
    main()
