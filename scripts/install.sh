#!/usr/bin/env bash
# Instala y configura todo lo necesario para compilar y correr este proyecto
# en cualquier distro Linux: Miniconda + entorno geant4_env (Geant4 11.4.2,
# CMake, gcc/g++), dependencias de sistema para Gmsh (libGLU), y el entorno
# Python aislado field/.venv (Python 3.13.5, Gmsh, NumPy) para el pipeline
# de mallado/campo de field/. No toca field/.venv con paquetes de geant4_env
# ni viceversa -- ver field/README.md, "Entorno Python aislado", sobre por
# qué están deliberadamente separados.
#
# Idempotente: se puede re-ejecutar sin romper una instalación ya hecha
# (cada paso comprueba si su resultado ya existe antes de actuar).
#
# Uso:
#   bash scripts/install.sh
#   bash scripts/install.sh --skip-system   # omite el paso de sudo/paquetes de distro
#   bash scripts/install.sh --with-elmer    # compila tambien Elmer FEM (opcional, ~15-30+ min)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MINICONDA_DIR="${MINICONDA_DIR:-$HOME/miniconda3}"
GEANT4_ENV_NAME="geant4_env"
PY313_ENV_NAME="py313_bootstrap"
SKIP_SYSTEM=0
WITH_ELMER=0

for arg in "$@"; do
  case "$arg" in
    --skip-system) SKIP_SYSTEM=1 ;;
    --with-elmer) WITH_ELMER=1 ;;
    *) echo "Argumento desconocido: $arg" >&2; exit 1 ;;
  esac
done

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$1" >&2; exit 1; }

if [[ "$(uname -s)" != "Linux" ]]; then
  die "Este instalador es solo para Linux (detectado: $(uname -s))."
fi

# ---------------------------------------------------------------------------
# 1. Dependencias de sistema: compilador base y libGLU (requerido por Gmsh
#    en tiempo de ejecución, ver field/README.md). Detecta el gestor de
#    paquetes de la distro; si no reconoce ninguno, avisa y continúa (el
#    resto del script puede seguir funcionando si esas libs ya existen).
# ---------------------------------------------------------------------------
install_system_packages() {
  log "Instalando dependencias de sistema (requiere sudo)"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y build-essential curl ca-certificates libglu1-mesa libgl1
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y gcc gcc-c++ make curl ca-certificates freeglut mesa-libGLU mesa-libGL
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y gcc gcc-c++ make curl ca-certificates freeglut mesa-libGLU mesa-libGL
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm --needed base-devel curl ca-certificates glu mesa
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y -t pattern devel_basis
    sudo zypper install -y curl ca-certificates glu Mesa-libGL1
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add --no-cache build-base curl ca-certificates glu mesa-gl
  else
    warn "No se reconoce el gestor de paquetes de esta distro (apt/dnf/yum/pacman/zypper/apk)."
    warn "Instala manualmente: un compilador de C/C++, curl, y la librería del sistema libGLU.so.1"
    warn "(necesaria para que Gmsh funcione, ver field/README.md)."
  fi
}

if [[ "$SKIP_SYSTEM" -eq 1 ]]; then
  log "Omitido: dependencias de sistema (--skip-system)"
else
  install_system_packages
fi

# ---------------------------------------------------------------------------
# 2. Miniconda: instala solo si no existe ya en $MINICONDA_DIR.
# ---------------------------------------------------------------------------
log "Comprobando Miniconda en $MINICONDA_DIR"
if [[ -x "$MINICONDA_DIR/bin/conda" ]]; then
  ok "Miniconda ya está instalado"
