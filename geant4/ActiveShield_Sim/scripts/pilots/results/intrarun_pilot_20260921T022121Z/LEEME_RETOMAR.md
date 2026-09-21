# Retomar el piloto Fase 7 (SE_within vs s_between) en otra maquina

Esta rama (`results/fase7-intrarun`) solo guarda resultados parciales del piloto
`run_intrarun_pilot.py` (36 corridas: 3 combos x 3 seeds x M in 2500/5000/10000/20000),
lanzado con los defaults del script en el commit `06fa973` de `main`. No es codigo.
Se guardan `manifest.csv` y `checkpoints/*.out` (lo unico que necesita el resume); los logs no.

## Pasos
```bash
git checkout main && git pull origin main          # el script debe ser >= 06fa973
git fetch origin results/fase7-intrarun
git checkout origin/results/fase7-intrarun -- geant4/ActiveShield_Sim/scripts/pilots/results/intrarun_pilot_20260921T022121Z
git restore --staged geant4/ActiveShield_Sim/scripts/pilots/results/intrarun_pilot_20260921T022121Z
# necesita ActiveShield_Sim compilado con las columnas intra-run (Fase 7) y geant4_env activo
cd geant4/ActiveShield_Sim/scripts/pilots
python3 -u run_intrarun_pilot.py --threads <nucleos> \
  --out-dir results/intrarun_pilot_20260921T022121Z
```
- NO cambies `--combos`, `--n-seeds` ni el resto de defaults: las semillas dependen de ellos.
- El resume salta las corridas con `exit_code 0` en `manifest.csv` y sigue con las que faltan.
- Antes de retomar, comprueba que la rama tiene TODOS los `.out` que dice el manifest.
- Los `out_path` del manifest son rutas absolutas de la maquina original; el analisis las ignora
  y usa `checkpoints/run_<combo>_M<M>_seed<i>.out`.
