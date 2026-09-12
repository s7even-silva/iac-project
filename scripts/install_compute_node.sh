#!/usr/bin/env bash
# Instalador MINIMO para un nodo de computo que solo va a CORRER las
# simulaciones ya existentes (ej. geant4/ActiveShield_Sim/scripts/
# run_organ_sweep.py, geant4/GCR_SEP_Sim/scripts/run_sweep.py) -- no
# regenerar geometria/campo. No instala: Qt6 (usa un build "noqt" de
# Geant4, ver environment.headless.yml -- misma fisica/GDML/datos,
# verificado 2026-09-12 comparando Geant4Config.cmake de ambas
# variantes), field/.venv (Gmsh/NumPy), py313_bootstrap, ni Elmer --
# ninguno de esos hace falta para correr el barrido, porque
# field/production/ ya trae los .map/GDML de produccion versionados en
# git (ver ese README). Si en algun momento necesitas regenerar campo/
# geometria en esta misma maquina, usa scripts/install.sh (completo) en
# vez de este.
#
# Idempotente, igual que install.sh.
#
# Uso:
#   bash scripts/install_compute_node.sh
#   bash scripts/install_compute_node.sh --skip-system   # omite el paso de sudo/paquetes de distro
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MINICONDA_DIR="${MINICONDA_DIR:-$HOME/miniconda3}"
GEANT4_ENV_NAME="geant4_env_headless"
SKIP_SYSTEM=0

for arg in "$@"; do
  case "$arg" in
    --skip-system) SKIP_SYSTEM=1 ;;
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
# 1. Dependencias de sistema: compilador base y libGL en tiempo de
#    ejecucion (Geant4 lo enlaza aunque el build sea "noqt", ver
#    environment.headless.yml). Sin libglu1-mesa a proposito -- eso es
#    solo para Gmsh/field/.venv, que este instalador no usa.
# ---------------------------------------------------------------------------
install_system_packages() {
  log "Instalando dependencias de sistema (requiere sudo)"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y build-essential curl ca-certificates libgl1
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y gcc gcc-c++ make curl ca-certificates mesa-libGL
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y gcc gcc-c++ make curl ca-certificates mesa-libGL
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm --needed base-devel curl ca-certificates mesa
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y -t pattern devel_basis
    sudo zypper install -y curl ca-certificates Mesa-libGL1
  elif command -v apk >/dev/null 2>&1; then
    sudo apk add --no-cache build-base curl ca-certificates mesa-gl
  else
    warn "No se reconoce el gestor de paquetes de esta distro (apt/dnf/yum/pacman/zypper/apk)."
    warn "Instala manualmente: un compilador de C/C++, curl, y libGL.so.1."
  fi
}

if [[ "$SKIP_SYSTEM" -eq 1 ]]; then
  log "Omitido: dependencias de sistema (--skip-system)"
else
  install_system_packages
fi

# ---------------------------------------------------------------------------
# 2. Miniconda (mismo paso que scripts/install.sh -- ver ahi el porque de
#    -b + conda init explicito).
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
  bash "$INSTALLER" -b -p "$MINICONDA_DIR"
  rm -f "$INSTALLER"
  trap - EXIT
  ok "Miniconda instalado en $MINICONDA_DIR"
fi

# shellcheck disable=SC1091
source "$MINICONDA_DIR/etc/profile.d/conda.sh"

USER_SHELL="$(basename "${SHELL:-bash}")"
case "$USER_SHELL" in
  bash|zsh) : ;;
  *) warn "Shell de login '$USER_SHELL' no reconocido para 'conda init'; usando bash." ; USER_SHELL=bash ;;
esac
RC_FILE="$HOME/.$([ "$USER_SHELL" = zsh ] && echo zshrc || echo bashrc)"
if [[ -f "$RC_FILE" ]] && grep -q ">>> conda initialize >>>" "$RC_FILE" 2>/dev/null; then
  ok "'conda init $USER_SHELL' ya aplicado en $RC_FILE"
