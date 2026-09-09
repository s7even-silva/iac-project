#!/usr/bin/env python3
"""Assemble multiple Double Helix pilot coils (barrel + endcaps) into one GDML.

This is the "replicate and orient" step described in DOMAINS.md and
GEOM14_STATUS.md brecha 5: it must run AFTER a single coil (generate_dh.py)
has been validated against Biot-Savart and its mesh audited (audit_dh.py).
It reuses controls()/generate() from generate_dh.py unchanged for each coil
in the array -- no new geometry algorithm, only orchestration of N calls to
the existing single-coil generator plus assembly bookkeeping.

Geom14 status (see field/GEOM14_STATUS.md): ARSSEM never confirms whether
Geom14 itself has endcaps, but Geom12/Geom13 (same Double Helix family) do,
each with barrel and endcap coils at different diameters. Assuming Geom14
follows the same barrel+endcap pattern is the best-supported extrapolation
from the published family, not an invented detail -- it is documented here
and in GEOM14_STATUS.md as exactly that: an assumption, not a confirmed
ARSSEM parameter. This generator supports (but does not require) endcaps:
an array with zero endcap coils reduces to a barrel-only assembly.

Coil-to-coil overlap is NOT checked here: each coil's own turns are swept
and fused into one solid (as in generate_dh.py), but different coils in the
array are never fused or intersection-tested against each other -- Gmsh
will silently accept overlapping solids. This is acceptable because Geant4
already checks placement overlaps for every imported piece against the
habitat AND every previously placed piece (ICRP110PhantomConstruction.cc,
CheckOverlaps after each G4PVPlacement) -- a bad array config fails loudly
at import time, not silently at mesh time. Do not treat a successful mesh
here as proof the array is geometrically valid.
"""
import argparse
import json
import math
from pathlib import Path
import platform

import gmsh
import numpy as np

from generate_dh import controls
from generate_mesh import digest
from cad_cleanup import remove_construction_entities


def _coil_solid(occ, coil_config, tag_prefix):
    """Build one swept DH coil solid; mirrors generate.generate()'s CAD steps."""
    points = controls(coil_config)
    tags = [occ.addPoint(*p) for p in points]
    curve = occ.addSpline(tags + [tags[0]])
    occ.synchronize()
    lo, hi = gmsh.model.getParametrizationBounds(1, curve)
    parameters = np.linspace(float(lo[0]), float(hi[0]), coil_config['field_segments'] + 1)
    path = np.asarray(gmsh.model.getValue(1, curve, parameters)).reshape(-1, 3)
    path[-1] = path[0]
    # See generate_dh.py's generate() for why this must scale with turns:
    # a fixed 8-patch cut hangs Gmsh's fragment/fuse indefinitely once a
    # patch spans more than ~1 turn (confirmed empirically at 7+ turns).
    n_cuts = max(8, math.ceil(coil_config['turns'] / 0.5))
    cut_parameters = np.linspace(float(lo[0]), float(hi[0]), n_cuts + 1)[1:-1]
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
        disk = occ.addDisk(*start, coil_config['conductor_radius_m'], coil_config['conductor_radius_m'],
                            zAxis=tangent)
        pieces.extend(occ.addPipe([(2, disk)], wire, 'DiscreteTrihedron'))
        occ.remove([(2, disk)], recursive=False)
    volumes, _ = occ.fuse(pieces[:1], pieces[1:])
    occ.synchronize()
    solids = [tag for dim, tag in volumes if dim == 3]
    if len(solids) != 1:
        raise ValueError(f'{tag_prefix}: expected one closed swept conductor, got {len(solids)}')
    return solids[0], path, coil_config['current_A']


def _validate_array(array):
    if array['schema_version'] != 1 or array['status'] != 'computational_pilot_array_not_geom14':
        raise ValueError('This generator currently supports the labelled pilot array only')
    coils = array['coils']
    if not coils:
        raise ValueError('Array must contain at least one coil')
    names = [c['name'] for c in coils]
    if len(names) != len(set(names)):
        raise ValueError('Coil names must be unique (used as GDML/material group names)')
    known_materials = set(array['materials_library']['materials'])
    for coil in coils:
        if coil['role'] not in ('barrel', 'endcap'):
            raise ValueError(f'Unknown coil role: {coil["role"]!r} (expected barrel or endcap)')
        if coil['material'] not in known_materials:
            raise ValueError(f'Coil {coil["name"]!r} references undefined material {coil["material"]!r}')


