#!/usr/bin/env python3
"""Fase 10 del plan estadistico (docs/bitacora/plan_estadistico.md):
Piloto B -- comprueba que los M_b fijados por la Fase 9 alcanzan para
resolver el ENDPOINT CIENTIFICO real (reduccion de dosis por blindaje
activo), no solo para estimar bien cada bin por separado.

    eta = 1 - D_shield/D_control
    H_eta,95 <= delta_eta/2 = 5 pp   (delta_eta=10pp, ya fijado en Fase 1)

Que hace, por cada combinacion (--combos, species/phase) y cada bin de la
malla definitiva:

  1. Corre "control" (field_scale=0, SIN blindaje activo -- mismo dominio
     y mapa de campo, solo escalado a cero, ver pilot_common.py) y
     "shield" (field_scale=1, blindaje a su valor de diseno), cada uno
     con M_b eventos (--m-b-csv, el archivo de la Fase 9, o --n-events
     fijo si todavia no se corrio Fase 9).
  2. Calcula D_control = suma_b W_b*R_b(control), D_shield = suma_b
     W_b*R_b(shield) -- misma formula que Fase 8, pero ahora con dos
     configuraciones de campo en vez de dos binnings.
  3. Calcula eta = 1 - D_shield/D_control.
  4. Propaga V(eta) con la formula del plan (control/shield
     independientes -- SIN common random numbers todavia, ver mas abajo):

         V(eta) ~= V(D_shield)/D_control^2 + D_shield^2*V(D_control)/D_control^4

     con V(D_k) = suma_b W_b^2 * SE_b(k)^2 (SE_b de cada corrida, via el
     estimador intra-run ya validado en el Piloto A).
  5. Compara H_eta,95 = 1.96*sqrt(V(eta)) (aproximacion normal, valida si
     el regimen MC de Fase 7 esta confirmado) contra delta_eta/2=5pp.

COMMON RANDOM NUMBERS (CRN): NO implementado en esta version -- el plan
lo menciona como optimizacion posible ("si la covarianza es positiva,
el pareamiento puede reducir sustancialmente la varianza de la
diferencia"), pero exige correr control y shield con la MISMA seed y
analizar la covarianza, una complejidad adicional que el plan mismo dice
que "el Piloto B debe determinar si esta estrategia realmente ayuda...
no se asume a priori" -- fuera de alcance de este primer corte. Con este
script, control y shield SI usan seeds distintas por diseño (ver
seed_for()), asi que V(eta) se calcula asumiendo independencia (formula
de arriba), sin covarianza.

Uso:
    python3 pilots/run_fase10_endpoint.py
    python3 pilots/run_fase10_endpoint.py --m-b-csv pilots/results/fase9_calibracion_mb_XXXX/m_b_propuesto.csv
    python3 pilots/run_fase10_endpoint.py --n-events 10000 --n-bins 8  # sin Fase 9 corrida todavia

Costo: n_combos * n_bins * 2 (control+shield) corridas. Con 3 combos, 8
bins: 48 corridas.
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

PHASE_SEED_OFFSET = 30_000_000  # Fase 10

DEFAULT_COMBOS = ["GCR_He/min", "SEP_p/min", "GCR_H/min"]

# delta_eta/2, ya fijado en Fase 1 del plan (delta_eta=10pp, criterio
# primario shield/control) -- NO redefinir aqui segun lo que salga del
# piloto (ver Fase 1, "Registrar que el piloto NO se utilizara para
# redefinir delta_eta segun el efecto observado").
H_ETA_BUDGET_PCT = 5.0


def seed_for(combo_idx: int, bin_index: int, is_shield: bool) -> tuple[int, int]:
    config_marker = 1 if is_shield else 0
    seed1 = pc.PILOT_BASE_SEED + PHASE_SEED_OFFSET + 100_000 * combo_idx + 10_000 * config_marker + 2 * bin_index
    return seed1, seed1 + 1


def load_mb_by_bin(m_b_csv: Path | None, default_n_events: int):
    """{(species,phase,bin_index): M_b} desde el CSV de Fase 9, o None si
    no se dio -- en ese caso cada bin usa default_n_events parejo (mismo
    fallback que ya existe como 'alternativa simple' en la Fase 9 del
    plan: M_b=10000 para todos)."""
    if m_b_csv is None:
        return {}
    mb = {}
    with open(m_b_csv, newline="") as f:
        for row in csv.DictReader(f):
            key = (row["species"], row["phase"], int(row["bin_index"]))
            mb[key] = int(row["M_b_propuesto"])
    return mb


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--combos", type=str, default=",".join(DEFAULT_COMBOS),
                         help=f"Lista de 'species/phase'. Default: {DEFAULT_COMBOS}")
    parser.add_argument("--n-bins", type=int, default=8,
                         help="Malla definitiva (default 8 -- ver resultado de Fase 8).")
    parser.add_argument("--m-b-csv", type=Path, default=None,
                         help="m_b_propuesto.csv de la Fase 9 -- si no se da, usa --n-events parejo "
                              "para todos los bins ('alternativa simple' del plan).")
    parser.add_argument("--n-events", type=int, default=10000,
                         help="M_b parejo si no se da --m-b-csv (default 10000, igual que produccion).")
    parser.add_argument("--offset-x-m", type=float, default=0.0)
    parser.add_argument("--field-map", type=Path, default=ros.DEFAULT_FIELD_MAP)
    parser.add_argument("--coil-geometry", type=Path, default=ros.DEFAULT_COIL_GEOMETRY)
    parser.add_argument("--no-coil-geometry", action="store_true")
    parser.add_argument("--build-dir", type=Path, default=None)
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--print-progress-every", type=int, default=500)
    parser.add_argument("--out-dir", type=Path, default=None,
                         help="Reusar un directorio de una corrida anterior para retomarla -- ver --no-resume.")
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
    mb_by_bin = load_mb_by_bin(args.m_b_csv, args.n_events)
    if not mb_by_bin:
        print(f"Sin --m-b-csv -- usando M_b={args.n_events} parejo para todos los bins "
              "('alternativa simple', ver Fase 9 del plan).")

    combos_spec = []
    for spec in args.combos.split(","):
        parts = spec.strip().split("/")
        if len(parts) != 2:
            sys.exit(f"ERROR: '{spec}' invalido -- Fase 10 espera 'species/phase'.")
        combos_spec.append(tuple(parts))

    out_dir, resuming = pc.resolve_out_dir(args, Path(__file__).resolve().parent, "fase10_endpoint")
    out_dir.mkdir(parents=True, exist_ok=True)
    macros_dir, logs_dir, outs_dir = out_dir / "macros", out_dir / "logs", out_dir / "outs"
    for d in (macros_dir, logs_dir, outs_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest.csv"
    manifest_fieldnames = ["species", "phase", "bin_index", "config", "m_b", "energy_mev",
                            "flux_bin", "seed1", "seed2", "exit_code", "duration_s", "out_path"]
    key_fields = ["species", "phase", "bin_index", "config"]
    done_keys = pc.load_done_keys(manifest_path, key_fields) if resuming else set()
    manifest_rows = pc.read_existing_manifest_rows(manifest_path) if resuming else []
    if resuming:
        print(f"Retomando {out_dir} -- {len(done_keys)} corrida(s) ya exitosa(s), se saltan "
              f"(usar --no-resume para rehacer todo).")

    # runs[(species,phase,config)][bin_index] = {...}
    runs = {}
    total_bins = sum(len(energy_bins.build_bins(spectra_dir, n_bins=args.n_bins)[sp]) for sp in combos_spec)
    total_runs = total_bins * 2  # control + shield
    run_n = 0

    # work_unit incluye config+bin (control y shield del mismo bin corren
    # el mismo M_b, pero son geometrias de campo distintas -- no deben
    # compartir referencia de duracion entre si).
    all_work = [
        ((species, phase, str(bin_index), config),
         f"{species}/{phase}", f"{config}/bin={bin_index}",
         mb_by_bin.get((species, phase, bin_index), args.n_events))
        for species, phase in combos_spec
        for bin_index, _e, _f in energy_bins.build_bins(spectra_dir, n_bins=args.n_bins)[(species, phase)]
        for config in ("control", "shield")
    ]
    pending_work = [(cl, wu, ne) for k, cl, wu, ne in all_work if k not in done_keys]
    eta_s, missing = pc.estimate_remaining_s("fase10", pending_work, score)
    if eta_s is not None:
        print(f"ETA del trabajo restante ({len(pending_work)} corrida(s)): ~{pc.format_eta(eta_s)}"
              + (f" ({missing} sin referencia previa, no incluida(s))" if missing else ""))
    elif pending_work:
        print(f"Sin referencia de tiempo previa para ninguna de las {len(pending_work)} corrida(s) "
              f"pendientes en esta maquina -- se ira midiendo y mostrando desde la primera.")

    for combo_idx, (species, phase) in enumerate(combos_spec):
        bins = energy_bins.build_bins(spectra_dir, n_bins=args.n_bins)[(species, phase)]
        for config, field_scale in (("control", 0.0), ("shield", 1.0)):
            runs.setdefault((species, phase, config), {})
            for bin_index, energy_rep, flux_bin in bins:
                run_n += 1
                m_b = mb_by_bin.get((species, phase, bin_index), args.n_events)
                out_path = outs_dir / f"{species}_{phase}_bin{bin_index}_{config}.out"
                key = (species, phase, str(bin_index), config)
                if key in done_keys:
                    print(f"\n[{run_n}/{total_runs}] {species}/{phase} bin={bin_index} {config} "
                          f"-- YA HECHA (retomando), se salta")
                    runs[(species, phase, config)][bin_index] = {"out_path": out_path, "m_b": m_b, "flux_bin": flux_bin}
                    continue

                seed1, seed2 = seed_for(combo_idx, bin_index, is_shield=(config == "shield"))
                combo = {"species": species, "phase": phase, "energy_mev": energy_rep}
                macro = pc.build_macro(
                    combo, args.offset_x_m, seed1, seed2, n_threads, args.print_progress_every,
                    field_map, coil_geometry, m_b, out_path, field_scale=field_scale,
                )
                macro_path = macros_dir / f"{species}_{phase}_bin{bin_index}_{config}.mac"
                macro_path.write_text(macro)

                log_path = logs_dir / f"{species}_{phase}_bin{bin_index}_{config}.log"
                print(f"\n[{run_n}/{total_runs}] {species}/{phase} bin={bin_index} {config} "
                      f"(field_scale={field_scale}) M_b={m_b}")
                print(f"    log completo en {log_path}")
                duration_s = pc.run_verbose(binary_path, macro_path, build_dir, log_path, out_path, m_b)
                exit_code = 0 if duration_s is not None else 1
                if duration_s is None:
                    duration_s = 0.0
                status = "OK" if exit_code == 0 else "FALLO"
                print(f"    -> {status}, {run_n}/{total_runs} corridas hechas, {duration_s:.1f}s")

                if exit_code == 0:
                    pc.record_reference_duration("fase10", f"{species}/{phase}",
                                                  f"{config}/bin={bin_index}", m_b, duration_s, score)
                    done_keys.add(key)
                    n_left = sum(1 for k, _cl, _wu, _ne in all_work if k not in done_keys)
                    eta_s, missing = pc.estimate_remaining_s(
                        "fase10", [(cl, wu, ne) for k, cl, wu, ne in all_work if k not in done_keys], score)
                    if eta_s is not None:
                        print(f"    ETA restante ({n_left} corrida(s)): ~{pc.format_eta(eta_s)}"
                              + (f" ({missing} sin referencia)" if missing else ""))
                    elif n_left:
                        print(f"    ETA restante: sin referencia aun para ninguna de las "
                              f"{n_left} corrida(s) pendientes.")

                manifest_rows.append({
                    "species": species, "phase": phase, "bin_index": bin_index, "config": config,
                    "m_b": m_b, "energy_mev": energy_rep, "flux_bin": flux_bin,
                    "seed1": seed1, "seed2": seed2, "exit_code": exit_code,
                    "duration_s": round(duration_s, 2), "out_path": str(out_path),
                })
                with open(manifest_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=manifest_fieldnames)
                    writer.writeheader()
                    writer.writerows(manifest_rows)

                if exit_code == 0:
                    runs[(species, phase, config)][bin_index] = {
                        "out_path": out_path, "m_b": m_b, "flux_bin": flux_bin,
                    }

    print()
    print("Corridas completas. Calculando eta e IC95%...")
    analyze(combos_spec, runs, out_dir)


def source_area_cm2(hull_thickness_cm=1.5):
    ship_radius_cm = ros.SHIP_RADIUS_M * 100.0
    ship_half_length_cm = ros.SHIP_HALF_LENGTH_M * 100.0
    source_radius_cm = math.sqrt(ship_radius_cm**2 + ship_half_length_cm**2) + hull_thickness_cm + 20.0
    return math.pi * source_radius_cm**2


def dose_and_variance(species, phase, config, runs, area_cm2):
    """D = suma_b W_b*R_b, V(D) = suma_b W_b^2*SE_b^2 -- bins
    independientes (semillas distintas por bin, ver seed_for())."""
    key = (species, phase, config)
    d_total, v_total = 0.0, 0.0
    missing = []
    for bin_index, data in runs.get(key, {}).items():
        out_path = data["out_path"]
        if not Path(out_path).is_file():
            missing.append(bin_index)
            continue
        rows = pc.parse_organ_table_full(Path(out_path))
        total_dep_j = sum(r["edep_J"] for oid, r in rows.items() if oid != 0)
        se_total = math.sqrt(sum(r.get("se_run_j", 0.0) ** 2 for oid, r in rows.items() if oid != 0))
        w_b = area_cm2 * data["flux_bin"]
        m_b = data["m_b"]
        r_b = total_dep_j / m_b
        se_r_b = se_total / m_b  # SE de R_b, no de la suma -- misma normalizacion que r_b
        d_total += r_b * w_b
        v_total += (w_b ** 2) * (se_r_b ** 2)
    return d_total, v_total, missing


def analyze(combos_spec, runs, out_dir):
    area_cm2 = source_area_cm2()

    resultado_rows = []
    resultado_fieldnames = ["species", "phase", "D_control", "V_D_control", "D_shield", "V_D_shield",
                             "eta_pct", "V_eta", "H_eta_95_pct", "bins_faltantes_control", "bins_faltantes_shield"]
    for species, phase in combos_spec:
        d0, v0, missing0 = dose_and_variance(species, phase, "control", runs, area_cm2)
        d1, v1, missing1 = dose_and_variance(species, phase, "shield", runs, area_cm2)
        if d0 == 0:
            eta_pct = float("nan")
            v_eta = float("nan")
            h_eta_pct = float("nan")
        else:
            eta = 1.0 - d1 / d0
            eta_pct = eta * 100.0
            # V(eta) ~= V(D1)/D0^2 + D1^2*V(D0)/D0^4 -- formula del plan,
            # asumiendo control/shield independientes (sin CRN, ver docstring).
            v_eta = (v1 / (d0 ** 2)) + ((d1 ** 2) * v0 / (d0 ** 4))
            h_eta_pct = 1.96 * math.sqrt(v_eta) * 100.0 if v_eta >= 0 else float("nan")
        resultado_rows.append({
            "species": species, "phase": phase, "D_control": d0, "V_D_control": v0,
            "D_shield": d1, "V_D_shield": v1, "eta_pct": eta_pct, "V_eta": v_eta,
            "H_eta_95_pct": h_eta_pct,
            "bins_faltantes_control": ";".join(map(str, missing0)),
            "bins_faltantes_shield": ";".join(map(str, missing1)),
        })

    resultado_path = out_dir / "eta_por_combo.csv"
    with open(resultado_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=resultado_fieldnames)
        writer.writeheader()
        writer.writerows(resultado_rows)
    print(f"  eta por combo: {resultado_path}")

    write_fase10_state(resultado_rows, out_dir)


def write_fase10_state(resultado_rows, out_dir):
    """Gate AUTOMATIZABLE (mismo espiritu que Fase 8): el plan da un
    numero concreto, H_eta,95 <= delta_eta/2 = 5pp."""
    valid_rows = [r for r in resultado_rows if r["H_eta_95_pct"] == r["H_eta_95_pct"]]  # filtra NaN
    if not valid_rows:
        result = pilot_state.FaseResult(
            fase="fase10", veredicto=pilot_state.VERDICT_FALLO,
            resumen="Sin H_eta,95 valido para ninguna combinacion (D_control=0 o corridas fallidas).",
            detalle={"filas": resultado_rows}, out_dir=str(out_dir),
            instrucciones_si_no_auto="Revisar manifest.csv/logs/ -- posible fallo de corridas o "
                                      "D_control=0 (bin demasiado barato, revisar --combos).",
        )
        pilot_state.write_state(result)
        print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase10_estado.json'} (veredicto: FALLO)")
        return

    max_h = max(r["H_eta_95_pct"] for r in valid_rows)
    peor = max(valid_rows, key=lambda r: r["H_eta_95_pct"])

    if max_h <= H_ETA_BUDGET_PCT:
        veredicto = pilot_state.VERDICT_AUTO_CONTINUE
        resumen = (f"H_eta,95 maximo={max_h:.3f}pp (peor caso: {peor['species']}/{peor['phase']}, "
                   f"eta={peor['eta_pct']:.1f}%), <= presupuesto {H_ETA_BUDGET_PCT}pp -- "
                   "precision suficiente para el endpoint principal.")
        instrucciones = ("Criterio cumplido -- los M_b de la Fase 9 son suficientes. "
                          "Continuar a produccion definitiva (Etapa F, desplegar phase + "
                          "sembrar GCR_H/max, GCR_He/max, SEP_p/min con estos M_b).")
    else:
        veredicto = pilot_state.VERDICT_REVISAR
        resumen = (f"H_eta,95 maximo={max_h:.3f}pp (peor caso: {peor['species']}/{peor['phase']}), "
                   f"> presupuesto {H_ETA_BUDGET_PCT}pp -- precision INSUFICIENTE, "
                   "NO se redefine delta_eta (ver Fase 1: prohibido).")
        instrucciones = (
            "Ver Fase 10 del plan, 'Si falla el criterio': identificar que terminos W_b^2*V_b dominan "
            "la varianza (mismo archivo que Fase 9 ya calculo, m_b_propuesto.csv, columna "
            "contribucion_varianza_W2sigma2) y aumentar M_b SOLO en esos bins -- formula del plan: "
            "M_nuevo ~= M_actual * (H_actual/H_objetivo)^2. Volver a correr esta fase con los M_b "
            "aumentados antes de produccion."
        )

    result = pilot_state.FaseResult(
        fase="fase10", veredicto=veredicto, resumen=resumen,
        detalle={"H_eta_95_max_pct": max_h, "peor_caso": f"{peor['species']}/{peor['phase']}",
                 "presupuesto_pct": H_ETA_BUDGET_PCT, "filas": valid_rows},
        instrucciones_si_no_auto=instrucciones, out_dir=str(out_dir),
    )
    pilot_state.write_state(result)
    print(f"\nEstado escrito: {pilot_state.STATE_DIR / 'fase10_estado.json'} (veredicto: {veredicto})")
    print(f"Resumen: {resumen}")


if __name__ == "__main__":
    main()
