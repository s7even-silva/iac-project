import json
from pathlib import Path
import sys
import tempfile
import unittest

import gmsh
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mesh_swept import tube_tetrahedra, ribbon_tetrahedra, generate
from mesh_to_gdml import boundary, convert
from cad_cleanup import remove_construction_entities
from generate_dh import generate as generate_dh, controls, has_tape_section


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

    def test_ribbon_torus_and_orientation(self):
        theta = np.arange(128)*2*np.pi/128
        path = np.column_stack((np.cos(theta), np.sin(theta), np.zeros_like(theta)))
        width, thickness = .05, .0002
        nodes, tetra, volume, length = ribbon_tetrahedra(path, width, thickness, 4, 1)
        faces, recovered = boundary(tetra, dict(enumerate(nodes)))
        self.assertAlmostEqual(volume, recovered, places=12)
        self.assertAlmostEqual(length, 2*np.pi, delta=.001)
        expected = 2*np.pi*width*thickness  # thin-ribbon torus: 2*pi*R * cross-section area, R=1
        self.assertLess(abs(volume/expected-1), .001)
        with self.assertRaises(ValueError):
            ribbon_tetrahedra(path, width, thickness, 0, 1)

    def test_tape_section_end_to_end_cad_and_swept_agree(self):
        """Brecha 2 (GEOM14_STATUS.md): rectangular HTS tape cross-section
        instead of the circular equivalent-area placeholder. Checks the
        full path a real Geom14 run would take -- CAD (generate_dh.py) then
        structured swept tetrahedra (mesh_swept.py) then GDML -- agree on
        volume within the same 5% guard already used for circular coils,
        and that the resulting GDML mass matches the swept volume exactly
        (boundary() conserves the tetrahedral volume it was given)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            config = json.loads((ROOT/'examples/dh_pilot.json').read_text())
            config['turns'] = 2
            config['field_segments'] = 256
            config['tape_width_m'] = .02
            config['tape_thickness_m'] = .004
            self.assertTrue(has_tape_section(config))
            controls(config)  # must not raise: dimensions are self-consistent
            config_path = d/'tape.json'
            config_path.write_text(json.dumps(config))
            generate_dh(config_path, d)
            report = generate(d/'current_path.json', d/'mesh.msh')
            component = report['components'][0]
            self.assertEqual(component['section'], 'rectangular')
            self.assertLess(abs(component['relative_volume_error']), .05)
            convert(d/'mesh.msh', d/'materials.json', d/'dh.gdml')
            manifest = json.loads(d.joinpath('dh.manifest.json').read_text())
            self.assertAlmostEqual(manifest['components'][0]['volume_m3'], component['volume_m3'], places=9)

    def test_controls_rejects_invalid_tape_dimensions(self):
        config = json.loads((ROOT/'examples/dh_pilot.json').read_text())
        config['tape_width_m'] = .5  # wider than the coil's own radial gap
        config['tape_thickness_m'] = .01
        with self.assertRaises(ValueError):
            controls(config)
        config['tape_width_m'], config['tape_thickness_m'] = .02, .04  # thickness > width
        with self.assertRaises(ValueError):
            controls(config)

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
