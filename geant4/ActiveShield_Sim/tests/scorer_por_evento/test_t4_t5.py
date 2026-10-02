#!/usr/bin/env python3
"""Tests T4 y T5 de docs/bitacora/plan_barrido.md (sección 8), con una
corrida corta de Geant4 (~1–2 min).

T4: el scorer por evento (/eventStats/*) da, por órgano, el mismo S1 que
    ICRP110.out; M es igual al número de primarios; S1/S2 de cada categoría
    coinciden con los recalculados desde el archivo por evento (R12); los
    checkpoints son acumulados.
T5: una magnitud que no es energía (trackLength) se vuelca en su unidad
    (mm), no dividida por joule.

Uso: python3 test_t4_t5.py [--build-dir build] (lo registra ctest como event_stats).
"""
import argparse
import csv
import math
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
N = 3000

MACRO = f"""\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full
/spacecraft/shipRadius 0.6 m
/spacecraft/shipHalfLength 1.0 m
/spacecraft/hullThickness 0.001 cm
/run/numberOfThreads 2
/run/initialize
/random/setSeeds 4401 4402
/gun/species GCR_H
/gun/phase min
/gun/angularDistribution cosine
/gun/fixedEnergyMeV 1778.28
/score/create/boxMesh PhantomMesh
/score/mesh/boxSize 271.399 135.6995 888. mm
/score/mesh/nBin 254 127 222
/score/quantity/energyDeposit energyDeposit
/score/close
/score/create/boxMesh FluxBox
/score/mesh/boxSize 250. 250. 250. mm
/score/mesh/nBin 1 1 1
/score/quantity/trackLength primLen
/score/close
/eventStats/enable true
/eventStats/phantomSex male
/eventStats/phantomSection full
/eventStats/categoryFile event_categories.txt
/eventStats/checkpoints 1000,2000
/eventStats/output EventStats.tsv
/eventStats/perEventFile EventCategories.tsv
/run/beamOn {N}
/score/dumpQuantityToFile FluxBox primLen FluxLen.txt
/score/dumpQuantityToFile PhantomMesh energyDeposit PhantomMesh_Edep.txt
"""


def fail(message):
    print("FAIL:", message)
    sys.exit(1)


def rows_of(path):
    return list(csv.DictReader((l for l in open(path) if not l.startswith("#")), delimiter="\t"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--build-dir", type=Path, default=PROJECT/"build")
    a = p.parse_args()
    build = a.build_dir.resolve()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for name in ("ICRPdata", "data"):
            (work/name).symlink_to(build/name)
        subprocess.run([sys.executable, str(PROJECT/"scripts"/"write_event_categories.py"),
                        str(work/"event_categories.txt"), "--icrp-data-dir", str(build/"ICRPdata")],
                       check=True, capture_output=True)
        (work/"t.mac").write_text(MACRO)
        proc = subprocess.run([str(build/"ICRP110phantoms"), "t.mac"], cwd=work,
                              capture_output=True, text=True)
        if proc.returncode != 0 or "G4Exception" in proc.stdout:
            fail("la corrida falló:\n"+proc.stdout[-3000:]+proc.stderr[-3000:])

        stats = rows_of(work/"EventStats.tsv")
        header = [l for l in open(work/"EventStats.tsv") if l.startswith("# events_total")]
        if not header or int(header[0].split()[2]) != N:
            fail(f"events_total distinto de {N}")
        final = [r for r in stats if r["checkpoint"] == "-1"]
        if any(float(r["M"]) != N for r in final):
            fail("M final distinto del número de primarios")

        # S1 por órgano frente a ICRP110.out (6 cifras significativas impresas).
        out, section = {}, False
        for line in open(work/"ICRP110.out"):
            if line.startswith("OrganID"):
                section = True
            elif section and "|" in line:
                oid, rest = line.split("|", 1)
                out[int(oid)] = float(rest.split()[0])
        organs = {int(r["id"]): float(r["S1_J"]) for r in final if r["kind"] == "organ"}
        if not organs:
            fail("ningún órgano con depósito; la prueba no ejercita el scorer")
        for oid in set(organs) | {k for k, v in out.items() if v}:
            ref = out.get(oid, 0.0)
            if not math.isclose(organs.get(oid, 0.0), ref, rel_tol=1e-5, abs_tol=1e-30):
                fail(f"órgano {oid}: S1={organs.get(oid)} frente a ICRP110.out {ref}")

        cats = {r["id"]: r for r in final if r["kind"] == "category"}
        body = sum(v for k, v in organs.items() if k not in (0, 140))
        if not math.isclose(float(cats["total_body"]["S1_J"]), body, rel_tol=1e-9):
            fail("total_body no es la suma de los órganos")

        # S1/S2 por categoría desde el archivo por evento (R12).
        per = rows_of(work/"EventCategories.tsv")
        for name, r in cats.items():
            values = [float(e[name]) for e in per]
            s1, s2 = sum(values), sum(v*v for v in values)
            if not (math.isclose(s1, float(r["S1_J"]), rel_tol=1e-12, abs_tol=1e-300)
                    and math.isclose(s2, float(r["S2_J2"]), rel_tol=1e-12, abs_tol=1e-300)):
                fail(f"categoría {name}: S1/S2 no coinciden con el archivo por evento")
            s3, s4 = sum(v**3 for v in values), sum(v**4 for v in values)
            if not (math.isclose(s3, float(r["S3_J3"]), rel_tol=1e-12, abs_tol=1e-300)
                    and math.isclose(s4, float(r["S4_J4"]), rel_tol=1e-12, abs_tol=1e-300)):
                fail(f"categoría {name}: S3/S4 no coinciden con el archivo por evento")
            m = N
            den = (s2-s1*s1/m)**2
            if sum(1 for v in values if v != 0) >= 2 and den > 0:
                vov = (s4-4*s1*s3/m+6*s1*s1*s2/m**2-3*s1**4/m**3)/den-1/m
                if not math.isclose(vov, float(r["vov"]), rel_tol=1e-6):
                    fail(f"categoría {name}: VOV {r['vov']} frente a {vov}")
            elif r["vov"] != "inf":
                fail(f"categoría {name}: VOV sin varianza debería ser inf")
            nz = sum(1 for v in values if v != 0)
            if nz != int(float(r["n_nonzero"])):
                fail(f"categoría {name}: n_nonzero {r['n_nonzero']} frente a {nz}")
            # Checkpoints acumulados: eventos con id < M.
            for c in (1000, 2000):
                rc = next(x for x in stats if x["checkpoint"] == str(c) and x["kind"] == "category"
                          and x["id"] == name)
                sub = sum(float(e[name]) for e in per if int(e["event_id"]) < c)
                if not math.isclose(sub, float(rc["S1_J"]), rel_tol=1e-12, abs_tol=1e-300) or float(rc["M"]) != c:
                    fail(f"checkpoint {c} de {name} no es acumulado")

        flux = (work/"FluxLen.txt").read_text().splitlines()
        if not any("unit: mm" in l for l in flux):
            fail("T5: FluxLen.txt sin la unidad mm")
        length = float([l for l in flux if not l.startswith("#")][0].split()[3])
        if not 1.0 < length < 1e9:
            fail(f"T5: longitud de traza {length} mm fuera de rango (¿dividida por joule?)")
    print(f"OK T4/T5: {len(organs)} órganos, {cats['total_body']['n_nonzero']} eventos con depósito")


if __name__ == "__main__":
    main()
