#!/usr/bin/env python3
"""Piloto A (Fase 7 del plan estadistico, docs/bitacora/plan_estadistico.md):
valida que la incertidumbre intra-run (SE_within, calculada con una sola
corrida via los acumuladores S1/S2/N agregados a ICRP110UserScoreWriter.cc)
sea compatible con s_between (la dispersion observada entre corridas
INDEPENDIENTES de la misma combinacion fisica).

*** CAMBIO DE DISEnO REAL 2026-09-19, LEER ANTES DE MODIFICAR ESTE SCRIPT ***
La primera version de este script intentaba "checkpoints acumulados"
(varios /run/beamOn sucesivos en la MISMA sesion de macro, con la
hipotesis de que el scorer acumularia entre ellos porque no se encontro
ningun ResetScore() explicito en el codigo). Esa hipotesis era
INCORRECTA -- verificado en un log real (grep "### Run" mostro "Run 0",
"Run 1", "Run 2", "Run 3" para 4 beamOn sucesivos): en Geant4, CADA
/run/beamOn inicia un G4Run NUEVO e INDEPENDIENTE, con su propio ciclo de
vida de scoring desde cero -- no hay "acumular entre beamOn" que
aprovechar simplemente por ausencia de reset; la ausencia de reset no
implica acumulacion, cada Run simplemente empieza limpio por diseno del
framework. Confirmado con datos reales: el "edep total" de los
"checkpoints" NO era monotono creciente (1.14e-10 J en M=2500, bajaba a
6.88e-11 J en el "checkpoint" de M=5000, subia de nuevo despues) --
matematicamente imposible si de verdad fuera acumulado (edep no puede
bajar al agregar mas eventos no-negativos). Cada "checkpoint" en realidad
media un LOTE DE EVENTOS DISTINTO Y NO RELACIONADO con el anterior, y la
fluctuacion era simplemente ruido Monte Carlo normal entre esos lotes
independientes y chicos (18-40 de 142 organos con señal en cada uno).

DISEnO CORREGIDO (el que implementa esta version del script) -- "camino 1"
de las dos alternativas discutidas con el equipo: cada M en CHECKPOINTS_M
es ahora una CORRIDA INDEPENDIENTE completa (un solo /run/beamOn M por
proceso de Geant4, como ya hace run_organ_sweep.py), con su PROPIA semilla
determinista -- no un checkpoint dentro de una corrida mas grande. Esto es
exactamente la "Alternativa mas robusta" que el propio plan ya preveia en
la Fase 7 ("Correr cada tamaño M con seeds completamente nuevas... ~1.9x
mas eventos respecto del esquema con checkpoints"), adoptada aqui como
diseño principal (no alternativa) porque el esquema de checkpoints
resultó invalido, no solo mas caro.

Consecuencia en el calculo estadistico (ver analyze()): s_between YA NO
se calcula solo en M=20000 -- con este diseño, cada M tiene sus propias
n_seeds corridas independientes, asi que s_between(M) y SE_within(M) se
pueden comparar en LOS 4 VALORES DE M, dando una curva de comparacion
completa en vez de un solo punto. El costo total sube de
"n_combos*n_seeds corridas" a "n_combos*n_seeds*4 corridas" (una por
cada M, ya no compartidas dentro de una sola corrida larga).

Que hace, por cada combinacion representativa elegida (--combos):

  1. Para cada M en {2500, 5000, 10000, 20000}: corre N_SEEDS corridas
     INDEPENDIENTES (semillas distintas, deterministas y documentadas --
     ver seed_for()) de exactamente M eventos cada una (un solo
     /run/beamOn M por proceso).
  2. De cada corrida, extrae (Edep_J, SE_run_J) por organo desde las
     columnas nuevas del .out (S1/S2/N, columnas 4-7 de la tabla "ORGAN
     ENERGY DEPOSITIONS AND ABSORBED DOSE").
  3. Para cada M, con las N_SEEDS corridas independientes de ese M,
     calcula s_between por organo -- la dispersion REAL entre corridas
     independientes de ese tamaño.
  4. Compara s_between(M) contra SE_within(M) (promediado entre las
     N_SEEDS corridas de ese M) y reporta el ratio, PARA CADA M -- el
     criterio de aceptacion (Fase 7): deben ser "aproximadamente
     compatibles", sin un umbral numerico fijo todavia en el plan (queda
     a criterio del equipo al revisar el reporte).
  5. Ademas verifica SE(M) * sqrt(M) ~ constante (ley 1/sqrt(M)) usando
     el SE_within medio de cada M -- YA NO dentro de una sola seed (eso
     exigiria el diseño de checkpoints que resulto invalido), sino entre
     los 4 valores de M, cada uno con su propio conjunto de seeds.

LIMITACION DE DISEnO explicita (Camino B, ver docstring de
ICRP110UserScoreWriter.cc): SE_within se calcula agregando S1/S2 POR VOXEL
dentro de cada organo, no por evento-organo agregado -- si hay correlacion
positiva entre voxels del mismo evento (un primario que cruza el organo
deposita en varios voxels a la vez), SE_within puede SUBESTIMAR la
varianza real. Este piloto es precisamente el experimento que mide
empiricamente si eso importa en la practica (comparando contra s_between,
que no tiene esa limitacion). Si el ratio sale sistematicamente << 1
(SE_within mucho menor que s_between), es evidencia de que la covarianza
entre voxels si importa y hace falta el diseno mas costoso (instrumentar
EndOfEventAction, "Camino A", no implementado).

Uso pensado para una maquina de cpu_score alto (ej. fcm-pc1, ~21 vs. la
referencia de 4.461 en bryam-local) -- NO pasa por el coordinator/la cola
de produccion, es una corrida puntual fuera de ese sistema (decision de
equipo 2026-09-19: los pilotos son trabajo puntual, no barrido masivo, no
justifica extender el esquema del coordinator todavia).

Uso:
    # Compilar ActiveShield_Sim primero (ver README.md), con el scorer ya
    # actualizado (S1/S2/N -- este piloto NO funciona con un binario viejo,
    # ver check_scorer_has_intrarun_columns()).

    python3 pilots/run_intrarun_pilot.py
    python3 pilots/run_intrarun_pilot.py --combos GCR_He/min/6,SEP_p/min/0
    python3 pilots/run_intrarun_pilot.py --n-seeds 3 --threads 20

Costo: n_combos * n_seeds * 4 corridas independientes de Geant4 (una por
cada M en CHECKPOINTS_M) -- con los defaults (3 combos, 3 seeds), 36
corridas. Ver tiempos estimados reales en infra/coordinator/db.py
(REFERENCE_TIMINGS_S, escalado por cpu_score de la maquina que corra esto).

Salida: pilots/results/intrarun_pilot_<timestamp>/
    - run_<combo>_seed<seed_idx>_M<M>.out      (tabla completa de organos, cruda)
    - resumen_por_organo.csv                   (un resumen por combo/M/seed/organo)
    - comparacion_se_within_vs_s_between.csv   (el resultado central del piloto, por M)
    - reporte.txt                              (resumen legible + veredicto)
"""
import argparse
import csv
import math
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
import sweep_config  # noqa: E402
import energy_bins  # noqa: E402
import run_organ_sweep as ros  # noqa: E402 -- reusa constantes de geometria/campo, sin duplicarlas

