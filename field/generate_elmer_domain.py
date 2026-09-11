#!/usr/bin/env python3
"""Build the vacuum-plus-conductor CAD domain Elmer needs (GEOM14_STATUS.md
brecha 3): a conformal air sphere enclosing the swept DH conductor, with
Physical Volumes "conductor"/"air" and a Physical Surface "outer_boundary"
on the sphere's outer face for the far-field boundary condition.

This is deliberately NOT field/mesh_swept.py: that module exists to avoid
OpenCASCADE/Gmsh 2D triangulation entirely for the large production array
(brecha 5). A magnetostatic FEM domain needs an actual volume mesh of AIR
around the conductor with a real 2D triangulated interface between the two
regions -- there is no way to avoid Gmsh's 2D/3D triangulation here, so this
generator only targets small pilot coils (few turns), the same regime where
generate_dh.py's OpenCASCADE sweep is already known to complete quickly.
"""
import argparse
import json
import math
from pathlib import Path
import platform

import gmsh
import numpy as np
from generate_dh import controls
from provenance import digest


def generate(config, directory, enclosing_factor=3.0):
    c = json.loads(config.read_text())
    if not (1.0 < enclosing_factor < 100.0):
        raise ValueError('enclosing_factor must exceed 1 (sphere must enclose the coil envelope)')
    points = controls(c)
    directory.mkdir(parents=True, exist_ok=True)
    gmsh.initialize([], readConfigFiles=False)
    try:
        occ = gmsh.model.occ
        tags = [occ.addPoint(*p) for p in points]
        curve = occ.addSpline(tags + [tags[0]])
        occ.synchronize()
        lo, hi = gmsh.model.getParametrizationBounds(1, curve)
        # See generate_dh.py's generate() for why patch count must scale with
        # turns; unchanged here, same OpenCASCADE sweep/fuse hazard applies.
        n_cuts = max(8, math.ceil(c['turns'] / 0.5))
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
            disk = occ.addDisk(*start, c['conductor_radius_m'], c['conductor_radius_m'], zAxis=tangent)
            pieces.extend(occ.addPipe([(2, disk)], wire, 'DiscreteTrihedron'))
            occ.remove([(2, disk)], recursive=False)
        volumes, _ = occ.fuse(pieces[:1], pieces[1:])
        occ.synchronize()
        conductor = [tag for dim, tag in volumes if dim == 3]
        if len(conductor) != 1:
            raise ValueError('Expected one closed swept conductor')
        conductor_volume = occ.getMass(3, conductor[0])

        enclosing_radius = max(c['radii_m'])*enclosing_factor
        sphere = occ.addSphere(*c['center_m'], enclosing_radius)
        occ.synchronize()
        sphere_volume = occ.getMass(3, sphere)
        result, _ = occ.fragment([(3, sphere)], [(3, t) for t in conductor])
        occ.synchronize()
        # fragment() keeps the conductor's own tag; the sphere-minus-conductor
        # remainder is whichever other 3D tag came back (verified by volume,
        # not by assuming a fixed tag order -- OpenCASCADE does not guarantee one).
        conductor_tag = conductor[0]
        air_candidates = [tag for dim, tag in result if dim == 3 and tag != conductor_tag]
        if len(air_candidates) != 1:
            raise ValueError('Expected exactly one remaining air region after fragment')
        air_tag = air_candidates[0]
        air_volume = occ.getMass(3, air_tag)
        expected_air = sphere_volume-conductor_volume
        if abs(air_volume/expected_air-1) > 1e-6:
            raise ValueError('Air region volume does not match sphere-minus-conductor; fragment failed silently')

        # Identify the outer sphere face by area (4*pi*R^2, the full uncut
        # sphere shell): the conductor/air interface faces are fragments of
        # the swept conductor's lateral surface, each far smaller and none
        # matching this area, so this is robust without assuming a fixed
        # tag order or count from fragment().
        expected_area = 4*np.pi*enclosing_radius**2
        outer_surfaces = [tag for dim, tag in gmsh.model.getBoundary([(3, air_tag)], oriented=False)
                          if abs(occ.getMass(2, tag)/expected_area-1) < 1e-6]
        if not outer_surfaces:
            raise ValueError('Could not identify the outer sphere boundary surface')
        conductor_surfaces = [tag for dim, tag in gmsh.model.getBoundary([(3, conductor_tag)], oriented=False)]

        bounds = gmsh.model.getBoundingBox(3, air_tag)
        gmsh.write(str(directory/'domain.brep'))
    finally:
        gmsh.finalize()

    # A single global MeshSizeFromCurvature would refine the whole outer
    # sphere as finely as the millimetre-scale conductor (confirmed
    # empirically: it produced 126k surface nodes and 3D meshing never
    # finished in 55s+) -- use a Distance+Threshold field instead so element
    # size grows away from the conductor interface, fine only where the
    # conductor's own curvature actually requires it.
    coarse_size = enclosing_radius/6
    geo = ['SetFactory("OpenCASCADE");', 'Merge "domain.brep";',
           f'Physical Volume("conductor") = {{{conductor_tag}}};',
           f'Physical Volume("air") = {{{air_tag}}};',
           f'Physical Surface("outer_boundary") = {{{",".join(map(str, outer_surfaces))}}};',
           'Field[1] = Distance;',
           f'Field[1].SurfacesList = {{{",".join(map(str, conductor_surfaces))}}};',
           'Field[2] = Threshold;', 'Field[2].InField = 1;',
           f'Field[2].SizeMin = {c["mesh_min_size_m"]};',
           f'Field[2].SizeMax = {coarse_size:.8g};',
           f'Field[2].DistMin = {c["conductor_radius_m"]*2:.8g};',
           f'Field[2].DistMax = {enclosing_radius/2:.8g};',
           'Background Field = 2;',
           'Mesh.MeshSizeExtendFromBoundary = 0;',
           'Mesh.MeshSizeFromPoints = 0;',
           'Mesh.MeshSizeFromCurvature = 0;',
           f'Mesh.MeshSizeMin = {c["mesh_min_size_m"]};',
           f'Mesh.MeshSizeMax = {coarse_size:.8g};']
    (directory/'domain.geo').write_text('\n'.join(geo)+'\n')

    report = {'schema_version': 1, 'status': 'elmer_pilot_domain_not_geom14', 'config': c,
              'config_sha256': digest(config), 'generator_sha256': digest(Path(__file__)),
              'gmsh': gmsh.__version__, 'numpy': np.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'brep_sha256': digest(directory/'domain.brep'),
              'enclosing_factor': enclosing_factor, 'enclosing_radius_m': enclosing_radius,
              'conductor_volume_m3': conductor_volume, 'air_volume_m3': air_volume,
              'sphere_volume_m3': sphere_volume, 'bounds_m': bounds,
              'current_A': c['current_A'], 'conductor_radius_m': c['conductor_radius_m']}
    (directory/'domain.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'Elmer pilot domain generated in {directory}: conductor {conductor_volume:.6g} m3, '
          f'air {air_volume:.6g} m3, enclosing radius {enclosing_radius:.4g} m')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config', type=Path)
    p.add_argument('directory', type=Path)
    p.add_argument('--enclosing-factor', type=float, default=3.0,
                   help='Air sphere radius = max(radii_m) * this factor')
    a = p.parse_args()
    generate(a.config, a.directory, a.enclosing_factor)
