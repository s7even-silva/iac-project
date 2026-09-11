import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_ellipse import controls, generate
from compute_field import field_at


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

    def test_field_at_center_matches_equivalent_loop_estimate(self):
        """Regression check for the Biot-Savart field on this new topology
        (compute_field.py itself is unchanged -- this only validates the
        ellipse's current_path.json feeds it sensibly). B at the coil's own
        center should be within the right order of magnitude of a circular
        loop of the same geometric-mean radius sqrt(a*b), and purely axial
        (Z) -- both real, checkable properties of a planar current loop,
        not something that requires solving Elmer or knowing the real
        production geometry."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            generate(ROOT/'examples/crewhat_ellipse_tape12mm_pilot.json', directory)
            data = json.loads((directory/'current_path.json').read_text())
            path = np.asarray(data['path_m'])
            center = field_at(np.array([[0., 0., 0.]]), path, data['current_A'], data['conductor_radius_m'])[0]
            a, b = 4.0, 2.0
            analytic = 4*np.pi*1e-7*data['current_A']/(2*np.sqrt(a*b))
            self.assertAlmostEqual(center[0], 0.0)
            self.assertAlmostEqual(center[1], 0.0)
            self.assertLess(abs(center[2]/analytic-1), .15)

    def test_field_purely_axial_within_the_loops_own_plane(self):
        """Any point in the SAME plane as a planar current loop (on- or
        off-axis) has a field purely perpendicular to that plane -- every
        Biot-Savart contribution dl x r_hat is normal to the plane there,
        since both dl and r_hat lie in it. A design mistake this test would
        have caught early: aiming a Geant4 charged-particle probe along
        that normal direction, IN the loop's plane, gives zero deflection
        (v parallel to B), not because the pipeline is broken."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            generate(ROOT/'examples/crewhat_ellipse_tape12mm_pilot.json', directory)
            data = json.loads((directory/'current_path.json').read_text())
            path = np.asarray(data['path_m'])
            for point in [[1., 0., 0.], [0., 3., 0.], [9., 0., 0.]]:
                b = field_at(np.array([point]), path, data['current_A'], data['conductor_radius_m'])[0]
                self.assertAlmostEqual(b[0], 0.0)
                self.assertAlmostEqual(b[1], 0.0)


if __name__ == '__main__':
    unittest.main()
