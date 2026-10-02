#!/usr/bin/env python3
"""P0 de plan_piloto.md: dosis absorbida por unidad de fluencia en el
fantoma AM desnudo frente a ICRP 116 (irradiación isótropa, ISO).

Configuración: casco de 0.001 cm, sin bobinas ni campo, nave reducida (radio
0.6 m, semilongitud 1.0 m; esfera fuente ≈1.37 m). La ley coseno sobre la
esfera da fluencia isótropa y uniforme N/(πR²) dentro de ella (verificado,
plan_piloto.md), que es la geometría ISO de ICRP 116.

Coeficiente simulado por órgano o:
    d_o = (S1_o / M) / m_o · πR²   [Gy·cm²]  -> ×1e12 pGy·cm²
con S1_o del scorer por evento (/eventStats) y m_o la masa del órgano con la
definición de ICRP 116 (organos_p0.py). El SE sale de se_mean_J.

Nota: solo se comparan órganos que ICRP 116 tabula, con su definición
(organos_p0.py: el colon incluye la pared del recto, la médula roja se pondera
por la masa de médula activa de cada esponjosa). Las categorías propias del
proyecto (`remainder_tissues`, `total_body`) no se usan en P0.

Criterio D7 (plan_piloto.md): a >= 100 MeV/n, el IC95 del cociente
simulado/ICRP tiene que caer dentro de 1 ± tolerancia: 10% para pulmones,
colon, pared del estómago, hígado y médula roja; 15% para mama y tiroides.
El resto de órganos y energías son descriptivos.

Referencia por defecto: referencias/icrp116_organos_iso_am.csv (material
suplementario v2 de ICRP 116, fantoma masculino, ISO).

Uso:
    python3 p0_icrp116.py run --out-dir DIR --events 3000000 [--seeds 1]
    python3 p0_icrp116.py analyze --out-dir DIR
"""
import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import organos_p0  # noqa: E402
BASE_SEED = 20261001_50  # solo P0
SHIP_RADIUS_M, SHIP_HALF_LENGTH_M, HULL_CM = 0.6, 1.0, 0.001
SOURCE_R_CM = math.hypot(SHIP_RADIUS_M*100, SHIP_HALF_LENGTH_M*100)+HULL_CM+20.0
# Candidatos (plan_piloto.md, P0: 4–6 energías entre 100 MeV/n y 10 GeV/n);
# se fijan con D7 antes de correr.
POINTS = [("proton", e) for e in (100.0, 300.0, 1000.0, 3000.0, 10000.0)] + \
         [("alpha", e) for e in (100.0, 1000.0, 10000.0)]
SPECIES = {"proton": "GCR_H", "alpha": "GCR_He"}

