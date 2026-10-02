#!/usr/bin/env python3
"""¿Sirve el SE de una sola corrida (scorer por evento) para no repetir
corridas? Prueba por lotes en casos difíciles.

Idea: los eventos de Geant4 son independientes entre sí. Una corrida grande
de N eventos, partida por event_id en K lotes disjuntos de M eventos, da K
«corridas» independientes de tamaño M sin pagar K inicializaciones. (La
independencia entre semillas distintas se comprobó aparte en
prueba_atajo_intrarun.py.) Para cada caso, categoría y M:

- rho = sqrt(media SE²) / SD(medias de los lotes), con IC95 por χ² (K-1).
- cobertura = fracción de lotes cuyo IC95 normal (media ± 1.96·SE) contiene
  la media del resto de la corrida (deja-uno-fuera).
- p_sub2 = fracción de lotes cuyo SE es menor que la mitad de la SD real
  (el fallo peligroso: un lote sin el evento raro grande se cree preciso).
- err_rel = SD real / media: precisión relativa que da una corrida de M.

Diseño fijado antes de correr: casos y M de abajo; lectura «sirve» si en un
caso/categoría con suficientes eventos con depósito rho es compatible con 1,
la cobertura no baja de ~0.90 y p_sub2 es pequeño. Los casos usan la
geometría de producción actual (casco 1.5 cm, bobinas, mapa Elmer, esfera
6.94 m), que no es la final; sirven para medir colas, no dosis.

Uso:
    python3 prueba_lotes.py run --out-dir DIR --case NOMBRE --events N [--threads 3]
    python3 prueba_lotes.py analyze --out-dir DIR
"""
import argparse
import csv
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
REPO = PROJECT.parent.parent
FIELD = REPO/"field"/"production"
BATCH_SIZES = [2500, 5000, 10000, 20000, 50000]

# nombre -> (especie, fase, energía [MeV o MeV/n], offset_x_m, geometría)
# "casco": nave reducida (radio 0.6 m, semilongitud 1.0 m, esfera ≈1.39 m) con
# el casco real de 1.5 cm de Al, sin bobinas ni campo: ~7% de los primarios
# llegan al fantoma, y conserva el corte del casco y sus secundarios.
# "prod": geometría de producción actual; solo ~0.1–1% llega al fantoma.
CASES = {
    "sep70_casco": ("SEP_p", "max", 70.0, 0.0, "casco"),
    "sep150_casco": ("SEP_p", "max", 150.0, 0.0, "casco"),
    "he1000_casco": ("GCR_He", "min", 1000.0, 0.0, "casco"),
    "h10000_casco": ("GCR_H", "min", 10000.0, 0.0, "casco"),
    "sep300_prod": ("SEP_p", "max", 300.0, 0.0, "prod"),
    # Réplica con otra semilla (agregada después de ver h10000_casco, que dio
    # rho < 1 en lotes contiguos): confirma o descarta ese resultado.
    "h10000_casco_rep": ("GCR_H", "min", 10000.0, 0.0, "casco"),
}
SEEDS = {name: 20261002_00+10*i for i, name in enumerate(CASES)}

GEOMETRY = {"casco": """\
/spacecraft/shipRadius 0.6 m
/spacecraft/shipHalfLength 1.0 m
/spacecraft/hullThickness 1.5 cm
""", "prod": f"""\
/spacecraft/shipRadius 4.5 m
/spacecraft/shipHalfLength 5.0 m
/spacecraft/worldHalfSize 14 m
/spacecraft/coilGeometry {FIELD/'crewhat_corc_array.gdml'}
/spacecraft/fieldMap {FIELD/'crewhat_elmer_fullscale.map'}
/spacecraft/fieldScale 1.0
"""}

