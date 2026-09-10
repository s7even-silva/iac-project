#!/usr/bin/env python3
"""Structured linear tetrahedra along the DH circular section; conductor-only pilot."""
import argparse
import json
import math
from pathlib import Path
import platform
import time

import gmsh
import numpy as np
from generate_dh import controls, has_tape_section
from generate_mesh import digest


def sample_spine(config, step, sagitta):
    """Rebuild the same OCC spine; refine its chords, not the saved field polygon."""
    points = controls(config)
    tags = [gmsh.model.occ.addPoint(*p) for p in points]
    curve = gmsh.model.occ.addSpline(tags+[tags[0]])
    gmsh.model.occ.synchronize()
    lo, hi = gmsh.model.getParametrizationBounds(1, curve)
    parameters = np.linspace(lo[0], hi[0], len(points)+1)
    for _ in range(20):
        p = np.asarray(gmsh.model.getValue(1, curve, parameters)).reshape(-1, 3)
        mid = (parameters[:-1]+parameters[1:])/2
        q = np.asarray(gmsh.model.getValue(1, curve, mid)).reshape(-1, 3)
        error = np.linalg.norm(q-(p[:-1]+p[1:])/2, axis=1)
        refine = (error > sagitta) | (np.linalg.norm(np.diff(p, axis=0), axis=1) > step)
        if not np.any(refine):
            p[-1] = p[0]
            return p[:-1], float(np.max(error))
        parameters = np.sort(np.concatenate((parameters, mid[refine])))
        if len(parameters) > 500000:
            raise ValueError('Spine exceeds 500000 sections; revise resolution')
    raise ValueError('Spine refinement did not converge')


