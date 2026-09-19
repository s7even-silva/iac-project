#!/usr/bin/env python3
"""Fase 8 del plan estadistico (docs/bitacora/plan_estadistico.md):
convergencia del binning energetico -- determina si 8 bins son
suficientemente precisos, comparando contra 16 bins, ANTES de calibrar
M_b (Fase 9) o comprobar la precision shield/control (Fase 10). El
problema es de discretizacion, no de ruido Monte Carlo -- aumentar M no
lo arregla.

Que hace, por cada combinacion representativa (--combos):

  1. Corre TODOS los bins de la grilla de 8 (energy_bins.build_bins(...,
     n_bins=8)) y de la grilla de 16 (n_bins=16), cada uno con --n-events
     eventos, UNA sola vez (sin repeticiones -- esta fase mide error de
     discretizacion, no ruido MC; el ruido MC ya se abordo en la Fase 7).
  2. Calcula D_8 = suma_b W_b(8bins) * R_b y D_16 = suma_b W_b(16bins) * R_b
     -- misma formula fisica que aggregate_organ_doses.py, reproducida
     aqui porque ese script no esta estructurado como libreria reusable
     (todo vive en su main()).
  3. Calcula epsilon_binning = |D_16 - D_8| / |D_16| POR combinacion.
  4. Compara epsilon_binning (agregado, la METRICA REAL disponible en
     esta fase) contra el presupuesto B_8_16<=2.5pp del plan (ver mas
     abajo la nota de alcance).

ALCANCE REDUCIDO respecto del plan completo, documentado explicitamente:
la Fase 8 del plan pide idealmente comparar el ENDPOINT shield/control
(eta_16 vs eta_8, B_8_16 = |eta_16-eta_8|) -- eso requiere el caso
"control" (field_scale=0), que este script AUN NO implementa (queda para
cuando la Fase 10 lo necesite de verdad). Por ahora se compara
epsilon_binning de la DOSIS ABSOLUTA (D_shield sola, sin dividir por
D_control) -- una aproximacion mas simple, mencionada en el propio plan
como la metrica "Para dosis" antes de la de "endpoint principal". El
mismo presupuesto de 2.5pp se aplica aqui como proxy provisional -- si
epsilon_binning(dosis) ya es alto, es evidencia suficiente de que 8 bins
no alcanzan sin necesitar la comparacion completa con control.

Uso:
    python3 pilots/run_fase8_binning.py
    python3 pilots/run_fase8_binning.py --combos GCR_He/min/6,SEP_p/min/0
    python3 pilots/run_fase8_binning.py --n-events 10000 --threads 20

Costo: n_combos * (8+16) corridas independientes = n_combos*24 corridas.
Con los 3 combos default: 72 corridas.
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
# ver run_intrarun_pilot.py para el razonamiento de por que estas 3.
DEFAULT_COMBOS = ["GCR_He/min/6", "SEP_p/min/0", "GCR_H/min/2"]

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


def seed_for(combo_idx: int, n_bins: int, bin_index: int) -> tuple[int, int]:
    """Determinista, sin repeticiones (esta fase no mide ruido MC) --
    n_bins (8 o 16) entra en la formula para que las corridas de las dos
    grillas nunca compartan semilla, aunque compartan bin_index."""
    n_bins_marker = 0 if n_bins == 8 else 1
    seed1 = pc.PILOT_BASE_SEED + PHASE_SEED_OFFSET + 100_000 * combo_idx + 10_000 * n_bins_marker + 2 * bin_index
    return seed1, seed1 + 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--combos", type=str, default=",".join(DEFAULT_COMBOS),
                         help="Lista separada por comas de 'species/phase', ej. 'GCR_He/min,SEP_p/min'. "
                              "A diferencia de Fase 7, NO se fija un bin_index -- esta fase corre "
                              "TODOS los bins de cada grilla (8 y 16) para esa especie/fase. "
                              f"Default: {[c.rsplit('/', 1)[0] for c in DEFAULT_COMBOS]}")
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
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    import os
    n_threads = args.threads or os.cpu_count()

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

    out_dir = args.out_dir or (
        Path(__file__).resolve().parent / "results" /
        f"fase8_binning_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    macros_dir = out_dir / "macros"
    logs_dir = out_dir / "logs"
    outs_dir = out_dir / "outs"
    for d in (macros_dir, logs_dir, outs_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    manifest_path = out_dir / "manifest.csv"
    manifest_fieldnames = ["species", "phase", "n_bins", "bin_index", "energy_mev",
                            "seed1", "seed2", "exit_code", "duration_s", "out_path"]

    # runs[(species, phase, n_bins)] = {bin_index: out_path}
    runs = {}
    total_runs = sum(8 + 16 for _ in combos_spec)
    run_n = 0
    for combo_idx, (species, phase) in enumerate(combos_spec):
        for n_bins in (8, 16):
            bins = energy_bins.build_bins(spectra_dir, n_bins=n_bins)[(species, phase)]
            for bin_index, energy_rep, _flux_bin in bins:
                run_n += 1
                seed1, seed2 = seed_for(combo_idx, n_bins, bin_index)
                out_path = outs_dir / f"{species}_{phase}_bins{n_bins}_bin{bin_index}.out"
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
    analyze(combos_spec, runs, spectra_dir, args.n_events,
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


def analyze(combos_spec, runs, spectra_dir, n_events, ship_radius_m, ship_half_length_m, out_dir):
    area_cm2 = source_area_cm2(ship_radius_m, ship_half_length_m)

    resultado_rows = []
    resultado_fieldnames = ["species", "phase", "D_8bins", "D_16bins",
                             "epsilon_binning_pct", "bins_faltantes_8", "bins_faltantes_16"]
    for species, phase in combos_spec:
        d8, missing8 = total_dose_for_grid(species, phase, 8, runs, spectra_dir, area_cm2, n_events)
        d16, missing16 = total_dose_for_grid(species, phase, 16, runs, spectra_dir, area_cm2, n_events)
        eps_pct = (abs(d16 - d8) / abs(d16) * 100.0) if d16 != 0 else float("nan")
        resultado_rows.append({
            "species": species, "phase": phase, "D_8bins": d8, "D_16bins": d16,
            "epsilon_binning_pct": eps_pct,
            "bins_faltantes_8": ";".join(map(str, missing8)),
            "bins_faltantes_16": ";".join(map(str, missing16)),
        })

    resultado_path = out_dir / "epsilon_binning_por_combo.csv"
    with open(resultado_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resultado_fieldnames)
        writer.writeheader()
        writer.writerows(resultado_rows)
    print(f"  epsilon_binning por combo: {resultado_path}")

    write_fase8_state(resultado_rows, out_dir)


def write_fase8_state(resultado_rows, out_dir):
    """Gate AUTOMATIZABLE (a diferencia de Fase 7): el plan da un numero
    concreto (B_8_16<=2.5pp). Se aplica ese mismo umbral aqui a
    epsilon_binning(dosis) -- ver nota de alcance reducido en el
    docstring del modulo."""
    valid_rows = [r for r in resultado_rows if r["epsilon_binning_pct"] == r["epsilon_binning_pct"]]  # filtra NaN
    if not valid_rows:
        result = pilot_state.FaseResult(
            fase="fase8", veredicto=pilot_state.VERDICT_FALLO,
            resumen="Sin epsilon_binning valido para ninguna combinacion -- revisar corridas fallidas.",
            detalle={"filas": resultado_rows},
            instrucciones_si_no_auto="Revisar manifest.csv/logs/ de esta corrida para ver que fallo.",
            out_dir=str(out_dir),
        )
        pilot_state.write_state(result)
        print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase8_estado.json'} (veredicto: FALLO)")
        return

    max_eps = max(r["epsilon_binning_pct"] for r in valid_rows)
    peor = max(valid_rows, key=lambda r: r["epsilon_binning_pct"])

    if max_eps <= EPSILON_BUDGET_PCT - EPSILON_MARGIN_PCT:
        veredicto = pilot_state.VERDICT_AUTO_CONTINUE
        resumen = (f"epsilon_binning maximo={max_eps:.3f}% (peor caso: {peor['species']}/{peor['phase']}), "
                   f"claramente <= presupuesto {EPSILON_BUDGET_PCT}pp -- 8 bins suficientes.")
        instrucciones = "Continuar a Fase 9 (calibracion de M_b) con 8 bins, sin comprobar 16 bins."
    elif max_eps >= EPSILON_BUDGET_PCT + EPSILON_MARGIN_PCT:
        veredicto = pilot_state.VERDICT_REVISAR
        resumen = (f"epsilon_binning maximo={max_eps:.3f}% (peor caso: {peor['species']}/{peor['phase']}), "
                   f"claramente > presupuesto {EPSILON_BUDGET_PCT}pp -- 8 bins NO suficientes.")
        instrucciones = ("Adoptar 16 bins como candidato (ver Fase 8 del plan, 'Si 8 bins no cumplen'). "
                          "Puede hacer falta comprobar 16->32 tambien -- correr un script equivalente "
                          "comparando 16 vs 32 antes de congelar el binning definitivo (no implementado "
                          "todavia, extender run_fase8_binning.py con --n-bins-pair 16,32 si hace falta).")
    else:
        veredicto = pilot_state.VERDICT_LIMITROFE
        resumen = (f"epsilon_binning maximo={max_eps:.3f}% (peor caso: {peor['species']}/{peor['phase']}), "
                   f"cerca del presupuesto {EPSILON_BUDGET_PCT}pp (dentro de +-{EPSILON_MARGIN_PCT}pp) -- "
                   "limitrofe, el plan pide comprobar 16->32 en este caso.")
        instrucciones = ("Ver Fase 8 del plan, 'Si 8->16 es limitrofe o 16 no parece estable': "
                          "comprobar 16->32 antes de decidir. No implementado todavia en este script -- "
                          "extender run_fase8_binning.py o correr manualmente con --combos y una grilla de 32.")

    result = pilot_state.FaseResult(
        fase="fase8", veredicto=veredicto, resumen=resumen,
        detalle={"epsilon_binning_max_pct": max_eps, "peor_caso": f"{peor['species']}/{peor['phase']}",
                 "presupuesto_pct": EPSILON_BUDGET_PCT, "margen_pct": EPSILON_MARGIN_PCT,
                 "filas": valid_rows},
        instrucciones_si_no_auto=instrucciones,
        out_dir=str(out_dir),
    )
    pilot_state.write_state(result)
    print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase8_estado.json'} (veredicto: {veredicto})")
    print(f"Resumen: {resumen}")


if __name__ == "__main__":
    main()
