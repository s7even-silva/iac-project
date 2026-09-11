#!/usr/bin/env python3
"""Combina resultados_organo_sweep.csv (salida de run_organ_sweep.py) con los
espectros reales de OLTARIS para dar dosis absorbida y equivalente por
organo y posicion RADIAL del fantoma (offset_x_m), en el escenario fijo de
campo real del arreglo de 8 bobinas de CREW HaT a su corriente de diseno
maxima + evento mas peligroso por especie (ver run_organ_sweep.py y AGENTS.md).

Usa energy_bins.py (bins de energia + su peso fisico real, ver ese modulo)
en vez de un solo peso por especie -- misma formula de normalizacion fisica
que GCR_SEP_Sim/src/RunAction.cc, generalizada a sumar sobre (especie,bin)
en vez de solo especie:

    R[o,s,bin] = edep_J[o,s,bin] / (masa_kg[o] * N[s,bin])
    W[s,bin]   = pi * R_esfera_fuente_cm^2 * flujo_integrado_del_bin[s,bin]
    D_absorbida[o]   = suma_(s,bin) R[o,s,bin] * W[s,bin]              (Gy)
    D_equivalente[o] = suma_(s,bin) w_R[s] * R[o,s,bin] * W[s,bin]      (Sv)

w_R (ICRP 103 Tabla A.3): proton = 2, particula alfa = 20 -- por especie, no
por bin (ver AGENTS.md para la limitacion explicita: pondera por primario
de la corrida, no por particula-en-cada-paso).

GCR y SEP NO se suman entre si: GCR_H/GCR_He dan un resultado en Gy/dia (el
flujo de OLTARIS ya viene por dia), SEP_p en Gy/evento completo (Oct 1989) --
semantica temporal distinta, igual que en GCR_SEP_Sim (ver AGENTS.md).

Ademas del CSV agregado completo (por organo_id, sin agrupar), genera una
vista de los 6 tejidos de mayor riesgo estocastico de cancer -- ICRP 103
Tabla A.1, los w_T=0.12: colon, pulmon, estomago, mama, medula osea roja y
"tejidos restantes" (remainder, un compuesto de otros 14 tejidos que ICRP103
trata como una sola categoria). A diferencia de la version anterior de este
script (que reportaba una fila por organ_id que matcheaba una palabra
clave), esta version AGRUPA los organ_id de cada categoria en un solo valor
ponderado por masa -- Colon/Estomago/Intestino delgado/Vesicula biliar en
ICRP110 se segmentan en sub-regiones "wall"/"contents" (pared y contenido
del organo); "contents" (heces, contenido gastrico, sangre en camaras del
corazon) es material transitorio, no tejido vivo en riesgo de cancer, y se
EXCLUYE explicitamente de todas las categorias (ver EXCLUDE_KEYWORDS) --
limitacion/decision de modelado marcada aqui, no verificada contra una
convencion ICRP explicita mas alla del razonamiento biologico dado.

**Medula osea roja**, verificado contra los archivos reales de ICRPdata/
(2026-09-11, revierte la exclusion de la version anterior): ICRP110 no la
modela como un organ_id propio -- esta repartida como una FRACCION de la
masa de "spongiosa" (hueso esponjoso) en 19 sitios esqueleticos (humeros,
craneo, pelvis, columna, etc.), dada por AM_spongiosa.dat (columnas
RBM/YBM/Bone por ID de TEJIDO, columna "Tissue number" de AM_organs.dat,
no por organ_id). Aqui se lee ese ID de tejido de cada organo espongiosa,
se cruza con su fraccion RBM, y se pondera edep Y masa por esa fraccion
antes de combinar los 19 sitios en un solo valor de medula osea roja --
supone deposicion de dosis uniforme por unidad de masa dentro de cada
region de hueso esponjoso mixto (RBM/YBM/hueso), una aproximacion estandar
en dosimetria de fantomas de referencia pero no validada especificamente
para este espectro de radiacion aqui.

Si `ICRPdata/` no existe todavia (no se ha compilado en este entorno) o si
alguna categoria no matchea ningun organo real, se imprime una advertencia
explicita -- no falla en silencio, ver AGENTS.md ("nunca asumir sin
verificar contra el archivo real").
"""
import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import energy_bins