def frames(points):
    """Rotation-minimizing frame with distributed closure twist on a closed loop."""
    delta = np.roll(points, -1, axis=0)-points
    lengths = np.linalg.norm(delta, axis=1)
    if np.any(lengths <= 1e-14):
        raise ValueError('Coincident spine samples')
    direction = delta/lengths[:, None]
    tangent = direction+np.roll(direction, 1, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normals = np.empty_like(points)
    axis = np.eye(3)[np.argmin(np.abs(tangent[0]))]
    normals[0] = np.cross(tangent[0], axis)
    normals[0] /= np.linalg.norm(normals[0])
    def transport(n, a, b):
        v = np.cross(a, b)
        cosine = np.dot(a, b)
        if cosine < -.9:
            raise ValueError('Under-resolved sharp turn')
        result = n+np.cross(v, n)+np.cross(v, np.cross(v, n))/(1+cosine)
        return result/np.linalg.norm(result)
    for i in range(1, len(points)):
        normals[i] = transport(normals[i-1], tangent[i-1], tangent[i])
    end = transport(normals[-1], tangent[-1], tangent[0])
    twist = math.atan2(np.dot(np.cross(end, normals[0]), tangent[0]), np.dot(end, normals[0]))
    distance = np.concatenate(([0.], np.cumsum(lengths[:-1])))
    angle = twist*distance/lengths.sum()
    normals = normals*np.cos(angle)[:, None]+np.cross(tangent, normals)*np.sin(angle)[:, None]
    return normals, np.cross(tangent, normals), float(lengths.sum())


def _extrude_ring(points, ring_local):
    """Shared prism/tetrahedra extrusion along the spine for one cross-section ring.

    `ring_local` is (n_ring_nodes, 2) planar coordinates in the (normal,
    binormal) basis, listing every node OTHER than the on-spine centre node
    in a single loop order (consecutive entries are adjacent on the section
    boundary, wrapping from the last back to the first) -- this is exactly
    what both the circular ring and the rectangle perimeter need, so the
    prism/tetrahedra/orientation/volume logic is written once here and
    reused by both tube_tetrahedra() and ribbon_tetrahedra().
    """
    normals, binormals, spine_length = frames(points)
    sectors = ring_local.shape[0]
    ring = (points[:, None, :]+ring_local[None, :, 0, None]*normals[:, None, :]
            +ring_local[None, :, 1, None]*binormals[:, None, :])
    nodes = np.concatenate((points[:, None, :], ring), axis=1).reshape(-1, 3)
    # Same diagonal on every shared prism face, including the closure section.
    sections = np.arange(len(points))[:, None]*(sectors+1)
    next_sections = np.roll(sections, -1, axis=0)
    columns = np.sort(np.column_stack((np.zeros(sectors, dtype=int),
                        1+np.arange(sectors), 1+(np.arange(sectors)+1) % sectors)), axis=1)
    a, b, c = [(sections+columns[:, k]).ravel() for k in range(3)]
    d, e, f = [(next_sections+columns[:, k]).ravel() for k in range(3)]
    tetra = np.concatenate((np.column_stack((a, b, c, d)), np.column_stack((b, c, d, e)),
                            np.column_stack((c, d, e, f))))
    # Detect inverted prisms before orienting the tetrahedra for serialization.
    expected = np.tile(np.where(np.arange(sectors) == sectors-1, -1, 1), len(points))
    expected = np.tile(expected, 3)
    volume = 0.
    for first in range(0, len(tetra), 100000):
        t = tetra[first:first+100000]
        v = nodes[t]
        determinant = np.linalg.det(v[:, 1:]-v[:, :1])
        if np.any(determinant*expected[first:first+len(t)] <= 0):
            raise ValueError('Inverted tube cell: refine spine or inspect conductor curvature')
        negative = determinant < 0
        t[negative, :2] = t[negative, 1::-1]
        volume += float(np.abs(determinant).sum()/6)
    return nodes, tetra, volume, spine_length


def tube_tetrahedra(points, radius, sectors):
    angle = np.arange(sectors)*2*np.pi/sectors
    ring_local = radius*np.column_stack((np.cos(angle), np.sin(angle)))
    return _extrude_ring(points, ring_local)


def ribbon_tetrahedra(points, width, thickness, width_segments, thickness_segments):
    """Rectangular-section tube: `width` along the frame normal (the tape's
    wide face, conventionally oriented radially for an HTS tape wound with
    its perpendicular-field face along the winding normal -- see
    GEOM14_STATUS.md brecha 2), `thickness` along the binormal. Perimeter
    nodes only (no interior grid): the cross-section is a thin rectangle,
    so a perimeter-only tube mesh is sufficient for the same 3-tetrahedra-
    per-prism scheme already validated for the circular section, without
    inventing a second cell topology for interior quads.
    """
    if width_segments < 1 or thickness_segments < 1:
        raise ValueError('Require at least one segment per rectangle side')
    hw, ht = width/2, thickness/2
    # Counter-clockwise in the (normal, binormal) plane, matching tube_tetrahedra's
    # increasing-angle convention -- _extrude_ring's inversion check assumes it.
    bottom = np.column_stack((np.linspace(-hw, hw, width_segments+1), np.full(width_segments+1, -ht)))
    right = np.column_stack((np.full(thickness_segments+1, hw), np.linspace(-ht, ht, thickness_segments+1)))
    top = np.column_stack((np.linspace(hw, -hw, width_segments+1), np.full(width_segments+1, ht)))
    left = np.column_stack((np.full(thickness_segments+1, -hw), np.linspace(ht, -ht, thickness_segments+1)))
    ring_local = np.concatenate((bottom[:-1], right[:-1], top[:-1], left[:-1]))
    return _extrude_ring(points, ring_local)


def generate(source, output, step=.02, sectors=16, sagitta_fraction=.02, max_elements=5000000,
             tape_width_segments=4, tape_thickness_segments=1):
    """Circular section by default; rectangular tape (brecha 2) when the
    coil config carries tape_width_m/tape_thickness_m (has_tape_section()).
    Both are structured swept tetrahedra -- see tube_tetrahedra() and
    ribbon_tetrahedra() -- no OpenCASCADE/Gmsh 2D triangulation either way,
    the fix this module exists for (GEOM14_STATUS.md brecha 5)."""
    if (output.suffix != '.msh' or sectors < 8 or
            not np.isfinite([step, sagitta_fraction]).all() or step <= 0 or not 0 < sagitta_fraction < .1):
        raise ValueError('Require .msh, sectors>=8, positive step and 0<sagitta_fraction<0.1')
    data = json.loads(source.read_text())
    if data['status'] == 'computational_pilot_not_geom14':
        coils = [('dh_winding', data['config'], data['cad_volume_m3'])]
    elif data['status'] == 'computational_pilot_array_not_geom14':
        reports = {c['name']: c for c in data['coils']}
        coils = [(c['name'], c['config'], reports[c['name']]['cad_volume_m3']) for c in data['config']['coils']]
    else:
        raise ValueError('Only circular- or rectangular-section DH pilot reports are supported')
    start = time.monotonic()
    gmsh.initialize([], readConfigFiles=False)
    components = []
    node_offset = element_offset = 0
    temporary = output.with_name(output.stem+'.partial.msh')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        for i, (name, config, cad_volume) in enumerate(coils, 1):
            gmsh.model.add(f'spine_{i}')
            rectangular = has_tape_section(config)
            if rectangular:
                half_span = config['tape_width_m']/2
                perimeter_nodes = 2*(tape_width_segments+tape_thickness_segments)
            else:
                half_span = config['conductor_radius_m']
                perimeter_nodes = sectors
            points, error = sample_spine(config, step, half_span*sagitta_fraction)
            count = len(points)*perimeter_nodes*3
            if element_offset+count > max_elements:
                raise ValueError(f'Element budget exceeded: {element_offset+count} > {max_elements}')
            if rectangular:
                nodes, tetra, volume, length = ribbon_tetrahedra(
                    points, config['tape_width_m'], config['tape_thickness_m'],
                    tape_width_segments, tape_thickness_segments)
            else:
                nodes, tetra, volume, length = tube_tetrahedra(points, config['conductor_radius_m'], sectors)
            gmsh.model.remove()
            if i == 1:
                gmsh.model.add('swept_conductors')
            else:
                gmsh.model.setCurrent('swept_conductors')
            tag = gmsh.model.addDiscreteEntity(3)
            gmsh.model.addPhysicalGroup(3, [tag], name=name)
            gmsh.model.mesh.addNodes(3, tag, np.arange(1, len(nodes)+1)+node_offset, nodes.ravel())
            gmsh.model.mesh.addElementsByType(tag, 4, np.arange(1, len(tetra)+1)+element_offset,
                                             (tetra.ravel()+node_offset+1))
            relative = volume/cad_volume-1
            if abs(relative) > .05:
                raise ValueError(f'{name}: volume differs from CAD by {relative:.2%}, exceeds pilot 5% guard')
            components.append({'group': name, 'tag': tag, 'volume_m3': volume, 'section': 'rectangular'
                               if rectangular else 'circular', 'cad_volume_m3': cad_volume,
                               'relative_volume_error': relative, 'nodes': len(nodes),
                               'tetrahedra': len(tetra), 'sections': len(points),
                               'path_length_m': length, 'maximum_midpoint_chord_error_m': error})
            node_offset += len(nodes)
            element_offset += len(tetra)
            print(f'[swept] {name}: {len(points)} sections, {len(tetra)} tetrahedra, CAD delta {relative:.3%}', flush=True)
        for name, value in {'Mesh.MshFileVersion':4.1, 'Mesh.Binary':0, 'Mesh.SaveAll':1}.items():
            gmsh.option.setNumber(name, value)
        gmsh.write(str(temporary))
        temporary.replace(output)
    finally:
        gmsh.finalize()
        temporary.unlink(missing_ok=True)
    report = {'method': 'spine_swept_linear_tetrahedra', 'production_validated': False,
              'source_sha256':digest(source), 'generator_sha256':digest(Path(__file__)),
              'controls_sha256':digest(Path(__file__).with_name('generate_dh.py')),
              'mesh_sha256':digest(output), 'gmsh':gmsh.__version__, 'numpy':np.__version__,
              'python':platform.python_version(), 'platform':platform.platform(),
              'longitudinal_step_m':step, 'sectors':sectors, 'sagitta_fraction':sagitta_fraction,
              'tape_width_segments':tape_width_segments, 'tape_thickness_segments':tape_thickness_segments,
              'elapsed_s':time.monotonic()-start, 'components':components}
    output.with_suffix('.mesh-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path, help='current_path.json or array_current_paths.json')
    p.add_argument('output', type=Path)
    p.add_argument('--longitudinal-step', type=float, default=.02)
    p.add_argument('--sectors', type=int, default=16)
    p.add_argument('--sagitta-fraction', type=float, default=.02)
    p.add_argument('--max-elements', type=int, default=5000000)
    p.add_argument('--tape-width-segments', type=int, default=4,
                    help='Rectangular tape section only (ignored for circular coils)')
    p.add_argument('--tape-thickness-segments', type=int, default=1,
                    help='Rectangular tape section only (ignored for circular coils)')
    a = p.parse_args()
    generate(a.source, a.output, a.longitudinal_step, a.sectors, a.sagitta_fraction, a.max_elements,
              a.tape_width_segments, a.tape_thickness_segments)
