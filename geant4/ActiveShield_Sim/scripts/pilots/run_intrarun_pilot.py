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
    python3 pilots/run_intrarun_pilot.py --combos GCR_He/min/6,SEP_p/max/0
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
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
import run_organ_sweep as ros  # noqa: E402 -- reusa constantes de geometria/campo, sin duplicarlas
import pilot_common as pc  # noqa: E402 -- 2026-09-19, ver ese modulo (extraido al agregar fases 8/9/10)
import pilot_state  # noqa: E402

# Puntos M a comparar (Fase 7 del plan, "M = 2500, 5000, 10000, 20000") --
# cada uno es ahora una corrida INDEPENDIENTE completa, no un checkpoint
# acumulado dentro de una corrida mas grande (ver nota de diseño arriba).
CHECKPOINTS_M = [2500, 5000, 10000, 20000]

# Combinaciones representativas por defecto (Fase 8 del plan, "seleccionar
# unas pocas combinaciones representativas y dificiles, priorizando
# aquellas con R>=3 historico"): con R>=3 historico NO disponible
# localmente (verificado 2026-09-19: todos los CSV locales tienen solo
# rep0 para toda combinacion), se elige por criterio fisico explicito, no
# arbitrario. LAS 3 SON LAS 3 COMBINACIONES REALES DE PRODUCCION
# (run_organ_sweep.py:SPECIES_PHASE, verificado 2026-09-20 -- un comentario
# anterior aqui decia erroneamente "SEP_p/min... la fase NUEVA, no la de
# produccion actual": produccion usa SEP_p/MAX, no SEP_p/min; corregido):
#   - GCR_He/min/6: bin caro (referencia real ~7321s en cpu_score=4.461,
#     ~1789s=~30min en cpu_score=21 -- caso "dificil" que el plan pide).
#   - SEP_p/max/0: Oct 1989, el evento SEP de produccion -- bin0 elegido
#     porque en esta fase el patron de costo de SEP_p esta INVERTIDO
#     (barato en bins altos, caro en bins bajos, ver REFERENCE_TIMINGS_S
#     en infra/coordinator/db.py), asi que bin0 es el caso mas caro/dificil
#     de esta especie, no el mas barato.
#   - GCR_H/min/2: caso "tipico" de costo medio-bajo, ya en produccion
#     (fase min, bin2), para tener un punto de comparacion contra un caso
#     no especialmente exigente.
DEFAULT_COMBOS = ["GCR_He/min/6", "SEP_p/max/0", "GCR_H/min/2"]

