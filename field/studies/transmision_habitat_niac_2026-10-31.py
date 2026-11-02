"""Transmisión magnética al hábitat con la disposición de NIAC (2026-10-31).
Se hizo para elegir las energías de P1 paso 3 (plan_piloto.md, «las más
sensibles al campo, cerca del corte del escudo»). No es un piloto.

Traza hacia atrás protones (carga invertida) desde un punto del hábitat, en
direcciones isótropas, en el campo Biot-Savart volumétrico del arreglo (6 × 3
filamentos, el del mapa de producción). Por el teorema de Liouville, en un
campo magnético estático y en vacío, un flujo isótropo llega al punto con la
intensidad del espacio libre en toda dirección cuya traza hacia atrás escapa
al infinito, y con cero en las que quedan atrapadas. La fracción que escapa
es la transmisión magnética T: el campo solo reduce el flujo si T < 1.
Escapar es llegar a 40 m (más allá, la cola desvía menos de 0.03 rad a
0.37 GV); quedar atrapada, no llegar en 300 m de recorrido.

Además cuenta qué fracción de las trazas cruza el bobinado de alguna bobina
(material de 120–250 g/cm²), con y sin campo, con las mismas direcciones
de partida en todas las filas: es la parte del efecto del
campo sobre la dosis que pasa por el material. La prueba del bobinado es
aproximada (distancia a la elipse a primer orden) y no incluye el casco.

Compara con un toroide ideal: las mismas 8 bobinas con todas las normales
azimutales (la bobina 0 rotada de a 45°), para separar el efecto de los
sentidos de corriente supuestos en D9 del de la geometría del anillo.

Uso, desde field/ (unos 7 min con 8 hilos):
    .venv/bin/python studies/transmision_habitat_niac_2026-10-31.py > studies/transmision_habitat_niac_2026-10-31.txt
"""
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

FIELD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FIELD))
from compute_field_volumetric import Segments, field  # noqa: E402
from preselect_source_radius import K_GV, wilson  # noqa: E402

REPORT = FIELD/'production'/'crewhat_niac_array_current_paths.json'
POINTS = {'x=0': (0., 0., 0.), 'x=4 m': (4., 0., 0.)}  # x=4 m mira a la bobina 0 (φ = 0)
ENERGIES_MEV = [20, 70, 150, 300, 600, 1000, 2000]
N = 300
R_ESCAPE, MAX_LENGTH, MAX_TURN = 40.0, 300.0, 0.2  # m, m, rad por paso


def rigidity_gv(kinetic_mev, mass_mev=938.272):
    return np.sqrt(kinetic_mev**2+2*kinetic_mev*mass_mev)/1000


def toroid(report):
    """Las 8 bobinas como la 0 (normal azimutal) rotada de a 45°."""
    out = copy.deepcopy(report)
    p0 = np.array(report['coils'][0]['path_m'])
    for k, coil in enumerate(out['coils']):
        a = 2*np.pi*k/len(out['coils'])
        rot = np.array([[np.cos(a), -np.sin(a), 0.], [np.sin(a), np.cos(a), 0.], [0., 0., 1.]])
        coil['path_m'] = (p0@rot.T).tolist()
    return out


class Packs:
    """¿Está el punto dentro del bobinado? Marco local de cada bobina desde su trayectoria."""

    def __init__(self, report):
        t = report['config']['coil_template']
        self.half_radial, self.half_axial = t['winding_pack_radial_m']/2, t['winding_pack_axial_m']/2
        self.a, self.b = t['semi_major_m'], t['semi_minor_m']
        self.frames = []
        for coil in report['coils']:
            p = np.array(coil['path_m'])
            center = p.mean(0)
            _, _, vt = np.linalg.svd(p-center)
            self.frames.append((center, vt[0], vt[1], vt[2]))  # eje mayor, eje menor, normal

    def inside(self, x):
        hit = np.zeros(len(x), bool)
        for center, major, minor, normal in self.frames:
            d = x-center
            v, h, w = d@major, d@minor, d@normal
            s = np.sqrt((h/self.b)**2+(v/self.a)**2)+1e-12
            grad = np.sqrt((h/self.b**2)**2+(v/self.a**2)**2)/s+1e-12
            hit |= (np.abs(w) <= self.half_axial) & (np.abs(s-1)/grad <= self.half_radial)
        return hit


