#!/usr/bin/env python3
"""Build a single closed elliptical CREW HaT coil pilot; SI units, not a full NIAC design.

Unlike generate_dh.py's Double Helix (where tracing each turn is physically
necessary for the coil's own solenoidal-cancellation mechanism), a CREW HaT
coil is N electrically-identical turns stacked in a winding pack -- there is
no physical reason to trace them individually, and doing so (41,667 turns
for the 12mm-tape option, per field/ELMER_VALIDATION.md) is not tractable
with this project's per-turn swept-tetrahedra pipeline. This generator
instead sweeps ONE closed ellipse with a homogenized winding-pack
cross-section, carrying the coil's total ampere-turns as a single current.

`conductor_radius_m` in the output schema (required by compute_field.py,
unchanged) is NOT a real conductor dimension here: it is a Biot-Savart
near-field regularization scale (see compute_field.py:field_at). For the DH
pilot the true wire was thin relative to the coil, so a soft filament core
was a reasonable near-field stand-in; here the winding pack (whichever
`winding_pack_side_m` is passed) is comparable in scale to the coil's own
minor axis, so a single regularized filament is a much weaker approximation
close to the coil. It remains the same convention as generate_dh.py so
compute_field.py needs no changes -- but do not read a Biot-Savart field
map from this generator's output as valid near the coil without revisiting
that approximation (see field/ELMER_VALIDATION.md, sección CREW HaT).
"""
import argparse
import json
from pathlib import Path
import platform

import gmsh
import numpy as np
from provenance import digest
from cad_cleanup import remove_construction_entities
from generate_dh import _conductor_profile


def controls(c):
    if c['schema_version'] != 1 or c['status'] != 'computational_pilot_not_crewhat':
        raise ValueError('This generator currently supports the labelled pilot only')
    a, b = c['semi_major_m'], c['semi_minor_m']
    side, reg = c['winding_pack_side_m'], c['field_regularization_radius_m']
    values = [a, b, side, reg, c['current_A'], c['mesh_size_m'], c['mesh_min_size_m'], *c['center_m']]
    if not np.isfinite(values).all() or not (0 < b <= a and 0 < side and 0 < reg
                                              and 0 < c['mesh_min_size_m'] <= c['mesh_size_m']):
        raise ValueError('Invalid ellipse or winding-pack dimensions')
    # Minimum radius of curvature of an ellipse is at the ends of its major
    # axis: rho_min = b^2/a. A swept square cross-section of half-width
    # side/2 self-intersects there once side/2 approaches rho_min -- this is
    # a REAL geometric constraint of this coil shape, not a pilot-only
    # safeguard like generate_dh.py's "4x" margins (those had room to
    # spare; an ellipse this flat relative to its winding pack does not).
    # 1.2x is a thin margin, not a validated production safety factor --
    # revisit once a mesh-quality check exists for this generator.
    rho_min = b*b/a
    if side/2 >= rho_min/1.2:
        raise ValueError(f'winding_pack_side_m={side} too large for this ellipse: '
                          f'half-width {side/2:.4g} m vs. minimum radius of curvature '
                          f'{rho_min:.4g} m at the major-axis ends (need >=1.2x margin)')
    for key, minimum in [('control_points', 64), ('field_segments', 128), ('mesh_points_per_circle', 8)]:
        if type(c[key]) is not int or c[key] < minimum:
            raise ValueError(f'Invalid {key}')
    # endpoint=False: an ellipse closes on itself exactly at t=2*pi, unlike
    # generate_dh.py's helix (whose axial pitch keeps t=0 and t=2*pi*turns
    # apart) -- addSpline() below adds the single closing duplicate point
    # itself; including one here too would leave a zero-length last segment
    # and break OpenCASCADE's spline interpolation (confirmed empirically).
    t = np.linspace(0, 2*np.pi, c['control_points'], endpoint=False)
    return np.column_stack((a*np.cos(t), b*np.sin(t), np.zeros_like(t))) + c['center_m']


