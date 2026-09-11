#!/usr/bin/env python3
"""Field-uniformity metric over the protection region, for comparing
Halbach angular-pattern candidates BEFORE spending Elmer FEM time on any
of them (field/CREWHAT_STATUS.md, angular-pattern ablation -- Fase 0).
Reuses the same regularized Biot-Savart superposition already validated
for this array (field_at() from compute_field.py, unmodified) -- same
caveats as compute_field_ellipse_array.py: not Elmer/FEM, not valid close
to/inside a conductor. The grid here stays well clear of that regime: its
radius is the ship radius (<=4.5m for CREW HaT scale), while every coil
sits on an 8m ring, so every grid point is several metres from the
nearest conductor.

**Not a validated criterion, an explicit first one** (schema field
`production_validated: false`): a coefficient of variation (std/mean of
|B|) over a polar grid inside the protection disk, at a handful of Z
planes. The team can refine this metric later; the point of writing it
down and running it now is to have ONE fixed, reproducible number to
compare candidate angular patterns against, instead of eyeballing a
handful of probe points as done so far.
"""
import argparse
import json
from pathlib import Path
import platform

import numpy as np

from compute_field import field_at
from provenance import digest


def build_grid(ship_radius_m, n_radial, n_angular, z_values_m):
    """One centre point per Z plane, plus an n_radial x n_angular polar
    grid (radii excluding 0, to avoid double-counting the centre) inside
    the disk of the given radius, at each Z plane."""
    points = [(0.0, 0.0, z) for z in z_values_m]
    radii = np.linspace(ship_radius_m/n_radial, ship_radius_m, n_radial)
    angles = np.linspace(0.0, 2*np.pi, n_angular, endpoint=False)
    for z in z_values_m:
        for r in radii:
            for a in angles:
                points.append((r*np.cos(a), r*np.sin(a), z))
    return np.asarray(points, dtype=float)


def compute(source, grid):
    data = json.loads(source.read_text())
    coils = data['coils']
    if not coils:
        raise ValueError('Array report has no coils')
    core = data['config']['coil_template']['field_regularization_radius_m']
    total = np.zeros_like(grid)
    for coil in coils:
        path = np.asarray(coil['path_m'])
        total += field_at(grid, path, coil['current_A'], core)
    return total


def summarize(source, output, ship_radius_m, n_radial, n_angular, z_values_m):
    if not np.isfinite(ship_radius_m) or ship_radius_m <= 0:
        raise ValueError('ship_radius_m must be positive and finite')
    if n_radial < 1 or n_angular < 1:
        raise ValueError('Need at least one radial step and one angular step')
    grid = build_grid(ship_radius_m, n_radial, n_angular, z_values_m)
    b = compute(source, grid)
    magnitude = np.linalg.norm(b, axis=1)
    mean, std = float(magnitude.mean()), float(magnitude.std())
    report = {
        'production_validated': False,
        'metric': 'regularized_biot_savart_superposition_over_protection_region_grid',
        'source_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
        'python': platform.python_version(), 'numpy': np.__version__, 'platform': platform.platform(),
        'ship_radius_m': ship_radius_m, 'n_radial': n_radial, 'n_angular': n_angular,
        'z_values_m': z_values_m, 'n_points': int(len(grid)),
        'mean_T': mean, 'std_T': std,
        'coefficient_of_variation': std/mean if mean else None,
        'min_T': float(magnitude.min()), 'max_T': float(magnitude.max()),
        'points_m': grid.tolist(), 'magnitude_T': magnitude.tolist(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('points_m', 'magnitude_T')}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('source', type=Path, help='array_current_paths.json from generate_ellipse_array.py')
    p.add_argument('output', type=Path)
    p.add_argument('--ship-radius', type=float, default=4.5,
                   help='Protection-region disk radius, metres (default: CREW HaT-scaled ship, 4.5m)')
    p.add_argument('--n-radial', type=int, default=5)
    p.add_argument('--n-angular', type=int, default=8)
    p.add_argument('--z', type=float, nargs='+', default=[0.0, 2.0, -2.0], help='Z planes to sample, metres')
    a = p.parse_args()
    summarize(a.source, a.output, a.ship_radius, a.n_radial, a.n_angular, a.z)
