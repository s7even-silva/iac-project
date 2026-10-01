#!/bin/bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate geant4_env
cd "$(dirname "$0")"
V="python3 comparacion_mallas_y_mapas.py"
# T1: malla vs offset, sin campo
$V T1 1778.28 0.0 0 elmer 201 30000 7
$V T1 1778.28 1.0 0 elmer 201 30000 7
# T2b: reproduccion con apuntado radial (historico)
$V T2rad 562.341 0.0 1 elmer 301 5000 7 radial
$V T2rad 562.341 0.0 1 bs    301 5000 7 radial
# T2: Biot-Savart vs Elmer, ley coseno, mismas semillas
for s in 401 411 421; do
  $V T2 562.341 0.0 1 elmer $s 40000 7
  $V T2 562.341 0.0 1 bs    $s 40000 7
done
echo ALL_DONE
