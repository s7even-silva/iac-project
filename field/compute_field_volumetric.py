#!/usr/bin/env python3
"""Volumetric Biot-Savart field map of the CREW HaT coil array, reading
array_current_paths.json from generate_ellipse_array.py. No FEM and no finite
domain: the map can be as large as the source sphere needs.

With no magnetic materials (mu_r = 1, the same assumption as the Elmer .sif),
the field of a prescribed current is exactly the Biot-Savart integral of its
current density. compute_field_ellipse_array.py puts each coil's whole current
on its centreline, which is wrong near a 0.67 m winding pack. Here each pack
is split into n_radial x n_axial parallel filaments with equal current (turns
in series give a uniform current density), laid out like the CAD rectangle:
radial across the coil plane, axial along its normal. What remains is
quadrature error (filaments, and segments per loop), measured by refining
both with validate_volumetric_field.py.

Each straight segment uses the exact line-current formula outside a round core
with the filament's own cross-section area, and the uniform round-wire profile
inside it, so the field stays finite inside the pack (solid conductor, where
the value matters little for transport).
"""
import argparse
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import time

import numpy as np

from compute_field import grid_shape
from generate_ellipse import pack_section
from provenance import digest


def filaments(path, radial, axial, n_radial, n_axial):
    """Closed polylines of the n_radial x n_axial filaments of one planar coil."""
    loop = np.asarray(path, dtype=float)[:-1]
    normal = np.cross(loop, np.roll(loop, -1, axis=0)).sum(0)  # Newell: right-handed with the current
    normal /= np.linalg.norm(normal)
    tangent = np.roll(loop, -1, axis=0)-np.roll(loop, 1, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    outward = np.cross(tangent, normal)
    lines = []
    for a in ((np.arange(n_radial)+.5)/n_radial-.5)*radial:
        for b in ((np.arange(n_axial)+.5)/n_axial-.5)*axial:
            line = loop+a*outward+b*normal
            lines.append(np.vstack((line, line[:1])))
    return lines


class Segments:
    """All straight segments of all filaments, ready for field()."""

    def __init__(self, data, n_radial, n_axial):
        if n_radial < 1 or n_axial < 1:
            raise ValueError('Require at least one filament per direction')
        radial, axial = pack_section(data['config']['coil_template'])
        self.core = math.sqrt(radial*axial/(n_radial*n_axial)/math.pi)
        start, end, current = [], [], []
        for coil in data['coils']:
            share = coil['current_A']/(n_radial*n_axial)
            for line in filaments(coil['path_m'], radial, axial, n_radial, n_axial):
                start.append(line[:-1])
                end.append(line[1:])
                current.append(np.full(len(line)-1, share))
        self.start = np.vstack(start)
        delta = np.vstack(end)-self.start
        self.length = np.linalg.norm(delta, axis=1)
        self.dir = delta/self.length[:, None]
        self.current = np.concatenate(current)


def field(points, seg, chunk_points=4096, chunk_segments=256):
    """B in tesla at points (N x 3, metres)."""
    points = np.asarray(points, dtype=float)
    out = np.zeros_like(points)
    core2 = seg.core**2
    for i in range(0, len(points), chunk_points):
        px, py, pz = (points[i:i+chunk_points, k][:, None] for k in range(3))
        bx = by = bz = 0.
        for j in range(0, len(seg.length), chunk_segments):
            part = slice(j, j+chunk_segments)
            ux, uy, uz = seg.dir[part].T
            rx, ry, rz = px-seg.start[part, 0], py-seg.start[part, 1], pz-seg.start[part, 2]
            cx, cy, cz = uy*rz-uz*ry, uz*rx-ux*rz, ux*ry-uy*rx  # u x r = u x rho
            q = cx*cx+cy*cy+cz*cz  # rho^2 without cancellation
            s = rx*ux+ry*uy+rz*uz
            e = s-seg.length[part]
            # Exact segment formula; max(q, core^2) switches to the uniform-wire core.
            f = (s/np.sqrt(q+s*s+1e-300)-e/np.sqrt(q+e*e+1e-300))*(seg.current[part]/np.maximum(q, core2))
            bx, by, bz = bx+(f*cx).sum(1), by+(f*cy).sum(1), bz+(f*cz).sum(1)
        out[i:i+chunk_points] = np.column_stack((bx, by, bz))
    return out*1e-7  # mu0/(4 pi)


def trilinear(values, origin, step, points):
    """Same interpolation as MagneticFieldMap::Evaluate (values: nz x ny x nx x 3)."""
    shape = np.array(values.shape[2::-1])
    cell = (points-origin)/step
    index = np.clip(np.floor(cell).astype(int), 0, shape-2)
    w = np.clip(cell-index, 0., 1.)
    out = np.zeros_like(points)
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                weight = ((w[:, 0] if dx else 1-w[:, 0])*(w[:, 1] if dy else 1-w[:, 1])
                          * (w[:, 2] if dz else 1-w[:, 2]))
                out += weight[:, None]*values[index[:, 2]+dz, index[:, 1]+dy, index[:, 0]+dx]
    return out


_SEGMENTS = None


def _init(seg):
    global _SEGMENTS
    _SEGMENTS = seg


def _plane(args):
    xs, ys, z = args
    x, y = np.meshgrid(xs, ys)  # x fastest, as the map format expects
    return field(np.column_stack((x.ravel(), y.ravel(), np.full(x.size, z))), _SEGMENTS)


def interpolation_check(values, origin, step, seg, n, seed=20261031):
    """Trilinear map against direct evaluation at n random points per region.
    Relative errors only where |B| >= 10 mT (the habitat centre is ~0)."""
    rng = np.random.default_rng(seed)
    upper = origin+step*(np.array(values.shape[2::-1])-1)
    def habitat(p):
        return (np.hypot(p[:, 0], p[:, 1]) < 4.5) & (np.abs(p[:, 2]) < 5)
    regions = {'habitat (r<4.5 m, |z|<5 m)': habitat,
               'coils (|p|<12 m, outside habitat)': lambda p: (np.linalg.norm(p, axis=1) < 12) & ~habitat(p),
               'outer (|p|>=12 m)': lambda p: np.linalg.norm(p, axis=1) >= 12}
    report = {}
    for name, inside in regions.items():
        points = np.empty((0, 3))
        for _ in range(1000):
            candidate = rng.uniform(np.maximum(origin, -12) if name != 'outer (|p|>=12 m)' else origin,
                                    np.minimum(upper, 12) if name != 'outer (|p|>=12 m)' else upper,
                                    size=(20*n, 3))
            points = np.vstack((points, candidate[inside(candidate)]))[:n]
            if len(points) == n:
                break
        direct = field(points, seg)
        error = np.linalg.norm(trilinear(values, origin, step, points)-direct, axis=1)*1e3
        magnitude = np.linalg.norm(direct, axis=1)*1e3
        strong = magnitude >= 10
        report[name] = {'points': len(points),
                        'error_mT_p50_p95_max': np.percentile(error, [50, 95, 100]).tolist(),
                        'field_mT_p50_p95': np.percentile(magnitude, [50, 95]).tolist(),
                        'relative_where_B_ge_10mT_p50_p95': (np.percentile(error[strong]/magnitude[strong], [50, 95]).tolist()
                                                             if strong.any() else None)}
    return report


def generate(source, output, half_size, spacing, n_radial, n_axial, processes, max_points, check_points):
    if output.suffix != '.map' or output.resolve() == source.resolve():
        raise ValueError('Use a distinct .map output')
    half = np.broadcast_to(np.asarray(half_size, dtype=float), 3)
    data = json.loads(source.read_text())
    bounds = np.asarray(data['bounds_m'], dtype=float)
    if np.any(np.maximum(-bounds[:3], bounds[3:]) >= half):
        raise ValueError('Map must enclose the whole coil array on every axis')
    sizes, steps = zip(*(grid_shape(h, spacing) for h in half))
    if math.prod(sizes) > max_points:
        raise ValueError(f'{math.prod(sizes):,} nodes exceed --max-points={max_points:,}')
    seg = Segments(data, n_radial, n_axial)
    axes = [-h+s*np.arange(n) for h, s, n in zip(half, steps, sizes)]
    start = time.monotonic()
    with mp.Pool(processes, initializer=_init, initargs=(seg,)) as pool:
        planes = pool.map(_plane, [(axes[0], axes[1], z) for z in axes[2]])
    elapsed = time.monotonic()-start
    values = np.stack(planes).reshape(sizes[2], sizes[1], sizes[0], 3)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    try:
        with temporary.open('w') as f:
            f.write(f'# Volumetric Biot-Savart, {len(data["coils"])} coils, {n_radial}x{n_axial} filaments; '
                    'm and T; not production\n')
            f.write(' '.join(map(str, sizes))+'\n'+' '.join(f'{-h}' for h in half)+'\n'
                    + ' '.join(map(str, steps))+'\n')
            np.savetxt(f, values.reshape(-1, 3), fmt='%.7e')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    edge = np.ones(values.shape[:3], dtype=bool)
    edge[1:-1, 1:-1, 1:-1] = False
    report = {'model': 'volumetric_biot_savart', 'production_validated': False,
              'array_report_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
              'map_sha256': digest(output), 'python': platform.python_version(),
              'numpy': np.__version__, 'platform': platform.platform(),
              'half_size_m': half.tolist(), 'spacing_m': list(steps), 'shape': list(sizes),
              'filaments_radial_axial': [n_radial, n_axial], 'filament_core_radius_m': seg.core,
              'segments_total': len(seg.length), 'currents_A': [c['current_A'] for c in data['coils']],
              'boundary_max_T': float(np.linalg.norm(values[edge], axis=1).max()),
              'processes': processes, 'compute_seconds': elapsed}
    if check_points:
        report['interpolation_check'] = interpolation_check(values, -half, np.array(steps), seg, check_points)
    output.with_suffix('.field-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('array_report', type=Path, help='array_current_paths.json from generate_ellipse_array.py')
    p.add_argument('output', type=Path)
    p.add_argument('--half-size', type=float, nargs='+', required=True, help='metres: one value, or x y z')
    p.add_argument('--spacing', type=float, required=True, help='maximum grid step in metres')
    p.add_argument('--filaments', type=int, nargs=2, required=True, metavar=('RADIAL', 'AXIAL'))
    p.add_argument('--processes', type=int, default=os.cpu_count())
    p.add_argument('--max-points', type=int, default=5000000)
    p.add_argument('--check-points', type=int, default=0,
                   help='random points per region where the trilinear map is compared with direct evaluation')
    a = p.parse_args()
    if len(a.half_size) not in (1, 3):
        p.error('--half-size takes one value or three (x y z)')
    generate(a.array_report, a.output, a.half_size, a.spacing, *a.filaments, a.processes,
             a.max_points, a.check_points)
