#!/usr/bin/env python3
"""Convierte un CSV de espectro OLTARIS (mismo formato que usa
GCR_SEP_Sim/data/sources/oltaris/*.csv) en lineas de macro GPS
(`/gps/ene/type Arb` + `/gps/hist/point`) para ActiveShield_Sim.

ActiveShield_Sim usa G4GeneralParticleSource (GPS) en vez del
SpectrumSampler.cc a medida de GCR_SEP_Sim -- no hay binario propio que
lea el CSV directamente. Este modulo es el puente: reusa los mismos 3
archivos OLTARIS ya exportados (ver docs/checklist_espectros_reales.md
de GCR_SEP_Sim) sin duplicarlos ni tocar su formato.

Conversion de energia MeV/amu -> MeV total: para GCR (proton, alpha) el
CSV reporta energia por nucleon; GPS interpreta siempre energia cinetica
TOTAL de la particula (confirmado en PrimaryGeneratorAction.cc de
GCR_SEP_Sim: `kineticEnergy = keMeVPerNucleon * A * MeV`) -- por eso el
CSV de GCR se multiplica aqui por el numero de masa A antes de escribir
los puntos GPS. SEP (proton, A=1) no necesita conversion.

**No validado todavia contra SpectrumSampler.cc**: ambas implementaciones
deberian producir la misma forma de espectro, pero GPS interpola con su
propia convencion (`/gps/hist/inter Lin`, tipo "Arb") -- antes de confiar
en resultados de produccion, comparar un histograma de energias
muestreadas por GPS contra el CSV de origen (ver README de
ActiveShield_Sim, seccion del lanzador).
"""
from pathlib import Path


def read_oltaris_csv(path: Path, mass_number: int = 1):
    """Lee un CSV de 2 columnas (energia, flujo_diferencial), ignorando
    lineas de comentario ('#'). Devuelve pares (energia_MeV_total, flujo)
    ordenados por energia ascendente, escalando la energia por
    mass_number (1 para proton/SEP, 4 para alpha)."""
    points = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        energy_str, flux_str = line.split(",")
        points.append((float(energy_str) * mass_number, float(flux_str)))
    points.sort(key=lambda p: p[0])
    if len(points) < 2:
        raise ValueError(f"{path}: se necesitan al menos 2 puntos de espectro")
    return points


def gps_histogram_lines(path: Path, mass_number: int = 1, particle: str = "proton") -> list[str]:
    """Genera las lineas de macro GPS para muestrear energias con la
    forma del espectro de `path`. El flujo se usa solo como forma de la
    distribucion (peso relativo de muestreo), no como normalizacion
    absoluta -- la ponderacion fisica real (W[s,i], ver
    ActiveShield_Sim/docs/modelo_realista.md) es un paso aparte,
    pendiente, igual que en GCR_SEP_Sim (ver AGENTS.md, "Dosis absoluta
    pendiente de implementar")."""
    points = read_oltaris_csv(path, mass_number)
    lines = [
        f"/gps/particle {particle}",
        "/gps/ene/type Arb",
        "/gps/hist/type arb",
        "/gps/ene/unit MeV",
    ]
    for energy_mev, flux in points:
        lines.append(f"/gps/hist/point {energy_mev:.6E} {flux:.6E}")
    lines.append("/gps/hist/inter Lin")
    return lines


# Las 3 especies con espectro real OLTARIS ya exportado (2026-09-08) --
# ver GCR_SEP_Sim/docs/checklist_espectros_reales.md. Son las mismas 3
# combinaciones de mayor dosis por especie priorizadas para GCR_SEP_Sim;
# se reutilizan aqui como "especies mas peligrosas" para el segundo grupo
# de datos de ActiveShield_Sim (15 corridas), en vez de definir un
# criterio de peligrosidad nuevo y no verificado.
OLTARIS_DIR = (Path(__file__).resolve().parent.parent.parent
               / "GCR_SEP_Sim" / "data" / "sources" / "oltaris")

PRIORITY_SPECIES = [
    # (etiqueta, archivo, particula GPS, numero de masa)
    ("GCR_proton_min", OLTARIS_DIR / "gcr_proton_solarmin.csv", "proton", 1),
    ("GCR_alpha_min", OLTARIS_DIR / "gcr_alpha_solarmin.csv", "alpha", 4),
    ("SEP_proton_max", OLTARIS_DIR / "sep_proton_solarmax.csv", "proton", 1),
]
