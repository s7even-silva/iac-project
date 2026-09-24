# Resultados de `run_organ_sweep.py`/`aggregate_organ_doses.py`

**Interpretación de los primeros resultados (rep0) contra límites de
protección radiológica reales, incluyendo el hallazgo de que el eje
central del arreglo de bobinas es la posición de MAYOR dosis, no la más
protegida:** ver
[`INTERPRETACION_PROTECCION_RADIOLOGICA.md`](INTERPRETACION_PROTECCION_RADIOLOGICA.md).

Este directorio junta los resultados reales del barrido por órgano de
`ActiveShield_Sim` (dosis absorbida/equivalente por órgano ICRP110, en
función de la posición radial del fantoma dentro de la nave) — ver
`AGENTS.md` para el diseño completo del barrido, el mecanismo de bins de
energía, y el cómputo distribuido que generó la mayoría de estos datos.

`.gitignore` excluye `resultados/` globalmente salvo los `.csv` de esta
carpeta (`!geant4/**/resultados/*.csv`) — el objetivo es versionar los
resultados finales de cómputo real, no archivos de scratch.

## Crudo, por persona/aporte (`_bryam` / futuros `_<nombre>`)

- **`resultados_organo_sweep_bryam.csv`** — salida cruda de
  `run_organ_sweep.py`: una fila por `(especie, bin_index, offset_x_m,
  repeticion, organo_id)`, con `edep_J` (energía depositada) y
  `n_eventos` de esa corrida. Es la fuente de la que se derivan todos
  los `resultados_organo_agregados_*.csv` — nunca se edita a mano.
- **`organ_sweep_manifest_bryam.csv`** — un renglón por corrida real
  (no por órgano): semillas, exit code, duración, rutas de log/macro.
  Sirve para auditar qué combinaciones se corrieron y cuándo, y es lo
  que usa `import_local_results.py` para marcar jobs como `done` en el
  coordinator sin volver a computarlos.
- **`resultados_organo_agregados_bryam.csv`** / **`resultados_riesgo_
  estocastico_bryam.csv`** / **`resultados_riesgo_estocastico_
  repeticiones_bryam.csv`** — mismo significado que sus contrapartes
  `_pooled_todas_las_reps`/`_rep0` de más abajo, pero calculados **solo
  sobre el aporte de Bryam** (el corte parcial que existía antes de
  tener el coordinator) — sufijo `_bryam` porque es el trabajo de una
  sola persona, igual criterio que `GCR_SEP_Sim` para repartir el
  barrido en equipo.

## Agregados actuales (todo el trabajo junto: local + coordinator)

Generados con `aggregate_organ_doses.py --results
'coordinator_raw/results/job_*/*/results.csv'` (o filtrando antes por
repetición, ver más abajo) sobre los 323 resultados descargados del
coordinator de producción (`results/job_{id}/...`), que ya incluyen
tanto el trabajo corrido por workers reales (Docker/local) como el
importado antes de existir el sistema distribuido
(`import_local_results.py --worker-label bryam/joel`) — no hace falta
buscar ese trabajo previo por separado, ya está adentro.

**Dos familias de archivos, con sufijo explícito para no confundirlas:**

### `_rep0` — solo la repetición 0, sin mezclar

- **`resultados_organo_agregados_rep0.csv`**
- **`resultados_riesgo_estocastico_rep0.csv`**
- **`resultados_riesgo_estocastico_repeticiones_rep0.csv`**

Calculados filtrando primero las filas de entrada a `repeticion == 0`
(la única repetición 100% completa hoy, 120/120 combinaciones `done`)
antes de correr el agregador — pedido explícito para tener un punto de
referencia limpio sin mezclar con repeticiones 1-4, que a la fecha
están parciales. Es el CSV a usar si quieres "los resultados de la
primera vuelta completa del barrido", sin nada más.

### `_pooled_todas_las_reps` — todas las repeticiones disponibles, sumando eventos

- **`resultados_organo_agregados_pooled.csv`**
- **`resultados_riesgo_estocastico_pooled_todas_las_reps.csv`**
- **`resultados_riesgo_estocastico_repeticiones_pooled_todas_las_reps.csv`**

Calculados sobre **todos** los resultados descargados, sin filtrar por
repetición — el agregado principal (`resultados_organo_agregados_
pooled.csv`, `resultados_riesgo_estocastico_pooled_todas_las_reps.csv`)
**suma eventos de Monte Carlo entre repeticiones** para dar el mejor
punto estimado posible con los datos que hay (más eventos = menos
ruido estadístico), sin importar que algunas repeticiones estén
incompletas — es una vista de "mejor estimación puntual", no de barra
de error.

**El archivo de repeticiones (`_repeticiones_pooled_todas_las_reps.csv`)
es distinto: da media/std/SEM/IC95%/CV *entre* repeticiones** (cada
repetición combinada por separado, no pooled) — su columna
`n_repeticiones` cuenta, por cada fila `(categoría, offset_x_m)`,
cuántas repeticiones estaban **genuinamente completas** para esa
combinación (todas las 8 especies×bins presentes), nunca una
repetición parcial rellenada a medias. Con los datos de hoy (solo rep0
completa, rep1-3 parciales) esto da `n_repeticiones=1` en todas las
filas, con std/SEM/IC95%/CV en blanco — matemáticamente no hay barra de
error que calcular con una sola repetición completa. Cuando las
repeticiones 1-4 terminen del todo, volver a correr el mismo comando
sobre el conjunto completo dará la barra de error real de hasta 5
repeticiones.

