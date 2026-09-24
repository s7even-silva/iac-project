#!/usr/bin/env python3
"""Piezas compartidas entre los scripts de piloto (Fases 7-10 del plan
estadistico, docs/bitacora/plan_estadistico.md) -- extraido de
run_intrarun_pilot.py (2026-09-19) cuando se agregaron las fases 8/9/10 y
el orquestador de gates, para no duplicar ~200 lineas en cada fase.

Todo lo que vive aqui es especifico de "correr una sola simulacion de
ActiveShield_Sim con streaming en vivo y leer su .out instrumentado" --
NO especifico de ninguna fase en particular (eso vive en cada
run_faseN.py/analyze_faseN.py)."""
import csv
import json
import math
import multiprocessing
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
import run_organ_sweep as ros  # noqa: E402 -- reusa constantes de geometria/campo, sin duplicarlas

# BASE_SEED propio de los pilotos, DISTINTO de sweep_config.BASE_SEED_ACTIVE_SHIELD_SIM
# -- a proposito: las seeds de los pilotos no deben poder colisionar nunca
# con las de produccion (run_organ_sweep.py, seed1 = BASE_SEED_ACTIVE_SHIELD_SIM
# + 1000*rep + 2*index, index en [0,119] hoy). Fecha de creacion de esta
# infraestructura como offset grande y memorable, sin relacion aritmetica
# con el esquema de produccion. Compartido entre TODAS las fases -- cada
# una reserva su propio rango via un offset de fase (ver PHASE_SEED_OFFSET
# en cada run_faseN.py) para que dos fases distintas tampoco colisionen
# entre si.
PILOT_BASE_SEED = 20260919_00


