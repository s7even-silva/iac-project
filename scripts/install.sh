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
# 2.5. Términos de Servicio de Anaconda: desde 2025 conda exige aceptar el
#      ToS de los canales "defaults" (pkgs/main, pkgs/r) antes de resolver
#      CUALQUIER entorno, incluso uno cuyo environment.yml solo lista
#      "conda-forge" -- la instalación base de conda trae "defaults" en su
#      config global de canales aparte de lo que pida el .yml. Sin aceptar,
#      "conda env create" falla con "the following channels have not been
#      accepted" (confirmado: reportado tras probar el script en otra
#      máquina, con conda 26.5.3 recién instalado). "conda tos" es un
#      subcomando relativamente nuevo (plugin conda-anaconda-tos, 2025) --
#      si una Miniconda más vieja no lo trae, se omite con una advertencia
#      en vez de fallar todo el script.
# ---------------------------------------------------------------------------
if conda tos --help >/dev/null 2>&1; then
  log "Aceptando Términos de Servicio de los canales por defecto de Anaconda"
  conda tos accept -c https://repo.anaconda.com/pkgs/main -c https://repo.anaconda.com/pkgs/r
  ok "Términos de Servicio aceptados"
else
  warn "Esta versión de conda no tiene 'conda tos' -- si 'conda env create' falla"
  warn "más abajo por Términos de Servicio no aceptados, actualiza conda o acéptalos"
  warn "manualmente (ver https://www.anaconda.com/docs/getting-started/tos-plugin)."
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
# Same idea for C and Fortran: gcc_linux-64/gxx_linux-64/gfortran_linux-64
# from conda-forge do NOT expose plain "gcc"/"g++"/"gfortran" on PATH --
# only the long x86_64-conda-linux-gnu- prefixed names. Without pointing
# CMake at these explicitly, it silently falls back to auto-detecting a
# SYSTEM compiler instead (confirmed: this caused both a real link
# failure building Elmer -- mixing conda C/C++ with the system's
# /usr/bin/f95 -- and, after installing gfortran_linux-64, a "GNU Fortran
# major version is too old" error from CMake still finding /usr/bin/f95
# ahead of the newly-installed conda one).
GCC_BIN="$GEANT4_ENV_PREFIX/bin/x86_64-conda-linux-gnu-cc"
[[ -x "$GCC_BIN" ]] || GCC_BIN="gcc"
GFORTRAN_BIN="$GEANT4_ENV_PREFIX/bin/x86_64-conda-linux-gnu-gfortran"
[[ -x "$GFORTRAN_BIN" ]] || GFORTRAN_BIN="gfortran"

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
    # Elmer's own CMakeLists.txt (cmake/Modules/testGFortranVersion.cmake)
    # checks the Fortran compiler version by compiling AND RUNNING a tiny
    # program via try_run, not by trusting CMAKE_Fortran_COMPILER_VERSION.
    # On a VM whose hypervisor exposes an incomplete CPU feature set (seen
    # on a KVM/Oracle VM: avx2/bmi2 present but fma/f16c/lzcnt/osxsave
    # missing), conda-forge's gcc_linux-64/gfortran_linux-64 toolchain
    # links against its own sysroot's Scrt1.o, which carries an ELF
    # GNU_PROPERTY note declaring "x86 ISA needed: up to x86-64-v3" --
    # every binary built with it then aborts at exec with "CPU ISA level
    # is lower than required" (a glibc dynamic-linker compatibility check,
    # confirmed by inspecting `readelf -n` on the conda sysroot's Scrt1.o
    # vs. the system's, which only needs baseline). try_run can't tell
    # "compiler too old" apart from "binary can't even run here", so this
    # surfaces as the same misleading "GNU Fortran major version is too
    # old, should be at least 7" error CMake shows for a real old compiler.
    # Detect this up front with the exact same compile+run try_run does,
    # and fall back to the system's own gcc/g++/gfortran (same 15.x
    # version family, fully self-consistent sysroot) for Elmer specifically
    # -- Elmer compiles its own C/C++/Fortran sources from scratch, where
    # mixing sysroots across the three compilers is what caused the real
    # link failure documented above for GXX_BIN/GCC_BIN/GFORTRAN_BIN.
    # (Correction 2026-09-10: the two Geant4 client projects below do NOT
    # have that same requirement -- they only compile small .cc files that
    # link against Geant4/CLHEP's already-built .so files, so plain system
    # g++ works fine there too, confirmed by actually running the
    # resulting binaries on an ISA-limited VM; see the two `cmake` calls
    # near "Verificando: compilando" further down, which now use system
    # g++ directly instead of GXX_BIN for exactly this reason.)
    ELMER_ISA_PROBE="$(mktemp -d -t elmer-isa-probe-XXXXXX)"
    cat > "$ELMER_ISA_PROBE/probe.f90" <<'EOF'
