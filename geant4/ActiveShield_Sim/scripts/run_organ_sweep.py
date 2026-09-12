#!/usr/bin/env python3
"""Corre el barrido de dosis por organo en ActiveShield_Sim con BINS de
energia monoenergeticos (3 especies en su fase mas peligrosa x 8 bins de
energia x 5 posiciones radiales del fantoma = 120 corridas), con el campo
magnetico FIJO al maximo del arreglo Halbach de 8 bobinas de CREW HaT
(diseno NIAC, corriente de diseno 1e7 A por bobina -- ver AGENTS.md,
seccion ActiveShield_Sim / analisis de riesgo estocastico).

Tercera revision de esta tarea (2026-09-11), corrige un error real de las
dos versiones anteriores: usaban `SpectrumSampler` para MUESTREAR el
espectro continuo (mismo metodo que GCR_SEP_Sim), pero AGENTS.md ya tenia
registrada la decision de equipo de usar **bins de energia + reponderacion**
para la produccion de ActiveShield_Sim, explicitamente **"no portar
muestreo continuo como plan de produccion"** -- un descuido, no una
decision consciente de reemplazarla. Esta version sigue esa decision:

- Cada corrida es monoenergetica: `/gun/fixedEnergyMeV <valor>` fuerza la
  MISMA energia en todos los primarios de la corrida (ver
  ICRP110PhantomPrimaryGeneratorAction.hh), en vez de dejar que
  `SpectrumSampler` muestree el espectro real.
- `energy_bins.py` calcula, para cada especie, 8 bins log-espaciados
  (decision 2026-09-11, ver AGENTS.md) dentro del rango de energia que
  cubre >99.9% del flujo/fluencia real de OLTARIS (no el rango tabulado
  completo, que tiene 8 decadas y colas irrelevantes) y el peso fisico de
  cada bin (cuantos primarios reales de esa franja cruzan la esfera
  fuente) -- ver ese modulo para el detalle y la justificacion del rango.
- `aggregate_organ_doses.py` combina TODOS los (especie, bin) con su propio
  peso, en vez de un solo peso por especie -- mismo principio matematico
  que antes (`D = suma W[clave]*R[clave]`), solo con mas terminos en la suma.

Esto multiplica el conteo de corridas por el numero de bins/especie (8x mas
que la version anterior de 15 corridas) -- una tension real y reconocida con
"menos combinaciones y menos tiempo": la resolucion de bins se decidio
sacrificando parte de esa velocidad para seguir la decision ya tomada del
equipo, no accidentalmente. Ver AGENTS.md para la tabla de opciones de
bins/eventos evaluadas antes de fijar 8 bins.

Ademas (2026-09-11, ver AGENTS.md): campo real del arreglo de 8 bobinas de
CREW HaT (no un campo sintetico), a su corriente de diseno maxima (sin
escalar); posicion del fantoma RADIAL en el plano XY
(`/spacecraft/phantomOffsetX`, Y fijo en 0) en vez de a lo largo del eje Z
-- el campo real de Bryam varia principalmente radial/azimutalmente
respecto al anillo de bobinas; nave a escala real de CREW HaT
(`shipRadius=4.5m`, `shipHalfLength=5m` -- este segundo valor es supuesto
propio del equipo, ninguna fuente da la longitud axial).

Cada corrida es de UNA sola especie Y UN SOLO bin de energia
(ICRP110UserScoreWriter no distingue nada dentro de una misma corrida --
combinar todo con sus pesos fisicos se hace despues en Python, ver
aggregate_organ_doses.py). ICRP110UserScoreWriter siempre escribe su salida
en un archivo de nombre FIJO ("ICRP110.out", sin importar el nombre que se
le de a /score/dumpQuantityToFile) -- por eso las corridas son secuenciales
(subprocess.run una por una) y cada ICRP110.out se archiva con un nombre
unico inmediatamente despues de cada corrida, antes de lanzar la siguiente.

Requiere:
- ActiveShield_Sim ya compilado (ver README.md / AGENTS.md).
- El GDML solido de las 8 bobinas y su .map de campo Elmer FEM a escala
  real ya generados (entorno field/.venv, NO geant4_env -- este script no
  los genera). --field-map/--coil-geometry ya traen el default correcto
  (build/crewhat_elmer_fullscale.map, field/generated/crewhat_halbach_array/
  halbach_array.gdml) si ya los generaste siguiendo AGENTS.md ("Error de
  campo vs. error de dosis en Elmer, y extension a escala real"). Para
  comparar contra el Biot-Savart anterior (ya no el default, ver ahi por
  que): --field-map ../build/crewhat_niac_max.map.

Uso:
    python3 run_organ_sweep.py
    python3 run_organ_sweep.py --n-events 100 --limit 2  # piloto
    python3 run_organ_sweep.py --no-resume
    # Repartir en equipo (60/40 EXACTO por corridas, por posicion completa --
    # cada posicion trae sus 24 combinaciones de especie x bin, 5 posiciones
    # x 24 = 120):
    python3 run_organ_sweep.py --only-positions 2,3,4  # 72 corridas (60%)
    python3 run_organ_sweep.py --only-positions 0,1    # 48 corridas (40%)
    # Con repeticiones para media/std/IC95% (ver aggregate_organ_doses.py) --
    # multiplica el total: 120 x 5 = 600 corridas.
    python3 run_organ_sweep.py --repeats 5

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
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import sweep_config  # noqa: E402 -- constantes compartidas entre proyectos, ver geant4/sweep_config.py
import energy_bins  # noqa: E402

# Escenario fijo (decision 2026-09-11, ver AGENTS.md): NO cambiar a una lista
# con mas posiciones/especies/bins sin revisarlo antes.
SHIP_RADIUS_M = 4.5      # escala real de CREW HaT (NIAC, diametro Starship)
SHIP_HALF_LENGTH_M = 5.0  # supuesto propio, ninguna fuente da la longitud axial
WORLD_HALF_SIZE_M = 14.0  # encierra el arreglo (halbach_radius=8m) + margen, mismo valor que import_crewhat_halbach_array.mac
# Geometria SOLIDA de las 8 bobinas (material HTS real, no solo su campo) --
# decision de equipo (AGENTS.md, "Mantener material de devanados, soportes y
# crioestato en el modelo final: la contribucion pasiva y los secundarios
# pueden aumentar o reducir dosis") -- sin esto, la corrida solo ve el EFECTO
# del campo sobre trayectorias, nunca las bobinas como blindaje/fuente de
# secundarios. Mismo array_current_paths.json (mismas corrientes/posiciones,
# solo ruido de punto flotante ~1e-15 entre generaciones) que compute_field_
# ellipse_array.py uso para generar el .map de produccion -- geometria y
# campo son consistentes entre si.
DEFAULT_COIL_GEOMETRY = (Path(__file__).resolve().parent.parent.parent.parent
                          / "field" / "generated" / "crewhat_halbach_array" / "halbach_array.gdml")
# Elmer FEM a escala real de nave, no Biot-Savart -- decision de equipo
# 2026-09-11 (ver AGENTS.md, "Error de campo vs. error de dosis en Elmer, y
# extension a escala real"): Biot-Savart trata cada bobina como un filamento
# con nucleo de regularizacion de 6,7cm, mucho menor que el winding pack
# real (~1,4m); la region de la nave (radio 4,5-6,9m) no esta lo bastante
# lejos del arreglo (radio Halbach 8m) para que esa aproximacion sea buena
# ahi. Medido: Biot-Savart da 36-48% MAS dosis que Elmer en la misma
# configuracion (una sola semilla, no una validacion estadistica cerrada
# todavia) -- Elmer resuelve la distribucion de corriente real sobre la
# seccion del conductor, Biot-Savart no. build/crewhat_niac_max.map
# (Biot-Savart) se conserva en disco para comparacion, ya no es el default.
DEFAULT_FIELD_MAP = (Path(__file__).resolve().parent.parent.parent.parent / "build" / "crewhat_elmer_fullscale.map")
# Radial en XY; Y fijo en 0 (ver docstring). Interior de la nave es
# shipRadius(4.5m)-hullThickness(1.5cm) menos el medio-ancho del fantoma en
# X (~0.271m) = margen seguro ~4.2m; 4.0m ya se probo sin solapamientos.
OFFSET_X_VALUES_M = [0.0, 1.0, 2.0, 3.0, 4.0]
SPECIES_PHASE = {"GCR_H": "min", "GCR_He": "min", "SEP_p": "max"}

BASE_SEED = sweep_config.BASE_SEED_ACTIVE_SHIELD_SIM

MACRO_TEMPLATE = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full

/spacecraft/shipRadius {ship_radius_m} m
/spacecraft/shipHalfLength {ship_half_length_m} m
/spacecraft/worldHalfSize {world_half_size_m} m
{coil_geometry_line}/spacecraft/fieldMap {field_map}
/spacecraft/fieldScale 1.0
/spacecraft/phantomOffsetX {offset_x_m} m
/spacecraft/phantomOffsetY 0 m

/run/numberOfThreads {n_threads}
/run/initialize
/random/setSeeds {seed1} {seed2}

/control/verbose 1
/tracking/verbose 0
/run/verbose 0
/event/verbose 0

/gun/species {species}
/gun/phase {phase}
/gun/fixedEnergyMeV {energy_mev}

/score/create/boxMesh PhantomMesh
/score/mesh/boxSize 271.399 135.6995 888. mm
/score/mesh/nBin 254 127 222
/score/mesh/translate/xyz 0. 0. 0. mm
/score/quantity/energyDeposit energyDeposit
/score/close

/run/beamOn {n_events}

/score/dumpQuantityToFile PhantomMesh energyDeposit PhantomMesh_Edep.txt
"""