MACRO = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full
{geometry}/spacecraft/phantomOffsetX {offset} m
/spacecraft/phantomOffsetY 0 m
/run/numberOfThreads {threads}
/run/initialize
/random/setSeeds {seed1} {seed2}
/run/printProgress {progress}
/gun/species {species}
/gun/phase {phase}
/gun/angularDistribution cosine
/gun/fixedEnergyMeV {energy}
/score/create/boxMesh PhantomMesh
/score/mesh/boxSize 271.399 135.6995 888. mm
/score/mesh/nBin 254 127 222
/score/mesh/translate/xyz {offset_mm} 0. 0. mm
/score/quantity/energyDeposit energyDeposit
/score/close
/eventStats/enable true
/eventStats/phantomSex male
/eventStats/phantomSection full
/eventStats/categoryFile {categories}
/eventStats/output EventStats.tsv
/eventStats/perEventFile EventCategories.tsv
/run/beamOn {events}
"""


def run(a):
    build = a.build_dir.resolve()
    work = a.out_dir/a.case
    work.mkdir(parents=True, exist_ok=True)
    categories = a.out_dir/"event_categories.txt"
    if not categories.is_file():
        subprocess.run([sys.executable, str(PROJECT/"scripts"/"write_event_categories.py"), str(categories),
                        "--icrp-data-dir", str(build/"ICRPdata")], check=True)
    for name in ("ICRPdata", "data"):
        if not (work/name).exists():
            (work/name).symlink_to(build/name)
    species, phase, energy, offset, geometry = CASES[a.case]
    seed1 = SEEDS[a.case]
    (work/"run.mac").write_text(MACRO.format(
        geometry=GEOMETRY[geometry], offset=offset, offset_mm=offset*1000, threads=a.threads,
        seed1=seed1, seed2=seed1+1, progress=max(a.events//10, 1), species=species, phase=phase,
        energy=energy, categories=categories, events=a.events))
    t0 = time.time()
    with open(work/"run.log", "w") as log:
        subprocess.run([str(build/"ICRP110phantoms"), "run.mac"], cwd=work, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    print(f"{a.case}: {a.events} eventos en {time.time()-t0:.0f} s", flush=True)


def chi2_quantile(p, df):
    z = statistics.NormalDist().inv_cdf(p)
    return df*(1-2/(9*df)+z*math.sqrt(2/(9*df)))**3


def batch_stats(values_by_event, n_total, m):
    """values_by_event: {event_id: valor} (solo no nulos). Lotes [kM, (k+1)M)."""
    k = n_total//m
    s1 = [0.0]*k
    s2 = [0.0]*k
    nz = [0]*k
    for eid, v in values_by_event.items():
        b = eid//m
        if b < k:
            s1[b] += v
            s2[b] += v*v
            nz[b] += 1
    means, ses = [], []
    for b in range(k):
        mean = s1[b]/m
        var = max((s2[b]-s1[b]**2/m)/(m-1), 0.0)
        means.append(mean)
        ses.append(math.sqrt(var/m))
    return means, ses, nz


def analyze(a):
    rows = []
    print(f"{'caso':<11} {'categoria':<17} {'M':>6} {'K':>4} {'dep/lote':>8} {'err_rel':>7} "
          f"{'rho':>5} {'IC95 rho':>12} {'cobert':>6} {'p_sub2':>6} {'max/S1':>6}")
    for case_dir in sorted(p for p in a.out_dir.iterdir() if (p/"EventCategories.tsv").is_file()):
        lines = [l for l in open(case_dir/"EventCategories.tsv")]
        n_total = int(lines[0].split()[2])
        reader = csv.DictReader(lines[1:], delimiter="\t")
        per = list(reader)
        cats = [c for c in reader.fieldnames if c != "event_id"]
        for cat in cats:
            values = {int(r["event_id"]): float(r[cat]) for r in per if float(r[cat]) != 0.0}
            if len(values) < 20:
                continue
            total = sum(values.values())
            max_frac = max(values.values())/total
            for m in BATCH_SIZES:
                k = n_total//m
                if k < 8:
                    continue
                means, ses, nz = batch_stats(values, n_total, m)
                sd = statistics.stdev(means)
                grand = statistics.fmean(means)
                if sd == 0 or grand == 0:
                    continue
                rho = math.sqrt(statistics.fmean(s*s for s in ses))/sd
                lo = rho*math.sqrt(chi2_quantile(0.025, k-1)/(k-1))
                hi = rho*math.sqrt(chi2_quantile(0.975, k-1)/(k-1))
                cover = 0
                for b in range(k):
                    loo = (grand*k-means[b])/(k-1)
                    cover += abs(means[b]-loo) <= 1.96*ses[b]
                cover /= k
                p_sub2 = sum(s < 0.5*sd for s in ses)/k
                dep = statistics.fmean(nz)
                print(f"{case_dir.name:<11} {cat:<17} {m:>6} {k:>4} {dep:8.1f} {sd/grand:7.3f} "
                      f"{rho:5.2f} [{lo:4.2f},{hi:4.2f}] {cover:6.2f} {p_sub2:6.2f} {max_frac:6.3f}")
                rows.append({"caso": case_dir.name, "categoria": cat, "M": m, "K": k,
                             "eventos_con_deposito_por_lote": dep, "err_rel_real": sd/grand,
                             "rho": rho, "rho_ic95_lo": lo, "rho_ic95_hi": hi, "cobertura_ic95": cover,
                             "p_se_menor_mitad": p_sub2, "max_evento_sobre_S1_total": max_frac,
                             "N_total": n_total})
    out = a.out_dir/"resumen_lotes.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {out}")


def vov_of(s1, s2, s3, s4, n):
    """Varianza relativa de la varianza (MCNP; Pederson, Forster y Booth)."""
    den = (s2-s1*s1/n)**2
    if den <= 0:
        return math.inf
    return (s4-4*s1*s3/n+6*s1*s1*s2/n**2-3*s1**4/n**3)/den-1/n


def diagnose(a):
    """¿El diagnóstico que calcula una corrida por sí sola predice si su IC95
    es confiable? Para cada lote (= corrida de M eventos) calcula la VOV y
    n_nonzero, y agrupa la cobertura y la fracción de SE < SD/2 por estrato.
    El umbral VOV < 0.1 es el de MCNP, fijado de antemano (no ajustado aquí);
    los estratos de n_nonzero son descriptivos.

    La cobertura se mide contra la media del resto de lotes (deja-uno-fuera),
    así que aun con un SE perfecto su valor esperado es
    2Φ(1.96/sqrt(1+1/(K-1)))-1 (0.933 con K=8, 0.948 con K=80); se reporta
    como `cobertura_esperada_con_SE_exacto`."""
    norm = statistics.NormalDist()
    groups = {}
    for case_dir in sorted(p for p in a.out_dir.iterdir() if (p/"EventCategories.tsv").is_file()):
        lines = open(case_dir/"EventCategories.tsv").readlines()
        n_total = int(lines[0].split()[2])
        per = list(csv.DictReader(lines[1:], delimiter="\t"))
        cats = [c for c in per[0] if c != "event_id"]
        for cat in cats:
            values = {int(r["event_id"]): float(r[cat]) for r in per if float(r[cat]) != 0.0}
            if len(values) < 20:
                continue
            for m in BATCH_SIZES:
                k = n_total//m
                if k < 8:
                    continue
                acc = [[0.0, 0.0, 0.0, 0.0, 0] for _ in range(k)]
                for eid, v in values.items():
                    b = eid//m
                    if b < k:
                        x = acc[b]
                        x[0] += v; x[1] += v*v; x[2] += v**3; x[3] += v**4; x[4] += 1
                means = [x[0]/m for x in acc]
                sd = statistics.stdev(means)
                grand = statistics.fmean(means)
                expected = 2*norm.cdf(1.96/math.sqrt(1+1/(k-1)))-1
                for b, (s1, s2, s3, s4, nz) in enumerate(acc):
                    se = math.sqrt(max((s2-s1*s1/m)/(m-1), 0.0)/m)
                    loo = (grand*k-means[b])/(k-1)
                    covered = abs(means[b]-loo) <= 1.96*se
                    vov = vov_of(s1, s2, s3, s4, m) if nz >= 2 else math.inf
                    vb = "VOV<0.1" if vov < 0.1 else "VOV>=0.1"
                    nb = "nz>=200" if nz >= 200 else ("nz 50-199" if nz >= 50 else "nz<50")
                    for key in ((vb, "todos"), ("todos", nb), (vb, nb)):
                        g = groups.setdefault(key, [0, 0, 0, 0.0])
                        g[0] += 1; g[1] += covered; g[2] += se < 0.5*sd; g[3] += expected
    rows = []
    for (vb, nb), (n, cov, sub, exp) in sorted(groups.items()):
        rows.append({"vov": vb, "n_nonzero": nb, "lotes": n, "cobertura": cov/n,
                     "cobertura_esperada_con_SE_exacto": exp/n, "frac_SE_menor_mitad": sub/n})
        print(f"{vb:9s} {nb:10s} lotes={n:5d} cobertura={cov/n:.3f} (esperada {exp/n:.3f}) SE<SD/2={sub/n:.3f}")
    out = a.out_dir/"diagnostico_vov.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out-dir", type=Path, required=True)
    r.add_argument("--build-dir", type=Path, default=PROJECT/"build")
    r.add_argument("--case", choices=CASES, required=True)
    r.add_argument("--events", type=int, required=True)
    r.add_argument("--threads", type=int, default=3)
    s = sub.add_parser("analyze")
    s.add_argument("--out-dir", type=Path, required=True)
    d = sub.add_parser("diagnose", help="valida VOV/n_nonzero como autodiagnóstico de una corrida")
    d.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    a.out_dir = a.out_dir.resolve()
    {"run": run, "analyze": analyze, "diagnose": diagnose}[a.cmd](a)


if __name__ == "__main__":
    main()
