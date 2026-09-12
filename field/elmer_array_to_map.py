#!/usr/bin/env python3
"""Resample an Elmer FEM result for the 8-coil CREW HaT array (ascii VTU,
'air' body only) onto the uniform grid Geant4's TabulatedMagneticField
reads -- same .map format as compute_field_ellipse_array.py's Biot-Savart
map, so the two are directly comparable point-by-point.

Exists because elmer_to_map.py's CLI expects domain.json from
generate_elmer_domain.py (the single-conductor DH pilot's domain
generator) -- the array runs (field/generated/crewhat_elmer_array{,_r2})
were built with mesh_swept_air.py/generate_elmer_domain.py directly from
the command line (see field/CREWHAT_STATUS.md), with no equivalent
domain.json artifact. This script skips that layer and calls load_vtu()/
resample() directly, exactly like compare_elmer_array.py already does for
point probes -- same interpolation (nearest-tetrahedron barycentric via
elmer_to_map.py's spatial hash), just written out as a full grid instead
of a handful of points.

The requested half-size/spacing MUST fit inside the meshed air domain
(see domain.mesh-manifest.json's bounds_m for the run in question) or
resample() returns NaN for the points outside it, which this script
refuses to write (TabulatedMagneticField requires all-finite input).

--half-size takes 1 or 3 values (2026-09-12, fixed after a review of the
first version of this script correctly pointed out the map was a cube
sized to the shortest domain axis, wasting the real headroom on the
other two): the meshed domain from mesh_exterior.py is NOT a cube -- the
Halbach ring lives mostly in the coil array's XY plane (its own
generate_ellipse_array.py bounding box, then padded by the same amount on
every side), so it reaches much farther there than along the ship's Z
axis. A cubic map inherits the shortest axis for ALL three, which clips
the field at zero well inside where the ring (and now, since
coilGeometry imports by default, the coils' own solid) actually sits in
X/Y -- not just a wasted-headroom issue, a real physics gap for any
charged secondary that reaches that region. The .map format Geant4 reads
(TabulatedMagneticField.cc) already supports independent nx/ny/nz and
dx/dy/dz per axis; only this exporter was forcing a cube.
"""
import argparse
from pathlib import Path
import platform

import numpy as np

from compute_field import grid_shape
from elmer_to_map import load_vtu, resample
from provenance import digest


def _fill_conductor_gaps(grid, b, max_gap_fraction=0.05):
    """Nodes with no enclosing air tetrahedron are, on a well-formed
    domain, inside a coil's own conductor cross-section (verified
    2026-09-11: on the full-scale array domain, every NaN node sat
    ~3-4x the Biot-Savart regularization radius from a coil path --
    i.e. within the real winding-pack half-width, not a meshing hole).
    Elmer never solves the field *inside* a conductor as part of the
    air body, so this is expected, not a bug -- fill with the nearest
    valid air node's value instead of failing outright. A grid node
    landing there is also never a point a real trajectory occupies:
    the actual conductor SOLID is imported separately via
    /spacecraft/coilGeometry and stops/scatters particles there before
    any field lookup at that exact node would matter for dosimetry
    of the ship interior.

    Refuses to paper over a genuinely broken mesh: caps how much of
    the grid this may cover."""
    bad = ~np.isfinite(b).all(axis=1)
    n_bad = int(bad.sum())
    if n_bad == 0:
        return b, 0
    if n_bad > max_gap_fraction*len(b):
        raise ValueError(f'{n_bad:,} of {len(b):,} grid points ({n_bad/len(b):.1%}) have no enclosing air '
                          f'tetrahedron -- exceeds the {max_gap_fraction:.0%} expected from conductor '
                          'cross-sections alone; treat as a broken/undersized mesh, not a gap to fill')
    good_idx = np.flatnonzero(~bad)
    bad_idx = np.flatnonzero(bad)
    # Brute-force nearest neighbour: n_bad is always small (a handful of
    # conductor-interior nodes), so an O(n_bad * n_good) search is cheap.
    for i in bad_idx:
        d2 = np.sum((grid[good_idx]-grid[i])**2, axis=1)
        b[i] = b[good_idx[np.argmin(d2)]]
    return b, n_bad


def generate(vtu, output, half_size_xyz, spacing, max_points):
    """half_size_xyz: (half_x, half_y, half_z) in metres -- independent per
    axis (pass the same value 3x for the old cubic behaviour)."""
    if output.suffix != '.map' or output.resolve() == vtu.resolve():
        raise ValueError('Use a distinct .map output')
    shapes = [grid_shape(h, spacing) for h in half_size_xyz]
    (nx, stepx), (ny, stepy), (nz, stepz) = shapes
    n_total = nx*ny*nz
    if n_total > max_points:
        raise ValueError(f'{n_total:,} nodes exceed --max-points={max_points:,}; plan/refine explicitly')
    points, tetra, values = load_vtu(vtu)
    hx, hy, hz = half_size_xyz
    grid = np.array([(-hx+stepx*(i % nx), -hy+stepy*(i//nx % ny), -hz+stepz*(i//(nx*ny)))
                      for i in range(n_total)])
    b = resample(points, tetra, values, grid)
    b, n_filled = _fill_conductor_gaps(grid, b)
    if not np.isfinite(b).all():
        n_bad = int(np.count_nonzero(~np.isfinite(b).all(axis=1)))
        raise ValueError(f'{n_bad:,} of {n_total:,} grid points still non-finite after conductor-gap fill -- '
                          'shrink --half-size or check domain.mesh-manifest.json bounds_m for this run')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    try:
        with temporary.open('w') as f:
            f.write(f'# Elmer FEM resample of {vtu.name}, array of 8 coils; m and T; not production\n')
            f.write(f'{nx} {ny} {nz}\n{-hx} {-hy} {-hz}\n{stepx} {stepy} {stepz}\n')
            np.savetxt(f, b, fmt='%.12e')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {'model': 'elmer_fem_array_resample', 'vtu_sha256': digest(vtu),
              'generator_sha256': digest(Path(__file__)), 'map_sha256': digest(output),
              'python': platform.python_version(), 'numpy': np.__version__,
              'platform': platform.platform(), 'half_size_m': list(half_size_xyz),
              'spacing_m': [stepx, stepy, stepz], 'shape': [nx, ny, nz],
              'conductor_gap_nodes_filled': n_filled, 'production_validated': False}
    output.with_suffix('.field-manifest.json').write_text(__import__('json').dumps(report, indent=2)+'\n')
    print(__import__('json').dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('vtu', type=Path, help="Elmer's *_air_t0001.vtu (ResultOutputSolver ascii output)")
    p.add_argument('output', type=Path)
    p.add_argument('--half-size', type=float, nargs='+', required=True,
                    help='Map half-size(s) in metres: one value for a cube (old behaviour), or 3 '
                         '(X Y Z) for an anisotropic box matching the real (non-cubic) meshed domain')
    p.add_argument('--spacing', type=float, required=True, help='Maximum grid step in metres (shared by all axes)')
    p.add_argument('--max-points', type=int, default=1000000)
    a = p.parse_args()
    if len(a.half_size) == 1:
        half_size_xyz = (a.half_size[0],)*3
    elif len(a.half_size) == 3:
        half_size_xyz = tuple(a.half_size)
    else:
        p.error('--half-size takes 1 value (cube) or 3 values (X Y Z)')
    generate(a.vtu, a.output, half_size_xyz, a.spacing, a.max_points)
