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

## Workflow completo con gates (recomendado para uso normal)

```bash
# Primera vez, arranca en Fase 7:
python3 pilots/run_pilot_workflow.py --n-seeds 3 --threads 20

# Ver el estado actual sin correr nada:
python3 pilots/run_pilot_workflow.py --status

# Retomar despues de revisar un gate a mano (ver instrucciones que
# imprime el propio orquestador al detenerse):
python3 pilots/run_pilot_workflow.py --continue-to fase8
```

**Qué hace:** corre `run_faseN.py` (que ya hace correr+analizar sin
intervención) para cada fase en secuencia. Después de cada una, lee el
veredicto que esa fase escribió (`pilots/results/state/faseN_estado.json`,
ver `pilot_state.py`) y decide:

- **`auto_continue`**: el propio plan da un umbral numérico y el
  resultado lo cumple claramente (solo pasa en Fase 8 y Fase 10, que sí
  tienen un número — ver más abajo) → sigue solo a la fase siguiente,
  sin parar.
- **`limitrofe` / `revisar` / `fallo`**: el plan pide explícitamente
  juicio humano en este caso (Fase 7 casi siempre cae aquí — el plan no
  fija un umbral para "SE_within compatible con s_between") → el
  orquestador **se detiene**, imprime el resumen + instrucciones exactas
  de cómo continuar, y termina (no bloquea el terminal esperando input).

Esto es deliberado, no una limitación: automatizar los 4 gates sin
excepción significaría inventar umbrales que el plan nunca definió (ver
la discusión del equipo al diseñar esto, 2026-09-19) — el objetivo era
que **dentro** de cada fase, correr y analizar no requiera intervención
manual, no que las 4 fases decidan solas algo que el plan dice
explícitamente que requiere revisión.

## Reanudar tras un corte (resume)

Los 4 scripts `run_faseN.py` escriben un `manifest.csv` corrida por
corrida (append inmediato, no al final) y son reanudables **por
diseño**, igual que `run_organ_sweep.py`: si la máquina se apaga, se
cierra la sesión, o el proceso se corta a mitad de camino (le pasó de
verdad a una corrida de Fase 8 el 2026-09-19, cortada por fin de sesión
con 22/24 corridas ya hechas), **no hace falta borrar nada ni correr de
nuevo desde cero**. Basta con volver a invocar el mismo script con el
mismo `--out-dir` que generó la corrida cortada:

```bash
# out_dir real de la corrida cortada, tal como lo imprimió el script al arrancar
python3 run_fase8_binning.py --combos "GCR_H/min" --n-events 200 --threads 4 \
  --out-dir results/fase8_binning_20260919T214722Z
```

El script carga el manifiesto existente, salta toda combinación que ya
tenga `exit_code == 0` registrado (imprime `-- YA HECHA (retomando), se
salta`), y solo corre lo que falta. El análisis final (CSV de resumen +
`faseN_estado.json`) se recalcula sobre el conjunto completo (corridas
viejas + nuevas), no solo sobre las nuevas.

**Detalles verificados, no solo diseñados:**

- Una corrida que falló (`exit_code != 0`, ej. crash de Geant4) **no**
  cuenta como hecha — se reintenta en el siguiente resume. Verificado con
  un caso real: un primer intento de resume falló instantáneamente en 2
  corridas por un bug de ruta relativa (ver abajo), dejando filas con
  `exit_code=1` en el manifiesto; el segundo intento las reintentó y las
  completó, y el análisis final las usó correctamente — el manifiesto
  queda con ambas filas (la fallida y la exitosa) porque es un log de
  solo-append, no un upsert, pero eso no afecta la corrección: `analyze()`
  siempre lee el `.out` final en disco por convención de nombre, no las
  filas del manifiesto.
- Usar `--out-dir` **sin** haber corrido antes con ese directorio
  simplemente empieza una corrida nueva ahí (no hace falta que exista).
- `--no-resume` fuerza rehacer todo desde cero aunque el directorio ya
  tenga corridas exitosas (mismo flag que `run_organ_sweep.py`).
- Si no se pasa `--out-dir` al script de una fase directamente (no al
  orquestador, ver más abajo), cada invocación crea un directorio nuevo
  con timestamp — para reanudar así, apuntar explícitamente al `--out-dir`
  que imprimió la corrida cortada (queda también en la ruta que reportan
  los logs).
- `--out-dir` debe existir dentro del checkout (relativo o absoluto, da
  igual — el script lo resuelve a ruta absoluta internamente); un
  `--out-dir` relativo **sí funcionaba mal antes de 2026-09-20** (rompía
  la ruta de las macros nuevas al correr Geant4 con otro directorio de
  trabajo, con un crash `-11` sin mensaje claro) — ya corregido en
  `pilot_common.resolve_out_dir()`.

**El orquestador (`run_pilot_workflow.py`) retoma solo, sin que le pases
`--out-dir`:** antes de correr cada fase, busca en `results/` el
directorio más reciente con el prefijo de esa fase que tenga
`manifest.csv` (`pilot_common.find_latest_out_dir()`) y, si existe, se lo
pasa automáticamente al script de esa fase — que salta lo ya hecho igual
que si se lo hubieras pasado a mano. No hace falta que el usuario
recuerde ni copie ningún directorio; basta con volver a invocar

```bash
python3 pilots/run_pilot_workflow.py --continue-to fase8 --combos "GCR_H/min" --n-events 200 --threads 4
```

