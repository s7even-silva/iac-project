#!/usr/bin/env python3
"""Compare FEM and filament references at explicit probes outside the conductor.

The clearance guard is a pilot heuristic, not a validated error bound. Also
report the effect of removing the Biot-Savart regularization. Never use this
audit to validate the peak field inside a superconducting tape.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from compute_field import field_at
from elmer_to_map import load_vtu, resample
from generate_mesh import digest


def compare(vtu, source, probes, min_clearance_radii=10.):
    data = json.loads(source.read_text())
    query = np.asarray(json.loads(probes.read_text()), dtype=float)
    if query.ndim != 2 or query.shape[1] != 3 or not np.isfinite(query).all():
        raise ValueError('Probes must be a finite N x 3 JSON array in metres')
    if not np.isfinite(min_clearance_radii) or min_clearance_radii <= 1:
        raise ValueError('Require a clearance factor > 1')
    if data.get('config', {}).get('tape_width_m'):
        raise ValueError('This circular-wire clearance audit does not cover rectangular tape')
    path = np.asarray(data['path_m'])
    radius = float(data['conductor_radius_m'])
    distance = np.full(len(query), np.inf)
    for a, b in zip(path[:-1], path[1:]):
        d = b-a
        fraction = np.clip((query-a) @ d / (d @ d), 0., 1.)
        distance = np.minimum(distance, np.linalg.norm(query-a-fraction[:, None]*d, axis=1))
    if np.any(distance < min_clearance_radii*radius):
        raise ValueError('Probe too close to wire for this filament comparison')
    reference = field_at(query, path, data['current_A'], 0.)
    regularized = field_at(query, path, data['current_A'], radius)
    points, tetra, values = load_vtu(vtu)
    fem = resample(points, tetra, values, query)
    if not np.isfinite(fem).all():
        raise ValueError('Some probes are outside the supplied FEM body mesh')
    norm = np.linalg.norm(reference, axis=1)
    rows = []
    for i, point in enumerate(query):
        rows.append({'point_m': point.tolist(), 'distance_to_centerline_m': float(distance[i]),
                     'distance_in_wire_radii': float(distance[i]/radius),
                     'fem_T': fem[i].tolist(), 'filament_T': reference[i].tolist(),
                     'regularized_T': regularized[i].tolist(),
                     'absolute_vector_error_T': float(np.linalg.norm(fem[i]-reference[i])),
                     'relative_vector_error': float(np.linalg.norm(fem[i]-reference[i])/norm[i]) if norm[i] else None,
                     'regularization_relative_change': float(np.linalg.norm(regularized[i]-reference[i])/norm[i]) if norm[i] else None})
    return {'production_validated': False, 'clearance_factor_heuristic': min_clearance_radii,
            'vtu_sha256': digest(vtu), 'source_sha256': digest(source),
            'probes_sha256': digest(probes), 'probes': rows}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('vtu', type=Path)
    p.add_argument('source', type=Path)
    p.add_argument('probes', type=Path, help='JSON N x 3 coordinates in metres')
    p.add_argument('output', type=Path)
    p.add_argument('--min-clearance-radii', type=float, default=10.)
    a = p.parse_args()
    if a.output.resolve() in {x.resolve() for x in (a.vtu, a.source, a.probes)}:
        p.error('Use a distinct output file')
    result = compare(a.vtu, a.source, a.probes, a.min_clearance_radii)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