# field_scale (2026-09-19, agregado junto con las fases 8/9/10): antes
# hardcodeado a 1.0 en la macro -- la Fase 10 (Piloto B) necesita poder
# correr el caso "control" (sin blindaje activo) ademas del caso "shield",
# y el mecanismo ya documentado para eso (ver
# geant4/ActiveShield_Sim/docs/modelo_realista.md linea ~126) es
# /spacecraft/fieldScale 0 -- mismo dominio/mapa de campo, escalado a
# cero, en vez de omitir --field-map por completo (que cambiaria mas cosas
# a la vez de las que se quieren comparar).
PILOT_MACRO_TEMPLATE = """\
/phantom/setPhantomSex male
/phantom/setScoreWriterSex male
/phantom/setPhantomSection full
/phantom/setScoreWriterSection full

/spacecraft/shipRadius {ship_radius_m} m
/spacecraft/shipHalfLength {ship_half_length_m} m
/spacecraft/worldHalfSize {world_half_size_m} m
{coil_geometry_line}/spacecraft/fieldMap {field_map}
/spacecraft/fieldScale {field_scale}
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
                 field_map, coil_geometry, n_events, out_path, field_scale=1.0):
    """Una sola corrida (un solo /run/beamOn) de n_events eventos.
    field_scale=1.0 (default) es el caso "shield" (blindaje activo a su
    valor de diseno); field_scale=0.0 es el caso "control" (Fase 10)."""
    coil_geometry_line = (
        f"/spacecraft/coilGeometry {coil_geometry}\n" if coil_geometry is not None else ""
    )
    return PILOT_MACRO_TEMPLATE.format(
        ship_radius_m=ros.SHIP_RADIUS_M, ship_half_length_m=ros.SHIP_HALF_LENGTH_M,
        world_half_size_m=ros.WORLD_HALF_SIZE_M, coil_geometry_line=coil_geometry_line,
        field_map=field_map, field_scale=field_scale, offset_x_m=offset_x_m, n_threads=n_threads,
        seed1=seed1, seed2=seed2, print_progress_every=print_progress_every,
        species=combo["species"], phase=combo["phase"], energy_mev=combo["energy_mev"],
        n_events=n_events, out_path=out_path,
    )


# parse_organ_table_full: 2026-09-20, dejo de tener copia propia --
# antes duplicaba (identico caracter a caracter, salvo nombres de
# variable) lo que ahora vive como run_organ_sweep.parse_icrp110_out(),
# reescrita para incluir S1/S2/N/SE_run tambien (agregado ahi para que
# jobs_v2 del coordinator pueda subir estos estadisticos). Alias, no
# reimplementacion -- una sola fuente de verdad para este parseo. Unica
# diferencia de comportamiento: la version de run_organ_sweep.py lanza
# ValueError si la tabla de organos quedo completamente vacia (0 lineas
# parseadas) en vez de devolver {} silenciosamente -- verificado que
# check_scorer_has_intrarun_columns() de mas abajo sigue funcionando bien
# con esto (su chequeo real es "las columnas S1/S2/N faltan en filas que
# SI existen", un caso distinto que ValueError no intercepta) y que
# run_verbose() (la otra llamada real) ya envuelve esta funcion en un
# try/except generico.
parse_organ_table_full = ros.parse_icrp110_out


def check_scorer_has_intrarun_columns(build_dir: Path, binary_path: Path):
    """Corrida minima (bin barato, pocos eventos) para confirmar que el
    binario compilado YA tiene las columnas S1/S2/N/SE_run antes de
    invertir horas/minutos en el piloto completo -- falla rapido y
    explicito en vez de que el piloto entero corra y de resultados
    incompletos/erroneos sin que nadie lo note hasta el analisis final."""
    print("Verificando que el binario tiene las columnas intra-run (S1/S2/N/SE_run)...")
    project_root = Path(__file__).resolve().parent.parent.parent
    spectra_dir = project_root / "data" / "sources" / "oltaris"
    combos = ros.build_combinations(spectra_dir)
    combo = combos[0]  # GCR_H/min/bin0 -- el mas barato posible

    check_dir = build_dir / "pilots_check"
    check_dir.mkdir(parents=True, exist_ok=True)
    check_out_path = check_dir / "check.out"
    macro = build_macro(
        combo, offset_x_m=0.0, seed1=1, seed2=2, n_threads=1, print_progress_every=1000,
        field_map=(project_root.parent.parent / "field" / "production" / "crewhat_elmer_fullscale.map"),
        coil_geometry=None, n_events=100, out_path=check_out_path,
    )
    macro_path = check_dir / "check.mac"
    macro_path.write_text(macro)
    result = subprocess.run([str(binary_path), str(macro_path)], cwd=build_dir,
                             capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        sys.exit(f"ERROR: la corrida de verificacion fallo (exit {result.returncode}) -- "
                  f"revisa que ActiveShield_Sim este compilado con el scorer instrumentado. "
                  f"stderr:\n{result.stderr[-2000:]}")
    if not check_out_path.is_file():
        sys.exit(f"ERROR: {check_out_path} no se genero -- revisa el log de la corrida de verificacion.")
    rows = parse_organ_table_full(check_out_path)
    if not rows or "se_run_j" not in next(iter(rows.values())):
        sys.exit(
            "ERROR: el binario compilado NO tiene las columnas intra-run (S1_J/S2_J2/N/SE_run_J) "
            "en ICRP110.out -- este piloto requiere ICRP110UserScoreWriter.cc con los acumuladores "
            "S1/S2/N agregados (Fase 7 del plan estadistico). Recompila ActiveShield_Sim con el "
            "codigo actualizado antes de correr el piloto."
        )
    print("  OK: el binario tiene las columnas intra-run. Continuando.")


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
# throttle, una corrida con progress_every chico inundaria la terminal.
_PROGRESS_REPORT_INTERVAL_S = 5.0


# ---------------------------------------------------------------------
# Benchmark de maquina + ETA del trabajo restante (2026-09-20)
#
# Deliberadamente INDEPENDIENTE de infra/worker/worker.py:cpu_score() --
# incluso siendo el mismo principio (throughput real bajo carga
# multi-proceso, no single-thread, ver docstring de cpu_score() abajo),
# los pilotos corren fuera del coordinator/worker (ver README.md, "no
# pasan por el coordinator") y no deben depender de ese modulo. Duplica
# ~15 lineas, no una arquitectura entera.
#
# La tabla de referencia (duraciones_referencia.json) se AUTO-ALIMENTA:
# nunca viene pre-sembrada con numeros que esta maquina no midio. La
# unica combinacion con datos reales hoy (GCR_H/min, Fase 8, n_events=200)
# viene de una corrida real de esta misma sesion -- deliberadamente NO
# se pre-cargo aqui (ver discusion de equipo 2026-09-20): la primera vez
# que se corre una combinacion nueva, en cualquier maquina, no hay ETA
# total todavia (el script lo dice explicitamente), y desde la segunda
# corrida en adelante ya hay referencia real propia. Nunca se inventa un
# numero para una combinacion no medida.
# ---------------------------------------------------------------------

# MISMA operacion, MISMO numero de iteraciones y MISMA baseline de
# normalizacion que infra/worker/worker.py:cpu_score() -- a proposito,
# no una coincidencia: si difirieran, un cpu_score=1.4 en un piloto y un
# cpu_score=1.4 en el dashboard de produccion significarian cantidades
# de computo distintas, haciendo la comparacion entre ambos sistemas
# inutil (o peor, enganosamente comparable sin serlo). Se copian los
# valores literales en vez de importar worker.py para no acoplar los
# pilotos (que corren fuera del coordinator/worker, ver README.md) a ese
# modulo -- pero deben mantenerse sincronizados a mano si worker.py
# cambia su benchmark alguna vez.
_BENCHMARK_ITERATIONS_PER_PROC = 3_000_000
_BENCHMARK_REFERENCE_OPS_PER_SEC = 4_770_000.0

_REFERENCE_PATH = Path(__file__).resolve().parent / "results" / "state" / "duraciones_referencia.json"


def _benchmark_worker_proc(n_iterations: int) -> int:
    """Trabajo aritmetico fijo, sin IO -- corrido en un proceso aparte
    (multiprocessing.Pool, no threading: el GIL serializaria cualquier
    intento de paralelismo con hilos en Python puro)."""
    x = 0.5
    for _ in range(n_iterations):
        x = math.sqrt(math.sin(x) ** 2 + 1.0)
    return n_iterations


def cpu_score(n_procs: int) -> float | None:
    """Mide capacidad de computo real bajo carga multi-proceso (n_procs
    procesos simultaneos, tipicamente --threads de la fase, ya que eso es
    lo que realmente compite por CPU con el binario de Geant4 MT que se
    va a correr despues). Se corre UNA VEZ al arrancar el script. None si
    el benchmark falla por cualquier razon (nunca debe impedir que el
    piloto arranque -- sin cpu_score, simplemente no hay ETA total, ver
    estimate_remaining_s()).

    Comparable directamente con el cpu_score que reporta un worker del
    coordinator (GET /api/v1/workers) -- misma operacion aritmetica,
    mismas iteraciones por proceso, misma baseline de normalizacion (ver
    constantes arriba). Un cpu_score=1.4 acá y uno de 1.4 alli representan
    la misma capacidad de computo real."""
    try:
        n_procs = max(1, n_procs)
        started = time.perf_counter()
        with multiprocessing.Pool(processes=n_procs) as pool:
            pool.map(_benchmark_worker_proc, [_BENCHMARK_ITERATIONS_PER_PROC] * n_procs)
        elapsed_s = time.perf_counter() - started
        if elapsed_s <= 0:
            return None
        total_ops = n_procs * _BENCHMARK_ITERATIONS_PER_PROC
        return round((total_ops / elapsed_s) / _BENCHMARK_REFERENCE_OPS_PER_SEC, 3)
    except Exception as exc:  # noqa: BLE001 -- nunca tumbar el piloto por esto
        print(f"(cpu_score() fallo, se sigue sin el: {exc})")
        return None


def _load_reference_table() -> dict:
    if not _REFERENCE_PATH.is_file():
        return {}
    try:
        with open(_REFERENCE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _reference_key(fase: str, combo_label: str, work_unit: str, n_events: int) -> str:
    # n_events entra en la clave porque el costo por corrida escala con
    # el (Geant4 no tiene un costo fijo por evento independiente de
    # cuantos se pidan -- overhead de inicializacion aparte) -- mezclar
    # referencias de dos --n-events distintos daria una estimacion
    # sistematicamente sesgada.
    return f"{fase}|{combo_label}|{work_unit}|n_events={n_events}"


def record_reference_duration(fase: str, combo_label: str, work_unit: str,
                               n_events: int, duration_s: float, score: float | None) -> None:
    """Guarda una duracion real medida, NORMALIZADA por cpu_score (para
    que sea comparable entre maquinas distintas) -- promedia con lo que
    ya hubiera para esa clave exacta, no lo reemplaza de un solo dato
    (una corrida individual puede variar ~15-20%, ver DISPLAY_OVERESTIMATE_FACTOR
    en infra/coordinator/db.py para el mismo fenomeno en produccion).
    Sin cpu_score (benchmark fallo), no se guarda nada -- un tiempo sin
    normalizar contaminaria la tabla para cualquier otra maquina."""
    if score is None or score <= 0 or duration_s is None:
        return
    table = _load_reference_table()
    key = _reference_key(fase, combo_label, work_unit, n_events)
    normalized_s = duration_s * score  # tiempo equivalente a cpu_score=1.0
    prev = table.get(key)
    if prev is None:
        table[key] = {"normalized_s": normalized_s, "n_samples": 1}
    else:
        n = prev["n_samples"]
        table[key] = {
            "normalized_s": (prev["normalized_s"] * n + normalized_s) / (n + 1),
            "n_samples": n + 1,
        }
    _REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REFERENCE_PATH, "w") as f:
        json.dump(table, f, indent=2, sort_keys=True)


def estimate_remaining_s(fase: str, pending: list[tuple[str, str, int]], score: float | None) -> tuple[float | None, int]:
    """Estima el tiempo restante para una lista de trabajo pendiente
    [(combo_label, work_unit, n_events), ...] sumando la referencia
    normalizada de cada clave (si existe) reescalada por 1/score.

    Devuelve (segundos_estimados_o_None, n_sin_referencia). Si TODA la
    lista carece de referencia, o no hay score, devuelve (None, len(pending))
    -- nunca inventa un numero para lo no medido, solo dice cuanto falta
    medir.

    OJO al leer el numero que esto produce (verificado con datos reales,
    2026-09-20): puede parecer "estancado" corrida a corrida si un solo
    bin caro (ej. el bin de mayor energia de una grilla, ~250x mas lento
    que uno barato, ver REFERENCE_TIMINGS_S en infra/coordinator/db.py
    para el mismo fenomeno en produccion) sigue pendiente mientras varias
    corridas baratas ya se completan -- el total apenas se mueve porque
    esas corridas rapidas son una fraccion pequeña de la suma. No es un
    bug: cada bin tiene su propia clave de referencia (por diseño, para
    no promediar costos muy distintos entre si), asi que el bin caro
    domina el estimado hasta que finalmente se corre el."""
    if score is None or score <= 0:
        return None, len(pending)
    table = _load_reference_table()
    total_s = 0.0
    missing = 0
    for combo_label, work_unit, n_events in pending:
        key = _reference_key(fase, combo_label, work_unit, n_events)
        entry = table.get(key)
        if entry is None:
            missing += 1
            continue
        total_s += entry["normalized_s"] / score
    if missing == len(pending):
        return None, missing
    return total_s, missing


def format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}min"
    return f"{seconds / 3600:.1f}h"


def run_verbose(binary_path, macro_path, build_dir, log_path, out_path, n_events):
    """Corre el binario con streaming EN VIVO a la terminal (no solo al
    log) -- una sola corrida puede tardar minutos a horas segun el bin
    (ver tiempos estimados reales en infra/coordinator/db.py,
    REFERENCE_TIMINGS_S), asi que esperar en silencio hasta el exit final
    no es aceptable.

    Progreso en vivo: parsea las lineas "--> Event N starts" que emite
    Geant4 con /run/printProgress (ya en la macro), tomando el N mas alto
    visto entre los hilos worker (en MT, cada thread reporta su propio
    contador -- el maximo visto es una cota inferior razonable del
    progreso real, nunca sobreestima). Limitado a
    _PROGRESS_REPORT_INTERVAL_S para no inundar la terminal.

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

    try:
        rows = parse_organ_table_full(out_path)
        nonzero = [r for r in rows.values() if r["edep_J"] != 0]
        total_edep = sum(r["edep_J"] for r in rows.values())
        print(f"    resultado: {len(nonzero)}/{len(rows)} organos con edep!=0, "
              f"edep total={total_edep:.4e} J")
    except Exception as exc:  # noqa: BLE001 -- no tumbar el piloto solo por no poder mostrar el resumen
        print(f"    (no se pudo leer el resumen de {out_path}: {exc})")

    return duration_s


