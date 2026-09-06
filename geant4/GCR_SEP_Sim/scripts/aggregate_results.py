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

    groups = defaultdict(list)
    n_rows = 0
    for path in input_paths:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row["modelo"], row["fase"], float(row["field_T"]), float(row["astronaut_x_m"]))
                groups[key].append(float(row["dosis_Gy"]))
                n_rows += 1

    print(f"Leidas {n_rows} filas de {len(input_paths)} archivo(s), {len(groups)} combinaciones distintas.")

    out_rows = []
    n_warned = 0
    for (modelo, fase, field_t, x_m), doses in sorted(groups.items()):
        n = len(doses)
        mean = statistics.mean(doses)
        if n >= 2:
            std = statistics.stdev(doses)  # ddof=1 (muestral)
            sem = std / math.sqrt(n)
            t_crit = t_critical_95(n - 1)
            ci_half = t_crit * sem
            cv_pct = (std / mean * 100.0) if mean != 0 else float("nan")
        else:
            std = sem = ci_half = cv_pct = float("nan")

        if n != args.expected_n:
            print(f"  AVISO: {modelo}/{fase} field={field_t}T x={x_m}m tiene {n} repeticion(es), "
                  f"se esperaban {args.expected_n} (revisar corridas faltantes/fallidas)")
            n_warned += 1

        out_rows.append({
            "modelo": modelo, "fase": fase, "field_T": field_t, "astronaut_x_m": x_m,
            "n": n, "dosis_media_Gy": mean, "dosis_std_Gy": std, "dosis_sem_Gy": sem,
            "ic95_low_Gy": mean - ci_half if n >= 2 else float("nan"),
            "ic95_high_Gy": mean + ci_half if n >= 2 else float("nan"),
            "cv_pct": cv_pct,
        })

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\n{len(out_rows)} combinaciones agregadas ({n_warned} con repeticiones distintas a {args.expected_n}).")
    print(f"Escrito: {args.output}")


if __name__ == "__main__":
    main()