# Categorias ICRP 103 Tabla A.1, w_T=0.12 -- 5 de las 6 son un OR de palabras
# clave sobre el nombre real de organo (ver AM_organs.dat), excluyendo
# cualquier entrada con "contents" (ver docstring). La sexta, medula osea
# roja, se calcula aparte (RBM_KEYWORDS no se usa, ver load_rbm_organ_fractions).
CATEGORY_KEYWORDS = {
    "colon": ["colon"],
    "lung": ["lung"],
    "stomach": ["stomach"],
    "breast": ["breast"],
    # Los otros 14 tejidos que ICRP103 agrupa como "remainder tissues" (una
    # sola categoria de w_T=0.12, no 14 separadas): suprarrenales, vias
    # respiratorias extratoracicas, mucosa oral, traquea, vesicula biliar,
    # intestino delgado, corazon, rinon, ganglios linfaticos, musculo,
    # pancreas, prostata (fantoma masculino), bazo, timo.
    "remainder_tissues": [
        "adrenal", "nasal passage", "oral mucosa", "trachea", "gall bladder",
        "small intestine", "heart", "kidney", "lymphatic", "muscle",
        "pancreas", "prostate", "spleen", "thymus",
    ],
}
EXCLUDE_KEYWORDS = ["contents"]  # material transitorio, no tejido vivo -- ver docstring

# w_R, ICRP 103 Tabla A.3 -- por especie (particula primaria), no por bin de
# energia: estos valores simplificados no dependen de la energia en el marco
# de ICRP103 (a diferencia del Q(L) mas detallado de reportes anteriores).
W_R = {"GCR_H": 2.0, "GCR_He": 20.0, "SEP_p": 2.0}

MODEL_OF = {"GCR_H": "GCR", "GCR_He": "GCR", "SEP_p": "SEP"}


def parse_organ_line(line):
    """Parsea una linea de datos de AM_organs.dat: <id> <nombre...> <tissue_number> <density>.
    Devuelve (organ_id, nombre, tissue_number) o None si la linea no es de
    datos (encabezados, lineas vacias). El nombre puede tener comas/parentesis
    pero no tabs/espacios multiples con significado -- se reconstruye uniendo
    los tokens intermedios con un solo espacio, ya que solo se usa para
    matching por palabra clave, no para mostrarse con el espaciado original."""
    tokens = line.split()
    if len(tokens) < 4:
        return None
    try:
        organ_id = int(tokens[0])
        tissue_number = int(tokens[-2])
        float(tokens[-1])  # density, validado pero no usado aqui
    except ValueError:
        return None
    name = " ".join(tokens[1:-2])
    return organ_id, name, tissue_number


def load_organ_metadata(icrp_data_dir):
    """Lee AM_organs.dat -> {organ_id: (nombre, tissue_number)}. Devuelve {}
    y no falla si el archivo no existe (ver docstring del modulo)."""
    organs_path = icrp_data_dir / "ICRP110_g4dat" / "P110_data_V1.2" / "AM" / "AM_organs.dat"
    if not organs_path.is_file():
        print(f"ADVERTENCIA: no se encontro {organs_path} -- compila ActiveShield_Sim primero "
              "(ICRPdata/ se descarga automaticamente via CMake, ver AGENTS.md). "
              "Se omite la vista de riesgo estocastico.")
        return {}
    metadata = {0: ("Air", None)}
    with open(organs_path) as f:
        for line in f:
            parsed = parse_organ_line(line)
            if parsed is None:
                continue
            organ_id, name, tissue_number = parsed
            metadata[organ_id] = (name, tissue_number)
    return metadata


def load_organ_masses_kg(icrp_data_dir):
    """Lee ICRPdata/OrganMasses.dat (columna Male, en g) -> {organ_id: masa_kg}."""
    masses_path = icrp_data_dir / "OrganMasses.dat"
    if not masses_path.is_file():
        print(f"ADVERTENCIA: no se encontro {masses_path} -- se omite la vista de riesgo estocastico.")
        return {}
    masses = {}
    with open(masses_path) as f:
        next(f)  # encabezado
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            organ_id = int(parts[0])
            masses[organ_id] = float(parts[1]) / 1000.0  # g -> kg
    return masses


