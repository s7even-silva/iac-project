"""Chequeo exploratorio (2026-10-31, no es un piloto): cola del campo
Biot-Savart fuera de la esfera fuente para la disposición de NIAC y para K=1,
con radios mayores que los de la preselección del 2026-10-01.

Para cada radio R: ∫ u×B dl a lo largo de la recta hacia atrás desde la esfera
(la métrica A de preselect_source_radius.py; desviación θ = 0.2998·∫/R_GV) y
|B| sobre la esfera. Sirve para estimar qué radios hay que trazar en P1 paso 1
(métrica B, reentradas), calibrando contra K=1, cuya fracción de reentradas ya
se midió (plan_piloto.md). No fija ningún radio.

Uso, desde field/ (antes generar las trayectorias de corriente):
    .venv/bin/python generate_ellipse_array.py production/crewhat_corc_array_config.json generated/crewhat_k1_array
    .venv/bin/python generate_ellipse_array.py examples/crewhat_niac_array.json generated/crewhat_niac_array
    .venv/bin/python studies/cola_campo_niac_k1_2026-10-31.py > studies/cola_campo_niac_k1_2026-10-31.txt
"""
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preselect_source_radius import Coils, sample_entries, straight_tail  # noqa: E402

REPORTS = {'K1': 'generated/crewhat_k1_array/array_current_paths.json',
           'NIAC': 'generated/crewhat_niac_array/array_current_paths.json'}
RADII = [12, 14, 16, 18, 20, 22, 24, 28, 32]
N = 2000


def task(args):
    name, R = args
    coils = Coils(REPORTS[name])
    net, _ = straight_tail(coils, R, N, 100.0, 20261031+R)
    P, _ = sample_entries(R, N, np.random.default_rng(R))
    B = np.linalg.norm(coils.field(P), axis=1)*1e3
    return name, R, np.median(net), np.quantile(net, .9), np.quantile(net, .99), B.mean(), np.quantile(B, .9)


if __name__ == '__main__':
    print('disposición R(m) | ∫u×B dl (T·m): mediana p90 p99 | |B| en la esfera (mT): media p90', flush=True)
    with mp.Pool(8) as pool:
        for row in pool.imap(task, [(n, R) for n in REPORTS for R in RADII]):
            print('%-4s %2d | %.3f %.3f %.3f | %.1f %.1f' % row, flush=True)
