"""Volumetric Biot-Savart (compute_field_volumetric.py) against closed forms."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compute_field_volumetric import Segments, field, filaments

MU0 = 4e-7*np.pi


def circle_report(radius, radial, axial, current, segments=1024):
    t = np.linspace(0, 2*np.pi, segments+1)
    path = np.column_stack((radius*np.cos(t), radius*np.sin(t), np.zeros_like(t)))
    path[-1] = path[0]
    return {'config': {'coil_template': {'winding_pack_radial_m': radial, 'winding_pack_axial_m': axial}},
            'coils': [{'path_m': path.tolist(), 'current_A': current}]}


def thick_coil_on_axis(z, a1, a2, z1, z2, current):
    """Closed form of a uniform rectangular-section circular coil on its axis."""
    j = current/((a2-a1)*(z2-z1))
    def term(zeta):
        return zeta*np.log((a2+np.hypot(a2, zeta))/(a1+np.hypot(a1, zeta)))
    return MU0*j/2*(term(z2-z)-term(z1-z))


class VolumetricTests(unittest.TestCase):
    def test_thick_coil_on_axis_matches_closed_form(self):
        """Also catches swapped radial/axial sides (~0.5% here) and the single
        filament (~0.15%): the tolerance is 3e-4."""
        R, w, t, current = 4.0, 0.67, 0.32, 1e7
        seg = Segments(circle_report(R, w, t, current), 8, 4)
        for z in (0.0, 1.0, 3.0):
            b = field(np.array([[0., 0., z]]), seg)[0]
            exact = thick_coil_on_axis(z, R-w/2, R+w/2, -t/2, t/2, current)
            self.assertAlmostEqual(b[0], 0., places=9)
            self.assertAlmostEqual(b[1], 0., places=9)
            self.assertLess(abs(b[2]/exact-1), 3e-4)

    def test_filaments_fill_the_pack_rectangle(self):
        lines = filaments(circle_report(4.0, 0.6, 0.3, 1.)['coils'][0]['path_m'], 0.6, 0.3, 3, 2)
        r = [np.linalg.norm(line[:, :2], axis=1).mean() for line in lines]
        z = [line[:, 2].mean() for line in lines]
        np.testing.assert_allclose(sorted(set(np.round(r, 6))), [3.8, 4.0, 4.2], atol=1e-3)
        np.testing.assert_allclose(sorted(set(np.round(z, 6))), [-0.075, 0.075], atol=1e-12)

    def test_core_is_exact_outside_and_finite_inside(self):
        seg = Segments(circle_report(1.0, 0.1, 0.1, 1.), 1, 1)  # only to get the class
        seg.start = np.array([[0., 0., -1e3]])
        seg.dir = np.array([[0., 0., 1.]])
        seg.length = np.array([2e3])
        seg.current = np.array([1.])
        seg.core = 0.1
        outside, inside, axis = field(np.array([[0.5, 0., 0.], [0.05, 0., 0.], [0., 0., 0.]]), seg)
        self.assertAlmostEqual(outside[1]/(MU0/(2*np.pi*0.5)), 1., places=6)
        self.assertAlmostEqual(inside[1]/(MU0*0.05/(2*np.pi*0.1**2)), 1., places=6)
        np.testing.assert_array_equal(axis, 0.)


if __name__ == '__main__':
    unittest.main()