else
  log "Ejecutando 'conda init $USER_SHELL'"
  "$MINICONDA_DIR/bin/conda" init "$USER_SHELL" >/dev/null
  ok "conda init aplicado -- abre una terminal nueva (o reinicia esta) para que 'conda' quede disponible"
fi

# ---------------------------------------------------------------------------
# 2.5. Terminos de Servicio de Anaconda (ver scripts/install.sh, mismo motivo).
# ---------------------------------------------------------------------------
if conda tos --help >/dev/null 2>&1; then
  log "Aceptando Términos de Servicio de los canales por defecto de Anaconda"
  conda tos accept -c https://repo.anaconda.com/pkgs/main -c https://repo.anaconda.com/pkgs/r
  ok "Términos de Servicio aceptados"
else
  warn "Esta versión de conda no tiene 'conda tos' -- acéptalos manualmente si falla el paso siguiente."
fi

# ---------------------------------------------------------------------------
# 3. Entorno geant4_env_headless: Geant4 11.4.2 build "noqt" + CMake +
#    gcc/g++/gfortran de conda-forge -- ver environment.headless.yml para
#    el detalle completo de por que noqt y que se ahorra.
# ---------------------------------------------------------------------------
log "Comprobando entorno conda '$GEANT4_ENV_NAME'"
if conda env list | grep -qE "^\s*${GEANT4_ENV_NAME}\s"; then
  ok "El entorno '$GEANT4_ENV_NAME' ya existe"
else
  log "Creando '$GEANT4_ENV_NAME' desde environment.headless.yml (unos minutos)"
  conda env create -f "$REPO_ROOT/environment.headless.yml"
  ok "Entorno '$GEANT4_ENV_NAME' creado"
fi
GEANT4_ENV_PREFIX="$MINICONDA_DIR/envs/$GEANT4_ENV_NAME"

# ---------------------------------------------------------------------------
# 4. Compilar los dos proyectos con -DWITH_GEANT4_UIVIS=OFF (evita pedir
#    los componentes ui_all/vis_all -- no hacen falta para correr en modo
#    batch, y el build "noqt" no trae Qt6 para satisfacerlos de todos
#    modos). g++ del sistema, no el compilador largo de conda -- mismo
#    motivo ya verificado en scripts/install.sh (enlazar/ejecutar contra
#    las .so de Geant4/CLHEP no exige compartir sysroot con la libreria).
# ---------------------------------------------------------------------------
set +u
conda activate "$GEANT4_ENV_NAME"
set -u

log "Compilando GCR_SEP_Sim (headless)"
(
  cd "$REPO_ROOT/geant4/GCR_SEP_Sim"
  cmake -S . -B build -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$GEANT4_ENV_PREFIX" -DWITH_GEANT4_UIVIS=OFF >/dev/null
  cmake --build build -j"$(nproc)" >/dev/null
)
ok "GCR_SEP_Sim compila"

log "Compilando ActiveShield_Sim (headless)"
(
  cd "$REPO_ROOT/geant4/ActiveShield_Sim"
  cmake -S . -B build -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$GEANT4_ENV_PREFIX" -DWITH_GEANT4_UIVIS=OFF >/dev/null
  cmake --build build -j"$(nproc)" >/dev/null
)
ok "ActiveShield_Sim compila"

log "Verificando con ctest"
ctest --test-dir "$REPO_ROOT/geant4/ActiveShield_Sim/build" --output-on-failure
ok "Tests pasan"

set +u
conda deactivate
set -u

cat <<EOF

$(printf '\033[1;32m%s\033[0m' 'Instalación mínima completa.')

field/production/ ya trae el .map y el GDML de producción (versionados en
git) -- no hace falta regenerar nada para correr el barrido:

  source $MINICONDA_DIR/etc/profile.d/conda.sh
  conda activate $GEANT4_ENV_NAME
  cd geant4/ActiveShield_Sim/build
  python3 ../scripts/run_organ_sweep.py --only-positions <lo que te toque>

Si en algún momento necesitas regenerar geometría/campo (field/.venv,
Elmer) en esta misma máquina, usa scripts/install.sh en vez de este.
EOF