else
  log "Instalando Miniconda (Python 3, x86_64/aarch64 auto-detectado)"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64)  MINICONDA_ARCH="x86_64" ;;
    aarch64) MINICONDA_ARCH="aarch64" ;;
    *) die "Arquitectura no soportada por este instalador: $ARCH" ;;
  esac
  INSTALLER="$(mktemp -t miniconda-installer-XXXXXX.sh)"
  trap 'rm -f "$INSTALLER"' EXIT
  curl -fsSL "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${MINICONDA_ARCH}.sh" -o "$INSTALLER"
  # -b (modo batch) instala sin tocar el shell del usuario -- necesario para
  # correr este script sin interacción, pero deja "conda"/"conda activate"
  # inutilizables en cualquier terminal nueva, incluso tras reiniciarla
  # (confirmado: usuario reportó exactamente esto en otra maquina). El
  # instalador interactivo (sin -b) sí ofrece y corre "conda init" por su
  # cuenta; replicamos ese paso aquí explícitamente para el shell de login
  # del usuario (no necesariamente bash, que es el que corre este script).
  bash "$INSTALLER" -b -p "$MINICONDA_DIR"
  rm -f "$INSTALLER"
  trap - EXIT
  ok "Miniconda instalado en $MINICONDA_DIR"
fi

# shellcheck disable=SC1091
source "$MINICONDA_DIR/etc/profile.d/conda.sh"

# conda init es idempotente (actualiza su propio bloque marcado en el rc
# file, no lo duplica) -- se corre siempre, no solo en la instalación
# nueva de arriba, para cubrir tambien el caso de una Miniconda ya
# instalada (por este script en una version anterior, o manualmente) cuyo
# shell de login nunca recibió "conda init".
USER_SHELL="$(basename "${SHELL:-bash}")"
case "$USER_SHELL" in
  bash|zsh) : ;;
  *) warn "Shell de login '$USER_SHELL' no reconocido para 'conda init'; usando bash." ; USER_SHELL=bash ;;
esac
RC_FILE="$HOME/.$([ "$USER_SHELL" = zsh ] && echo zshrc || echo bashrc)"
if [[ -f "$RC_FILE" ]] && grep -q ">>> conda initialize >>>" "$RC_FILE" 2>/dev/null; then
  ok "'conda init $USER_SHELL' ya aplicado en $RC_FILE"
else
  log "Ejecutando 'conda init $USER_SHELL' (necesario para usar 'conda' en terminales nuevas)"
  "$MINICONDA_DIR/bin/conda" init "$USER_SHELL" >/dev/null
  ok "conda init aplicado a $USER_SHELL -- abre una terminal nueva (o reinicia esta) para que 'conda' quede disponible"
fi

# ---------------------------------------------------------------------------
# 3. Entorno geant4_env: Geant4 11.4.2 + CMake + gcc/g++ de conda-forge,
#    exactamente como pide environment.yml (incluye GDML, requerido por
#    ActiveShield_Sim).
# ---------------------------------------------------------------------------
log "Comprobando entorno conda '$GEANT4_ENV_NAME'"
if conda env list | grep -qE "^\s*${GEANT4_ENV_NAME}\s"; then
  ok "El entorno '$GEANT4_ENV_NAME' ya existe"
else
  log "Creando '$GEANT4_ENV_NAME' desde environment.yml (puede tardar varios minutos)"
  conda env create -f "$REPO_ROOT/environment.yml"
  ok "Entorno '$GEANT4_ENV_NAME' creado"
fi

GEANT4_ENV_PREFIX="$MINICONDA_DIR/envs/$GEANT4_ENV_NAME"
GXX_BIN="$GEANT4_ENV_PREFIX/bin/x86_64-conda-linux-gnu-c++"
[[ -x "$GXX_BIN" ]] || GXX_BIN="g++"

# ---------------------------------------------------------------------------
# 4. Entorno py313_bootstrap: SOLO para tener un intérprete Python 3.13.x
#    disponible en cualquier distro (nombres de paquete de Python 3.13
#    varían entre apt/dnf/pacman y no siempre están en los repos estables).
#    No se le instala nada más; field/bootstrap.py usa este intérprete
#    solo para crear field/.venv con pip, aislado de este entorno también.
# ---------------------------------------------------------------------------
log "Comprobando entorno conda '$PY313_ENV_NAME' (solo intérprete Python 3.13)"
if conda env list | grep -qE "^\s*${PY313_ENV_NAME}\s"; then
  ok "El entorno '$PY313_ENV_NAME' ya existe"
