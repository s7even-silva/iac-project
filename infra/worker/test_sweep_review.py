import importlib.util
from pathlib import Path
import pytest

path = Path(__file__).resolve().parents[2] / 'geant4/ActiveShield_Sim/scripts/run_organ_sweep.py'
import sys
sys.path.insert(0, str(path.parent))
spec = importlib.util.spec_from_file_location('sweep_review', path)
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)


def test_resume_rejects_old_schema_and_changed_grid(tmp_path):
    manifest = tmp_path / 'organ_sweep_manifest.csv'
    manifest.write_text('index,repeticion\n0,0\n')
    with pytest.raises(ValueError, match='esquema antiguo'):
        sweep.validate_resume_grid(tmp_path, 8)
    manifest.write_text('n_bins\n8\n')
    with pytest.raises(ValueError, match='otra grilla'):
        sweep.validate_resume_grid(tmp_path, 16)
    sweep.validate_resume_grid(tmp_path, 8)


@pytest.mark.parametrize('suffix,expected', [('', False), (' 1e-3 1e-6 2 0.1', True)])
def test_parser_old_and_intrarun_output(tmp_path, suffix, expected):
    path = tmp_path / 'ICRP110.out'
    path.write_text('ORGAN ENERGY DEPOSITIONS AND ABSORBED DOSE\nOrganID | values\n1 | 0.001 0.002' + suffix + '\nTotal energy\n')
    result = sweep.parse_icrp110_out(path)
    assert result[1]['edep_J'] == .001
    assert ('s1_j' in result[1]) == expected
