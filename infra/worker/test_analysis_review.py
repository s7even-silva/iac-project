"""Regression tests for silent mixing of physical scenarios and MC uncertainty."""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "geant4/ActiveShield_Sim/scripts"
sys.path.insert(0, str(SCRIPTS))
import aggregate_organ_doses as aggregate
import energy_bins
import run_organ_sweep as sweep


def row(**changes):
    result = dict(especie="GCR_H", fase="min", bin_index="0", n_bins="1",
                  offset_x_m="0", repeticion="0", organo_id="1",
                  edep_J="2", dose_gy_run="4", n_eventos="10")
    return result | changes


BINS = {(s, p): [(0, 100, 1)] for s, p in energy_bins.SPECIES_RANGE}


@pytest.mark.parametrize("changes", [dict(n_eventos="-1"), dict(edep_J="nan"),
    dict(dose_gy_run="inf"), dict(bin_index="1"), dict(energy_mev="20")])
def test_reject_corrupt_result(changes):
    with pytest.raises(ValueError):
        aggregate.validate_result_rows([row(**changes)], BINS)


def test_reject_phases_of_same_model_but_allow_historic_gcr_sep():
    aggregate.validate_result_rows([row(), row(especie="SEP_p", fase="max")], BINS)
    with pytest.raises(ValueError, match="Fases incompatibles"):
        aggregate.validate_result_rows([row(), row(especie="GCR_He", fase="max")], BINS)


def test_reject_inconsistent_event_count_within_run():
    with pytest.raises(ValueError, match="inconsistente"):
        aggregate.validate_result_rows([row(), row(organo_id="2", n_eventos="20")], BINS)


def test_incomplete_uncertainty_is_per_model():
    assert not aggregate.uncertainty_available("GCR", [("GCR_H", "min", 0)], [])
    assert not aggregate.uncertainty_available("GCR", [], [("GCR_H", "min", 0)])
    assert aggregate.uncertainty_available("SEP", [("GCR_H", "min", 0)], [])


def test_resume_rejects_changed_source_or_statistics(tmp_path):
    (tmp_path / "organ_sweep_manifest.csv").write_text(
        "n_bins,angular_distribution,n_events\n8,radial,100\n")
    sweep.validate_resume_grid(tmp_path, 8, "radial", 100)
    with pytest.raises(ValueError, match="angular"):
        sweep.validate_resume_grid(tmp_path, 8, "cosine", 100)
    with pytest.raises(ValueError, match="eventos"):
        sweep.validate_resume_grid(tmp_path, 8, "radial", 1000)


@pytest.mark.parametrize("data", ["1,1\n1,2\n", "2,1\n1,2\n", "1,nan\n2,1\n", "1,-1\n2,1\n"])
def test_invalid_spectra(tmp_path, data):
    path = tmp_path / "spectrum.csv"
    path.write_text(data)
    with pytest.raises(ValueError):
        energy_bins.load_spectrum(path)


def test_integrated_bin_weights_conserve_flux():
    for n in (1, 8, 16, 32):
        edges = energy_bins.log_bin_edges(1., 10., n)
        total = sum(energy_bins.integral_between([1., 10.], [2., 4.], a, b)
                    for a, b in zip(edges, edges[1:]))
        assert total == pytest.approx(27.)


@pytest.mark.parametrize("n_bins,reps", [(1, 1), (2, 2)])
def test_csv_suppresses_incomplete_confidence_interval(tmp_path, monkeypatch, n_bins, reps):
    source = tmp_path / "input.csv"
    rows = [row(n_bins=str(n_bins), repeticion=str(r), edep_J=str(2 + r)) for r in range(reps)]
    with source.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(aggregate, "load_organ_metadata", lambda _: {1: ("lung", 1)})
    monkeypatch.setattr(aggregate, "load_organ_masses_kg", lambda _: {1: 1.0})
    monkeypatch.setattr(aggregate, "load_rbm_fraction_by_tissue", lambda _: {})
    monkeypatch.setattr(sys, "argv", ["aggregate", "--results", str(source), "--out", str(tmp_path / "out.csv")])
    aggregate.main()
    with (tmp_path / "resultados_riesgo_estocastico_por_bin.csv").open() as f:
        result = next(csv.DictReader(f))
    assert float(result["D_equivalente_GCR_Sv_dia"]) > 0
    assert result["SE_D_equivalente_GCR_Sv_dia"] == ""
    assert result["ic95_low_GCR"] == result["ic95_high_GCR"] == ""
    assert result["bins_R1_sin_varianza"] if reps == 1 else result["bins_ausentes"]


def test_aggregate_cli_normalizes_by_total_events_and_rejects_duplicates(tmp_path):
    source = tmp_path / "input.csv"
    rows = [row(), row(repeticion="1", edep_J="6", dose_gy_run="12", n_eventos="30")]
    with source.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    output = tmp_path / "out.csv"
    command = [sys.executable, str(SCRIPTS / "aggregate_organ_doses.py"),
               "--results", str(source), "--out", str(output),
               "--icrp-data-dir", str(tmp_path / "absent"), "--source-sphere-radius-m", "1"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    bins = energy_bins.build_bins(SCRIPTS.parent / "data/sources/oltaris", 1)
    import math
    expected = (16 / 40) * math.pi * 100**2 * bins[("GCR_H", "min")][0][2]
    with output.open() as f:
        actual = next(csv.DictReader(f))
    assert float(actual["D_absorbida_GCR_Gy_dia"]) == pytest.approx(expected)
    result = subprocess.run(command + ["--results", str(source), str(source)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "duplicada" in result.stderr
