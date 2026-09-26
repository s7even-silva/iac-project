#!/usr/bin/env python3
"""Calcula epsilon_binning (Fase 8 del plan estadistico, ver
docs/bitacora/plan_estadistico.md) a partir del CSV consolidado
resultados_organo_sweep_fase8_binning.csv -- reproducible desde cualquier
sesion/maquina, sin necesitar acceso a la DB del coordinator ni a git show.

Formula (misma que run_fase8_binning.py/aggregate_organ_doses.py):
  W[bin] = area_cm2 * flujo_integrado_del_bin (energy_bins.build_bins)
  R[bin] = edep_J_total_del_bin (suma sobre TODOS los organos) / N_eventos
  D_N    = suma_bin W[bin] * R[bin]
  epsilon_binning(lo,hi) = |D_hi - D_lo| / |D_hi|

D_N es un proxy de dosis de cuerpo completo (sin dividir por masa -- no
hay ICRPdata/ en todas las maquinas que puedan correr esto). Valido para
comparar n_bins entre si de la MISMA especie (la masa es una constante
que se cancela en epsilon_binning), no como Gy real ni para comparar
especies entre si. Mismo alcance reducido que usa run_fase8_binning.py
para este proposito especifico ("una D agregada simple, suficiente para
epsilon_binning. No separa [por organo]").

Uso:
    python3 epsilon_binning_fase8_resumen.py
Escribe epsilon_binning_fase8_resultado.csv en el mismo directorio.
"""
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import energy_bins  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
INPUT_CSV = HERE / "resultados_organo_sweep_fase8_binning.csv"
OUTPUT_CSV = HERE / "epsilon_binning_fase8_resultado.csv"
SPECTRA_DIR = REPO_ROOT / "geant4/ActiveShield_Sim/data/sources/oltaris"

SHIP_RADIUS_M, SHIP_HALF_LENGTH_M, HULL_CM = 4.5, 5.0, 1.5
SOURCE_RADIUS_CM = math.sqrt((SHIP_RADIUS_M * 100) ** 2 + (SHIP_HALF_LENGTH_M * 100) ** 2) + HULL_CM + 20.0
AREA_CM2 = math.pi * SOURCE_RADIUS_CM ** 2

SPECIES_PHASE = {"SEP_p": "max", "GCR_H": "min", "GCR_He": "min"}
N_BINS_GRID = [8, 16, 32, 64]  # 64 solo existe para SEP_p


def main():
    edep_by = defaultdict(float)  # (species, n_bins, bin_index) -> suma edep_J (todos los organos)
    n_by = {}
    for row in csv.DictReader(open(INPUT_CSV)):
        key = (row["especie"], int(row["n_bins"]), int(row["bin_index"]))
        edep_by[key] += float(row["edep_J"])
        n_by[key] = int(row["n_eventos"])

    print(f"Combinaciones (especie,n_bins,bin_index) reales en el CSV: {len(edep_by)}")

    D_by = {}
    coverage = {}
    for species, phase in SPECIES_PHASE.items():
        for n_bins in N_BINS_GRID:
            bins = energy_bins.build_bins(SPECTRA_DIR, n_bins=n_bins)[(species, phase)]
            D, present = 0.0, 0
            for bin_index, energy_rep, flux_bin in bins:
                key = (species, n_bins, bin_index)
                if key not in edep_by:
                    continue
                present += 1
                w = AREA_CM2 * flux_bin
                r = edep_by[key] / n_by[key]
                D += w * r
            D_by[(species, n_bins)] = D
            coverage[(species, n_bins)] = (present, len(bins))

    rows = []
    print(f"\n{'especie':8s} {'n_bins':6s} {'cobertura':10s} {'D_N (proxy)':>18s}")
    for (species, n_bins), D in sorted(D_by.items()):
        p, e = coverage[(species, n_bins)]
        print(f"{species:8s} {n_bins:<6d} {p}/{e:<8d} {D:18.6e}")

    print(f"\n{'especie':8s} {'par':10s} {'epsilon_binning_pct':>20s}  veredicto")
    for species in SPECIES_PHASE:
        available = sorted(n for (sp, n) in D_by if sp == species)
        for lo, hi in zip(available, available[1:]):
            p_hi, e_hi = coverage[(species, hi)]
            D_lo, D_hi = D_by[(species, lo)], D_by[(species, hi)]
            if p_hi != e_hi or D_hi == 0:
                continue
            eps = abs(D_hi - D_lo) / abs(D_hi) * 100.0
            veredicto = "auto_continue" if eps <= 2.5 else ("limitrofe" if eps <= 3.0 else "revisar")
            print(f"{species:8s} {lo}->{hi:<7d} {eps:20.3f}  {veredicto}")
            rows.append({"especie": species, "n_bins_lo": lo, "n_bins_hi": hi,
                         "D_lo_proxy": D_lo, "D_hi_proxy": D_hi,
                         "epsilon_binning_pct": eps, "veredicto": veredicto})

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["especie", "n_bins_lo", "n_bins_hi", "D_lo_proxy",
                                                "D_hi_proxy", "epsilon_binning_pct", "veredicto"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nEscrito: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
