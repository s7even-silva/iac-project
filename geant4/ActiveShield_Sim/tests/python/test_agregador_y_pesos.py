"""Tests de regresión T6 y T7 de docs/bitacora/plan_barrido.md (sección 8).

T6: el agregador da dosis por primario (sin factor N) y rechaza duplicados,
    energías que no son de la grilla y grillas mezcladas.
T7: la suma de los pesos por bin reproduce la integral del espectro en el
    rango cubierto (error relativo < 1e-6).

Correr con: python3 -m pytest geant4/ActiveShield_Sim/tests/python
"""
import csv
import math
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT/"scripts"
SPECTRA = PROJECT/"data"/"sources"/"oltaris"
sys.path.insert(0, str(SCRIPTS))
import energy_bins  # noqa: E402

FIELDS = ["especie", "fase", "bin_index", "n_bins", "energy_mev", "offset_x_m", "repeticion",
          "organo_id", "edep_J", "dose_gy_run", "n_eventos"]
MASS_KG = 2.0
R_M = 10.0


# --- T7 -------------------------------------------------------------------

@pytest.mark.parametrize("n_bins", [8, 16])
def test_t7_suma_de_pesos_igual_a_integral(n_bins):
    bins_by_key = energy_bins.build_bins(SPECTRA, n_bins=n_bins)
    for (species, phase), bins in bins_by_key.items():
        filename, lo, hi = energy_bins.SPECIES_RANGE[(species, phase)]
        energies, fluxes = energy_bins.load_spectrum(SPECTRA/filename)
        total = energy_bins.integral_between(energies, fluxes, lo, hi)
        area = math.pi*(R_M*100)**2
        weights = sum(area*flux for _i, _e, flux in bins)
        assert weights/area == pytest.approx(total, rel=1e-6), (species, phase)


def test_t7_integral_trapecio_exacta_para_funcion_lineal():
    energies = [1.0, 2.0, 5.0, 10.0]
    fluxes = [3.0+2.0*e for e in energies]
    # La interpolación es lineal a trozos: exacta para una recta.
    lo, hi = 1.5, 7.0
    exact = 3.0*(hi-lo)+(hi**2-lo**2)
    assert energy_bins.integral_between(energies, fluxes, lo, hi) == pytest.approx(exact, rel=1e-12)


# --- T6 -------------------------------------------------------------------

def _row(bins, species="GCR_H", phase="min", b=0, offset=0.0, rep=0, organ=1, edep=1e-9, n=1000,
         n_bins=8, energy=None):
    e = bins[(species, phase)][b][1] if energy is None else energy
    return {"especie": species, "fase": phase, "bin_index": b, "n_bins": n_bins, "energy_mev": e,
            "offset_x_m": offset, "repeticion": rep, "organo_id": organ, "edep_J": edep,
            "dose_gy_run": edep/MASS_KG, "n_eventos": n}


def _write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _aggregate(tmp_path, *paths):
    out = tmp_path/"agregado.csv"
    proc = subprocess.run([sys.executable, str(SCRIPTS/"aggregate_organ_doses.py"),
                           "--results", *map(str, paths), "--spectra-dir", str(SPECTRA),
                           "--icrp-data-dir", str(tmp_path/"sin_icrp"),
                           "--source-sphere-radius-m", str(R_M), "--out", str(out)],
                          capture_output=True, text=True)
    return proc, out


@pytest.fixture(scope="module")
def bins8():
    return energy_bins.build_bins(SPECTRA, n_bins=8)


