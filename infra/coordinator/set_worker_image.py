#!/usr/bin/env python3
"""Fija el digest de imagen que el equipo quiere que TODOS los workers
Docker corran ahora mismo -- expuesto en GET /api/v1/health como
worker_image_digest. Un worker Docker (ver auto_update() en worker.py)
lo consulta antes de cada job nuevo y se auto-actualiza solo si difiere
del suyo -- nunca a mitad de una simulacion, ver AGENTS.md.

No expuesto por HTTP a proposito (mismo criterio que seed_jobs.py): un
endpoint publico para esto seria una superficie de ataque real (cualquiera
con la URL podria forzar a todos los workers a correr una imagen
arbitraria). Se escribe directo a la SQLite, igual que seed_jobs.py.

Uso:
    # Fijar el digest de una imagen ya publicada en GHCR:
    python3 set_worker_image.py sha256:78cce5255237fe3296bcd985fc04c8675ed98d46d07dd20cef7f0ea70f1ac461

    # Aceptar tambien la forma completa imagen@sha256:... (se extrae el digest):
    python3 set_worker_image.py ghcr.io/s7even-silva/iac-project/geant4-worker@sha256:78cce...

    # Ver el digest actual sin cambiar nada:
    python3 set_worker_image.py --show

    # Desactivar la auto-actualizacion (todos los workers se quedan con
    # lo que ya tienen, comportamiento de siempre):
    python3 set_worker_image.py --clear
"""
import argparse
import re
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402

DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}$")


def extract_digest(value: str) -> str:
    candidate = value
    if "@" in value:
        repository, candidate = value.rsplit("@", 1)
        if not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]*", repository):
            raise ValueError("Referencia de repositorio invalida")
    if not DIGEST_RE.fullmatch(candidate):
        raise ValueError("Se requiere sha256:<64 hex> o repositorio@sha256:<64 hex>")
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("digest", nargs="?", default=None,
                        help="Digest sha256:... o referencia completa imagen@sha256:...")
    group.add_argument("--show", action="store_true", help="Muestra el digest actual, sin cambiar nada.")
    group.add_argument("--clear", action="store_true", help="Desactiva la auto-actualizacion (borra el valor).")
    parser.add_argument("--db", type=Path, help="SQLite del SERVICIO coordinator (no una copia local)")
    args = parser.parse_args()
    if not args.show and args.db is None and not os.environ.get("COORDINATOR_DB"):
        parser.error("Indica --db o COORDINATOR_DB para no activar una SQLite local por accidente")
    if args.db is not None:
        db.DB_PATH = args.db
    if not db.DB_PATH.is_file():
        parser.error(f"No existe la DB del servicio: {db.DB_PATH}")
    try:
        digest = extract_digest(args.digest) if args.digest else None
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Coordinator DB: {db.DB_PATH.resolve()}")
    db.init_db()

    if args.show:
        current = db.get_config("worker_image_digest")
        print(current or "(sin fijar -- ningun worker se auto-actualiza)")
        return

    if args.clear:
        db.set_config("worker_image_digest", "")
        print("worker_image_digest limpiado -- ningun worker se auto-actualizara hasta que se fije uno nuevo.")
        return

    db.set_config("worker_image_digest", digest)
    print(f"worker_image_digest fijado a {digest}")
    print("Los workers Docker con auto-actualizacion lo tomaran antes de su siguiente job (no interrumpe corridas en curso).")


if __name__ == "__main__":
    main()
