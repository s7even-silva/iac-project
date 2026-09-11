#!/usr/bin/env python3
"""Fase 7 of the angular-pattern ablation (field/CREWHAT_STATUS.md): does
the coil array's fixed phase matter relative to where the phantom is
displaced?

A rigid rotation of the whole Halbach pattern about the ship's Z axis is
physically equivalent to sampling the SAME field at a rotated query angle
instead -- so this reuses the EXISTING K=1 array (no new coil orientation,
no new CAD/mesh, no new Elmer run, unlike Fases 2-4) and just samples it
azimuthally at a fixed radius. If the answer here is "no, magnitude barely
varies with angle", a fixed installation phase is fine regardless of where
the phantom sweep (field/CREWHAT_STATUS.md, phantom position sweep
infrastructure) ends up pointing; if it varies a lot, orienting the array
relative to the expected phantom displacement direction would matter.

Reuses compute() from uniformity_metric.py (same regularized Biot-Savart
superposition, same caveats: not Elmer/FEM, not valid close to a coil).
"""
import argparse
import json
from pathlib import Path
import platform

import numpy as np

from uniformity_metric import compute
from provenance import digest


def build_ring(radius_m, n_angular, z_m):
    angles = np.linspace(0.0, 2*np.pi, n_angular, endpoint=False)
    points = np.column_stack((radius_m*np.cos(angles), radius_m*np.sin(angles), np.full(n_angular, z_m)))
    return points, np.degrees(angles)


def summarize(source, output, radius_m, n_angular, z_m):
    if not np.isfinite(radius_m) or radius_m <= 0:
        raise ValueError('radius_m must be positive and finite')
    if n_angular < 3:
        raise ValueError('Need at least 3 angular samples to say anything about variation')
    grid, angles_deg = build_ring(radius_m, n_angular, z_m)
    b = compute(source, grid)
    magnitude = np.linalg.norm(b, axis=1)
    mean, std = float(magnitude.mean()), float(magnitude.std())
    report = {
        'production_validated': False,
        'metric': 'azimuthal_field_sensitivity_at_fixed_radius_biot_savart',
        'note': ('Rigid rotation of the whole coil pattern about Z is equivalent to '
                 'rotating the query angle instead -- answers whether phantom-offset '
                 'direction relative to the coil phase matters, without a new Elmer run.'),
        'source_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
        'python': platform.python_version(), 'numpy': np.__version__, 'platform': platform.platform(),
        'radius_m': radius_m, 'z_m': z_m, 'n_angular': n_angular,
        'mean_T': mean, 'std_T': std,
        'coefficient_of_variation': std/mean if mean else None,
        'min_T': float(magnitude.min()), 'max_T': float(magnitude.max()),
        'worst_to_best_ratio': float(magnitude.max()/magnitude.min()) if magnitude.min() else None,
        'angle_deg': angles_deg.tolist(), 'magnitude_T': magnitude.tolist(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('angle_deg', 'magnitude_T')}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('source', type=Path, help='array_current_paths.json from generate_ellipse_array.py')
    p.add_argument('output', type=Path)
    p.add_argument('--radius', type=float, required=True, help='Fixed radial offset to sample, metres')
    p.add_argument('--n-angular', type=int, default=16)
    p.add_argument('--z', type=float, default=0.0)
    a = p.parse_args()
    summarize(a.source, a.output, a.radius, a.n_angular, a.z)
