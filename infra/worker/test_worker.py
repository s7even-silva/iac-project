import importlib.util
import csv
import io
from pathlib import Path

spec = importlib.util.spec_from_file_location('worker_under_test', Path(__file__).with_name('worker.py'))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_exact_repetition():
    job = dict(species='GCR_He', bin_index=7, offset_x_m=3., repeticion=2, n_events=100)
    cmd = worker.build_command(job)
    assert cmd[cmd.index('--repetition-start')+1] == '2'
    assert cmd[cmd.index('--repeats')+1] == '1'
    assert cmd[cmd.index('--only-bins')+1] == '7'
    assert '--no-resume' in cmd


def test_header_only_is_not_result(tmp_path):
    (tmp_path/'resultados_organo_sweep.csv').write_text(','.join(worker.RESULTS_FIELDNAMES)+'\n')
    job = dict(species='SEP_p', bin_index=1, offset_x_m=1., repeticion=0)
    assert worker.filter_results_csv(job, tmp_path) == ''


def test_filter_excludes_other_repetitions(tmp_path):
    job = dict(species='SEP_p', bin_index=1, offset_x_m=1., repeticion=2)
    with (tmp_path/'resultados_organo_sweep.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=worker.RESULTS_FIELDNAMES)
        w.writeheader()
        for rep in [0, 2]:
            w.writerow(dict(especie='SEP_p',bin_index=1,offset_x_m=1.,repeticion=rep))
    assert len(list(csv.DictReader(io.StringIO(worker.filter_results_csv(job, tmp_path))))) == 1