MACRO = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full
/spacecraft/shipRadius {ship_r} m
/spacecraft/shipHalfLength {ship_l} m
/spacecraft/hullThickness {hull} cm
/run/numberOfThreads {threads}
/run/initialize
/random/setSeeds {seed1} {seed2}
/run/printProgress {progress}
/gun/species {species}
/gun/phase min
/gun/angularDistribution cosine
/gun/fixedEnergyMeV {energy}
/score/create/boxMesh PhantomMesh
/score/mesh/boxSize 271.399 135.6995 888. mm
/score/mesh/nBin 254 127 222
/score/quantity/energyDeposit energyDeposit
/score/close
/eventStats/enable true
/eventStats/phantomSex male
/eventStats/phantomSection full
/eventStats/categoryFile {categories}
/eventStats/output EventStats.tsv
/run/beamOn {events}
"""


def run(a):
    build = a.build_dir.resolve()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    categories = a.out_dir/"organos_p0.txt"
    organos_p0.write(categories, build/"ICRPdata")
    for i, (particle, energy) in enumerate(POINTS):
        for s in range(a.seeds):
            work = a.out_dir/f"{particle}_{energy:g}"/f"seed_{s}"
            if (work/"EventStats.tsv").is_file():
                continue
            work.mkdir(parents=True, exist_ok=True)
            for name in ("ICRPdata", "data"):
                if not (work/name).exists():
                    (work/name).symlink_to(build/name)
            seed1 = BASE_SEED+1000*s+2*i
            (work/"run.mac").write_text(MACRO.format(
                ship_r=SHIP_RADIUS_M, ship_l=SHIP_HALF_LENGTH_M, hull=HULL_CM, threads=a.threads,
                seed1=seed1, seed2=seed1+1, progress=max(a.events//4, 1), species=SPECIES[particle],
                energy=energy, categories=categories, events=a.events))
            with open(work/"run.log", "w") as log:
                subprocess.run([str(build/"ICRP110phantoms"), "run.mac"], cwd=work, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            print(f"{particle} {energy:g} MeV/n semilla {s}: listo", flush=True)


def analyze(a):
    masses = {r["categoria"]: float(r["masa_kg"])
              for r in csv.DictReader(open(a.out_dir/"organos_p0.masses.tsv"), delimiter="\t")}
    reference = {}
    for r in csv.DictReader(l for l in open(a.reference) if not l.startswith("#")):
        reference[(r["particula"], float(r["energia_mev_por_nucleon"]), r["organo_icrp"])] = float(r["coef_pGy_cm2"])
    area = math.pi*SOURCE_R_CM**2
    rows = []
    for particle, energy in POINTS:
        for stats in sorted((a.out_dir/f"{particle}_{energy:g}").glob("seed_*/EventStats.tsv")):
            lines = (l for l in open(stats) if not l.startswith("#"))
            for r in csv.DictReader(lines, delimiter="\t"):
                if r["checkpoint"] != "-1" or r["kind"] != "category":
                    continue
                organ = r["id"]
                d = float(r["mean_J"])/masses[organ]*area*1e12
                se = float(r["se_mean_J"])/masses[organ]*area*1e12
                ref = reference.get((particle, energy, organ))
                tol = organos_p0.TOLERANCE.get(organ) if energy >= organos_p0.MIN_ENERGY_PRIMARY else None
                lo = (d-1.96*se)/ref if ref else None
                hi = (d+1.96*se)/ref if ref else None
                reliable = r["vov"] != "inf" and float(r["vov"]) < 0.1
                if tol is None or ref is None:
                    verdict = "descriptivo"
                elif not reliable:
                    verdict = "SE_no_confiable"
                else:
                    verdict = "dentro" if (lo >= 1-tol and hi <= 1+tol) else (
                        "fuera" if (hi < 1-tol or lo > 1+tol) else "inconcluso")
                rows.append({"particula": particle, "energia_mev_por_nucleon": energy,
                             "semilla": stats.parent.name, "organo_icrp": organ,
                             "coef_sim_pGy_cm2": d, "se_pGy_cm2": se,
                             "eventos_con_deposito": r["n_nonzero"], "vov": r["vov"],
                             "coef_icrp116_pGy_cm2": ref if ref else "",
                             "cociente": d/ref if ref else "", "ic95_lo": lo if ref else "",
                             "ic95_hi": hi if ref else "", "tolerancia": tol if tol else "",
                             "veredicto": verdict})
    if not rows:
        raise SystemExit("Sin corridas en --out-dir")
    out = a.out_dir/"p0_resumen.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        if r["tolerancia"]:
            print(f"{r['particula']:6s} {r['energia_mev_por_nucleon']:>8g} {r['organo_icrp']:9s} "
                  f"cociente={r['cociente']:.3f} [{r['ic95_lo']:.3f},{r['ic95_hi']:.3f}] "
                  f"tol=±{r['tolerancia']:.0%} vov={float(r['vov']):.3f} -> {r['veredicto']}")
    print(f"{len(rows)} filas -> {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out-dir", type=Path, required=True)
    r.add_argument("--build-dir", type=Path, default=PROJECT/"build")
    r.add_argument("--events", type=int, required=True)
    r.add_argument("--seeds", type=int, default=1)
    r.add_argument("--threads", type=int, default=4)
    s = sub.add_parser("analyze")
    s.add_argument("--out-dir", type=Path, required=True)
    s.add_argument("--reference", type=Path, default=HERE/"referencias"/"icrp116_organos_iso_am.csv")
    a = p.parse_args()
    run(a) if a.cmd == "run" else analyze(a)


if __name__ == "__main__":
    main()