def trace(seg, packs, point, rig, n, rng):
    """(escapa, cruza el bobinado) por traza; seg=None traza rectas (sin campo)."""
    u = rng.normal(size=(n, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    x = np.tile(point, (n, 1))
    k = -K_GV/rig
    escaped, crossed, length = np.zeros(n, bool), np.zeros(n, bool), np.zeros(n)
    B = field(x, seg) if seg else np.zeros_like(x)
    active = np.arange(n)
    while active.size:
        xa, ua, Ba = x[active], u[active], B[active]
        r = np.linalg.norm(xa, axis=1)
        ds = np.minimum(0.05+0.02*r, MAX_TURN/(abs(k)*np.linalg.norm(Ba, axis=1)+1e-12))
        near = (np.hypot(xa[:, 0], xa[:, 1]) > 5) & (np.hypot(xa[:, 0], xa[:, 1]) < 11) & (np.abs(xa[:, 2]) < 5)
        ds = np.clip(np.where(near, np.minimum(ds, 0.08), ds), 0.002, 1.0)  # no saltar el bobinado
        xh = xa+ua*(0.5*ds)[:, None]
        Bh = field(xh, seg) if seg else np.zeros_like(xh)
        # Rotación exacta de u alrededor de B en el paso, como en preselect_source_radius.backtrack.
        bn = np.linalg.norm(Bh, axis=1)
        axis = np.divide(Bh, bn[:, None], out=np.zeros_like(Bh), where=bn[:, None] > 0)
        c, s = np.cos(k*bn*ds)[:, None], np.sin(k*bn*ds)[:, None]
        un = ua*c-np.cross(axis, ua)*s+axis*np.einsum('ij,ij->i', axis, ua)[:, None]*(1-c)
        xn = xh+un*(0.5*ds)[:, None]
        x[active], u[active], B[active] = xn, un, Bh
        length[active] += ds
        crossed[active] |= packs.inside(xn)
        out = np.linalg.norm(xn, axis=1) >= R_ESCAPE
        escaped[active[out]] = True
        active = active[~out & (length[active] < MAX_LENGTH)]
    return escaped, crossed


def main():
    report = json.loads(REPORT.read_text())
    packs = Packs(report)
    rows = []
    t0 = time.time()
    print('arreglo | punto | T_p (MeV) | R (GV) | transmisión T [IC95] | cruza bobinado: sin campo, con campo', flush=True)
    for layout, data in (('NIAC', report), ('toroide', toroid(report))):
        seg = Segments(data, 6, 3)
        for name, point in POINTS.items():
            point = np.array(point)
            _, straight = trace(None, packs, point, 1.0, N, np.random.default_rng(1))
            for e in ENERGIES_MEV:
                esc, crossed = trace(seg, packs, point, rigidity_gv(e), N, np.random.default_rng(1))
                k = int(esc.sum())
                lo, hi = wilson(k, N)
                rows.append({'layout': layout, 'point': name, 'proton_MeV': e, 'rigidity_GV': float(rigidity_gv(e)),
                             'n': N, 'transmission': k/N, 'transmission_ci95': [lo, hi],
                             'crosses_pack_no_field': float(straight.mean()), 'crosses_pack': float(crossed.mean())})
                print(f'{layout:<7} | {name:<5} | {e:9} | {rigidity_gv(e):6.2f} | {k/N:.3f} [{lo:.3f}, {hi:.3f}] | '
                      f'{straight.mean():.3f}, {crossed.mean():.3f}', flush=True)
    print(f'{time.time()-t0:.0f} s')
    Path(__file__).with_suffix('.json').write_text(json.dumps(
        {'report': str(REPORT.relative_to(FIELD)), 'filaments': [6, 3], 'n': N, 'r_escape_m': R_ESCAPE,
         'max_length_m': MAX_LENGTH, 'rows': rows}, indent=1)+'\n')


if __name__ == '__main__':
    main()
