#!/usr/bin/env python3
"""Combina resultados_organo_sweep.csv (salida de run_organ_sweep.py) con los
espectros reales de OLTARIS para dar dosis absorbida y equivalente por
organo y posicion del fantoma, en el escenario fijo de blindaje maximo (10 T)
+ evento mas peligroso por especie (ver run_organ_sweep.py y AGENTS.md).

Reimplementa en Python puro (sin numpy) la misma integral trapezoidal que
SpectrumSampler.cc usa para el flujo/fluencia integrado, y la misma formula
de normalizacion fisica que GCR_SEP_Sim/src/RunAction.cc:

    R[o,s] = edep_J[o,s] / (masa_kg[o] * N[s])   -- ya viene resuelto en
                                                      resultados_organo_sweep.csv
                                                      como dose_gy_run/N[s]
                                                      (dose_gy_run = edep/masa
                                                      acumulado en la corrida)
    W[s]   = pi * R_esfera_fuente_cm^2 * flujo_integrado[s]
    D_absorbida[o]   = suma_s R[o,s] * W[s]              (Gy)
    D_equivalente[o] = suma_s w_R[s] * R[o,s] * W[s]      (Sv)

w_R (ICRP 103 Tabla A.3): proton = 2, particula alfa = 20 -- ver AGENTS.md
para la limitacion explicita (pondera por primario de la corrida, no por
particula-en-cada-paso).

GCR y SEP NO se suman entre si: GCR_H/GCR_He dan un resultado en Gy/dia (el
flujo de OLTARIS ya viene por dia), SEP_p en Gy/evento completo (Oct 1989) --
semantica temporal distinta, igual que en GCR_SEP_Sim (ver AGENTS.md).

Ademas del CSV agregado completo (por organo_id), genera una vista filtrada
a los organos de mayor riesgo estocastico de cancer -- ICRP 103 Tabla A.1,
los w_T=0.12 mas altos: colon, pulmon, estomago, mama -- emparejando por
palabra clave sobre el nombre real de organo (leido de
ICRPdata/.../AM_organs.dat, descargado automaticamente al compilar, ver
CMakeLists.txt). Si esa carpeta no existe todavia (no se ha compilado en
este entorno) o si alguna palabra clave no matchea ningun organo real, se
imprime una advertencia explicita -- no falla en silencio, ver AGENTS.md
("nunca asumir sin verificar contra el archivo real").

NO incluye medula osea roja (el w_T=0.12 restante) a proposito, verificado
contra el AM_organs.dat real: ICRP110 no la modela como un organ_id propio
-- esta distribuida como una FRACCION de la dosis de "spongiosa" (hueso
esponjoso) en cada sitio esqueletico, dada por AM_spongiosa.dat (columnas
RBM/YBM/Bone por ID de tejido, no de organo). ICRP110UserScoreWriter no
calcula esa fraccion -- ICRP110.out solo da Edep/Dosis por organ_id, no
ponderado por contenido de medula. Agregarla exigiria leer
AM_spongiosa.dat y cruzarlo con el ID de tejido (no de organo) de cada
voxel -- fuera de alcance de este script, ver AGENTS.md.
"""
import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

# Palabras clave (ICRP103 Tabla A.1, w_T=0.12) para la vista de riesgo
# estocastico. Fantoma masculino (AM): la mama SI esta segmentada en ICRP110
# para ambos sexos, pero w_T=0.12 es un valor promediado por sexo -- ver
# AGENTS.md por la limitacion de interpretar riesgo de cancer de mama a
# partir de un fantoma masculino. Medula osea roja (el w_T=0.12 restante) NO
# esta aqui -- ICRP110 no la modela como organ_id propio, ver docstring del
# modulo.
STOCHASTIC_RISK_KEYWORDS = ["colon", "lung", "stomach", "breast"]

# w_R, ICRP 103 Tabla A.3.
W_R = {"GCR_H": 2.0, "GCR_He": 20.0, "SEP_p": 2.0}

SPECTRUM_FILES = {
    "GCR_H":  "gcr_proton_solarmin.csv",
    "GCR_He": "gcr_alpha_solarmin.csv",
    "SEP_p":  "sep_proton_solarmax.csv",
}
MODEL_OF = {"GCR_H": "GCR", "GCR_He": "GCR", "SEP_p": "SEP"}


