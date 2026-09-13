#!/usr/bin/env bash
# Un contenedor no interactivo no carga .bashrc (donde install_compute_node.sh
# ya dejo el bloque de 'conda init') -- activamos el entorno explicitamente
# antes de correr el comando pedido.
#
# install_compute_node.sh instala en $MINICONDA_DIR (default $HOME/miniconda3,
# ver ese script) -- como root dentro del contenedor $HOME=/root, NO
# /opt/miniconda3 (bug real encontrado al probar la imagen: ese path
# hardcodeado no existia). Usar $HOME aqui replica exactamente lo que el
# script ya decidio, en vez de fijar una ruta propia distinta.
set -eo pipefail

# Los scripts de activacion que Geant4/conda-forge instalan en
# etc/conda/activate.d/ (ej. activate-geant4-data-abla.sh) referencian
# variables sin inicializar antes de asignarlas -- patron comun de conda,
# no compatible con `set -u` (bug real encontrado al probar la imagen:
# "G4ABLADATA: unbound variable"). Desactivar -u solo alrededor de la
# activacion, no en el resto del entrypoint.
set +u
# shellcheck disable=SC1091
source "${HOME}/miniconda3/etc/profile.d/conda.sh"
conda activate geant4_env_headless
set -u

exec "$@"
