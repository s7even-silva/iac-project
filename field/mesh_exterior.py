#!/usr/bin/env python3
"""Add a global air box to an existing linear conductor mesh, without CAD sweeps.

Run under an external timeout: native Gmsh calls cannot be interrupted reliably
by a Python timer. Output is published only after conformity/volume checks.
"""
import argparse
import json
from pathlib import Path
import time

import gmsh
import numpy as np
from generate_mesh import digest
from mesh_to_gdml import boundary


def face_keys(faces):
    return sorted(map(tuple, np.sort(np.asarray(faces).reshape(-1, 3), axis=1)))


def generate(source, output, padding=1., air_size=.3, optimize_threshold=.01, threads=1):
    if source.resolve() == output.resolve() or output.suffix != '.msh':
        raise ValueError('Use a distinct .msh output')
    if not np.isfinite([padding, air_size, optimize_threshold]).all() or min(padding, air_size) <= 0:
        raise ValueError('Require finite positive padding and air size')
    if not 0 < optimize_threshold <= 1 or threads < 1:
        raise ValueError('Require 0 < optimization threshold <= 1 and threads >= 1')
    start = time.monotonic()
    temporary = output.with_name(output.stem + '.partial.msh')
    output.parent.mkdir(parents=True, exist_ok=True)
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.option.setNumber('General.NumThreads', threads)
        gmsh.option.setNumber('Mesh.Renumber', 0)
        gmsh.open(str(source))
        ids, xyz, _ = gmsh.model.mesh.getNodes()
        points = dict(zip(map(int, ids), np.asarray(xyz).reshape(-1, 3)))
        components = []
        entities_seen = set()
        for dim, physical in gmsh.model.getPhysicalGroups(3):
            name = gmsh.model.getPhysicalName(dim, physical)
            if name.lower() in ('air', 'vacuum'):
                raise ValueError('Input must contain conductors only; regenerate with mesh_swept.py')
            chunks = []
            for entity in gmsh.model.getEntitiesForPhysicalGroup(3, physical):
                if int(entity) in entities_seen:
                    raise ValueError('Overlapping physical groups are not supported')
                entities_seen.add(int(entity))
                kinds, _, nodes = gmsh.model.mesh.getElements(3, int(entity))
                if list(kinds) != [4]:
                    raise ValueError('Each conductor must contain only linear tetrahedra')
                chunks.append(np.asarray(nodes[0], dtype=np.int64).reshape(-1, 4))
            tetra = np.concatenate(chunks)
            faces, volume = boundary(tetra, points)
            components.append((name or f'conductor_{physical}', tetra, np.asarray(faces), volume))
        if not components:
            raise ValueError('No physical conductor volumes found')
        if entities_seen != {tag for _, tag in gmsh.model.getEntities(3)}:
            raise ValueError('Every input volume must belong to a physical conductor group')
        used = np.unique(np.concatenate([t.ravel() for _, t, _, _ in components]))
        coords = np.array([points[int(i)] for i in used])
        lower, upper = coords.min(0)-padding, coords.max(0)+padding
        gmsh.clear()
        # Only the six planes of a box go through the 2D mesher.
        gmsh.model.occ.addBox(*lower, *(upper-lower))
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber('Mesh.MeshSizeMax', air_size)
        gmsh.model.mesh.generate(2)
        outer_ids, outer_xyz, _ = gmsh.model.mesh.getNodes()
        offset = int(used.max())
        kinds, _, nodes = gmsh.model.mesh.getElements(2)
        if list(kinds) != [2]:
            raise ValueError('Outer surface must contain linear triangles')
        outer_faces = np.asarray(nodes[0], dtype=np.int64).reshape(-1, 3)+offset
        outer_ids = np.asarray(outer_ids, dtype=np.int64)+offset
        gmsh.clear()
        loops, surfaces = [], []
        for name, tetra, faces, volume in components:
            surface = gmsh.model.addDiscreteEntity(2)
            boundary_ids = np.unique(faces)
            gmsh.model.mesh.addNodes(2, surface, boundary_ids,
                                    np.array([points[int(i)] for i in boundary_ids]).ravel())
            gmsh.model.mesh.addElementsByType(surface, 2, [], faces.ravel())
            loops.append(gmsh.model.geo.addSurfaceLoop([surface]))
            surfaces.append(surface)
        outer = gmsh.model.addDiscreteEntity(2)
        gmsh.model.mesh.addNodes(2, outer, outer_ids, outer_xyz)
        gmsh.model.mesh.addElementsByType(outer, 2, [], outer_faces.ravel())
        outer_loop = gmsh.model.geo.addSurfaceLoop([outer])
        air = gmsh.model.geo.addVolume([outer_loop, *loops])
        gmsh.model.geo.synchronize()
        gmsh.option.setNumber('Mesh.MeshSizeMax', air_size)
        gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary', 0)
        gmsh.option.setNumber('Mesh.Algorithm3D', 10)
        gmsh.option.setNumber('Mesh.OptimizeThreshold', optimize_threshold)
        gmsh.option.setNumber('Mesh.RandomSeed', 1)
        print('[exterior] meshing air; conductor surfaces already triangulated', flush=True)
        gmsh.model.mesh.generate(3)
        for surface, (_, _, faces, _) in zip(surfaces, components):
            _, _, actual = gmsh.model.mesh.getElements(2, surface)
            if face_keys(actual[0]) != face_keys(faces):
                raise ValueError('Mesher changed the conductor interface; refusing nonconforming mesh')
        _, air_tags, air_nodes = gmsh.model.mesh.getElements(3, air)
        air_tetra = np.asarray(air_nodes[0], dtype=np.int64).reshape(-1, 4)
        all_ids, all_xyz, _ = gmsh.model.mesh.getNodes()
        mesh_points = dict(zip(map(int, all_ids), np.asarray(all_xyz).reshape(-1, 3)))
        interface_ids = np.unique(np.concatenate([c[2].ravel() for c in components]))
        if not np.array_equal(np.array([mesh_points[int(i)] for i in interface_ids]),
                              np.array([points[int(i)] for i in interface_ids])):
            raise ValueError('Mesher moved conductor interface nodes')
        quality = gmsh.model.mesh.getElementQualities(air_tags[0], 'minSICN')
        air_faces, air_volume = boundary(air_tetra, mesh_points)
        expected = np.concatenate([outer_faces, *[c[2] for c in components]])
        if face_keys(air_faces) != face_keys(expected):
            raise ValueError('Air boundary does not match the outer box plus conductor interfaces')
        target_volume = float(np.prod(upper-lower))-sum(c[3] for c in components)
        if not np.isclose(air_volume, target_volume, rtol=1e-8, atol=1e-12):
            raise ValueError('Air volume does not equal box minus conductors')
        # Restore ORIGINAL conductor tetrahedra; never remesh their interiors.
        for index, (surface, (name, tetra, faces, volume)) in enumerate(zip(surfaces, components), 1):
            entity = gmsh.model.addDiscreteEntity(3, boundary=[surface])
            interior = np.setdiff1d(np.unique(tetra), np.unique(faces))
            gmsh.model.mesh.addNodes(3, entity, interior,
                                    np.array([points[int(i)] for i in interior]).ravel())
            gmsh.model.mesh.addElementsByType(entity, 4, [], tetra.ravel())
            gmsh.model.addPhysicalGroup(3, [entity], index, name)
        gmsh.model.addPhysicalGroup(3, [air], len(components)+1, 'air')
        gmsh.model.addPhysicalGroup(2, [outer], len(components)+2, 'outer_boundary')
        gmsh.model.mesh.renumberNodes()
        gmsh.model.mesh.renumberElements()
        for key, value in {'Mesh.MshFileVersion': 4.1, 'Mesh.Binary': 0, 'Mesh.SaveAll': 0}.items():
            gmsh.option.setNumber(key, value)
        gmsh.write(str(temporary))
        temporary.replace(output)
        report = {'method': 'discrete_conductor_global_air', 'production_validated': False,
                  'source_sha256': digest(source), 'mesh_sha256': digest(output),
                  'generator_sha256': digest(Path(__file__)), 'gmsh': gmsh.__version__,
                  'padding_m': padding, 'air_size_m': air_size,
                  'optimization_threshold': optimize_threshold, 'threads': threads,
                  'bounds_m': [lower.tolist(), upper.tolist()], 'air_volume_m3': air_volume,
                  'air_tetrahedra': len(air_tetra), 'interface_preserved': True,
                  'air_minSICN_percentiles_0_1_50_100': np.percentile(quality, [0, 1, 50, 100]).tolist(),
                  'conductors': [{'name': c[0], 'tetrahedra': len(c[1]), 'volume_m3': c[3]}
                                 for c in components], 'elapsed_s': time.monotonic()-start}
        output.with_suffix('.mesh-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
        return report
    finally:
        gmsh.finalize()
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Conductor-only .msh from mesh_swept.py')
    parser.add_argument('output', type=Path)
    parser.add_argument('--padding', type=float, default=1., help='Box margin from conductor bounds, metres')
    parser.add_argument('--air-size', type=float, default=.3, help='Maximum air element size, metres')
    parser.add_argument('--optimize-threshold', type=float, default=.01,
                        help='Gmsh quality optimization target, not an accuracy tolerance')
    parser.add_argument('--threads', type=int, default=1)
    args = parser.parse_args()
    print(json.dumps(generate(args.source, args.output, args.padding, args.air_size,
                              args.optimize_threshold, args.threads), indent=2))
