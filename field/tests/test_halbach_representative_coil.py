import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_halbach_representative_coil import generate


class RepresentativeCoilTests(unittest.TestCase):
    def test_k1_of_8_matches_halbach_orientation_formula(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            generate(ROOT/'examples/crewhat_halbach_array_pilot.json', 1, directory)
            data = json.loads((directory/'current_path.json').read_text())
            self.assertAlmostEqual(data['halbach_position_deg'], 45.0)
            self.assertAlmostEqual(data['halbach_moment_deg'], 90.0)
            np.testing.assert_allclose(data['halbach_normal'], [0.0, 1.0, 0.0], atol=1e-10)
            # Same shape as any single coil in the array: identical CAD
            # volume regardless of k (only position/orientation differ).
            self.assertAlmostEqual(data['cad_volume_m3'], 8.6983148, places=5)

    def test_rejects_out_of_range_k(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate(ROOT/'examples/crewhat_halbach_array_pilot.json', 8, Path(tmp))


if __name__ == '__main__':
    unittest.main()
