#!/usr/bin/env python3
"""Build a closed, smoothed Double Helix pilot; SI units, not a Geom14 design."""
import argparse
import json
import math
from pathlib import Path
import platform

import gmsh
import numpy as np
from generate_mesh import digest
from cad_cleanup import remove_construction_entities


def has_tape_section(c):
    """True if the coil declares a real rectangular HTS tape cross-section
    (GEOM14_STATUS.md brecha 2) instead of the circular equivalent-area
    placeholder. `conductor_radius_m` is still required either way: it also
    feeds compute_field.py's regularized Biot-Savart core, which is a
    separate near-field approximation independent of the CAD/mesh shape
    (see brecha 2's note on why the regularized core stays valid regardless
    of the true cross-section)."""
    return 'tape_width_m' in c and 'tape_thickness_m' in c


def controls(c):
    if c['schema_version'] != 1 or c['status'] != 'computational_pilot_not_geom14':
        raise ValueError('This generator currently supports the labelled pilot only')
    r1, r2 = c['radii_m']
    a, pitch, tilt = c['conductor_radius_m'], c['pitch_m'], c['tilt_deg']
    values = [r1, r2, a, pitch, tilt, c['current_A'], c['mesh_size_m'], c['mesh_min_size_m'], *c['center_m']]
    if not np.isfinite(values).all() or not (0 < a < (r2-r1)/4 and r1 > 4*a and 0 < tilt < 90 and pitch > 4*a and 0 < c['mesh_min_size_m'] <= c['mesh_size_m']):
        raise ValueError('Invalid or insufficiently separated pilot dimensions')
    if has_tape_section(c):
        w, th = c['tape_width_m'], c['tape_thickness_m']
        if not np.isfinite([w, th]).all() or not (0 < th < w < (r2-r1)/4 and r1 > 4*w and pitch > 4*w):
            raise ValueError('Invalid or insufficiently separated tape cross-section dimensions')
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


def _conductor_profile(occ, c, start, tangent, axis_point, axis_direction):
    """2D profile (a disk, or an oriented rectangle for a real HTS tape) to
    sweep along the wire at `start` with tangent `tangent`. Shared by
    generate_dh.py and generate_array.py so both stay consistent (brecha 2).

    The rectangle's width axis approximates the coil's local radial
    direction (outward from `axis_point`/`axis_direction`), Gram-Schmidt
    orthogonalized against the tangent -- the wide face of the tape then
    faces the winding's own radial direction, matching ARSSEM's "field
    perpendicular to the tape" framing (S4.3) as closely as a Double Helix
    parametric spine allows without a per-turn conductor orientation from
    ARSSEM (not published, see GEOM14_STATUS.md brecha 1). Falls back to
    the disk when the coil config carries no tape dimensions, so every
    existing circular-section pilot is unaffected.
    """
    tangent = np.asarray(tangent, dtype=float)
    tangent /= np.linalg.norm(tangent)
    if not has_tape_section(c):
        return occ.addDisk(*start, c['conductor_radius_m'], c['conductor_radius_m'], zAxis=tangent)
    start = np.asarray(start, dtype=float)
    axis_point, axis_direction = np.asarray(axis_point, dtype=float), np.asarray(axis_direction, dtype=float)
    axis_direction /= np.linalg.norm(axis_direction)
    offset = start-axis_point
    radial = offset-np.dot(offset, axis_direction)*axis_direction
    width_axis = radial-np.dot(radial, tangent)*tangent
    norm = np.linalg.norm(width_axis)
    if norm < 1e-9:
        raise ValueError('Tape width axis degenerates (spine crosses the coil axis)')
    width_axis /= norm
    thickness_axis = np.cross(tangent, width_axis)
    w, th = c['tape_width_m'], c['tape_thickness_m']
    corners = [start-w/2*width_axis-th/2*thickness_axis, start+w/2*width_axis-th/2*thickness_axis,
               start+w/2*width_axis+th/2*thickness_axis, start-w/2*width_axis+th/2*thickness_axis]
    pts = [occ.addPoint(*p) for p in corners]
    lines = [occ.addLine(pts[i], pts[(i+1) % 4]) for i in range(4)]
    loop = occ.addCurveLoop(lines)
    return occ.addPlaneSurface([loop])


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
        # Each patch must span LESS THAN one full helix turn, or the swept
        # conductor disk self-intersects within that single patch before the
        # per-patch fuse step -- OpenCASCADE's fragment/fuse then hangs
        # indefinitely instead of erroring (confirmed empirically: 6 turns
        # with 8 fixed patches -- 0.75 turn/patch -- meshes in seconds; 7
        # turns -- 0.875 turn/patch -- already hangs; the pilot's 60-turn
        # coils, at 7.5 turns/patch with the old fixed count, never
        # terminated in three attempts). Scale patch count with turns so
        # each patch stays under ~0.5 turn regardless of the coil's total
        # winding count; keep the original 8-patch minimum for short coils.
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
            profile = _conductor_profile(occ, c, start, tangent, c['center_m'], [0, 0, 1])
            pieces.extend(occ.addPipe([(2, profile)], wire, 'DiscreteTrihedron'))
            occ.remove([(2, profile)], recursive=False)
        volumes, _ = occ.fuse(pieces[:1], pieces[1:])
        occ.synchronize()
        solids = [tag for dim, tag in volumes if dim == 3]
        if len(solids) != 1:
            raise ValueError('Expected one closed swept conductor')
        cad_volume = occ.getMass(3, solids[0])
        bounds = gmsh.model.getBoundingBox(3, solids[0])
        removed = remove_construction_entities()
        gmsh.write(str(directory/'dh.brep'))
    finally:
        gmsh.finalize()
    # Export only the solid and its boundaries, not the construction spine.
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
              'construction_entities_removed': removed,
              'cleanup_sha256': digest(Path(__file__).with_name('cad_cleanup.py')),
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
