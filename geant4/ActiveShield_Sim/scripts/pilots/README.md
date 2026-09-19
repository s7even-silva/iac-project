# Pilotos del plan estadístico (Fases 7-10)

Scripts para las corridas puntuales de validación previas a producción
(ver `docs/bitacora/plan_estadistico.md`, sección "Secuencia de validación
y calibración antes de producción"). **No pasan por el coordinator ni la
cola de producción** — son trabajo puntual, no un barrido masivo, así que
se corren directo contra un `build/` ya compilado en la máquina que los
ejecute (decisión de equipo 2026-09-19: no vale la pena extender el
esquema del coordinator para esto).

Pensados para correr en una máquina de `cpu_score` alto (ver
`GET /api/v1/workers` del coordinator para ver qué máquina está online
ahora mismo con el mejor score) — los bins caros del barrido (ej.
`GCR_He bin6/7`) que en la máquina de referencia (`cpu_score=4.461`)
tardan horas, en una máquina de `cpu_score≈21` bajan a minutos.

## Requisitos

- `ActiveShield_Sim` compilado (ver `README.md` del proyecto raíz) **con
  el scorer instrumentado** (`ICRP110UserScoreWriter.cc` con los
  acumuladores S1/S2/N — si no lo tiene, el piloto falla rápido y
  explícito al arrancar, antes de invertir tiempo de cómputo).
- Entorno `geant4_env` activado (`conda activate geant4_env`) — mismo
  requisito que `run_organ_sweep.py`.
- `field/production/` ya presente en el checkout (versionado en git, no
  hace falta regenerarlo — ver `AGENTS.md`).

## Fase 7 — Piloto A: validación del estimador de incertidumbre intra-run

```bash
# Con los defaults (3 combinaciones representativas, 3 seeds por (combo,M)):
python3 pilots/run_intrarun_pilot.py

# Una combinación puntual, para probar rápido:
python3 pilots/run_intrarun_pilot.py --combos "GCR_H/min/2" --n-seeds 2

# Con todos los núcleos de una máquina rápida:
python3 pilots/run_intrarun_pilot.py --threads 20
```

**Qué hace:** por cada combinación `species/phase/bin_index`, corre 4
valores de `M` (2500, 5000, 10000, 20000 eventos), cada uno con
`--n-seeds` corridas **independientes** (semillas propias, deterministas).
De cada corrida extrae `SE_within` (calculado dentro de esa sola corrida,
vía los acumuladores S1/S2/N del scorer) y compara contra `s_between` (la
dispersión real entre las corridas independientes de ese mismo `M`).

**⚠️ Nota de diseño importante — leer antes de modificar el script:** la
primera versión de este piloto intentaba "checkpoints acumulados" (varios
`/run/beamOn` sucesivos en una sola sesión de macro, confiando en que
Geant4 acumulaba el scorer entre ellos). **Esa hipótesis era incorrecta**
— cada `/run/beamOn` inicia un `G4Run` nuevo e independiente en Geant4,
verificado con datos reales (el "edep total" de los "checkpoints" no era
monótono creciente, algo imposible si de verdad fuera acumulado). El
diseño actual usa una corrida independiente por cada `M`, no checkpoints
— ver el docstring completo de `run_intrarun_pilot.py` y la sección de
Fase 7 en `docs/bitacora/plan_estadistico.md` para el detalle completo del
hallazgo.

**Costo:** `n_combos × n_seeds × 4` corridas independientes. Con los
defaults (3 combos, 3 seeds) son 36 corridas. Tiempos reales de referencia
en `infra/coordinator/db.py` (`REFERENCE_TIMINGS_S`), escalados por el
`cpu_score` de la máquina — el caso más caro del default (`GCR_He bin6`)
ronda ~30 min en `cpu_score=4.461`, ~7 min en `cpu_score≈21`.

**Salida** (`pilots/results/intrarun_pilot_<timestamp UTC>/`):
- `manifest.csv` — una fila por corrida (semillas, exit code, duración).
- `logs/` — log completo de cada corrida (stdout de Geant4).
- `checkpoints/` — el `.out` crudo de cada corrida (pese al nombre del
  directorio, ya no son "checkpoints" en el sentido viejo — es solo dónde
  vive cada corrida independiente, un archivo por `(combo, M, seed)`).
- `resumen_por_organo.csv` — una fila por (combo, M, seed, órgano), con
  Edep/S1/S2/N/SE_run.
- `comparacion_se_within_vs_s_between.csv` — el resultado central: por
  cada (combo, M, órgano), la media de edep, `s_between` real, `SE_within`
  promedio, y su ratio.
- `convergencia_1_sobre_sqrtM.csv` — verificación de que `SE(M)·√M` sea
  aproximadamente constante entre los 4 valores de M.
- `reporte.txt` — resumen legible con el ratio agregado por M y la
  interpretación (ver el propio texto del reporte).

**Criterio de aceptación:** no hay un umbral numérico fijo todavía (ver
`docs/bitacora/plan_estadistico.md`, Fase 7 — "Si falla" — esto es
deliberado, el equipo revisa el reporte y decide). Lectura general:
- ratio ≈ 1.0 → `SE_within` predice bien la dispersión real, el diseño
  actual del scorer ("Camino B": S1/S2 agregados por voxel dentro de cada
  órgano) queda validado para usar `R=1` en producción.
- ratio << 1.0 → `SE_within` subestima la varianza real (evidencia de que
  la covarianza entre voxels del mismo evento importa) — no pasar a
  `R=1` sin el diseño más costoso (instrumentar `EndOfEventAction`,
  "Camino A", no implementado).
- ratio >> 1.0 → inesperado, investigar antes de continuar.

## Fases 8, 9, 10 — no implementadas todavía

Dependen del resultado real del Piloto A (ver la tabla de "Secuencia de
validación" en `docs/bitacora/plan_estadistico.md`) — se diseñan e
implementan después de tener un resultado real del Piloto A, no antes
(decisión de equipo 2026-09-19: el plan es secuencial, diseñar las fases
siguientes sobre un resultado que todavía no existe sería trabajo
especulativo).
