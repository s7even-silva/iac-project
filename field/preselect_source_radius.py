#!/usr/bin/env python3
"""P1, paso 1 (plan_piloto.md): preselección del radio de la esfera fuente
con el campo Biot-Savart regularizado del arreglo CREW HaT, sin dominio
finito (el campo se evalúa analíticamente en cualquier punto, no desde un
.map truncado).

La esfera fuente lanza primarios con ley coseno sobre una esfera de radio R
e ignora lo que el campo hizo con ellos fuera de R. Por el teorema de
Liouville, en un campo magnético estático la intensidad de un flujo isótropo
se conserva a lo largo de cada trayectoria: en un punto P de la esfera, la
intensidad entrante en la dirección d es la del espacio libre si la
trayectoria que llega a (P, d), trazada hacia atrás, viene del infinito, y no
lo es si (a) la traza hacia atrás vuelve a cruzar la esfera (la partícula ya
estaba dentro antes: el lanzamiento en P la cuenta dos veces) o (b) queda
atrapada. La fracción de pares (P, d) en (a) o (b), pesada con ley coseno,
es el error de fuente de ese radio para esa rigidez.

Dos métricas por radio R:

A. Cola ∫ u×B dl a lo largo de la recta hacia atrás (la métrica del plan,
   aproximación de recta): ángulo de desviación θ = 0.2998·|∫u×B dl| / R_GV.
B. Fracción mala f(R, rigidez) trazando hacia atrás protones (carga +1)
   en el campo, con IC95 de Wilson.

No aprueba ni descarta radios por sí mismo: el umbral es D3/P1. Biot-Savart
no es el campo de producción (Elmer); esto solo preselecciona qué dominios
vale la pena resolver con Elmer (P1, paso 2).
"""
import argparse
import json
import math
import multiprocessing as mp
import platform
import time
from pathlib import Path

import numpy as np

from compute_field import field_at
from provenance import digest

K_GV = 0.299792458  # GV por (T·m): θ = K·∫B⊥dl / R


class Coils:
    def __init__(self, report_path):
        data = json.loads(Path(report_path).read_text())
        self.core = data['config']['coil_template']['field_regularization_radius_m']
        starts, dirs, lens, cur = [], [], [], []
        self.paths, self.currents = [], []
        for coil in data['coils']:
            path = np.asarray(coil['path_m'], dtype=float)
            self.paths.append(path)
            self.currents.append(coil['current_A'])
            delta = path[1:]-path[:-1]
            length = np.linalg.norm(delta, axis=1)
            starts.append(path[:-1])
            dirs.append(delta/length[:, None])
            lens.append(length)
            cur.append(np.full(len(length), coil['current_A']))
        self.start = np.vstack(starts)
        self.dir = np.vstack(dirs)
        self.len = np.concatenate(lens)
        self.cur = np.concatenate(cur)
        self.bounds = data['bounds_m']
        pts = np.vstack(self.paths)
        half_diag = data['config']['coil_template']['winding_pack_side_m']*math.sqrt(2)/2
        self.r_material_max = float(np.linalg.norm(pts, axis=1).max()+half_diag)

    def field(self, points, chunk=96):
        """Misma fórmula que compute_field.field_at, vectorizada por segmentos."""
        points = np.asarray(points, dtype=float)
        out = np.zeros_like(points)
        a2 = self.core**2
        for i in range(0, len(self.len), chunk):
            s0, u = self.start[i:i+chunk], self.dir[i:i+chunk]
            L, I = self.len[i:i+chunk], self.cur[i:i+chunk]
            r = points[:, None, :]-s0[None, :, :]
            s = np.einsum('nsk,sk->ns', r, u)
            rho = r-s[..., None]*u[None, :, :]
            q = np.einsum('nsk,nsk->ns', rho, rho)+a2
            f = (s/np.sqrt(q+s*s)-(s-L)/np.sqrt(q+(s-L)**2))/q*I
            out += np.einsum('ns,nsk->nk', f, np.cross(u[None, :, :], rho))
        return out*1e-7


