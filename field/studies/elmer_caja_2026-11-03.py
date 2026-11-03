"""¿Cuánto de la diferencia Elmer − Biot-Savart (una bobina, P1 paso 2) es la
caja finita de Elmer? Predicción sin parámetros ajustables (2026-11-03,
análisis hecho después de ver los datos de los cuatro niveles).

Elmer impone AV = 0 en la caja (`case.sif`), es decir B·n = 0: el flujo que en
el espacio libre cierra afuera tiene que volver por dentro. La solución exacta
de ese problema es B_caja = B_BS − ∇φ, con φ armónica en la caja y
∂φ/∂n = B_BS·n en sus seis caras (la diferencia es irrotacional, solenoidal
y sin flujo normal, así que es única). φ se calcula por series de cosenos en
cada cara, con B_BS de la misma bobina (6 × 3 filamentos) en una grilla de
0.2 m sobre las caras. Si Elmer − (BS − ∇φ) queda en el error de malla, lo
que separaba a Elmer de Biot-Savart era la caja, no Biot-Savart.

En el hábitat compara además la diferencia media Elmer − BS con la que
predice la caja, y da la escala Elmer/(BS en la caja) − 1, que mediría un
error de corriente entre los dos códigos.

Uso, desde field/ (cada carpeta es un nivel de elmer_una_bobina.sh, con
validacion.json y domain.mesh-manifest.json; ~1 min en la laptop):
    .venv/bin/python studies/elmer_caja_2026-11-03.py NIVEL1 NIVEL2 ... > studies/elmer_caja_2026-11-03.txt
"""
import json
import sys
from pathlib import Path

import numpy as np

FIELD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FIELD))
from compute_field_volumetric import Segments, field  # noqa: E402
from provenance import digest  # noqa: E402

REPORT = FIELD/'production'/'crewhat_niac_array_current_paths.json'
FACE_STEP, MAX_MODES = 0.2, 80  # m, modos por lado de cada cara
GROUPS = ('near_coil', 'habitat', 'radial')


def box_gradient(seg, lo, hi, points):
    """∇φ en los puntos: φ armónica en la caja [lo, hi] con ∂φ/∂x_i = B_i(BS) en las caras normales a i."""
    grad = np.zeros_like(points)
    for i in range(3):
        j, l = [a for a in range(3) if a != i]
        L = hi-lo
        nj, nl = (int(np.ceil(L[a]/FACE_STEP)) for a in (j, l))
        uj, ul = ((np.arange(n)+0.5)/n for n in (nj, nl))
        data = []
        for side in (lo[i], hi[i]):
            face = np.zeros((nj, nl, 3))
            face[..., i] = side
            face[..., j] = (lo[j]+uj*L[j])[:, None]
            face[..., l] = (lo[l]+ul*L[l])[None, :]
            data.append(field(face.reshape(-1, 3), seg)[:, i].reshape(nj, nl))
        mj, ml = np.arange(min(nj, MAX_MODES)), np.arange(min(nl, MAX_MODES))
        cj, cl = np.cos(np.pi*np.outer(mj, uj)), np.cos(np.pi*np.outer(ml, ul))
        weight = np.outer(np.where(mj == 0, 1., 2.), np.where(ml == 0, 1., 2.))/(nj*nl)
        c0, c1 = (weight*(cj@d@cl.T) for d in data)  # coeficientes de coseno en x_i = lo y x_i = hi
        xi = points[:, i]-lo[i]
        # Modo (0, 0): cuadrático en x_i; los tres suman laplaciano 0 porque el flujo neto de B es 0.
        grad[:, i] += (c1[0, 0]-c0[0, 0])*xi/L[i]+c0[0, 0]
        kj, kl = np.pi*mj/L[j], np.pi*ml/L[l]
        k = np.hypot(kj[:, None], kl[None, :])
        k[0, 0] = 1.
        a, b = np.pi*(points[:, j]-lo[j])/L[j], np.pi*(points[:, l]-lo[l])/L[l]
        cos_j, sin_j = np.cos(np.outer(a, mj)), np.sin(np.outer(a, mj))
        cos_l, sin_l = np.cos(np.outer(b, ml)), np.sin(np.outer(b, ml))
        # sinh y cosh relativos a sinh(k L_i), en forma estable: e^{k(ξ−L)}(1 ∓ e^{−2kξ})/(1 − e^{−2kL}).
        den = 1-np.exp(-2*k*L[i])
        e1 = np.exp(k[None]*(xi[:, None, None]-L[i]))
        e0 = np.exp(-k[None]*xi[:, None, None])
        s1, ch1 = e1*(1-np.exp(-2*k[None]*xi[:, None, None]))/den, e1*(1+np.exp(-2*k[None]*xi[:, None, None]))/den
        s0, ch0 = e0*(1-np.exp(-2*k[None]*(L[i]-xi[:, None, None])))/den, e0*(1+np.exp(-2*k[None]*(L[i]-xi[:, None, None])))/den
        c0m, c1m = c0.copy(), c1.copy()
        c0m[0, 0] = c1m[0, 0] = 0.
        # φ = cos cos [c1 cosh(kξ) − c0 cosh(k(L−ξ))]/(k sinh kL)
        phi_k = (c1m*ch1-c0m*ch0)/k
        grad[:, i] += np.einsum('pm,pn,pmn->p', cos_j, cos_l, c1m*s1+c0m*s0)
        grad[:, j] += np.einsum('pm,pn,pmn->p', -sin_j*kj, cos_l, phi_k)
        grad[:, l] += np.einsum('pm,pn,pmn->p', cos_j, -sin_l*kl, phi_k)
    return grad