def build_combinations(spectra_dir):
    bins_by_species = energy_bins.build_bins(spectra_dir)
    combos = []
    index = 0
    for species, phase in SPECIES_PHASE.items():
        for bin_index, energy_rep, flux_bin in bins_by_species[species]:
            for offset_x_m in OFFSET_X_VALUES_M:
                combos.append({
                    "index": index, "species": species, "phase": phase,
                    "bin_index": bin_index, "energy_mev": energy_rep, "flux_bin": flux_bin,
                    "offset_x_m": offset_x_m,
                })
                index += 1
    return combos


def parse_icrp110_out(out_path):
    """Extrae (organ_id, edep_J, dose_Gy) de la tabla "para TODOS los
    organos" de ICRP110.out (incluye IDs con edep 0, en orden estrictamente
    creciente de ID). Se usa esta tabla -- no la de "solo organos con edep
    != 0" que aparece antes en el mismo archivo -- porque da un valor por ID
    sin depender de alinear posicionalmente esa otra tabla con la lista de
    nombres de organo que le sigue. El mapeo ID->nombre se hace aparte, en
    aggregate_organ_doses.py, leyendo ICRPdata/.../AM_organs.dat directamente.
    Formato exacto parseado aqui: ver ICRP110UserScoreWriter.cc, seccion
    final ("OrganID | Edep Dose", todos los IDs 0..NOrganIDs-1).
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
    parser.add_argument("--field-map", type=Path, default=DEFAULT_FIELD_MAP,
                         help="Ruta al .map del arreglo de 8 bobinas. Default (2026-09-11): el FEM de Elmer a "
                              "escala real (build/crewhat_elmer_fullscale.map), no Biot-Savart -- ver AGENTS.md "
                              "para por que. Pasar build/crewhat_niac_max.map explicitamente para comparar "
                              "contra el Biot-Savart anterior.")
    parser.add_argument("--coil-geometry", type=Path, default=DEFAULT_COIL_GEOMETRY,
                         help="GDML solido de las 8 bobinas (default: field/generated/crewhat_halbach_array/"
                              "halbach_array.gdml)")
    parser.add_argument("--no-coil-geometry", action="store_true",
                         help="Omitir /spacecraft/coilGeometry -- solo el efecto del campo sobre trayectorias, "
                              "sin masa/secundarios de las bobinas. NO es el comportamiento de produccion "
                              "(ver AGENTS.md, 'Mantener material de devanados...'); usar solo para comparar.")
    parser.add_argument("--build-dir", type=Path, default=None,
                         help="Directorio de build con ICRP110phantoms compilado (default: <repo>/build)")
    parser.add_argument("--n-events", type=int, default=sweep_config.DEFAULT_N_EVENTS,
                         help=f"Eventos por corrida, default {sweep_config.DEFAULT_N_EVENTS}")
    parser.add_argument("--threads", type=int, default=os.cpu_count(),
                         help="Hilos de Geant4 MT por corrida via /run/numberOfThreads (default: todos los "
                              "nucleos detectados -- antes de este flag, el binario usaba el default de 4 "
                              "hardcodeado en ICRP110phantoms.cc, nunca sobreescrito aqui). Verificado "
                              "(2026-09-11) que el scorer por organo funde correctamente entre hilos: dosis "
                              "identica bit a bit entre 1/4/14 hilos, ~25-90%% mas rapido segun eventos/corrida.")
    parser.add_argument("--only-positions", type=str, default=None,
                         help="Lista separada por comas de offset_x_m a correr, ej. '2,3,4' -- para repartir "
                              "el barrido en equipo (mismo principio que --only-model de GCR_SEP_Sim/run_sweep.py: "
                              "el indice global de cada corrida se asigna ANTES de filtrar, asi que las semillas "
                              "no cambian sin importar como se reparta). Ej.: 3 posiciones (72 de 120 corridas, "
                              "60%%) para una maquina mas rapida, las otras 2 (48 corridas, 40%%) para la otra.")
    parser.add_argument("--limit", type=int, default=None,
                         help="Solo correr las primeras N combinaciones ya filtradas (piloto)")
    parser.add_argument("--repeats", type=int, default=1,
                         help="Repeticiones por combinacion, con semillas distintas (default 1 -- para "
                              "pilotos; usar mas para poder calcular media/std/IC95%% en aggregate_organ_doses.py, "
                              "mismo principio que --repeats de GCR_SEP_Sim/run_sweep.py). N repeticiones "
                              "multiplica el total de corridas por N (ej. 120 combos x 5 = 600).")
    parser.add_argument("--no-resume", dest="resume", action="store_false", default=True,
                         help="Rehacer desde cero incluso las corridas ya exitosas (exit_code 0)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    build_dir = (args.build_dir or (project_root / "build")).resolve()
    binary_path = build_dir / "ICRP110phantoms"
    field_map = args.field_map.resolve()
    coil_geometry = None if args.no_coil_geometry else args.coil_geometry.resolve()

    if not binary_path.is_file():
        sys.exit(f"ERROR: no se encontro {binary_path}. Compila ActiveShield_Sim primero (ver README.md).")
    if not field_map.is_file():
        sys.exit(f"ERROR: no se encontro {field_map}. Generalo con field/generate_ellipse_array.py + "
                  "field/compute_field_ellipse_array.py primero (entorno field/.venv, no geant4_env -- "
                  "ver docstring de este script).")
    if coil_geometry is not None and not coil_geometry.is_file():
        sys.exit(f"ERROR: no se encontro {coil_geometry}. Generalo con field/generate_ellipse_array.py + "
                  "field/mesh_swept.py + field/mesh_to_gdml.py, o pasa --no-coil-geometry para omitirlo "
                  "(no es el comportamiento de produccion, ver AGENTS.md).")

    generated_dir = build_dir / "macros" / "generated_organ"
    logs_dir = build_dir / "logs_organ"
    archive_dir = build_dir / "organ_out_archive"
    generated_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    spectra_dir = project_root / "data" / "sources" / "oltaris"  # fuente de verdad versionada, no build_dir/data
    combos = build_combinations(spectra_dir)
    if args.only_positions is not None:
        wanted = {float(x) for x in args.only_positions.split(",")}
        combos = [c for c in combos if c["offset_x_m"] in wanted]
    if args.limit is not None:
        combos = combos[:args.limit]

    manifest_path = build_dir / "organ_sweep_manifest.csv"
    manifest_fieldnames = ["index", "repeticion", "especie", "fase", "bin_index", "energy_mev", "offset_x_m",
                            "n_events", "seed1", "seed2", "macro_path", "exit_code",
                            "duration_s", "log_path", "out_archive_path"]

    done_runs = set()
    if args.resume and manifest_path.is_file():
        with open(manifest_path, newline="") as f:
            for row in csv.DictReader(f):
                if row["exit_code"] == "0":
                    done_runs.add((int(row["index"]), int(row["repeticion"])))
        print(f"resume: {len(done_runs)} corrida(s) ya completada(s), se saltaran (--no-resume para rehacerlas).")

    manifest_mode = "a" if (args.resume and manifest_path.is_file()) else "w"
    manifest_file = open(manifest_path, manifest_mode, newline="")
    manifest_writer = csv.DictWriter(manifest_file, fieldnames=manifest_fieldnames)
    if manifest_mode == "w":
        manifest_writer.writeheader()
        manifest_file.flush()

    results_path = build_dir / "resultados_organo_sweep.csv"
    results_fieldnames = ["especie", "fase", "bin_index", "energy_mev", "offset_x_m", "repeticion",
                           "organo_id", "edep_J", "dose_gy_run", "n_eventos"]
    results_mode = "a" if (args.resume and results_path.is_file()) else "w"
    results_file = open(results_path, results_mode, newline="")
    results_writer = csv.DictWriter(results_file, fieldnames=results_fieldnames)
    if results_mode == "w":
        results_writer.writeheader()
        results_file.flush()

    total_runs = len(combos) * args.repeats
    print(f"Corriendo {len(combos)} combinacion(es) x {args.repeats} repeticion(es) = {total_runs} corridas "
          f"(n_events={args.n_events}, campo=NIAC max fijo) con {binary_path.name} en {build_dir}")

    n_failed = 0
    n_skipped = 0
    run_n = 0
    # Orden repeticion-mayor (todas las combinaciones de rep=0 antes que
    # cualquiera de rep=1): con --repeats>1, esto da un primer resultado
    # completo y usable (las 120 combinaciones con 1 repeticion) mucho antes
    # que terminar todo el barrido, en vez de tener 120 combinaciones a
    # medio terminar durante la mayor parte de la corrida. El resume por
    # (index, repeticion) no depende del orden de iteracion, asi que esto
    # no cambia que combinaciones quedan pendientes si se corta a la mitad.
    for rep in range(args.repeats):
        for combo in combos:
            run_n += 1
            if (combo["index"], rep) in done_runs:
                n_skipped += 1
                continue

            seed1 = BASE_SEED + 1000 * rep + 2 * combo["index"]
            seed2 = seed1 + 1

            macro_path = generated_dir / f"organ_run_{combo['index']:03d}_r{rep:02d}.mac"
            coil_geometry_line = f"/spacecraft/coilGeometry {coil_geometry}\n" if coil_geometry is not None else ""
            macro_path.write_text(MACRO_TEMPLATE.format(
                ship_radius_m=SHIP_RADIUS_M, ship_half_length_m=SHIP_HALF_LENGTH_M,
                world_half_size_m=WORLD_HALF_SIZE_M, coil_geometry_line=coil_geometry_line,
                field_map=field_map, offset_x_m=f"{combo['offset_x_m']:.3f}",
                seed1=seed1, seed2=seed2,
                species=combo["species"], phase=combo["phase"],
                energy_mev=f"{combo['energy_mev']:.6e}",
                n_events=args.n_events, n_threads=args.threads,
            ))

            log_path = logs_dir / f"organ_run_{combo['index']:03d}_r{rep:02d}.log"
            label = (f"[{run_n}/{total_runs}] {combo['species']}/{combo['phase']} "
                     f"bin{combo['bin_index']}={combo['energy_mev']:.3e} offsetX={combo['offset_x_m']}m "
                     f"rep={rep}")
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

            archive_path = archive_dir / f"organ_run_{combo['index']:03d}_r{rep:02d}.out"
            parsed_ok = False
            if result.returncode == 0 and out_path.is_file():
                out_path.rename(archive_path)
                try:
                    rows = parse_icrp110_out(archive_path)
                    for organ_id, edep_j, dose_gy in rows:
                        results_writer.writerow({
                            "especie": combo["species"], "fase": combo["phase"],
                            "bin_index": combo["bin_index"], "energy_mev": combo["energy_mev"],
                            "offset_x_m": combo["offset_x_m"], "repeticion": rep,
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
                "index": combo["index"], "repeticion": rep, "especie": combo["species"], "fase": combo["phase"],
                "bin_index": combo["bin_index"], "energy_mev": combo["energy_mev"],
                "offset_x_m": combo["offset_x_m"],
                "n_events": args.n_events, "seed1": seed1, "seed2": seed2,
                "macro_path": str(macro_path),
                "exit_code": result.returncode if parsed_ok else (result.returncode or 1),
                "duration_s": round(duration_s, 2), "log_path": str(log_path),
                "out_archive_path": str(archive_path) if parsed_ok else "",
            })
            manifest_file.flush()

    manifest_file.close()
    results_file.close()

    print(f"\nListo: {total_runs - n_skipped} corrida(s) nueva(s), {n_failed} fallida(s), "
          f"{n_skipped} ya completada(s) (saltadas).")
    print(f"Manifiesto: {manifest_path}")
    print(f"Resultados: {results_path}")
    if n_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
