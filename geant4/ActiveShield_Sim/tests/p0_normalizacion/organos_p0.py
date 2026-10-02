#!/usr/bin/env python3
"""Órganos de P0 con la definición de ICRP 116 (Tabla 4.2), traducidos a los
organ_id del fantoma AM de ICRP 110, y la tolerancia D7 de cada uno.

No usa las categorías de write_event_categories.py: ahí «colon» no incluye la
pared del recto y «remainder_tissues» es una agregación por masa propia.
ICRP 116 define el colon como RC + LC + RSig (con la pared del recto) y
calcula la médula roja como el promedio, ponderado por masa de médula activa,
de la dosis en la esponjosa de cada hueso (§3.4, §4.1). Eso equivale a pesar
cada esponjosa con su fracción de médula roja, como hace el resto del
proyecto.

Escribe un archivo de categorías para /eventStats/categoryFile y su
`.masses.tsv`.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent/"scripts"))
import aggregate_organ_doses as agg  # noqa: E402

# Acrónimo ICRP 116 -> organ_id del fantoma AM (AM_organs.dat).
ORGANS = {
    "Lungs": [96, 97, 98, 99],                       # RLung + LLung (tejido y sangre)
    "Colon": [76, 78, 80, 82, 84, 86],               # RC + LC + RSig (incluye la pared del recto)
    "St-wall": [72],
    "Liver": [95],
    "Breast": [62, 63, 64, 65],                      # Breast-a + Breast-g
    "Thyroid": [132],
    "Testes": [129, 130],
    "UB-wall": [137],
    "Oesophagus": [110],
    "Brain": [61],
    "Kidneys": [89, 90, 91, 92, 93, 94],
    "Pancreas": [113],
    "Spleen": [127],
    "Adrenals": [1, 2],
    "Thymus": [131],
}

# D7 (plan_piloto.md, P0): IC95 del cociente dentro de 1 ± tolerancia, a
# energías >= 100 MeV/n. Los demás órganos son descriptivos.
TOLERANCE = {"Lungs": 0.10, "Colon": 0.10, "St-wall": 0.10, "Liver": 0.10, "R-marrow": 0.10,
             "Breast": 0.15, "Thyroid": 0.15}
MIN_ENERGY_PRIMARY = 100.0  # MeV/n


def build(icrp_data_dir):
    masses = agg.load_organ_masses_kg(icrp_data_dir)
    metadata = agg.load_organ_metadata(icrp_data_dir)
    rbm = agg.build_rbm_organ_fractions(metadata, agg.load_rbm_fraction_by_tissue(icrp_data_dir))
    rows = [(name, oid, 1.0) for name, ids in ORGANS.items() for oid in ids]
    rows += [("R-marrow", oid, frac) for oid, frac in sorted(rbm.items())]
    pooled = {}
    for name, oid, w in rows:
        if oid not in masses:
            raise SystemExit(f"organ_id {oid} ({name}) sin masa en OrganMasses.dat")
        pooled[name] = pooled.get(name, 0.0)+w*masses[oid]
    return rows, pooled


def write(output, icrp_data_dir):
    rows, pooled = build(icrp_data_dir)
    with open(output, "w") as f:
        f.write("# organo_icrp organ_id peso -- generado por tests/p0_normalizacion/organos_p0.py\n")
        for name, oid, w in rows:
            f.write(f"{name} {oid} {w!r}\n")
    with open(Path(output).with_suffix(".masses.tsv"), "w") as f:
        f.write("categoria\tmasa_kg\n")
        for name, m in pooled.items():
            f.write(f"{name}\t{m!r}\n")
    return pooled


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("output", type=Path)
    p.add_argument("--icrp-data-dir", type=Path, default=HERE.parent.parent/"build"/"ICRPdata")
    a = p.parse_args()
    for name, m in write(a.output, a.icrp_data_dir).items():
        print(f"{name:12s} {m:8.4f} kg")
