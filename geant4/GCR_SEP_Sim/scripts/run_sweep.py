#!/usr/bin/env python3
"""Corre el barrido de GCR_SEP_Sim: modelo x fase solar x campo x posicion.

Genera una macro por corrida, ejecuta el binario `gcrsim` compilado de forma
secuencial (evita condiciones de carrera al escribir el CSV de salida),
inyecta semillas aleatorias deterministicas por corrida y repeticion (el
codigo no fija semilla por si solo) y deja un manifiesto + logs para revisar
despues.

Cada una de las 140 combinaciones (4 modelo x fase, 7 campos, 5 posiciones)
tiene un indice global fijo (0-139), asignado ANTES de aplicar --only-model.
Esto es importante para el trabajo en equipo: si cada persona corre un
--only-model distinto, sus semillas y nombres de archivo nunca chocan aunque
despues junten los resultados en una misma carpeta (ver README.md).

Uso:
    python3 run_sweep.py                                # barrido completo (140 combos x 1 repeticion)
    python3 run_sweep.py --n-events 100 --limit 4        # piloto rapido
    python3 run_sweep.py --only-model GCR --repeats 5    # trabajo repartido en equipo, con estadistica
    python3 run_sweep.py --build-dir ../build            # si el build no esta en ../build
    python3 run_sweep.py --only-model GCR --repeats 5 --resume   # retomar un barrido cortado a medias

--resume: si el proceso se corta a la mitad (Ctrl+C, corte de luz, se cierra
la sesion SSH sin tmux, etc.), las corridas ya completadas con exito NO se
pierden -- el binario gcrsim hace append a resultados_dosis_sweep.csv corrida
por corrida, y este script hace lo mismo con sweep_manifest.csv. Al relanzar
el mismo comando con --resume, se lee el manifiesto existente y se saltan las
combinaciones (index, repeticion) que ya tengan una corrida con exit_code 0;
todo lo demas (incluidas las que fallaron) se vuelve a correr. Sin --resume,
el manifiesto se reinicia desde cero y las corridas viejas de un barrido
anterior con los mismos parametros quedarian duplicadas en el CSV de
resultados -- usar --resume precisamente para evitar eso.
"""
import argparse
import csv
import itertools
import subprocess
import sys
import time
from pathlib import Path

MODEL_PHASES = [("GCR", "max"), ("GCR", "min"), ("SEP", "max"), ("SEP", "min")]
FIELD_VALUES_T = [7.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]
POSITIONS_M = [0.0, 0.7, 1.4, 2.1, 2.8]

BASE_SEED = 20260905  # fecha del pivote de metodologia, solo para tener un valor fijo

MACRO_TEMPLATE = """\
/run/initialize
/random/setSeeds {seed1} {seed2}
/detector/shield false
/detector/field true
/detector/fieldValue {field_t}
/detector/hullThicknessCm 0.3
/detector/astronautX {x_cm}
/gun/model {model}
/gun/phase {phase}
/gun/dirMode isotropic
/run/beamOn {n_events}
"""


