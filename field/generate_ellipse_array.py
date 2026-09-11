#!/usr/bin/env python3
"""Assemble N elliptical CREW HaT coils into a dipole Halbach torus GDML.

Reuses generate_ellipse.py's controls() unchanged for each coil's LOCAL
geometry (built flat, centered at the origin), then applies this module's
own rotation + translation to place it in the array -- same "orchestrate,
don't modify" principle generate_array.py already uses for the Double
Helix. generate_ellipse.py itself is untouched.

**The angular pattern below is the team's own engineering assumption, not
a number from NIAC Phase I or the 2024 thesis.** Neither document gives a
per-coil angle table, nor even a count of how many of the 8 coils are
"radial" vs "tangential" mounting types (NIAC Sec. 5.3.3, p.61 -- a
STRUCTURAL/mechanical distinction, not necessarily the electromagnetic
phase used here) -- confirmed by two rounds of targeted search, see
field/CREWHAT_STATUS.md. This generator instead applies the standard K=1
("dipole") Halbach array formula from magnet engineering: for N elements
evenly spaced around a circle at position angle phi_k = 2*pi*k/N, a dipole
Halbach array orients each element's own magnetic moment at angle
theta_k = 2*phi_k (moment rotates twice as fast as position) -- the same
rule used for Halbach-cylinder MRI magnets and accelerator wigglers. Every
coil here is the SAME mounting type; this is a deliberate simplification,
not a reconstruction of CREW HaT's real (possibly mixed radial/tangential)
design, which the sources don't specify well enough to reproduce.

Each coil's semi-major axis (a) is oriented along the ship's own length
(global Z) and its semi-minor axis (b) tangential to the ring, with its
own magnetic moment (normal to its plane) pointing radially at theta_k in
the global XY plane -- one reasonable, buildable 3D realization of
"Halbach Torus", not the only possible one.

**Angular-pattern ablation (2026-09-10, field/CREWHAT_STATUS.md):** an
optional top-level `theta_deg_pattern` (list of N angles in degrees, one
per coil) overrides the order_k formula's theta_k with an explicit,
per-coil moment angle -- e.g. to test a literal "alternating radial/
tangential" reading of NIAC Sec. 5.3.3 against the smooth K=1 formula
above. Position angle phi_k (and therefore each coil's center on the
ring) is unaffected either way. Omit the key to keep today's exact
behaviour; halbach_order_k stays a required field either way, purely as
a record of which formula the config is deviating from when an override
is present.
"""
import argparse
import json
import math
from pathlib import Path
import platform

import gmsh
import numpy as np

from generate_ellipse import controls as ellipse_controls
from generate_dh import _conductor_profile
from provenance import digest
from cad_cleanup import remove_construction_entities


def halbach_orientation(k, n, order_k, radius, theta_override=None):
    """Position angle, moment angle, this coil's center/normal, and the
    3x3 rotation mapping generate_ellipse.py's local convention (semi-major
    along local x, semi-minor along local y, normal along local z, flat in
    local XY) into this coil's place in the ring.

    theta_override (radians), when given, replaces the order_k formula for
    THIS coil's moment angle only -- phi/center (the ring position) are
    always the regular n-fold spacing, regardless of theta_override."""
    phi = 2*np.pi*k/n
    theta = (order_k+1)*phi if theta_override is None else theta_override
    center = radius*np.array([np.cos(phi), np.sin(phi), 0.0])
    normal = np.array([np.cos(theta), np.sin(theta), 0.0])
    u = np.array([0.0, 0.0, 1.0])                         # semi-major -> ship's length axis
    v = np.array([np.sin(theta), -np.cos(theta), 0.0])    # semi-minor -> tangential to the ring
    rotation = np.column_stack((u, v, normal))
    return phi, theta, center, normal, rotation


