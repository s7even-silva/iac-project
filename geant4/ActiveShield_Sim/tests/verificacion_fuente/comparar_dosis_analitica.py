#!/usr/bin/env python3
"""Dosis de cuerpo entero de dosis_fantoma_desnudo.mac frente a Phi*(S/rho) de pura ionizacion.
Uso: python3 comparar_dosis_analitica.py <ICRP110.out> [N_primarios] (desde geant4/ActiveShield_Sim)."""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_organ_sweep as ros, energy_bins as eb, aggregate_organ_doses as ag
base = Path(__file__).resolve().parents[2]
rows = ros.parse_icrp110_out(Path(sys.argv[1]))
masas = ag.load_organ_masses_kg(base / "build" / "ICRPdata")
ids = [k for k in rows if k not in (0, 140)]
edep = sum(rows[k]["edep_J"] for k in ids); m = sum(masas.get(k, 0) for k in ids)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40000
R = math.sqrt(450**2 + 500**2) + 0.001 + 20.0
phi = [f for i, E, f in eb.build_bins(base / "data" / "sources" / "oltaris")[("GCR_H", "min")] if i == 4][0]
D_sim = math.pi * R**2 * phi * edep / (m * N)
me, Mp, T, K, ZA, I = 0.51099895, 938.272, 1778.28, 0.307075, 0.55508, 75e-6
g = 1 + T / Mp; b2 = 1 - 1 / g**2
Tmax = 2 * me * b2 * g**2 / (1 + 2 * g * me / Mp + (me / Mp)**2)
S = K * ZA / b2 * (0.5 * math.log(2 * me * b2 * g**2 * Tmax / I**2) - b2)   # Bethe, agua, sin correccion de densidad
D_an = phi * S * 1.602176634e-10
print(f"D simulada {D_sim:.4e} Gy/dia, D ionizacion {D_an:.4e} Gy/dia, cociente {D_sim/D_an:.3f}")