def test_t6_dosis_por_primario_sin_factor_n(tmp_path, bins8):
    # Dos repeticiones con N distinto: R = (edep1+edep2)/(masa*(N1+N2)).
    rows = [_row(bins8, rep=0, edep=3e-9, n=1000), _row(bins8, rep=1, edep=5e-9, n=3000)]
    _write(tmp_path/"r.csv", rows)
    proc, out = _aggregate(tmp_path, tmp_path/"r.csv")
    assert proc.returncode == 0, proc.stdout+proc.stderr
    r = (3e-9+5e-9)/(MASS_KG*4000)
    w = math.pi*(R_M*100)**2*bins8[("GCR_H", "min")][0][2]
    got = next(csv.DictReader(open(out)))
    assert float(got["D_absorbida_GCR_Gy_dia"]) == pytest.approx(r*w, rel=1e-9)
    assert float(got["D_equivalente_GCR_Sv_dia"]) == pytest.approx(2.0*r*w, rel=1e-9)


def test_t6_rechaza_fila_duplicada_entre_archivos(tmp_path, bins8):
    _write(tmp_path/"a.csv", [_row(bins8)])
    _write(tmp_path/"b.csv", [_row(bins8)])
    proc, _ = _aggregate(tmp_path, tmp_path/"a.csv", tmp_path/"b.csv")
    assert proc.returncode != 0 and "duplicada" in proc.stdout+proc.stderr


def test_t6_rechaza_energia_fuera_de_grilla(tmp_path, bins8):
    _write(tmp_path/"r.csv", [_row(bins8, energy=123.456)])
    proc, _ = _aggregate(tmp_path, tmp_path/"r.csv")
    assert proc.returncode != 0 and "energy_mev" in proc.stdout+proc.stderr


def test_t6_rechaza_grillas_mezcladas(tmp_path, bins8):
    bins16 = energy_bins.build_bins(SPECTRA, n_bins=16)
    _write(tmp_path/"r.csv", [_row(bins8), _row(bins16, n_bins=16, b=1, organ=2)])
    proc, _ = _aggregate(tmp_path, tmp_path/"r.csv")
    assert proc.returncode != 0 and "grillas" in proc.stdout+proc.stderr


def test_t6_rechaza_n_inconsistente_en_una_corrida(tmp_path, bins8):
    _write(tmp_path/"r.csv", [_row(bins8, organ=1, n=1000), _row(bins8, organ=2, n=999)])
    proc, _ = _aggregate(tmp_path, tmp_path/"r.csv")
    assert proc.returncode != 0 and "inconsistente" in proc.stdout+proc.stderr


# --- run_organ_sweep --event-stats ---------------------------------------

def test_parse_event_stats_dosis_y_truncadas(tmp_path):
    import run_organ_sweep
    tsv = tmp_path/"EventStats.tsv"
    header = ("checkpoint\tM\tkind\tid\tS1_J\tS2_J2\tn_nonzero\tmax_J\tmax_event_id\tmean_J\t"
              "se_mean_J\tS3_J3\tS4_J4\tvov")
    tsv.write_text("# EventStats v1\n# events_total 100\n"
                   "# truncated_tracks 7 truncated_primaries 2 truncated_kinetic_energy_MeV 3.5\n"
                   f"{header}\n"
                   "-1\t100\torgan\t26\t2e-12\t4e-24\t1\t2e-12\t5\t2e-14\t2e-14\t8e-36\t1.6e-47\tinf\n"
                   "-1\t100\tcategory\tlung\t4e-12\t8e-24\t2\t2e-12\t5\t4e-14\t2.8e-14\t1e-35\t2e-47\t0.5\n")
    rows = run_organ_sweep.parse_event_stats(tsv, {"lung": 2.0}, {26: 0.5})
    organ, lung = rows
    assert organ["dosis_gy_por_primario"] == pytest.approx(2e-14/0.5)
    assert lung["dosis_gy_por_primario"] == pytest.approx(4e-14/2.0)
    assert lung["se_dosis_gy_por_primario"] == pytest.approx(2.8e-14/2.0)
    assert lung["vov"] == "0.5" and organ["vov"] == "inf"
    assert lung["truncated_tracks"] == "7" and lung["truncated_primaries"] == "2"
    assert set(lung) == set(run_organ_sweep.EVENT_STATS_FIELDNAMES) - {
        "especie", "fase", "bin_index", "n_bins", "energy_mev", "offset_x_m", "repeticion"}
