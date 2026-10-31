#!/usr/bin/env bash
# Validación del mapa de Biot-Savart volumétrico con Elmer, una sola bobina
# (plan_piloto.md, P1 paso 2; field/README.md, «Biot-Savart volumétrico»).
#
# Uso, desde cualquier carpeta:
#   bash field/elmer_una_bobina.sh MARGEN_M AIRE_M [HILOS]
#
# Cada PC corre un nivel de malla. Deja todo en
# field/generated/elmer_una_bobina_m<MARGEN>_a<AIRE>/ y, al final, la
# comparación con Biot-Savart en validacion.json, que guarda además el campo
# de Elmer en las sondas para comparar después los niveles entre sí.
# La malla del conductor se refina con el aire (lado de min(AIRE/2, 0.15) m).
set -euo pipefail
MARGEN=${1:?"margen de la caja alrededor de la bobina, en m"}
AIRE=${2:?"tamaño máximo de los tetraedros de aire, en m"}
HILOS=${3:-$(nproc)}
F="$(cd "$(dirname "$0")" && pwd)"
PY="$F/.venv/bin/python"
ELMER_BIN="$(cat "$F/.elmer-prefix" 2>/dev/null || echo "$HOME/.local/elmerfem/bin")"
COND=$("$PY" -c "print(min(float('$AIRE')/2, 0.15))")

# 1. Malla del conductor (una vez por tamaño y PC).
G="$F/generated/niac_conductor_$COND"
if [[ ! -f "$G/halbach_array.msh" ]]; then
  mkdir -p "$G"
  "$PY" - "$F/examples/crewhat_niac_array.json" "$G/config.json" "$COND" <<'EOF'
import json, sys
c = json.load(open(sys.argv[1]))
h = float(sys.argv[3])
c['coil_template']['mesh_size_m'], c['coil_template']['mesh_min_size_m'] = h, h/2
json.dump(c, open(sys.argv[2], 'w'), indent=1)
EOF
  "$PY" "$F/generate_ellipse_array.py" "$G/config.json" "$G" > "$G/cad.log" 2>&1
  "$PY" "$F/generate_mesh.py" "$G/halbach_array.geo" "$G/halbach_array.msh" \
    --dependency "$G/halbach_array.brep" --dependency "$G/config.json" > "$G/malla.log" 2>&1
fi

# 2. Módulo local de Elmer (una vez por PC).
[[ -f "$F/generated/elmer_plugin/CoilSolverRestricted.so" ]] || \
  "$PY" "$F/build_coilsolver.py" --elmerf90 "$ELMER_BIN/elmerf90"

# 3. Aire alrededor de la bobina 0 sola, malla de Elmer y solve.
D="$F/generated/elmer_una_bobina_m${MARGEN}_a${AIRE}"
mkdir -p "$D" && cd "$D"
echo "[elmer] mallando el aire (margen $MARGEN m, aire $AIRE m, conductor $COND m)"
"$PY" "$F/mesh_exterior.py" "$G/halbach_array.msh" domain.msh --groups crewhat_coil_0 \
  --padding "$MARGEN" --air-size "$AIRE" --threads "$HILOS" > malla.log 2>&1
"$PY" -c "import json; m = json.load(open('domain.mesh-manifest.json')); print('[elmer]', m['air_tetrahedra'], 'tetraedros de aire')"
"$ELMER_BIN/ElmerGrid" 14 2 domain.msh -out elmer_mesh > grid.log 2>&1
cat elmer_mesh/mesh.names
cp "$F/examples/crewhat_niac_single_coil.sif" case.sif
cp "$F/generated/elmer_plugin/CoilSolverRestricted.so" .
echo "[elmer] resolviendo (un proceso; ver solver.log)"
OMP_NUM_THREADS=1 "$ELMER_BIN/ElmerSolver" case.sif > solver.log 2>&1
grep -E "BiCGStabl robust|ALL DONE" solver.log

# 4. Comparación con Biot-Savart volumétrico de la misma bobina.
"$PY" "$F/validate_volumetric_field.py" "$F/production/crewhat_niac_array_current_paths.json" \
  validacion.json --coil 0 --filaments 6 3 24 12 --radial-max 12 --vtu elmer_mesh/elmer_pilot_air_t0001.vtu
echo "[elmer] listo: $D/validacion.json"
