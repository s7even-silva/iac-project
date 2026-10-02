#!/usr/bin/env python3
"""Escribe el archivo de categorias que lee /eventStats/categoryFile (scorer
por evento, R1/R12 de docs/bitacora/plan_barrido.md).

Formato: una linea `<categoria> <organ_id> <peso>`. La energia de la
categoria en un evento es sum_o peso_o * e_o; su masa es sum_o peso_o * m_o.
Las categorias y pesos salen de las mismas funciones que usa
aggregate_organ_doses.py (una sola definicion): las 5 por palabra clave con
peso 1, medula osea roja con la fraccion RBM de cada organo espongiosa, y
`total_body` con todos los organos salvo aire (0 y 140), igual que el total
de ICRP110.out.

Ademas escribe `<salida>.masses.tsv` con la masa pooled de cada categoria.
"""
import argparse
from pathlib import Path

import aggregate_organ_doses as agg

AIR_IDS = {0, 140}


def category_weights(icrp_data_dir):
    metadata = agg.load_organ_metadata(icrp_data_dir)
    masses = agg.load_organ_masses_kg(icrp_data_dir)
    if not metadata or not masses:
        raise SystemExit(f"Faltan datos ICRP en {icrp_data_dir}")
    rows = []
    for category, organ_ids in agg.build_category_organ_ids(metadata).items():
        rows += [(category, oid, 1.0) for oid in sorted(set(organ_ids))]
    rbm = agg.build_rbm_organ_fractions(metadata, agg.load_rbm_fraction_by_tissue(icrp_data_dir))
    rows += [("red_bone_marrow", oid, frac) for oid, frac in sorted(rbm.items())]
    rows += [("total_body", oid, 1.0) for oid in sorted(masses) if oid not in AIR_IDS and masses[oid] > 0]
    pooled = {}
    for category, oid, weight in rows:
        pooled[category] = pooled.get(category, 0.0)+weight*masses.get(oid, 0.0)
    return rows, pooled


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output", type=Path)
    p.add_argument("--icrp-data-dir", type=Path,
                   default=Path(__file__).resolve().parent.parent/"build"/"ICRPdata")
    a = p.parse_args()
    rows, pooled = category_weights(a.icrp_data_dir)
    with open(a.output, "w") as f:
        f.write("# categoria organ_id peso -- generado por write_event_categories.py\n")
        for category, oid, weight in rows:
            f.write(f"{category} {oid} {weight!r}\n")
    with open(a.output.with_suffix(".masses.tsv"), "w") as f:
        f.write("categoria\tmasa_kg\n")
        for category, mass in pooled.items():
            f.write(f"{category}\t{mass!r}\n")
    print(f"{len(rows)} entradas, {len(pooled)} categorias -> {a.output}")


if __name__ == "__main__":
    main()
