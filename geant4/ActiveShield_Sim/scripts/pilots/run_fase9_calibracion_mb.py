#!/usr/bin/env python3
"""Fase 9 del plan estadistico (docs/bitacora/plan_estadistico.md):
calibracion del numero de eventos M_b por bin, sobre el binning YA
CONGELADO por la Fase 8 (8 o 16 bins segun ese resultado).

Objetivo (formula del plan):

    V(D) = suma_b W_b^2 * sigma_b^2 / M_b
    M_b proporcional a |W_b| * sigma_b / sqrt(c_b)

Necesita, para CADA bin de la malla definitiva (no solo los 3 combos
puntuales del Piloto A -- ver Fase 9 del plan, checklist: "Medir SE_b(M)
para bins representativos" en la malla DEFINITIVA, que recien se conoce
al final de la Fase 8):

  - sigma_b: desviacion estandar de la dosis de ese bin -- estimada aqui
    con el MISMO metodo validado en el Piloto A (Fase 7): SE_within de
    una corrida instrumentada (S1/S2/N del scorer), NO requiere
    repeticiones nuevas si el Piloto A ya valido que SE_within es
    confiable -- si Fase 7 dio veredicto REVISAR/LIMITROFE sin que el
    equipo lo haya confirmado, este script lo advierte explicitamente
    antes de calcular nada (ver check_fase7_validated()).
  - W_b: peso fisico del bin (energy_bins.py, ya calculado).
  - c_b: costo por evento -- medido DIRECTO de esta misma corrida
    (duration_s / n_events de cada bin), no de REFERENCE_TIMINGS_S
    (que es de otra maquina/config) -- mas preciso para la maquina real
    donde se esta corriendo esto.

Que hace, por cada combinacion (--combos, formato species/phase):

  1. Corre TODOS los bins de la malla definitiva (--n-bins, default 8 --
     cambiar a 16 si la Fase 8 dio veredicto REVISAR/LIMITROFE y el
     equipo decidio 16 bins) con --n-events-probe eventos cada uno (un
     numero moderado, no el M_b final -- esto es una corrida de SONDEO
     para estimar sigma_b/c_b, no la produccion real).
  2. Calcula sigma_b (via SE_within * sqrt(n_events_probe), la relacion
     SE=sigma/sqrt(N) invertida) y c_b (segundos/evento medido) por bin.
  3. Calcula W_b^2*sigma_b^2 (contribucion de cada bin a la varianza) e
     identifica los bins dominantes.
  4. Calcula M_b propuesto = M_min * (peso_b / min(peso_b)), con
     peso_b = |W_b|*sigma_b/sqrt(c_b) normalizado -- ver
     calcular_mb_propuesto() para el detalle exacto y M_min (piso minimo
     para evitar tallies patologicamente escasos, ver checklist del plan).

Uso:
    python3 pilots/run_fase9_calibracion_mb.py
    python3 pilots/run_fase9_calibracion_mb.py --n-bins 16   # si Fase 8 eligio 16
    python3 pilots/run_fase9_calibracion_mb.py --n-events-probe 5000 --threads 20

Costo: n_combos * n_bins corridas de sondeo (--n-events-probe eventos
cada una). Con los defaults (3 combos, 8 bins, n_events_probe=5000): 24
corridas.
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

PHASE_SEED_OFFSET = 20_000_000  # Fase 9

DEFAULT_COMBOS = ["GCR_He/min", "SEP_p/min", "GCR_H/min"]

# Piso minimo de M_b -- "mantener un minimo de historias que evite
# tallies patologicamente escasos" (checklist del plan). Mismo orden de
# magnitud que el bin mas barato ya usado en produccion (n_events=10000
# de run_organ_sweep.py), no un numero arbitrario.
M_MIN = 2500
M_MAX = 20000  # tope superior -- mismo M_max del Piloto A, evita M_b absurdamente grandes por un sigma_b atipico


def seed_for(combo_idx: int, bin_index: int) -> tuple[int, int]:
    seed1 = pc.PILOT_BASE_SEED + PHASE_SEED_OFFSET + 100_000 * combo_idx + 2 * bin_index
    return seed1, seed1 + 1


def check_fase7_validated():
    """Advertencia (NO bloqueante -- esta fase puede correr igual, el
    equipo puede decidir seguir adelante a sabiendas) si Fase 7 no dejo
    un veredicto que sugiera que SE_within es confiable. sigma_b aqui se
    deriva de SE_within, asi que si esa maquinaria no esta validada,
    M_b calculado aqui hereda esa incertidumbre."""
    result = pilot_state.read_state("fase7")
    if result is None:
        print("ADVERTENCIA: no se encontro pilots/results/state/fase7_estado.json -- "
              "esta fase usa SE_within (Piloto A) para estimar sigma_b sin haber confirmado "
              "que ese estimador sea confiable. Correr run_intrarun_pilot.py primero, o "
              "continuar a sabiendas si ya se reviso por otro medio.")
        return
    if result.veredicto != pilot_state.VERDICT_AUTO_CONTINUE:
        print(f"ADVERTENCIA: Fase 7 (Piloto A) tiene veredicto '{result.veredicto}', no AUTO_CONTINUE "
              f"-- resumen: {result.resumen}")
        print("  sigma_b en esta fase se deriva de SE_within -- si el equipo no confirmo que ese "
              "estimador es confiable, M_b calculado aqui hereda esa incertidumbre. Continuando "
              "de todos modos (esta advertencia no bloquea, ver docstring del modulo).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--combos", type=str, default=",".join(DEFAULT_COMBOS),
                         help=f"Lista de 'species/phase' (todos los bins de la malla). Default: {DEFAULT_COMBOS}")
    parser.add_argument("--n-bins", type=int, default=8,
                         help="Malla definitiva ya congelada por Fase 8 (default 8 -- cambiar a 16 "
                              "si Fase 8 dio veredicto distinto de AUTO_CONTINUE y el equipo decidio 16).")
    parser.add_argument("--offset-x-m", type=float, default=0.0)
    parser.add_argument("--n-events-probe", type=int, default=5000,
                         help="Eventos de la corrida de SONDEO por bin (default 5000, NO es M_b final "
                              "-- ver docstring del modulo).")
    parser.add_argument("--field-map", type=Path, default=ros.DEFAULT_FIELD_MAP)
    parser.add_argument("--coil-geometry", type=Path, default=ros.DEFAULT_COIL_GEOMETRY)
    parser.add_argument("--no-coil-geometry", action="store_true")
    parser.add_argument("--build-dir", type=Path, default=None)
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--print-progress-every", type=int, default=500)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    check_fase7_validated()

    import os
    n_threads = args.threads or os.cpu_count()

    project_root = Path(__file__).resolve().parent.parent.parent
    build_dir, binary_path, field_map, coil_geometry = pc.resolve_paths(args, project_root)
    pc.check_scorer_has_intrarun_columns(build_dir, binary_path)

    spectra_dir = project_root / "data" / "sources" / "oltaris"

    combos_spec = []
    for spec in args.combos.split(","):
        parts = spec.strip().split("/")
        if len(parts) != 2:
            sys.exit(f"ERROR: '{spec}' invalido -- Fase 9 espera 'species/phase', sin bin_index.")
        combos_spec.append(tuple(parts))

    out_dir = args.out_dir or (
        Path(__file__).resolve().parent / "results" /
        f"fase9_calibracion_mb_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    macros_dir, logs_dir, outs_dir = out_dir / "macros", out_dir / "logs", out_dir / "outs"
    for d in (macros_dir, logs_dir, outs_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    manifest_path = out_dir / "manifest.csv"
    manifest_fieldnames = ["species", "phase", "bin_index", "energy_mev", "flux_bin",
                            "seed1", "seed2", "exit_code", "duration_s", "out_path"]

    total_runs = len(combos_spec) * args.n_bins
    run_n = 0
    # runs[(species,phase)][bin_index] = {"out_path", "duration_s", "energy_mev", "flux_bin"}
    runs = {}
    for combo_idx, (species, phase) in enumerate(combos_spec):
        bins = energy_bins.build_bins(spectra_dir, n_bins=args.n_bins)[(species, phase)]
        runs[(species, phase)] = {}
        for bin_index, energy_rep, flux_bin in bins:
            run_n += 1
            seed1, seed2 = seed_for(combo_idx, bin_index)
            out_path = outs_dir / f"{species}_{phase}_bin{bin_index}.out"
            combo = {"species": species, "phase": phase, "energy_mev": energy_rep}
            macro = pc.build_macro(
                combo, args.offset_x_m, seed1, seed2, n_threads, args.print_progress_every,
                field_map, coil_geometry, args.n_events_probe, out_path,
            )
            macro_path = macros_dir / f"{species}_{phase}_bin{bin_index}.mac"
            macro_path.write_text(macro)

            log_path = logs_dir / f"{species}_{phase}_bin{bin_index}.log"
            print(f"\n[{run_n}/{total_runs}] {species}/{phase} bin={bin_index} E={energy_rep:.3e} MeV")
            print(f"    log completo en {log_path}")
            duration_s = pc.run_verbose(binary_path, macro_path, build_dir, log_path,
                                         out_path, args.n_events_probe)
            exit_code = 0 if duration_s is not None else 1
            if duration_s is None:
                duration_s = 0.0
            status = "OK" if exit_code == 0 else "FALLO"
            print(f"    -> {status}, {run_n}/{total_runs} corridas hechas, {duration_s:.1f}s")

            manifest_rows.append({
                "species": species, "phase": phase, "bin_index": bin_index, "energy_mev": energy_rep,
                "flux_bin": flux_bin, "seed1": seed1, "seed2": seed2,
                "exit_code": exit_code, "duration_s": round(duration_s, 2), "out_path": str(out_path),
            })
            with open(manifest_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=manifest_fieldnames)
                writer.writeheader()
                writer.writerows(manifest_rows)

            if exit_code == 0:
                runs[(species, phase)][bin_index] = {
                    "out_path": out_path, "duration_s": duration_s,
                    "energy_mev": energy_rep, "flux_bin": flux_bin,
                }

    print()
    print("Corridas completas. Calculando M_b...")
    analyze(combos_spec, runs, args.n_events_probe, args.n_bins, out_dir)


def source_area_cm2(ship_radius_m=None, ship_half_length_m=None, hull_thickness_cm=1.5):
    ship_radius_m = ship_radius_m or ros.SHIP_RADIUS_M
    ship_half_length_m = ship_half_length_m or ros.SHIP_HALF_LENGTH_M
    ship_radius_cm = ship_radius_m * 100.0
    ship_half_length_cm = ship_half_length_m * 100.0
    source_radius_cm = math.sqrt(ship_radius_cm**2 + ship_half_length_cm**2) + hull_thickness_cm + 20.0
    return math.pi * source_radius_cm**2


def analyze(combos_spec, runs, n_events_probe, n_bins, out_dir):
    area_cm2 = source_area_cm2()

    mb_rows = []
    mb_fieldnames = ["species", "phase", "bin_index", "energy_mev", "W_b", "sigma_b_J",
                      "c_b_s_per_event", "contribucion_varianza_W2sigma2", "peso_asignacion",
                      "M_b_propuesto"]

    # Primero: recolectar sigma_b/c_b/W_b de TODOS los bins de TODAS las
    # combinaciones -- la normalizacion de M_b (relativa al bin mas barato)
    # es GLOBAL, no por combinacion, porque compiten por el mismo
    # presupuesto de computo total.
    raw = []  # [(species, phase, bin_index, energy_mev, w_b, sigma_b, c_b)]
    for (species, phase), bins_data in runs.items():
        for bin_index, data in bins_data.items():
            out_path = data["out_path"]
            if not Path(out_path).is_file():
                continue
            rows = pc.parse_organ_table_full(Path(out_path))
            # sigma_b agregado sobre TODOS los organos del cuerpo (excluye
            # Air, organo_id=0) -- suma de varianzas de organos
            # independientes (mismo criterio que aggregate_organ_doses.py
            # Fase 2/3: V(suma) = suma V si son independientes).
            se_total_sq = sum(r.get("se_run_j", 0.0) ** 2 for oid, r in rows.items() if oid != 0)
            sigma_b = math.sqrt(se_total_sq) * math.sqrt(n_events_probe)  # SE = sigma/sqrt(N) invertido
            w_b = area_cm2 * data["flux_bin"]
            c_b = data["duration_s"] / n_events_probe if n_events_probe else float("nan")
            raw.append((species, phase, bin_index, data["energy_mev"], w_b, sigma_b, c_b))

    if not raw:
        write_fase9_state([], out_dir)
        return

    # peso_b = |W_b|*sigma_b/sqrt(c_b) -- formula del plan.
    pesos = []
    for species, phase, bin_index, energy_mev, w_b, sigma_b, c_b in raw:
        peso = (abs(w_b) * sigma_b / math.sqrt(c_b)) if c_b > 0 else 0.0
        pesos.append(peso)
    min_peso_nonzero = min((p for p in pesos if p > 0), default=1.0)

    for (species, phase, bin_index, energy_mev, w_b, sigma_b, c_b), peso in zip(raw, pesos):
        contrib_var = (w_b ** 2) * (sigma_b ** 2)
        m_b = M_MIN * (peso / min_peso_nonzero) if min_peso_nonzero > 0 else M_MIN
        m_b = max(M_MIN, min(M_MAX, round(m_b)))
        mb_rows.append({
            "species": species, "phase": phase, "bin_index": bin_index, "energy_mev": energy_mev,
            "W_b": w_b, "sigma_b_J": sigma_b, "c_b_s_per_event": c_b,
            "contribucion_varianza_W2sigma2": contrib_var, "peso_asignacion": peso,
            "M_b_propuesto": m_b,
        })

    mb_rows.sort(key=lambda r: -r["contribucion_varianza_W2sigma2"])
    mb_path = out_dir / "m_b_propuesto.csv"
    with open(mb_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=mb_fieldnames)
        writer.writeheader()
        writer.writerows(mb_rows)
    print(f"  M_b propuesto: {mb_path}")

    write_fase9_state(mb_rows, out_dir)


def write_fase9_state(mb_rows, out_dir):
    """Fase 9 SIEMPRE termina en REVISAR (nunca AUTO_CONTINUE) -- el plan
    exige explicitamente 'Documentar los M_b definitivos' antes de seguir
    a Fase 10, que es una decision de equipo (fijar el presupuesto de
    computo real, no solo la formula), no algo que este script pueda
    decidir solo."""
    if not mb_rows:
        result = pilot_state.FaseResult(
            fase="fase9", veredicto=pilot_state.VERDICT_FALLO,
            resumen="Sin datos -- ninguna corrida de sondeo produjo resultados utilizables.",
            out_dir=str(out_dir),
        )
        pilot_state.write_state(result)
        print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase9_estado.json'} (veredicto: FALLO)")
        return

    top3 = mb_rows[:3]
    top3_str = ", ".join(f"{r['species']}/{r['phase']}/bin{r['bin_index']}" for r in top3)
    result = pilot_state.FaseResult(
        fase="fase9", veredicto=pilot_state.VERDICT_REVISAR,
        resumen=(f"M_b propuesto para {len(mb_rows)} bins. Bins que dominan la varianza: {top3_str}. "
                 "El plan exige documentar los M_b definitivos antes de Fase 10 -- decision de equipo, "
                 "no automatizable (el presupuesto de computo real depende de cuanto tiempo/maquinas hay)."),
        detalle={"n_bins": len(mb_rows), "bins_dominantes": top3},
        instrucciones_si_no_auto=(
            f"Revisar {out_dir / 'm_b_propuesto.csv'}, decidir los M_b definitivos (la formula da una "
            "PROPUESTA, no un numero final -- el equipo puede recortar M_MAX/ajustar el piso M_MIN "
            "segun el presupuesto de computo real disponible). Documentar la decision en "
            "docs/bitacora/plan_estadistico.md (Fase 9, 'Documentar los M_b definitivos') y correr "
            "run_pilot_workflow.py --continue-to fase10 con los M_b elegidos."
        ),
        out_dir=str(out_dir),
    )
    pilot_state.write_state(result)
    print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase9_estado.json'} (veredicto: REVISAR)")
    print(f"Resumen: {result.resumen}")


if __name__ == "__main__":
    main()
