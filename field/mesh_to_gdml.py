#!/usr/bin/env python3
"""Convert first-order Gmsh tetrahedra to closed material-separated GDML surfaces."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import xml.etree.ElementTree as ET

import gmsh
import numpy as np


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boundary(tetrahedra, points):
    """Outward surface of a conforming tetrahedral volume; reject broken topology."""
    faces = {}
    volume = 0.0
    for tet in tetrahedra:
        tet = tuple(map(int, tet))
        if len(set(tet)) != 4:
            raise ValueError('Repeated vertex in tetrahedron')
        p = np.array([points[n] for n in tet])
        determinant = float(np.dot(p[1]-p[0], np.cross(p[2]-p[0], p[3]-p[0])))
        if not np.isfinite(determinant) or abs(determinant) <= 1e-30:
            raise ValueError('Degenerate tetrahedron')
        volume += abs(determinant) / 6
        for opposite in range(4):
            face = tuple(tet[i] for i in range(4) if i != opposite)
            a, b, c = (points[n] for n in face)
            if np.dot(np.cross(b-a, c-a), points[tet[opposite]]-a) > 0:
                face = (face[0], face[2], face[1])
            faces.setdefault(tuple(sorted(face)), []).append(face)
    surface = []
    for key, adjacent in sorted(faces.items()):
        if len(adjacent) == 1:
            surface.append(adjacent[0])
        elif len(adjacent) == 2:
            def edges(face):
                return {(face[i], face[(i+1) % 3]) for i in range(3)}
            if edges(adjacent[0]) != {(b, a) for a, b in edges(adjacent[1])}:
                raise ValueError('Duplicate or inconsistently joined tetrahedra')
        else:
            raise ValueError('Non-manifold tetrahedral mesh')
    if not surface:
        raise ValueError('Empty surface')
    edges = Counter((f[i], f[(i+1) % 3]) for f in surface for i in range(3))
    if any(count != 1 or edges[(b, a)] != 1 for (a, b), count in edges.items()):
        raise ValueError('Surface is not a closed oriented manifold')
    centre = points[surface[0][0]]
    surface_volume = sum(float(np.dot(points[a]-centre,
                            np.cross(points[b]-centre, points[c]-centre)))
                         for a, b, c in surface) / 6
    if not np.isclose(surface_volume, volume, rtol=1e-8, atol=1e-24):
        raise ValueError('Surface and tetrahedral volumes disagree')
    return surface, volume


def load_config(path):
    config = json.loads(Path(path).read_text())
    if config.get('schema_version') != 1 or config.get('length_unit') not in ('m', 'mm'):
        raise ValueError('Require schema_version=1 and explicit length_unit=m or mm')
    if not isinstance(config.get('groups'), dict) or not config['groups']:
        raise ValueError('Require physical-volume groups mapped to materials (or null to exclude)')
    elements = config.get('elements', {})
    materials = config.get('materials', {})
    for name in [*elements, *materials]:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name):
            raise ValueError(f'Invalid element/material identifier: {name}')
    for element in elements.values():
        if not isinstance(element['Z'], int) or not 1 <= element['Z'] <= 118:
            raise ValueError('Invalid atomic number')
        if not np.isfinite(element['A']) or element['A'] <= 0:
            raise ValueError('Invalid atomic mass')
    for material in materials.values():
        density = material['density_g_cm3']
        fractions = material['mass_fractions']
        if not np.isfinite(density) or density <= 0 or not fractions:
            raise ValueError('Invalid material density/composition')
        if any(e not in elements or not np.isfinite(w) or w <= 0 for e, w in fractions.items()):
            raise ValueError('Unknown element or invalid mass fraction')
        if not np.isclose(sum(fractions.values()), 1., rtol=0., atol=1e-10):
            raise ValueError('Material mass fractions must sum to one')
    if any(m is not None and m not in materials for m in config['groups'].values()):
        raise ValueError('Physical group references an undefined material')
    return config


def convert(mesh_path, config_path, output):
    mesh_path, config_path, output = map(Path, (mesh_path, config_path, output))
    if mesh_path.suffix != '.msh' or output.suffix != '.gdml':
        raise ValueError('Require .msh input and .gdml output')
    inputs = {mesh_path.resolve(), config_path.resolve()}
    if output.resolve() in inputs or output.with_suffix('.manifest.json').resolve() in inputs:
        raise ValueError('Output must not overwrite an input')
    config = load_config(config_path)
    scale = 1. if config['length_unit'] == 'm' else .001
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.option.setNumber('General.Terminal', 0)
        gmsh.open(str(mesh_path))
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        points = {int(t): p*scale for t, p in zip(tags, np.asarray(xyz).reshape(-1, 3))}
        if not points or not all(np.isfinite(p).all() for p in points.values()):
            raise ValueError('Missing/non-finite mesh coordinates')
        assignment = {}
        seen_names = set()
        for _, group in gmsh.model.getPhysicalGroups(3):
            name = gmsh.model.getPhysicalName(3, group)
            if name in seen_names or name not in config['groups']:
                raise ValueError(f'Duplicate or unmapped physical volume group: {name}')
            seen_names.add(name)
            for volume in gmsh.model.getEntitiesForPhysicalGroup(3, group):
                if int(volume) in assignment:
                    raise ValueError('A volume belongs to more than one material group')
                assignment[int(volume)] = (name, config['groups'][name])
        if seen_names != set(config['groups']):
            raise ValueError('Configuration lists groups absent from the mesh')
        components = []
        for _, tag in gmsh.model.getEntities(3):
            if tag not in assignment:
                raise ValueError(f'Volume {tag} has no explicit material/exclusion')
            name, material = assignment[tag]
            if material is None:
                continue
            types, _, nodes = gmsh.model.mesh.getElements(3, tag)
            if list(types) != [4]:
                raise ValueError('Only first-order 4-node tetrahedra supported; mesh with ElementOrder=1')
            surface, volume = boundary(np.asarray(nodes[0]).reshape(-1, 4), points)
            components.append(dict(tag=tag, group=name, material=material,
                                   surface=surface, volume_m3=volume))
        if not components:
            raise ValueError('No material volumes to export')
    finally:
        gmsh.finalize()
    root = ET.Element('gdml')
    define = ET.SubElement(root, 'define')
    used = sorted({n for component in components for face in component['surface'] for n in face})
    for n in used:
        ET.SubElement(define, 'position', name=f'coil_p{n}', unit='m',
                      **dict(zip(('x', 'y', 'z'), (format(v, '.17g') for v in points[n]))))
    materials = ET.SubElement(root, 'materials')
    for name, el in sorted(config['elements'].items()):
        element = ET.SubElement(materials, 'element', name=f'coil_el_{name}', Z=str(el['Z']))
        ET.SubElement(element, 'atom', value=str(el['A']), unit='g/mole')
    for name, mat in sorted(config['materials'].items()):
        material = ET.SubElement(materials, 'material', name=f'coil_mat_{name}')
        ET.SubElement(material, 'D', value=str(mat['density_g_cm3']), unit='g/cm3')
        for element, fraction in sorted(mat['mass_fractions'].items()):
            ET.SubElement(material, 'fraction', n=str(fraction), ref=f'coil_el_{element}')
    solids = ET.SubElement(root, 'solids')
    extent = np.max(np.abs([points[n] for n in used]), axis=0) + 1.
    ET.SubElement(solids, 'box', name='coil_transport_box', lunit='m',
                  **dict(zip(('x', 'y', 'z'), map(str, 2*extent))))
    structure = ET.SubElement(root, 'structure')
    report_components = []
    for component in components:
        name = f"coil_part_{component['tag']}"
        solid = ET.SubElement(solids, 'tessellated', name=f'{name}_solid')
        for a, b, c in component['surface']:
            ET.SubElement(solid, 'triangular', vertex1=f'coil_p{a}', vertex2=f'coil_p{b}',
                          vertex3=f'coil_p{c}', type='ABSOLUTE')
        volume = ET.SubElement(structure, 'volume', name=name)
        ET.SubElement(volume, 'materialref', ref=f"coil_mat_{component['material']}")
        ET.SubElement(volume, 'solidref', ref=f'{name}_solid')
        ET.SubElement(volume, 'auxiliary', auxtype='physical_group', auxvalue=component['group'])
        report_components.append({k: v for k, v in component.items() if k != 'surface'} |
            {'triangles': len(component['surface']),
             'mass_kg': component['volume_m3']*config['materials'][component['material']]['density_g_cm3']*1000})
    world = ET.SubElement(structure, 'volume', name='coil_transport_world')
    ET.SubElement(world, 'materialref', ref='G4_Galactic')
    ET.SubElement(world, 'solidref', ref='coil_transport_box')
    for component in components:
        pv = ET.SubElement(world, 'physvol', name=f"coil_placement_{component['tag']}")
        ET.SubElement(pv, 'volumeref', ref=f"coil_part_{component['tag']}")
    setup = ET.SubElement(root, 'setup', name='Default', version='1.0')
    ET.SubElement(setup, 'world', ref='coil_transport_world')
    ET.indent(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding='utf-8', xml_declaration=True)
    report = {'schema_version': 1, 'coordinate_frame': 'Geant4 world, metres',
              'python': platform.python_version(), 'platform': platform.platform(),
              'gmsh': gmsh.__version__, 'numpy': np.__version__,
              'mesh_sha256': sha256(mesh_path), 'materials_sha256': sha256(config_path),
              'converter_sha256': sha256(__file__), 'gdml_sha256': sha256(output),
              'components': report_components}
    output.with_suffix('.manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh', type=Path)
    parser.add_argument('materials', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        report = convert(args.mesh, args.materials, args.output)
        print(f"Exported {len(report['components'])} components to {args.output}")
    except (ValueError, KeyError, OSError) as error:
        sys.exit(f'Conversion failed: {error}')
