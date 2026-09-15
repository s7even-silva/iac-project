import json
import os
import time
import diagnostics


def test_samples_and_persistent_capture(tmp_path):
    sampler = diagnostics.Sampler(os.getpid())
    sampler.sample()
    end = time.monotonic() + .05
    while time.monotonic() < end:
        pass
    current = sampler.sample()
    assert any(t['cpu_pct_one_core'] is not None and t['cpu_pct_one_core'] > 0 for t in current['threads'])
    work = tmp_path / 'work'
    (work / 'events').mkdir(parents=True)
    (work / 'events/thread-0.jsonl').write_text('{"event":1,"phase":"begin"}\n')
    (work / 'organ_run_001.mac').write_text('/random/setSeeds 123 124')
    target = sampler.capture(tmp_path/'persistent', work, {'job_id':1,'attempt':2}, ['run'], 'sha256:test')
    result = json.loads(target.read_text())
    assert result['job']['attempt'] == 2
    assert result['pending_events'] == [{'event': 1, 'phase': 'begin'}]
    assert 'events/thread-0.jsonl' in result['artifacts']
    for _ in range(5):
        sampler.capture(tmp_path/'persistent', work, {'job_id':1,'attempt':2}, [], None)
    assert len(list((tmp_path/'persistent').glob('*.json'))) == 3


def test_missing_proc_data_is_explicit(tmp_path):
    assert 'unavailable' in diagnostics.read(tmp_path/'absent')
