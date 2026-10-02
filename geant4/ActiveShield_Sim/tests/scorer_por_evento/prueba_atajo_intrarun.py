#!/usr/bin/env python3
"""Prueba inicial (exploratoria, no es P2) del atajo intra-run con el scorer
por evento: ¿el SE que da una sola corrida predice la dispersión real entre
corridas independientes?

Diseño fijado antes de correr (regla 2 de plan_piloto.md):

- Fantoma AM desnudo (casco 0.001 cm, sin bobinas ni campo), nave reducida
  (radio 0.6 m, semilongitud 1.0 m) para que la esfera fuente (≈1.37 m)
  dé una fracción de primarios que tocan el fantoma razonable. Ley coseno.
- GCR_H a 1778.28 MeV por defecto; K semillas independientes, M eventos
  cada una, checkpoints intermedios.
- Por categoría (y cuerpo entero): ρ = sqrt(media_k SE_k²) / s_between,
  con SE_k el error estándar de la media por primario de la semilla k y
  s_between la desviación estándar entre semillas de esa misma media.
- Se calcula también con el SE del «Camino B» (columna S2 por vóxel de
  ICRP110.out, que ignora la correlación entre vóxeles del mismo evento).
- IC95 de ρ solo por la incertidumbre de s_between (χ² con K-1 g.l.,
  aproximación de Wilson-Hilferty). Supone normalidad de las medias por
  semilla; con colas pesadas el IC es optimista. El numerador promedia K
  varianzas y su incertidumbre se ignora.
- Lectura: «compatible» si el IC contiene 1. Con K=10 el IC es ~±45%:
  detecta errores gruesos (como un factor 2), no valida la varianza con
  precisión. Eso es P2.

Uso (desde cualquier lugar; usa build/ para el binario y los datos):
    python3 prueba_atajo_intrarun.py --out-dir DIR [--seeds 10 --events 20000]
    python3 prueba_atajo_intrarun.py --out-dir DIR --analyze-only
"""
import argparse
import csv
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
sys.path.insert(0, str(PROJECT/"scripts"))
import write_event_categories  # noqa: E402

BASE_SEED = 20261001_00  # solo para esta prueba; no se reutiliza en el barrido