def sample_entries(radius, n, rng):
    """P uniforme en la esfera, d entrante con ley coseno respecto de -n."""
    normal = rng.normal(size=(n, 3))
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    cos_t = np.sqrt(rng.random(n))
    phi = 2*np.pi*rng.random(n)
    sin_t = np.sqrt(1-cos_t**2)
    helper = np.where(np.abs(normal[:, :1]) < 0.9, [[1., 0., 0.]], [[0., 1., 0.]])
    e1 = np.cross(normal, helper)
    e1 /= np.linalg.norm(e1, axis=1)[:, None]
    e2 = np.cross(normal, e1)
    d = -cos_t[:, None]*normal+sin_t[:, None]*(np.cos(phi)[:, None]*e1+np.sin(phi)[:, None]*e2)
    return radius*normal, d


def straight_tail(coils, radius, n, r_far, seed):
    rng = np.random.default_rng(seed)
    P, d = sample_entries(radius, n, rng)
    # Recta hacia atrás Q(t) = P - t d; t de 0 a la distancia en que |Q| = r_far.
    out = -d
    b = np.einsum('ij,ij->i', P, out)
    t_far = -b+np.sqrt(b*b-(radius**2-r_far**2))
    nodes = 200
    g = np.geomspace(1e-3, 1.0, nodes)
    g = np.concatenate(([0.0], g))
    net = np.zeros((n, 3))
    absint = np.zeros(n)
    prev = None
    for k, frac in enumerate(g):
        Q = P+out*(t_far*frac)[:, None]
        cross = np.cross(out, coils.field(Q))
        if prev is not None:
            dt = t_far*(frac-g[k-1])
            net += 0.5*(cross+prev)*dt[:, None]
            absint += 0.5*(np.linalg.norm(cross, axis=1)+np.linalg.norm(prev, axis=1))*dt
        prev = cross
    return np.linalg.norm(net, axis=1), absint


def backtrack(coils, radius, rigidity_gv, n, r_escape, seed, max_steps=6000):
    rng = np.random.default_rng(seed)
    x, d = sample_entries(radius, n, rng)
    u = -d                      # velocidad hacia atrás
    k = -K_GV/rigidity_gv       # carga invertida al trazar hacia atrás
    status = np.zeros(n, dtype=np.int8)  # 0 activo, 1 escapa, 2 reentra, 3 atrapado
    path_len = np.zeros(n)
    active = np.arange(n)
    for _ in range(max_steps):
        if active.size == 0:
            break
        xa, ua = x[active], u[active]
        r = np.linalg.norm(xa, axis=1)
        Bx = coils.field(xa)
        kb = np.abs(k)*np.linalg.norm(Bx, axis=1)
        ds = np.clip(np.minimum(0.02*r, 0.1/(kb+1e-12)), 0.002, 2.0)
        xh = xa+ua*(0.5*ds)[:, None]
        B = coils.field(xh)
        # Rotación exacta de u alrededor de B en el paso: du/ds = k u×B.
        bn = np.linalg.norm(B, axis=1)
        ang = k*bn*ds
        axis = np.divide(B, bn[:, None], out=np.zeros_like(B), where=bn[:, None] > 0)
        c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
        adot = np.einsum('ij,ij->i', axis, ua)[:, None]
        # Rodrigues con signo: u×B = |B| u×axis, que es -axis×u.
        un = ua*c-np.cross(axis, ua)*s+axis*adot*(1-c)
        xn = xh+un*(0.5*ds)[:, None]
        x[active], u[active] = xn, un
        path_len[active] += ds
        rn = np.linalg.norm(xn, axis=1)
        esc = rn >= r_escape
        back = rn < radius
        status[active[esc]] = 1
        status[active[back & ~esc]] = 2
        active = active[~(esc | back)]
    status[active] = 3
    return status, path_len


def wilson(k, n, z=1.959964):
    if n == 0:
        return (math.nan, math.nan)
    p = k/n
    den = 1+z*z/n
    c = (p+z*z/(2*n))/den
    h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (max(0.0, c-h), min(1.0, c+h))


def proton_kinetic_mev(rigidity_gv):
    m = 938.272
    p = rigidity_gv*1000.0
    return math.sqrt(p*p+m*m)-m


