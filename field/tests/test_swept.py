import json
from pathlib import Path
import sys
import tempfile
import unittest

import gmsh
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mesh_swept import tube_tetrahedra, generate
from mesh_to_gdml import boundary
from cad_cleanup import remove_construction_entities


class SweptTests(unittest.TestCase):
    def test_closed_torus_and_volume_convergence(self):
        theta = np.arange(128)*2*np.pi/128
        path = np.column_stack((np.cos(theta), np.sin(theta), np.zeros_like(theta)))
        errors = []
        for sectors in (8, 16):
            nodes, tetra, volume, length = tube_tetrahedra(path, .02, sectors)
            faces, recovered = boundary(tetra, dict(enumerate(nodes)))
            self.assertEqual(len(faces), 2*len(path)*sectors)
            self.assertAlmostEqual(volume, recovered, places=12)
            self.assertAlmostEqual(length, 2*np.pi, delta=.001)
            errors.append(abs(volume/(2*np.pi**2*.02**2)-1))
        self.assertLess(errors[1], errors[0]/3)
        self.assertLess(errors[1], .03)

    def test_cleanup_keeps_solid_and_boundary(self):
        gmsh.initialize([], readConfigFiles=False)
        try:
            gmsh.option.setNumber('General.Terminal', 0)
            tag = gmsh.model.occ.addBox(0, 0, 0, 1, 1, 1)
            p = gmsh.model.occ.addPoint(2, 2, 2)
            q = gmsh.model.occ.addPoint(3, 2, 2)
            gmsh.model.occ.addLine(p, q)
            gmsh.model.occ.synchronize()
            removed = remove_construction_entities()
            self.assertEqual(removed['1'], 1)
            self.assertEqual(len(gmsh.model.getEntities(2)), 6)
            self.assertEqual(len(gmsh.model.getEntities(1)), 12)
            self.assertAlmostEqual(gmsh.model.occ.getMass(3, tag), 1.)
        finally:
            gmsh.finalize()

    def test_budget_and_source_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            config = json.loads((ROOT/'examples/dh_pilot.json').read_text())
            source = d/'source.json'
            source.write_text(json.dumps({'status':config['status'], 'config':config, 'cad_volume_m3':.0107042}))
            with self.assertRaisesRegex(ValueError, 'budget'):
                generate(source, d/'mesh.msh', max_elements=1)
            self.assertFalse((d/'mesh.msh').exists())
            with self.assertRaises(ValueError):
                generate(source, d/'mesh.msh', step=0)


if __name__ == '__main__':
    unittest.main()
