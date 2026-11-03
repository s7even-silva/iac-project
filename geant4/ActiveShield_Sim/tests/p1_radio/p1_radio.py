#!/usr/bin/env python3
"""P1 paso 3 de plan_piloto.md: ¿la dosis cambia con el radio de la esfera
fuente? Diseño y criterio fijados el 2026-10-31, antes de correr; B y D4 salen
de scripts/design_parameters.py.

Casos: protones de 70 y 100 MeV sobre el fantoma AM en x = 0 y en x = 4 m
(frente a la bobina 0). Son las energías donde la dosis más depende del
campo: el campo dentro del hábitat (0.45 T junto a la pared) curva los
protones frenados por el casco. Corridas cortas en la laptop, en x = 0, dieron
D_campo/D_control = 0.22 ± 0.08 a 70 MeV, 0.49 ± 0.10 a 100 MeV y
0.83 ± 0.14 a 150 MeV (plan_piloto.md, P1 paso 3). Son además las de menor
rigidez con dosis, las que más desvía la cola del campo (paso 1). Por caso,
cuatro corridas independientes:
  - escudo con R = 14, 16 y 18 m (los candidatos del paso 1), con el mapa
    final (--field-map). El límite de traza queda fijo en 108 m, el que
    tendría R = 18 m: solo varía el radio;
  - control sin campo con R = 16 m: da la dosis sin escudo D0, que escala B.

Decisión, con la dosis absorbida de cuerpo entero (total_body):
  - Δ(Ri, Rj) = (D(Ri) - D(Rj))/D0, con D ∝ R²·S1/M (la misma fluencia);
    equivalentes si el IC95 de Δ cae entero dentro de ±B (plan_barrido.md,
    sección 5). Si una de las corridas no pasa D4 en total_body, esa
    comparación no concluye.
  - R = 14 m se acepta si es equivalente a 16 y a 18 m en los cuatro casos.
    Si no, se corre R20 (reserva del paso 1) y se juzga 16 m contra 18 y
    20 m; 14 m queda descartado.
  - Las otras categorías y B_SECONDARY se reportan y no deciden: cada
    categoría con ±2.5% pediría unos 25 millones de eventos con depósito por
    corrida (la mama masculina recibe el 0.24% de los de cuerpo entero).

Eventos: una sonda de 5·10⁵ primarios con R = 16 m mide la media y la SD por
primario de total_body en el control y en el escudo. N(control) da un SE de
D0 del 1%; N(R) = ((R/16)·SD_escudo/(τ·media_control))², con τ = B/(4·√2),
deja SE(Δ) ≤ B/4 (en cada comparación, 96% de probabilidad de aprobar si la
dosis no cambia). Los dos se multiplican por 1.25 por el error de la sonda.
Los N quedan fijos en sonda.json: no se extienden corridas mirando Δ.

Una corrida se puede partir entre PCs (--parts N --part K): cada parte tiene
N/partes eventos y su propia semilla, y analyze suma S1-S4, M y los eventos
con depósito de todas las partes.

Uso, desde geant4/ActiveShield_Sim con geant4_env activado:
    python3 tests/p1_radio/p1_radio.py sonda --case p70_x0 --out-dir DIR --field-map MAPA
    python3 tests/p1_radio/p1_radio.py run --case p70_x0 --out-dir DIR --field-map MAPA \\
        [--runs control R14 R16 R18] [--parts 4 --part 1]
    python3 tests/p1_radio/p1_radio.py analyze --out-dir DIR
"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
REPO = PROJECT.parent.parent
sys.path.insert(0, str(PROJECT/"scripts"))
sys.path.insert(0, str(HERE.parent/"scorer_por_evento"))
import design_parameters as dp  # noqa: E402
from prueba_lotes import vov_of  # noqa: E402
from run_organ_sweep import parse_event_stats  # noqa: E402

# nombre -> (energía del protón en MeV, x del fantoma en m)
CASES = {"p70_x0": (70.0, 0.0), "p100_x0": (100.0, 0.0), "p70_x4": (70.0, 4.0), "p100_x4": (100.0, 4.0)}
RADII_M = (14.0, 16.0, 18.0)
RESERVE_RADIUS_M = 20.0
CONTROL_RADIUS_M = 16.0
MAX_TRACK_LENGTH_M = 3*2*18.0
PROBE_EVENTS = 500000
CONTROL_REL_SE = 0.01
SHIELD_REL_SE = dp.B/(4*math.sqrt(2))
EVENT_MARGIN = 1.25
# Semillas solo de P1 paso 3: base + 1000·(parte-1) + 20·caso + 2·corrida, es
# decir 200-273 en cada millar desde 2026103200 (P0 usa 150-165 y P2, 100-146).
SEED_BASE = 2026103200
RUN_INDEX = {"control": 0, "R14": 1, "R16": 2, "R18": 3, "R20": 4, "sonda_control": 5, "sonda_escudo": 6}
STATS = ("M", "S1_J", "S2_J2", "S3_J3", "S4_J4", "n_nonzero", "max_J")

MACRO = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full
/spacecraft/shipRadius 4.5 m
/spacecraft/shipHalfLength 5.0 m
/spacecraft/sourceSphereRadius {radius} m
/spacecraft/envelopeMaxTrackLength {max_track} m
/spacecraft/worldHalfSize {world} m
/spacecraft/coilGeometry {gdml}
/spacecraft/phantomOffsetX {x} m
{field}/run/numberOfThreads {threads}
/run/initialize
/random/setSeeds {seed1} {seed2}
/run/printProgress {progress}
/run/verbose 1
/gun/species SEP_p
/gun/phase max
/gun/angularDistribution cosine
/gun/fixedEnergyMeV {energy}
/score/create/boxMesh PhantomMesh
/score/mesh/boxSize 271.399 135.6995 888. mm
/score/mesh/nBin 254 127 222
/score/mesh/translate/xyz {x_mm} 0. 0. mm
/score/quantity/energyDeposit energyDeposit
/score/close
/eventStats/enable true
/eventStats/phantomSex male
/eventStats/phantomSection full
/eventStats/categoryFile {categories}
/eventStats/output EventStats.tsv
/run/beamOn {events}
"""