def _task(args):
    kind, report, radius, rig, n, r_far, seed = args
    coils = Coils(report)
    t0 = time.time()
    if kind == 'tail':
        net, absint = straight_tail(coils, radius, n, r_far, seed)
        return {'kind': kind, 'radius_m': radius, 'n': n, 'seconds': time.time()-t0,
                'net_Tm_quantiles': {q: float(np.quantile(net, q)) for q in (0.5, 0.9, 0.99, 1.0)},
                'abs_Tm_quantiles': {q: float(np.quantile(absint, q)) for q in (0.5, 0.9, 0.99, 1.0)},
                'net_Tm_mean': float(net.mean())}
    status, length = backtrack(coils, radius, rig, n, r_far, seed)
    counts = {name: int(np.sum(status == v)) for v, name in ((1, 'escape'), (2, 'reenter'), (3, 'trapped'))}
    bad = counts['reenter']+counts['trapped']
    return {'kind': kind, 'radius_m': radius, 'rigidity_GV': rig,
            'proton_T_MeV': proton_kinetic_mev(rig), 'n': n, 'counts': counts,
            'bad_fraction': bad/n, 'bad_ci95': wilson(bad, n),
            'median_path_m': float(np.median(length)), 'seconds': time.time()-t0}


def self_checks(coils, map_path):
    rng = np.random.default_rng(1)
    pts = rng.uniform(-12, 12, size=(200, 3))
    ref = sum(field_at(pts, p, c, coils.core) for p, c in zip(coils.paths, coils.currents))
    rel = float(np.max(np.linalg.norm(coils.field(pts)-ref, axis=1)/np.maximum(np.linalg.norm(ref, axis=1), 1e-12)))
    result = {'vectorized_vs_field_at_max_rel': rel}
    if map_path:
        with open(map_path) as f:
            lines = [ln for ln in f if not ln.startswith('#')]
        nx, ny, nz = map(int, lines[0].split())
        x0 = np.array(lines[1].split(), dtype=float)
        dx = np.array(lines[2].split(), dtype=float)
        idx = rng.integers(0, nx*ny*nz, size=300)
        ijk = np.column_stack((idx % nx, idx//nx % ny, idx//(nx*ny)))
        p = x0+dx*ijk
        vals = np.array([lines[3+i].split() for i in idx], dtype=float)
        got = coils.field(p)
        mask = np.linalg.norm(vals, axis=1) > 1e-3
        result['map_check_points'] = int(mask.sum())
        result['map_max_rel'] = float(np.max(np.linalg.norm(got[mask]-vals[mask], axis=1)/np.linalg.norm(vals[mask], axis=1)))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('array_report', type=Path, help='array_current_paths.json de generate_ellipse_array.py')
    p.add_argument('output', type=Path, help='JSON de resultados')
    p.add_argument('--radii', type=float, nargs='+', required=True)
    p.add_argument('--rigidities-gv', type=float, nargs='+', required=True)
    p.add_argument('--n-tail', type=int, default=2000)
    p.add_argument('--n-track', type=int, default=2000)
    p.add_argument('--r-escape', type=float, default=100.0)
    p.add_argument('--seed', type=int, default=20261001)
    p.add_argument('--processes', type=int, default=4)
    p.add_argument('--check-map', type=Path, help='.map Biot-Savart de producción para verificar las trayectorias de corriente')
    a = p.parse_args()

    coils = Coils(a.array_report)
    checks = self_checks(coils, a.check_map)
    print(json.dumps(checks), flush=True)
    tasks = []
    for i, R in enumerate(a.radii):
        tasks.append(('tail', str(a.array_report), R, None, a.n_tail, a.r_escape, a.seed+i))
        for j, rig in enumerate(a.rigidities_gv):
            tasks.append(('track', str(a.array_report), R, rig, a.n_track, a.r_escape, a.seed+1000*(i+1)+j))
    results = []
    with mp.Pool(a.processes) as pool:
        for res in pool.imap_unordered(_task, tasks):
            print(json.dumps(res), flush=True)
            results.append(res)
    report = {'generator_sha256': digest(Path(__file__)), 'array_report_sha256': digest(a.array_report),
              'r_material_max_m': coils.r_material_max, 'bounds_m': coils.bounds,
              'self_checks': checks, 'args': {k: str(v) for k, v in vars(a).items()},
              'python': platform.python_version(), 'numpy': np.__version__, 'results': results}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