def _coil_solid(occ, coil_config, rotation, center, normal):
    local_points = ellipse_controls({**coil_config, 'center_m': [0.0, 0.0, 0.0]})
    points = local_points @ rotation.T + center
    tags = [occ.addPoint(*p) for p in points]
    curve = occ.addSpline(tags + [tags[0]])
    occ.synchronize()
    lo, hi = gmsh.model.getParametrizationBounds(1, curve)
    parameters = np.linspace(float(lo[0]), float(hi[0]), coil_config['field_segments']+1)
    path = np.asarray(gmsh.model.getValue(1, curve, parameters)).reshape(-1, 3)
    path[-1] = path[0]
    n_cuts = 8  # single closed ellipse, no "turns" to scale by (see generate_ellipse.py)
    cut_parameters = np.linspace(float(lo[0]), float(hi[0]), n_cuts+1)[1:-1]
    cut_points = np.asarray(gmsh.model.getValue(1, curve, cut_parameters)).reshape(-1, 3)
    cuts = [occ.addPoint(*p) for p in cut_points]
    fragments, _ = occ.fragment([(1, curve)], [(0, p) for p in cuts])
    occ.synchronize()
    c_profile = {**coil_config, 'tape_width_m': coil_config['winding_pack_side_m'],
                 'tape_thickness_m': coil_config['winding_pack_side_m']}
    pieces = []
    for dim, tag in fragments:
        if dim != 1:
            continue
        low, _ = gmsh.model.getParametrizationBounds(1, tag)
        start = gmsh.model.getValue(1, tag, [float(low[0])])
        tangent = gmsh.model.getDerivative(1, tag, [float(low[0])])
        wire = occ.addWire([tag])
        # axis_point/axis_direction use THIS coil's own center/normal, not a
        # global default -- _conductor_profile's Gram-Schmidt radial-width
        # orientation must be relative to each coil's own tilted plane.
        profile = _conductor_profile(occ, c_profile, start, tangent, center, normal)
        pieces.extend(occ.addPipe([(2, profile)], wire, 'DiscreteTrihedron'))
        occ.remove([(2, profile)], recursive=False)
    volumes, _ = occ.fuse(pieces[:1], pieces[1:])
    occ.synchronize()
    solids = [tag for dim, tag in volumes if dim == 3]
    if len(solids) != 1:
        raise ValueError(f'Expected one closed swept coil, got {len(solids)}')
    return solids[0], path


def _validate(array):
    if array['schema_version'] != 1 or array['status'] != 'computational_pilot_halbach_not_crewhat':
        raise ValueError('This generator currently supports the labelled Halbach pilot only')
    if not isinstance(array['n_coils'], int) or array['n_coils'] < 2:
        raise ValueError('Need at least 2 integer coils for a Halbach array')
    if array['halbach_radius_m'] <= 0 or not np.isfinite(array['halbach_radius_m']):
        raise ValueError('Invalid halbach_radius_m')
    override = array.get('theta_deg_pattern')
    if override is None:
        if array['halbach_order_k'] != 1:
            raise ValueError('Only the K=1 dipole Halbach order is implemented')
    elif (not isinstance(override, list) or len(override) != array['n_coils']
          or not all(isinstance(v, (int, float)) and np.isfinite(v) for v in override)):
        raise ValueError('theta_deg_pattern must have one finite angle in degrees per coil')
    ellipse_controls({**array['coil_template'], 'center_m': [0.0, 0.0, 0.0]})


