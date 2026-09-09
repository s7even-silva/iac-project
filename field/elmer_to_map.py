#!/usr/bin/env python3
"""Resample Elmer's FEM magnetic field (ascii VTU, unstructured tetrahedral
mesh) onto the uniform regular grid Geant4's TabulatedMagneticField reads
(same .map format as compute_field.py's regularized Biot-Savart pilot map,
so the two are directly comparable point-by-point -- GEOM14_STATUS.md
brecha 4).

Deliberately parses the ascii VTU with the standard library only (no vtk/
pyvista): field/.venv is pinned to Gmsh+NumPy (see AGENTS.md, "Entorno
Python aislado") and this is the only place in the pipeline that needs to
read an Elmer result, so a full VTK dependency is not worth adding for one
consumer. Elmer's "Ascii Output = True" + "Vtu format = Logical True"
(ResultOutputSolver) writes plain-text numbers inside <DataArray> elements,
which is what makes this feasible.

Interpolation is nearest-tetrahedron point sampling via a barycentric
containment search over a coarse spatial hash of tetrahedra -- not a
production-grade FEM interpolator. Good enough for a pilot validation
against Biot-Savart (brecha 4); revisit if resampling a production-size
mesh becomes a bottleneck.
"""
import argparse
import json
from pathlib import Path
import platform
import xml.etree.ElementTree as ET

import numpy as np
from generate_mesh import digest


_B_NAMES = ('magnetic flux density', 'b', 'magnetic flux density_1')


def load_vtu(path):
    """Points, tetrahedra (4-node connectivity) and per-node B (T) from one
    ascii VTU piece written by Elmer's ResultOutputSolver.

    Uses iterparse + element.clear() rather than ET.parse(): a full DOM of
    a several-hundred-MB ascii VTU (one <DataArray> text node per field,
    each holding every node's value as literal ASCII floats) held the
    whole file in memory multiple times over and was OOM-killed on this
    machine's 5.7GB RAM while running immediately after ElmerSolver itself
    (which was still holding several GB). Streaming parse + dropping each
    <DataArray> (and its now-parsed text) right after reading it keeps peak
    memory close to just the NumPy arrays this function returns.
    """
    points = tetrahedra = b = None
    connectivity = offsets = types = None
    current_section = None  # 'Points' | 'Cells' | 'PointData' | None
    for event, elem in ET.iterparse(path, events=('start', 'end')):
        tag = elem.tag
        if event == 'start':
            if tag in ('Points', 'Cells', 'PointData'):
                current_section = tag
            continue
        # event == 'end'
        if tag == 'DataArray' and current_section is not None:
            name = elem.get('Name')
            components = int(elem.get('NumberOfComponents', 1))
            if current_section == 'Points' and name is None:
                points = np.fromstring(elem.text or '', sep=' ').reshape(-1, 3)
            elif current_section == 'Cells' and name == 'connectivity':
                connectivity = np.fromstring(elem.text or '', sep=' ', dtype=np.int64)
            elif current_section == 'Cells' and name == 'offsets':
                offsets = np.fromstring(elem.text or '', sep=' ', dtype=np.int64)
            elif current_section == 'Cells' and name == 'types':
                types = np.fromstring(elem.text or '', sep=' ', dtype=np.int64)
            elif current_section == 'PointData' and (name or '').lower() in _B_NAMES:
                values = np.fromstring(elem.text or '', sep=' ')
                b = values.reshape(-1, components) if components > 1 else values
            elem.clear()  # drop this array's text now that it is parsed into NumPy
        elif tag in ('Points', 'Cells', 'PointData'):
            current_section = None
            elem.clear()
    if points is None:
        raise ValueError(f'{path}: no <Points><DataArray> found')
    if connectivity is None or offsets is None or types is None:
        raise ValueError(f'{path}: missing connectivity/offsets/types in <Cells>')
    # VTK_TETRA = 10 (linear, 4-node); this pipeline only ever emits first-order tets.
    is_tet = types == 10
    if not np.any(is_tet):
        raise ValueError(f'{path}: no linear tetrahedra (VTK type 10) found')
    starts = np.concatenate(([0], offsets[:-1]))
    tet_starts, tet_ends = starts[is_tet], offsets[is_tet]
    if not np.all(tet_ends-tet_starts == 4):
        raise ValueError('Expected exactly 4 nodes per tetrahedron cell')
    tetrahedra = np.stack([connectivity[s:s+4] for s in tet_starts])
    if b is None:
        raise ValueError('No magnetic flux density field found in PointData; '
                         'check "Calculate Magnetic Field Strength" / field name in the .sif')
    b = b.reshape(len(points), -1)
    if b.shape[1] != 3:
        raise ValueError(f'Expected a 3-component field, got {b.shape[1]} components')
    return points, tetrahedra, b


