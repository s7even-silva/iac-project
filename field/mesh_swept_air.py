#!/usr/bin/env python3
"""Structured swept tetrahedra for BOTH the conductor and a surrounding air
shell, for Elmer's FEM domain (GEOM14_STATUS.md brecha 3/4) -- the
counterpart to field/generate_elmer_domain.py, which builds the same two
regions via OpenCASCADE/Gmsh 2D+3D triangulation. That CAD route hangs for
multi-turn coils exactly like generate_mesh.py used to for the conductor
alone (confirmed empirically on a 5-turn/0.9m solenoid diagnostic case:
2D meshing never completed): this module avoids Gmsh 2D triangulation
entirely, the same fix mesh_swept.py already applies to the conductor-only
mesh, extended here to also cover the air shell around it.

The spine is a CLOSED loop (the Double Helix winding returns on itself),
so a tube of air around it is already a closed region -- no end caps are
needed, unlike an open solenoid or a straight wire segment.
"""
import argparse
import json
from pathlib import Path
import platform
import time

import gmsh
import numpy as np
from generate_mesh import digest
from mesh_swept import frames, sample_spine
from mesh_to_gdml import boundary as extract_boundary


def _hex_to_tets(corner_indices):
    """Split each hexahedron into 6 tetrahedra using a face-diagonal choice
    based only on each face's own global node indices (min-index corner is
    always one end of the diagonal), never on which hexahedron is asking.

    This is required, not cosmetic: a naive per-cell corner-order split
    (e.g. always (a,b,c,f)) picks a DIFFERENT diagonal on a shared face
    depending on which neighbouring hexahedron generated it, because the
    same physical face is labelled with different local corner names by
    its two owning cells. Two neighbours then triangulate their common
    face differently, leaving that face without a matching partner on
    each side -- boundary()'s manifold check catches exactly this
    ("Duplicate or inconsistently joined tetrahedra"), confirmed
    empirically on this module's first version. Keying every face's
    diagonal off its own sorted global indices makes both neighbours agree
    without communicating.

    `corner_indices` is (N, 8) node indices per hexahedron, ordered
    a,b,c,d (one quad face) then e,f,g,h (the opposite quad face, e above
    a, f above b, g above c, h above d). Returns (N*6, 4) tetrahedra.
    """
    a, b, c, d, e, f, g, h = corner_indices.T
    # Kuhn/Freudenthal-style split: for a hexahedron, always cut along the
    # space diagonal from the corner with the smallest global index (here,
    # `a` after a per-hexahedron rotation is not enough on its own -- what
    # actually needs to agree between neighbours is each SHARED FACE's
    # diagonal, not the cell's own space diagonal). Each of the 6
    # quadrilateral faces of the hexahedron is split along the diagonal
    # through its lowest-index corner; this is a function of that face's 4
    # global indices alone, so both hexahedra sharing a face compute the
    # same split independently.
    def face_diag_low(p, q, r, s):
        """Quad p,q,r,s (in order around the face); returns which corner
        is the low-index end of this face's canonical diagonal, and the
        two triangles that follow from cutting there."""
        idx = np.stack((p, q, r, s), axis=1)
        low = np.argmin(idx, axis=1)
        # Diagonal always connects the lowest-index corner to the corner
        # two steps around the quad from it (the opposite corner).
        opp = (low+2) % 4
        others = np.stack([(low+1) % 4, (low+3) % 4], axis=1)
        lo_val = idx[np.arange(len(idx)), low]
        opp_val = idx[np.arange(len(idx)), opp]
        o1 = idx[np.arange(len(idx)), others[:, 0]]
        o2 = idx[np.arange(len(idx)), others[:, 1]]
        return np.stack((lo_val, o1, opp_val), axis=1), np.stack((lo_val, opp_val, o2), axis=1)

    # A hexahedron with all 6 faces individually split this way is itself
    # split into 6 tetrahedra by additionally cutting from the single
    # global-lowest corner of the WHOLE hexahedron to each of the 6
    # triangulated face triangles that do not already contain it -- this
    # is the standard generalisation of "cone from the lowest vertex" and
    # is watertight because every face triangle used is one two hexahedra
    # sharing that face will always agree on (computed from that face's 4
    # global indices alone, independent of which hexahedron asks).
    corners = np.stack((a, b, c, d, e, f, g, h), axis=1)
    lowest_pos = np.argmin(corners, axis=1)
    apex = corners[np.arange(len(corners)), lowest_pos]
    faces = [(a, b, c, d), (e, f, g, h), (a, b, f, e), (b, c, g, f), (c, d, h, g), (d, a, e, h)]
    tets = []
    for p, q, r, s in faces:
        t1, t2 = face_diag_low(p, q, r, s)
        for tri in (t1, t2):
            # Skip degenerate cones where the apex is already a vertex of this triangle.
            keep = ~np.any(tri == apex[:, None], axis=1)
            cone = np.column_stack((tri, apex))
            tets.append(cone[keep])
    return np.concatenate(tets)