else
  log "Creando '$PY313_ENV_NAME' con Python 3.13"
  conda create -y -n "$PY313_ENV_NAME" "python=3.13" >/dev/null
  ok "Entorno '$PY313_ENV_NAME' creado"
fi
PY313_BIN="$MINICONDA_DIR/envs/$PY313_ENV_NAME/bin/python3"
[[ -x "$PY313_BIN" ]] || die "No se encontró el Python 3.13 esperado en $PY313_BIN"
"$PY313_BIN" -c 'import sys; assert sys.version_info[:2] == (3, 13), sys.version' \
  || die "El Python de '$PY313_ENV_NAME' no es 3.13.x"

# ---------------------------------------------------------------------------
# 5. field/.venv: el pipeline de mallado/campo (Gmsh, NumPy), aislado de
#    conda por completo (ver field/README.md). field/bootstrap.py exige
#    ejecutarse con Python 3.13 exacto -- se lo damos explícitamente.
# ---------------------------------------------------------------------------
log "Comprobando field/.venv"
if [[ -x "$REPO_ROOT/field/.venv/bin/python" ]]; then
  ok "field/.venv ya existe"
else
  log "Creando field/.venv con $PY313_BIN"
  (cd "$REPO_ROOT" && "$PY313_BIN" field/bootstrap.py)
  ok "field/.venv creado"
fi

# ---------------------------------------------------------------------------
# 5.5. Elmer FEM (opcional, --with-elmer): solver del campo magnetico, aun
#      no integrado al flujo del proyecto (ver field/GEOM14_STATUS.md,
#      brecha 3) -- se omite por defecto para no alargar la instalacion base
#      con algo que todavia no se usa. No hay paquete Elmer en conda-forge
#      (confirmado 2026-09-08); el PPA oficial de Ubuntu
#      (ppa:elmer-csc-ubuntu/elmer-csc-ppa) solo cubre distros Ubuntu/Debian
#      especificas, no "cualquier distro" -- se compila desde fuente en su
#      lugar, mismo criterio que Miniconda en el paso 2 de este script.
# ---------------------------------------------------------------------------
ELMER_PREFIX="${ELMER_PREFIX:-$HOME/.local/elmerfem}"
if [[ "$WITH_ELMER" -eq 1 ]]; then
  log "Comprobando Elmer FEM en $ELMER_PREFIX"
  if [[ -x "$ELMER_PREFIX/bin/ElmerSolver" ]]; then
    ok "Elmer ya está instalado en $ELMER_PREFIX"
  else
    if [[ "$SKIP_SYSTEM" -eq 0 ]]; then
      log "Instalando dependencias de compilación de Elmer (requiere sudo)"
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y git gfortran libopenmpi-dev libblas-dev liblapack-dev
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y git gcc-gfortran openmpi-devel blas-devel lapack-devel
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm --needed git gcc-fortran openmpi blas lapack
      elif command -v zypper >/dev/null 2>&1; then
        sudo zypper install -y git gcc-fortran openmpi-devel blas-devel lapack-devel
      else
        warn "No se reconoce el gestor de paquetes para las dependencias de Elmer."
        warn "Instala manualmente: git, gfortran, MPI (OpenMPI), BLAS y LAPACK de desarrollo."
      fi
    fi
    log "Compilando Elmer FEM desde fuente en $ELMER_PREFIX (puede tardar 15-30+ min)"
    ELMER_SRC="$(mktemp -d -t elmerfem-src-XXXXXX)"
    git clone --depth 1 https://www.github.com/ElmerCSC/elmerfem "$ELMER_SRC"
    # cmake vive en geant4_env (declarado en environment.yml), no se instala
    # por separado en el sistema -- sin activar el entorno aqui, este paso
    # fallaba con "cmake: command not found" en una distro sin cmake de
    # sistema (p. ej. --skip-system, o un gestor de paquetes que no lo trae
    # por defecto). Mismo patron que la verificacion final mas abajo.
    set +u
    conda activate "$GEANT4_ENV_NAME"
    set -u
    cmake -S "$ELMER_SRC" -B "$ELMER_SRC/build" \
      -DCMAKE_INSTALL_PREFIX="$ELMER_PREFIX" \
      -DWITH_MPI:BOOLEAN=TRUE -DWITH_OpenMP:BOOLEAN=TRUE
    cmake --build "$ELMER_SRC/build" -j"$(nproc)"
    cmake --install "$ELMER_SRC/build"
    set +u
    conda deactivate
    set -u
    rm -rf "$ELMER_SRC"
    ok "Elmer instalado en $ELMER_PREFIX"
  fi
  echo "$ELMER_PREFIX/bin" > "$REPO_ROOT/field/.elmer-prefix"
