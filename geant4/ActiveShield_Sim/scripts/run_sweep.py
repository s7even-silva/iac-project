#!/usr/bin/env python3
"""Lanzador del "segundo grupo de datos" de ActiveShield_Sim: 3 especies
(las mas peligrosas, con espectro OLTARIS real ya exportado) x 5
posiciones del fantoma = 15 corridas, con el campo del arreglo Halbach de
CREW HaT a su intensidad de diseno (~10 T de pico), calculando dosis
absorbida por organo (via el scorer original ICRP110, ya funcional).

A diferencia de GCR_SEP_Sim (binario propio `gcrsim` + SpectrumSampler.cc
+ CSV agregado por corrida), ActiveShield_Sim usa el binario de ejemplo
`ICRP110phantoms` + G4GeneralParticleSource (GPS) + el scorer por organo
original del ejemplo -- ver `spectrum_to_gps.py` para el puente CSV->GPS,
y `aggregate_organ_dose.py` para el post-procesamiento a dosis
equivalente. Mismo patron de manifiesto/resume/semillas que
`GCR_SEP_Sim/scripts/run_sweep.py`, adaptado a esta interfaz.

**Requisitos previos, ninguno automatizado por este script todavia:**
1. Compilar ActiveShield_Sim (ver README.md de ese proyecto).
2. Generar la geometria+campo del arreglo Halbach de 8 bobinas (si no
   existen ya en `field/generated/crewhat_halbach_array/`):

       cd field && source .venv/bin/activate
       python3 generate_ellipse_array.py examples/crewhat_halbach_array_pilot.json generated/crewhat_halbach_array
       python3 mesh_swept.py ...  # ver field/README.md para la secuencia completa
       python3 mesh_to_gdml.py ... generated/crewhat_halbach_array/halbach_array.gdml
       python3 compute_field_ellipse_array.py generated/crewhat_halbach_array/array_current_paths.json \\
           generated/crewhat_halbach_array/halbach_array.map --half-size 14 --spacing 0.5

   **El archivo .map del arreglo completo (campo) no existe todavia en
   este repo** (solo la geometria .gdml) -- confirmar con
   `ls field/generated/crewhat_halbach_array/*.map` antes de lanzar el
   barrido con el campo activado. Sin ese archivo, `/spacecraft/fieldMap`
   fallara.

**Riesgo operativo real, sin mitigar automaticamente:** a diferencia de
GCR_SEP_Sim, ActiveShield_Sim NO tiene G4UserLimits/StepLimiterPhysics
contra particulas atrapadas circulando en el campo (ver AGENTS.md,
"particulas atrapadas", y el comentario de
field/examples/import_crewhat_ellipse_field.mac). Este script aplica un
timeout de proceso (--timeout-s, default 600s) como red de seguridad,
pero un timeout no es lo mismo que arreglar la causa -- si muchas
corridas se cuelgan, revisar el rango de energias bajas del espectro
antes de asumir que es solo lentitud.

**No validado todavia (marcado explicitamente, no silenciado):**
- La conversion CSV->histograma GPS (`spectrum_to_gps.py`) no se ha
  comparado contra el muestreo de `SpectrumSampler.cc` de GCR_SEP_Sim.
- Las 5 posiciones default (0-4m) solo tienen confirmado sin solapamiento
  el caso de 2m (`tests/phantom_offset.mac`, seccion "head" no "full") --
  correr primero con --limit chico y revisar el log por errores de
  solapamiento antes del barrido completo.
- El campo real usado (fieldScale=1, ~10T de pico) es el "mayor campo de
  blindaje" pedido para este grupo -- no es un barrido de intensidad como
  en GCR_SEP_Sim, es un valor fijo.
"""
import argparse
import csv
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import sweep_config  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spectrum_to_gps import PRIORITY_SPECIES, gps_histogram_lines  # noqa: E402

# Posiciones del fantoma (m), via /spacecraft/phantomOffsetX -- nave a
# escala CREW HaT (shipRadius=4.5m). Solo 0m y 2m estan confirmados sin
# solapamiento (ver docstring del modulo); 3-4m se validan en la corrida
# misma (Geant4 aborta con overlap si no caben).
POSITIONS_M = [0.0, 1.0, 2.0, 3.0, 4.0]

