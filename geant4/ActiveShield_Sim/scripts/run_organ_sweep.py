#!/usr/bin/env python3
"""Corre el barrido reducido de dosis por organo en ActiveShield_Sim: 3
especies (en su fase mas peligrosa) x 5 posiciones del fantoma, a la maxima
intensidad de campo del barrido de GCR_SEP_Sim (10 T) -- ver AGENTS.md,
seccion ActiveShield_Sim / analisis de riesgo estocastico.

Esto NO es un barrido de campo/fase completo: se decidio (2026-09-10)
reducirlo al escenario que le interesa al usuario -- blindaje maximo +
evento mas peligroso de cada especie (GCR en minimo solar, mayor flujo GCR;
SEP en Oct 1989, peor evento SEP) -- variando solo la posicion del fantoma
dentro de la nave, en vez de correr las 140 combinaciones de campo x fase x
posicion. Si luego se quiere explorar otras intensidades o la fase
contraria, hay que correr este script de nuevo con otros parametros (no es
configurable por CLI a proposito, ver AGENTS.md por el porque de la
reduccion).

Cada corrida es de UNA sola especie (ICRP110UserScoreWriter no distingue
especies dentro de una misma corrida -- combinar especies con sus pesos
fisicos W[s] se hace despues en Python, ver aggregate_organ_doses.py).
ICRP110UserScoreWriter siempre escribe su salida en un archivo de nombre
FIJO ("ICRP110.out", sin importar el nombre que se le de a
/score/dumpQuantityToFile) -- por eso las corridas son secuenciales
(subprocess.run una por una) y cada ICRP110.out se archiva con un nombre
unico inmediatamente despues de cada corrida, antes de lanzar la siguiente.

Requiere:
- ActiveShield_Sim ya compilado (ver README.md / AGENTS.md).
- Un mapa de campo uniforme ya generado con field/generate_uniform_map.py
  (entorno field/.venv, NO geant4_env -- este script no lo genera, para no
  mezclar entornos, ver AGENTS.md).

Uso:
    python3 run_organ_sweep.py --field-map ../build/uniform_1T.map
    python3 run_organ_sweep.py --field-map ../build/uniform_1T.map --n-events 100 --limit 2  # piloto
    python3 run_organ_sweep.py --field-map ../build/uniform_1T.map --no-resume

Resume esta activado por defecto (mismo criterio que GCR_SEP_Sim/run_sweep.py):
al relanzar el mismo comando se saltan los indices de corrida que ya tengan
exit_code 0 en organ_sweep_manifest.csv. OJO: el manifiesto no registra si
--n-events cambio entre corridas -- si se corre primero un piloto con pocos
eventos y despues se quiere la corrida completa, usar --no-resume para
rehacer esos indices con el --n-events real (si no, quedarian con la
estadistica del piloto mezclada con el resto).
"""
import argparse
import csv
import itertools
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import sweep_config  # noqa: E402 -- constantes compartidas entre proyectos, ver geant4/sweep_config.py

# Escenario fijo (decision 2026-09-10, ver AGENTS.md): NO cambiar a una lista
# con mas valores de campo/fase sin revisarlo antes -- fue una reduccion de
# alcance deliberada frente al barrido completo de 140 corridas.
FIELD_T = 10.0
POSITIONS_CM = [0.0, 70.0, 140.0, 210.0, 280.0]
SPECIES_PHASE = [("GCR_H", "min"), ("GCR_He", "min"), ("SEP_p", "max")]

BASE_SEED = sweep_config.BASE_SEED_ACTIVE_SHIELD_SIM

MACRO_TEMPLATE = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full

/spacecraft/fieldMap {field_map}
/spacecraft/fieldScale {field_scale}
/spacecraft/phantomPositionCm {position_cm}

/run/initialize
/random/setSeeds {seed1} {seed2}

/control/verbose 1
/tracking/verbose 0
/run/verbose 0
/event/verbose 0

/gun/species {species}
/gun/phase {phase}

/score/create/boxMesh PhantomMesh
/score/mesh/boxSize 271.399 135.6995 888. mm
/score/mesh/nBin 254 127 222
/score/mesh/translate/xyz 0. 0. 0. mm
/score/quantity/energyDeposit energyDeposit
/score/close

/run/beamOn {n_events}

