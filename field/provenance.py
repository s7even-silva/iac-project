#!/usr/bin/env python3
"""SHA256 provenance hashing, shared by every field/ script regardless of its own dependencies.

Split out of generate_mesh.py so pure-NumPy modules (compute_field.py,
compute_field_array.py) don't have to import gmsh just to hash a file.
"""
import hashlib


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
