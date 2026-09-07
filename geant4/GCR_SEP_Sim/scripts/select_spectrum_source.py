#!/usr/bin/env python3
"""Copia los 6 CSV de espectro de una fuente (data/sources/<fuente>/) a
data/, que es donde SpectrumSampler los lee en tiempo de ejecucion
(PrimaryGeneratorAction.cc los abre como "data/gcr_proton_solarmax.csv", etc.,
relativo al directorio de build -- ver CMakeLists.txt, que copia data/ a
build/).

Por que copiar y no symlink: el equipo compila tanto en Linux como en
Windows (computadoras de la universidad). Git en Windows no crea symlinks
reales por defecto (requiere modo desarrollador + core.symlinks=true, nada
de eso es el default), asi que un symlink se rompe silenciosamente para
cualquiera que clone el repo en Windows sin esa configuracion. Copiar un
archivo es identico en cualquier SO sin configuracion especial.

SpectrumSampler.cc es agnostico a la fuente de los datos -- solo lee un CSV
de dos columnas (energia, flujo). El "adaptador" real entre una fuente de
datos (SPENVIS, OLTARIS, lo que sea) y el codigo de Geant4 es este script:
cambiar de fuente es correrlo con otro nombre, no tocar C++.

Uso:
    python3 select_spectrum_source.py spenvis
    python3 select_spectrum_source.py oltaris_oct1989
    python3 select_spectrum_source.py --list
"""
import argparse
import shutil
import sys
from pathlib import Path

REQUIRED_FILES = [
    "gcr_proton_solarmax.csv", "gcr_proton_solarmin.csv",
    "gcr_alpha_solarmax.csv", "gcr_alpha_solarmin.csv",
    "sep_proton_solarmax.csv", "sep_proton_solarmin.csv",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", nargs="?", help="Nombre de la carpeta en data/sources/ a activar")
    parser.add_argument("--list", action="store_true", help="Listar fuentes disponibles en data/sources/ y salir")
    parser.add_argument("--only", nargs="+", choices=REQUIRED_FILES, default=None,
                         help="Copiar solo estos archivos en vez de los 6 (ej. para activar SEP de una "
                              "fuente y dejar GCR de otra) -- usar con cuidado, revisar bien Metodos si "
                              "se mezclan fuentes distintas por especie/fase")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    sources_dir = project_root / "data" / "sources"
    data_dir = project_root / "data"

    if args.list or args.source is None:
        available = sorted(p.name for p in sources_dir.iterdir() if p.is_dir()) if sources_dir.is_dir() else []
        print("Fuentes disponibles en data/sources/:")
        for name in available:
            src = sources_dir / name
            have = [f for f in REQUIRED_FILES if (src / f).is_file()]
            status = "completa" if len(have) == len(REQUIRED_FILES) else f"incompleta ({len(have)}/{len(REQUIRED_FILES)})"
            print(f"  - {name}  [{status}]")
        if args.source is None:
            sys.exit(0 if args.list else "Falta el nombre de la fuente. Usar --list para ver las disponibles.")
        return

    src_dir = sources_dir / args.source
    if not src_dir.is_dir():
        sys.exit(f"ERROR: no existe {src_dir}")

    files_to_copy = args.only or REQUIRED_FILES
    missing = [f for f in files_to_copy if not (src_dir / f).is_file()]
    if missing:
        sys.exit(f"ERROR: faltan estos archivos en {src_dir}: {', '.join(missing)}")

    data_dir.mkdir(parents=True, exist_ok=True)
    for fname in files_to_copy:
        shutil.copyfile(src_dir / fname, data_dir / fname)
        print(f"  {src_dir / fname} -> {data_dir / fname}")

    print(f"\nListo: {len(files_to_copy)} archivo(s) copiados desde '{args.source}' a {data_dir}.")
    print("IMPORTANTE: CMakeLists.txt copia data/ a build/data/ durante la fase de "
          "configuracion de CMake (file(COPY ...)), no en cada 'make'. Para que el "
          "binario use los CSV actualizados hay que volver a correr 'cmake ..' "
          "dentro de build/ (no basta con 'make -j'), o copiar los CSV a mano a "
          "build/data/ si no se quiere reconfigurar todo.")


if __name__ == "__main__":
    main()
