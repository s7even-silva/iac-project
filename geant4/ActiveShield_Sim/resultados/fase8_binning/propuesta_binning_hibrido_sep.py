#!/usr/bin/env python3
"""PROPUESTA todavia NO decidida ni validada con simulacion real -- ver
docs/bitacora/plan_estadistico.md, Fase 8, seccion "Propuesta: binning
no uniforme para SEP_p". Este script solo ESTIMA que tan bien funcionaria
un esquema de binning no uniforme para SEP_p, reusando los 128 bins ya
medidos (resultados_organo_sweep_fase8_binning.csv) -- no corre Geant4.

Motivacion: el binning log-uniforme actual necesita 64 bins para bajar
epsilon_binning a 4.22% (todavia arriba del presupuesto 2.5pp, y la mejora
64->128 resulto compatible con ruido MC, no señal real -- ver Fase 8). El
99% de la dosis de SEP_p viene de una franja angosta del espectro
(64.95-300 MeV de un rango tabulado de 0.01-300 MeV), asi que un binning
uniforme le da muy pocos bins utiles a esa franja. La alternativa: un
esquema de 2 segmentos log-espaciados (pocos bins en 0.01-<corte> MeV,
la mayoria en <corte>-300 MeV).

Metodo de estimacion (sin nueva simulacion):
  Cada bin real corrido usa UN energia representativa (media geometrica de
  sus bordes, ver energy_bins.bin_representative_energy) para aproximar
  R(E) en todo el ancho del bin -- ese es el origen del error de binning
  (R(E) no es constante dentro del bin). Para estimar un esquema de bins
  NUEVO sin correrlo: se interpola R(E) en log-log usando los 128 puntos
  (e_rep, R) ya medidos como la mejor curva empirica de R(E) disponible,
  evaluada en la energia representativa de cada bin candidato, y se pesa
  por el flujo real integrado en su rango (energy_bins.integral_between,
  exacto, no interpolado). D_estimado = suma_bin AREA_CM2 * flujo_bin *
  R_interpolado(e_rep_bin).

  OJO -- limitacion real, verificada aqui mismo (ver 'chequeo de
  consistencia' abajo): al reconstruir los esquemas uniformes 8/16/32/64
  con este metodo y compararlos contra el epsilon_binning REAL medido
  (epsilon_binning_fase8_resultado.csv), el orden de magnitud coincide
  pero no el valor exacto -- la interpolacion log-log entre puntos
  ampliamente espaciados no capura curvatura fina de R(E) (posibles
  picos tipo Bragg, umbrales de reaccion, etc). Por eso esto es una
  ESTIMACION para elegir el mejor candidato a probar, NO un reemplazo de
  validarlo con una tanda real de jobs_v2 (ver seed pendiente, mucho mas
  barata que las 128 corridas ya hechas).

Uso:
    python3 propuesta_binning_hibrido_sep.py
Escribe propuesta_binning_hibrido_sep_resultado.csv en el mismo directorio.
"""
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import energy_bins  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
INPUT_CSV = HERE / "resultados_organo_sweep_fase8_binning.csv"
OUTPUT_CSV = HERE / "propuesta_binning_hibrido_sep_resultado.csv"
SPECTRA_DIR = REPO_ROOT / "geant4/ActiveShield_Sim/data/sources/oltaris"

SHIP_RADIUS_M, SHIP_HALF_LENGTH_M, HULL_CM = 4.5, 5.0, 1.5
SOURCE_RADIUS_CM = math.sqrt((SHIP_RADIUS_M * 100) ** 2 + (SHIP_HALF_LENGTH_M * 100) ** 2) + HULL_CM + 20.0
AREA_CM2 = math.pi * SOURCE_RADIUS_CM ** 2

SPECIES, PHASE = "SEP_p", "max"
CSV_FILE, LO, HI = energy_bins.SPECIES_RANGE[(SPECIES, PHASE)]

# Candidatos evaluados: (n_low, corte_MeV, n_high). Elegidos por un barrido
# de corte (40-100 MeV) y de n_low (1-5) con total fijo en 16, mas una
# comparacion de presupuesto total (10/12/14/16 bins) -- ver bitacora del
# plan estadistico para el barrido completo.
CANDIDATOS = [
    (2, 50, 14),   # mejor a presupuesto total = 16 (igual al actual objetivo de convergencia)
    (3, 65, 13),
    (1, 65, 11),   # mejor numerico encontrado, descartado como principal por fragil (1 solo punto en 4 decadas)
    (2, 65, 12),   # RECOMENDADO: robustez (2 puntos en la zona de bajo flujo) a costo casi nulo
    (3, 65, 11),
]
RECOMENDADO = (2, 65, 12)