def run_radius(name):
    return float(name[1:]) if name.startswith("R") else CONTROL_RADIUS_M


def with_field(name):
    return name.startswith("R") or name == "sonda_escudo"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def simulate(a, case, name, events, work, part=1, parts=1):
    build = a.build_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    categories = a.out_dir/"event_categories.txt"
    if not categories.is_file():
        subprocess.run([sys.executable, str(PROJECT/"scripts"/"write_event_categories.py"), str(categories),
                        "--icrp-data-dir", str(build/"ICRPdata")], check=True)
    for link in ("ICRPdata", "data"):
        if not (work/link).exists():
            (work/link).symlink_to(build/link)
    energy, x = CASES[case]
    radius = run_radius(name)
    seed1 = SEED_BASE+1000*(part-1)+20*list(CASES).index(case)+2*RUN_INDEX[name]
    config = {"case": case, "run": name, "part": part, "parts": parts, "proton_MeV": energy, "x_m": x,
              "radius_m": radius, "max_track_length_m": MAX_TRACK_LENGTH_M, "events": events,
              "threads": a.threads, "seeds": [seed1, seed1+1], "physics_list": dp.PHYSICS_LIST}
    field = ""
    if with_field(name):
        if not a.field_map:
            sys.exit(f"{name} lleva campo: pasar --field-map con el mapa final")
        field = f"/spacecraft/fieldMap {a.field_map.resolve()}\n"
        config.update(field_map=str(a.field_map.resolve()), field_map_sha256=sha256(a.field_map))
    (work/"config.json").write_text(json.dumps(config, indent=2)+"\n")
    (work/"run.mac").write_text(MACRO.format(
        radius=radius, max_track=MAX_TRACK_LENGTH_M, world=radius+1,
        gdml=REPO/"field"/"production"/"crewhat_niac_array.gdml", x=x, x_mm=1000*x, field=field,
        threads=a.threads, seed1=seed1, seed2=seed1+1, progress=max(events//20, 1), energy=energy,
        categories=categories, events=events))
    start = time.time()
    with open(work/"run.log", "w") as log:
        subprocess.run([str(build/"ICRP110phantoms"), "run.mac"], cwd=work, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    text = (work/"run.log").read_text()
    # Un binario anterior al 2026-10-31 no tiene /spacecraft/envelopeMaxTrackLength.
    got = re.search(r"Source sphere radius \[m\]: (\S+); MagnetEnvelope max track length \[m\]: (\S+)", text)
    if not got or abs(float(got[1])-radius) > 1e-6 or abs(float(got[2])-MAX_TRACK_LENGTH_M) > 1e-6:
        sys.exit(f"{work}: el radio o el límite de traza no son los pedidos (ver run.log)")
    used = re.search(r"Physics list: (\S+)", text)  # un binario anterior al 2026-11-03 no la imprime
    if not used or used[1] != dp.PHYSICS_LIST:
        sys.exit(f"{work}: la lista de física no es {dp.PHYSICS_LIST} (recompilar, o quitar PHYSLIST)")
    real = re.findall(r"Real=([0-9.]+)s", text)
    return float(real[-1]) if real else time.time()-start


def read_part(work):
    """({categoría: S1-S4, M, ...} de la corrida completa, primarios con trazas cortadas)."""
    rows = parse_event_stats(work/"EventStats.tsv", {}, {})
    cats = {r["id"]: {k: float(r[k]) for k in STATS}
            for r in rows if r["checkpoint"] == "-1" and r["tipo"] == "category"}
    truncated = rows[0]["truncated_primaries"]
    return cats, float(truncated) if truncated != "" else 0.0


def merge(parts):
    """Partes independientes de una corrida: suman S1-S4, M y eventos con depósito; max_J es el mayor."""
    out = {}
    for name in parts[0][0]:
        c = {k: sum(p[0][name][k] for p in parts) for k in STATS if k != "max_J"}
        c["max_J"] = max(p[0][name]["max_J"] for p in parts)
        c["vov"] = vov_of(c["S1_J"], c["S2_J2"], c["S3_J3"], c["S4_J4"], c["M"]) if c["n_nonzero"] >= 2 else math.inf
        out[name] = c
    return out, sum(p[1] for p in parts)/out["total_body"]["M"]


def read_run(run_dir):
    """Todas las partes de una corrida juntas, o None si falta alguna."""
    done = {}
    for stats in run_dir.glob("parte_*_de_*/EventStats.tsv"):
        k, n = map(int, re.fullmatch(r"parte_(\d+)_de_(\d+)", stats.parent.name).groups())
        done.setdefault(n, set()).add(k)
    complete = [n for n, ks in done.items() if ks == set(range(1, n+1))]
    if len(done) != 1 or not complete:
        return None
    n = complete[0]
    return merge([read_part(run_dir/f"parte_{k}_de_{n}") for k in range(1, n+1)])


def moments(c):
    """Media por primario, su SE y la SD por primario."""
    m = c["M"]
    var = max((c["S2_J2"]-c["S1_J"]**2/m)/(m-1), 0.0)
    return c["S1_J"]/m, math.sqrt(var/m), math.sqrt(var)


def passes_d4(c):
    return (c["n_nonzero"] >= dp.MIN_NONZERO_EVENTS and c["vov"] < dp.MAX_VOV
            and c["S1_J"] > 0 and c["max_J"]/c["S1_J"] <= dp.MAX_EVENT_FRACTION)


def compare(run_i, run_j, control):
    """Cada argumento es (R en m, estadísticos de una categoría). Δ = (D_i - D_j)/D0 con D ∝ R²·S1/M."""
    (ri, ci), (rj, cj), (r0, c0) = run_i, run_j, control
    (mi, si, _), (mj, sj, _), (m0, s0, _) = moments(ci), moments(cj), moments(c0)
    d0 = r0**2*m0
    if d0 <= 0:
        return None
    delta = (ri**2*mi-rj**2*mj)/d0
    se = math.hypot(ri**2*si, rj**2*sj, delta*r0**2*s0)/d0
    reach = abs(delta)+1.96*se
    return {"delta": delta, "se": se, "ci95": [delta-1.96*se, delta+1.96*se],
            "d4": passes_d4(ci) and passes_d4(cj) and passes_d4(c0),
            "equivalent_B": reach < dp.B, "equivalent_B_secondary": reach < dp.B_SECONDARY}


def decide(pairs, radii, key="equivalent_B"):
    """El tercer radio desde arriba, si es equivalente (y con D4) a los dos mayores en todos los casos."""
    r, refs = radii[-3], radii[-2:]
    ok = all(p is not None and p["d4"] and p[key] for case in pairs.values() for ref in refs for p in [case[(r, ref)]])
    return r if ok else None


def sonda(a):
    probe, n = {}, a.events or PROBE_EVENTS
    for name in ("sonda_control", "sonda_escudo"):
        work = a.out_dir/a.case/name
        seconds = simulate(a, a.case, name, n, work)
        cats, _ = read_part(work)
        mean, _, sd = moments(cats["total_body"])
        probe[name] = {"events": n, "with_deposit": cats["total_body"]["n_nonzero"],
                       "mean_J": mean, "sd_J": sd, "seconds_per_event": seconds/n}
    mu0, sd0 = probe["sonda_control"]["mean_J"], probe["sonda_control"]["sd_J"]
    sd1 = probe["sonda_escudo"]["sd_J"]
    if mu0 <= 0 or sd1 <= 0:
        sys.exit("La sonda no tuvo eventos con depósito en cuerpo entero: revisar la configuración")
    events = {"control": math.ceil(EVENT_MARGIN*(sd0/(CONTROL_REL_SE*mu0))**2)}
    for r in RADII_M+(RESERVE_RADIUS_M,):
        events[f"R{r:g}"] = math.ceil(EVENT_MARGIN*((r/CONTROL_RADIUS_M)*sd1/(SHIELD_REL_SE*mu0))**2)
    hours = {name: n*probe["sonda_escudo" if with_field(name) else "sonda_control"]["seconds_per_event"]/3600
             for name, n in events.items()}
    report = {"case": a.case, "threads": a.threads, "physics_list": dp.PHYSICS_LIST, "probe": probe,
              "events": events, "estimated_hours": hours}
    (a.out_dir/a.case/"sonda.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))
    print(f"Horas estimadas con {a.threads} hilos, sin la inicialización (~30 s con el mapa .bmap).")


def run(a):
    if not 1 <= a.part <= a.parts:
        sys.exit("--part tiene que estar entre 1 y --parts")
    probe = None if a.events else json.loads((a.out_dir/a.case/"sonda.json").read_text())
    if probe and probe.get("physics_list") != dp.PHYSICS_LIST:
        sys.exit(f"La sonda de {a.case} no se hizo con {dp.PHYSICS_LIST}: repetirla")
    for name in a.runs:
        work = a.out_dir/a.case/name/f"parte_{a.part}_de_{a.parts}"
        if (work/"EventStats.tsv").is_file():
            print(f"{work}: ya está, se salta")
            continue
        events = a.events or math.ceil(probe["events"][name]/a.parts)
        seconds = simulate(a, a.case, name, events, work, a.part, a.parts)
        (work/"tiempo.json").write_text(json.dumps({"events": events, "seconds": seconds,
                                                    "threads": a.threads}, indent=2)+"\n")
        print(f"{work}: {events} eventos en {seconds/3600:.2f} h")


def analyze(a):
    pairs, by_category, runs_info, maps, radii_by_case = {}, {}, {}, set(), {}
    for case in CASES:
        d = a.out_dir/case
        control = read_run(d/"control")
        runs = {run_radius(p.name): read_run(p) for p in d.glob("R*") if p.is_dir()}
        runs = {r: v for r, v in runs.items() if v is not None}
        if control is None or len(runs) < 3:
            print(f"{case}: incompleto (faltan el control, algún radio o alguna parte); no entra en la decisión")
            continue
        for r, (cats, truncated) in sorted(runs.items()):
            maps |= {json.loads(p.read_text()).get("field_map_sha256") for p in (d/f"R{r:g}").glob("parte_*/config.json")}
            runs_info[f"{case}/R{r:g}"] = {"total_body_with_deposit": cats["total_body"]["n_nonzero"],
                                           "d4_total_body": passes_d4(cats["total_body"]),
                                           "truncated_primary_fraction": truncated}
        radii = sorted(runs)
        radii_by_case[case] = radii
        c0 = control[0]
        pairs[case] = {(ri, rj): compare((ri, runs[ri][0]["total_body"]), (rj, runs[rj][0]["total_body"]),
                                         (CONTROL_RADIUS_M, c0["total_body"]))
                       for i, ri in enumerate(radii) for rj in radii[i+1:]}
        by_category[case] = {name: compare((radii[0], runs[radii[0]][0][name]), (radii[-1], runs[radii[-1]][0][name]),
                                           (CONTROL_RADIUS_M, c0[name]))
                             for name in c0 if name != "total_body"}
    if not pairs:
        sys.exit("No hay casos completos en --out-dir")
    if len(maps) != 1 or None in maps:
        sys.exit(f"Las corridas con escudo no usaron un mismo mapa: {maps}")
    lists = {json.loads(p.read_text()).get("physics_list") for p in a.out_dir.glob("*/*/parte_*/config.json")}
    if lists != {dp.PHYSICS_LIST}:
        sys.exit(f"Las partes no usaron todas {dp.PHYSICS_LIST}: {lists}")
    complete = len(pairs) == len(CASES) and len({tuple(r) for r in radii_by_case.values()}) == 1
    radii = next(iter(radii_by_case.values()))
    chosen = decide(pairs, radii) if complete else None
    chosen2 = decide(pairs, radii, "equivalent_B_secondary") if complete else None
    print(f"B = {dp.B:.2%} de D0; B secundario = {dp.B_SECONDARY:.2%}. Métrica: total_body.")
    for case, rows in pairs.items():
        print(case)
        for (ri, rj), p in rows.items():
            if p is None:
                print(f"    R{ri:g} - R{rj:g}: el control no tiene dosis")
                continue
            verdict = ("no concluye (D4)" if not p["d4"] else "equivalente" if p["equivalent_B"]
                       else "no equivalente")
            print(f"    R{ri:g} - R{rj:g}: Δ = {p['delta']:+.2%} ± {1.96*p['se']:.2%} (IC95) -> {verdict}"
                  f"{'; también con B secundario' if p['equivalent_B_secondary'] else ''}")
    for name, info in runs_info.items():
        print(f"    {name}: {info['total_body_with_deposit']:.0f} eventos con depósito, D4 {info['d4_total_body']}, "
              f"trazas cortadas en {info['truncated_primary_fraction']:.2%} de los primarios")
    if not complete:
        print("Decisión: pendiente, faltan casos o radios.")
    else:
        judged = radii[-3]
        print(f"Decisión ({judged:g} m frente a {radii[-2]:g} y {radii[-1]:g} m): "
              f"{'se acepta R = %g m' % chosen if chosen else 'no se acepta'}; con B secundario: "
              f"{'también' if chosen2 else 'no'}.")
    summary = {"B": dp.B, "B_secondary": dp.B_SECONDARY, "metric": "total_body", "complete": complete,
               "chosen_radius_m": chosen, "chosen_radius_secondary_m": chosen2, "field_map_sha256": maps.pop(),
               "runs": runs_info,
               "total_body": {case: {f"R{ri:g}-R{rj:g}": p for (ri, rj), p in rows.items()}
                              for case, rows in pairs.items()},
               "categories_smallest_vs_largest_radius": by_category}
    (a.out_dir/"p1_paso3_resumen.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(f"-> {a.out_dir/'p1_paso3_resumen.json'}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for cmd in ("sonda", "run"):
        s = sub.add_parser(cmd)
        s.add_argument("--case", choices=list(CASES), required=True)
        s.add_argument("--out-dir", type=Path, required=True)
        s.add_argument("--field-map", type=Path, help="mapa final (en Drive; manifiesto en field/production)")
        s.add_argument("--build-dir", type=Path, default=PROJECT/"build")
        s.add_argument("--threads", type=int, default=os.cpu_count())
        s.add_argument("--events", type=int, help="solo para pruebas; por defecto, 5·10⁵ (sonda) o N de sonda.json / partes")
        if cmd == "run":
            s.add_argument("--runs", nargs="+", choices=list(RUN_INDEX)[:5], default=["control", "R14", "R16", "R18"])
            s.add_argument("--parts", type=int, default=1)
            s.add_argument("--part", type=int, default=1)
    s = sub.add_parser("analyze")
    s.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    {"sonda": sonda, "run": run, "analyze": analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