# Puntos M a comparar (Fase 7 del plan, "M = 2500, 5000, 10000, 20000") --
# cada uno es ahora una corrida INDEPENDIENTE completa, no un checkpoint
# acumulado dentro de una corrida mas grande (ver nota de diseño arriba).
CHECKPOINTS_M = [2500, 5000, 10000, 20000]

# Combinaciones representativas por defecto (Fase 8 del plan, "seleccionar
# unas pocas combinaciones representativas y dificiles, priorizando
# aquellas con R>=3 historico"): con R>=3 historico NO disponible
# localmente (verificado 2026-09-19: todos los CSV locales tienen solo
# rep0 para toda combinacion), se elige por criterio fisico explicito, no
# arbitrario:
#   - GCR_He/min/6: bin caro (referencia real ~7321s en cpu_score=4.461,
#     ~1789s=~30min en cpu_score=21 -- caso "dificil" que el plan pide).
#   - SEP_p/min/0: la fase NUEVA (min, no la de produccion actual) con
#     mayor sospecha de comportamiento distinto (ver AGENTS.md, espectro
#     "duro" de Feb1956 vs. Oct1989) -- bin0 elegido porque a esta fase el
#     patron de costo de SEP_p esta INVERTIDO (barato en bins altos, caro
#     en bins bajos, ver REFERENCE_TIMINGS_S en infra/coordinator/db.py).
#   - GCR_H/min/2: caso "tipico" de costo medio-bajo, ya en produccion
#     (fase min, bin2), para tener un punto de comparacion contra un caso
#     no especialmente exigente.
DEFAULT_COMBOS = ["GCR_He/min/6", "SEP_p/min/0", "GCR_H/min/2"]