def integrated_flux(csv_path):
    """Integral trapezoidal del flujo/fluencia diferencial, identica a
    SpectrumSampler::SpectrumSampler (energia,flujo por linea, '#' = comentario)."""
    energies, fluxes = [], []
    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            e_str, f_str = line.replace(",", " ").split()[:2]
            energies.append(float(e_str))
            fluxes.append(float(f_str))
    if len(energies) < 2:
        raise ValueError(f"{csv_path}: muy pocos puntos validos")
    total = 0.0
    for i in range(1, len(energies)):
        d_e = energies[i] - energies[i-1]
        avg_flux = 0.5 * (fluxes[i] + fluxes[i-1])
        total += avg_flux * d_e
    return total


def load_organ_names(icrp_data_dir):
    """Lee ICRPdata/ICRP110_g4dat/P110_data_V1.2/AM/AM_organs.dat (mismo
    archivo que ICRP110UserScoreWriter.cc abre en runtime) y devuelve
    {organ_id: nombre_crudo_de_la_linea}. Formato de esa linea: se asume que
    el primer token es el ID (igual que el resto del archivo -- ver
    ICRP110UserScoreWriter.cc lineas ~370-410); el resto de la linea se
    reporta tal cual, sin recortar, porque su formato exacto (columnas de
    Material ID/densidad) no se ha verificado contra el archivo real en este
    entorno (ICRPdata/ aun no se descarga hasta compilar, ver AGENTS.md).
    Devuelve {} y no falla si el archivo no existe -- la vista de riesgo
    estocastico se omite en ese caso, con una advertencia."""
    organs_path = icrp_data_dir / "ICRP110_g4dat" / "P110_data_V1.2" / "AM" / "AM_organs.dat"
    if not organs_path.is_file():
        print(f"ADVERTENCIA: no se encontro {organs_path} -- compila ActiveShield_Sim primero "
              "(ICRPdata/ se descarga automaticamente via CMake, ver AGENTS.md). "
              "Se omite la vista de riesgo estocastico (nombres de organo).")
        return {}
    names = {0: "0 Air"}
    with open(organs_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            token = line.split()[0]
            try:
                organ_id = int(token)
            except ValueError:
                continue
            names[organ_id] = line.strip()
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", type=Path, default=None,
                         help="resultados_organo_sweep.csv (default: <repo>/build/resultados_organo_sweep.csv)")
    parser.add_argument("--spectra-dir", type=Path, default=None,
                         help="Carpeta con los CSV de OLTARIS (default: <ActiveShield_Sim>/data)")
    parser.add_argument("--icrp-data-dir", type=Path, default=None,
                         help="Carpeta ICRPdata (default: <repo>/build/ICRPdata)")
    parser.add_argument("--ship-radius-m", type=float, default=2.8,
                         help="Debe coincidir con /spacecraft/shipRadius usado en la corrida (default 2.8, el "
                              "default de ICRP110PhantomConstruction)")
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
    spectra_dir = args.spectra_dir or (project_root / "data")
    icrp_data_dir = args.icrp_data_dir or (build_dir / "ICRPdata")
    out_path = args.out or (results_path.parent / "resultados_organo_agregados.csv")
    risk_out_path = out_path.parent / "resultados_riesgo_estocastico.csv"

    if not results_path.is_file():
        sys.exit(f"ERROR: no se encontro {results_path}. Corre run_organ_sweep.py primero.")

    # Radio de la esfera fuente, mismo critero que
    # ICRP110PhantomConstruction::GetSourceSphereRadius (media diagonal del
    # cilindro + casco + margen de 20 cm) -- debe coincidir con los valores
    # de shipRadius/shipHalfLength/hullThickness realmente usados al correr
    # el barrido (los defaults de C++ si no se sobreescribieron con
    # /spacecraft/... en la macro, que run_organ_sweep.py no hace).
    ship_radius_cm = args.ship_radius_m * 100.0
    ship_half_length_cm = args.ship_half_length_m * 100.0
    source_radius_cm = math.sqrt(ship_radius_cm**2 + ship_half_length_cm**2) + args.hull_thickness_cm + 20.0
    area_cm2 = math.pi * source_radius_cm**2

    integrated_flux_by_species = {}
    for species, filename in SPECTRUM_FILES.items():
        csv_path = spectra_dir / filename
        if not csv_path.is_file():
            sys.exit(f"ERROR: no se encontro {csv_path} (espectro de {species}).")
        integrated_flux_by_species[species] = integrated_flux(csv_path)

    weight_by_species = {s: area_cm2 * flux for s, flux in integrated_flux_by_species.items()}
    print("Pesos fisicos W[s] (primarios reales que cruzan la esfera fuente):")
    for species, w in weight_by_species.items():
        unit = "primarios/dia" if MODEL_OF[species] == "GCR" else "primarios en el evento completo"
        print(f"  W[{species}] = {w:.6e} ({unit})")

    # R[o,s] por (organo, posicion, especie): dose_gy_run/N ya es el "Gy por
    # primario simulado de esa especie" (R[s] en RunAction.cc), aplicado por
    # organo en vez de a todo el fantoma.
    r_by_key = defaultdict(dict)  # (organo_id, position_cm) -> {species: R}
    with open(results_path, newline="") as f:
        for row in csv.DictReader(f):
            n = int(row["n_eventos"])
            if n == 0:
                continue
            key = (int(row["organo_id"]), float(row["position_cm"]))
            species = row["especie"]
            r_by_key[key][species] = float(row["dose_gy_run"]) / n

    out_fieldnames = ["organo_id", "position_cm",
                      "D_absorbida_GCR_Gy_dia", "D_equivalente_GCR_Sv_dia",
                      "D_absorbida_SEP_Gy_evento", "D_equivalente_SEP_Sv_evento"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        for (organo_id, position_cm), r_by_species in sorted(r_by_key.items()):
            d_abs_gcr = d_eq_gcr = d_abs_sep = d_eq_sep = 0.0
            for species, r in r_by_species.items():
                w = weight_by_species[species]
                contrib_abs = r * w
                contrib_eq = W_R[species] * contrib_abs
                if MODEL_OF[species] == "GCR":
                    d_abs_gcr += contrib_abs
                    d_eq_gcr += contrib_eq
                else:
                    d_abs_sep += contrib_abs
                    d_eq_sep += contrib_eq
            writer.writerow({
                "organo_id": organo_id, "position_cm": position_cm,
                "D_absorbida_GCR_Gy_dia": d_abs_gcr, "D_equivalente_GCR_Sv_dia": d_eq_gcr,
                "D_absorbida_SEP_Gy_evento": d_abs_sep, "D_equivalente_SEP_Sv_evento": d_eq_sep,
            })
    print(f"\nAgregado completo (por organo_id): {out_path}")

    # Vista de riesgo estocastico: filtra a los organos con mas peso ICRP103
    # (w_T=0.12), emparejando por palabra clave sobre el nombre real.
    organ_names = load_organ_names(icrp_data_dir)
    if organ_names:
        matched_ids = {}
        for keyword in STOCHASTIC_RISK_KEYWORDS:
            hits = [oid for oid, name in organ_names.items() if keyword in name.lower()]
            if not hits:
                print(f"ADVERTENCIA: la palabra clave '{keyword}' no matcheo ningun organo en "
                      f"{icrp_data_dir} -- revisar el nombre real en AM_organs.dat y ajustar "
                      "STOCHASTIC_RISK_KEYWORDS en este script.")
            for oid in hits:
                matched_ids[oid] = keyword

        with open(risk_out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["organo_id", "organo_nombre", "palabra_clave"] + out_fieldnames[1:])
            writer.writeheader()
            for (organo_id, position_cm), r_by_species in sorted(r_by_key.items(), key=lambda kv: kv[0][1]):
                if organo_id not in matched_ids:
                    continue
                d_abs_gcr = d_eq_gcr = d_abs_sep = d_eq_sep = 0.0
                for species, r in r_by_species.items():
                    w = weight_by_species[species]
                    contrib_abs = r * w
                    contrib_eq = W_R[species] * contrib_abs
                    if MODEL_OF[species] == "GCR":
                        d_abs_gcr += contrib_abs
                        d_eq_gcr += contrib_eq
                    else:
                        d_abs_sep += contrib_abs
                        d_eq_sep += contrib_eq
                writer.writerow({
                    "organo_id": organo_id, "organo_nombre": organ_names[organo_id],
                    "palabra_clave": matched_ids[organo_id], "position_cm": position_cm,
                    "D_absorbida_GCR_Gy_dia": d_abs_gcr, "D_equivalente_GCR_Sv_dia": d_eq_gcr,
                    "D_absorbida_SEP_Gy_evento": d_abs_sep, "D_equivalente_SEP_Sv_evento": d_eq_sep,
                })
        print(f"Vista de riesgo estocastico (organos ICRP103 w_T=0.12, por posicion): {risk_out_path}")


if __name__ == "__main__":
    main()
