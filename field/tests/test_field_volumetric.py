"""Volumetric Biot-Savart (compute_field_volumetric.py) against closed forms."""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compute_field_volumetric import Segments, field, filaments, generate, merge, read_map, write_binary

MU0 = 4e-7*np.pi


def circle_report(radius, radial, axial, current, segments=1024):
    t = np.linspace(0, 2*np.pi, segments+1)
    path = np.column_stack((radius*np.cos(t), radius*np.sin(t), np.zeros_like(t)))
    path[-1] = path[0]
    return {'config': {'coil_template': {'winding_pack_radial_m': radial, 'winding_pack_axial_m': axial}},
            'coils': [{'path_m': path.tolist(), 'current_A': current}],
            'bounds_m': [-radius-radial/2, -radius-radial/2, -axial/2, radius+radial/2, radius+radial/2, axial/2]}


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

    def test_compiled_kernel_matches_numpy(self):
        import compute_field_volumetric as cfv
        if cfv.compiled_kernel() is None:
            self.skipTest('no gcc: the NumPy kernel is the only one')
        seg = Segments(circle_report(4.0, 0.67, 0.32, 1e7, segments=256), 6, 3)
        points = np.random.default_rng(5).uniform(-8, 8, size=(500, 3))
        compiled = field(points, seg)
        cfv._KERNEL[:] = [None]  # force NumPy for this comparison
        try:
            numpy_version = field(points, seg)
        finally:
            cfv._KERNEL[:] = []
        np.testing.assert_allclose(compiled, numpy_version, rtol=1e-11, atol=1e-15)

    def test_parts_merge_into_the_same_map(self):
        """Splitting the z planes across PCs and merging gives the identical file."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            report = tmp/'report.json'
            report.write_text(json.dumps(circle_report(1.0, 0.2, 0.1, 1e4, segments=64)))
            args = dict(half_size=[1.5], spacing=0.5, n_radial=2, n_axial=1, processes=1,
                        max_points=10**6, check_points=0)
            generate(report, tmp/'whole.map', **args)
            for k in (1, 2, 3):
                generate(report, tmp/f'part{k}.npz', **args, part=(k, 3))
            merge(report, tmp/'merged.map', [tmp/'part3.npz', tmp/'part1.npz', tmp/'part2.npz'], 0)
            self.assertEqual((tmp/'whole.map').read_bytes(), (tmp/'merged.map').read_bytes())
            with self.assertRaises(ValueError):
                merge(report, tmp/'gap.map', [tmp/'part1.npz', tmp/'part3.npz'], 0)
            # A stopped run's planes are reused only for the same map.
            stale = tmp/'whole2.map.planos'
            stale.mkdir()
            (stale/'key.json').write_text(json.dumps({'other': 'map'}))
            with self.assertRaises(ValueError):
                generate(report, tmp/'whole2.map', **args)

    def test_binary_map_layout_and_text_equivalence(self):
        """The .bmap layout that TabulatedMagneticField.cc reads (tests/test_field_map.cc writes the
        same one), and the same field as the text map: generated directly or converted."""
        values = np.arange(4*3*2*3, dtype=float).reshape(4, 3, 2, 3)  # nz, ny, nx, 3
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with open(tmp/'small.bmap', 'wb') as f:
                write_binary(f, values, [-1., -2., -3.], [0.5, 1., 2.])
            expected = (b'IACBMAP1'+struct.pack('<3Q6d', 2, 3, 4, -1, -2, -3, 0.5, 1, 2)
                        + struct.pack(f'<{values.size}f', *values.ravel()))
            self.assertEqual((tmp/'small.bmap').read_bytes(), expected)

            report = tmp/'report.json'
            report.write_text(json.dumps(circle_report(1.0, 0.2, 0.1, 1e4, segments=64)))
            args = dict(half_size=[1.5], spacing=0.5, n_radial=2, n_axial=1, processes=1,
                        max_points=10**6, check_points=0)
            generate(report, tmp/'m.map', **args)
            generate(report, tmp/'m.bmap', **args)
            subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'map_to_binary.py'),
                            str(tmp/'m.map'), str(tmp/'c.bmap')], check=True, capture_output=True)
            text, origin, steps = read_map(tmp/'m.map')
            for name in ('m.bmap', 'c.bmap'):
                binary, origin2, steps2 = read_map(tmp/name)
                np.testing.assert_array_equal(origin2, origin)
                np.testing.assert_array_equal(steps2, steps)
                np.testing.assert_allclose(binary, text, rtol=2e-7, atol=1e-12)
            self.assertTrue((tmp/'m.bmap-manifest.json').is_file() and (tmp/'m.field-manifest.json').is_file())
            converted = json.loads((tmp/'c.bmap-manifest.json').read_text())
            self.assertEqual(converted['format'], 'IACBMAP1 float32')
            self.assertLess(converted['max_relative_difference_vs_source'], 1e-6)


if __name__ == '__main__':
    unittest.main()
