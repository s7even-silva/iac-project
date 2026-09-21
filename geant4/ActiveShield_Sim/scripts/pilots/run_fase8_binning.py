#!/usr/bin/env python3
"""Fase 8 del plan estadistico (docs/bitacora/plan_estadistico.md):
convergencia del binning energetico -- determina si 8 bins son
suficientemente precisos, comparando contra 16 (y, si hace falta, contra
32) bins, ANTES de calibrar M_b (Fase 9) o comprobar la precision
shield/control (Fase 10). El problema es de discretizacion, no de ruido
Monte Carlo -- aumentar M no lo arregla.

Que hace, por cada combinacion representativa (--combos) y cada grilla
de --n-bins-grid (default 8,16,32):

  1. Corre TODOS los bins de esa grilla (energy_bins.build_bins(...,
     n_bins=N)), cada uno con --n-events eventos, UNA sola vez (sin
     repeticiones -- esta fase mide error de discretizacion, no ruido
     MC; el ruido MC ya se abordo en la Fase 7).
  2. Calcula D_N = suma_b W_b(N bins) * R_b para cada grilla -- misma
     formula fisica que aggregate_organ_doses.py, reproducida aqui
     porque ese script no esta estructurado como libreria reusable
     (todo vive en su main()).
  3. Calcula epsilon_binning = |D_hi - D_lo| / |D_hi| entre CADA PAR
     CONSECUTIVO de grillas (8 vs 16, 16 vs 32, etc. -- no solo el
     primer par, ver docstring de analyze()).
  4. Compara epsilon_binning del par MAS FINO (el ultimo, ej. 16 vs 32)
     contra el presupuesto B_8_16<=2.5pp del plan para decidir el
     veredicto final (ver mas abajo la nota de alcance) -- un par mas
     fino que converge es evidencia mas fuerte que solo el primero.

DISEnO GENERALIZADO 2026-09-20 (antes: 8 y 16 hardcodeados en el codigo,
sin forma de agregar 32 sin reescribir el script) -- --n-bins-grid
acepta cualquier lista ordenada de enteros, no solo 2 valores. Con
"8,16" el comportamiento es identico al de antes de este cambio (un solo
par, un solo epsilon_binning). El plan pide explicitamente "si 8->16 es
limitrofe o 16 no parece estable: comprobar 16->32 antes de decidir" --
antes de este cambio, eso exigia correr el script dos veces con un
--n-bins fijo distinto cada vez y comparar los CSV a mano; ahora una
sola invocacion con la grilla completa da todos los pares de una vez.

BUG DE SEMILLAS CORREGIDO 2026-09-21: combo_idx (usado por seed_for())
solia ser la POSICION de cada combinacion dentro de --combos, no un id
fijo por especie/fase -- dos invocaciones de "las mismas" combinaciones
con --combos en distinto orden generaban semillas de Geant4 DISTINTAS
para cada una, sin ningun aviso. Confirmado con datos reales: la misma
combinacion GCR_H/min corrida en dos sesiones con --combos en orden
distinto dio epsilon_binning(8vs16) de 2.78% en una y 37.84% en la otra
-- no era evidencia de ruido/no-convergencia, eran dos experimentos con
semilla distinta comparados como si fueran el mismo. Corregido anclando
combo_idx a la posicion en run_organ_sweep.SPECIES_PHASE (ver
combo_idx_for()), no a --combos -- el resultado ya no depende del orden
del flag. CUALQUIER out-dir de Fase 8 generado antes de este fix
(2026-09-20 o anterior) quedo con semillas no reproducibles y debe
descartarse, no retomarse con --out-dir.

ALCANCE REDUCIDO respecto del plan completo, documentado explicitamente:
la Fase 8 del plan pide idealmente comparar el ENDPOINT shield/control
(eta_16 vs eta_8, B_8_16 = |eta_16-eta_8|) -- eso requiere el caso
"control" (field_scale=0), que este script AUN NO implementa (queda para
cuando la Fase 10 lo necesite de verdad). Por ahora se compara
epsilon_binning de la DOSIS ABSOLUTA (D_shield sola, sin dividir por
D_control) -- una aproximacion mas simple, mencionada en el propio plan
como la metrica "Para dosis" antes de la de "endpoint principal". El
mismo presupuesto de 2.5pp se aplica aqui como proxy provisional -- si
epsilon_binning(dosis) ya es alto, es evidencia suficiente de que la
grilla mas gruesa del par no alcanza sin necesitar la comparacion
completa con control.

Uso:
    python3 pilots/run_fase8_binning.py
    python3 pilots/run_fase8_binning.py --combos GCR_He/min,SEP_p/max
    python3 pilots/run_fase8_binning.py --n-events 10000 --threads 20
    python3 pilots/run_fase8_binning.py --n-bins-grid 16,32  # solo el par 16 vs 32

Costo: n_combos * suma(grilla) corridas independientes. Con la grilla
default (8+16+32=56) y los 3 combos default: 168 corridas -- bastante
mas caro que antes (72), ver --n-bins-grid para acotar a un subconjunto
(ej. "16,32" si 8 ya se descarto en una corrida previa) si el costo
completo no es necesario.
"""
import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
import energy_bins  # noqa: E402
import run_organ_sweep as ros  # noqa: E402
import pilot_common as pc  # noqa: E402
import pilot_state  # noqa: E402