# BASE_SEED propio del piloto, DISTINTO de sweep_config.BASE_SEED_ACTIVE_SHIELD_SIM
# -- a proposito: las seeds de este piloto no deben poder colisionar nunca
# con las de produccion (run_organ_sweep.py, seed1 = BASE_SEED_ACTIVE_SHIELD_SIM
# + 1000*rep + 2*index, index en [0,119] hoy). Fecha de creacion de este
# piloto como offset grande y memorable, sin relacion aritmetica con el
# esquema de produccion.
PILOT_BASE_SEED = 20260919_00


def seed_for(combo_idx: int, m_idx: int, seed_idx: int) -> tuple[int, int]:
    """(seed1, seed2) deterministas para (combinacion, indice de M,
    seed_idx del piloto) -- documentado explicitamente (no solo
    reproducible por casualidad), ya que la Fase 20 del plan pide
    registrar metadatos de reproduccion para cualquier corrida, incluidos
    los pilotos.

    Incluye m_idx (2026-09-19, rediseño tras el hallazgo de que cada M es
    ahora una corrida independiente, no un checkpoint) -- sin esto,
    "seed_idx=0" del combo X en M=2500 y en M=5000 usarian la MISMA
    semilla, lo cual no es incorrecto en si (dos corridas de distinto
    tamaño con la misma semilla siguen siendo validas y hasta comparables
    con CRN, ver Fase 10 del plan), pero aqui se prefiere dar a cada
    (combo,M,seed_idx) una semilla propia y distinguible -- evita
    cualquier ambigüedad de "es una coincidencia de diseño o data real"
    al revisar el manifest.csv despues."""
    seed1 = PILOT_BASE_SEED + 100_000 * combo_idx + 1_000 * m_idx + 2 * seed_idx
    return seed1, seed1 + 1


PILOT_MACRO_TEMPLATE = """\
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
/run/printProgress {print_progress_every}

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
/control/shell cp ICRP110.out {out_path}
"""


def build_macro(combo, offset_x_m, seed1, seed2, n_threads, print_progress_every,
                 field_map, coil_geometry, n_events, out_path):
    """Una sola corrida (un solo /run/beamOn) de n_events eventos --
    ver la nota de diseño al inicio del modulo: cada M del piloto es
    ahora una corrida independiente completa, no un checkpoint dentro de
    una corrida mas grande."""
    coil_geometry_line = (
        f"/spacecraft/coilGeometry {coil_geometry}\n" if coil_geometry is not None else ""
    )
    return PILOT_MACRO_TEMPLATE.format(
        ship_radius_m=ros.SHIP_RADIUS_M, ship_half_length_m=ros.SHIP_HALF_LENGTH_M,
        world_half_size_m=ros.WORLD_HALF_SIZE_M, coil_geometry_line=coil_geometry_line,
        field_map=field_map, offset_x_m=offset_x_m, n_threads=n_threads,
        seed1=seed1, seed2=seed2, print_progress_every=print_progress_every,
        species=combo["species"], phase=combo["phase"], energy_mev=combo["energy_mev"],
        n_events=n_events, out_path=out_path,
    )


def parse_organ_table_full(out_path: Path):
    """Como run_organ_sweep.parse_icrp110_out(), pero lee TAMBIEN las
    columnas 4-7 (S1_J, S2_J2, N, SE_run_J) que agrega el scorer
    instrumentado -- el parser original de produccion solo usa
    parts[0]/parts[1] (Edep/Dose) a proposito, para no depender de un
    formato que todavia no existia cuando se escribio. Devuelve
    {organo_id: {edep_J, dose_Gy, s1_j, s2_j2, n, se_run_j}}."""
    text = out_path.read_text()
    marker = "ORGAN ENERGY DEPOSITIONS AND ABSORBED DOSE"
    if marker not in text:
        raise ValueError(f"{out_path}: no se encontro la seccion '{marker}'")
    tail = text.split(marker, 1)[1]
    rows = {}
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
        organo_id = int(left.strip())
        entry = {"edep_J": float(parts[0]), "dose_Gy": float(parts[1])}
        if len(parts) >= 6:
            entry["s1_j"] = float(parts[2])
            entry["s2_j2"] = float(parts[3])
            entry["n"] = int(parts[4])
            entry["se_run_j"] = float(parts[5])
        rows[organo_id] = entry
    return rows


