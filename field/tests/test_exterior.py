"""Regression: a swept conductor must survive adding a conforming global air domain."""
from pathlib import Path
import sys
import json
import tempfile
import unittest
import gmsh
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mesh_swept import tube_tetrahedra
from mesh_exterior import generate
from mesh_to_gdml import boundary


class ExteriorTests(unittest.TestCase):
    def test_tubular_export_has_globally_unique_element_ids(self):
        from mesh_swept_air import generate as generate_tube
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'source.json', Path(tmp)/'tube.msh'
            config = json.loads((root/'examples/dh_pilot.json').read_text())
            source.write_text(json.dumps({'status': config['status'], 'config': config,
                                          'cad_volume_m3': .0107042}))
            report = generate_tube(source, output, air_radius_factor=2., step=.04)
            # Inspect raw element identifiers: Gmsh itself discards duplicates on open.
            lines = output.read_text().splitlines()
            pos = lines.index('$Elements')+1
            blocks, count, _, _ = map(int, lines[pos].split())
            pos += 1
            tags = []
            volume_count = 0
            for _ in range(blocks):
                dim, entity, kind, n = map(int, lines[pos].split())
                pos += 1
                tags.extend(int(row.split()[0]) for row in lines[pos:pos+n])
                if dim == 3:
                    volume_count += n
                pos += n
            self.assertEqual(len(tags), count)
            self.assertEqual(len(tags), len(set(tags)))
            self.assertEqual(volume_count, report['conductor_tetrahedra']+report['air_tetrahedra'])

    def test_two_conductors_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/'coils.msh', Path(tmp)/'domain.msh'
            theta = np.arange(64)*2*np.pi/64
            path = np.column_stack((.3*np.cos(theta), .3*np.sin(theta), np.zeros_like(theta)))
            nodes, tetra, volume, _ = tube_tetrahedra(path, .025, 8)
            gmsh.initialize([], readConfigFiles=False)
            try:
                gmsh.option.setNumber('General.Terminal', 0)
                for i in range(2):
                    tag = gmsh.model.addDiscreteEntity(3)
                    gmsh.model.addPhysicalGroup(3, [tag], i+1, f'coil_{i}')
                    shifted = nodes + np.array([2., 0., i*.4])
                    gmsh.model.mesh.addNodes(3, tag, np.arange(1, len(nodes)+1)+i*len(nodes), shifted.ravel())
                    gmsh.model.mesh.addElementsByType(tag, 4, [], tetra.ravel()+1+i*len(nodes))
                gmsh.write(str(source))
            finally:
                gmsh.finalize()
            report = generate(source, output, padding=.3, air_size=.2)
            self.assertTrue(report['interface_preserved'])
            gmsh.initialize([], readConfigFiles=False)
            try:
                gmsh.option.setNumber('General.Terminal', 0)
                gmsh.open(str(output))
                ids, xyz, _ = gmsh.model.mesh.getNodes()
                points = dict(zip(map(int, ids), np.array(xyz).reshape(-1, 3)))
                all_tags = []
                for dim, entity in gmsh.model.getEntities():
                    _, tags, _ = gmsh.model.mesh.getElements(dim, entity)
                    all_tags.extend(np.concatenate(tags) if tags else [])
                self.assertEqual(len(all_tags), len(set(all_tags)))
                for physical in (1, 2):
                    entity = int(gmsh.model.getEntitiesForPhysicalGroup(3, physical)[0])
                    _, _, connectivity = gmsh.model.mesh.getElements(3, entity)
                    restored = np.array(connectivity[0]).reshape(-1, 4)
                    self.assertEqual(len(restored), len(tetra))
                    _, restored_volume = boundary(restored, points)
                    self.assertAlmostEqual(restored_volume, volume, places=12)
                self.assertGreater(report['air_tetrahedra'], 0)
                self.assertEqual(gmsh.model.getPhysicalName(2, 4), 'outer_boundary')
            finally:
                gmsh.finalize()


if __name__ == '__main__':
    unittest.main()