def generate(config, directory):
    c = json.loads(config.read_text())
    points = controls(c)
    directory.mkdir(parents=True, exist_ok=True)
    # _conductor_profile() only checks for tape_width_m/tape_thickness_m to
    # decide disk vs. rectangle -- reuse it as-is for the square winding
    # pack by presenting the same two keys, no duplicated CAD logic.
    c_profile = {**c, 'tape_width_m': c['winding_pack_side_m'],
                 'tape_thickness_m': c['winding_pack_side_m']}
    gmsh.initialize([], readConfigFiles=False)
    try:
        occ = gmsh.model.occ
        tags = [occ.addPoint(*p) for p in points]
        curve = occ.addSpline(tags + [tags[0]])
        occ.synchronize()
        lo, hi = gmsh.model.getParametrizationBounds(1, curve)
        parameters = np.linspace(float(lo[0]), float(hi[0]), c['field_segments']+1)
        path = np.asarray(gmsh.model.getValue(1, curve, parameters)).reshape(-1, 3)
        path[-1] = path[0]
        # Split into patches before sweeping, same reason as generate_dh.py:
        # OpenCASCADE hangs fusing a single periodic swept face. A closed
        # ellipse has no "turns" to scale patch count by; 8 matches DH's
        # own minimum for a single short loop.
        n_cuts = 8
        cut_parameters = np.linspace(float(lo[0]), float(hi[0]), n_cuts+1)[1:-1]
        cut_points = np.asarray(gmsh.model.getValue(1, curve, cut_parameters)).reshape(-1, 3)
        cuts = [occ.addPoint(*p) for p in cut_points]
        fragments, _ = occ.fragment([(1, curve)], [(0, p) for p in cuts])
        occ.synchronize()
        pieces = []
        for dim, tag in fragments:
            if dim != 1:
                continue
            low, _ = gmsh.model.getParametrizationBounds(1, tag)
            start = gmsh.model.getValue(1, tag, [float(low[0])])
            tangent = gmsh.model.getDerivative(1, tag, [float(low[0])])
            wire = occ.addWire([tag])
            profile = _conductor_profile(occ, c_profile, start, tangent, c['center_m'], [0, 0, 1])
            pieces.extend(occ.addPipe([(2, profile)], wire, 'DiscreteTrihedron'))
            occ.remove([(2, profile)], recursive=False)
        volumes, _ = occ.fuse(pieces[:1], pieces[1:])
        occ.synchronize()
        solids = [tag for dim, tag in volumes if dim == 3]
        if len(solids) != 1:
            raise ValueError('Expected one closed swept coil')
        cad_volume = occ.getMass(3, solids[0])
        bounds = gmsh.model.getBoundingBox(3, solids[0])
        removed = remove_construction_entities()
        gmsh.write(str(directory/'ellipse.brep'))
        gmsh.write(str(directory/'ellipse.step'))
    finally:
        gmsh.finalize()
    geo = 'SetFactory("OpenCASCADE");\nMerge "ellipse.brep";\nPhysical Volume("crewhat_coil") = Volume{:};\n'
    geo += f'Mesh.MeshSizeMin = {c["mesh_min_size_m"]};\nMesh.MeshSizeMax = {c["mesh_size_m"]};\nMesh.MeshSizeFromCurvature = {c["mesh_points_per_circle"]};\n'
    (directory/'ellipse.geo').write_text(geo)
    # Real HTS material if the config carries one (materials_library +
    # material, same convention generate_array.py uses for the DH array);
    # falls back to placeholder copper so older configs without those keys
    # keep working unchanged.
    if 'materials_library' in c and 'material' in c:
        library = c['materials_library']
        if c['material'] not in library['materials']:
            raise ValueError(f'Undefined material {c["material"]!r} in materials_library')
        materials = {'schema_version': 1, 'length_unit': 'm', 'elements': library['elements'],
                     'materials': library['materials'], 'groups': {'crewhat_coil': c['material']}}
    else:
        materials = {'schema_version': 1, 'length_unit': 'm', 'elements': {'Cu': {'Z': 29, 'A': 63.546}},
                     'materials': {'placeholder_copper': {'density_g_cm3': 8.96, 'mass_fractions': {'Cu': 1.0}}},
                     'groups': {'crewhat_coil': 'placeholder_copper'}}
    (directory/'materials.json').write_text(json.dumps(materials, indent=2)+'\n')
    report = {'schema_version': 1, 'status': c['status'], 'config': c,
              'config_sha256': digest(config), 'generator_sha256': digest(Path(__file__)),
              'gmsh': gmsh.__version__, 'numpy': np.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'brep_sha256': digest(directory/'ellipse.brep'),
              'step_sha256': digest(directory/'ellipse.step'),
              'construction_entities_removed': removed,
              'cleanup_sha256': digest(Path(__file__).with_name('cad_cleanup.py')),
              'current_A': c['current_A'],
              # NOT a real conductor radius -- see module docstring.
              'conductor_radius_m': c['field_regularization_radius_m'],
              'winding_pack_side_m': c['winding_pack_side_m'],
              'cad_volume_m3': cad_volume, 'bounds_m': bounds,
              'path_m': path.tolist()}
    (directory/'current_path.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'Pilot generated in {directory}; CAD volume {cad_volume:.8g} m3')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config', type=Path)
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    generate(a.config, a.directory)
