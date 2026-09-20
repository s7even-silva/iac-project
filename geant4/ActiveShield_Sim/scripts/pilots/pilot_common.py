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