**Bug real corregido (2026-09-15, ver AGENTS.md):** antes de este
cambio, este archivo contaba una repetición como válida aunque le
faltaran combinaciones — mezclando repeticiones con cobertura desigual
sin avisar y reportando `n_repeticiones=4` de forma engañosa. Los CSV
de esta carpeta ya reflejan el fix; si ves un `resultados_organo_
agregados_completo.csv` o `resultados_riesgo_estocastico.csv` **sin
sufijo** en algún backup viejo, son de ANTES del fix — no usarlos.

## Columnas

**`resultados_organo_sweep_*.csv` / `rep0_only_results.csv` (crudo, por órgano):**
`especie` (GCR_H/GCR_He/SEP_p), `fase` (min/max, solar), `bin_index`
(0-7, bin de energía), `energy_mev` (MeV/nucleón, ver AGENTS.md sobre el
factor ×A para GCR_He), `offset_x_m` (posición radial del fantoma, 0-4),
`repeticion` (0-4), `organo_id` (ver más abajo), `edep_J` (energía
depositada en ese órgano, Joules), `dose_gy_run` (edep/masa de esa
corrida específica, sin normalizar por flujo real), `n_eventos`.

**`resultados_organo_agregados_*.csv` (por órgano, sin agrupar):**
`organo_id`, `offset_x_m`, `D_absorbida_GCR_Gy_dia` (dosis absorbida
real, GCR, Gy/día — el flujo de OLTARIS ya viene por día),
`D_equivalente_GCR_Sv_dia` (ponderada por `w_R`, Sv/día),
`D_absorbida_SEP_Gy_evento`/`D_equivalente_SEP_Sv_evento` (mismo par
para SEP, pero por evento completo — Oct 1989, no por día: semántica
temporal distinta de GCR, ver AGENTS.md). GCR y SEP nunca se suman entre
sí.

**`organo_id`**: índice que usa el scorer de Geant4
(`ICRP110UserScoreWriter.cc`) sobre los voxels del fantoma —
`organo_id=0` es **aire** (fuera de cualquier tejido segmentado, dosis
0 es el resultado físico correcto ahí, no un error) y `organo_id=141`
es la capa de piel superior/inferior del fantoma. Para `organo_id`
1-140, el nombre real está en `build/ICRPdata/ICRP110_g4dat/P110_data_
V1.2/AM/AM_organs.dat` en la línea `organo_id - 1` (el desplazamiento
de 1 es por el aire insertado en el índice 0 antes de leer ese
archivo) — ej. `organo_id=111` → línea 110 → "Oesophagus". El fantoma
es **masculino** (`AM`, adult male) — órganos exclusivamente femeninos
(ovarios, útero) existen como `organo_id` en la tabla pero dan dosis 0
en las corridas porque ese tejido no está presente en el fantoma
masculino real.

**`resultados_riesgo_estocastico*.csv` (6 categorías ICRP103, `w_T=0.12`):**
`categoria` (colon, lung, stomach, breast, red_bone_marrow,
remainder_tissues — cada una agrupa varios `organo_id` reales
ponderados por masa, ver AGENTS.md para el detalle de qué se excluye
como "contents" transitorio y cómo se calcula médula ósea roja),
`masa_kg` (masa total de esa categoría en el fantoma), mismas columnas
de dosis que el agregado por órgano.

**`resultados_riesgo_estocastico_repeticiones*.csv` (estadística entre
repeticiones):** `categoria`, `offset_x_m`, `n_repeticiones` (cuántas
repeticiones completas entraron en ESA fila — ver la explicación de
arriba), y por cada especie (GCR/SEP): `_media`, `_std` (desviación
estándar muestral), `_sem` (error estándar de la media), `_ic95_low`/
`_ic95_high` (intervalo de confianza 95%, t de Student), `_cv_pct`
(coeficiente de variación, %). Vacío cuando `n_repeticiones < 2` — no
hay std que calcular con una sola muestra.

## Cómo regenerar

```bash
# Bajar todo lo que hay en el coordinator de producción (ver AGENTS.md,
# infra/README.md para acceso a la VM):
mkdir -p coordinator_raw
tar -xzf coordinator_results.tar.gz -C coordinator_raw   # ya descargado de la VM

# Todo lo disponible, pooled (mejor punto estimado, sin filtrar repetición):
python3 ../scripts/aggregate_organ_doses.py \
  --results "coordinator_raw/results/job_*/*/results.csv" \
  --out resultados_organo_agregados_pooled.csv
# (esto tambien escribe resultados_riesgo_estocastico_pooled_todas_las_reps.csv
#  y su _repeticiones -- renombrar el archivo sin sufijo tras correrlo)

# Solo una repetición específica (ej. rep0), sin mezclar con otras:
python3 -c "
import csv, glob
rows, header = [], None
for f in glob.glob('coordinator_raw/results/job_*/*/results.csv'):
    with open(f, newline='') as fh:
        r = csv.DictReader(fh)
        header = header or r.fieldnames
        rows += [row for row in r if int(row['repeticion']) == 0]
with open('rep0_only_results.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=header); w.writeheader(); w.writerows(rows)
"
python3 ../scripts/aggregate_organ_doses.py \
  --results rep0_only_results.csv \
  --out resultados_organo_agregados_rep0.csv
```