y encuentra sola la corrida de Fase 8 cortada anteriormente (verificado:
`Resume automatico: retomando .../fase8_binning_<timestamp>/` seguido de
saltar las 24/24 combinaciones ya hechas). Para forzar una corrida nueva
desde cero (ignorando cualquier directorio anterior de esa fase), pasar
`--no-resume` — el orquestador lo detecta y no inyecta ningún
`--out-dir`, dejando que la fase cree uno nuevo con timestamp como
siempre. Pasar `--out-dir` explícito a mano también sigue funcionando
(tiene prioridad sobre la búsqueda automática).

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

## Fase 8 — Convergencia del binning energético

```bash
python3 pilots/run_fase8_binning.py
python3 pilots/run_fase8_binning.py --combos "GCR_He/min,SEP_p/min"
python3 pilots/run_fase8_binning.py --n-events 10000 --threads 20
```

**Qué hace:** por cada combinación `species/phase` (sin bin_index — corre
**todos** los bins), corre la grilla de 8 bins y la de 16 bins
(`energy_bins.build_bins(..., n_bins=16)`, ya soportado sin tocar ese
módulo), calcula `D_8`/`D_16` (dosis total, misma fórmula que
`aggregate_organ_doses.py`) y `epsilon_binning = |D_16-D_8|/|D_16|`.

**Alcance reducido respecto del plan completo** (documentado en el
docstring del script): el plan idealmente compara el *endpoint*
`eta_16` vs `eta_8` (necesita el caso "control", `field_scale=0`) — este
script compara `epsilon_binning` de la dosis absoluta como proxy, más
simple, suficiente para descartar 8 bins si ya falla ahí.

**Gate automatizable** — único de las 4 fases con un umbral 100% numérico
del plan (`B_8→16 ≤ 2.5 pp`): `auto_continue` si claramente cumple,
`revisar` si claramente no, `limitrofe` si está cerca del umbral (el plan
pide comprobar 16→32 en ese caso, no implementado todavía).

**Costo:** `n_combos × 24` corridas (8+16 bins). Con 3 combos: 72.

## Fase 9 — Calibración de M_b por bin

```bash
python3 pilots/run_fase9_calibracion_mb.py
python3 pilots/run_fase9_calibracion_mb.py --n-bins 16  # si Fase 8 dio 16
```

**Qué hace:** corre una corrida de **sondeo** (`--n-events-probe`, no el
`M_b` final) por cada bin de la malla ya congelada por Fase 8, mide
`sigma_b` (vía `SE_within`, el estimador ya validado en Fase 7),
`W_b` (peso físico, `energy_bins.py`) y `c_b` (costo real medido,
segundos/evento de *esta* máquina). Calcula `M_b ∝ |W_b|·σ_b/√c_b`
(fórmula del plan) y ordena los bins por su contribución a la varianza
total.

**Siempre termina en `revisar`** (nunca `auto_continue`) — el plan exige
explícitamente "documentar los `M_b` definitivos" como decisión de
equipo (depende del presupuesto de cómputo real disponible, no solo de
la fórmula).

**Costo:** `n_combos × n_bins` corridas de sondeo. Con 3 combos, 8 bins,
`n_events_probe=5000`: 24 corridas.

## Fase 10 — Piloto B: precisión del endpoint shield vs. control

```bash
python3 pilots/run_fase10_endpoint.py --m-b-csv pilots/results/fase9_calibracion_mb_XXXX/m_b_propuesto.csv
python3 pilots/run_fase10_endpoint.py --n-events 10000  # sin Fase 9 corrida, M_b parejo
```

**Qué hace:** corre **control** (`field_scale=0`, sin blindaje activo —
mismo mapa de campo, escalado a cero) y **shield** (`field_scale=1`,
diseño real) para cada bin, con los `M_b` de la Fase 9 (o un valor parejo
si no se corrió esa fase). Calcula `eta = 1 - D_shield/D_control`,
propaga `V(eta)` (fórmula del plan, asumiendo independencia — **sin
common random numbers todavía**, ver docstring del script) y compara
`H_eta,95` contra `delta_eta/2 = 5 pp` (criterio ya fijado en Fase 1).

**Gate automatizable**: `auto_continue` si `H_eta,95 ≤ 5pp` en el peor
caso — señal de que los `M_b` alcanzan para producción. Si falla, el
plan prohíbe redefinir `delta_eta` — solo permite aumentar `M_b`
selectivamente en los bins que dominan la varianza.

**Costo:** `n_combos × n_bins × 2` (control+shield). Con 3 combos, 8
bins: 48 corridas.

## Módulos compartidos

- `pilot_common.py` — geometría/macro/parsing/streaming en vivo, usado
  por las 4 fases (extraído de `run_intrarun_pilot.py` al agregar las
  fases 8-10, para no duplicar ~200 líneas 3 veces).
- `pilot_state.py` — contrato `FaseResult`/`write_state`/`read_state`
  (JSON en `pilots/results/state/faseN_estado.json`) que usa el
  orquestador para decidir si avanza solo o se detiene.

## Semillas: sin colisión entre fases ni con producción

Cada fase reserva su propio rango vía `PHASE_SEED_OFFSET` (0 para Fase 7,
`10_000_000` para Fase 8, `20_000_000` para Fase 9, `30_000_000` para
Fase 10), sumado a `pilot_common.PILOT_BASE_SEED` — que a su vez es
distinto de `sweep_config.BASE_SEED_ACTIVE_SHIELD_SIM` (producción). Ver
el docstring de cada `seed_for()` para el detalle exacto de la fórmula.
