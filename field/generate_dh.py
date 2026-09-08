#!/usr/bin/env python3
"""Build a closed, smoothed Double Helix pilot; SI units, not a Geom14 design."""
import argparse
import json
from pathlib import Path
import platform

import gmsh
import numpy as np
from generate_mesh import digest


def controls(c):
    if c['schema_version'] != 1 or c['status'] != 'computational_pilot_not_geom14':
        raise ValueError('This generator currently supports the labelled pilot only')
    r1, r2 = c['radii_m']
    a, pitch, tilt = c['conductor_radius_m'], c['pitch_m'], c['tilt_deg']
    values = [r1, r2, a, pitch, tilt, c['current_A'], c['mesh_size_m'], c['mesh_min_size_m'], *c['center_m']]
    if not np.isfinite(values).all() or not (0 < a < (r2-r1)/4 and r1 > 4*a and 0 < tilt < 90 and pitch > 4*a and 0 < c['mesh_min_size_m'] <= c['mesh_size_m']):
        raise ValueError('Invalid or insufficiently separated pilot dimensions')
    for key, minimum in [('turns', 1), ('control_points_per_turn', 16), ('field_segments', 128),
                         ('mesh_points_per_circle', 8)]:
        if type(c[key]) is not int or c[key] < minimum:
            raise ValueError(f'Invalid {key}')
    t = np.linspace(0, 2*np.pi*c['turns'], c['turns']*c['control_points_per_turn']+1)
    def helix(r, sign):
        return np.column_stack((r*np.cos(t), r*np.sin(t),
                                pitch*(t/(2*np.pi)-c['turns']/2)
                                + sign*r/np.tan(np.deg2rad(tilt))*np.sin(t)))
    # Opposite tilts and opposite traversal: transverse contributions add.
    # The periodic interpolating spline also rounds the two return connections.
    return np.concatenate((helix(r1, 1), helix(r2, -1)[::-1])) + c['center_m']


def generate(config, directory):
    c = json.loads(config.read_text())
    points = controls(c)
    directory.mkdir(parents=True, exist_ok=True)
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
        # Sweep and fuse patches individually to avoid a single periodic face.
        cut_parameters = np.linspace(float(lo[0]), float(hi[0]), 9)[1:-1]
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
        solids = [tag for dim, tag in volumes if dim == 3]
        if len(solids) != 1:
            raise ValueError('Expected one closed swept conductor')
        cad_volume = occ.getMass(3, solids[0])
        bounds = gmsh.model.getBoundingBox(3, solids[0])
        gmsh.write(str(directory/'dh.brep'))
    finally:
        gmsh.finalize()
    # BREP may also contain construction curves, but only the solid is meshed.
    geo = 'SetFactory("OpenCASCADE");\nMerge "dh.brep";\nPhysical Volume("dh_winding") = Volume{:};\n'
    geo += f'Mesh.MeshSizeMin = {c["mesh_min_size_m"]};\nMesh.MeshSizeMax = {c["mesh_size_m"]};\nMesh.MeshSizeFromCurvature = {c["mesh_points_per_circle"]};\n'
    (directory/'dh.geo').write_text(geo)
    materials = {'schema_version': 1, 'length_unit': 'm', 'elements': {'Cu': {'Z': 29, 'A': 63.546}},
                 'materials': {'pilot_copper': {'density_g_cm3': 8.96, 'mass_fractions': {'Cu': 1.0}}},
                 'groups': {'dh_winding': 'pilot_copper'}}
    (directory/'materials.json').write_text(json.dumps(materials, indent=2)+'\n')
    report = {'schema_version': 1, 'status': c['status'], 'config': c,
              'config_sha256': digest(config), 'generator_sha256': digest(Path(__file__)),
              'gmsh': gmsh.__version__, 'numpy': np.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'brep_sha256': digest(directory/'dh.brep'),
              'current_A': c['current_A'], 'conductor_radius_m': c['conductor_radius_m'],
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
