#!/usr/bin/env python3
"""Volumetric Biot-Savart field map of the CREW HaT coil array, reading
array_current_paths.json from generate_ellipse_array.py. No FEM and no finite
domain: the map can be as large as the source sphere needs.

With no magnetic materials (mu_r = 1, the same assumption as the Elmer .sif),
the field of a prescribed current is exactly the Biot-Savart integral of its
current density. compute_field_ellipse_array.py puts each coil's whole current
on its centreline, which is wrong near a 0.67 m winding pack. Here each pack
is split into n_radial x n_axial parallel filaments with equal current (turns
in series give a uniform current density), laid out like the CAD rectangle:
radial across the coil plane, axial along its normal. What remains is
quadrature error (filaments, and segments per loop), measured by refining
both with validate_volumetric_field.py.

Each straight segment uses the exact line-current formula outside a round core
with the filament's own cross-section area, and the uniform round-wire profile
inside it, so the field stays finite inside the pack (solid conductor, where
the value matters little for transport).
"""
import argparse
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import shutil
import sys
import time

import numpy as np

from compute_field import grid_shape
from generate_ellipse import pack_section
from provenance import digest


def filaments(path, radial, axial, n_radial, n_axial):
    """Closed polylines of the n_radial x n_axial filaments of one planar coil."""
    loop = np.asarray(path, dtype=float)[:-1]
    normal = np.cross(loop, np.roll(loop, -1, axis=0)).sum(0)  # Newell: right-handed with the current
    normal /= np.linalg.norm(normal)
    tangent = np.roll(loop, -1, axis=0)-np.roll(loop, 1, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    outward = np.cross(tangent, normal)
    lines = []
    for a in ((np.arange(n_radial)+.5)/n_radial-.5)*radial:
        for b in ((np.arange(n_axial)+.5)/n_axial-.5)*axial:
            line = loop+a*outward+b*normal
            lines.append(np.vstack((line, line[:1])))
    return lines


class Segments:
    """All straight segments of all filaments, ready for field()."""

    def __init__(self, data, n_radial, n_axial):
        if n_radial < 1 or n_axial < 1:
            raise ValueError('Require at least one filament per direction')
        radial, axial = pack_section(data['config']['coil_template'])
        self.core = math.sqrt(radial*axial/(n_radial*n_axial)/math.pi)
        start, end, current = [], [], []
        for coil in data['coils']:
            share = coil['current_A']/(n_radial*n_axial)
            for line in filaments(coil['path_m'], radial, axial, n_radial, n_axial):
                start.append(line[:-1])
                end.append(line[1:])
                current.append(np.full(len(line)-1, share))
        self.start = np.vstack(start)
        delta = np.vstack(end)-self.start
        self.length = np.linalg.norm(delta, axis=1)
        self.dir = delta/self.length[:, None]
        self.current = np.concatenate(current)


def field(points, seg, chunk_points=4096, chunk_segments=256):
    """B in tesla at points (N x 3, metres)."""
    points = np.asarray(points, dtype=float)
    out = np.zeros_like(points)
    core2 = seg.core**2
    for i in range(0, len(points), chunk_points):
        px, py, pz = (points[i:i+chunk_points, k][:, None] for k in range(3))
        bx = by = bz = 0.
        for j in range(0, len(seg.length), chunk_segments):
            part = slice(j, j+chunk_segments)
            ux, uy, uz = seg.dir[part].T
            rx, ry, rz = px-seg.start[part, 0], py-seg.start[part, 1], pz-seg.start[part, 2]
            cx, cy, cz = uy*rz-uz*ry, uz*rx-ux*rz, ux*ry-uy*rx  # u x r = u x rho
            q = cx*cx+cy*cy+cz*cz  # rho^2 without cancellation
            s = rx*ux+ry*uy+rz*uz
            e = s-seg.length[part]
            # Exact segment formula; max(q, core^2) switches to the uniform-wire core.
            f = (s/np.sqrt(q+s*s+1e-300)-e/np.sqrt(q+e*e+1e-300))*(seg.current[part]/np.maximum(q, core2))
            bx, by, bz = bx+(f*cx).sum(1), by+(f*cy).sum(1), bz+(f*cz).sum(1)
        out[i:i+chunk_points] = np.column_stack((bx, by, bz))
    return out*1e-7  # mu0/(4 pi)


def trilinear(values, origin, step, points):
    """Same interpolation as MagneticFieldMap::Evaluate (values: nz x ny x nx x 3)."""
    shape = np.array(values.shape[2::-1])
    cell = (points-origin)/step
    index = np.clip(np.floor(cell).astype(int), 0, shape-2)
    w = np.clip(cell-index, 0., 1.)
    out = np.zeros_like(points)
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                weight = ((w[:, 0] if dx else 1-w[:, 0])*(w[:, 1] if dy else 1-w[:, 1])
                          * (w[:, 2] if dz else 1-w[:, 2]))
                out += weight[:, None]*values[index[:, 2]+dz, index[:, 1]+dy, index[:, 0]+dx]
    return out


_SEGMENTS = None


def _init(seg):
    global _SEGMENTS
    _SEGMENTS = seg


def _row(args):
    xs, y, z = args  # one row of x at fixed (y, z): x fastest, as the map format expects
    return field(np.column_stack((xs, np.full(len(xs), y), np.full(len(xs), z))), _SEGMENTS)


def interpolation_check(values, origin, step, seg, n, seed=20261031):
    """Trilinear map against direct evaluation at n random points per region.
    Relative errors only where |B| >= 10 mT (the habitat centre is ~0)."""
    rng = np.random.default_rng(seed)
    upper = origin+step*(np.array(values.shape[2::-1])-1)
    def habitat(p):
        return (np.hypot(p[:, 0], p[:, 1]) < 4.5) & (np.abs(p[:, 2]) < 5)
    regions = {'habitat (r<4.5 m, |z|<5 m)': habitat,
               'coils (|p|<12 m, outside habitat)': lambda p: (np.linalg.norm(p, axis=1) < 12) & ~habitat(p),
               'outer (|p|>=12 m)': lambda p: np.linalg.norm(p, axis=1) >= 12}
    report = {}
    for name, inside in regions.items():
        points = np.empty((0, 3))
        for _ in range(1000):
            candidate = rng.uniform(np.maximum(origin, -12) if name != 'outer (|p|>=12 m)' else origin,
                                    np.minimum(upper, 12) if name != 'outer (|p|>=12 m)' else upper,
                                    size=(20*n, 3))
            points = np.vstack((points, candidate[inside(candidate)]))[:n]
            if len(points) == n:
                break
        direct = field(points, seg)
        error = np.linalg.norm(trilinear(values, origin, step, points)-direct, axis=1)*1e3
        magnitude = np.linalg.norm(direct, axis=1)*1e3
        strong = magnitude >= 10
        report[name] = {'points': len(points),
                        'error_mT_p50_p95_max': np.percentile(error, [50, 95, 100]).tolist(),
                        'field_mT_p50_p95': np.percentile(magnitude, [50, 95]).tolist(),
                        'relative_where_B_ge_10mT_p50_p95': (np.percentile(error[strong]/magnitude[strong], [50, 95]).tolist()
                                                             if strong.any() else None)}
    return report


def grid(data, half_size, spacing, max_points):
    half = np.broadcast_to(np.asarray(half_size, dtype=float), 3)
    bounds = np.asarray(data['bounds_m'], dtype=float)
    if np.any(np.maximum(-bounds[:3], bounds[3:]) >= half):
        raise ValueError('Map must enclose the whole coil array on every axis')
    sizes, steps = zip(*(grid_shape(h, spacing) for h in half))
    if math.prod(sizes) > max_points:
        raise ValueError(f'{math.prod(sizes):,} nodes exceed --max-points={max_points:,}')
    return half, sizes, steps


def compute_planes(seg, half, sizes, steps, z_indices, processes, checkpoint=None, key=None):
    """B on the z planes z_indices (ascending), as len(z_indices) x ny x nx x 3.

    Work is split into rows of x, so progress shows within seconds. With a
    checkpoint folder every finished plane is saved there, and a run stopped
    with Ctrl+C resumes from the planes already done (only if `key`, the
    inputs that fix the values, is the same)."""
    axes = [-h+s*np.arange(n) for h, s, n in zip(half, steps, sizes)]
    planes = {}
    if checkpoint:
        checkpoint.mkdir(parents=True, exist_ok=True)
        stamp = checkpoint/'key.json'
        if stamp.is_file() and json.loads(stamp.read_text()) != key:
            raise ValueError(f'{checkpoint} holds planes of a different map; delete it or change the output')
        stamp.write_text(json.dumps(key))
        planes = {i: np.load(checkpoint/f'z{i:04d}.npy') for i in z_indices
                  if (checkpoint/f'z{i:04d}.npy').is_file()}
    todo = [i for i in z_indices if i not in planes]
    print(f'[campo] {len(z_indices)*sizes[0]*sizes[1]:,} nodos ({sizes[0]}x{sizes[1]}x{len(z_indices)} '
          f'de {sizes[2]} planos z), {len(seg.length):,} segmentos, {processes} procesos'
          + (f'; se retoman {len(planes)} planos ya calculados' if planes else ''), file=sys.stderr, flush=True)
    tasks = [(axes[0], y, axes[2][i]) for i in todo for y in axes[1]]
    start = last = time.monotonic()
    rows = []
    with mp.Pool(processes, initializer=_init, initargs=(seg,)) as pool:
        for k, row in enumerate(pool.imap(_row, tasks), 1):
            rows.append(row)
            if len(rows) == sizes[1]:  # a whole plane is done
                i = todo[(k-1)//sizes[1]]
                planes[i] = np.stack(rows)
                rows = []
                if checkpoint:
                    np.save(checkpoint/f'z{i:04d}.npy', planes[i])
            now = time.monotonic()
            if now-last >= 5 or k == len(tasks):
                last = now
                print(f'\r[campo] {100*k/len(tasks):.1f}% ({k:,}/{len(tasks):,} filas), {(now-start)/60:.1f} min, '
                      f'faltan ~{(now-start)*(len(tasks)/k-1)/60:.1f} min ', end='', file=sys.stderr, flush=True)
    print(file=sys.stderr)
    return np.stack([planes[i] for i in z_indices]), time.monotonic()-start


def write_map(source, output, data, seg, values, half, steps, n_radial, n_axial, check_points, extra):
    sizes = values.shape[2::-1]
    print(f'[campo] escribiendo {output}', file=sys.stderr, flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    try:
        with temporary.open('w') as f:
            f.write(f'# Volumetric Biot-Savart, {len(data["coils"])} coils, {n_radial}x{n_axial} filaments; '
                    'm and T; not production\n')
            f.write(' '.join(map(str, sizes))+'\n'+' '.join(f'{-h}' for h in half)+'\n'
                    + ' '.join(map(str, steps))+'\n')
            np.savetxt(f, values.reshape(-1, 3), fmt='%.7e')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    edge = np.ones(values.shape[:3], dtype=bool)
    edge[1:-1, 1:-1, 1:-1] = False
    report = {'model': 'volumetric_biot_savart', 'production_validated': False,
              'array_report_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
              'map_sha256': digest(output), 'python': platform.python_version(),
              'numpy': np.__version__, 'platform': platform.platform(),
              'half_size_m': half.tolist(), 'spacing_m': list(steps), 'shape': list(sizes),
              'filaments_radial_axial': [n_radial, n_axial], 'filament_core_radius_m': seg.core,
              'segments_total': len(seg.length), 'currents_A': [c['current_A'] for c in data['coils']],
              'boundary_max_T': float(np.linalg.norm(values[edge], axis=1).max()), **extra}
    if check_points:
        print('[campo] comparando la interpolación con el cálculo directo', file=sys.stderr, flush=True)
        report['interpolation_check'] = interpolation_check(values, -half, np.array(steps), seg, check_points)
    output.with_suffix('.field-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


def part_meta(source, half, steps, sizes, n_radial, n_axial):
    """What every part of one map must share."""
    return {'array_report_sha256': digest(source), 'generator_sha256': digest(Path(__file__)),
            'half_size_m': half.tolist(), 'spacing_m': list(steps), 'shape': list(sizes),
            'filaments_radial_axial': [n_radial, n_axial]}


def generate(source, output, half_size, spacing, n_radial, n_axial, processes, max_points, check_points,
             part=None):
    """Whole map (.map), or part K of N of its z planes (.npz) for merge()."""
    data = json.loads(source.read_text())
    half, sizes, steps = grid(data, half_size, spacing, max_points)
    seg = Segments(data, n_radial, n_axial)
    # What fixes the values of every plane: a checkpoint is only reused if it matches.
    key = {'array_report_sha256': digest(source), 'half_size_m': half.tolist(), 'spacing_m': list(steps),
           'filaments_radial_axial': [n_radial, n_axial]}
    if part is None:
        if output.suffix != '.map' or output.resolve() == source.resolve():
            raise ValueError('Use a distinct .map output')
        checkpoint = output.with_name(output.name+'.planos')
        values, elapsed = compute_planes(seg, half, sizes, steps, list(range(sizes[2])), processes,
                                         checkpoint, key)
        write_map(source, output, data, seg, values, half, steps, n_radial, n_axial, check_points,
                  {'processes': processes, 'compute_seconds': elapsed})
        shutil.rmtree(checkpoint)
        return
    k, n = part
    if not 1 <= k <= n or output.suffix != '.npz':
        raise ValueError('--part K N needs 1 <= K <= N and a .npz output')
    z_indices = np.array_split(np.arange(sizes[2]), n)[k-1].tolist()
    checkpoint = output.with_name(output.name+'.planos')
    values, elapsed = compute_planes(seg, half, sizes, steps, z_indices, processes, checkpoint, key)
    meta = {**part_meta(source, half, steps, sizes, n_radial, n_axial), 'part': [k, n],
            'z_indices': [z_indices[0], z_indices[-1]], 'processes': processes, 'compute_seconds': elapsed,
            'platform': platform.platform()}
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez(output, values=values, meta=np.array(json.dumps(meta)))
    shutil.rmtree(checkpoint)
    print(f'[campo] parte {k}/{n} (planos z {z_indices[0]}-{z_indices[-1]}) en {output}', file=sys.stderr)


def merge(source, output, part_files, check_points):
    """Join the parts of one map, checking they are the same map and cover every z plane once."""
    if output.suffix != '.map':
        raise ValueError('Use a .map output')
    parts = []
    for path in part_files:
        with np.load(path) as f:
            parts.append((json.loads(str(f['meta'])), f['values']))
    parts.sort(key=lambda p: p[0]['z_indices'][0])
    first = parts[0][0]
    shared = ('array_report_sha256', 'generator_sha256', 'half_size_m', 'spacing_m', 'shape',
              'filaments_radial_axial')
    for meta, _ in parts:
        if any(meta[key] != first[key] for key in shared):
            raise ValueError('Parts come from different maps (input, code version, grid or filaments)')
    if first['array_report_sha256'] != digest(source):
        raise ValueError('array_report differs from the one the parts were computed with')
    expected, covered = 0, []
    for meta, _ in parts:
        lo, hi = meta['z_indices']
        if lo != expected:
            raise ValueError(f'z planes {expected}..{lo-1} missing or duplicated; check the parts')
        expected = hi+1
        covered.append(meta['part'])
    if expected != first['shape'][2]:
        raise ValueError(f'z planes {expected}..{first["shape"][2]-1} missing')
    data = json.loads(source.read_text())
    n_radial, n_axial = first['filaments_radial_axial']
    seg = Segments(data, n_radial, n_axial)
    values = np.concatenate([v for _, v in parts])
    extra = {'parts': [{key: meta[key] for key in ('part', 'z_indices', 'processes', 'compute_seconds', 'platform')}
                       for meta, _ in parts],
             'compute_seconds': sum(meta['compute_seconds'] for meta, _ in parts)}
    write_map(source, output, data, seg, values, np.array(first['half_size_m']), first['spacing_m'],
              n_radial, n_axial, check_points, extra)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('array_report', type=Path, help='array_current_paths.json from generate_ellipse_array.py')
    p.add_argument('output', type=Path, help='.map (whole map or merge) or .npz (--part)')
    p.add_argument('--half-size', type=float, nargs='+', help='metres: one value, or x y z')
    p.add_argument('--spacing', type=float, help='maximum grid step in metres')
    p.add_argument('--filaments', type=int, nargs=2, metavar=('RADIAL', 'AXIAL'))
    p.add_argument('--part', type=int, nargs=2, metavar=('K', 'N'),
                   help='compute only part K of N of the z planes (one per PC), into a .npz')
    p.add_argument('--merge', type=Path, nargs='+', metavar='PART_NPZ',
                   help='join the .npz parts into the .map output instead of computing')
    p.add_argument('--processes', type=int, default=os.cpu_count())
    p.add_argument('--max-points', type=int, default=20000000,
                   help='guard against accidental huge maps (±30 m at 0.25 m is 14 M nodes, ~630 MB)')
    p.add_argument('--check-points', type=int, default=0,
                   help='random points per region where the trilinear map is compared with direct evaluation')
    a = p.parse_args()
    if a.merge:
        merge(a.array_report, a.output, a.merge, a.check_points)
    else:
        if a.half_size is None or a.spacing is None or a.filaments is None:
            p.error('--half-size, --spacing and --filaments are required unless --merge is given')
        if len(a.half_size) not in (1, 3):
            p.error('--half-size takes one value or three (x y z)')
        generate(a.array_report, a.output, a.half_size, a.spacing, *a.filaments, a.processes,
                 a.max_points, a.check_points, a.part)
