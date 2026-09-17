#!/usr/bin/env python3
"""Bins de energia monoenergeticos para el barrido de dosis por organo, con
reponderacion por el flujo/fluencia real de OLTARIS -- sigue la decision de
equipo registrada en AGENTS.md ("Bins de energia + reponderacion para
produccion... No portar muestreo continuo como plan de produccion"), que el
primer intento de esta tarea (2026-09-10/11) no siguio por descuido (usaba
SpectrumSampler para MUESTREO CONTINUO, el metodo que esa decision dice
explicitamente que no se use para produccion -- corregido 2026-09-11).

Rango de cada espectro (2026-09-11, decision propia -- AGENTS.md dejaba
"bordes/rango" como pendiente): NO se usa el rango tabulado completo de
OLTARIS (8 decadas para GCR, 1e-2 a 1e6 MeV/amu) porque los extremos
contribuyen una fraccion despreciable del flujo real. Se usa en cambio el
rango que cubre >99.9% del flujo/fluencia integrado (percentiles calculados
directamente de los CSV reales, no supuestos):

    GCR_H  min (gcr_proton_solarmin.csv):  10 - 1e5     MeV/amu  (cubre 99.911%)
    GCR_H  max (gcr_proton_solarmax.csv):  30 - 3e5     MeV/amu  (cubre 99.906%)
    GCR_He min (gcr_alpha_solarmin.csv):   10 - 1e5     MeV/amu  (cubre 99.902%)
    GCR_He max (gcr_alpha_solarmax.csv):   10 - 1e5     MeV/amu  (cubre 99.912%)
    SEP_p  max (sep_proton_solarmax.csv):  0.01 - 300   MeV      (cubre 99.983%)
    SEP_p  min (sep_proton_solarmin.csv):  0.03 - 2500  MeV      (cubre 99.932%)

Los 3 rangos de "min" (GCR_H, GCR_He) y "max" (SEP_p) son los originales,
calculados el 2026-09-11 (ver arriba). Los 3 de "max" (GCR_H, GCR_He) y
"min" (SEP_p) se agregaron el 2026-09-16 al expandir el barrido a las 6
combinaciones especie x fase (antes cada especie corria en una sola fase
fija) -- MISMO metodo exacto (busqueda del rango mas angosto, entre
bordes candidatos en potencias redondas de 10, que cubra >=99.9% de la
integral trapezoidal total del CSV), verificado reproduciendo primero los
3 porcentajes ya documentados arriba antes de confiar en los 3 nuevos
(coincidencia exacta hasta el tercer decimal). NO se asumio que el rango
de la fase ya conocida sirviera para la fase nueva de la misma especie --
la forma espectral difiere entre min/max (confirmado leyendo los CSV: el
espectro SEP-min, por ejemplo, es mas "duro"/de cola mas pesada que
SEP-max, ver AGENTS.md) asi que cada uno de los 6 rangos se calculo por
separado contra su propio CSV.

Bins log-espaciados (espaciado geometrico uniforme, estandar para espectros
que caen varias decadas) dentro de ese rango; energia representativa de cada
bin = media geometrica de sus bordes. El peso fisico de cada bin (cuantos
primarios reales de esa franja de energia cruzan la esfera fuente) se
calcula igual que el peso W[s] de todo el espectro en RunAction.cc/
aggregate_organ_doses.py, pero con la integral trapezoidal restringida a
[borde_inferior, borde_superior] del bin en vez de todo el rango tabulado:

    W[s,bin] = pi * R_esfera_fuente_cm^2 * integral_(borde_inf a borde_sup) Flujo_s(E) dE

Esto reemplaza W[s] (todo el espectro) del script anterior por una suma de
W[s,bin] sobre los bins -- Sum_bin W[s,bin] es ligeramente MENOR que W[s]
completo (no llega al 100% del flujo, ver arriba) porque se recorta el
0.02-0.1% de flujo en los extremos, no por error de la integral.
"""
import math

