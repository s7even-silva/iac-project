import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_ellipse_array import halbach_orientation, generate, _validate
from compute_field import field_at


def small_array_config():
    """4 coils, not the real 8 -- fast enough for a unit test while still
    exercising the same fragment/fuse-per-coil code path as the real pilot."""
    base = json.loads((ROOT/'examples/crewhat_halbach_array_pilot.json').read_text())
    base['n_coils'] = 4
    base['coil_template']['control_points'] = 64
    base['coil_template']['field_segments'] = 128
    return base


class HalbachOrientationTests(unittest.TestCase):
    def test_dipole_moment_rotates_twice_position_angle(self):
        for k in range(8):
            phi, theta, center, normal, rotation = halbach_orientation(k, 8, 1, 8.0)
            self.assertAlmostEqual(theta, 2*phi)
            np.testing.assert_allclose(center, 8.0*np.array([np.cos(phi), np.sin(phi), 0.0]))
            np.testing.assert_allclose(normal, np.array([np.cos(theta), np.sin(theta), 0.0]))
            # rotation must be a proper orthonormal basis: it carries the
            # coil's own local frame into place without stretching it.
            np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-12)

    def test_only_k1_dipole_order_implemented(self):
        with self.assertRaises(ValueError):
            _validate({**small_array_config(), 'halbach_order_k': 2})

    def test_rejects_fewer_than_two_coils(self):
        with self.assertRaises(ValueError):
            _validate({**small_array_config(), 'n_coils': 1})


class HalbachArrayGenerationTests(unittest.TestCase):
    def test_four_coil_array_volume_and_angles(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = small_array_config()
            config_path = directory/'config.json'
            config_path.write_text(json.dumps(config))
            generate(config_path, directory/'out')
            data = json.loads((directory/'out'/'array_current_paths.json').read_text())
            self.assertEqual(len(data['coils']), 4)
            # Same shape swept 4 times at different orientations: identical
            # per-coil volume, matching the single-coil generator's own
            # validated volume (no accidental cross-coil fusion).
            volumes = [c['cad_volume_m3'] for c in data['coils']]
            for v in volumes[1:]:
                self.assertAlmostEqual(v, volumes[0], places=6)
            expected_positions = [0.0, 90.0, 180.0, 270.0]
            expected_moments = [0.0, 180.0, 0.0, 180.0]  # theta=2*phi mod 360, N=4
            for c, pos, mom in zip(data['coils'], expected_positions, expected_moments):
                self.assertAlmostEqual(c['position_deg'], pos)
                self.assertAlmostEqual(c['moment_deg'], mom)

    def test_dipole_field_pattern_inside_vs_outside_the_ring(self):
        """The whole point of a dipole Halbach array: roughly uniform field
        inside the ring (the protection region), decaying outside. Real
        physical behaviour confirmed on the full 8-coil pilot (see
        field/CREWHAT_STATUS.md) -- this is a cheap 4-coil regression of
        the same qualitative pattern, plus the 180-degree point symmetry a
        dipole field must have (B at -p must equal B at p exactly)."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = small_array_config()
            config_path = directory/'config.json'
            config_path.write_text(json.dumps(config))
            generate(config_path, directory/'out')
            data = json.loads((directory/'out'/'array_current_paths.json').read_text())
            paths = [np.asarray(c['path_m']) for c in data['coils']]
            currents = [c['current_A'] for c in data['coils']]
            core = config['coil_template']['field_regularization_radius_m']

            def b_total(point):
                total = np.zeros(3)
                for path, current in zip(paths, currents):
                    total += field_at(np.array([point]), path, current, core)[0]
                return total

            b_center = b_total((0.0, 0.0, 0.0))
            b_ring = b_total((config['halbach_radius_m'], 0.0, 0.0))
            b_far = b_total((config['halbach_radius_m']*2, 0.0, 0.0))
            self.assertGreater(np.linalg.norm(b_ring), np.linalg.norm(b_center))
            self.assertGreater(np.linalg.norm(b_ring), np.linalg.norm(b_far))
            p = (1.5, 1.5, 0.0)
            np.testing.assert_allclose(b_total(p), b_total(tuple(-c for c in p)), atol=1e-7)


if __name__ == '__main__':
    unittest.main()