def _prism_tetrahedra(inner, outer, sectors):
    """Tetrahedra filling the shell between one closed ring of `inner`
    nodes and the corresponding closed ring of `outer` nodes, both
    (n_points, sectors, 3) arrays already positioned in world space, with
    sections advancing along axis 0 and sectors wrapping around axis 1.
    Returns tetrahedra indexing into the flattened
    `nodes = concatenate((inner, outer))` array, plus that flattened node
    array and the enclosed volume. See _hex_to_tets for why the diagonal
    choice must be keyed off global node indices, not per-cell corner order.
    """
    n_points = inner.shape[0]
    nodes = np.concatenate((inner.reshape(-1, 3), outer.reshape(-1, 3)))
    inner_index = (np.arange(n_points)[:, None]*sectors+np.arange(sectors)[None, :])
    outer_index = inner_index+n_points*sectors
    next_inner = np.roll(inner_index, -1, axis=0)
    next_outer = np.roll(outer_index, -1, axis=0)
    next_sector_inner = np.roll(inner_index, -1, axis=1)
    next_sector_outer = np.roll(outer_index, -1, axis=1)
    next_both_inner = np.roll(next_inner, -1, axis=1)
    next_both_outer = np.roll(next_outer, -1, axis=1)
    corners = np.stack((inner_index, next_sector_inner, next_both_inner, next_inner,
                        outer_index, next_sector_outer, next_both_outer, next_outer), axis=-1)
    corners = corners.reshape(-1, 8)
    tetra = _hex_to_tets(corners)
    volume = 0.
    for first in range(0, len(tetra), 200000):
        block = tetra[first:first+200000]
        v = nodes[block]
        determinant = np.linalg.det(v[:, 1:]-v[:, :1])
        negative = determinant < 0
        block[negative, :2] = block[negative, 1::-1]
        volume += float(np.abs(determinant).sum()/6)
    return nodes, tetra, volume


def conductor_and_air_tetrahedra(points, conductor_radius, air_radius, sectors):
    """Two conforming tetrahedral regions sharing the conductor's surface
    ring: `conductor` (centre-to-ring prisms, tube_tetrahedra's own scheme)
    and `air` (ring-to-ring prisms between conductor_radius and air_radius,
    a single shell -- not a large enclosing sphere, so this is a compact
    near-field air domain, not a full free-space truncation; see the field
    error this trades off in GEOM14_STATUS.md brecha 3/4).

    `air_radius` is bounded above by the spine's own local radius of
    curvature: a tube wider than the curve can bend around self-intersects
    at sharp bends (confirmed empirically on the Double Helix pilot's
    smoothed return sections, minimum radius of curvature ~0.038m vs. a
    naively chosen air_radius of 0.072m -- boundary()'s manifold check
    catches this as broken topology, not a clean error). Checked
    explicitly here with a safety margin, rather than only failing later
    inside a topology check whose message does not point at the cause.
    """
    if not 0 < conductor_radius < air_radius:
        raise ValueError('Require 0 < conductor_radius < air_radius')
    normals, binormals, length = frames(points)
    delta = np.roll(points, -1, axis=0)-points
    segment_lengths = np.linalg.norm(delta, axis=1)
    tangent = delta/segment_lengths[:, None]
    dtangent = np.roll(tangent, -1, axis=0)-tangent
    curvature = np.linalg.norm(dtangent, axis=1)/segment_lengths
    min_curvature_radius = 1/max(float(np.max(curvature)), 1e-12)
    if air_radius >= .8*min_curvature_radius:
        raise ValueError(
            f'air_radius={air_radius:.4g} m is too large for this spine: minimum radius of '
            f'curvature is {min_curvature_radius:.4g} m and the air tube would self-intersect '
            f'at sharp bends (need air_radius < 0.8*{min_curvature_radius:.4g}='
            f'{.8*min_curvature_radius:.4g} m)')
    angle = np.arange(sectors)*2*np.pi/sectors
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    def ring(radius):
        return (points[:, None, :]+radius*(normals[:, None, :]*cos_a[None, :, None]
                                           +binormals[:, None, :]*sin_a[None, :, None]))
    conductor_ring = ring(conductor_radius)
    air_ring = ring(air_radius)

    # Conductor: centre-to-ring prisms, same topology as tube_tetrahedra().
    n_points = len(points)
    conductor_nodes = np.concatenate((points[:, None, :], conductor_ring), axis=1).reshape(-1, 3)
    sections = np.arange(n_points)[:, None]*(sectors+1)
    next_sections = np.roll(sections, -1, axis=0)
    columns = np.sort(np.column_stack((np.zeros(sectors, dtype=int),
                        1+np.arange(sectors), 1+(np.arange(sectors)+1) % sectors)), axis=1)
    a, b, c = [(sections+columns[:, k]).ravel() for k in range(3)]
    d, e, f = [(next_sections+columns[:, k]).ravel() for k in range(3)]
    conductor_tetra = np.concatenate((np.column_stack((a, b, c, d)), np.column_stack((b, c, d, e)),
                                      np.column_stack((c, d, e, f))))
    expected = np.tile(np.where(np.arange(sectors) == sectors-1, -1, 1), n_points)
    expected = np.tile(expected, 3)
    conductor_volume = 0.
    for first in range(0, len(conductor_tetra), 200000):
        block = conductor_tetra[first:first+200000]
        v = conductor_nodes[block]
        determinant = np.linalg.det(v[:, 1:]-v[:, :1])
        if np.any(determinant*expected[first:first+len(block)] <= 0):
            raise ValueError('Inverted conductor cell: refine spine or inspect curvature')
        negative = determinant < 0
        block[negative, :2] = block[negative, 1::-1]
        conductor_volume += float(np.abs(determinant).sum()/6)

    air_nodes, air_tetra, air_volume = _prism_tetrahedra(conductor_ring, air_ring, sectors)
    # air_nodes duplicates the conductor ring at its own indices 0..n_points*sectors-1;
    # reindex the air region's tetrahedra to share those exact nodes with the
    # conductor mesh (same coordinates, by construction) rather than keep a
    # second duplicate copy -- required for a conforming interface in Elmer.
    # conductor_nodes layout is [centre_0, ring_0(0..sectors-1), centre_1, ring_1(...), ...]
    # so ring node (point i, sector j) sits at conductor_nodes index i*(sectors+1)+1+j.
    ring_lookup = (np.arange(n_points)[:, None]*(sectors+1)+1+np.arange(sectors)[None, :]).ravel()
    air_tetra_reindexed = air_tetra.copy()
    is_inner = air_tetra < n_points*sectors
    air_tetra_reindexed[is_inner] = ring_lookup[air_tetra[is_inner]]
    air_tetra_reindexed[~is_inner] = air_tetra[~is_inner]-n_points*sectors+len(conductor_nodes)
    combined_nodes = np.concatenate((conductor_nodes, air_nodes[n_points*sectors:]))
    outer_node_indices = np.arange(len(conductor_nodes), len(combined_nodes))
    return (conductor_nodes, conductor_tetra, conductor_volume,
            combined_nodes, air_tetra_reindexed, air_volume, length, outer_node_indices)


