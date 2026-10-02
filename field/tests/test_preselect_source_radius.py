import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compute_field import field_at
from preselect_source_radius import Coils, backtrack, sample_entries


def loop_report(directory, radius=1.0, current=1e6, core=0.01):
    t = np.linspace(0, 2*np.pi, 65)
    path = np.column_stack((radius*np.cos(t), radius*np.sin(t), np.zeros_like(t)))
    path[-1] = path[0]
    report = {'config': {'coil_template': {'field_regularization_radius_m': core,
                                           'winding_pack_side_m': 0.0}},
              'bounds_m': [-radius, -radius, 0, radius, radius, 0],
              'coils': [{'path_m': path.tolist(), 'current_A': current}]}
    target = Path(directory)/'array_current_paths.json'
    target.write_text(json.dumps(report))
    return target, path


class PreselectTests(unittest.TestCase):
    def test_vectorized_field_matches_field_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            report, path = loop_report(tmp)
            coils = Coils(report)
            points = np.random.default_rng(3).uniform(-3, 3, size=(50, 3))
            np.testing.assert_allclose(coils.field(points), field_at(points, path, 1e6, 0.01),
                                       rtol=1e-12, atol=1e-18)

    def test_entries_follow_cosine_law(self):
        P, d = sample_entries(5.0, 200000, np.random.default_rng(4))
        np.testing.assert_allclose(np.linalg.norm(P, axis=1), 5.0)
        cos = -np.einsum('ij,ij->i', d, P/5.0)
        self.assertTrue(np.all(cos >= 0))
        # Ley coseno: p(c) = 2c, media 2/3 y media de c² igual a 1/2.
        self.assertAlmostEqual(cos.mean(), 2/3, delta=0.003)
        self.assertAlmostEqual((cos**2).mean(), 1/2, delta=0.003)

    def test_weak_field_lets_every_direction_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            report, _ = loop_report(tmp, current=1.0)
            status, _ = backtrack(Coils(report), 3.0, 1.0, 200, 30.0, seed=5)
            self.assertTrue(np.all(status == 1))

    def test_strong_field_produces_reentries(self):
        with tempfile.TemporaryDirectory() as tmp:
            report, _ = loop_report(tmp, current=5e7)
            status, _ = backtrack(Coils(report), 1.5, 0.2, 300, 30.0, seed=6)
            self.assertGreater(np.mean(status != 1), 0.05)


if __name__ == '__main__':
    unittest.main()