def _tetrahedron_barycentric(query, p0, p1, p2, p3):
    """Barycentric coords of `query` (N,3) in tetrahedra (N,3 each vertex)."""
    m = np.stack((p1-p0, p2-p0, p3-p0), axis=-1)  # (N,3,3)
    rhs = query-p0
    det = np.linalg.det(m)
    singular = np.abs(det) < 1e-30
    safe_det = np.where(singular, 1.0, det)
    inv = np.linalg.inv(np.where(singular[:, None, None], np.eye(3), m))
    uvw = np.einsum('nij,nj->ni', inv, rhs)
    l1, l2, l3 = uvw[:, 0], uvw[:, 1], uvw[:, 2]
    l0 = 1-l1-l2-l3
    inside = (~singular) & (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
    return np.stack((l0, l1, l2, l3), axis=-1), inside


def _grid_hash(bounds_min, bounds_max, cell_size):
    """Bucket tetrahedra into every cell their axis-aligned bounding box
    overlaps (not just the cell of their centroid): a graded mesh has
    tetrahedra tens of times larger than the median near the outer
    boundary (confirmed empirically: median span ~1cm, max ~0.67m on the
    pilot's air domain), so centroid-only bucketing under-covers exactly
    the coarse, far-from-conductor region a Biot-Savart comparison (brecha
    4) most needs. Returns a dict mapping cell key (tuple) to tetrahedron
    indices."""
    lo = np.floor(bounds_min/cell_size).astype(np.int64)
    hi = np.floor(bounds_max/cell_size).astype(np.int64)
    buckets = {}
    for t in range(len(lo)):
        xs = range(lo[t, 0], hi[t, 0]+1)
        ys = range(lo[t, 1], hi[t, 1]+1)
        zs = range(lo[t, 2], hi[t, 2]+1)
        for x in xs:
            for y in ys:
                for z in zs:
                    buckets.setdefault((x, y, z), []).append(t)
    return {key: np.asarray(v, dtype=np.int64) for key, v in buckets.items()}


def resample(points, tetrahedra, b, grid_points):
    """For each grid point, find an enclosing tetrahedron via a uniform
    spatial hash (no O(chunk*T) distance matrix -- that blew past available
    RAM on a 2.6M-tetrahedron mesh, see GEOM14_STATUS.md brecha 4 notes)
    and barycentrically interpolate B there; NaN if no tetrahedron of this
    mesh contains it (point outside the meshed air domain)."""
    coords = points[tetrahedra]  # (T,4,3)
    bounds_min, bounds_max = coords.min(axis=1), coords.max(axis=1)
    spans = bounds_max-bounds_min
    # A graded mesh has tetrahedra tens of times larger than the median far
    # from the conductor (confirmed: median span ~1cm, p99 ~10cm, max
    # ~0.67m on the pilot's air domain) -- size cells off a high percentile,
    # not the median, so a single big tetrahedron touches a bounded number
    # of cells (a few dozen, not hundreds of thousands) while still being
    # correctly bucketed into every cell its bounding box overlaps.
    cell_size = max(float(np.percentile(spans.max(axis=1), 95)), 1e-9)
    buckets = _grid_hash(bounds_min, bounds_max, cell_size)
    result = np.full((len(grid_points), 3), np.nan)
    query_cells = np.floor(grid_points/cell_size).astype(np.int64)
    for i, (point, cell) in enumerate(zip(grid_points, query_cells)):
        key = tuple(cell)
        candidates = buckets.get(key)
        if candidates is None or len(candidates) == 0:
            continue
        p0, p1, p2, p3 = (coords[candidates, k] for k in range(4))
        query = np.repeat(point[None, :], len(candidates), axis=0)
        bary, inside = _tetrahedron_barycentric(query, p0, p1, p2, p3)
        hit = np.flatnonzero(inside)
        if len(hit) == 0:
            continue
        result[i] = bary[hit[0]] @ b[tetrahedra[candidates[hit[0]]]]
    return result


def generate(vtu, source, output, half_size, spacing, max_points):
    if output.suffix != '.map':
        raise ValueError('Use a .map output, matching compute_field.py')
    from compute_field import grid_shape
    n, step = grid_shape(half_size, spacing)
    if n**3 > max_points:
        raise ValueError(f'{n**3:,} nodes exceed --max-points={max_points:,}; plan/refine explicitly')
    points, tetrahedra, b = load_vtu(vtu)
    data = json.loads(source.read_text())
    center = np.asarray(data['config']['center_m'])
    output.parent.mkdir(parents=True, exist_ok=True)
    edge_max, coverage = 0.0, 0
    temporary = output.with_suffix(output.suffix+'.tmp')
    try:
        with temporary.open('w') as f:
            f.write('# Elmer FEM resampled field; m and T; pilot, brecha 4 validation not yet done\n')
            f.write(f'{n} {n} {n}\n{-half_size} {-half_size} {-half_size}\n{step} {step} {step}\n')
            for first in range(0, n**3, 4096):
                indices = np.arange(first, min(first+4096, n**3))
                ijk = np.column_stack((indices % n, indices//n % n, indices//(n*n)))
                grid_points = -half_size+step*ijk+center
                values = resample(points, tetrahedra, b, grid_points)
                coverage += int(np.sum(np.isfinite(values[:, 0])))
                edge = np.any((ijk == 0) | (ijk == n-1), axis=1)
                finite_edge = edge & np.isfinite(values[:, 0])
                if np.any(finite_edge):
                    edge_max = max(edge_max, float(np.max(np.linalg.norm(values[finite_edge], axis=1))))
                np.nan_to_num(values, copy=False)
                np.savetxt(f, values, fmt='%.12e')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {'model': 'elmer_fem_resampled_pilot', 'vtu_sha256': digest(vtu),
              'source_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
              'map_sha256': digest(output), 'python': platform.python_version(),
              'numpy': np.__version__, 'platform': platform.platform(),
              'half_size_m': half_size, 'spacing_m': step, 'shape': [n]*3,
              'grid_points_covered': coverage, 'grid_points_total': n**3,
              'boundary_max_T': edge_max, 'production_validated': False}
    output.with_suffix('.field-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('vtu', type=Path, help='Ascii VTU written by ResultOutputSolver')
    p.add_argument('source', type=Path, help='domain.json from generate_elmer_domain.py')
    p.add_argument('output', type=Path)
    p.add_argument('--half-size', type=float, required=True)
    p.add_argument('--spacing', type=float, required=True)
    p.add_argument('--max-points', type=int, default=1000000)
    a = p.parse_args()
    generate(a.vtu, a.source, a.output, a.half_size, a.spacing, a.max_points)