def generate(config, directory):
    array = json.loads(config.read_text())
    _validate(array)
    n, radius, order_k = array['n_coils'], array['halbach_radius_m'], array['halbach_order_k']
    theta_deg_pattern = array.get('theta_deg_pattern')
    template = array['coil_template']
    directory.mkdir(parents=True, exist_ok=True)
    gmsh.initialize([], readConfigFiles=False)
    try:
        occ = gmsh.model.occ
        names, solids, paths, angles, bounds_per_coil = [], [], [], [], []
        for k in range(n):
            theta_override = None if theta_deg_pattern is None else math.radians(theta_deg_pattern[k])
            phi, theta, center, normal, rotation = halbach_orientation(k, n, order_k, radius, theta_override)
            solid, path = _coil_solid(occ, template, rotation, center, normal)
            name = f'crewhat_coil_{k}'
            names.append(name)
            solids.append(solid)
            paths.append(path.tolist())
            angles.append({'position_deg': math.degrees(phi) % 360, 'moment_deg': math.degrees(theta) % 360})
            bounds_per_coil.append(gmsh.model.getBoundingBox(3, solid))
        cad_volume_by_name = {name: occ.getMass(3, tag) for name, tag in zip(names, solids)}
        removed = remove_construction_entities()
        gmsh.write(str(directory/'halbach_array.brep'))
        gmsh.write(str(directory/'halbach_array.step'))
        overall_bounds = [min(b[i] for b in bounds_per_coil) if i < 3 else max(b[i] for b in bounds_per_coil)
                           for i in range(6)]
    finally:
        gmsh.finalize()

    geo_lines = ['SetFactory("OpenCASCADE");', 'Merge "halbach_array.brep";']
    for i, name in enumerate(names, start=1):
        geo_lines.append(f'Physical Volume("{name}") = {{{i}}};')
    geo_lines += [f'Mesh.MeshSizeMin = {template["mesh_min_size_m"]};',
                  f'Mesh.MeshSizeMax = {template["mesh_size_m"]};',
                  f'Mesh.MeshSizeFromCurvature = {template["mesh_points_per_circle"]};']
    (directory/'halbach_array.geo').write_text('\n'.join(geo_lines)+'\n')

    # Same real-material convention as generate_ellipse.py: all N coils
    # share the template's material, since they're the same shape/conductor.
    if 'materials_library' in template and 'material' in template:
        library = template['materials_library']
        if template['material'] not in library['materials']:
            raise ValueError(f'Undefined material {template["material"]!r} in materials_library')
        materials = {'schema_version': 1, 'length_unit': 'm', 'elements': library['elements'],
                     'materials': library['materials'], 'groups': {name: template['material'] for name in names}}
    else:
        materials = {'schema_version': 1, 'length_unit': 'm', 'elements': {'Cu': {'Z': 29, 'A': 63.546}},
                     'materials': {'placeholder_copper': {'density_g_cm3': 8.96, 'mass_fractions': {'Cu': 1.0}}},
                     'groups': {name: 'placeholder_copper' for name in names}}
    (directory/'materials.json').write_text(json.dumps(materials, indent=2)+'\n')

    report = {'schema_version': 1, 'status': array['status'], 'config': array,
              'config_sha256': digest(config), 'generator_sha256': digest(Path(__file__)),
              'gmsh': gmsh.__version__, 'numpy': np.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'brep_sha256': digest(directory/'halbach_array.brep'),
              'step_sha256': digest(directory/'halbach_array.step'),
              'construction_entities_removed': removed,
              'cleanup_sha256': digest(Path(__file__).with_name('cad_cleanup.py')),
              'bounds_m': overall_bounds,
              'halbach_radius_m': radius, 'n_coils': n, 'halbach_order_k': order_k,
              'angular_pattern': 'explicit_theta_deg_pattern' if theta_deg_pattern is not None
                                  else 'halbach_order_formula',
              'theta_deg_pattern': theta_deg_pattern,
              'coils': [
                  {'name': names[i], 'current_A': template['current_A'], 'path_m': paths[i],
                   'cad_volume_m3': cad_volume_by_name[names[i]], 'bounds_m': bounds_per_coil[i], **angles[i]}
                  for i in range(n)
              ]}
    (directory/'array_current_paths.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'Halbach array generated in {directory}: {n} coils, total CAD volume '
          f'{sum(cad_volume_by_name.values()):.8g} m3')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('config', type=Path)
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    generate(a.config, a.directory)
