import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compute_field import field_at, grid_shape, generate
from generate_dh import controls, generate as generate_dh
from prepare_domain_sweep import prepare
from audit_dh import audit


class FieldTests(unittest.TestCase):
    def test_dh_cad_and_closed_current_share_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            generate_dh(ROOT/'examples/dh_pilot.json', directory)
            data = json.loads((directory/'current_path.json').read_text())
            path = np.asarray(data['path_m'])
            np.testing.assert_array_equal(path[0], path[-1])
            expected = np.linalg.norm(np.diff(path, axis=0), axis=1).sum()*np.pi*data['conductor_radius_m']**2
            self.assertLess(abs(data['cad_volume_m3']/expected-1), .02)
            self.assertGreater(data['bounds_m'][0], 2.8)
            self.assertEqual(data['status'], 'computational_pilot_not_geom14')
            report = audit(directory/'current_path.json')
            self.assertEqual(report['ampere_turns_per_helix_magnitude'], 300)
            self.assertIsNone(report['I_over_Ic'])
            self.assertIsNone(report['peak_conductor_B_T'])
            self.assertFalse(report['production_validated'])
            self.assertAlmostEqual(audit(directory/'current_path.json', critical_current=200)['current_margin_fraction'], .5)
            with self.assertRaises(ValueError):
                audit(directory/'current_path.json', critical_current=-1)

    def test_mesh_patch_count_scales_with_turns(self):
        """Regression test for a real hang found 2026-09-08: generate_dh.py
        used to cut the swept curve into a FIXED 8 patches regardless of
        `turns`, so each patch's angular span grew with turns. Once a patch
        spanned close to or more than one full helix turn (confirmed at 7+
        turns with dh_pilot.json's geometry), the swept conductor disk
        self-intersected within that single patch, and OpenCASCADE's
        fragment/fuse in generate() hung indefinitely instead of raising --
        6 turns meshed in seconds, 7 turns never completed in 90s+. The fix
        scales patch count with `turns` (see generate() and _coil_solid()).
        This test uses 8 turns (above the confirmed break point) with a
        real subprocess timeout so a regression fails loudly here instead
        of hanging the whole test suite."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = json.loads((ROOT/'examples/dh_pilot.json').read_text())
            config['center_m'] = [0.0, 0.0, 0.0]
            config['turns'] = 8
            config['field_segments'] = 1024
            config_path = directory/'config.json'
            config_path.write_text(json.dumps(config))
            generate_dh(config_path, directory/'out')
            subprocess.run(
                [sys.executable, str(ROOT/'generate_mesh.py'),
                 str(directory/'out'/'dh.geo'), str(directory/'out'/'dh.msh'),
                 '--dependency', str(directory/'out'/'dh.brep'),
                 '--dependency', str(config_path)],
                cwd=ROOT, timeout=60, check=True, capture_output=True)
            self.assertTrue((directory/'out'/'dh.msh').is_file())

    def test_loop_axis_and_current_reversal(self):
        t = np.linspace(0, 2*np.pi, 2049)
        path = np.column_stack((np.cos(t), np.sin(t), np.zeros_like(t)))
        path[-1] = path[0]
        points = np.array([[0., 0., z] for z in (0, .5, 2, 10)])
        result = field_at(points, path, 123., 0)
        expected = 2*np.pi*1e-7*123/(1+points[:, 2]**2)**1.5
        np.testing.assert_allclose(result[:, 2], expected, rtol=3e-6)
        np.testing.assert_allclose(result[:, :2], 0, atol=1e-18)
        np.testing.assert_allclose(field_at(points, path[::-1], 123., 0), -result, atol=1e-18)
        np.testing.assert_array_equal(field_at(points, path, 0., .01), 0)

    def test_invalid_path_and_dimensions(self):
        with self.assertRaises(ValueError):
            field_at([[0., 0., 1.]], [[0, 0, 0], [1, 0, 0]], 1, .1)
        with self.assertRaises(ValueError):
            grid_shape(10, 0)
        c = json.loads((ROOT/'examples/dh_pilot.json').read_text())
        self.assertTrue(np.isfinite(controls(c)).all())
        c['radii_m'] = [.35, .351]
        with self.assertRaises(ValueError):
            controls(c)

    def test_plan_and_map_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            source = d/'path.json'
            data = {'bounds_m': [-1, -1, -.1, 1, 1, .1], 'current_A': 100,
                    'conductor_radius_m': .01,
                    'path_m': [[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0], [1, 0, 0]]}
            source.write_text(json.dumps(data))
            prepare(source, d/'plan', 1, 10)
            plan = json.loads((d/'plan/domain_plan.json').read_text())
            self.assertEqual([c['map_half_side_m'] for c in plan['cases']], [20, 40, 80])
            self.assertEqual(plan['fixed_world_half_size_m'], 81)
            with self.assertRaises(ValueError):
                prepare(source, d/'bad', 1, 1)
            with self.assertRaises(ValueError):
                generate(source, d/'large.map', 80, .1, 1000000)
            generate(source, d/'small.map', 6, 6, 100)
            rows = np.loadtxt(d/'small.map')
            np.testing.assert_array_equal(rows[0], [3, 3, 3])
            points = np.array([[x, y, z] for z in (-6, 0, 6) for y in (-6, 0, 6) for x in (-6, 0, 6)])
            np.testing.assert_allclose(rows[3:], field_at(points, data['path_m'], 100, .01), atol=1e-18)


if __name__ == '__main__':
    unittest.main()
