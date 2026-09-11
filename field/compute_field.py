#!/usr/bin/env python3
"""Regularized Biot-Savart reference map for the DH pilot (not Elmer/FEM)."""
import argparse
import json
import math
from pathlib import Path
import platform

import numpy as np
from provenance import digest

def field_at(points, path, current, core_radius):
    """Analytic integral per straight segment of a softened 1/r^3 kernel.

    core_radius=0 gives the filament field off the wire. Positive core is a
    numerical pilot approximation, NOT the exact field inside a finite wire.
    """
    points, path = np.asarray(points, dtype=float), np.asarray(path, dtype=float)
    if (points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all()
            or path.ndim != 2 or path.shape[1] != 3 or len(path) < 4
            or not np.isfinite(path).all() or not np.array_equal(path[0], path[-1])
            or not np.isfinite([current, core_radius]).all() or core_radius < 0):
        raise ValueError('Require a finite closed path, current and nonnegative core')
    result = np.zeros_like(points)
    for start, end in zip(path[:-1], path[1:]):
        delta = end-start
        length = np.linalg.norm(delta)
        if length <= 1e-14:
            raise ValueError('Zero-length current segment')
        direction = delta/length
        r = points-start
        s = r @ direction
        rho = r-s[:, None]*direction
        q = np.sum(rho*rho, axis=1)+core_radius**2
        if np.any(q == 0):
            raise ValueError('Filament-axis singularity: use a positive pilot core')
        factor = (s/np.sqrt(q+s*s)-(s-length)/np.sqrt(q+(s-length)**2))/q
        result += np.cross(direction, rho)*factor[:, None]
    return result*(1e-7*current)  # mu0/(4 pi), SI approximation adequate for pilot.


def grid_shape(half_size, spacing):
    if not np.isfinite([half_size, spacing]).all() or half_size <= 0 or spacing <= 0:
        raise ValueError('Positive finite half size and spacing required')
    n = math.ceil(2*half_size/spacing)+1
    return n, 2*half_size/(n-1)


def generate(source, output, half_size, spacing, max_points):
    if output.suffix != '.map' or output.resolve() == source.resolve():
        raise ValueError('Use a distinct .map output')
    data = json.loads(source.read_text())
    n, step = grid_shape(half_size, spacing)
    if n**3 > max_points:
        raise ValueError(f'{n**3:,} nodes exceed --max-points={max_points:,}; plan/refine explicitly')
    if max(abs(v) for v in data['bounds_m']) >= half_size or half_size <= 5:
        raise ValueError('Map must enclose conductor and the full habitat')
    output.parent.mkdir(parents=True, exist_ok=True)
    path = np.asarray(data['path_m'])
    core = data['conductor_radius_m']
    edge_max = 0.0
    temporary = output.with_suffix(output.suffix+'.tmp')
    try:
        with temporary.open('w') as f:
            f.write('# PILOT regularized Biot-Savart; m and T; not production\n')
            f.write(f'{n} {n} {n}\n{-half_size} {-half_size} {-half_size}\n{step} {step} {step}\n')
            for first in range(0, n**3, 4096):
                indices = np.arange(first, min(first+4096, n**3))
                ijk = np.column_stack((indices % n, indices//n % n, indices//(n*n)))
                points = -half_size+step*ijk
                values = field_at(points, path, data['current_A'], core)
                edge = np.any((ijk == 0) | (ijk == n-1), axis=1)
                if np.any(edge):
                    edge_max = max(edge_max, float(np.max(np.linalg.norm(values[edge], axis=1))))
                np.savetxt(f, values, fmt='%.12e')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {'model': 'closed_polygon_regularized_biot_savart_pilot',
              'path_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
              'map_sha256': digest(output), 'python': platform.python_version(),
              'numpy': np.__version__, 'platform': platform.platform(),
              'half_size_m': half_size, 'spacing_m': step, 'shape': [n]*3,
              'current_A': data['current_A'], 'core_radius_m': core,
              'boundary_max_T': edge_max, 'production_validated': False}
    output.with_suffix('.field-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('path', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--half-size', type=float, required=True, help='Map cube half-side in metres')
    p.add_argument('--spacing', type=float, required=True, help='Maximum uniform grid step in metres')
    p.add_argument('--max-points', type=int, default=1000000)
    a = p.parse_args()
    generate(a.path, a.output, a.half_size, a.spacing, a.max_points)