def check_scorer_has_intrarun_columns(build_dir: Path, binary_path: Path):
    """Corrida minima (bin barato, pocos eventos) para confirmar que el
    binario compilado YA tiene las columnas S1/S2/N/SE_run antes de
    invertir horas en el piloto completo -- falla rapido y explicito en
    vez de que el piloto entero corra y de resultados incompletos/erroneos
    sin que nadie lo note hasta el analisis final."""
    print("Verificando que el binario tiene las columnas intra-run (S1/S2/N/SE_run)...")
    project_root = Path(__file__).resolve().parent.parent.parent
    spectra_dir = project_root / "data" / "sources" / "oltaris"
    combos = ros.build_combinations(spectra_dir)
    combo = combos[0]  # GCR_H/min/bin0 -- el mas barato posible

    check_dir = build_dir / "pilots_check"
    check_dir.mkdir(parents=True, exist_ok=True)
    check_out_path = check_dir / "check.out"
    macro = PILOT_MACRO_TEMPLATE.format(
        ship_radius_m=ros.SHIP_RADIUS_M, ship_half_length_m=ros.SHIP_HALF_LENGTH_M,
        world_half_size_m=ros.WORLD_HALF_SIZE_M, coil_geometry_line="",
        field_map=(project_root.parent.parent / "field" / "production" / "crewhat_elmer_fullscale.map"),
        offset_x_m=0.0, n_threads=1, seed1=1, seed2=2, print_progress_every=1000,
        species=combo["species"], phase=combo["phase"], energy_mev=combo["energy_mev"],
        n_events=100, out_path=check_out_path,
    )
    macro_path = check_dir / "check.mac"
    macro_path.write_text(macro)
    result = subprocess.run([str(binary_path), str(macro_path)], cwd=build_dir,
                             capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        sys.exit(f"ERROR: la corrida de verificacion fallo (exit {result.returncode}) -- "
                  f"revisa que ActiveShield_Sim este compilado con el scorer instrumentado. "
                  f"stderr:\n{result.stderr[-2000:]}")
    out_path = check_dir / "check.out"
    if not out_path.is_file():
        sys.exit(f"ERROR: {out_path} no se genero -- revisa el log de la corrida de verificacion.")
    rows = parse_organ_table_full(out_path)
    if not rows or "se_run_j" not in next(iter(rows.values())):
        sys.exit(
            "ERROR: el binario compilado NO tiene las columnas intra-run (S1_J/S2_J2/N/SE_run_J) "
            "en ICRP110.out -- este piloto requiere ICRP110UserScoreWriter.cc con los acumuladores "
            "S1/S2/N agregados (Fase 7 del plan estadistico). Recompila ActiveShield_Sim con el "
            "codigo actualizado antes de correr el piloto."
        )
    print("  OK: el binario tiene las columnas intra-run. Continuando con el piloto real.")


def t_critical_95(df):
    # Mismo criterio/tabla que aggregate_organ_doses.py (copiado, no
    # importado -- ver ese archivo para por que).
    T_TABLE_95 = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228,
    }
    if df <= 0:
        return float("nan")
    return T_TABLE_95.get(df, 1.96)


_EVENT_PROGRESS_RE = re.compile(r"--> Event (\d+) starts")
# Cada cuantos segundos, como maximo, reportar progreso -- Geant4 con
# /run/printProgress imprime una linea por cada N eventos y por CADA hilo
# worker (4 threads = 4 lineas por cada N eventos reales) -- sin este
# throttle, una corrida con progress_every chico inundaria la terminal
# igual que ya se evito evitando el echo linea por linea completo.
_PROGRESS_REPORT_INTERVAL_S = 5.0