def load_rbm_fraction_by_tissue(icrp_data_dir):
    """Lee AM_spongiosa.dat -> {tissue_number: fraccion_RBM}. Columnas:
    Med(=tissue number) RBM YBM Bone -- ver docstring del modulo."""
    spongiosa_path = icrp_data_dir / "ICRP110_g4dat" / "P110_data_V1.2" / "AM" / "AM_spongiosa.dat"
    if not spongiosa_path.is_file():
        print(f"ADVERTENCIA: no se encontro {spongiosa_path} -- se omite medula osea roja "
              "de la vista de riesgo estocastico.")
        return {}
    fractions = {}
    with open(spongiosa_path) as f:
        next(f)  # encabezado "Med RBM YBM Bone"
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            fractions[int(parts[0])] = float(parts[1])
    return fractions


def build_category_organ_ids(organ_metadata):
    """{categoria: [organ_id,...]} emparejando por palabra clave sobre el
    nombre real (case-insensitive), excluyendo EXCLUDE_KEYWORDS. Advierte
    (no falla) si una palabra clave no matchea nada."""
    category_organ_ids = defaultdict(list)
    for category, keywords in CATEGORY_KEYWORDS.items():
        matched_by_keyword = {kw: [] for kw in keywords}
        for organ_id, (name, _tissue_number) in organ_metadata.items():
            lname = name.lower()
            if any(exc in lname for exc in EXCLUDE_KEYWORDS):
                continue
            for kw in keywords:
                if kw in lname:
                    matched_by_keyword[kw].append(organ_id)
        for kw, hits in matched_by_keyword.items():
            if not hits:
                print(f"ADVERTENCIA: la palabra clave '{kw}' (categoria '{category}') no matcheo "
                      "ningun organo -- revisar el nombre real en AM_organs.dat y ajustar "
                      "CATEGORY_KEYWORDS en este script.")
            category_organ_ids[category].extend(hits)
    return dict(category_organ_ids)


