#!/usr/bin/env python3
"""P0 de plan_piloto.md: dosis absorbida por unidad de fluencia en el
fantoma AM desnudo frente a ICRP 116 (irradiación isótropa, ISO).

Preparado, no corrido: P0 no se aprueba sin la tolerancia D7 ni la tabla
ICRP 116 transcrita y versionada. Fijar D7, la lista de energías/órganos y
las comparaciones primarias antes de ejecutar `run`.

Configuración: casco de 0.001 cm, sin bobinas ni campo, nave reducida (radio
0.6 m, semilongitud 1.0 m; esfera fuente ≈1.37 m). La ley coseno sobre la
esfera da fluencia isótropa y uniforme N/(πR²) dentro de ella (verificado,
plan_piloto.md), que es la geometría ISO de ICRP 116.

Coeficiente simulado por categoría c:
    d_c = (S1_c / M) / m_c · πR²   [Gy·cm²]  -> ×1e12 pGy·cm²
con S1_c del scorer por evento (/eventStats) y m_c la masa pooled de
write_event_categories.py. El SE sale de se_mean_J del mismo archivo.

Tabla de referencia (`--reference`, CSV): columnas
    particula (proton|alpha), energia_mev_por_nucleon, categoria, coef_pGy_cm2
con los valores ISO de ICRP 116 para el fantoma masculino (dosis absorbida,
no efectiva). Las categorías tienen que ser las de write_event_categories.py.

Uso:
    python3 p0_icrp116.py run --out-dir DIR --events 20000 [--seeds 1]
    python3 p0_icrp116.py analyze --out-dir DIR --reference icrp116_iso_am.csv
"""
import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
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
    categories = a.out_dir/"event_categories.txt"
    subprocess.run([sys.executable, str(PROJECT/"scripts"/"write_event_categories.py"), str(categories),
                    "--icrp-data-dir", str(build/"ICRPdata")], check=True)
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
              for r in csv.DictReader(open(a.out_dir/"event_categories.masses.tsv"), delimiter="\t")}
    reference = {}
    if a.reference:
        for r in csv.DictReader(open(a.reference)):
            reference[(r["particula"], float(r["energia_mev_por_nucleon"]), r["categoria"])] = float(r["coef_pGy_cm2"])
    area = math.pi*SOURCE_R_CM**2
    rows = []
    for particle, energy in POINTS:
        for stats in sorted((a.out_dir/f"{particle}_{energy:g}").glob("seed_*/EventStats.tsv")):
            lines = (l for l in open(stats) if not l.startswith("#"))
            for r in csv.DictReader(lines, delimiter="\t"):
                if r["checkpoint"] != "-1" or r["kind"] != "category":
                    continue
                cat = r["id"]
                d = float(r["mean_J"])/masses[cat]*area*1e12
                se = float(r["se_mean_J"])/masses[cat]*area*1e12
                ref = reference.get((particle, energy, cat))
                row = {"particula": particle, "energia_mev_por_nucleon": energy, "semilla": stats.parent.name,
                       "categoria": cat, "coef_sim_pGy_cm2": d, "se_pGy_cm2": se,
                       "eventos_con_deposito": r["n_nonzero"], "coef_icrp116_pGy_cm2": ref or "",
                       "cociente": d/ref if ref else "",
                       "ic95_lo": (d-1.96*se)/ref if ref else "", "ic95_hi": (d+1.96*se)/ref if ref else ""}
                rows.append(row)
    if not rows:
        raise SystemExit("Sin corridas en --out-dir")
    out = a.out_dir/"p0_resumen.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} filas -> {out}")
    if not reference:
        print("Sin --reference: solo coeficientes simulados; P0 no se evalúa.")


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
    s.add_argument("--reference", type=Path)
    a = p.parse_args()
    run(a) if a.cmd == "run" else analyze(a)


if __name__ == "__main__":
    main()