def run_verbose(binary_path, macro_path, build_dir, log_path, out_path, n_events):
    """Corre el binario con streaming EN VIVO a la terminal (no solo al
    log) -- una sola corrida de este piloto puede tardar minutos a horas
    segun el bin (ver tiempos estimados reales en infra/coordinator/db.py,
    REFERENCE_TIMINGS_S), asi que esperar en silencio hasta el exit final
    no es aceptable: se necesita saber que tan avanzada va la corrida
    ahora mismo, no solo al terminar.

    Progreso en vivo: parsea las lineas "--> Event N starts" que emite
    Geant4 con /run/printProgress (ya en la macro), tomando el N mas alto
    visto entre los hilos worker (en MT, cada thread reporta su propio
    contador, no hay una sola linea "global" -- el maximo visto es una
    cota inferior razonable del progreso real, nunca sobreestima). Se
    limita a reportar como mucho una vez cada _PROGRESS_REPORT_INTERVAL_S
    -- Geant4 imprime una linea por thread por cada N eventos, y sin
    throttle eso inundaria la terminal en corridas con progress_every
    chico.

    Devuelve la duracion en segundos, o None si el proceso termino con
    exit code distinto de 0 (fallo)."""
    t0 = time.time()
    last_report = t0
    max_event_seen = -1

    process = subprocess.Popen(
        [str(binary_path), str(macro_path)], cwd=build_dir,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    with open(log_path, "w") as logf:
        while True:
            line = process.stdout.readline()
            if line:
                logf.write(line)
                match = _EVENT_PROGRESS_RE.search(line)
                if match:
                    max_event_seen = max(max_event_seen, int(match.group(1)))
                now = time.time()
                if max_event_seen >= 0 and (now - last_report) >= _PROGRESS_REPORT_INTERVAL_S:
                    last_report = now
                    pct = 100.0 * max_event_seen / n_events if n_events else 0.0
                    elapsed = now - t0
                    rate = max_event_seen / elapsed if elapsed > 0 else 0.0
                    eta_str = f"{(n_events - max_event_seen) / rate:.0f}s" if rate > 0 else "?"
                    print(f"    ... evento ~{max_event_seen}/{n_events} ({pct:5.1f}%), "
                          f"{elapsed:6.1f}s transcurridos, ETA ~{eta_str}")
                continue
            if process.poll() is not None:
                break
    duration_s = time.time() - t0
    if process.returncode != 0:
        print(f"    !! Proceso termino con exit code {process.returncode} -- ver {log_path}")
        return None

    # Resultado inmediato apenas termina -- mismo principio que antes
    # (feedback real, no solo "OK"): edep total y cuantos organos ya
    # tienen señal, leido directo del .out recien generado.
    try:
        rows = parse_organ_table_full(out_path)
        nonzero = [r for r in rows.values() if r["edep_J"] != 0]
        total_edep = sum(r["edep_J"] for r in rows.values())
        print(f"    resultado: {len(nonzero)}/{len(rows)} organos con edep!=0, "
              f"edep total={total_edep:.4e} J")
    except Exception as exc:  # noqa: BLE001 -- no tumbar el piloto solo por no poder mostrar el resumen
        print(f"    (no se pudo leer el resumen de {out_path}: {exc})")

    return duration_s


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--combos", type=str, default=",".join(DEFAULT_COMBOS),
                         help="Lista separada por comas de 'species/phase/bin_index', "
                              f"ej. 'GCR_He/min/6,SEP_p/min/0'. Default: {DEFAULT_COMBOS}")
    parser.add_argument("--offset-x-m", type=float, default=0.0,
                         help="Offset radial del fantoma (default 0.0 -- un solo offset, el piloto "
                              "valida el estimador, no el efecto de posicion).")
    parser.add_argument("--n-seeds", type=int, default=3,
                         help="Seeds independientes por combinacion (default 3, minimo del plan "
                              "para poder calcular s_between con algo de margen -- N=2 da un IC "
                              "extremadamente ancho, ver discusion estadistica previa del equipo).")
    parser.add_argument("--field-map", type=Path, default=ros.DEFAULT_FIELD_MAP)
    parser.add_argument("--coil-geometry", type=Path, default=ros.DEFAULT_COIL_GEOMETRY)
    parser.add_argument("--no-coil-geometry", action="store_true")
    parser.add_argument("--build-dir", type=Path, default=None)
    parser.add_argument("--threads", type=int, default=None,
                         help="Hilos de Geant4 MT (default: todos los nucleos detectados).")
    parser.add_argument("--print-progress-every", type=int, default=500)
    parser.add_argument("--out-dir", type=Path, default=None,
                         help="Default: pilots/results/intrarun_pilot_<timestamp UTC>/")
    args = parser.parse_args()

    import os
    n_threads = args.threads or os.cpu_count()

    project_root = Path(__file__).resolve().parent.parent.parent
    build_dir = (args.build_dir or (project_root / "build")).resolve()
    binary_path = build_dir / "ICRP110phantoms"
    field_map = args.field_map.resolve()
    coil_geometry = None if args.no_coil_geometry else args.coil_geometry.resolve()

    if not binary_path.is_file():
        sys.exit(f"ERROR: no se encontro {binary_path}. Compila ActiveShield_Sim primero.")
    if not field_map.is_file():
        sys.exit(f"ERROR: no se encontro {field_map}.")
    if coil_geometry is not None and not coil_geometry.is_file():
        sys.exit(f"ERROR: no se encontro {coil_geometry}.")

    check_scorer_has_intrarun_columns(build_dir, binary_path)

    out_dir = args.out_dir or (
        Path(__file__).resolve().parent / "results" /
        f"intrarun_pilot_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    macros_dir = out_dir / "macros"
    logs_dir = out_dir / "logs"
    checkpoints_dir = out_dir / "checkpoints"
    for d in (macros_dir, logs_dir, checkpoints_dir):
        d.mkdir(parents=True, exist_ok=True)

    spectra_dir = project_root / "data" / "sources" / "oltaris"
    all_combos = ros.build_combinations(spectra_dir)
    combos_by_key = {(c["species"], c["phase"], c["bin_index"]): c for c in all_combos}

    requested = []
    for spec in args.combos.split(","):
        species, phase, bin_index = spec.strip().split("/")
        key = (species, phase, int(bin_index))
        if key not in combos_by_key:
            sys.exit(f"ERROR: combinacion {spec} no existe en build_combinations() -- "
                      f"revisa species/phase/bin_index (0-7).")
        requested.append((spec.strip(), combos_by_key[key]))

    total_runs = len(requested) * len(CHECKPOINTS_M) * args.n_seeds
    print(f"Piloto A (Fase 7): {len(requested)} combinacion(es) x {len(CHECKPOINTS_M)} valores de M "
          f"x {args.n_seeds} seed(s) = {total_runs} corridas INDEPENDIENTES de Geant4 "
          f"(cada M es su propia corrida completa, ver nota de diseño al inicio del modulo).")
    print(f"M = {CHECKPOINTS_M}")
    print(f"Salida: {out_dir}")
    print()

    manifest_rows = []
    manifest_path = out_dir / "manifest.csv"
    manifest_fieldnames = ["combo_label", "species", "phase", "bin_index", "energy_mev", "M",
                            "seed_idx", "seed1", "seed2", "exit_code", "duration_s", "macro_path", "out_path"]

    run_n = 0
    for combo_idx, (combo_label_raw, combo) in enumerate(requested):
        combo_label = combo_label_raw.replace("/", "_")
        for m_idx, m in enumerate(CHECKPOINTS_M):
            for seed_idx in range(args.n_seeds):
                run_n += 1
                seed1, seed2 = seed_for(combo_idx, m_idx, seed_idx)
                run_out_path = checkpoints_dir / f"run_{combo_label}_M{m}_seed{seed_idx}.out"
                macro = build_macro(
                    combo, args.offset_x_m, seed1, seed2, n_threads, args.print_progress_every,
                    field_map, coil_geometry, m, run_out_path,
                )
                macro_path = macros_dir / f"{combo_label}_M{m}_seed{seed_idx}.mac"
                macro_path.write_text(macro)

                log_path = logs_dir / f"{combo_label}_M{m}_seed{seed_idx}.log"
                print(f"\n[{run_n}/{total_runs}] {combo_label} M={m} seed_idx={seed_idx} "
                      f"(species={combo['species']} phase={combo['phase']} bin={combo['bin_index']} "
                      f"E={combo['energy_mev']:.3e} MeV, seed1={seed1} seed2={seed2})")
                print(f"    log completo en {log_path}")
                duration_s = run_verbose(binary_path, macro_path, build_dir, log_path, run_out_path, m)
                exit_code = 0 if duration_s is not None else 1
                if duration_s is None:
                    duration_s = 0.0
                status = "OK" if exit_code == 0 else "FALLO"
                print(f"    -> {status}, {run_n}/{total_runs} corridas hechas, {duration_s:.1f}s esta corrida")

                manifest_rows.append({
                    "combo_label": combo_label, "species": combo["species"], "phase": combo["phase"],
                    "bin_index": combo["bin_index"], "energy_mev": combo["energy_mev"], "M": m,
                    "seed_idx": seed_idx, "seed1": seed1, "seed2": seed2,
                    "exit_code": exit_code, "duration_s": round(duration_s, 2),
                    "macro_path": str(macro_path), "out_path": str(run_out_path),
                })
                with open(manifest_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=manifest_fieldnames)
                    writer.writeheader()
                    writer.writerows(manifest_rows)

    print()
    print("Corridas completas. Analizando resultados...")
    analyze(requested, args.n_seeds, checkpoints_dir, out_dir)


def analyze(requested, n_seeds, checkpoints_dir, out_dir):
    """Lee todos los .out de corridas (una por combo/M/seed, ver nota de
    diseño al inicio del modulo), arma el resumen por organo y la
    comparacion SE_within vs s_between PARA CADA M (ya no solo en
    M=20000: con el rediseño, cada M tiene su propio conjunto de seeds
    independientes, asi que se puede comparar en los 4 valores de M)."""
    resumen_path = out_dir / "resumen_por_organo.csv"
    resumen_fieldnames = ["combo_label", "M", "seed_idx", "organo_id", "edep_J",
                           "s1_j", "s2_j2", "n", "se_run_j"]
    resumen_rows = []

    # data_by_m[(combo_label, M, organo_id)] = [edep_j por seed]
    data_by_m = {}
    se_within_by_m = {}

    for combo_label_raw, combo in requested:
        combo_label = combo_label_raw.replace("/", "_")
        for m in CHECKPOINTS_M:
            for seed_idx in range(n_seeds):
                out_path = checkpoints_dir / f"run_{combo_label}_M{m}_seed{seed_idx}.out"
                if not out_path.is_file():
                    print(f"  ADVERTENCIA: falta {out_path} -- corrida incompleta, se omite.")
                    continue
                rows = parse_organ_table_full(out_path)
                for organo_id, entry in rows.items():
                    if "se_run_j" not in entry:
                        continue  # ya deberia haber fallado en check_scorer_has_intrarun_columns, defensivo
                    resumen_rows.append({
                        "combo_label": combo_label, "M": m, "seed_idx": seed_idx,
                        "organo_id": organo_id, "edep_J": entry["edep_J"],
                        "s1_j": entry["s1_j"], "s2_j2": entry["s2_j2"],
                        "n": entry["n"], "se_run_j": entry["se_run_j"],
                    })
                    data_by_m.setdefault((combo_label, m, organo_id), []).append(entry["edep_J"])
                    se_within_by_m.setdefault((combo_label, m, organo_id), []).append(entry["se_run_j"])

    with open(resumen_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resumen_fieldnames)
        writer.writeheader()
        writer.writerows(resumen_rows)
    print(f"  Resumen por organo: {resumen_path} ({len(resumen_rows)} filas)")

    # Comparacion central: s_between (entre seeds independientes de ese M)
    # vs SE_within promedio (entre esas mismas seeds), PARA CADA M -- solo
    # para organos con edep real en >=2 seeds de ese M (si un organo da 0
    # en alguna seed, esa fila no es comparable de forma limpia -- se
    # documenta como "n_seeds_con_datos" en vez de forzar un promedio con
    # ceros que distorsionaria s_between).
    comparacion_rows = []
    comparacion_fieldnames = ["combo_label", "M", "organo_id", "n_seeds_con_datos",
                               "edep_medio_J", "s_between_J", "se_within_medio_J",
                               "ratio_se_within_sobre_s_between", "ic95_s_between_low", "ic95_s_between_high"]

    combo_labels = sorted({c.replace("/", "_") for c, _ in requested})
    organo_ids = sorted({oid for (_cl, _m, oid) in data_by_m})

    for combo_label in combo_labels:
        for m in CHECKPOINTS_M:
            for organo_id in organo_ids:
                key = (combo_label, m, organo_id)
                edeps = data_by_m.get(key, [])
                ses = se_within_by_m.get(key, [])
                nonzero_edeps = [e for e in edeps if e != 0]
                if len(nonzero_edeps) < 2:
                    continue  # sin suficientes seeds con senal real -- no comparable
                s_between = statistics.stdev(nonzero_edeps)
                se_within_medio = statistics.fmean(s for s, e in zip(ses, edeps) if e != 0)
                edep_medio = statistics.fmean(nonzero_edeps)
                ratio = (se_within_medio / s_between) if s_between > 0 else float("nan")
                n = len(nonzero_edeps)
                sem = s_between / math.sqrt(n)
                hw = t_critical_95(n - 1) * sem
                comparacion_rows.append({
                    "combo_label": combo_label, "M": m, "organo_id": organo_id, "n_seeds_con_datos": n,
                    "edep_medio_J": edep_medio, "s_between_J": s_between,
                    "se_within_medio_J": se_within_medio, "ratio_se_within_sobre_s_between": ratio,
                    "ic95_s_between_low": edep_medio - hw, "ic95_s_between_high": edep_medio + hw,
                })

    comparacion_path = out_dir / "comparacion_se_within_vs_s_between.csv"
    with open(comparacion_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=comparacion_fieldnames)
        writer.writeheader()
        writer.writerows(comparacion_rows)
    print(f"  Comparacion SE_within vs s_between (por M): {comparacion_path} ({len(comparacion_rows)} filas)")

    # Verificacion de la ley 1/sqrt(M): SE(M)*sqrt(M) deberia ser ~constante
    # -- usando el SE_within MEDIO de cada M (entre sus propias seeds), ya
    # no dentro de una sola seed a traves de checkpoints (ese diseño
    # resulto invalido, ver nota al inicio del modulo).
    convergencia_rows = []
    convergencia_fieldnames = ["combo_label", "organo_id"] + [f"SE_sqrtM_M{m}" for m in CHECKPOINTS_M]
    for combo_label in combo_labels:
        for organo_id in organo_ids:
            values = []
            for m in CHECKPOINTS_M:
                key = (combo_label, m, organo_id)
                edeps = data_by_m.get(key, [])
                ses = se_within_by_m.get(key, [])
                se_nonzero = [s for s, e in zip(ses, edeps) if e != 0]
                if not se_nonzero:
                    values.append(None)
                    continue
                se_medio = statistics.fmean(se_nonzero)
                values.append(se_medio * math.sqrt(m))
            if any(v is not None for v in values):
                row = {"combo_label": combo_label, "organo_id": organo_id}
                for m, v in zip(CHECKPOINTS_M, values):
                    row[f"SE_sqrtM_M{m}"] = v
                convergencia_rows.append(row)
    convergencia_path = out_dir / "convergencia_1_sobre_sqrtM.csv"
    with open(convergencia_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=convergencia_fieldnames)
        writer.writeheader()
        writer.writerows(convergencia_rows)
    print(f"  Verificacion SE(M)*sqrt(M): {convergencia_path} ({len(convergencia_rows)} filas)")

    # Reporte legible.
    reporte_path = out_dir / "reporte.txt"
    with open(reporte_path, "w") as f:
        f.write("PILOTO A (Fase 7) -- Reporte de validacion del estimador intra-run\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Combinaciones: {[c for c, _ in requested]}\n")
        f.write(f"Seeds independientes por (combinacion, M): {n_seeds}\n")
        f.write(f"Valores de M comparados: {CHECKPOINTS_M}\n\n")

        if not comparacion_rows:
            f.write("SIN DATOS COMPARABLES -- ninguna combinacion/organo/M tuvo edep!=0 en\n"
                    "al menos 2 seeds. Revisar manifest.csv/logs/ para ver si alguna corrida\n"
                    "fallo, o si la combinacion elegida es demasiado barata (bin de energia\n"
                    "muy baja, ver AGENTS.md sobre bins 0-1).\n")
        else:
            f.write(f"Filas comparables (organo con datos en >=2 seeds): {len(comparacion_rows)}\n\n")
            f.write("Ratio SE_within/s_between por M (agregado sobre todas las combinaciones/organos):\n")
            for m in CHECKPOINTS_M:
                ratios_m = [r["ratio_se_within_sobre_s_between"] for r in comparacion_rows
                            if r["M"] == m and r["ratio_se_within_sobre_s_between"] == r["ratio_se_within_sobre_s_between"]]
                if ratios_m:
                    f.write(f"  M={m:>6}: n={len(ratios_m):>4}, media={statistics.fmean(ratios_m):.3f}, "
                            f"mediana={statistics.median(ratios_m):.3f}, "
                            f"min={min(ratios_m):.3f}, max={max(ratios_m):.3f}\n")
                else:
                    f.write(f"  M={m:>6}: sin filas comparables\n")
            f.write("\n")
            f.write("Interpretacion (ver docstring del script para el detalle):\n")
            f.write("  ratio ~ 1.0  -> SE_within predice bien la dispersion real, Camino B validado.\n")
            f.write("  ratio << 1.0 -> SE_within SUBESTIMA la varianza real (covarianza entre\n")
            f.write("                  voxels del mismo evento importa) -- no usar R=1 sin el\n")
            f.write("                  diseno mas costoso (Camino A, EndOfEventAction).\n")
            f.write("  ratio >> 1.0 -> inesperado, investigar antes de continuar (posible error\n")
            f.write("                  en el calculo, o s_between subestimado por muy pocas seeds).\n\n")
            f.write("Este piloto NO fija un umbral numerico de aceptacion (queda a criterio\n")
            f.write("del equipo revisando este reporte + comparacion_se_within_vs_s_between.csv,\n")
            f.write("ver Fase 7 del plan: 'Si falla... no se pasa a produccion con R=1 hasta\n")
            f.write("identificar la causa').\n")
        f.write("\n")
        f.write(f"Detalle completo: {comparacion_path.name}\n")
        f.write(f"Verificacion 1/sqrt(M): {convergencia_path.name}\n")

    print(f"  Reporte: {reporte_path}")
    print()
    print(reporte_path.read_text())


if __name__ == "__main__":
    main()
