import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_ellipse_array import generate
from phase_sensitivity import build_ring, summarize


def small_array_config():
    """Same 4-coil trick as the other ellipse-array tests: fast, same path."""
    base = json.loads((ROOT/'examples/crewhat_halbach_array_pilot.json').read_text())
    base['n_coils'] = 4
    base['coil_template']['control_points'] = 64
    base['coil_template']['field_segments'] = 128
    return base


class RingTests(unittest.TestCase):
    def test_ring_has_the_requested_number_of_equally_spaced_points(self):
        grid, angles_deg = build_ring(radius_m=2.0, n_angular=8, z_m=0.0)
        self.assertEqual(len(grid), 8)
        radii = np.linalg.norm(grid[:, :2], axis=1)
        np.testing.assert_allclose(radii, 2.0)
        np.testing.assert_allclose(grid[:, 2], 0.0)
        np.testing.assert_allclose(angles_deg, np.linspace(0.0, 360.0, 8, endpoint=False))

    def test_rejects_nonpositive_radius(self):
        with self.assertRaises(ValueError):
            summarize(Path('unused.json'), Path('unused.json'), radius_m=0.0, n_angular=8, z_m=0.0)

    def test_rejects_too_few_angular_samples(self):
        with self.assertRaises(ValueError):
            summarize(Path('unused.json'), Path('unused.json'), radius_m=2.0, n_angular=2, z_m=0.0)


class SummaryTests(unittest.TestCase):
    def test_reports_a_self_consistent_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config_path = directory/'config.json'
            config_path.write_text(json.dumps(small_array_config()))
            generate(config_path, directory/'array')
            output = directory/'phase.json'
            summarize(directory/'array'/'array_current_paths.json', output,
                      radius_m=2.0, n_angular=8, z_m=0.0)
            report = json.loads(output.read_text())
            self.assertFalse(report['production_validated'])
            self.assertEqual(report['n_angular'], len(report['angle_deg']))
            self.assertEqual(report['n_angular'], len(report['magnitude_T']))
            self.assertGreater(report['mean_T'], 0.0)
            self.assertAlmostEqual(report['coefficient_of_variation'], report['std_T']/report['mean_T'])
            self.assertAlmostEqual(report['worst_to_best_ratio'], report['max_T']/report['min_T'])


if __name__ == '__main__':
    unittest.main()
