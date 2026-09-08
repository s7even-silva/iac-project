#!/usr/bin/env python3
"""Prepare, without running, the proposed 2A/4A/8A map-domain study."""
import argparse
import json
from pathlib import Path
import shlex
import sys

import numpy as np
from compute_field import grid_shape
from generate_mesh import digest


def prepare(source, directory, spacing, enclosing_radius=None):
    data = json.loads(source.read_text())
    bounds = np.asarray(data['bounds_m']).reshape(2, 3)
    # Conservative origin-centred enclosing radius from the CAD bounding box.
    minimum = float(np.linalg.norm(np.max(np.abs(bounds), axis=0)))
    radius = minimum if enclosing_radius is None else enclosing_radius
    if not np.isfinite(radius) or radius < minimum:
        raise ValueError(f'A must enclose the CAD; conservative minimum {minimum:g} m')
    directory.mkdir(parents=True, exist_ok=True)
    source = source.resolve()
    cases = []
    largest = 8*radius
    for multiplier in (2, 4, 8):
        half = multiplier*radius
        if half <= 5:
            raise ValueError('Map must also enclose the habitat; increase --enclosing-radius')
        n, step = grid_shape(half, spacing)
        output = (directory/f'R{multiplier}A.map').resolve()
        command = [sys.executable, str(Path(__file__).with_name('compute_field.py').resolve()),
                   str(source), str(output), '--half-size', str(half), '--spacing', str(spacing)]
        macro = directory/f'R{multiplier}A.preinit.mac'
        macro.write_text('# Execute before initialization; add coilGeometry and your source/run macro.\n'
                         f'/spacecraft/worldHalfSize {max(10, largest+1)} m\n'
                         f'/spacecraft/fieldMap {output}\n/spacecraft/fieldScale 1\n')
        cases.append({'factor': multiplier, 'map_half_side_m': half,
                      'nodes': n**3, 'spacing_m': step, 'raw_B_float64_bytes': n**3*24,
                      'text_size_estimate_bytes': n**3*60,
                      'requires_budget_override': n**3 > 1000000,
                      'command': shlex.join(command), 'preinit_macro': str(macro)})
    report = {'status': 'proposed_study_not_validated', 'path_sha256': digest(source),
              'A_m': radius, 'CAD_enclosing_radius_upper_bound_m': minimum,
              'fixed_source_sphere_radius_m': largest,
              'fixed_world_half_size_m': max(10, largest+1),
              'note': 'Cubic map cutoffs, inscribed sphere radius R. Fixed source for all cases; validate its own radius separately.',
              'cases': cases}
    (directory/'domain_plan.json').write_text(json.dumps(report, indent=2)+'\n')
    (directory/'generate_maps.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\n'
                                             +'\n'.join(c['command'] for c in cases)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('path', type=Path)
    p.add_argument('directory', type=Path)
    p.add_argument('--spacing', type=float, required=True)
    p.add_argument('--enclosing-radius', type=float, help='Optional A in metres, at least CAD enclosing bound')
    a = p.parse_args()
    prepare(a.path, a.directory, a.spacing, a.enclosing_radius)