def cargar_R_medido_128():
    """R(e_rep) = edep_J total (todos los organos) / n_eventos, por bin_index,
    de los 128 bins ya corridos y consolidados. Devuelve lista (e_rep, R)
    ordenada por energia -- la mejor curva empirica de R(E) disponible."""
    edep_by, n_by = defaultdict(float), {}
    for row in csv.DictReader(open(INPUT_CSV)):
        if row["especie"] != SPECIES or int(row["n_bins"]) != 128:
            continue
        bin_index = int(row["bin_index"])
        edep_by[bin_index] += float(row["edep_J"])
        n_by[bin_index] = int(row["n_eventos"])

    bins128 = energy_bins.build_bins(SPECTRA_DIR, n_bins=128)[(SPECIES, PHASE)]
    fine, D_ref = [], 0.0
    for bin_index, e_rep, flux_bin in bins128:
        if bin_index not in edep_by:
            raise RuntimeError(f"Falta bin_index={bin_index} de n_bins=128 en {INPUT_CSV} -- "
                                "no deberia pasar si la tanda 4 esta completa y consolidada.")
        R = edep_by[bin_index] / n_by[bin_index]
        fine.append((e_rep, R))
        D_ref += AREA_CM2 * flux_bin * R
    fine.sort()
    return fine, D_ref


def r_interp_loglog(fine, e):
    es = [f[0] for f in fine]
    if e <= es[0]:
        return fine[0][1]
    if e >= es[-1]:
        return fine[-1][1]
    for i in range(1, len(es)):
        if es[i] >= e:
            e0, r0 = fine[i - 1]
            e1, r1 = fine[i]
            if r0 <= 0 or r1 <= 0:
                t = (e - e0) / (e1 - e0)
                return r0 + t * (r1 - r0)
            t = (math.log(e) - math.log(e0)) / (math.log(e1) - math.log(e0))
            return math.exp(math.log(r0) + t * (math.log(r1) - math.log(r0)))
    return fine[-1][1]


def eval_scheme(fine, energies, fluxes, edges):
    D = 0.0
    for i in range(len(edges) - 1):
        e_lo, e_hi = edges[i], edges[i + 1]
        e_rep = energy_bins.bin_representative_energy(e_lo, e_hi)
        flux_bin = energy_bins.integral_between(energies, fluxes, e_lo, e_hi)
        D += AREA_CM2 * flux_bin * r_interp_loglog(fine, e_rep)
    return D


def main():
    fine, D_ref = cargar_R_medido_128()
    energies, fluxes = energy_bins.load_spectrum(SPECTRA_DIR / CSV_FILE)
    print(f"D_ref ({SPECIES}/{PHASE}, 128 bins medidos, proxy cuerpo completo) = {D_ref:.4e}")

    print("\nChequeo de consistencia (reconstruir uniformes 8/16/32/64 con este metodo\n"
          "de interpolacion y comparar contra epsilon_binning REAL medido -- ver texto\n"
          "arriba, el orden de magnitud debe coincidir pero no el valor exacto):")
    for n in (8, 16, 32, 64):
        edges = energy_bins.log_bin_edges(LO, HI, n)
        D = eval_scheme(fine, energies, fluxes, edges)
        eps = abs(D - D_ref) / abs(D_ref) * 100.0
        print(f"  uniforme n={n:<4d} D_interp={D:.4e}  eps_interp_vs_ref128={eps:.3f}%")

    rows = []
    print(f"\n{'n_low':>5} {'corte_MeV':>10} {'n_high':>7} {'total':>6} {'D_estimado':>14} "
          f"{'eps_vs_ref128_pct':>18}  nota")
    for n_low, corte, n_high in CANDIDATOS:
        edges = energy_bins.log_bin_edges(LO, corte, n_low)[:-1] + energy_bins.log_bin_edges(corte, HI, n_high)
        D = eval_scheme(fine, energies, fluxes, edges)
        eps = abs(D - D_ref) / abs(D_ref) * 100.0
        nota = "RECOMENDADO" if (n_low, corte, n_high) == RECOMENDADO else ""
        print(f"{n_low:>5} {corte:>10} {n_high:>7} {n_low + n_high:>6} {D:>14.4e} {eps:>18.3f}  {nota}")
        rows.append({"n_low": n_low, "corte_mev": corte, "n_high": n_high, "n_total": n_low + n_high,
                      "D_estimado_proxy": D, "eps_vs_ref128_pct": eps, "recomendado": nota == "RECOMENDADO"})

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["n_low", "corte_mev", "n_high", "n_total",
                                                "D_estimado_proxy", "eps_vs_ref128_pct", "recomendado"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nEscrito: {OUTPUT_CSV}")
    print("\nEsto es una ESTIMACION, no una validacion -- antes de adoptarlo para produccion,\n"
          "sembrar una tanda real de jobs_v2 con este esquema custom (requiere primero agregar\n"
          "soporte de bordes no uniformes a energy_bins.py/run_organ_sweep.py, hoy solo aceptan\n"
          "grilla log-uniforme por especie) y comparar epsilon_binning real contra ref(128).")


if __name__ == "__main__":
    main()
