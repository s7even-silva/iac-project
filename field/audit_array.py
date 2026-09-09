#!/usr/bin/env python3
"""Report DH array (barrel + endcaps) geometry/current consistency, per coil
and for the assembly as a whole. Never certifies superconducting operation.

Same numerical checks as audit_dh.py, applied to every coil in
array_current_paths.json (from generate_array.py), plus assembly-level
totals (total conductor mass, per-coil ampere-turns) that only make sense
once there is more than one coil. Reuses field_at() unchanged; this file
adds no new field physics, only bookkeeping across coils.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from audit_dh import mesh_volume
from compute_field import field_at
from generate_mesh import digest


def audit(source, mesh=None, critical_current=None):
    data = json.loads(source.read_text())
    if data['status'] != 'computational_pilot_array_not_geom14':
        raise ValueError('This audit supports the multi-coil DH array pilot only')
    if critical_current is not None and (not np.isfinite(critical_current) or critical_current <= 0):
        raise ValueError('Critical current must be positive and finite')

    materials = data['config']['materials_library']['materials']
    coil_configs = {c['name']: c for c in data['config']['coils']}

    coil_reports = []
    for coil in data['coils']:
        path = np.asarray(coil['path_m'])
        if not np.array_equal(path[0], path[-1]):
            raise ValueError(f'{coil["name"]}: current circuit must be closed')
        coil_config = coil_configs[coil['name']]
        conductor_radius = coil_config['config']['conductor_radius_m']
        length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
        current = coil['current_A']
        turns = coil_config['config']['turns']
        center = coil_config['config']['center_m']
        material_name = coil_config['material']
        density_kg_m3 = materials[material_name]['density_g_cm3'] * 1000.0
        probes = field_at([center, [0, 0, 0]], path, current, conductor_radius)
        coil_reports.append({
            'name': coil['name'], 'role': coil['role'],
            'closed_path': True, 'turns_per_helix': turns, 'helices': 2,
            'current_A': current, 'ampere_turns_per_helix_magnitude': abs(current) * turns,
            'total_conductor_path_length_m': length,
            'I_times_total_length_A_m': abs(current) * length,
            'cad_volume_m3': coil['cad_volume_m3'],
            'material': material_name, 'density_kg_m3': density_kg_m3,
            'cad_mass_kg': density_kg_m3 * coil['cad_volume_m3'],
            'coil_center_B_T': probes[0].tolist(), 'cabin_origin_B_T': probes[1].tolist(),
            'critical_current_A_user_supplied': critical_current,
            'I_over_Ic': None if critical_current is None else abs(current) / critical_current,
            'current_margin_fraction': None if critical_current is None else 1 - abs(current) / critical_current,
        })

    report = {'status': data['status'], 'production_validated': False,
              'source_sha256': digest(source), 'auditor_sha256': digest(Path(__file__)),
              'n_coils': len(coil_reports),
              'n_barrel': sum(1 for c in coil_reports if c['role'] == 'barrel'),
              'n_endcap': sum(1 for c in coil_reports if c['role'] == 'endcap'),
              'coils': coil_reports,
              # Per-coil mass (each with its own material's density) summed --
              # NOT a single density applied to total volume, since different
              # coils may use different materials (e.g. an Al passive endcap
              # core alongside an HTS barrel).
              'assembly_cad_conductor_mass_kg': sum(c['cad_mass_kg'] for c in coil_reports),
              'assembly_mesh_volume_m3': None, 'assembly_mesh_volume_relative_error': None,
              'notes': ['N*I is per coil-helix, not a scalar sum across coils or opposing windings.',
                        'Path length already includes all turns and returns per coil; do not multiply again by N.',
                        'Probe fields are single-coil regularized values, NOT the superposed array field '
                        '-- use compute_field_array.py for the assembled field.',
                        'An input Ic must match B, field angle, temperature and strain; ratio alone is not validation.',
                        'Coil-to-coil overlap is not checked here or in generate_array.py; Geant4 import checks it.']}
    if mesh is not None:
        report['mesh_sha256'] = digest(mesh)
        report['assembly_mesh_volume_m3'] = mesh_volume(mesh)
        cad_total = sum(c['cad_volume_m3'] for c in coil_reports)
        report['assembly_mesh_volume_relative_error'] = report['assembly_mesh_volume_m3'] / cad_total - 1
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('source', type=Path, help='array_current_paths.json from generate_array.py')
    p.add_argument('output', type=Path)
    p.add_argument('--mesh', type=Path, help='Conductor-only .msh (all coils), in metres; same CAD as source')
    p.add_argument('--critical-current', type=float, help='Optional user-supplied Ic in A; no default from ARSSEM')
    a = p.parse_args()
    if a.output.resolve() in {a.source.resolve(), None if a.mesh is None else a.mesh.resolve()}:
        p.error('Output must be distinct from inputs')
    result = audit(a.source, a.mesh, a.critical_current)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
