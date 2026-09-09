#!/usr/bin/env python3
"""Convert first-order Gmsh tetrahedra to closed material-separated GDML surfaces."""
import argparse
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
    """Outward surface of a conforming tetrahedral volume; reject broken topology.

    Vectorized with NumPy (2026-09-09): the original pure-Python loop over
    faces (dict + sorted() per face) took 10+ minutes on a real 6.24M-tetra
    Geom14 array mesh (~25M faces). Same validation guarantees, same return
    shape (list of (a, b, c) int-tuples, float volume) -- only the
    implementation changed, not the contract other code relies on
    (mesh_to_gdml.convert() and field/tests/test_swept.py both use this
    return shape directly).
    """
    tets = np.asarray(tetrahedra, dtype=np.int64)
    if tets.ndim != 2 or tets.shape[1] != 4:
        raise ValueError('Expected 4-node tetrahedra')
    sorted_tets = np.sort(tets, axis=1)
    if np.any(sorted_tets[:, :-1] == sorted_tets[:, 1:]):
        raise ValueError('Repeated vertex in tetrahedron')

    node_ids = np.fromiter(points.keys(), dtype=np.int64)
    if node_ids.size == 0 or node_ids.min() < 0:
        raise ValueError('Invalid point indices')
    coords = np.empty((int(node_ids.max()) + 1, 3))
    coords[node_ids] = np.array([points[int(n)] for n in node_ids])

    p0, p1, p2, p3 = (coords[tets[:, i]] for i in range(4))
    determinant = np.einsum('ij,ij->i', p1 - p0, np.cross(p2 - p0, p3 - p0))
    if not np.all(np.isfinite(determinant)) or np.any(np.abs(determinant) <= 1e-30):
        raise ValueError('Degenerate tetrahedron')
    volume = float(np.sum(np.abs(determinant)) / 6)

    # Four faces per tetrahedron, each omitting one vertex (in vertex order);
    # "opposite" holds that omitted vertex, aligned with each row of "faces".
    face_local = np.array([[1, 2, 3], [0, 2, 3], [0, 1, 3], [0, 1, 2]])
    faces = tets[:, face_local].reshape(-1, 3)
    opposite = tets.reshape(-1)

    a, b, c = coords[faces[:, 0]], coords[faces[:, 1]], coords[faces[:, 2]]
    opp = coords[opposite]
    orient = np.einsum('ij,ij->i', np.cross(b - a, c - a), opp - a)
    flip = orient > 0
    faces = faces.copy()
    faces[flip, 1], faces[flip, 2] = faces[flip, 2].copy(), faces[flip, 1].copy()

    # np.unique(..., axis=0, ...) compares whole rows and is ~15x slower
    # than 1D np.unique at this scale (benchmarked: 106s vs 6.5s for 25M
    # rows) -- encode each sorted-vertex-triple as a single int64 key in a
    # fixed base (> max node id, so the encoding is injective) and run
    # np.unique on that 1D array instead. Same partition, only the lookup
    # mechanism changes.
    base = int(node_ids.max()) + 1
    def encode(rows):
        # Generic over row width (3 for faces, 2 for edges): each column's
        # place value is base**(width-1-column), same idea as positional
        # numeral encoding with digits 0..base-1.
        weights = base ** np.arange(rows.shape[1] - 1, -1, -1, dtype=np.int64)
        return rows @ weights

    key = np.sort(faces, axis=1)
    _, inverse, counts = np.unique(encode(key), return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    if np.any(counts > 2):
        raise ValueError('Non-manifold tetrahedral mesh')
    surface = faces[counts[inverse] == 1]
    if len(surface) == 0:
        raise ValueError('Empty surface')

    # Closed oriented manifold: every directed edge (a, b) around the
    # surface must appear exactly once, and its reverse (b, a) exactly once
    # (equivalent to the original's Counter-based edge check).
    directed_edges = np.concatenate((surface[:, [0, 1]], surface[:, [1, 2]], surface[:, [2, 0]]))
    undirected_key = np.sort(directed_edges, axis=1)
    _, edge_inverse, edge_counts = np.unique(encode(undirected_key), return_inverse=True, return_counts=True)
    if np.any(edge_counts != 2):
        raise ValueError('Duplicate or inconsistently joined tetrahedra')
    edge_inverse = edge_inverse.ravel()
    order = np.argsort(edge_inverse, kind='stable')
    paired = directed_edges[order].reshape(-1, 2, 2)
    if not np.array_equal(paired[:, 0], paired[:, 1, ::-1]):
        raise ValueError('Surface is not a closed oriented manifold')

    centre = coords[surface[0, 0]]
    tri_a, tri_b, tri_c = coords[surface[:, 0]], coords[surface[:, 1]], coords[surface[:, 2]]
    surface_volume = float(np.sum(np.einsum(
        'ij,ij->i', tri_a - centre, np.cross(tri_b - centre, tri_c - centre)))) / 6
    if not np.isclose(surface_volume, volume, rtol=1e-8, atol=1e-24):
        raise ValueError('Surface and tetrahedral volumes disagree')
    return [tuple(map(int, face)) for face in surface], volume


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
        # Vectorized finiteness check + array-to-dict conversion (dict is
        # still needed: boundary()'s public contract takes {id: xyz}, and
        # values below are looked up by scattered node id, not by position)
        # -- a per-node .isfinite() call in a Python comprehension took
        # ~4s at 1.4M nodes; the vectorized check takes under 0.1s.
        coords_all = np.asarray(xyz, dtype=np.float64).reshape(-1, 3) * scale
        if coords_all.size == 0 or not np.isfinite(coords_all).all():
            raise ValueError('Missing/non-finite mesh coordinates')
        points = dict(zip(map(int, tags), coords_all))
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
    # Vectorized dedup: a Python set-comprehension + sorted() over every
    # (face, vertex) pair was ~9x slower at this scale (4.2M faces, 1.4M
    # unique nodes: ~9s vs ~1s with np.unique).
    all_face_nodes = np.concatenate([np.asarray(c['surface'], dtype=np.int64).ravel()
                                     for c in components]) if components else np.empty(0, dtype=np.int64)
    used = np.unique(all_face_nodes).tolist()
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
    # Reuse coords_all (already a dense array) instead of a Python list
    # comprehension of 1.4M dict lookups + array conversions. Gmsh node
    # tags are not guaranteed contiguous or sorted, so map explicitly
    # (tag -> its row in coords_all) rather than assume tag - min(tags)
    # indexes correctly.
    tag_to_row = np.empty(int(tags.max()) + 1, dtype=np.int64)
    tag_to_row[np.asarray(tags, dtype=np.int64)] = np.arange(len(tags))
    extent = np.max(np.abs(coords_all[tag_to_row[np.asarray(used, dtype=np.int64)]]), axis=0) + 1.
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
