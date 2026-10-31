#!/usr/bin/env python3
"""P2 de plan_piloto.md: ¿el SE de una sola corrida es confiable cuando la
corrida pasa D4? Diseño y criterios fijados el 2026-10-31, antes de correr;
los umbrales salen de scripts/design_parameters.py.

P2a usa la configuración de control (geometría de NIAC, casco de 1.5 cm, sin
campo, esfera fuente de 16 m, fantoma AM en x = 0, ley coseno), así que no
espera el mapa. P2b repite SEP_p 150 MeV con el mapa final (--field-map).

Una corrida larga por caso se parte por event_id en K = 40 lotes de M eventos
(cada lote equivale a una corrida independiente de M eventos, como en
prueba_lotes.py), y además en 160 lotes de M/4 para ver que D4 rechaza esos
lotes. M sale de una sonda que solo mide la fracción f de eventos con
depósito en cuerpo entero: M = ceil(400/f). El plan decía 10⁴ eventos, pero
con la esfera de 16 m eso da ~4 eventos con depósito (f ~ 4·10⁻⁴ en SEP de
150 MeV); la sonda usa 2·10⁵ para que f tenga error de ~10%. Es solo
dimensionamiento: no mira el SE ni los criterios.

D4, por lote y categoría: al menos 200 eventos con depósito, VOV < 0.1 y el
mayor evento <= 10% de S1. Aprobación por caso, con los lotes que pasan D4:
  a) cobertura >= 0.90: fracción de pares (lote, categoría) cuyo IC95
     (media ± 1.96 SE) contiene la media de la corrida completa;
  b) en cada categoría con al menos 10 lotes que pasan D4,
     rho = sqrt(media SE² de esos lotes) / SD de las medias de todos los lotes
     >= 0.75. La SD usa todos los lotes porque es la dispersión real de una
     corrida de M eventos; quitar los lotes con eventos grandes la achicaría;
  c) descriptivo: cobertura de los lotes que no pasan D4.

Uso, desde geant4/ActiveShield_Sim con geant4_env activado:
    python3 tests/scorer_por_evento/p2_estimador.py sonda --case sep70 --out-dir DIR
    python3 tests/scorer_por_evento/p2_estimador.py run --case sep70 --out-dir DIR
    python3 tests/scorer_por_evento/p2_estimador.py analyze --out-dir DIR
Cada caso puede ir en una PC distinta; analyze lee todos los casos de DIR.
"""
import argparse
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
REPO = PROJECT.parent.parent
sys.path.insert(0, str(PROJECT/"scripts"))
import design_parameters as dp  # noqa: E402
from prueba_lotes import chi2_quantile, vov_of  # noqa: E402

# nombre -> (especie, fase, energía [MeV o MeV/n], con campo)
CASES = {
    "sep70": ("SEP_p", "max", 70.0, False),      # justo sobre el corte del casco: cola pesada
    "sep150": ("SEP_p", "max", 150.0, False),    # régimen típico de SEP
    "he1000": ("GCR_He", "min", 1000.0, False),  # carga 2 y fragmentación
    "h10000": ("GCR_H", "min", 10000.0, False),  # cascadas hadrónicas
    "sep150_campo": ("SEP_p", "max", 150.0, True),  # P2b, con el mapa final
}
SEEDS = {name: 2026103100+10*i for i, name in enumerate(CASES)}  # solo P2
SOURCE_RADIUS_M = 16.0
PROBE_EVENTS = 200000
TARGET_NONZERO = 400  # eventos con depósito en cuerpo entero por lote