program probe
end program probe
EOF
    ELMER_CC="$GCC_BIN"
    ELMER_CXX="$GXX_BIN"
    ELMER_FC="$GFORTRAN_BIN"
    if "$GFORTRAN_BIN" "$ELMER_ISA_PROBE/probe.f90" -o "$ELMER_ISA_PROBE/probe" >/dev/null 2>&1 \
       && "$ELMER_ISA_PROBE/probe" >/dev/null 2>&1; then
      ok "Toolchain de conda-forge ejecuta binarios correctamente (usado para Elmer)"
    else
      warn "El toolchain de conda-forge no puede ejecutar binarios en esta máquina"
      warn "(síntoma típico: 'CPU ISA level is lower than required' -- el"
      warn "sysroot de conda-forge exige hasta x86-64-v3 y este hipervisor no"
      warn "expone fma/f16c/lzcnt/osxsave completos). Usando gcc/g++/gfortran"
      warn "del sistema para compilar Elmer en su lugar."
      command -v gcc >/dev/null 2>&1 || die "Se necesita 'gcc' del sistema (instala build-essential / el paquete equivalente de tu distro)."
      command -v g++ >/dev/null 2>&1 || die "Se necesita 'g++' del sistema."
      command -v gfortran >/dev/null 2>&1 || die "Se necesita 'gfortran' del sistema."
      ELMER_CC="gcc"
      ELMER_CXX="g++"
      ELMER_FC="gfortran"
    fi
    rm -rf "$ELMER_ISA_PROBE"

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
    # WITH_MPI=FALSE deliberately: this project never runs ElmerSolver
    # distributed (always a single process, no mpirun -- confirmed by
    # every real run so far logging "Running one task without MPI
    # parallelization"). With MPI enabled, Elmer's own CMakeLists.txt
    # (cmake/Modules/testMPIcapabilities.cmake) compiles AND RUNS a real
    # MPI program (MPI_Init/Allreduce/Finalize) via try_run to check
    # MPI_IN_PLACE support -- OpenMPI programs can hang indefinitely at
    # that point on certain single-node network configurations (a known,
    # documented OpenMPI issue, not specific to this project). Confirmed:
    # reported stuck for an extended time at exactly that CMake message on
    # another machine. Disabling MPI avoids the check (and the hang)
    # entirely, at the cost of a capability (distributed Elmer) this
    # project has never used.
    cmake -S "$ELMER_SRC" -B "$ELMER_SRC/build" \
      -DCMAKE_INSTALL_PREFIX="$ELMER_PREFIX" \
      -DCMAKE_C_COMPILER="$ELMER_CC" -DCMAKE_CXX_COMPILER="$ELMER_CXX" \
      -DCMAKE_Fortran_COMPILER="$ELMER_FC" \
      -DWITH_MPI:BOOLEAN=FALSE -DWITH_OpenMP:BOOLEAN=TRUE
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
#
#    Fix (2026-09-10): estos dos `cmake` usaban GXX_BIN (el compilador
#    largo de conda-forge), no system g++ como recomiendan las instrucciones
#    manuales de AGENTS.md/README.md -- eso compilaba binarios exigiendo
#    ISA x86-64-v3 (mismo bug ya diagnosticado para Elmer, ver más arriba)
#    que compilan sin error pero abortan con "CPU ISA level is lower than
#    required" al ejecutarse en una VM con CPU recortada, algo que este
#    paso de verificación nunca detectaba porque solo compila, no corre
#    los binarios. A diferencia de Elmer (que compila su propio C/C++/
#    Fortran desde cero y sí necesita un triplete de compiladores
#    consistente), estos dos proyectos solo compilan un puñado de .cc
#    propios que enlazan contra las bibliotecas .so ya compiladas de
#    Geant4/CLHEP -- confirmado que system g++ las enlaza y ejecuta sin
#    problema, igual que ya documentaban (sin verificar hasta ahora) los
#    comandos manuales. Corregido a system g++ en los dos `cmake` de abajo.
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
  cmake -S . -B build -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$GEANT4_ENV_PREFIX" >/dev/null
  cmake --build build -j"$(nproc)" >/dev/null
)
ok "GCR_SEP_Sim compila"

log "Verificando: compilando ActiveShield_Sim"
(
  cd "$REPO_ROOT/geant4/ActiveShield_Sim"
  cmake -S . -B build -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$GEANT4_ENV_PREFIX" >/dev/null
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
