import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generate_mesh import generate
from mesh_to_gdml import boundary, convert, load_config, sha256


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.points = {0: np.array([0.,0.,0.]), 1: np.array([1.,0.,0.]),
                       2: np.array([0.,1.,0.]), 3: np.array([0.,0.,1.]),
                       4: np.array([0.,0.,-1.])}

    def test_orientation_and_shared_face(self):
        faces, volume = boundary([[0,1,2,3], [0,1,2,4]], self.points)
        self.assertEqual(len(faces), 6)
        self.assertAlmostEqual(volume, 1/3)
        self.assertNotIn((0,1,2), [tuple(sorted(f)) for f in faces])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            boundary([[0,1,2,3], [0,1,2,3]], self.points)

    def test_degenerate_rejected(self):
        with self.assertRaises(ValueError):
            boundary([[0,1,2,2]], self.points)


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name)
        cls.mesh = cls.path/'demo.msh'
        generate(ROOT/'examples/conversion_demo.geo', cls.mesh)
        cls.config = json.loads((ROOT/'examples/materials.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_conversion(self, config):
        path = self.path/'materials.json'
        path.write_text(json.dumps(config))
        return convert(self.mesh, path, self.path/'demo.gdml')

    def test_materials_curved_shape_mass_and_determinism(self):
        report = self.run_conversion(self.config)
        self.assertEqual(len(report['components']), 2)
        components = {c['group']: c for c in report['components']}
        self.assertAlmostEqual(components['demo_support']['mass_kg'], .2*1.2*.1*2699, places=7)
        expected = 2*math.pi**2*.4*.07**2
        self.assertLess(abs(components['demo_winding']['volume_m3']/expected-1), .1)
        root = ET.parse(self.path/'demo.gdml').getroot()
        self.assertEqual({v.attrib['name'] for v in root.findall('materials/material')},
                         {'coil_mat_aluminium', 'coil_mat_copper'})
        first = sha256(self.path/'demo.gdml')
        second = self.run_conversion(self.config)
        self.assertEqual(first, second['gdml_sha256'])
        # Regenerate the mesh, rather than merely serializing it twice.
        other = self.path/'second.msh'
        generate(ROOT/'examples/conversion_demo.geo', other)
        self.assertEqual(sha256(self.mesh), sha256(other))

    def test_units(self):
        metres = self.run_conversion(self.config)
        config = copy.deepcopy(self.config)
        config['length_unit'] = 'mm'
        millimetres = self.run_conversion(config)
        for a,b in zip(metres['components'],millimetres['components']):
            self.assertAlmostEqual(b['mass_kg']/a['mass_kg'], 1e-9, delta=1e-19)

    def test_missing_group(self):
        config = copy.deepcopy(self.config)
        del config['groups']['demo_support']
        with self.assertRaises(ValueError):
            self.run_conversion(config)

    def test_exclusion(self):
        config = copy.deepcopy(self.config)
        config['groups']['demo_support'] = None
        self.assertEqual(len(self.run_conversion(config)['components']), 1)

    def test_invalid_fraction(self):
        config = copy.deepcopy(self.config)
        config['materials']['copper']['mass_fractions']['Cu'] = .9
        with self.assertRaises(ValueError):
            self.run_conversion(config)

    def test_undefined_material(self):
        config = copy.deepcopy(self.config)
        config['groups']['demo_support'] = 'unregistered'
        with self.assertRaises(ValueError):
            self.run_conversion(config)


if __name__ == '__main__':
    unittest.main()