def resolve_paths(args, project_root):
    """Comun a todos los run_faseN.py: resuelve build_dir/binary_path/
    field_map/coil_geometry y valida que existan, con los mismos mensajes
    de error en las 4 fases."""
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
    return build_dir, binary_path, field_map, coil_geometry


def resolve_out_dir(args, pilots_dir: Path, prefix: str) -> tuple[Path, bool]:
    """Comun a todos los run_faseN.py -- resuelve el directorio de salida
    y dice si es una corrida NUEVA o una que se esta RETOMANDO.

    2026-09-20, agregado tras un corte real de una corrida de prueba (la
    sesion que la lanzo termino a mitad, dejando 22 de 24 corridas
    hechas) -- antes de esto, cada run_faseN.py generaba un directorio
    NUEVO con timestamp en cada invocacion (fase8_binning_<timestamp>/),
    asi que relanzar el mismo comando NUNCA podia apuntar al directorio
    anterior -- no habia forma de retomar, solo de volver a empezar de
    cero (perdiendo las corridas ya hechas, potencialmente horas de
    computo en una maquina remota).

    Con --out-dir explicito (el mismo que imprimio la corrida cortada),
    args.resume (default True, ver add_resume_arg()) decide si esta
    funcion reporta "retomando" (True) o si el llamador debe limpiar el
    directorio y empezar de cero (False, --no-resume). Sin --out-dir, es
    siempre una corrida nueva (no hay nada que retomar).

    SIEMPRE resuelve a ruta ABSOLUTA (.resolve()) -- bug real encontrado
    probando el resume (2026-09-20): un --out-dir RELATIVO (ej.
    'results/fase8_binning_XXXX', tal como se escribe comodamente en la
    terminal) se pasaba tal cual a macros_dir/logs_dir/outs_dir, pero el
    subprocess de Geant4 corre con cwd=build_dir (no el directorio desde
    donde se invoco este script) -- las rutas relativas resultantes no
    resolvian ahi, dando 'ERROR: Can not open a macro file' y el proceso
    terminaba con SIGSEGV (exit -11) en vez de un error claro. Resolver
    aqui, una sola vez, evita que cada run_faseN.py tenga que acordarse
    de hacerlo por separado."""
    if args.out_dir is not None:
        out_dir = args.out_dir.resolve()
        return out_dir, args.resume and out_dir.is_dir()
    out_dir = pilots_dir / "results" / f"{prefix}_{_utc_timestamp()}"
    return out_dir, False