PHASE_SEED_OFFSET = 10_000_000  # Fase 8 -- distinto del offset 0 de Fase 7

# Mismas combinaciones representativas que Fase 7, por consistencia --
# ver run_intrarun_pilot.py para el razonamiento de por que estas 3 (son
# las 3 combinaciones REALES de produccion, run_organ_sweep.py:SPECIES_PHASE
# -- SEP_p es MAX/Oct1989 aqui, no min; corregido 2026-09-20, un bug
# anterior tenia esto invertido).
DEFAULT_COMBOS = ["GCR_He/min/6", "SEP_p/max/0", "GCR_H/min/2"]

# Presupuesto de error de discretizacion, ver Fase 8 del plan (linea
# "usar provisionalmente como presupuesto de error de discretizacion:
# B_8_16 <= 2.5 pp") -- unico umbral EXPLICITAMENTE numerico entre las
# fases 7-10, por eso esta es la fase con el gate mas automatizable.
EPSILON_BUDGET_PCT = 2.5

# Zona de "limitrofe" alrededor del presupuesto -- ni tan claramente
# dentro como para descartar sin mirar, ni tan claramente fuera. Ancho
# elegido de forma conservadora (20% del propio presupuesto a cada
# lado) -- decision propia de implementacion, no un numero que venga del
# plan (el plan solo dice "si 8->16 es limitrofe", sin cuantificarlo).
EPSILON_MARGIN_PCT = 0.5


# Marcador de semilla por grilla -- FIJO por valor de n_bins, no por
# posicion dentro de --n-bins-grid (asi 8 y 16 siguen dando EXACTAMENTE
# las mismas semillas que antes de generalizar a mas de 2 grillas,
# 2026-09-20 -- retrocompatible con corridas ya hechas/manifest.csv
# existentes que dependen de esas semillas para el resume). Grillas mas
# alla de las listadas (ej. 64, si algun dia hace falta) caen al
# fallback determinista de abajo, sin colision con las ya asignadas.
_SEED_MARKER_BY_N_BINS = {8: 0, 16: 1, 32: 2}