def build_rbm_organ_fractions(organ_metadata, rbm_fraction_by_tissue):
    """{organ_id: fraccion_RBM} para los organos espongiosa (identificados por
    tener un tissue_number presente en AM_spongiosa.dat) -- ver docstring."""
    rbm_organ_fractions = {}
    for organ_id, (_name, tissue_number) in organ_metadata.items():
        if tissue_number in rbm_fraction_by_tissue:
            rbm_organ_fractions[organ_id] = rbm_fraction_by_tissue[tissue_number]
    if not rbm_organ_fractions:
        print("ADVERTENCIA: ningun organo con tissue_number en AM_spongiosa.dat -- "
              "se omite medula osea roja de la vista de riesgo estocastico.")
    return rbm_organ_fractions


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=None,
                         help="resultados_organo_sweep.csv (default: <repo>/build/resultados_organo_sweep.csv)")
    parser.add_argument("--spectra-dir", type=Path, default=None,
                         help="Carpeta con los CSV de OLTARIS (default: <ActiveShield_Sim>/data)")
    parser.add_argument("--icrp-data-dir", type=Path, default=None,
                         help="Carpeta ICRPdata (default: <repo>/build/ICRPdata)")
    parser.add_argument("--ship-radius-m", type=float, default=4.5,
                         help="Debe coincidir con /spacecraft/shipRadius usado en la corrida (default 4.5, "
                              "escala real de CREW HaT usada por run_organ_sweep.py)")
    parser.add_argument("--ship-half-length-m", type=float, default=5.0,
                         help="Debe coincidir con /spacecraft/shipHalfLength usado (default 5.0)")
    parser.add_argument("--hull-thickness-cm", type=float, default=1.5,
                         help="Debe coincidir con /spacecraft/hullThickness usado (default 1.5)")
    parser.add_argument("--out", type=Path, default=None,
                         help="CSV agregado de salida (default: junto a --results)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    build_dir = project_root / "build"
    results_path = args.results or (build_dir / "resultados_organo_sweep.csv")
    spectra_dir = args.spectra_dir or (project_root / "data" / "sources" / "oltaris")
    icrp_data_dir = args.icrp_data_dir or (build_dir / "ICRPdata")
    out_path = args.out or (results_path.parent / "resultados_organo_agregados.csv")
    risk_out_path = out_path.parent / "resultados_riesgo_estocastico.csv"

    if not results_path.is_file():
        sys.exit(f"ERROR: no se encontro {results_path}. Corre run_organ_sweep.py primero.")

    # Radio de la esfera fuente, mismo criterio que
    # ICRP110PhantomConstruction::GetSourceSphereRadius (media diagonal del
    # cilindro + casco + margen de 20 cm) -- debe coincidir con los valores
    # de shipRadius/shipHalfLength/hullThickness realmente usados al correr
    # el barrido.
    ship_radius_cm = args.ship_radius_m * 100.0
    ship_half_length_cm = args.ship_half_length_m * 100.0
    source_radius_cm = math.sqrt(ship_radius_cm**2 + ship_half_length_cm**2) + args.hull_thickness_cm + 20.0
    area_cm2 = math.pi * source_radius_cm**2

    # weight_by_key[(especie, bin_index)] = W[s,bin] -- mismos bins/rango que
    # run_organ_sweep.py calculo al generar las macros (energy_bins.build_bins
    # es determinista dado el mismo spectra_dir, asi que se recalcula aqui en
    # vez de leerlo de resultados_organo_sweep.csv).
    bins_by_species = energy_bins.build_bins(spectra_dir)
    weight_by_key = {}
    print("Pesos fisicos W[s,bin] (primarios reales de esa franja de energia que cruzan la esfera fuente):")
    for species, bins in bins_by_species.items():
        unit = "primarios/dia" if MODEL_OF[species] == "GCR" else "primarios en el evento completo"
        for bin_index, energy_rep, flux_bin in bins:
            weight_by_key[(species, bin_index)] = area_cm2 * flux_bin
            print(f"  W[{species},bin{bin_index} E={energy_rep:.3e}] = {weight_by_key[(species, bin_index)]:.6e} ({unit})")

    def combine_bins(r_by_key_local):
        """{(especie,bin_index): R} (Gy/primario) -> (D_abs_GCR, D_eq_GCR, D_abs_SEP, D_eq_SEP)."""
        d_abs_gcr = d_eq_gcr = d_abs_sep = d_eq_sep = 0.0
        for (species, bin_index), r in r_by_key_local.items():
            w = weight_by_key[(species, bin_index)]
            contrib_abs = r * w
            contrib_eq = W_R[species] * contrib_abs
            if MODEL_OF[species] == "GCR":
                d_abs_gcr += contrib_abs
                d_eq_gcr += contrib_eq
            else:
                d_abs_sep += contrib_abs
                d_eq_sep += contrib_eq
        return d_abs_gcr, d_eq_gcr, d_abs_sep, d_eq_sep

    # edep_by_run[(especie, bin_index, offset_x_m)][organo_id] = edep_J
    # n_events_by_run[(especie, bin_index, offset_x_m)] = N
    edep_by_run = defaultdict(dict)
    n_events_by_run = {}
    with open(results_path, newline="") as f:
        for row in csv.DictReader(f):
            n = int(row["n_eventos"])
            if n == 0:
                continue
            run_key = (row["especie"], int(row["bin_index"]), float(row["offset_x_m"]))
            edep_by_run[run_key][int(row["organo_id"])] = float(row["edep_J"])
            n_events_by_run[run_key] = n

    # --- CSV completo por organo_id (sin agrupar), R[o,s,bin] = dose_gy_run/N ---
    r_by_key = defaultdict(dict)  # (organo_id, offset_x_m) -> {(species,bin_index): R}
    with open(results_path, newline="") as f:
        for row in csv.DictReader(f):
            n = int(row["n_eventos"])
            if n == 0:
                continue
            key = (int(row["organo_id"]), float(row["offset_x_m"]))
            r_by_key[key][(row["especie"], int(row["bin_index"]))] = float(row["dose_gy_run"]) / n

    out_fieldnames = ["organo_id", "offset_x_m",
                      "D_absorbida_GCR_Gy_dia", "D_equivalente_GCR_Sv_dia",
                      "D_absorbida_SEP_Gy_evento", "D_equivalente_SEP_Sv_evento"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        for (organo_id, offset_x_m), r_by_bin in sorted(r_by_key.items()):
            d_abs_gcr, d_eq_gcr, d_abs_sep, d_eq_sep = combine_bins(r_by_bin)
            writer.writerow({
                "organo_id": organo_id, "offset_x_m": offset_x_m,
                "D_absorbida_GCR_Gy_dia": d_abs_gcr, "D_equivalente_GCR_Sv_dia": d_eq_gcr,
                "D_absorbida_SEP_Gy_evento": d_abs_sep, "D_equivalente_SEP_Sv_evento": d_eq_sep,
            })
    print(f"\nAgregado completo (por organo_id, sin agrupar): {out_path}")

    # --- Vista de riesgo estocastico: 6 categorias ICRP103 w_T=0.12, cada una
    # agrupando varios organo_id en un solo valor ponderado por masa. ---
    organ_metadata = load_organ_metadata(icrp_data_dir)
    organ_masses_kg = load_organ_masses_kg(icrp_data_dir) if organ_metadata else {}
    if organ_metadata and organ_masses_kg:
        category_organ_ids = build_category_organ_ids(organ_metadata)
        rbm_fraction_by_tissue = load_rbm_fraction_by_tissue(icrp_data_dir)
        rbm_organ_fractions = build_rbm_organ_fractions(organ_metadata, rbm_fraction_by_tissue)

        # Masa fija por categoria (no depende de la corrida).
        pooled_mass_kg = {
            category: sum(organ_masses_kg.get(oid, 0.0) for oid in organ_ids)
            for category, organ_ids in category_organ_ids.items()
        }
        if rbm_organ_fractions:
            pooled_mass_kg["red_bone_marrow"] = sum(
                organ_masses_kg.get(oid, 0.0) * frac for oid, frac in rbm_organ_fractions.items()
            )

        offsets = sorted({offset for (_species, _bin, offset) in edep_by_run})
        species_bins = sorted({(species, bin_idx) for (species, bin_idx, _offset) in edep_by_run})
        risk_fieldnames = ["categoria", "offset_x_m", "masa_kg"] + out_fieldnames[2:]
        with open(risk_out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=risk_fieldnames)
            writer.writeheader()
            for category, organ_ids in {**category_organ_ids,
                                         **({"red_bone_marrow": None} if rbm_organ_fractions else {})}.items():
                mass_kg = pooled_mass_kg.get(category, 0.0)
                if mass_kg <= 0:
                    print(f"ADVERTENCIA: masa total 0 para la categoria '{category}' -- se omite.")
                    continue
                for offset_x_m in offsets:
                    r_by_bin = {}
                    for species, bin_idx in species_bins:
                        run_key = (species, bin_idx, offset_x_m)
                        if run_key not in edep_by_run:
                            continue
                        n = n_events_by_run[run_key]
                        if category == "red_bone_marrow":
                            pooled_edep = sum(
                                edep_by_run[run_key].get(oid, 0.0) * frac
                                for oid, frac in rbm_organ_fractions.items()
                            )
                        else:
                            pooled_edep = sum(edep_by_run[run_key].get(oid, 0.0) for oid in organ_ids)
                        r_by_bin[(species, bin_idx)] = (pooled_edep / mass_kg) / n
                    d_abs_gcr, d_eq_gcr, d_abs_sep, d_eq_sep = combine_bins(r_by_bin)
                    writer.writerow({
                        "categoria": category, "offset_x_m": offset_x_m, "masa_kg": mass_kg,
                        "D_absorbida_GCR_Gy_dia": d_abs_gcr, "D_equivalente_GCR_Sv_dia": d_eq_gcr,
                        "D_absorbida_SEP_Gy_evento": d_abs_sep, "D_equivalente_SEP_Sv_evento": d_eq_sep,
                    })
        print(f"Vista de riesgo estocastico (6 categorias ICRP103 w_T=0.12, por offset radial): {risk_out_path}")


if __name__ == "__main__":
    main()