def _utc_timestamp() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def find_latest_out_dir(pilots_dir: Path, prefix: str) -> Path | None:
    """Busca el directorio mas reciente results/<prefix>_<timestamp>/ que
    tenga un manifest.csv (senal de que al menos arranco a correr, no solo
    se creo vacio). Devuelve None si no hay ninguno.

    2026-09-20, agregado para que run_pilot_workflow.py pueda retomar una
    fase cortada SIN que el usuario tenga que pasar --out-dir a mano --
    el orquestador corre las 4 fases en secuencia, asi que un --out-dir
    global no serviria (cada fase necesita el suyo propio). El nombre
    incluye timestamp UTC (ver _utc_timestamp()), asi que ordenar por
    nombre de directorio es equivalente a ordenar por fecha de creacion."""
    results_dir = pilots_dir / "results"
    if not results_dir.is_dir():
        return None
    candidates = sorted(
        d for d in results_dir.glob(f"{prefix}_*")
        if d.is_dir() and (d / "manifest.csv").is_file()
    )
    return candidates[-1] if candidates else None


def add_resume_arg(parser):
    """Comun a todos los run_faseN.py -- --no-resume fuerza rehacer todo
    desde cero, mismo patron/nombre que run_organ_sweep.py (donde resume
    ya esta activado por defecto)."""
    parser.add_argument("--no-resume", dest="resume", action="store_false", default=True,
                         help="Rehacer desde cero incluso las corridas ya exitosas (exit_code 0) -- "
                              "por defecto, si --out-dir ya existe con un manifest.csv, se saltan "
                              "las combinaciones que ya tengan exit_code=0 ahi.")