# BUG REAL encontrado y corregido (2026-09-21): combo_idx solia ser
# enumerate(combos_spec), es decir la POSICION dentro de --combos, no un
# identificador fijo de la combinacion -- dos invocaciones de la misma
# combinacion species/phase con --combos en distinto orden generaban
# semillas de Geant4 DISTINTAS para "la misma" corrida (confirmado con
# datos reales: GCR_H/min en --combos "GCR_H/min,..." vs en --combos
# "...,GCR_H/min" broto epsilon_binning 8vs16 de 2.78% contra 37.84% --
# no era ruido MC ni evidencia de no convergencia, eran dos experimentos
# con distinta semilla comparados como si fueran el mismo). Corregido
# anclando combo_idx a la posicion de (species, phase) en
# run_organ_sweep.SPECIES_PHASE (la lista canonica ya usada en toda la
# produccion real, con orden estable documentado ahi) en vez de a
# --combos -- asi el resultado no depende del orden en que se pase el
# flag, sin importar quien corra el script o en que maquina.
#
# ROMPE retrocompatibilidad de semillas con manifest.csv generados ANTES
# de este fix (2026-09-20 y antes) -- estaban expuestos al mismo bug, asi
# que no son un dato valido que preservar: cualquier out-dir de Fase 8
# anterior a este commit debe descartarse y recorrerse desde cero, no
# retomarse con --out-dir/resume.
_COMBO_IDX_BY_SPECIES_PHASE = {sp: i for i, sp in enumerate(ros.SPECIES_PHASE)}


def combo_idx_for(species: str, phase: str) -> int:
    key = (species, phase)
    if key in _COMBO_IDX_BY_SPECIES_PHASE:
        return _COMBO_IDX_BY_SPECIES_PHASE[key]
    # Fallback para una combinacion fuera de SPECIES_PHASE (ej. un caso
    # experimental que production todavia no adopto) -- determinista por
    # hash del par, con offset para no colisionar con los indices reales
    # 0/1/2 de arriba.
    return len(_COMBO_IDX_BY_SPECIES_PHASE) + (hash(key) % 1000)


