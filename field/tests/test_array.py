import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_array import generate as generate_array
from compute_field_array import generate as generate_field_array
from compute_field import field_at
from audit_array import audit as audit_array


def two_coil_config(directory_hint=''):
    """Small, fast two-coil array: reuses dh_pilot.json's geometry twice at
    different centres, well-separated so no fusion/overlap work is needed
    beyond what generate_dh.py already validates for a single coil."""
    base = json.loads((ROOT / 'examples/dh_pilot.json').read_text())
    base['turns'] = 2
    base['field_segments'] = 256
    coil_a = dict(base, center_m=[0.0, 0.0, -2.0])
    coil_b = dict(base, center_m=[0.0, 0.0, 2.0])
    return {
        'schema_version': 1,
        'status': 'computational_pilot_array_not_geom14',
        'coils': [
            {'name': 'coil_a', 'role': 'barrel', 'material': 'pilot_copper', 'config': coil_a},
            {'name': 'coil_b', 'role': 'endcap', 'material': 'pilot_copper', 'config': coil_b},
        ],
        'materials_library': {
            'elements': {'Cu': {'Z': 29, 'A': 63.546}},
            'materials': {'pilot_copper': {'density_g_cm3': 8.96, 'mass_fractions': {'Cu': 1.0}}},
        },
    }


class ArrayTests(unittest.TestCase):
    def test_array_generates_one_solid_and_group_per_coil(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            config_path = d / 'array.json'
            config_path.write_text(json.dumps(two_coil_config()))
            generate_array(config_path, d / 'out')

            geo = (d / 'out' / 'array.geo').read_text()
            self.assertIn('Physical Volume("coil_a") = {1};', geo)
            self.assertIn('Physical Volume("coil_b") = {2};', geo)

            materials = json.loads((d / 'out' / 'materials.json').read_text())
            self.assertEqual(materials['groups'], {'coil_a': 'pilot_copper', 'coil_b': 'pilot_copper'})
            self.assertIn('pilot_copper', materials['materials'])

            report = json.loads((d / 'out' / 'array_current_paths.json').read_text())
            names = [c['name'] for c in report['coils']]
            self.assertEqual(names, ['coil_a', 'coil_b'])
            for coil in report['coils']:
                path = np.asarray(coil['path_m'])
                np.testing.assert_array_equal(path[0], path[-1])
                self.assertGreater(coil['cad_volume_m3'], 0)
            # Two well-separated identical coils: total volume is exactly twice one.
            self.assertAlmostEqual(
                report['coils'][0]['cad_volume_m3'], report['coils'][1]['cad_volume_m3'], places=9)

    def test_rejects_duplicate_names_unknown_role_and_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            cfg = two_coil_config()
            cfg['coils'][1]['name'] = 'coil_a'
            path = d / 'dup.json'
            path.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                generate_array(path, d / 'out')

            cfg = two_coil_config()
            cfg['coils'][0]['role'] = 'sidecap'
            path = d / 'badrole.json'
            path.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                generate_array(path, d / 'out2')

            cfg = two_coil_config()
            cfg['coils'][0]['material'] = 'unobtainium'
            path = d / 'badmat.json'
            path.write_text(json.dumps(cfg))
            with self.assertRaises(ValueError):
                generate_array(path, d / 'out3')

    def test_field_array_is_the_superposition_of_each_coil(self):
        """Two identical circular loops (not the DH pilot -- exact analytic
        check, same idea as test_field.py's single-loop test): field at the
        common axis midpoint must equal the sum of each loop's independent
        contribution, confirming compute_field_array.py adds contributions
        rather than e.g. averaging or using only the last coil."""
        t = np.linspace(0, 2 * np.pi, 513)
        loop_a = np.column_stack((np.cos(t), np.sin(t), np.full_like(t, -0.5)))
        loop_a[-1] = loop_a[0]
        loop_b = np.column_stack((np.cos(t), np.sin(t), np.full_like(t, 0.5)))
        loop_b[-1] = loop_b[0]
        current, core = 100.0, 0.001
        point = np.array([[0.0, 0.0, 0.0]])
        individual = field_at(point, loop_a, current, core) + field_at(point, loop_b, current, core)

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            report = {
                'bounds_m': [-1, -1, -1, 1, 1, 1],
                'config': {'coils': [
                    {'name': 'a', 'config': {'conductor_radius_m': core}},
                    {'name': 'b', 'config': {'conductor_radius_m': core}},
                ]},
                'coils': [
                    {'name': 'a', 'current_A': current, 'path_m': loop_a.tolist()},
                    {'name': 'b', 'current_A': current, 'path_m': loop_b.tolist()},
                ],
            }
            source = d / 'array_current_paths.json'
            source.write_text(json.dumps(report))
            generate_field_array(source, d / 'array.map', half_size=6, spacing=6, max_points=1_000_000)
            rows = np.loadtxt(d / 'array.map')
            # Grid is 3x3x3 (half_size=spacing=6); index 13 (0-based) is the centre point (0,0,0).
            np.testing.assert_allclose(rows[3 + 13], individual[0], atol=1e-18)

    def test_audit_array_reports_per_coil_and_assembly_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            config_path = d / 'array.json'
            config_path.write_text(json.dumps(two_coil_config()))
            generate_array(config_path, d / 'out')
            report = audit_array(d / 'out' / 'array_current_paths.json')
            self.assertEqual(report['n_coils'], 2)
            self.assertEqual(report['n_barrel'], 1)
            self.assertEqual(report['n_endcap'], 1)
            self.assertEqual(len(report['coils']), 2)
            for coil in report['coils']:
                self.assertEqual(coil['material'], 'pilot_copper')
                self.assertAlmostEqual(coil['density_kg_m3'], 8960.0)
                self.assertAlmostEqual(coil['cad_mass_kg'], 8960.0 * coil['cad_volume_m3'], places=6)
            expected_mass = sum(c['cad_mass_kg'] for c in report['coils'])
            self.assertAlmostEqual(report['assembly_cad_conductor_mass_kg'], expected_mass, places=6)
            self.assertFalse(report['production_validated'])
            with self.assertRaises(ValueError):
                audit_array(d / 'out' / 'array_current_paths.json', critical_current=-1)


if __name__ == '__main__':
    unittest.main()