def load_done_keys(manifest_path: Path, key_fields: list[str]) -> set[tuple]:
    """Lee un manifest.csv ya existente (de una corrida cortada) y
    devuelve el set de tuplas `key_fields` que ya tienen exit_code=0 --
    cada run_faseN.py arma su propia clave (ej. (species,phase,n_bins,
    bin_index) para Fase 8) segun que columnas identifican una corrida
    unica en su manifiesto. Vacio (no como error) si el archivo no
    existe todavia -- primera corrida, nada que retomar."""
    if not manifest_path.is_file():
        return set()
    done = set()
    with open(manifest_path, newline="") as f:
        for row in csv.DictReader(f):
            if int(row["exit_code"]) == 0:
                done.add(tuple(row[k] for k in key_fields))
    return done


def read_existing_manifest_rows(manifest_path: Path) -> list[dict]:
    """Filas ya escritas de un manifest.csv existente, para no perderlas
    al reabrir el archivo en modo escritura (los run_faseN.py reescriben
    el CSV completo en cada fila nueva, ver manifest_rows.append() +
    writer.writerows(manifest_rows) -- hace falta precargar lo viejo para
    no truncarlo)."""
    if not manifest_path.is_file():
        return []
    with open(manifest_path, newline="") as f:
        return list(csv.DictReader(f))
