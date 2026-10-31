#!/usr/bin/env python3
"""Validation of the volumetric Biot-Savart field (plan_piloto.md, P1 paso 2).

Probes in three groups, built from the array report:
- near_coil: coil 0, four stations (both ends of each axis of the ellipse),
  four directions (out of the pack across the coil plane, outward and inward,
  and out of its two flat faces), 0.05-2 m beyond the pack surface. This is
  where the filament quadrature is worst and where Elmer meshes are finest.
- habitat: 1 m grid inside the hull (r <= 4.5 m, |z| <= 5 m), where dose is
  scored; with the NIAC layout the field there is a small remainder.
- radial: lines from the axis to --radial-max at phi = 0, 22.5 and 45 deg in
  z = 0, and phi = 0 at z = 6 m, out to the source sphere candidates; points
  inside or touching a winding pack are dropped.

With --coil K only that coil is kept: with mu_r = 1 the field is linear in
the currents, so validating one coil validates the array, and a single coil
avoids the habitat cancellation that hides Elmer's per-coil error.

Comparisons, each against the finest Biot-Savart (the last --filaments pair):
1. coarser filament grids (self-convergence of the quadrature);
2. optional Elmer results (--vtu, coarse to fine), plus each Elmer result
   against the next one (Elmer's own refinement change).
Errors are |dB| in mT, and |dB|/|B| where |B| >= 1% of the group maximum.

To join the levels run on different PCs (coarse to fine):
    validate_volumetric_field.py --tendencia nivel_a.json nivel_b.json ...
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

from compute_field_volumetric import Segments, field
from elmer_to_map import load_vtu, resample
from generate_ellipse import pack_section
from provenance import digest


def probes(data, radial_max):
    radial, axial = pack_section(data['config']['coil_template'])
    loop = np.asarray(data['coils'][0]['path_m'], dtype=float)[:-1]
    normal = np.cross(loop, np.roll(loop, -1, axis=0)).sum(0)
    normal /= np.linalg.norm(normal)
    tangent = np.roll(loop, -1, axis=0)-np.roll(loop, 1, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    near = []
    for k in (0, len(loop)//4, len(loop)//2, 3*len(loop)//4):
        outward = np.cross(tangent[k], normal)
        for direction, half in ((outward, radial/2), (-outward, radial/2), (normal, axial/2), (-normal, axial/2)):
            near += [loop[k]+direction*(half+d) for d in (0.05, 0.1, 0.2, 0.5, 1.0, 2.0)]
    g = np.arange(-4.5, 4.51, 1.0)
    x, y, z = np.meshgrid(g, g, np.arange(-5, 5.01, 1.0), indexing='ij')
    habitat = np.column_stack((x.ravel(), y.ravel(), z.ravel()))
    habitat = habitat[np.hypot(habitat[:, 0], habitat[:, 1]) <= 4.5]
    r = np.arange(0.5, radial_max+1e-9, 0.5)
    lines = [np.column_stack((r*np.cos(np.radians(phi)), r*np.sin(np.radians(phi)), np.full_like(r, z0)))
             for phi, z0 in ((0, 0), (22.5, 0), (45, 0), (0, 6))]
    radial_points = np.vstack(lines)
    # Drop line points inside or touching a winding pack (solid conductor).
    clearance = np.hypot(radial, axial)/2+0.05
    centreline = np.vstack([c['path_m'] for c in data['coils']])
    distance = np.min(np.linalg.norm(radial_points[:, None]-centreline[None], axis=2), axis=1)
    return {'near_coil': np.array(near), 'habitat': habitat, 'radial': radial_points[distance > clearance]}


def stats(value, reference):
    valid = np.isfinite(value).all(axis=1)
    if not valid.any():  # the whole group lies outside the Elmer mesh
        return {'points': 0, 'outside_mesh': int(len(value)),
                'error_mT_p50_p95_max': [np.nan]*3, 'relative_p50_p95_max': [np.nan]*3}
    error = np.linalg.norm(value[valid]-reference[valid], axis=1)*1e3
    magnitude = np.linalg.norm(reference[valid], axis=1)*1e3
    keep = magnitude >= 0.01*magnitude.max()
    relative = error[keep]/magnitude[keep]
    return {'points': int(valid.sum()), 'outside_mesh': int((~valid).sum()),
            'error_mT_p50_p95_max': np.percentile(error, [50, 95, 100]).tolist(),
            'relative_p50_p95_max': np.percentile(relative, [50, 95, 100]).tolist()}


def trend(json_paths):
    """Elmer levels from several PCs (each its own validacion.json), on the
    probes valid in all of them: error against Biot-Savart per level, and the
    change between consecutive levels (Elmer's own refinement error)."""
    runs = [json.loads(Path(path).read_text()) for path in json_paths]
    reference = np.array(runs[0]['fields_T'][runs[0]['reference']])
    elmer = [np.array(next(v for k, v in run['fields_T'].items() if k.startswith('elmer:'))) for run in runs]
    valid = np.all([np.isfinite(e).all(axis=1) for e in elmer], axis=0)
    first = 0
    for group, block in runs[0]['probes'].items():
        rows = slice(first, first+len(block))
        first += len(block)
        keep = valid[rows]
        if not keep.any():
            continue
        ref = reference[rows][keep]
        scale = np.linalg.norm(ref, axis=1)
        print(f'{group} ({keep.sum()} sondas comunes): mediana / p95 del error relativo')
        for path, e in zip(json_paths, elmer):
            rel = np.linalg.norm(e[rows][keep]-ref, axis=1)/scale
            print(f'  {path}: frente a Biot-Savart {np.median(rel):.2%} / {np.percentile(rel, 95):.2%}')
        for (a, ea), (b, eb) in zip(zip(json_paths, elmer), list(zip(json_paths, elmer))[1:]):
            rel = np.linalg.norm(eb[rows][keep]-ea[rows][keep], axis=1)/scale
            print(f'  cambio {a} -> {b}: {np.median(rel):.2%} / {np.percentile(rel, 95):.2%}')


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--tendencia':
        trend(sys.argv[2:])
        return
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('array_report', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--filaments', type=int, nargs='+', required=True,
                   help='radial axial pairs, coarse to fine; the last pair is the reference')
    p.add_argument('--vtu', type=Path, nargs='*', default=[], help="Elmer *_air_t0001.vtu, coarse to fine")
    p.add_argument('--radial-max', type=float, default=18.0)
    p.add_argument('--coil', type=int, help='validate only this coil of the array (the problem is linear)')
    a = p.parse_args()
    if len(a.filaments) % 2:
        p.error('--filaments takes radial axial pairs')
    data = json.loads(a.array_report.read_text())
    if a.coil is not None:
        data['coils'] = [data['coils'][a.coil]]
    groups = probes(data, a.radial_max)
    points = np.vstack(list(groups.values()))
    slices, first = {}, 0
    for name, block in groups.items():
        slices[name] = slice(first, first+len(block))
        first += len(block)
    pairs = list(zip(a.filaments[::2], a.filaments[1::2]))
    fields = {f'bs_{nr}x{na}': field(points, Segments(data, nr, na)) for nr, na in pairs}
    reference_name = f'bs_{pairs[-1][0]}x{pairs[-1][1]}'
    for vtu in a.vtu:
        fields[f'elmer:{vtu}'] = resample(*load_vtu(vtu), points)
    comparisons = [(name, reference_name) for name in fields if name != reference_name]
    elmer = [name for name in fields if name.startswith('elmer:')]
    comparisons += list(zip(elmer[:-1], elmer[1:]))
    report = {'array_report_sha256': digest(a.array_report), 'reference': reference_name,
              'vtu_sha256': {str(v): digest(v) for v in a.vtu},
              'probes': {name: block.tolist() for name, block in groups.items()},
              'fields_T': {name: value.tolist() for name, value in fields.items()},
              'comparisons': []}
    for value, ref in comparisons:
        row = {'value': value, 'against': ref,
               'groups': {g: stats(fields[value][s], fields[ref][s]) for g, s in slices.items()}}
        report['comparisons'].append(row)
        print(f'{value} vs {ref}')
        for g, st in row['groups'].items():
            e, r = st['error_mT_p50_p95_max'], st['relative_p50_p95_max']
            print(f'  {g:9s} |dB| p50/p95/max = {e[0]:.3g}/{e[1]:.3g}/{e[2]:.3g} mT; '
                  f'relativo {r[0]:.2%}/{r[1]:.2%}/{r[2]:.2%}; fuera de malla {st["outside_mesh"]}')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=1)+'\n')


if __name__ == '__main__':
    main()