def generate(source, output, air_radius_factor=6.0, step=.02, sectors=16,
             sagitta_fraction=.02, max_elements=5000000):
    """Conformal conductor+air domain for Elmer (GEOM14_STATUS.md brecha
    3/4), circular-section pilots only (see generate_dh.py's
    has_tape_section() -- not yet extended to the rectangular tape here).

    `air_radius_factor` sets the air shell's outer radius as a multiple of
    conductor_radius_m: this is a COMPACT near-field air domain (a tube
    around the spine), not a large enclosing sphere like
    generate_elmer_domain.py's OpenCASCADE route -- trades a smaller,
    always-completes mesh for a shorter far-field truncation distance
    (more boundary-condition error at the outer surface). See
    GEOM14_STATUS.md for the resulting field validation against
    Biot-Savart.
    """
    if output.suffix != '.msh' or sectors < 8 or air_radius_factor <= 1:
        raise ValueError('Require .msh, sectors>=8, air_radius_factor>1')
    if not np.isfinite([step, sagitta_fraction]).all() or step <= 0 or not 0 < sagitta_fraction < .1:
        raise ValueError('Require positive step and 0<sagitta_fraction<0.1')
    data = json.loads(source.read_text())
    if data['status'] != 'computational_pilot_not_geom14':
        raise ValueError('Only the single-coil circular-section pilot report is supported')
    config = data['config']
    conductor_radius = config['conductor_radius_m']
    air_radius = conductor_radius*air_radius_factor
    cad_volume = data['cad_volume_m3']

    start = time.monotonic()
    gmsh.initialize([], readConfigFiles=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.stem+'.partial.msh')
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        points, error = sample_spine(config, step, conductor_radius*sagitta_fraction)
        (cond_nodes, cond_tetra, cond_volume, combined_nodes, air_tetra,
         air_volume, length, outer_node_indices) = conductor_and_air_tetrahedra(
             points, conductor_radius, air_radius, sectors)
        relative = cond_volume/cad_volume-1
        if abs(relative) > .05:
            raise ValueError(f'Conductor volume differs from CAD by {relative:.2%}, exceeds pilot 5% guard')

        # Outer boundary faces: extract the air region's full closed surface
        # (boundary() already validates it is a closed oriented manifold),
        # then keep only the faces whose 3 corners are all outer-shell nodes
        # -- the conductor/air interface faces have at least one corner on
        # the inner ring instead, so this cleanly separates the two without
        # a second, separate distance-based classification.
        all_air_points = {i: combined_nodes[i] for i in np.unique(air_tetra)}
        air_faces, _ = extract_boundary(air_tetra, all_air_points)
        outer_set = set(outer_node_indices.tolist())
        outer_faces = np.array([f for f in air_faces if all(v in outer_set for v in f)])
        if len(outer_faces) == 0:
            raise ValueError('Could not identify any outer boundary faces')

        gmsh.model.remove()
        gmsh.model.add('conductor_and_air')
        conductor_tag = gmsh.model.addDiscreteEntity(3)
        gmsh.model.addPhysicalGroup(3, [conductor_tag], name='conductor')
        gmsh.model.mesh.addNodes(3, conductor_tag, np.arange(1, len(cond_nodes)+1), cond_nodes.ravel())
        gmsh.model.mesh.addElementsByType(conductor_tag, 4, np.arange(1, len(cond_tetra)+1),
                                          cond_tetra.ravel()+1)
        air_tag = gmsh.model.addDiscreteEntity(3)
        gmsh.model.addPhysicalGroup(3, [air_tag], name='air')
        # combined_nodes' first len(cond_nodes) entries ARE cond_nodes (by
        # construction in conductor_and_air_tetrahedra) -- only the air-only
        # tail needs adding to Gmsh; air_tetra already indexes the full
        # combined_nodes array (1-based after the +1 below).
        air_only_nodes = combined_nodes[len(cond_nodes):]
        gmsh.model.mesh.addNodes(3, air_tag, np.arange(len(cond_nodes)+1, len(combined_nodes)+1),
                                 air_only_nodes.ravel())
        gmsh.model.mesh.addElementsByType(air_tag, 4, np.arange(1, len(air_tetra)+1), air_tetra.ravel()+1)
        # 2D physical surface for the outer boundary: ElmerGrid needs actual
        # 2D elements in the .msh to populate mesh.boundary -- a Physical
        # Volume alone (as generated above) produces an EMPTY mesh.boundary
        # (confirmed empirically), leaving Elmer with no way to apply the
        # far-field AV=0 condition.
        boundary_tag = gmsh.model.addDiscreteEntity(2)
        gmsh.model.addPhysicalGroup(2, [boundary_tag], name='outer_boundary')
        gmsh.model.mesh.addElementsByType(boundary_tag, 2, np.arange(1, len(outer_faces)+1),
                                          outer_faces.ravel()+1)
        for name, value in {'Mesh.MshFileVersion': 4.1, 'Mesh.Binary': 0, 'Mesh.SaveAll': 1}.items():
            gmsh.option.setNumber(name, value)
        gmsh.write(str(temporary))
        temporary.replace(output)
    finally:
        gmsh.finalize()
        temporary.unlink(missing_ok=True)

    report = {'method': 'spine_swept_conductor_and_air_shell', 'production_validated': False,
              'source_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
              'mesh_sha256': digest(output), 'numpy': np.__version__,
              'python': platform.python_version(), 'platform': platform.platform(),
              'longitudinal_step_m': step, 'sectors': sectors, 'sagitta_fraction': sagitta_fraction,
              'conductor_radius_m': conductor_radius, 'air_radius_m': air_radius,
              'air_radius_factor': air_radius_factor,
              'conductor_volume_m3': cond_volume, 'cad_volume_m3': cad_volume,
              'relative_volume_error': relative, 'air_volume_m3': air_volume,
              'path_length_m': length, 'maximum_midpoint_chord_error_m': error,
              'conductor_nodes': len(cond_nodes), 'conductor_tetrahedra': len(cond_tetra),
              'air_nodes': len(combined_nodes)-len(cond_nodes), 'air_tetrahedra': len(air_tetra),
              'elapsed_s': time.monotonic()-start}
    output.with_suffix('.mesh-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'[swept-air] conductor: {len(cond_tetra)} tetrahedra, CAD delta {relative:.3%}; '
          f'air: {len(air_tetra)} tetrahedra, radius factor {air_radius_factor}', flush=True)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path, help='current_path.json from generate_dh.py')
    p.add_argument('output', type=Path)
    p.add_argument('--air-radius-factor', type=float, default=6.0)
    p.add_argument('--longitudinal-step', type=float, default=.02)
    p.add_argument('--sectors', type=int, default=16)
    p.add_argument('--sagitta-fraction', type=float, default=.02)
    p.add_argument('--max-elements', type=int, default=5000000)
    a = p.parse_args()
    generate(a.source, a.output, a.air_radius_factor, a.longitudinal_step, a.sectors,
             a.sagitta_fraction, a.max_elements)
