#!/usr/bin/env python3
"""Report DH pilot geometry/current consistency; never certify superconducting operation."""
import argparse
import json
from pathlib import Path

import gmsh
import numpy as np
from compute_field import field_at
from provenance import digest


def mesh_volume(mesh):
    """Linear-tetra volume only, not a topology/overlap validation."""
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.open(str(mesh))
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(tags)
        sorted_tags = np.asarray(tags)[order]
        points = np.asarray(xyz).reshape(-1, 3)[order]
        total = 0.
        for _, tag in gmsh.model.getEntities(3):
            types, _, nodes = gmsh.model.mesh.getElements(3, tag)
            if list(types) != [4]:
                raise ValueError('Audit requires linear tetrahedra and conductor-only mesh in metres')
            t = np.asarray(nodes[0]).reshape(-1, 4)
            for first in range(0, len(t), 100000):
                vertices = points[np.searchsorted(sorted_tags, t[first:first+100000])]
                total += np.abs(np.linalg.det(vertices[:, 1:]-vertices[:, :1])).sum()/6
        if not np.isfinite(total) or total <= 0:
            raise ValueError('Invalid mesh volume')
        return float(total)
    finally:
        gmsh.finalize()


def audit(source, mesh=None, critical_current=None):
    data = json.loads(source.read_text())
    if data['status'] != 'computational_pilot_not_geom14':
        raise ValueError('This audit supports the single-circuit DH pilot only')
    path = np.asarray(data['path_m'])
    if not np.array_equal(path[0], path[-1]):
        raise ValueError('Current circuit must be closed')
    length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
    current, c = data['current_A'], data['config']
    if critical_current is not None and (not np.isfinite(critical_current) or critical_current <= 0):
        raise ValueError('Critical current must be positive and finite')
    probes = field_at([c['center_m'], [0, 0, 0]], path, current, data['conductor_radius_m'])
    report = {'status': data['status'], 'production_validated': False,
              'source_sha256': digest(source), 'auditor_sha256': digest(Path(__file__)),
              'closed_path': True, 'turns_per_helix': c['turns'], 'helices': 2,
              'current_A': current, 'ampere_turns_per_helix_magnitude': abs(current)*c['turns'],
              'total_conductor_path_length_m': length,
              'I_times_total_length_A_m': abs(current)*length,
              'copper_density_kg_m3': 8960., 'cad_volume_m3': data['cad_volume_m3'],
              'cad_copper_mass_kg': 8960*data['cad_volume_m3'],
              'mesh_volume_m3': None, 'mesh_volume_relative_error': None,
              'coil_center_B_T': probes[0].tolist(), 'cabin_origin_B_T': probes[1].tolist(),
              'peak_conductor_B_T': None, 'maximum_cabin_B_T': None,
              'critical_current_A_user_supplied': critical_current,
              'I_over_Ic': None if critical_current is None else abs(current)/critical_current,
              'current_margin_fraction': None if critical_current is None else 1-abs(current)/critical_current,
              'notes': ['N*I is per helix, not a scalar sum of opposing winding currents.',
                        'Path length already includes all turns and returns; do not multiply again by N.',
                        'Probe fields are regularized pilot values, not protection-region or conductor maxima.',
                        'An input Ic must match B, field angle, temperature and strain; ratio alone is not validation.']}
    if mesh is not None:
        report['mesh_sha256'] = digest(mesh)
        report['mesh_volume_m3'] = mesh_volume(mesh)
        report['mesh_volume_relative_error'] = report['mesh_volume_m3']/data['cad_volume_m3']-1
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--mesh', type=Path, help='Conductor-only .msh, in metres; same CAD as source')
    p.add_argument('--critical-current', type=float, help='Optional user-supplied Ic in A; no default from ARSSEM')
    a = p.parse_args()
    if a.output.resolve() in {a.source.resolve(), None if a.mesh is None else a.mesh.resolve()}:
        p.error('Output must be distinct from inputs')
    result = audit(a.source, a.mesh, a.critical_current)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
