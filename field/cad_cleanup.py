"""Remove construction entities after all material solids have been assembled."""
import gmsh


def remove_construction_entities():
    """Keep solids and their boundaries; call only in solid-only generators.

    Not a generic importer cleanup: independent physical surfaces or wires can
    be intentional in other models. DH generators export material solids only.
    """
    removed = {}
    for dim in (2, 1, 0):
        orphaned = [(d, tag) for d, tag in gmsh.model.getEntities(dim)
                    if len(gmsh.model.getAdjacencies(d, tag)[0]) == 0]
        removed[str(dim)] = len(orphaned)
        gmsh.model.occ.remove(orphaned, recursive=False)
        gmsh.model.occ.synchronize()
    return removed