/score/dumpQuantityToFile PhantomMesh energyDeposit PhantomMesh_Edep.txt
"""


def build_combinations():
    combos = []
    for index, ((species, phase), position_cm) in enumerate(
        itertools.product(SPECIES_PHASE, POSITIONS_CM)
    ):
        combos.append({"index": index, "species": species, "phase": phase, "position_cm": position_cm})
    return combos


def parse_icrp110_out(out_path):
    """Extrae (organ_id, edep_J, dose_Gy) de la tabla "para TODOS los
    organos" de ICRP110.out (incluye IDs con edep 0, en orden estrictamente
    creciente de ID). Se usa esta tabla -- no la de "solo organos con edep
    != 0" que aparece antes en el mismo archivo -- porque da un valor por ID
    sin depender de alinear posicionalmente esa otra tabla con la lista de
    nombres de organo que le sigue. El mapeo ID->nombre se hace aparte, en
    aggregate_organ_doses.py, leyendo ICRPdata/.../AM_organs.dat directamente
    (no verificado en este entorno porque ICRPdata/ aun no se ha descargado,
    ver AGENTS.md). Formato exacto parseado aqui: ver
    ICRP110UserScoreWriter.cc, seccion final ("OrganID | Edep Dose", todos
    los IDs 0..NOrganIDs-1).
    """
    text = out_path.read_text()
    marker = "ORGAN ENERGY DEPOSITIONS AND ABSORBED DOSE"
    if marker not in text:
        raise ValueError(f"{out_path}: no se encontro la seccion '{marker}'")
    tail = text.split(marker, 1)[1]
    rows = []
    in_table = False
    for line in tail.splitlines():
        if line.startswith("OrganID"):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("Total energy"):
            break
        if "|" not in line:
            continue
        left, right = line.split("|", 1)
        parts = right.split()
        if len(parts) < 2:
            continue
        rows.append((int(left.strip()), float(parts[0]), float(parts[1])))
    if not rows:
        raise ValueError(f"{out_path}: no se pudo parsear ninguna fila de la tabla de organos")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--field-map", type=Path, required=True,
                         help="Ruta al .map generado con field/generate_uniform_map.py (referencia 1 T)")
    parser.add_argument("--build-dir", type=Path, default=None,
                         help="Directorio de build con ICRP110phantoms compilado (default: <repo>/build)")
    parser.add_argument("--n-events", type=int, default=sweep_config.DEFAULT_N_EVENTS,
                         help=f"Eventos por corrida, default {sweep_config.DEFAULT_N_EVENTS}")
    parser.add_argument("--limit", type=int, default=None,
                         help="Solo correr las primeras N combinaciones (piloto)")
    parser.add_argument("--no-resume", dest="resume", action="store_false", default=True,
                         help="Rehacer desde cero incluso las corridas ya exitosas (exit_code 0)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    build_dir = (args.build_dir or (project_root / "build")).resolve()
    binary_path = build_dir / "ICRP110phantoms"
    field_map = args.field_map.resolve()

    if not binary_path.is_file():
        sys.exit(f"ERROR: no se encontro {binary_path}. Compila ActiveShield_Sim primero (ver README.md).")
    if not field_map.is_file():
        sys.exit(f"ERROR: no se encontro {field_map}. Generalo con field/generate_uniform_map.py primero "
                  "(entorno field/.venv, no geant4_env -- ver AGENTS.md).")

    generated_dir = build_dir / "macros" / "generated_organ"
    logs_dir = build_dir / "logs_organ"
    archive_dir = build_dir / "organ_out_archive"
    generated_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    combos = build_combinations()
    if args.limit is not None:
        combos = combos[:args.limit]

    manifest_path = build_dir / "organ_sweep_manifest.csv"
    manifest_fieldnames = ["index", "especie", "fase", "field_T", "position_cm",
                            "n_events", "seed1", "seed2", "macro_path", "exit_code",
                            "duration_s", "log_path", "out_archive_path"]

    done_runs = set()
    if args.resume and manifest_path.is_file():
        with open(manifest_path, newline="") as f:
            for row in csv.DictReader(f):
                if row["exit_code"] == "0":
                    done_runs.add(int(row["index"]))
        print(f"resume: {len(done_runs)} corrida(s) ya completada(s), se saltaran (--no-resume para rehacerlas).")

    manifest_mode = "a" if (args.resume and manifest_path.is_file()) else "w"
    manifest_file = open(manifest_path, manifest_mode, newline="")
    manifest_writer = csv.DictWriter(manifest_file, fieldnames=manifest_fieldnames)
    if manifest_mode == "w":
        manifest_writer.writeheader()
        manifest_file.flush()

    results_path = build_dir / "resultados_organo_sweep.csv"
    results_fieldnames = ["especie", "fase", "field_T", "position_cm", "organo_id",
                           "edep_J", "dose_gy_run", "n_eventos"]
    results_mode = "a" if (args.resume and results_path.is_file()) else "w"
    results_file = open(results_path, results_mode, newline="")
    results_writer = csv.DictWriter(results_file, fieldnames=results_fieldnames)
    if results_mode == "w":
        results_writer.writeheader()
        results_file.flush()

    print(f"Corriendo {len(combos)} combinacion(es) (n_events={args.n_events}, field={FIELD_T} T) "
          f"con {binary_path.name} en {build_dir}")

    n_failed = 0
    n_skipped = 0
    for combo in combos:
        if combo["index"] in done_runs:
            n_skipped += 1
            continue

        seed1 = BASE_SEED + 2 * combo["index"]
        seed2 = seed1 + 1

        macro_path = generated_dir / f"organ_run_{combo['index']:03d}.mac"
        macro_path.write_text(MACRO_TEMPLATE.format(
            field_map=field_map, field_scale=f"{FIELD_T:.2f}",
            position_cm=f"{combo['position_cm']:.2f}",
            seed1=seed1, seed2=seed2,
            species=combo["species"], phase=combo["phase"],
            n_events=args.n_events,
        ))

        log_path = logs_dir / f"organ_run_{combo['index']:03d}.log"
        label = (f"[{combo['index']+1}/{len(combos)}] {combo['species']}/{combo['phase']} "
                 f"field={FIELD_T}T pos={combo['position_cm']}cm")
        print(label, end=" ... ", flush=True)

        out_path = build_dir / "ICRP110.out"
        out_path.unlink(missing_ok=True)  # nombre fijo, ver docstring del modulo

        start = time.monotonic()
        with open(log_path, "w") as logfile:
            result = subprocess.run(
                [str(binary_path), str(macro_path)],
                cwd=build_dir, stdout=logfile, stderr=subprocess.STDOUT, text=True,
            )
        duration_s = time.monotonic() - start

        archive_path = archive_dir / f"organ_run_{combo['index']:03d}.out"
        parsed_ok = False
        if result.returncode == 0 and out_path.is_file():
            out_path.rename(archive_path)
            try:
                rows = parse_icrp110_out(archive_path)
                for organ_id, edep_j, dose_gy in rows:
                    results_writer.writerow({
                        "especie": combo["species"], "fase": combo["phase"],
                        "field_T": FIELD_T, "position_cm": combo["position_cm"],
                        "organo_id": organ_id, "edep_J": edep_j, "dose_gy_run": dose_gy,
                        "n_eventos": args.n_events,
                    })
                results_file.flush()
                parsed_ok = True
            except ValueError as exc:
                print(f"\n  ADVERTENCIA: no se pudo parsear {archive_path}: {exc}")

        status = "OK" if (result.returncode == 0 and parsed_ok) else f"FALLO (exit {result.returncode})"
        if status != "OK":
            n_failed += 1
        print(f"{status} ({duration_s:.1f}s)")

        manifest_writer.writerow({
            "index": combo["index"], "especie": combo["species"], "fase": combo["phase"],
            "field_T": FIELD_T, "position_cm": combo["position_cm"],
            "n_events": args.n_events, "seed1": seed1, "seed2": seed2,
            "macro_path": str(macro_path),
            "exit_code": result.returncode if parsed_ok else (result.returncode or 1),
            "duration_s": round(duration_s, 2), "log_path": str(log_path),
            "out_archive_path": str(archive_path) if parsed_ok else "",
        })
        manifest_file.flush()

    manifest_file.close()
    results_file.close()

    print(f"\nListo: {len(combos) - n_skipped} corrida(s) nueva(s), {n_failed} fallida(s), "
          f"{n_skipped} ya completada(s) (saltadas).")
    print(f"Manifiesto: {manifest_path}")
    print(f"Resultados: {results_path}")
    if n_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
