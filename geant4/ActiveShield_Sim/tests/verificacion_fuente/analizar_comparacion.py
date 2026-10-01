#!/usr/bin/env python3
import json, math, re, statistics as st, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_organ_sweep as ros

HERE = Path(__file__).resolve().parents[2] / "build" / "verificacion_fuente"
recs = [json.loads(l) for l in open(HERE / "results.jsonl")]

def load(tag):
    rows = ros.parse_icrp110_out(HERE / "runs" / f"{tag}.out")
    n = int(re.search(r"_n(\d+)$", tag).group(1))
    edep = sum(v["edep_J"] for k, v in rows.items() if k != 140)
    # SE intra-run (subestimado, ver Fase 7): suma de varianzas por organo
    var = sum((v.get("se_run_j") or 0.0) ** 2 for k, v in rows.items() if k != 140)
    return n, edep, math.sqrt(var)

print(f"{'tag':60s} {'s':>6s} {'edep/primario [J]':>18s} {'SE_intra %':>10s}")
per = {}
for r in recs:
    n, e, se = load(r["tag"])
    per[r["tag"]] = (n, e / n)
    print(f"{r['tag']:60s} {r['seconds']:6.0f} {e/n:18.4e} {100*se/e if e else float('nan'):10.1f}")

def pick(prefix):
    return {t: v for t, v in per.items() if t.startswith(prefix)}

t1 = pick("T1_")
x0 = [v[1] for t, v in t1.items() if "_x0.0_" in t]
x1 = [v[1] for t, v in t1.items() if "_x1.0_" in t]
if x0 and x1:
    print(f"\nT1 (sin campo, ley coseno): dosis x=1 / x=0 = {x1[0]/x0[0]:.3f}")

for lab in ("T2rad_", "T2_"):
    d = pick(lab)
    el = {re.search(r"_s(\d+)_", t).group(1): v[1] for t, v in d.items() if "_elmer_" in t}
    bs = {re.search(r"_s(\d+)_", t).group(1): v[1] for t, v in d.items() if "_bs_" in t}
    seeds = sorted(set(el) & set(bs))
    if not seeds:
        continue
    ratios = [bs[s] / el[s] for s in seeds]
    tot = sum(bs[s] for s in seeds) / sum(el[s] for s in seeds)
    extra = ""
    if len(ratios) > 1:
        m, sd = st.mean(ratios), st.stdev(ratios)
        extra = f", media por semilla {m:.3f} ± {sd/math.sqrt(len(ratios)):.3f} (SE entre semillas)"
    print(f"{lab} BS/Elmer: semillas {seeds}, cociente de pools {tot:.3f}{extra}; por semilla {[round(x,3) for x in ratios]}")