else
  log "Omitido: Elmer FEM (pasar --with-elmer para instalarlo; no bloquea el resto)"
fi

# ---------------------------------------------------------------------------
# 6. Verificación final: compila ambos proyectos Geant4 y corre los tests
#    Python de field/, igual que se validó manualmente en sesiones previas
#    (ver AGENTS.md, "Verificación de este cambio").
# ---------------------------------------------------------------------------
log "Verificando: compilando GCR_SEP_Sim"
# Los scripts de activación de conda-forge para los datasets de Geant4
# (G4ABLADATA y similares) referencian variables sin valor por defecto
# (p. ej. "$G4ABLADATA" en vez de "${G4ABLADATA:-}"), lo que rompe bajo
# `set -u`. No son scripts de este repo -- se desactiva nounset solo
# durante la activación/desactivación de conda.
set +u
conda activate "$GEANT4_ENV_NAME"
set -u
(
  cd "$REPO_ROOT/geant4/GCR_SEP_Sim"
  cmake -S . -B build -DCMAKE_CXX_COMPILER="$GXX_BIN" -DCMAKE_PREFIX_PATH="$GEANT4_ENV_PREFIX" >/dev/null
  cmake --build build -j"$(nproc)" >/dev/null
)
ok "GCR_SEP_Sim compila"

log "Verificando: compilando ActiveShield_Sim"
(
  cd "$REPO_ROOT/geant4/ActiveShield_Sim"
  cmake -S . -B build -DCMAKE_CXX_COMPILER="$GXX_BIN" -DCMAKE_PREFIX_PATH="$GEANT4_ENV_PREFIX" >/dev/null
  cmake --build build -j"$(nproc)" >/dev/null
)
ok "ActiveShield_Sim compila"
set +u
conda deactivate
set -u

log "Verificando: tests Python de field/"
"$REPO_ROOT/field/.venv/bin/python" -m unittest discover -s "$REPO_ROOT/field/tests" >/dev/null
ok "Tests de field/ pasan"

cat <<EOF

$(printf '\033[1;32m%s\033[0m' 'Instalación completa.')

Para trabajar en cada parte del proyecto:

  Geant4 (compilar/correr GCR_SEP_Sim o ActiveShield_Sim):
    source $MINICONDA_DIR/etc/profile.d/conda.sh
    conda activate $GEANT4_ENV_NAME
    cd geant4/<proyecto>/build && ./gcrsim ...   (o ./ICRP110phantoms ...)

  Pipeline de mallado/campo (field/):
    field/.venv/bin/python field/generate_dh.py ...
    (no hace falta activar nada; también puedes 'source field/.venv/bin/activate')
EOF

if [[ "$WITH_ELMER" -eq 1 ]]; then
cat <<EOF

  Elmer FEM (compilado desde fuente):
    export PATH="$ELMER_PREFIX/bin:\$PATH"
    ElmerSolver ...   (ver field/GEOM14_STATUS.md, brecha 3, para el
                        siguiente paso: acoplarlo al ejemplo mgdyn_steady_coils)
EOF
else
cat <<EOF

Nota: Elmer (el solver FEM del campo magnético) NO se instaló -- pasa
--with-elmer para compilarlo desde fuente (no está en conda-forge ni hay
un paquete portable entre distros; 15-30+ min). Todavía no está integrado
al flujo del proyecto (ver AGENTS.md y field/GEOM14_STATUS.md, brecha 3).
EOF
fi