def build_combinations():
    """Las 140 combinaciones con su indice global (0-139), fijo sin importar
    ningun filtro que se aplique despues (--only-model, --limit)."""
    combos = []
    for index, ((model, phase), field_t, x_m) in enumerate(
        itertools.product(MODEL_PHASES, FIELD_VALUES_T, POSITIONS_M)
    ):
        combos.append({"index": index, "model": model, "phase": phase, "field_t": field_t, "x_m": x_m})
    return combos


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-dir", type=Path, default=None,
                         help="Directorio de build con el binario gcrsim compilado (default: <repo>/build)")
    parser.add_argument("--n-events", type=int, default=10000,
                         help="Eventos por corrida (/run/beamOn), default 10000")
    parser.add_argument("--repeats", type=int, default=1,
                         help="Repeticiones por combinacion, con semillas distintas (default 1; usar 5 para estadistica del articulo)")
    parser.add_argument("--only-model", choices=["GCR", "SEP"], default=None,
                         help="Solo correr las 70 combinaciones de este modelo (para repartir el barrido en equipo)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Solo correr las primeras N combinaciones ya filtradas (para pilotos rapidos)")
    parser.add_argument("--resume", action="store_true",
                         help="Saltar (index, repeticion) que ya aparecen exitosas (exit_code 0) en sweep_manifest.csv, "
                              "para retomar un barrido que se corto a la mitad sin duplicar corridas")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    build_dir = (args.build_dir or (project_root / "build")).resolve()
    gcrsim_path = build_dir / "gcrsim"

    if not gcrsim_path.is_file():
        sys.exit(f"ERROR: no se encontro {gcrsim_path}. Compila el proyecto primero (ver README.md / CLAUDE.md).")

    generated_dir = build_dir / "macros" / "generated"
    logs_dir = build_dir / "logs"
    generated_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    combos = build_combinations()
    if args.only_model is not None:
        combos = [c for c in combos if c["model"] == args.only_model]
    if args.limit is not None:
        combos = combos[:args.limit]

    manifest_path = build_dir / "sweep_manifest.csv"
    manifest_fieldnames = ["index", "repeticion", "modelo", "fase", "field_T", "astronaut_x_m",
                            "n_events", "seed1", "seed2", "macro_path", "exit_code",
                            "duration_s", "log_path"]

    done_runs = set()
    if args.resume and manifest_path.is_file():
        with open(manifest_path, newline="") as f:
            for row in csv.DictReader(f):
                if row["exit_code"] == "0":
                    done_runs.add((int(row["index"]), int(row["repeticion"])))
        print(f"--resume: {len(done_runs)} corrida(s) ya completada(s) en {manifest_path}, se saltaran.")

    # Modo de apertura del manifiesto: "a" (append) si se retoma sobre uno
    # existente, "w" (nuevo) en cualquier otro caso -- incluido --resume sin
    # manifiesto previo, donde igual hay que escribir el encabezado.
    manifest_mode = "a" if (args.resume and manifest_path.is_file()) else "w"
    manifest_file = open(manifest_path, manifest_mode, newline="")
    manifest_writer = csv.DictWriter(manifest_file, fieldnames=manifest_fieldnames)
    if manifest_mode == "w":
        manifest_writer.writeheader()
        manifest_file.flush()

    total_runs = len(combos) * args.repeats
    print(f"Corriendo {len(combos)} combinaciones x {args.repeats} repeticion(es) = {total_runs} corridas "
          f"(n_events={args.n_events}) con gcrsim en {build_dir}")

    n_failed = 0
    n_skipped = 0
    run_n = 0
    for combo in combos:
        for rep in range(args.repeats):
            run_n += 1
            if (combo["index"], rep) in done_runs:
                n_skipped += 1
                continue
            seed1 = BASE_SEED + 1000 * rep + 2 * combo["index"]
            seed2 = seed1 + 1
            x_cm = combo["x_m"] * 100.0

            macro_path = generated_dir / f"run_{combo['index']:04d}_r{rep:02d}.mac"
            macro_path.write_text(MACRO_TEMPLATE.format(
                seed1=seed1, seed2=seed2,
                field_t=f"{combo['field_t']:.2f}",
                x_cm=f"{x_cm:.2f}",
                model=combo["model"], phase=combo["phase"],
                n_events=args.n_events,
            ))

            log_path = logs_dir / f"run_{combo['index']:04d}_r{rep:02d}.log"
            label = (f"[{run_n}/{total_runs}] idx={combo['index']} rep={rep} "
                     f"{combo['model']}/{combo['phase']} field={combo['field_t']}T x={combo['x_m']}m")
            print(label, end=" ... ", flush=True)

            start = time.monotonic()
            with open(log_path, "w") as logfile:
                result = subprocess.run(
                    [str(gcrsim_path), str(macro_path)],
                    cwd=build_dir, stdout=logfile, stderr=subprocess.STDOUT, text=True,
                )
            duration_s = time.monotonic() - start

            status = "OK" if result.returncode == 0 else f"FALLO (exit {result.returncode})"
            if result.returncode != 0:
                n_failed += 1
            print(f"{status} ({duration_s:.1f}s)")

            manifest_writer.writerow({
                "index": combo["index"], "repeticion": rep,
                "modelo": combo["model"], "fase": combo["phase"],
                "field_T": combo["field_t"], "astronaut_x_m": combo["x_m"],
                "n_events": args.n_events, "seed1": seed1, "seed2": seed2,
                "macro_path": str(macro_path), "exit_code": result.returncode,
                "duration_s": round(duration_s, 2), "log_path": str(log_path),
            })
            manifest_file.flush()

    manifest_file.close()

    print(f"\nListo: {total_runs - n_skipped} corridas nuevas, {n_failed} fallidas, {n_skipped} saltadas por --resume.")
    print(f"Manifiesto: {manifest_path}")
    print(f"Resultados: {build_dir / 'resultados_dosis_sweep.csv'}")
    if n_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