def seed_for(combo_idx: int, n_bins: int, bin_index: int) -> tuple[int, int]:
    """Determinista, sin repeticiones (esta fase no mide ruido MC) --
    n_bins entra en la formula para que corridas de grillas distintas
    nunca compartan semilla, aunque compartan bin_index. combo_idx debe
    venir de combo_idx_for(species, phase), NUNCA de la posicion en
    --combos (ver nota de bug arriba)."""
    if n_bins in _SEED_MARKER_BY_N_BINS:
        n_bins_marker = _SEED_MARKER_BY_N_BINS[n_bins]
    else:
        # Fallback para una grilla no listada arriba -- determinista
        # (mismo n_bins siempre da el mismo marcador) y sin colision con
        # los marcadores fijos 0/1/2, pero SIN garantia de no colisionar
        # entre si mismo si dos grillas no listadas caen en el mismo
        # modulo -- agregar la grilla nueva a _SEED_MARKER_BY_N_BINS
        # explicitamente si esto llega a usarse en produccion real.
        n_bins_marker = 3 + (n_bins % 1000)
    seed1 = pc.PILOT_BASE_SEED + PHASE_SEED_OFFSET + 100_000 * combo_idx + 10_000 * n_bins_marker + 2 * bin_index
    return seed1, seed1 + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--combos", type=str, default=",".join(DEFAULT_COMBOS),
                         help="Lista separada por comas de 'species/phase', ej. 'GCR_He/min,SEP_p/max'. "
                              "A diferencia de Fase 7, NO se fija un bin_index -- esta fase corre "
                              "TODOS los bins de cada grilla (8 y 16) para esa especie/fase. "
                              f"Default: {[c.rsplit('/', 1)[0] for c in DEFAULT_COMBOS]}")
    parser.add_argument("--n-bins-grid", type=str, default="8,16,32",
                         help="Lista ordenada de grillas a comparar, separadas por comas (default 8,16,32 -- "
                              "el plan pide 'si 8->16 es limitrofe o 16 no parece estable, comprobar 16->32 "
                              "antes de decidir'). epsilon_binning se calcula entre CADA PAR CONSECUTIVO "
                              "(8 vs 16, 16 vs 32, ...), y el veredicto final usa el ULTIMO par (el mas fino). "
                              "Pasar solo 2 valores (ej. '16,32') para acotar a un unico par -- util para "
                              "retomar/extender una corrida que ya descarto 8 bins en una invocacion previa.")
    parser.add_argument("--offset-x-m", type=float, default=0.0)
    parser.add_argument("--n-events", type=int, default=10000,
                         help="Eventos por corrida (default 10000, el mismo n_events de produccion -- "
                              "esta fase mide error de discretizacion, no necesita mas eventos que eso).")
    parser.add_argument("--field-map", type=Path, default=ros.DEFAULT_FIELD_MAP)
    parser.add_argument("--coil-geometry", type=Path, default=ros.DEFAULT_COIL_GEOMETRY)
    parser.add_argument("--no-coil-geometry", action="store_true")
    parser.add_argument("--build-dir", type=Path, default=None)
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--print-progress-every", type=int, default=500)
    parser.add_argument("--out-dir", type=Path, default=None,
                         help="Reusar un directorio de una corrida anterior (ej. cortada a mitad) "
                              "para retomarla -- ver --no-resume.")
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

    spectra_dir = project_root / "data" / "sources" / "oltaris"

    # combos_spec: lista de (species, phase) sin bin_index -- se corren
    # TODOS los bins de cada grilla.
    combos_spec = []
    for spec in args.combos.split(","):
        parts = spec.strip().split("/")
        if len(parts) != 2:
            sys.exit(f"ERROR: '{spec}' invalido -- Fase 8 espera 'species/phase', sin bin_index "
                      "(se corren todos los bins de cada grilla).")
        species, phase = parts
        combos_spec.append((species, phase))

    try:
        n_bins_grid = [int(x) for x in args.n_bins_grid.split(",")]
    except ValueError:
        sys.exit(f"ERROR: --n-bins-grid '{args.n_bins_grid}' invalido -- debe ser una lista de enteros "
                  "separados por comas, ej. '8,16,32'.")
    if len(n_bins_grid) < 2:
        sys.exit("ERROR: --n-bins-grid necesita al menos 2 valores para poder comparar un par "
                  "(epsilon_binning se calcula entre grillas consecutivas).")
    if any(n <= 0 for n in n_bins_grid) or n_bins_grid != sorted(n_bins_grid):
        sys.exit(f"ERROR: --n-bins-grid '{args.n_bins_grid}' debe ser una lista ORDENADA de enteros "
                  "positivos (ej. '8,16,32', no '16,8' ni '8,0,16').")

    out_dir, resuming = pc.resolve_out_dir(args, Path(__file__).resolve().parent, "fase8_binning")
    out_dir.mkdir(parents=True, exist_ok=True)
    macros_dir = out_dir / "macros"
    logs_dir = out_dir / "logs"
    outs_dir = out_dir / "outs"
    for d in (macros_dir, logs_dir, outs_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest.csv"
    manifest_fieldnames = ["species", "phase", "n_bins", "bin_index", "energy_mev",
                            "seed1", "seed2", "exit_code", "duration_s", "out_path"]
    key_fields = ["species", "phase", "n_bins", "bin_index"]
    done_keys = pc.load_done_keys(manifest_path, key_fields) if resuming else set()
    manifest_rows = pc.read_existing_manifest_rows(manifest_path) if resuming else []
    if resuming:
        print(f"Retomando {out_dir} -- {len(done_keys)} corrida(s) ya exitosa(s), se saltan "
              f"(usar --no-resume para rehacer todo).")

    # runs[(species, phase, n_bins)] = {bin_index: out_path}
    runs = {}
    total_runs = sum(sum(n_bins_grid) for _ in combos_spec)
    run_n = 0

    # Plan de trabajo completo (para el ETA total) -- work_unit identifica
    # la corrida de forma comparable entre invocaciones (mismo criterio
    # que la clave de reference_key()): "n_bins=N/bin=N".
    all_work = []
    for species, phase in combos_spec:
        for n_bins in n_bins_grid:
            bins = energy_bins.build_bins(spectra_dir, n_bins=n_bins)[(species, phase)]
            for bin_index, _energy_rep, _flux_bin in bins:
                key = (species, phase, str(n_bins), str(bin_index))
                combo_label = f"{species}/{phase}"
                work_unit = f"n_bins={n_bins}/bin={bin_index}"
                all_work.append((key, combo_label, work_unit))

    pending_work = [(combo_label, work_unit, args.n_events)
                     for key, combo_label, work_unit in all_work if key not in done_keys]
    eta_s, missing = pc.estimate_remaining_s("fase8", pending_work, score)
    if eta_s is not None:
        print(f"ETA del trabajo restante ({len(pending_work)} corrida(s)): ~{pc.format_eta(eta_s)}"
              + (f" ({missing} sin referencia previa, no incluida(s))" if missing else ""))
    elif pending_work:
        print(f"Sin referencia de tiempo previa para ninguna de las {len(pending_work)} corrida(s) "
              f"pendientes en esta maquina -- se ira midiendo y mostrando desde la primera.")

    for species, phase in combos_spec:
        combo_idx = combo_idx_for(species, phase)
        for n_bins in n_bins_grid:
            bins = energy_bins.build_bins(spectra_dir, n_bins=n_bins)[(species, phase)]
            for bin_index, energy_rep, _flux_bin in bins:
                run_n += 1
                out_path = outs_dir / f"{species}_{phase}_bins{n_bins}_bin{bin_index}.out"
                key = (species, phase, str(n_bins), str(bin_index))
                if key in done_keys:
                    print(f"\n[{run_n}/{total_runs}] {species}/{phase} n_bins={n_bins} bin={bin_index} "
                          f"-- YA HECHA (retomando), se salta")
                    runs.setdefault((species, phase, n_bins), {})[bin_index] = (out_path, 0)
                    continue

                seed1, seed2 = seed_for(combo_idx, n_bins, bin_index)
                combo = {"species": species, "phase": phase, "energy_mev": energy_rep}
                macro = pc.build_macro(
                    combo, args.offset_x_m, seed1, seed2, n_threads, args.print_progress_every,
                    field_map, coil_geometry, args.n_events, out_path,
                )
                macro_path = macros_dir / f"{species}_{phase}_bins{n_bins}_bin{bin_index}.mac"
                macro_path.write_text(macro)

                log_path = logs_dir / f"{species}_{phase}_bins{n_bins}_bin{bin_index}.log"
                print(f"\n[{run_n}/{total_runs}] {species}/{phase} n_bins={n_bins} bin={bin_index} "
                      f"E={energy_rep:.3e} MeV")
                print(f"    log completo en {log_path}")
                duration_s = pc.run_verbose(binary_path, macro_path, build_dir, log_path,
                                             out_path, args.n_events)
                exit_code = 0 if duration_s is not None else 1
                if duration_s is None:
                    duration_s = 0.0
                status = "OK" if exit_code == 0 else "FALLO"
                print(f"    -> {status}, {run_n}/{total_runs} corridas hechas, {duration_s:.1f}s")

                if exit_code == 0:
                    combo_label = f"{species}/{phase}"
                    work_unit = f"n_bins={n_bins}/bin={bin_index}"
                    pc.record_reference_duration("fase8", combo_label, work_unit,
                                                  args.n_events, duration_s, score)
                    done_keys.add(key)  # ya no cuenta como pendiente para el ETA restante
                    eta_s, missing = pc.estimate_remaining_s(
                        "fase8",
                        [(cl, wu, args.n_events) for k, cl, wu in all_work if k not in done_keys],
                        score,
                    )
                    n_left = sum(1 for k, _, _ in all_work if k not in done_keys)
                    if eta_s is not None:
                        print(f"    ETA restante ({n_left} corrida(s)): ~{pc.format_eta(eta_s)}"
                              + (f" ({missing} sin referencia)" if missing else ""))
                    elif n_left:
                        print(f"    ETA restante: sin referencia aun para ninguna de las "
                              f"{n_left} corrida(s) pendientes.")

                manifest_rows.append({
                    "species": species, "phase": phase, "n_bins": n_bins, "bin_index": bin_index,
                    "energy_mev": energy_rep, "seed1": seed1, "seed2": seed2,
                    "exit_code": exit_code, "duration_s": round(duration_s, 2), "out_path": str(out_path),
                })
                with open(manifest_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=manifest_fieldnames)
                    writer.writeheader()
                    writer.writerows(manifest_rows)

                key = (species, phase, n_bins)
                runs.setdefault(key, {})[bin_index] = (out_path, exit_code)

    print()
    print("Corridas completas. Analizando resultados...")
    # ros.SHIP_RADIUS_M/SHIP_HALF_LENGTH_M -- mismo escenario fijo de
    # produccion (ver run_organ_sweep.py), sin flag propio: esta fase no
    # cambia geometria de nave, solo el binning energetico.
    analyze(combos_spec, runs, spectra_dir, args.n_events, n_bins_grid,
            ros.SHIP_RADIUS_M, ros.SHIP_HALF_LENGTH_M, out_dir)


def source_area_cm2(ship_radius_m, ship_half_length_m, hull_thickness_cm=1.5):
    """Misma formula que aggregate_organ_doses.py -- area de la esfera
    fuente (radio = diagonal media + casco + margen de 20cm)."""
    ship_radius_cm = ship_radius_m * 100.0
    ship_half_length_cm = ship_half_length_m * 100.0
    source_radius_cm = math.sqrt(ship_radius_cm**2 + ship_half_length_cm**2) + hull_thickness_cm + 20.0
    return math.pi * source_radius_cm**2


def total_dose_for_grid(species, phase, n_bins, runs, spectra_dir, area_cm2, n_events):
    """D = suma_b W_b * R_b, con W_b = area_cm2 * flujo_integrado_del_bin
    (energy_bins.py) y R_b = edep_J_total_del_organo_relevante /
    (masa*N) -- aqui usa TotalDep (todos los organos del cuerpo, ya
    calculado por el scorer) en vez de un organo especifico, para dar
    una D agregada simple, suficiente para epsilon_binning. No separa
    por organo -- si hace falta esa granularidad, extender aqui."""
    bins = energy_bins.build_bins(spectra_dir, n_bins=n_bins)[(species, phase)]
    key = (species, phase, n_bins)
    total_d = 0.0
    missing = []
    for bin_index, _energy_rep, flux_bin in bins:
        if bin_index not in runs.get(key, {}):
            missing.append(bin_index)
            continue
        out_path, exit_code = runs[key][bin_index]
        if exit_code != 0 or not Path(out_path).is_file():
            missing.append(bin_index)
            continue
        rows = pc.parse_organ_table_full(Path(out_path))
        total_dep_j = sum(r["edep_J"] for oid, r in rows.items() if oid != 0)  # excluye Air (organo_id=0)
        w_b = area_cm2 * flux_bin
        r_b = total_dep_j / n_events  # Gy*kg-equivalente por primario -- sin dividir por masa (D relativa, ok para epsilon)
        total_d += r_b * w_b
    return total_d, missing


def analyze(combos_spec, runs, spectra_dir, n_events, n_bins_grid, ship_radius_m, ship_half_length_m, out_dir):
    """Calcula D_N para cada grilla de n_bins_grid, y epsilon_binning
    entre CADA PAR CONSECUTIVO (n_bins_grid[i] vs n_bins_grid[i+1]) --
    una fila por (combo, par) en vez de una columna fija D_8bins/D_16bins
    como antes de generalizar a mas de 2 grillas (2026-09-20). Con
    n_bins_grid=[8,16] da exactamente 1 fila por combo, igual que antes."""
    area_cm2 = source_area_cm2(ship_radius_m, ship_half_length_m)

    # Dosis por (combo, n_bins) -- calculada una sola vez por grilla,
    # reusada en los dos pares consecutivos que la involucran (ej. D_16
    # entra tanto en el par 8vs16 como en el par 16vs32).
    dose_by_combo_and_n = {}
    for species, phase in combos_spec:
        for n_bins in n_bins_grid:
            dose_by_combo_and_n[(species, phase, n_bins)] = total_dose_for_grid(
                species, phase, n_bins, runs, spectra_dir, area_cm2, n_events)

    resultado_rows = []
    resultado_fieldnames = ["species", "phase", "n_bins_lo", "n_bins_hi", "D_lo", "D_hi",
                             "epsilon_binning_pct", "bins_faltantes_lo", "bins_faltantes_hi"]
    for species, phase in combos_spec:
        for n_lo, n_hi in zip(n_bins_grid, n_bins_grid[1:]):
            d_lo, missing_lo = dose_by_combo_and_n[(species, phase, n_lo)]
            d_hi, missing_hi = dose_by_combo_and_n[(species, phase, n_hi)]
            eps_pct = (abs(d_hi - d_lo) / abs(d_hi) * 100.0) if d_hi != 0 else float("nan")
            resultado_rows.append({
                "species": species, "phase": phase, "n_bins_lo": n_lo, "n_bins_hi": n_hi,
                "D_lo": d_lo, "D_hi": d_hi, "epsilon_binning_pct": eps_pct,
                "bins_faltantes_lo": ";".join(map(str, missing_lo)),
                "bins_faltantes_hi": ";".join(map(str, missing_hi)),
            })

    resultado_path = out_dir / "epsilon_binning_por_combo.csv"
    with open(resultado_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resultado_fieldnames)
        writer.writeheader()
        writer.writerows(resultado_rows)
    print(f"  epsilon_binning por combo/par: {resultado_path}")

    write_fase8_state(resultado_rows, n_bins_grid, out_dir)


def write_fase8_state(resultado_rows, n_bins_grid, out_dir):
    """Gate AUTOMATIZABLE (a diferencia de Fase 7): el plan da un numero
    concreto (B_8_16<=2.5pp). Se aplica ese mismo umbral aqui a
    epsilon_binning(dosis) -- ver nota de alcance reducido en el
    docstring del modulo.

    Con mas de 2 grillas (2026-09-20): el veredicto FINAL se basa en el
    PAR MAS FINO (el ultimo de n_bins_grid, ej. 16 vs 32) -- es la
    evidencia mas fuerte de si la discretizacion ya convergio o si
    todavia hace falta subdividir mas. Los pares anteriores (ej. 8 vs 16)
    se resumen aparte, para contexto (ej. "8 vs 16 ya habia dado
    limitrofe, 16 vs 32 confirma que converge" es una historia distinta
    de "8 vs 16 parecia limitrofe, pero 16 vs 32 sigue sin converger --
    seguir subdividiendo")."""
    n_bins_lo_final, n_bins_hi_final = n_bins_grid[-2], n_bins_grid[-1]
    final_pair_rows = [r for r in resultado_rows if r["n_bins_hi"] == n_bins_hi_final]
    valid_rows = [r for r in final_pair_rows if r["epsilon_binning_pct"] == r["epsilon_binning_pct"]]  # filtra NaN

    # Resumen legible de pares anteriores (si los hay) -- no decide el
    # veredicto, solo da contexto en el resumen/detalle.
    earlier_pairs_summary = []
    earlier_pairs = list(zip(n_bins_grid[:-2], n_bins_grid[1:-1])) if len(n_bins_grid) > 2 else []
    for n_lo, n_hi in earlier_pairs:
        pair_rows = [r for r in resultado_rows
                     if r["n_bins_lo"] == n_lo and r["n_bins_hi"] == n_hi
                     and r["epsilon_binning_pct"] == r["epsilon_binning_pct"]]
        if pair_rows:
            max_eps_pair = max(r["epsilon_binning_pct"] for r in pair_rows)
            earlier_pairs_summary.append(f"{n_lo} vs {n_hi}: max={max_eps_pair:.3f}%")

    if not valid_rows:
        result = pilot_state.FaseResult(
            fase="fase8", veredicto=pilot_state.VERDICT_FALLO,
            resumen=(f"Sin epsilon_binning valido para el par final ({n_bins_lo_final} vs "
                     f"{n_bins_hi_final}) en ninguna combinacion -- revisar corridas fallidas."),
            detalle={"filas": resultado_rows, "pares_anteriores": earlier_pairs_summary},
            instrucciones_si_no_auto="Revisar manifest.csv/logs/ de esta corrida para ver que fallo.",
            out_dir=str(out_dir),
        )
        pilot_state.write_state(result)
        print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase8_estado.json'} (veredicto: FALLO)")
        return

    max_eps = max(r["epsilon_binning_pct"] for r in valid_rows)
    peor = max(valid_rows, key=lambda r: r["epsilon_binning_pct"])
    contexto = f" (pares anteriores: {'; '.join(earlier_pairs_summary)})" if earlier_pairs_summary else ""

    if max_eps <= EPSILON_BUDGET_PCT - EPSILON_MARGIN_PCT:
        veredicto = pilot_state.VERDICT_AUTO_CONTINUE
        resumen = (f"epsilon_binning({n_bins_lo_final} vs {n_bins_hi_final}) maximo={max_eps:.3f}% "
                   f"(peor caso: {peor['species']}/{peor['phase']}), claramente <= presupuesto "
                   f"{EPSILON_BUDGET_PCT}pp -- {n_bins_lo_final} bins ya son suficientes{contexto}.")
        instrucciones = (f"Continuar a Fase 9 (calibracion de M_b) con {n_bins_lo_final} bins, "
                          f"sin necesidad de {n_bins_hi_final}.")
    elif max_eps >= EPSILON_BUDGET_PCT + EPSILON_MARGIN_PCT:
        veredicto = pilot_state.VERDICT_REVISAR
        resumen = (f"epsilon_binning({n_bins_lo_final} vs {n_bins_hi_final}) maximo={max_eps:.3f}% "
                   f"(peor caso: {peor['species']}/{peor['phase']}), claramente > presupuesto "
                   f"{EPSILON_BUDGET_PCT}pp -- ni siquiera {n_bins_hi_final} bins alcanzan{contexto}.")
        instrucciones = (f"Adoptar {n_bins_hi_final} bins como candidato de todos modos NO es seguro -- "
                          f"el error de discretizacion sigue por encima del presupuesto incluso en el par "
                          f"mas fino corrido. Extender --n-bins-grid con un valor mayor (ej. "
                          f"'{n_bins_lo_final},{n_bins_hi_final},{n_bins_hi_final*2}') y volver a correr.")
    else:
        veredicto = pilot_state.VERDICT_LIMITROFE
        resumen = (f"epsilon_binning({n_bins_lo_final} vs {n_bins_hi_final}) maximo={max_eps:.3f}% "
                   f"(peor caso: {peor['species']}/{peor['phase']}), cerca del presupuesto "
                   f"{EPSILON_BUDGET_PCT}pp (dentro de +-{EPSILON_MARGIN_PCT}pp) -- limitrofe incluso en "
                   f"el par mas fino corrido{contexto}.")
        instrucciones = (f"Ver Fase 8 del plan, 'Si 8->16 es limitrofe o 16 no parece estable': seguir "
                          f"subdividiendo. Correr de nuevo con --n-bins-grid "
                          f"'{n_bins_lo_final},{n_bins_hi_final},{n_bins_hi_final*2}' para comprobar "
                          f"{n_bins_hi_final} vs {n_bins_hi_final*2} antes de decidir.")

    result = pilot_state.FaseResult(
        fase="fase8", veredicto=veredicto, resumen=resumen,
        detalle={"epsilon_binning_max_pct": max_eps, "peor_caso": f"{peor['species']}/{peor['phase']}",
                 "par_final": f"{n_bins_lo_final} vs {n_bins_hi_final}",
                 "presupuesto_pct": EPSILON_BUDGET_PCT, "margen_pct": EPSILON_MARGIN_PCT,
                 "pares_anteriores": earlier_pairs_summary, "filas": valid_rows},
        instrucciones_si_no_auto=instrucciones,
        out_dir=str(out_dir),
    )
    pilot_state.write_state(result)
    print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase8_estado.json'} (veredicto: {veredicto})")
    print(f"Resumen: {resumen}")


if __name__ == "__main__":
    main()