MACRO = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full
/spacecraft/shipRadius 4.5 m
/spacecraft/shipHalfLength 5.0 m
/spacecraft/sourceSphereRadius {radius} m
/spacecraft/worldHalfSize {world} m
/spacecraft/coilGeometry {gdml}
{field}/run/numberOfThreads {threads}
/run/initialize
/random/setSeeds {seed1} {seed2}
/run/printProgress {progress}
/run/verbose 1
/gun/species {species}
/gun/phase {phase}
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
/eventStats/perEventFile EventCategories.tsv
/run/beamOn {events}
"""


def simulate(a, work, events, seed_offset):
    build = a.build_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    categories = a.out_dir/"event_categories.txt"
    if not categories.is_file():
        subprocess.run([sys.executable, str(PROJECT/"scripts"/"write_event_categories.py"), str(categories),
                        "--icrp-data-dir", str(build/"ICRPdata")], check=True)
    for name in ("ICRPdata", "data"):
        if not (work/name).exists():
            (work/name).symlink_to(build/name)
    species, phase, energy, with_field = CASES[a.case]
    if with_field and not a.field_map:
        sys.exit(f"{a.case} es P2b: pasar --field-map con el mapa final")
    field = f"/spacecraft/fieldMap {a.field_map.resolve()}\n" if with_field else ""
    seed1 = SEEDS[a.case]+seed_offset
    (work/"run.mac").write_text(MACRO.format(
        radius=SOURCE_RADIUS_M, world=SOURCE_RADIUS_M+1, gdml=REPO/"field"/"production"/"crewhat_niac_array.gdml",
        field=field, threads=a.threads, seed1=seed1, seed2=seed1+1, progress=max(events//20, 1),
        species=species, phase=phase, energy=energy, categories=categories, events=events))
    start = time.time()
    with open(work/"run.log", "w") as log:
        subprocess.run([str(build/"ICRP110phantoms"), "run.mac"], cwd=work, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    # Tiempo de los eventos sin la inicialización: "Real=...s" del resumen de la corrida.
    real = re.findall(r"Real=([0-9.]+)s", (work/"run.log").read_text())
    return float(real[-1]) if real else time.time()-start


def read_events(path):
    """(N total, categorías, {categoría: {event_id: valor}}) sin los eventos nulos."""
    with open(path) as f:
        n_total = int(f.readline().split()[2])
        names = f.readline().rstrip("\n").split("\t")[1:]
        values = {name: {} for name in names}
        for line in f:
            fields = line.rstrip("\n").split("\t")
            eid = int(fields[0])
            for name, v in zip(names, fields[1:]):
                if float(v) != 0.0:
                    values[name][eid] = float(v)
    return n_total, names, values


def sonda(a):
    work = a.out_dir/a.case/"sonda"
    seconds = simulate(a, work, PROBE_EVENTS, seed_offset=5)
    n_total, _, values = read_events(work/"EventCategories.tsv")
    f = len(values["total_body"])/n_total
    if f == 0:
        sys.exit("Ningún evento depositó en cuerpo entero: agrandar la sonda (--events) antes de seguir")
    m = math.ceil(TARGET_NONZERO/f)
    nonzero = len(values["total_body"])
    report = {"case": a.case, "probe_events": n_total, "events_with_deposit": nonzero,
              "fraction_with_deposit": f, "M": m, "N": dp.P2_BATCHES*m, "probe_event_seconds": seconds,
              "threads": a.threads, "estimated_run_hours": seconds/n_total*dp.P2_BATCHES*m/3600}
    (a.out_dir/a.case/"sonda.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))
    print(f"Horas estimadas con {a.threads} hilos, sin contar la inicialización.")


def run(a):
    probe = json.loads((a.out_dir/a.case/"sonda.json").read_text())
    events = a.events or probe["N"]
    seconds = simulate(a, a.out_dir/a.case/"corrida", events, seed_offset=0)
    (a.out_dir/a.case/"corrida"/"tiempo.json").write_text(
        json.dumps({"events": events, "seconds": seconds, "threads": a.threads}, indent=2)+"\n")
    print(f"{a.case}: {events} eventos en {seconds/3600:.2f} h")


def batches(values, n_total, m):
    """Por lote [kM, (k+1)M): media, SE, eventos con depósito, mayor evento/S1 y VOV."""
    k = n_total//m
    acc = [[0.0, 0.0, 0.0, 0.0, 0, 0.0] for _ in range(k)]
    for eid, v in values.items():
        b = eid//m
        if b < k:
            x = acc[b]
            x[0] += v; x[1] += v*v; x[2] += v**3; x[3] += v**4; x[4] += 1; x[5] = max(x[5], v)
    rows = []
    for s1, s2, s3, s4, nz, largest in acc:
        rows.append({"mean": s1/m, "se": math.sqrt(max((s2-s1*s1/m)/(m-1), 0.0)/m), "nonzero": nz,
                     "max_fraction": largest/s1 if s1 > 0 else math.inf,
                     "vov": vov_of(s1, s2, s3, s4, m) if nz >= 2 else math.inf})
    return rows


def passes_d4(row):
    return (row["nonzero"] >= dp.MIN_NONZERO_EVENTS and row["vov"] < dp.MAX_VOV
            and row["max_fraction"] <= dp.MAX_EVENT_FRACTION)


def evaluate(n_total, names, values, k):
    m = n_total//k
    covered, total, covered_fail, total_fail, rhos = 0, 0, 0, 0, {}
    for name in names:
        rows = batches(values[name], n_total, m)
        if len(rows) < 2:
            continue
        grand = sum(v for eid, v in values[name].items() if eid < len(rows)*m)/(len(rows)*m)
        sd = statistics.stdev(r["mean"] for r in rows)
        good = [r for r in rows if passes_d4(r)]
        for r in rows:
            hit = abs(r["mean"]-grand) <= 1.96*r["se"]
            if passes_d4(r):
                covered += hit; total += 1
            else:
                covered_fail += hit; total_fail += 1
        if len(good) >= 10 and sd > 0:
            rho = math.sqrt(statistics.fmean(r["se"]**2 for r in good))/sd
            dof = len(rows)-1
            rhos[name] = {"rho": rho, "batches_passing_d4": len(good),
                          "ic95": [rho*math.sqrt(chi2_quantile(0.025, dof)/dof),
                                   rho*math.sqrt(chi2_quantile(0.975, dof)/dof)]}
    return {"K": k, "M": m, "pairs_passing_d4": total, "coverage_passing_d4": covered/total if total else None,
            "pairs_failing_d4": total_fail, "coverage_failing_d4": covered_fail/total_fail if total_fail else None,
            "rho": rhos}


def analyze(a):
    summary = {}
    for case_dir in sorted(p for p in a.out_dir.iterdir() if (p/"corrida"/"EventCategories.tsv").is_file()):
        n_total, names, values = read_events(case_dir/"corrida"/"EventCategories.tsv")
        main = evaluate(n_total, names, values, dp.P2_BATCHES)
        fine = evaluate(n_total, names, values, 4*dp.P2_BATCHES)
        coverage_ok = main["coverage_passing_d4"] is not None and main["coverage_passing_d4"] >= dp.P2_MIN_COVERAGE
        rho_ok = all(r["rho"] >= dp.P2_MIN_RHO for r in main["rho"].values())
        verdict = "aprueba" if coverage_ok and rho_ok and main["rho"] else "no aprueba"
        summary[case_dir.name] = {"N": n_total, "K40": main, "K160": fine, "verdict": verdict}
        print(f"{case_dir.name}: {verdict}. K=40, M={main['M']}: cobertura {main['coverage_passing_d4']} "
              f"en {main['pairs_passing_d4']} pares que pasan D4 (sin D4: {main['coverage_failing_d4']} "
              f"en {main['pairs_failing_d4']}); K=160: {fine['pairs_passing_d4']} pares pasan D4")
        for name, r in main["rho"].items():
            print(f"    {name:<18} rho = {r['rho']:.2f} [{r['ic95'][0]:.2f}, {r['ic95'][1]:.2f}] "
                  f"({r['batches_passing_d4']} lotes pasan D4)")
    if not summary:
        sys.exit("No hay corridas en --out-dir")
    (a.out_dir/"p2_resumen.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(f"-> {a.out_dir/'p2_resumen.json'}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("sonda", "run"):
        s = sub.add_parser(cmd)
        s.add_argument("--case", choices=sorted(CASES), required=True)
        s.add_argument("--out-dir", type=Path, required=True)
        s.add_argument("--build-dir", type=Path, default=PROJECT/"build")
        s.add_argument("--threads", type=int, default=os.cpu_count())
        s.add_argument("--field-map", type=Path, help="mapa final, solo para sep150_campo (P2b)")
        if cmd == "run":
            s.add_argument("--events", type=int, help="por defecto, 40·M de la sonda")
    s = sub.add_parser("analyze")
    s.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    {"sonda": sonda, "run": run, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