# (species, phase) -> (archivo_csv, energia_min, energia_max) -- ver
# docstring del modulo por el razonamiento del rango. Mismas unidades
# nativas del CSV (MeV/amu para GCR, MeV para SEP) -- SampleEnergy()/el
# override monoenergetico usan esa misma convencion nativa, ver
# ICRP110PhantomPrimaryGeneratorAction.cc.
#
# Indexado por (species, phase), no solo species (2026-09-16, antes 1:1) --
# necesario para las 3 combinaciones nuevas (GCR_H/max, GCR_He/max,
# SEP_p/min) que expanden el barrido de 3 a 6 casos especie x fase. Las 3
# entradas "min"/"max" ya en produccion (indices [0]) NO cambiaron de
# valor -- mismo archivo/rango exacto que antes, solo la clave del dict
# gano la dimension phase.
SPECIES_RANGE = {
    ("GCR_H", "min"):  ("gcr_proton_solarmin.csv", 10.0, 1.0e5),
    ("GCR_H", "max"):  ("gcr_proton_solarmax.csv", 30.0, 3.0e5),
    ("GCR_He", "min"): ("gcr_alpha_solarmin.csv", 10.0, 1.0e5),
    ("GCR_He", "max"): ("gcr_alpha_solarmax.csv", 10.0, 1.0e5),
    ("SEP_p", "max"):  ("sep_proton_solarmax.csv", 0.01, 300.0),
    ("SEP_p", "min"):  ("sep_proton_solarmin.csv", 0.03, 2500.0),
}

N_BINS_PER_SPECIES = 8  # decision 2026-09-11, ver AGENTS.md (opciones evaluadas: 5/8/10)


def load_spectrum(csv_path):
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
    return energies, fluxes


def integral_between(energies, fluxes, lo, hi):
    """Integral trapezoidal de la funcion lineal a trozos definida por
    (energies, fluxes) entre lo y hi (ambos deben estar dentro del rango
    tabulado), interpolando linealmente en los extremos si no coinciden con
    un punto tabulado. Misma logica que integrated_flux() en
    aggregate_organ_doses.py, generalizada a un sub-rango arbitrario."""
    if lo < energies[0] or hi > energies[-1] or lo >= hi:
        raise ValueError(f"Rango de bin [{lo},{hi}] fuera de los datos tabulados "
                          f"[{energies[0]},{energies[-1]}] o invalido")

    def interp(e):
        for i in range(1, len(energies)):
            if energies[i] >= e:
                t = (e - energies[i-1]) / (energies[i] - energies[i-1])
                return fluxes[i-1] + t * (fluxes[i] - fluxes[i-1])
        return fluxes[-1]

    points_e = [lo] + [e for e in energies if lo < e < hi] + [hi]
    points_f = [interp(lo)] + [fluxes[energies.index(e)] for e in energies if lo < e < hi] + [interp(hi)]
    total = 0.0
    for i in range(1, len(points_e)):
        d_e = points_e[i] - points_e[i-1]
        avg_flux = 0.5 * (points_f[i] + points_f[i-1])
        total += avg_flux * d_e
    return total


def log_bin_edges(lo, hi, n_bins):
    return [lo * (hi / lo) ** (i / n_bins) for i in range(n_bins + 1)]


def bin_representative_energy(edge_lo, edge_hi):
    return math.sqrt(edge_lo * edge_hi)  # media geometrica, estandar para bins log-espaciados


def build_bins(spectra_dir, n_bins=N_BINS_PER_SPECIES):
    """{(species, phase): [(bin_index, energy_rep, integrated_flux_bin), ...]}
    para las 6 combinaciones de SPECIES_RANGE, leyendo sus CSV reales
    desde spectra_dir. Indexado por (species, phase) desde 2026-09-16
    (antes solo species, cuando cada especie tenia una unica fase fija) --
    ver SPECIES_RANGE."""
    bins_by_key = {}
    for (species, phase), (filename, lo, hi) in SPECIES_RANGE.items():
        energies, fluxes = load_spectrum(spectra_dir / filename)
        edges = log_bin_edges(lo, hi, n_bins)
        bins = []
        for i in range(n_bins):
            e_rep = bin_representative_energy(edges[i], edges[i+1])
            flux_bin = integral_between(energies, fluxes, edges[i], edges[i+1])
            bins.append((i, e_rep, flux_bin))
        bins_by_key[(species, phase)] = bins
    return bins_by_key