BASE_SEED = sweep_config.BASE_SEED_ACTIVE_SHIELD_SIM

# Configuracion fija del campo/geometria de produccion para este grupo:
# arreglo Halbach de 8 bobinas de CREW HaT, patron dipolar K=1 (ver
# AGENTS.md), a su corriente de diseno (fieldScale=1 -> ~10T de pico).
SHIP_RADIUS_M = 4.5
WORLD_HALF_SIZE_M = 14.0
COIL_GEOMETRY = "../../../field/generated/crewhat_halbach_array/halbach_array.gdml"
FIELD_MAP = "../../../field/generated/crewhat_halbach_array/halbach_array.map"

MACRO_TEMPLATE = """\
/run/numberOfThreads 1
/spacecraft/worldHalfSize {world_half_size} m
/spacecraft/shipRadius {ship_radius} m
/spacecraft/coilGeometry {coil_geometry}
/spacecraft/fieldMap {field_map}
/spacecraft/fieldScale 1
/spacecraft/phantomOffsetX {offset_x} m
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full
/run/initialize
/random/setSeeds {seed1} {seed2}
{gps_lines}
/gps/pos/type Surface
/gps/pos/shape Sphere
/gps/pos/centre 0 0 0 m
/gps/pos/radius {source_radius} m
/gps/ang/type cos
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
    index = 0
    for label, csv_path, particle, mass_number in PRIORITY_SPECIES:
        for x_m in POSITIONS_M:
            combos.append({"index": index, "label": label, "csv_path": csv_path,
                            "particle": particle, "mass_number": mass_number, "x_m": x_m})
            index += 1
    return combos


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-dir", type=Path, default=None,
                         help="Directorio de build con ICRP110phantoms compilado (default: <proyecto>/build)")
    parser.add_argument("--n-events", type=int, default=1000,
                         help="Eventos por corrida (default 1000, igual que male.in -- ActiveShield_Sim "
                              "transporta en un fantoma vóxel completo + mapa de campo real, mucho mas "
                              "lento por evento que GCR_SEP_Sim; medir con --limit 1 antes de subir esto)")
    parser.add_argument("--timeout-s", type=int, default=600,
                         help="Timeout por corrida en segundos (red de seguridad contra particulas "
                              "atrapadas -- ActiveShield_Sim no tiene StepLimiterPhysics, ver docstring)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Solo correr las primeras N combinaciones (piloto rapido)")
    parser.add_argument("--no-resume", dest="resume", action="store_false", default=True,
                         help="Desactivar resume (activado por defecto)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    build_dir = (args.build_dir or (project_root / "build")).resolve()
    binary_path = build_dir / "ICRP110phantoms"

    if not binary_path.is_file():
        sys.exit(f"ERROR: no se encontro {binary_path}. Compila ActiveShield_Sim primero (ver README.md).")

    field_map_path = (build_dir / FIELD_MAP).resolve()
    coil_geometry_path = (build_dir / COIL_GEOMETRY).resolve()
    if not coil_geometry_path.is_file():
        sys.exit(f"ERROR: no se encontro {coil_geometry_path}. Genera el arreglo Halbach primero "
                  "(ver docstring de este script / field/README.md).")
    if not field_map_path.is_file():
        sys.exit(f"ERROR: no se encontro {field_map_path}. Falta correr compute_field_ellipse_array.py "
                  "sobre array_current_paths.json para generar el .map del arreglo completo "
                  "(ver docstring de este script) -- todavia no se ha generado en este repo.")

    generated_dir = build_dir / "macros" / "generated_activeshield"
    logs_dir = build_dir / "logs_activeshield"
    organ_dose_dir = build_dir / "organ_dose"
    for d in (generated_dir, logs_dir, organ_dose_dir):
        d.mkdir(parents=True, exist_ok=True)

    combos = build_combinations()
    if args.limit is not None:
        combos = combos[:args.limit]

    manifest_path = build_dir / "activeshield_manifest.csv"
    manifest_fieldnames = ["index", "especie", "particle", "astronaut_x_m", "n_events",
                            "seed1", "seed2", "macro_path", "organ_dose_path", "exit_code",
                            "duration_s", "log_path"]

    done_runs = set()
    if args.resume and manifest_path.is_file():
        with open(manifest_path, newline="") as f:
            for row in csv.DictReader(f):
                if row["exit_code"] == "0":
                    done_runs.add(int(row["index"]))
        print(f"resume: {len(done_runs)} corrida(s) ya completada(s) en {manifest_path}, se saltaran "
              "(usar --no-resume para rehacerlas).")

    manifest_mode = "a" if (args.resume and manifest_path.is_file()) else "w"
    manifest_file = open(manifest_path, manifest_mode, newline="")
    manifest_writer = csv.DictWriter(manifest_file, fieldnames=manifest_fieldnames)
    if manifest_mode == "w":
        manifest_writer.writeheader()
        manifest_file.flush()

    print(f"Corriendo {len(combos)} combinaciones (n_events={args.n_events}) con ICRP110phantoms en {build_dir}")
    print("ADVERTENCIA: sin piloto de tiempo previo con esta geometria+campo, el costo por corrida es "
          "desconocido -- si esto es la primera vez, usar --limit 1 antes de lanzar todo.")

    n_failed = 0
    n_timeout = 0
    n_skipped = 0
    source_radius = WORLD_HALF_SIZE_M - 1.0

    for run_n, combo in enumerate(combos, start=1):
        if combo["index"] in done_runs:
            n_skipped += 1
            continue

        seed1 = BASE_SEED + 2 * combo["index"]
        seed2 = seed1 + 1
        gps_lines = "\n".join(gps_histogram_lines(combo["csv_path"], combo["mass_number"], combo["particle"]))

        macro_path = generated_dir / f"run_{combo['index']:04d}_{combo['label']}.mac"
        macro_path.write_text(MACRO_TEMPLATE.format(
            world_half_size=WORLD_HALF_SIZE_M, ship_radius=SHIP_RADIUS_M,
            coil_geometry=COIL_GEOMETRY, field_map=FIELD_MAP,
            offset_x=f"{combo['x_m']:.2f}", seed1=seed1, seed2=seed2,
            gps_lines=gps_lines, source_radius=source_radius, n_events=args.n_events,
        ))

        log_path = logs_dir / f"run_{combo['index']:04d}.log"
        label = f"[{run_n}/{len(combos)}] idx={combo['index']} {combo['label']} x={combo['x_m']}m"
        print(label, end=" ... ", flush=True)

        out_file = build_dir / "ICRP110.out"
        out_file.unlink(missing_ok=True)

        start = time.monotonic()
        exit_code = None
        try:
            with open(log_path, "w") as logfile:
                result = subprocess.run(
                    [str(binary_path), str(macro_path)],
                    cwd=build_dir, stdout=logfile, stderr=subprocess.STDOUT, text=True,
                    timeout=args.timeout_s,
                )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = -1
            n_timeout += 1
        duration_s = time.monotonic() - start

        organ_dose_path = ""
        if exit_code == 0 and out_file.is_file():
            organ_dose_path = organ_dose_dir / f"run_{combo['index']:04d}_{combo['label']}_x{combo['x_m']}.out"
            shutil.move(str(out_file), str(organ_dose_path))
        elif exit_code == 0:
            print("(sin ICRP110.out pese a exit 0 -- revisar el log)", end=" ")

        status = {0: "OK", -1: f"TIMEOUT (>{args.timeout_s}s)"}.get(exit_code, f"FALLO (exit {exit_code})")
        if exit_code not in (0, -1) :
            n_failed += 1
        print(f"{status} ({duration_s:.1f}s)")

        manifest_writer.writerow({
            "index": combo["index"], "especie": combo["label"], "particle": combo["particle"],
            "astronaut_x_m": combo["x_m"], "n_events": args.n_events,
            "seed1": seed1, "seed2": seed2, "macro_path": str(macro_path),
            "organ_dose_path": str(organ_dose_path), "exit_code": exit_code,
            "duration_s": round(duration_s, 2), "log_path": str(log_path),
        })
        manifest_file.flush()

    manifest_file.close()

    print(f"\nListo: {len(combos) - n_skipped} corridas nuevas, {n_failed} fallidas, "
          f"{n_timeout} con timeout, {n_skipped} ya completadas (saltadas).")
    print(f"Manifiesto: {manifest_path}")
    print(f"Dosis por organo (una por corrida): {organ_dose_dir}")
    if n_failed or n_timeout:
        sys.exit(1)


if __name__ == "__main__":
    main()
