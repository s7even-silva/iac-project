#!/usr/bin/env python3
"""Regularized Biot-Savart reference map for a multi-coil array (Halbach-style
superposition), reading array_current_paths.json from generate_array.py.

Same regularized-kernel caveats as compute_field.py: this is a development
reference map, not Elmer/FEM, and is not valid close to/inside a conductor.
See field/GEOM14_STATUS.md brechas 3-4 -- Elmer is the pending FEM solver.

Superposition is the only new physics here: total B at a point is the sum of
each coil's independent Biot-Savart contribution (field_at() from
compute_field.py is reused unchanged, once per coil, then summed). This is
exact for prescribed currents in vacuum/mu_r=1 media (magnetostatics is
linear), which is the same "corrientes prescritas" assumption already
documented as the initial operating point in GEOM14_STATUS.md.
"""
import argparse
import json
import math
from pathlib import Path
import platform

import numpy as np

from compute_field import field_at, grid_shape
from generate_mesh import digest


def generate(source, output, half_size, spacing, max_points):
    if output.suffix != '.map' or output.resolve() == source.resolve():
        raise ValueError('Use a distinct .map output')
    data = json.loads(source.read_text())
    coils = data['coils']
    if not coils:
        raise ValueError('Array report has no coils')
    n, step = grid_shape(half_size, spacing)
    if n**3 > max_points:
        raise ValueError(f'{n**3:,} nodes exceed --max-points={max_points:,}; plan/refine explicitly')
    if max(abs(v) for v in data['bounds_m']) >= half_size or half_size <= 5:
        raise ValueError('Map must enclose the full coil array and the habitat')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Each coil in generate_array.py's schema carries its own conductor
    # radius implicitly via its own config; array_current_paths.json does
    # not re-expose it per coil, so this reads it back from the array config
    # embedded in the report. Matched by name explicitly (not by list
    # position) so this does not silently mispair radius-to-coil if the two
    # lists are ever reordered independently.
    config_by_name = {c['name']: c['config'] for c in data['config']['coils']}
    paths = [np.asarray(coil['path_m']) for coil in coils]
    currents = [coil['current_A'] for coil in coils]
    cores = [config_by_name[coil['name']]['conductor_radius_m'] for coil in coils]
    edge_max = 0.0
    temporary = output.with_suffix(output.suffix + '.tmp')
    try:
        with temporary.open('w') as f:
            f.write(f'# PILOT regularized Biot-Savart, {len(coils)}-coil superposition; m and T; not production\n')
            f.write(f'{n} {n} {n}\n{-half_size} {-half_size} {-half_size}\n{step} {step} {step}\n')
            for first in range(0, n**3, 4096):
                indices = np.arange(first, min(first + 4096, n**3))
                ijk = np.column_stack((indices % n, indices // n % n, indices // (n * n)))
                points = -half_size + step * ijk
                values = np.zeros_like(points)
                for path, current, core in zip(paths, currents, cores):
                    values += field_at(points, path, current, core)
                edge = np.any((ijk == 0) | (ijk == n - 1), axis=1)
                if np.any(edge):
                    edge_max = max(edge_max, float(np.max(np.linalg.norm(values[edge], axis=1))))
                np.savetxt(f, values, fmt='%.12e')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {'model': 'closed_polygon_regularized_biot_savart_array_superposition_pilot',
              'path_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
              'map_sha256': digest(output), 'python': platform.python_version(),
              'numpy': np.__version__, 'platform': platform.platform(),
              'half_size_m': half_size, 'spacing_m': step, 'shape': [n] * 3,
              'n_coils': len(coils), 'currents_A': currents, 'core_radii_m': cores,
              'boundary_max_T': edge_max, 'production_validated': False}
    output.with_suffix('.field-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('array_report', type=Path, help='array_current_paths.json from generate_array.py')
    p.add_argument('output', type=Path)
    p.add_argument('--half-size', type=float, required=True, help='Map cube half-side in metres')
    p.add_argument('--spacing', type=float, required=True, help='Maximum uniform grid step in metres')
    p.add_argument('--max-points', type=int, default=1000000)
    a = p.parse_args()
    generate(a.array_report, a.output, a.half_size, a.spacing, a.max_points)
