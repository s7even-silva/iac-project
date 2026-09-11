#!/usr/bin/env python3
"""Build ONE standalone coil at a given Halbach array index, isolated.

Reuses generate_ellipse_array.py's halbach_orientation()/_coil_solid()
unmodified. Exists to test a single coil's real array orientation (CAD,
mesh, Elmer Coil Normal sign) without paying the cost of generating and
meshing the full N-coil array -- used 2026-09-10 to confirm the "Coil
Normal = -normal" sign rule found for the unrotated single-coil pilot
(field/examples/crewhat_ellipse_pilot.sif) also holds for a genuinely
rotated coil (k=1 of the real n=8 array), without needing to validate all
8 orientations individually. See field/CREWHAT_STATUS.md, "Convención de
signo de Coil Normal, validada para una bobina rotada".
"""
import argparse
import json
from pathlib import Path

import gmsh
import numpy as np

from provenance import digest
from cad_cleanup import remove_construction_entities
from generate_ellipse_array import halbach_orientation, _coil_solid


def generate(array_config, k, directory):
    array = json.loads(array_config.read_text())
    n, order_k, radius = array['n_coils'], array['halbach_order_k'], array['halbach_radius_m']
    if not (0 <= k < n):
        raise ValueError(f'k={k} out of range for n_coils={n}')
    template = array['coil_template']
    phi, theta, center, normal, rotation = halbach_orientation(k, n, order_k, radius)
    directory.mkdir(parents=True, exist_ok=True)
    gmsh.initialize([], readConfigFiles=False)
    try:
        occ = gmsh.model.occ
        solid, path = _coil_solid(occ, template, rotation, center, normal)
        cad_volume = occ.getMass(3, solid)
        bounds = gmsh.model.getBoundingBox(3, solid)
        removed = remove_construction_entities()
        gmsh.write(str(directory/'coil.brep'))
    finally:
        gmsh.finalize()

    geo = 'SetFactory("OpenCASCADE");\nMerge "coil.brep";\nPhysical Volume("crewhat_coil") = Volume{:};\n'
    geo += (f'Mesh.MeshSizeMin = {template["mesh_min_size_m"]};\n'
            f'Mesh.MeshSizeMax = {template["mesh_size_m"]};\n'
            f'Mesh.MeshSizeFromCurvature = {template["mesh_points_per_circle"]};\n')
    (directory/'coil.geo').write_text(geo)

    if 'materials_library' in template and 'material' in template:
        library = template['materials_library']
        materials = {'schema_version': 1, 'length_unit': 'm', 'elements': library['elements'],
                     'materials': library['materials'], 'groups': {'crewhat_coil': template['material']}}
    else:
        materials = {'schema_version': 1, 'length_unit': 'm', 'elements': {'Cu': {'Z': 29, 'A': 63.546}},
                     'materials': {'placeholder_copper': {'density_g_cm3': 8.96, 'mass_fractions': {'Cu': 1.0}}},
                     'groups': {'crewhat_coil': 'placeholder_copper'}}
    (directory/'materials.json').write_text(json.dumps(materials, indent=2)+'\n')

    report = {'schema_version': 1, 'status': 'computational_pilot_not_crewhat', 'config': template,
              'config_sha256': digest(array_config), 'generator_sha256': digest(Path(__file__)),
              'gmsh': gmsh.__version__, 'numpy': np.__version__,
              'brep_sha256': digest(directory/'coil.brep'),
              'construction_entities_removed': removed,
              'current_A': template['current_A'],
              'conductor_radius_m': template['field_regularization_radius_m'],
              'cad_volume_m3': cad_volume, 'bounds_m': bounds, 'path_m': path.tolist(),
              'halbach_k': k, 'halbach_n': n, 'halbach_order_k': order_k, 'halbach_radius_m': radius,
              'halbach_position_deg': float(np.degrees(phi) % 360),
              'halbach_moment_deg': float(np.degrees(theta) % 360),
              'halbach_normal': normal.tolist(), 'halbach_center': center.tolist()}
    (directory/'current_path.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'Representative coil k={k}/{n} generated in {directory}; '
          f'CAD volume {cad_volume:.8g} m3; normal {normal.tolist()}; center {center.tolist()}')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('array_config', type=Path, help='e.g. examples/crewhat_halbach_array_pilot.json')
    p.add_argument('k', type=int, help='Coil index (0-based) to build in isolation')
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    generate(a.array_config, a.k, a.directory)
