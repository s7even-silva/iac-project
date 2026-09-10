import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_ellipse import controls, generate


class EllipseTests(unittest.TestCase):
    def test_crewhat_ellipse_cad_volume_matches_swept_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            generate(ROOT/'examples/crewhat_ellipse_tape12mm_pilot.json', directory)
            data = json.loads((directory/'current_path.json').read_text())
            path = np.asarray(data['path_m'])
            np.testing.assert_array_equal(path[0], path[-1])
            # Numerically integrated ellipse perimeter (no closed form) times
            # the square cross-section area -- a straight solid-of-revolution
            # estimate, ignoring the small correction from sweeping a curve
            # of varying curvature (same style of check as test_field.py's
            # DH volume test).
            a, b = 4.0, 2.0
            t = np.linspace(0, 2*np.pi, 100000, endpoint=False)
            dt = 2*np.pi/len(t)
            speed = np.sqrt((a*np.sin(t))**2 + (b*np.cos(t))**2)
            perimeter = np.sum(speed)*dt
            expected = perimeter*data['winding_pack_side_m']**2
            self.assertLess(abs(data['cad_volume_m3']/expected-1), .01)
            self.assertEqual(data['status'], 'computational_pilot_not_crewhat')
            # Bounds must extend exactly semi-axis + half the winding pack.
            half = data['winding_pack_side_m']/2
            self.assertAlmostEqual(data['bounds_m'][3], a+half, places=2)
            self.assertAlmostEqual(data['bounds_m'][4], b+half, places=2)
            self.assertAlmostEqual(data['bounds_m'][5], half, places=2)

    def test_oversized_winding_pack_rejected_for_curvature(self):
        """A winding pack whose half-width approaches the ellipse's minimum
        radius of curvature (b^2/a, at the major-axis ends) would self-
        intersect when swept -- controls() must reject it before Gmsh/OCC
        ever gets a chance to hang or produce a degenerate solid."""
        config = json.loads((ROOT/'examples/crewhat_ellipse_tape12mm_pilot.json').read_text())
        config['winding_pack_side_m'] = 1.9  # rho_min=1m here; half-width 0.95 >= 1/1.2
        with self.assertRaises(ValueError):
            controls(config)

    def test_corc_variant_generates_with_smaller_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            generate(ROOT/'examples/crewhat_ellipse_corc_pilot.json', directory)
            data = json.loads((directory/'current_path.json').read_text())
            self.assertLess(data['cad_volume_m3'], 10)


if __name__ == '__main__':
    unittest.main()
