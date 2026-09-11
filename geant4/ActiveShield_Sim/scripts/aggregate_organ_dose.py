#!/usr/bin/env python3
"""Post-procesa los archivos ICRP110.out (uno por corrida, ver
run_sweep.py) del segundo grupo de datos de ActiveShield_Sim: dosis
absorbida por organo -> dosis equivalente (Sv) en los organos de mayor
riesgo estocastico (ICRP 103), agrupada por especie y posicion.

**Todo en este script es un supuesto propio del equipo, sin fijar
todavia -- marcado explicitamente, no una cifra de produccion aceptada**
(mismo principio que el resto del repo, ver AGENTS.md):

1. **Factor de ponderacion radiologica (wR) por particula**: se usa un
   valor fijo de ICRP 103 (proton=2, alpha=20), NO una curva Q(L) por
   energia/LET -- para iones pesados y protones de muy baja energia esto
   es una simplificacion conocida, no una cifra aceptada para el articulo.
   Ver la nota en docs/modelo_realista.md: "Gy no se convierte en Sv
   cambiando solo la etiqueta; la dosis equivalente requiere su
   ponderacion radiobiologica definida" -- este script es un primer
   intento de esa definicion, pendiente de que el equipo la confirme.
2. **Agrupacion de organos**: el fantoma ICRP110 divide cada organo
   fisiologico en varias sub-regiones con su propio OrganID (ej. colon en
   4 segmentos, medula en 6 sitios oseos) -- se agrupan aqui por
   coincidencia de texto en el nombre (ver ORGAN_GROUPS), sumando Edep y
   masa antes de calcular dosis. "Medullary cavity" se usa como proxy de
   medula osea roja (unico organID disponible en ICRP110 para eso) --
   el fantoma no separa medula roja de amarilla, simplificacion conocida
   de ICRP110, no de este script.
3. Reporta dosis equivalente por organo, NO dosis efectiva (no se aplica
   ponderacion tisular wT ni se suma entre organos) -- coincide con lo
   pedido ("dosis equivalente segun los organos con mas riesgo
   estocastico"), no con una dosis efectiva de cuerpo entero.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

# ICRP 103, Tabla A.3 -- wR por tipo de particula. Simplificado: sin
# dependencia de energia/LET (ver docstring, punto 1).
RADIATION_WEIGHTING_FACTOR = {
    "proton": 2.0,
    "alpha": 20.0,
}

# Organos/tejidos de mayor riesgo estocastico segun ICRP 103 (wT=0.12:
# medula osea roja, colon, pulmon, estomago, mama; wT=0.08: gonadas) --
# emparejados por substring (insensible a mayusculas) contra los nombres
# de AM_organs.dat/AF_organs.dat. Ver punto 2 del docstring.
ORGAN_GROUPS = {
    "medula_osea_roja (medullary cavity, proxy ICRP110)": ["medullary cavity"],
    "colon": ["colon"],
    "pulmon": ["lung"],
    "estomago": ["stomach"],
    "mama": ["breast"],
    "gonadas": ["testis", "testes", "ovary", "ovaries"],
}

ORGAN_LINE_RE = re.compile(r"^\s*(\d+)\s*\|\s*(\S+)\s*$")


def load_organ_names(icrp_data_dir: Path, sex: str) -> dict[int, str]:
    """Lee AM_organs.dat/AF_organs.dat (mismo archivo que usa
    ICRP110UserScoreWriter.cc) para mapear OrganID -> nombre."""
    fname = "AM_organs.dat" if sex == "male" else "AF_organs.dat"
    path = icrp_data_dir / ("AM" if sex == "male" else "AF") / fname
    names = {0: "Air"}
    lines = path.read_text().splitlines()[4:]  # mismas 4 lineas de encabezado que ignora ICRP110UserScoreWriter.cc
    for idx, line in enumerate(lines, start=1):
        if line.strip():
            names[idx] = line.strip()
    return names


def parse_icrp110_out(path: Path) -> dict[int, tuple[float, float]]:
    """Devuelve {OrganID: (Edep_J, Dose_Gy)} de la ULTIMA tabla del
    archivo (la que incluye todos los OrganIDs, incluso los de dosis
    cero) -- ver ICRP110UserScoreWriter.cc, seccion final."""
    text = path.read_text()
    marker = "OrganID\tEdep (J) \tDose (Gy)"
    idx = text.rfind(marker)
    if idx == -1:
        raise ValueError(f"{path}: no se encontro la tabla final de dosis por organo")
    body = text[idx:].splitlines()[2:]
    doses = {}
    for line in body:
        if line.startswith("Total"):
            break
        parts = line.split("|")
        if len(parts) != 2:
            continue
        organ_id = int(parts[0].strip())
        edep_j, dose_gy = (float(x) for x in parts[1].split())
        doses[organ_id] = (edep_j, dose_gy)
    return doses


def group_doses(doses: dict[int, tuple[float, float]], organ_names: dict[int, str]) -> dict[str, float]:
    """Suma Edep de las sub-regiones de cada grupo y recalcula dosis del
    grupo dividiendo por la masa total (a partir de Edep/Dose de cada
    sub-region, ya que Dose=Edep/masa -> masa=Edep/Dose)."""
    grouped_edep = {g: 0.0 for g in ORGAN_GROUPS}
    grouped_mass_kg = {g: 0.0 for g in ORGAN_GROUPS}
    for organ_id, (edep_j, dose_gy) in doses.items():
        name = organ_names.get(organ_id, "")
        for group, keywords in ORGAN_GROUPS.items():
            if any(kw in name.lower() for kw in keywords):
                grouped_edep[group] += edep_j
                if dose_gy > 0:
                    grouped_mass_kg[group] += edep_j / dose_gy
    result = {}
    for group in ORGAN_GROUPS:
        mass = grouped_mass_kg[group]
        result[group] = grouped_edep[group] / mass if mass > 0 else 0.0
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path, help="activeshield_manifest.csv de run_sweep.py")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--icrp-data-dir", type=Path, default=None,
                         help="Directorio ICRPdata/ICRP110_g4dat/P110_data_V1.2 (default: <build>/ICRPdata/...)")
    parser.add_argument("--sex", choices=["male", "female"], default="male")
    args = parser.parse_args()

    build_dir = args.manifest.resolve().parent
    icrp_data_dir = args.icrp_data_dir or (build_dir / "ICRPdata" / "ICRP110_g4dat" / "P110_data_V1.2")
    if not icrp_data_dir.is_dir():
        sys.exit(f"ERROR: no se encontro {icrp_data_dir}")
    organ_names = load_organ_names(icrp_data_dir, args.sex)

    rows = []
    with open(args.manifest, newline="") as f:
        for row in csv.DictReader(f):
            if row["exit_code"] != "0" or not row["organ_dose_path"]:
                continue
            organ_dose_path = Path(row["organ_dose_path"])
            if not organ_dose_path.is_file():
                print(f"AVISO: falta {organ_dose_path} (indice {row['index']}), se omite", file=sys.stderr)
                continue
            wr = RADIATION_WEIGHTING_FACTOR.get(row["particle"])
            if wr is None:
                print(f"AVISO: sin wR definido para particula '{row['particle']}' (indice {row['index']}), "
                      "se omite", file=sys.stderr)
                continue
            doses_gy = group_doses(parse_icrp110_out(organ_dose_path), organ_names)
            out_row = {"especie": row["especie"], "particle": row["particle"],
                       "astronaut_x_m": row["astronaut_x_m"], "n_events": row["n_events"], "wR": wr}
            for group, dose_gy in doses_gy.items():
                out_row[f"{group}_Gy"] = dose_gy
                out_row[f"{group}_Sv"] = dose_gy * wr
            rows.append(out_row)

    if not rows:
        sys.exit("ERROR: no hay corridas exitosas con organ_dose_path valido en el manifiesto")

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Escrito {args.output} ({len(rows)} corridas)")


if __name__ == "__main__":
    main()