def generate(config, directory):
    array = json.loads(config.read_text())
    _validate_array(array)
    directory.mkdir(parents=True, exist_ok=True)
    gmsh.initialize([], readConfigFiles=False)
    try:
        occ = gmsh.model.occ
        solids, paths, currents, bounds_per_coil = [], [], [], []
        for coil in array['coils']:
            solid, path, current = _coil_solid(occ, coil['config'], coil['name'])
            solids.append((coil['name'], solid))
            paths.append(path.tolist())
            currents.append(current)
            bounds_per_coil.append(gmsh.model.getBoundingBox(3, solid))
        volumes_by_name = {}
        cad_volume_by_name = {}
        for name, tag in solids:
            volumes_by_name[name] = tag
            cad_volume_by_name[name] = occ.getMass(3, tag)
        removed = remove_construction_entities()
        gmsh.write(str(directory / 'array.brep'))
        overall_bounds = [
            min(b[i] for b in bounds_per_coil) if i < 3 else max(b[i] for b in bounds_per_coil)
            for i in range(6)
        ]
    finally:
        gmsh.finalize()

    # One Physical Volume per coil, in BREP entity order (OpenCASCADE numbers
    # solids sequentially as they are created; solids[i] got tag i+1 here
    # because nothing else in this model produced a 3D entity before it).
    geo_lines = ['SetFactory("OpenCASCADE");', 'Merge "array.brep";']
    for i, (name, _) in enumerate(solids, start=1):
        geo_lines.append(f'Physical Volume("{name}") = {{{i}}};')
    mesh_size = array.get('mesh_size_m', min(c['config']['mesh_size_m'] for c in array['coils']))
    mesh_min = array.get('mesh_min_size_m', min(c['config']['mesh_min_size_m'] for c in array['coils']))
    mesh_curve = array.get('mesh_points_per_circle', min(c['config']['mesh_points_per_circle'] for c in array['coils']))
    geo_lines += [f'Mesh.MeshSizeMin = {mesh_min};', f'Mesh.MeshSizeMax = {mesh_size};',
                  f'Mesh.MeshSizeFromCurvature = {mesh_curve};']
    (directory / 'array.geo').write_text('\n'.join(geo_lines) + '\n')

    materials = {'schema_version': 1, 'length_unit': 'm',
                 'elements': array['materials_library']['elements'],
                 'materials': array['materials_library']['materials'],
                 'groups': {coil['name']: coil['material'] for coil in array['coils']}}
    (directory / 'materials.json').write_text(json.dumps(materials, indent=2) + '\n')

    report = {'schema_version': 1, 'status': array['status'], 'config': array,
              'config_sha256': digest(config), 'generator_sha256': digest(Path(__file__)),
              'gmsh': gmsh.__version__, 'numpy': np.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'brep_sha256': digest(directory / 'array.brep'),
              'construction_entities_removed': removed,
              'cleanup_sha256': digest(Path(__file__).with_name('cad_cleanup.py')),
              'bounds_m': overall_bounds,
              'coils': [
                  {'name': coil['name'], 'role': coil['role'],
                   'current_A': currents[i], 'path_m': paths[i],
                   'cad_volume_m3': cad_volume_by_name[coil['name']],
                   'bounds_m': bounds_per_coil[i]}
                  for i, coil in enumerate(array['coils'])
              ]}
    (directory / 'array_current_paths.json').write_text(json.dumps(report, indent=2) + '\n')
    n_barrel = sum(1 for c in array['coils'] if c['role'] == 'barrel')
    n_endcap = sum(1 for c in array['coils'] if c['role'] == 'endcap')
    print(f'Array generated in {directory}: {n_barrel} barrel + {n_endcap} endcap coil(s), '
          f'total CAD volume {sum(cad_volume_by_name.values()):.8g} m3')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('config', type=Path)
    p.add_argument('directory', type=Path)
    a = p.parse_args()
    generate(a.config, a.directory)