MACRO = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full
/spacecraft/shipRadius 0.6 m
/spacecraft/shipHalfLength 1.0 m
/spacecraft/hullThickness 0.001 cm
/spacecraft/phantomOffsetX 0 m
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
/score/mesh/translate/xyz 0. 0. 0. mm
/score/quantity/energyDeposit energyDeposit
/score/close
/eventStats/enable true
/eventStats/phantomSex male
/eventStats/phantomSection full
/eventStats/categoryFile {categories}
/eventStats/checkpoints {checkpoints}
/eventStats/output EventStats.tsv
/run/beamOn {events}
/score/dumpQuantityToFile PhantomMesh energyDeposit PhantomMesh_Edep.txt
"""


def chi2_quantile(p, df):
    z = statistics.NormalDist().inv_cdf(p)
    return df*(1-2/(9*df)+z*math.sqrt(2/(9*df)))**3


def read_event_stats(path):
    lines = (l for l in open(path) if not l.startswith("#"))
    out = {}
    for r in csv.DictReader(lines, delimiter="\t"):
        out[(int(r["checkpoint"]), r["kind"], r["id"])] = r
    return out


def read_camino_b(path):
    """organ_id -> (S1_J, S2_J2, n) de la tabla final de ICRP110.out."""
    out, section = {}, False
    for line in open(path):
        if line.startswith("OrganID"):
            section = True
            continue
        if section and "|" in line:
            oid, rest = line.split("|", 1)
            v = rest.split()
            out[int(oid)] = (float(v[2]), float(v[3]), float(v[4]))
    return out


def run_seed(args, k, build, categories):
    work = args.out_dir/f"seed_{k:02d}"
    if (work/"EventStats.tsv").is_file() and (work/"ICRP110.out").is_file():
        return
    work.mkdir(parents=True, exist_ok=True)
    for name in ("ICRPdata", "data"):
        link = work/name
        if not link.exists():
            link.symlink_to(build/name)
    seed1 = BASE_SEED+2*k
    (work/"run.mac").write_text(MACRO.format(
        threads=args.threads, seed1=seed1, seed2=seed1+1, progress=max(args.events//4, 1),
        species=args.species, phase=args.phase, energy=args.energy, categories=categories,
        checkpoints=",".join(map(str, args.checkpoints)), events=args.events))
    t0 = time.time()
    with open(work/"run.log", "w") as log:
        rc = subprocess.run([str(build/"ICRP110phantoms"), "run.mac"], cwd=work,
                            stdout=log, stderr=subprocess.STDOUT).returncode
    if rc != 0:
        raise SystemExit(f"semilla {k}: exit {rc}, ver {work/'run.log'}")
    print(f"semilla {k}: {time.time()-t0:.0f} s", flush=True)


def analyze(args, categories):
    rows, _ = write_event_categories.category_weights(args.icrp_data_dir)
    weights = {}
    for cat, oid, w in rows:
        weights.setdefault(cat, []).append((oid, w))
    seeds = sorted(p for p in args.out_dir.glob("seed_*") if (p/"EventStats.tsv").is_file())
    K = len(seeds)
    if K < 3:
        raise SystemExit("Hacen falta al menos 3 semillas completas")
    stats = [read_event_stats(p/"EventStats.tsv") for p in seeds]
    camino_b = [read_camino_b(p/"ICRP110.out") for p in seeds]
    lo_f = math.sqrt(chi2_quantile(0.025, K-1)/(K-1))
    hi_f = math.sqrt(chi2_quantile(0.975, K-1)/(K-1))
    checkpoints = sorted({c for c, _, _ in stats[0]}, key=lambda c: (c == -1, c))
    print(f"K={K} semillas; IC95 de rho = rho * [{lo_f:.2f}, {hi_f:.2f}] (chi2, normalidad)\n")
    header = f"{'M':>7} {'categoria':<18} {'media/prim [J]':>14} {'s_between':>10} {'rho_evento':>10} {'IC95':>13} {'rho_caminoB':>11} {'n_dep/sem':>9} {'max/S1':>7}"
    print(header)
    result_rows = []
    for c in checkpoints:
        for cat in weights:
            recs = [s[(c, "category", cat)] for s in stats]
            M = float(recs[0]["M"])
            means = [float(r["mean_J"]) for r in recs]
            if not any(means):
                continue
            s_between = statistics.stdev(means)
            se_rms = math.sqrt(statistics.fmean(float(r["se_mean_J"])**2 for r in recs))
            rho = se_rms/s_between if s_between > 0 else math.nan
            rho_b = math.nan
            if c == -1:
                # Fórmula histórica (run_organ_sweep.se_run_total_j): por órgano,
                # SE_total² = n·var_n con var_n = (S2 - S1²/n)/(n-1) y n = pares
                # vóxel-evento; órganos de una categoría tratados como independientes.
                se_b = []
                for cb in camino_b:
                    var_total = 0.0
                    for oid, w in weights[cat]:
                        s1, s2, n = cb.get(oid, (0.0, 0.0, 0.0))
                        if n >= 2:
                            var_total += w*w*n*max((s2-s1*s1/n)/(n-1), 0.0)
                    se_b.append(var_total/M**2)
                rho_b = math.sqrt(statistics.fmean(se_b))/s_between
            n_dep = statistics.fmean(float(r["n_nonzero"]) for r in recs)
            max_frac = max(float(r["max_J"])/float(r["S1_J"]) for r in recs if float(r["S1_J"]) > 0)
            label = "final" if c == -1 else str(c)
            print(f"{label:>7} {cat:<18} {statistics.fmean(means):14.4e} {s_between:10.3e} {rho:10.2f} "
                  f"[{rho*lo_f:5.2f},{rho*hi_f:5.2f}] {rho_b:11.2f} {n_dep:9.0f} {max_frac:7.3f}")
            result_rows.append({"checkpoint": label, "M": M, "categoria": cat, "K": K,
                                "media_J_por_primario": statistics.fmean(means), "s_between": s_between,
                                "se_within_rms": se_rms, "rho_evento": rho, "ic95_lo": rho*lo_f,
                                "ic95_hi": rho*hi_f, "rho_camino_b": rho_b,
                                "eventos_con_deposito_media": n_dep, "max_evento_sobre_S1": max_frac})
    with open(args.out_dir/"resumen_atajo_intrarun.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(result_rows[0]))
        w.writeheader()
        w.writerows(result_rows)
    print(f"\n-> {args.out_dir/'resumen_atajo_intrarun.csv'}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--build-dir", type=Path, default=PROJECT/"build")
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--events", type=int, default=20000)
    p.add_argument("--checkpoints", type=int, nargs="+", default=[5000, 10000])
    p.add_argument("--species", default="GCR_H")
    p.add_argument("--phase", default="min")
    p.add_argument("--energy", type=float, default=1778.28)
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--analyze-only", action="store_true")
    a = p.parse_args()
    a.out_dir = a.out_dir.resolve()
    build = a.build_dir.resolve()
    a.icrp_data_dir = build/"ICRPdata"
    a.out_dir.mkdir(parents=True, exist_ok=True)
    categories = a.out_dir/"event_categories.txt"
    if not categories.is_file():
        subprocess.run([sys.executable, str(PROJECT/"scripts"/"write_event_categories.py"), str(categories),
                        "--icrp-data-dir", str(a.icrp_data_dir)], check=True)
    if not a.analyze_only:
        for k in range(a.seeds):
            run_seed(a, k, build, categories)
    analyze(a, categories)


if __name__ == "__main__":
    main()