def relative(value, reference):
    r = np.linalg.norm(value-reference, axis=1)/np.linalg.norm(reference, axis=1)
    return np.median(r), np.percentile(r, 95)


def main():
    data = json.loads(REPORT.read_text())
    data['coils'] = data['coils'][:1]
    seg = Segments(data, 6, 3)
    rows = {}
    print('nivel | grupo | sondas | Elmer frente a BS: mediana / p95 | Elmer frente a BS − ∇φ (caja): mediana / p95')
    for level in map(Path, sys.argv[1:]):
        run = json.loads((level/'validacion.json').read_text())
        assert run['array_report_sha256'] == digest(REPORT), level
        lo, hi = map(np.array, json.loads((level/'domain.mesh-manifest.json').read_text())['bounds_m'])
        points = np.concatenate([run['probes'][g] for g in GROUPS])
        sizes = [len(run['probes'][g]) for g in GROUPS]
        ref = np.array(run['fields_T']['bs_24x12'])
        elmer = np.array(next(v for k, v in run['fields_T'].items() if k.startswith('elmer')), float)
        # Autocontrol: a 1 mm de cada cara, lejos de los bordes, B_BS − ∇φ no tiene flujo normal.
        faces, normals = [], []
        for i, sign in ((i, s) for i in range(3) for s in (-1, 1)):
            p = lo+(hi-lo)*np.random.default_rng(i).uniform(0.2, 0.8, (10, 3))
            p[:, i] = (hi if sign > 0 else lo)[i]-sign*1e-3
            faces.append(p)
            normals.append(np.tile(sign*np.eye(3)[i], (10, 1)))
        faces, normals = np.concatenate(faces), np.concatenate(normals)
        grad = box_gradient(seg, lo, hi, np.concatenate([points, faces]))
        flux = np.sum(field(faces, seg)*normals, axis=1)
        assert np.abs(flux-np.sum(grad[len(points):]*normals, axis=1)).max() < 0.01*np.abs(flux).max(), level
        boxed = ref-grad[:len(points)]
        rows[level.name] = {}
        for g, part in zip(GROUPS, np.split(np.arange(len(points)), np.cumsum(sizes)[:-1])):
            part = part[np.isfinite(elmer[part]).all(1)]
            raw, box = relative(elmer[part], ref[part]), relative(elmer[part], boxed[part])
            rows[level.name][g] = {'probes': len(part), 'elmer_vs_bs_p50_p95': raw, 'elmer_vs_bs_in_box_p50_p95': box}
            print(f'{level.name} | {g} | {len(part)} | {raw[0]:.1%} / {raw[1]:.1%} | {box[0]:.1%} / {box[1]:.1%}', flush=True)
            if g == 'habitat':
                fitted = (elmer[part]-ref[part]).mean(0)  # mejor campo uniforme, ajustado a Elmer
                predicted = (boxed[part]-ref[part]).mean(0)
                b = boxed[part]
                scale = np.sum((elmer[part]-b)*b)/np.sum(b*b)
                rows[level.name][g] |= {'uniform_fit_mT': (fitted*1e3).tolist(),
                                        'box_mean_predicted_mT': (predicted*1e3).tolist(), 'scale_vs_box': scale}
                print(f'    hábitat: diferencia media {np.round(fitted*1e3, 1)} mT, predicha por la caja '
                      f'{np.round(predicted*1e3, 1)} mT; escala Elmer/(BS en la caja) − 1 = {scale:+.2%}', flush=True)
    Path(__file__).with_suffix('.json').write_text(json.dumps(
        {'report_sha256': digest(REPORT), 'filaments': [6, 3], 'face_step_m': FACE_STEP, 'max_modes': MAX_MODES,
         'levels': rows}, indent=1)+'\n')


if __name__ == '__main__':
    main()
