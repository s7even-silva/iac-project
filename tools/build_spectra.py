"""Build src/data/spectra.json for Box 1 from the OLTARIS CSVs on main.

Usage: python3 tools/build_spectra.py <path to geant4/ActiveShield_Sim/data/sources/oltaris>

Each spectrum is converted from dN/dT (per MeV/nucleon) to the share of
particles per decade of rigidity, for kinetic energies >= 10 MeV/nucleon,
and its cumulative fraction in rigidity.
"""
import json
import math
import sys
from pathlib import Path

# Mass per nucleon (MeV) and A/Z for each species.
SPECIES = {
    "p": {"mu": 938.272, "A": 1, "Z": 1},
    "He": {"mu": 3727.379 / 4, "A": 4, "Z": 2},
}
SPECTRA = [
    ("gcr_h", "gcr_proton_solarmin.csv", "p", "GCR protons, solar minimum (BON2020)"),
    ("gcr_he", "gcr_alpha_solarmin.csv", "He", "GCR helium, solar minimum (BON2020)"),
    ("sep", "sep_proton_solarmax.csv", "p", "SEP protons, October 1989 event"),
]
T_MIN = 10.0  # MeV/nucleon


def rigidity_gv(tn, sp):
    s = SPECIES[sp]
    pn = math.sqrt(tn * (tn + 2 * s["mu"]))  # MeV/c per nucleon
    return s["A"] * pn / s["Z"] / 1000.0


def load(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        t, f = line.split(",")
        rows.append((float(t), float(f)))
    return rows


def main(src):
    out = {"source": "NASA OLTARIS exports, iac-project main: geant4/ActiveShield_Sim/data/sources/oltaris",
           "t_min_mev_per_n": T_MIN, "spectra": {}}
    for key, fname, sp, label in SPECTRA:
        s = SPECIES[sp]
        rows = [(t, f) for t, f in load(Path(src) / fname) if t >= T_MIN and f > 0]
        lr, dens = [], []
        for t, f in rows:
            pn = math.sqrt(t * (t + 2 * s["mu"]))
            # dN/dlog10R = ln10 * dN/dT * p_n^2 / (T + mu)
            lr.append(math.log10(rigidity_gv(t, sp)))
            dens.append(math.log(10) * f * pn * pn / (t + s["mu"]))
        # Trapezoidal integral in log10 R, then normalise to percent per decade.
        cum = [0.0]
        for i in range(1, len(lr)):
            cum.append(cum[-1] + 0.5 * (dens[i] + dens[i - 1]) * (lr[i] - lr[i - 1]))
        total = cum[-1]
        out["spectra"][key] = {
            "label": label,
            "species": sp,
            "log10_R_GV": [round(x, 5) for x in lr],
            "pct_per_decade": [round(100 * d / total, 5) for d in dens],
            "cdf": [round(c / total, 6) for c in cum],
        }
    # Imported by the Vue code, so it is bundled into the page: no fetch at
    # the venue.
    Path(__file__).resolve().parent.parent.joinpath("src", "data", "spectra.json").write_text(
        json.dumps(out, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
