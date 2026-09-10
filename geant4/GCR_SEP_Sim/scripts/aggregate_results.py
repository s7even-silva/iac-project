#!/usr/bin/env python3
"""Agrega los resultados crudos del barrido (una fila por corrida/repeticion)
en estadisticas por combinacion: media, desviacion estandar, error estandar
e intervalo de confianza 95%, listas para la tabla y la grafica del articulo.

Piensa en esto como el paso final despues de que cada persona del equipo
corrio su parte del barrido (ver README.md, seccion "Division del trabajo").
Junta los CSV de todos y calcula la estadistica agrupando por
(modelo, fase, field_T, astronaut_x_m) -- es decir, junta las N repeticiones
de cada combinacion sin importar quien las corrio.

Uso:
    python3 aggregate_results.py resultados_dosis_sweep_GCR.csv resultados_dosis_sweep_SEP.csv
    python3 aggregate_results.py "resultados/*.csv" -o resultados_agregados.csv --expected-n 5
"""
import argparse
import csv
import glob
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# Valores criticos t de Student (dos colas, 95%) por grado de libertad (n-1).
# Tabla estandar de cualquier referencia de estadistica. Para df > 30 se usa
# la aproximacion normal (z = 1.96), habitual cuando ya no hay tabla a mano.
T_TABLE_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056,
    27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def t_critical_95(df):
    if df <= 0:
        return float("nan")
    return T_TABLE_95.get(df, 1.96)


def expand_inputs(patterns):
    paths = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        paths.extend(matches if matches else [pattern])
    return [Path(p) for p in paths]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="CSV(s) de resultados crudos (acepta patrones glob entre comillas)")
    parser.add_argument("-o", "--output", type=Path, default=Path("resultados_agregados.csv"),
                         help="CSV de salida (default: resultados_agregados.csv)")
    parser.add_argument("--expected-n", type=int, default=5,
                         help="Repeticiones esperadas por combinacion, para avisar si falta alguna (default 5)")
    args = parser.parse_args()

    input_paths = expand_inputs(args.inputs)
    missing = [p for p in input_paths if not p.is_file()]
    if missing:
        sys.exit(f"ERROR: no se encontraron estos archivos: {', '.join(str(p) for p in missing)}")
    if not input_paths:
        sys.exit("ERROR: no se encontro ningun CSV de entrada.")

    # dosis_Gy: dosis cruda de la corrida (QA, no pesada por flujo real).
    # dosis_absoluta_Gy: normalizacion fisica (Gy/dia para GCR, Gy del
    # evento completo para SEP) -- ver RunAction.cc y AGENTS.md. Columnas
    # antiguas (CSVs generados antes de esta normalizacion) no la traen;
    # se avisa y se omite esa metrica para esas filas en vez de fallar.
    DOSE_COLUMNS = [("dosis_Gy", ""), ("dosis_absoluta_Gy", "absoluta_")]

    groups = defaultdict(lambda: {col: [] for col, _ in DOSE_COLUMNS})
    n_rows = 0
    n_missing_absoluta = 0
    for path in input_paths:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row["modelo"], row["fase"], float(row["field_T"]), float(row["astronaut_x_m"]))
                for col, _ in DOSE_COLUMNS:
                    if col in row and row[col] != "":
                        groups[key][col].append(float(row[col]))
                    elif col == "dosis_absoluta_Gy":
                        n_missing_absoluta += 1
                n_rows += 1

    print(f"Leidas {n_rows} filas de {len(input_paths)} archivo(s), {len(groups)} combinaciones distintas.")
    if n_missing_absoluta:
        print(f"  AVISO: {n_missing_absoluta} fila(s) sin columna 'dosis_absoluta_Gy' (CSV generado con una "
              f"version anterior de RunAction.cc) -- se omiten de esa metrica, no de 'dosis_Gy'.")

    out_rows = []
    n_warned = 0
    for (modelo, fase, field_t, x_m), doses_by_col in sorted(groups.items()):
        row_out = {"modelo": modelo, "fase": fase, "field_T": field_t, "astronaut_x_m": x_m}
        n_ref = None
        for col, prefix in DOSE_COLUMNS:
            values = doses_by_col[col]
            n = len(values)
            if col == "dosis_Gy":
                n_ref = n
                row_out["n"] = n
            if n == 0:
                mean = std = sem = ci_half = cv_pct = float("nan")
            else:
                mean = statistics.mean(values)
                if n >= 2:
                    std = statistics.stdev(values)  # ddof=1 (muestral)
                    sem = std / math.sqrt(n)
                    t_crit = t_critical_95(n - 1)
                    ci_half = t_crit * sem
                    cv_pct = (std / mean * 100.0) if mean != 0 else float("nan")
                else:
                    std = sem = ci_half = cv_pct = float("nan")

            row_out[f"dosis_{prefix}media_Gy"] = mean
            row_out[f"dosis_{prefix}std_Gy"] = std
            row_out[f"dosis_{prefix}sem_Gy"] = sem
            row_out[f"ic95_{prefix}low_Gy"] = mean - ci_half if n >= 2 else float("nan")
            row_out[f"ic95_{prefix}high_Gy"] = mean + ci_half if n >= 2 else float("nan")
            row_out[f"cv_{prefix}pct"] = cv_pct

        if n_ref != args.expected_n:
            print(f"  AVISO: {modelo}/{fase} field={field_t}T x={x_m}m tiene {n_ref} repeticion(es), "
                  f"se esperaban {args.expected_n} (revisar corridas faltantes/fallidas)")
            n_warned += 1

        out_rows.append(row_out)

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\n{len(out_rows)} combinaciones agregadas ({n_warned} con repeticiones distintas a {args.expected_n}).")
    print(f"Escrito: {args.output}")


if __name__ == "__main__":
    main()
