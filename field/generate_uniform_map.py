#!/usr/bin/env python3
"""Synthetic uniform-field .map, for dose sweeps before the real Geom14/CREW HaT
coil field is validated (see field/GEOM14_STATUS.md and field/ELMER_VALIDATION.md
for why that isn't ready yet). NOT a coil-derived field -- Bz is constant inside
the box and (per TabulatedMagneticField's own out-of-bounds rule) zero outside it.

One map generated at a reference 1 T is enough for a whole field-intensity sweep:
ActiveShield_Sim's /spacecraft/fieldScale multiplies the loaded map by a scalar
at evaluation time (see ICRP110PhantomConstruction.cc), so sweeping 7-10 T means
reusing this same file with --fieldScale 7..10, not regenerating it per value.
"""
import argparse
import json
import math
import platform
from pathlib import Path

import numpy as np
from provenance import digest


def grid_shape(half_size, spacing):
    if not np.isfinite([half_size, spacing]).all() or half_size <= 0 or spacing <= 0:
        raise ValueError('Positive finite half size and spacing required')
    n = math.ceil(2 * half_size / spacing) + 1
    return n, 2 * half_size / (n - 1)


def generate(output, half_size, spacing, bz_tesla, max_points):
    if output.suffix != '.map':
        raise ValueError('Use a .map output')
    n, step = grid_shape(half_size, spacing)
    if n**3 > max_points:
        raise ValueError(f'{n**3:,} nodes exceed --max-points={max_points:,}; plan/refine explicitly')
    output.parent.mkdir(parents=True, exist_ok=True)
    field_vector = np.array([0.0, 0.0, bz_tesla])
    temporary = output.with_suffix(output.suffix + '.tmp')
    try:
        with temporary.open('w') as f:
            f.write(f'# Synthetic uniform field, Bz={bz_tesla} T inside the box, '
                     'zero outside (TabulatedMagneticField default); m and T; not a coil field\n')
            f.write(f'{n} {n} {n}\n{-half_size} {-half_size} {-half_size}\n{step} {step} {step}\n')
            values = np.tile(field_vector, (n**3, 1))
            np.savetxt(f, values, fmt='%.12e')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {'model': 'synthetic_uniform_field', 'generator_sha256': digest(Path(__file__)),
              'map_sha256': digest(output), 'python': platform.python_version(),
              'numpy': np.__version__, 'platform': platform.platform(),
              'half_size_m': half_size, 'spacing_m': step, 'shape': [n] * 3,
              'bz_tesla_reference': bz_tesla,
              'note': 'Reference field only -- sweep intensity via /spacecraft/fieldScale, '
                      'do not regenerate this file per intensity value.',
              'production_validated': False}
    output.with_suffix('.field-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('output', type=Path)
    p.add_argument('--half-size', type=float, required=True,
                    help='Map cube half-side in metres -- must enclose the ship '
                         '(half-diagonal sqrt(shipRadius^2+shipHalfLength^2)) plus margin')
    p.add_argument('--spacing', type=float, required=True, help='Maximum uniform grid step in metres')
    p.add_argument('--bz-tesla', type=float, default=1.0,
                    help='Reference field magnitude at generation time (default 1 T) -- '
                         'sweep actual intensity with /spacecraft/fieldScale, not this flag')
    p.add_argument('--max-points', type=int, default=1000000)
    a = p.parse_args()
    generate(a.output, a.half_size, a.spacing, a.bz_tesla, a.max_points)