# Offset de fase (2026-09-19, agregado al factorizar pilot_common.py):
# cada fase (7,8,9,10) usa un multiplo de 10_000_000 distinto sumado a
# pilot_common.PILOT_BASE_SEED, para que dos fases DISTINTAS nunca puedan
# colisionar entre si aunque usen indices de combo/M/seed parecidos --
# antes de esto solo habia una fase, asi que no hacia falta.
PHASE_SEED_OFFSET = 0  # Fase 7 -- primera, offset 0


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
    seed1 = pc.PILOT_BASE_SEED + PHASE_SEED_OFFSET + 100_000 * combo_idx + 1_000 * m_idx + 2 * seed_idx
    return seed1, seed1 + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--combos", type=str, default=",".join(DEFAULT_COMBOS),
                         help="Lista separada por comas de 'species/phase/bin_index', "
                              f"ej. 'GCR_He/min/6,SEP_p/max/0'. Default: {DEFAULT_COMBOS}")
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
                         help="Default: pilots/results/intrarun_pilot_<timestamp UTC>/. Reusar el "
                              "directorio de una corrida anterior para retomarla -- ver --no-resume.")
    pc.add_resume_arg(parser)
    args = parser.parse_args()

    import os
    n_threads = args.threads or os.cpu_count()

    print(f"Benchmark de esta maquina ({n_threads} procesos)...")
    score = pc.cpu_score(n_threads)
    print(f"  cpu_score={score}" if score is not None
          else "  cpu_score no disponible -- se sigue sin estimacion de tiempo total.")

    project_root = Path(__file__).resolve().parent.parent.parent
    build_dir, binary_path, field_map, coil_geometry = pc.resolve_paths(args, project_root)

    pc.check_scorer_has_intrarun_columns(build_dir, binary_path)

    out_dir, resuming = pc.resolve_out_dir(args, Path(__file__).resolve().parent, "intrarun_pilot")
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

    manifest_path = out_dir / "manifest.csv"
    manifest_fieldnames = ["combo_label", "species", "phase", "bin_index", "energy_mev", "M",
                            "seed_idx", "seed1", "seed2", "exit_code", "duration_s", "macro_path", "out_path"]
    key_fields = ["combo_label", "M", "seed_idx"]
    done_keys = pc.load_done_keys(manifest_path, key_fields) if resuming else set()
    manifest_rows = pc.read_existing_manifest_rows(manifest_path) if resuming else []
    if resuming:
        print(f"Retomando {out_dir} -- {len(done_keys)} corrida(s) ya exitosa(s), se saltan "
              f"(usar --no-resume para rehacer todo).")

    # (key_de_resume, combo_label_para_referencia, work_unit, M) por cada
    # corrida planeada -- work_unit NO incluye seed_idx (dos seeds del
    # mismo M cuestan lo mismo en promedio, ver reference_key() en
    # pilot_common.py: es correcto que compartan referencia).
    all_work = [((combo_label_raw.replace("/", "_"), str(m), str(seed_idx)), combo_label_raw, f"M={m}", m)
                for combo_label_raw, _combo in requested
                for m in CHECKPOINTS_M
                for seed_idx in range(args.n_seeds)]
    pending_work = [(cl, wu, m) for key, cl, wu, m in all_work if key not in done_keys]
    eta_s, missing = pc.estimate_remaining_s("fase7", pending_work, score)
    if eta_s is not None:
        print(f"ETA del trabajo restante ({len(pending_work)} corrida(s)): ~{pc.format_eta(eta_s)}"
              + (f" ({missing} sin referencia previa, no incluida(s))" if missing else ""))
    elif pending_work:
        print(f"Sin referencia de tiempo previa para ninguna de las {len(pending_work)} corrida(s) "
              f"pendientes en esta maquina -- se ira midiendo y mostrando desde la primera.")

    run_n = 0
    for combo_idx, (combo_label_raw, combo) in enumerate(requested):
        combo_label = combo_label_raw.replace("/", "_")
        for m_idx, m in enumerate(CHECKPOINTS_M):
            for seed_idx in range(args.n_seeds):
                run_n += 1
                run_out_path = checkpoints_dir / f"run_{combo_label}_M{m}_seed{seed_idx}.out"
                key = (combo_label, str(m), str(seed_idx))
                if key in done_keys:
                    print(f"\n[{run_n}/{total_runs}] {combo_label} M={m} seed_idx={seed_idx} "
                          f"-- YA HECHA (retomando), se salta")
                    continue

                seed1, seed2 = seed_for(combo_idx, m_idx, seed_idx)
                macro = pc.build_macro(
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
                duration_s = pc.run_verbose(binary_path, macro_path, build_dir, log_path, run_out_path, m)
                exit_code = 0 if duration_s is not None else 1
                if duration_s is None:
                    duration_s = 0.0
                status = "OK" if exit_code == 0 else "FALLO"
                print(f"    -> {status}, {run_n}/{total_runs} corridas hechas, {duration_s:.1f}s esta corrida")

                if exit_code == 0:
                    pc.record_reference_duration("fase7", combo_label_raw, f"M={m}", m, duration_s, score)
                    done_keys.add(key)
                    n_left = sum(1 for k, _cl, _wu, _m in all_work if k not in done_keys)
                    eta_s, missing = pc.estimate_remaining_s(
                        "fase7", [(cl, wu, mm) for k, cl, wu, mm in all_work if k not in done_keys], score)
                    if eta_s is not None:
                        print(f"    ETA restante ({n_left} corrida(s)): ~{pc.format_eta(eta_s)}"
                              + (f" ({missing} sin referencia)" if missing else ""))
                    elif n_left:
                        print(f"    ETA restante: sin referencia aun para ninguna de las "
                              f"{n_left} corrida(s) pendientes.")

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
                rows = pc.parse_organ_table_full(out_path)
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
                hw = pc.t_critical_95(n - 1) * sem
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

    write_fase7_state(comparacion_rows, n_seeds, out_dir, reporte_path)


def write_fase7_state(comparacion_rows, n_seeds, out_dir, reporte_path):
    """Escribe pilot_state.FaseResult para que el orquestador (Fase 22,
    run_pilot_workflow.py) sepa si puede seguir solo a la Fase 8.

    El plan NO da un umbral numerico para "SE_within compatible con
    s_between" (a diferencia de la Fase 8, que si tiene B_8_16<=2.5pp) --
    dice "aproximadamente compatibles", juicio del equipo. Por diseño
    (ver pilot_state.py), esto significa que Fase 7 casi nunca puede dar
    VERDICT_AUTO_CONTINUE por si sola -- el orquestador SIEMPRE se
    detiene aqui para que una persona revise el reporte, salvo el caso
    obvio de que la corrida fallara del todo (FALLO)."""
    if not comparacion_rows:
        result = pilot_state.FaseResult(
            fase="fase7", veredicto=pilot_state.VERDICT_FALLO,
            resumen="Sin datos comparables -- ninguna combinacion/organo/M tuvo edep!=0 en >=2 seeds.",
            detalle={"n_filas_comparables": 0},
            instrucciones_si_no_auto=(
                "Revisar manifest.csv/logs/ del piloto para ver si alguna corrida fallo, o si las "
                "combinaciones elegidas son demasiado baratas (pocos organos con señal real). "
                "Volver a correr run_intrarun_pilot.py con --combos distintos o mas --n-seeds."
            ),
            out_dir=str(out_dir),
        )
        pilot_state.write_state(result)
        print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase7_estado.json'} (veredicto: FALLO)")
        return

    if n_seeds < 3:
        result = pilot_state.FaseResult(
            fase="fase7", veredicto=pilot_state.VERDICT_REVISAR,
            resumen=(
                f"n_seeds={n_seeds} < 3 -- s_between calculado con muy pocos puntos, no confiable "
                "como validacion real (ver discusion estadistica del equipo: N=2 da un IC extremadamente "
                "ancho). Esta corrida solo sirve para verificar que el mecanismo funciona, no como Piloto A real."
            ),
            detalle={"n_seeds": n_seeds, "n_filas_comparables": len(comparacion_rows)},
            instrucciones_si_no_auto=(
                f"Volver a correr: python3 pilots/run_intrarun_pilot.py --n-seeds 3 (o mas) con las "
                f"combinaciones representativas por defecto antes de decidir si continuar a la Fase 8."
            ),
            out_dir=str(out_dir),
        )
        pilot_state.write_state(result)
        print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase7_estado.json'} (veredicto: REVISAR, n_seeds insuficiente)")
        return

    ratios = [r["ratio_se_within_sobre_s_between"] for r in comparacion_rows
              if r["ratio_se_within_sobre_s_between"] == r["ratio_se_within_sobre_s_between"]]
    mediana = statistics.median(ratios) if ratios else float("nan")
    result = pilot_state.FaseResult(
        fase="fase7", veredicto=pilot_state.VERDICT_REVISAR,
        resumen=(
            f"Piloto A completo con n_seeds={n_seeds}, {len(comparacion_rows)} filas comparables, "
            f"ratio SE_within/s_between mediana={mediana:.3f}. El plan no fija un umbral numerico "
            "para este criterio -- revisar el reporte antes de decidir si R=1 es defendible."
        ),
        detalle={"n_seeds": n_seeds, "n_filas_comparables": len(comparacion_rows), "ratio_mediana": mediana},
        instrucciones_si_no_auto=(
            f"Revisar {reporte_path} y {out_dir / 'comparacion_se_within_vs_s_between.csv'}. "
            "Si el ratio es razonablemente cercano a 1.0 en los M grandes (10000-20000, mas "
            "representativos de produccion), correr: python3 pilots/run_pilot_workflow.py --continue-to fase8. "
            "Si el ratio es sistematicamente << 1, el diseño Camino B (S1/S2 por voxel) no es "
            "suficiente -- no continuar a produccion con R=1 sin resolver esto primero."
        ),
        out_dir=str(out_dir),
    )
    pilot_state.write_state(result)
    print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase7_estado.json'} (veredicto: REVISAR)")


if __name__ == "__main__":
    main()
