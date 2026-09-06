#!/usr/bin/env python3
"""Corre el barrido completo de GCR_SEP_Sim: modelo x fase solar x campo x posicion.

Genera una macro por combinacion, ejecuta el binario `gcrsim` compilado de
forma secuencial (evita condiciones de carrera al escribir el CSV de salida),
inyecta semillas aleatorias deterministicas por corrida (el codigo no fija
semilla por si solo) y deja un manifiesto + logs para revisar despues.

Uso:
    python3 run_sweep.py                        # barrido completo (140 corridas)
    python3 run_sweep.py --n-events 100 --limit 4   # corrida piloto rapida
    python3 run_sweep.py --build-dir ../build   # si el build no esta en ../build
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
    combos = []
    for (model, phase), field_t, x_m in itertools.product(MODEL_PHASES, FIELD_VALUES_T, POSITIONS_M):
        combos.append({"model": model, "phase": phase, "field_t": field_t, "x_m": x_m})
    return combos


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-dir", type=Path, default=None,
                         help="Directorio de build con el binario gcrsim compilado (default: <repo>/build)")
    parser.add_argument("--n-events", type=int, default=10000,
                         help="Eventos por corrida (/run/beamOn), default 10000")
    parser.add_argument("--limit", type=int, default=None,
                         help="Solo correr las primeras N combinaciones (para pilotos rapidos)")
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
    if args.limit is not None:
        combos = combos[:args.limit]

    manifest_path = build_dir / "sweep_manifest.csv"
    manifest_rows = []

    print(f"Corriendo {len(combos)} combinaciones (n_events={args.n_events}) con gcrsim en {build_dir}")

    n_failed = 0
    for i, combo in enumerate(combos):
        seed1 = BASE_SEED + 2 * i
        seed2 = BASE_SEED + 2 * i + 1
        x_cm = combo["x_m"] * 100.0

        macro_path = generated_dir / f"run_{i:04d}.mac"
        macro_path.write_text(MACRO_TEMPLATE.format(
            seed1=seed1, seed2=seed2,
            field_t=f"{combo['field_t']:.2f}",
            x_cm=f"{x_cm:.2f}",
            model=combo["model"], phase=combo["phase"],
            n_events=args.n_events,
        ))

        log_path = logs_dir / f"run_{i:04d}.log"
        label = f"[{i+1}/{len(combos)}] {combo['model']}/{combo['phase']} field={combo['field_t']}T x={combo['x_m']}m"
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

        manifest_rows.append({
            "index": i, "modelo": combo["model"], "fase": combo["phase"],
            "field_T": combo["field_t"], "astronaut_x_m": combo["x_m"],
            "n_events": args.n_events, "seed1": seed1, "seed2": seed2,
            "macro_path": str(macro_path), "exit_code": result.returncode,
            "duration_s": round(duration_s, 2), "log_path": str(log_path),
        })

    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\nListo: {len(combos)} corridas, {n_failed} fallidas.")
    print(f"Manifiesto: {manifest_path}")
    print(f"Resultados: {build_dir / 'resultados_dosis_sweep.csv'}")
    if n_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
