import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_ellipse_array import generate
from uniformity_metric import build_grid, summarize


def small_array_config():
    """Same 4-coil trick as test_ellipse_array.py: fast, same code path."""
    base = json.loads((ROOT/'examples/crewhat_halbach_array_pilot.json').read_text())
    base['n_coils'] = 4
    base['coil_template']['control_points'] = 64
    base['coil_template']['field_segments'] = 128
    return base


class GridTests(unittest.TestCase):
    def test_point_count_matches_parameters(self):
        grid = build_grid(ship_radius_m=4.5, n_radial=3, n_angular=4, z_values_m=[0.0, 2.0])
        # One centre point per Z plane, plus n_radial*n_angular ring points per Z plane.
        self.assertEqual(len(grid), 2*(1+3*4))

    def test_points_stay_within_the_requested_disk(self):
        grid = build_grid(ship_radius_m=4.5, n_radial=4, n_angular=6, z_values_m=[0.0])
        radial = np.linalg.norm(grid[:, :2], axis=1)
        self.assertTrue(np.all(radial <= 4.5+1e-9))

    def test_rejects_nonpositive_ship_radius(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config_path = directory/'config.json'
            config_path.write_text(json.dumps(small_array_config()))
            generate(config_path, directory/'array')
            with self.assertRaises(ValueError):
                summarize(directory/'array'/'array_current_paths.json', directory/'out.json',
                          ship_radius_m=0.0, n_radial=2, n_angular=4, z_values_m=[0.0])


class SummaryTests(unittest.TestCase):
    def test_reports_a_self_consistent_uniformity_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config_path = directory/'config.json'
            config_path.write_text(json.dumps(small_array_config()))
            generate(config_path, directory/'array')
            output = directory/'uniformity.json'
            summarize(directory/'array'/'array_current_paths.json', output,
                      ship_radius_m=2.0, n_radial=3, n_angular=4, z_values_m=[0.0])
            report = json.loads(output.read_text())
            self.assertFalse(report['production_validated'])
            self.assertEqual(report['n_points'], len(report['points_m']))
            self.assertEqual(report['n_points'], len(report['magnitude_T']))
            self.assertGreater(report['mean_T'], 0.0)
            self.assertGreaterEqual(report['std_T'], 0.0)
            self.assertAlmostEqual(report['coefficient_of_variation'], report['std_T']/report['mean_T'])
            self.assertLessEqual(report['min_T'], report['mean_T'])
            self.assertGreaterEqual(report['max_T'], report['mean_T'])


if __name__ == '__main__':
    unittest.main()
