> Bitácora nueva (2026-09-16/17), no extraída de una versión anterior de
> `AGENTS.md`. Resume una discusión operativa/metodológica sobre cuántas
> repeticiones (`--repeats`) y qué escenarios físicos hacen falta en el
> barrido de `run_organ_sweep.py`. **Nada de esto es una decisión cerrada
> del equipo todavía** — son hallazgos, cálculos y recomendaciones sobre
> los que el equipo tiene que decidir; ver "Pendiente real" al final.

## Por qué surge esto

Administrando el coordinator en producción se preguntó por qué el barrido
usa **5 repeticiones** por combinación (`120 combinaciones × 5 = 600
corridas`). Se revisó el código (`run_organ_sweep.py`,
`aggregate_organ_doses.py`, `replicate_repeats.py`) y **no existe ninguna
justificación estadística documentada** — "5" aparece solo como el
ejemplo del docstring y como default de `replicate_repeats.py --repeats
4` (rep0 base + 4 = 5). Es una decisión práctica de equipo, no derivada de
un cálculo de tamaño de muestra ni de un objetivo de precisión.

## Marco estadístico aplicable

Cada repetición es una corrida Monte Carlo independiente (semilla
`BASE_SEED + 1000·rep + 2·index`, ambos parámetros de CLHEP). Con N
repeticiones de la dosis equivalente $D_i$:

$$\text{IC95\%} = \bar D \pm t_{0.975,\,N-1} \cdot \frac{s}{\sqrt N}$$

Tabla de $t$ de Student (dos colas, 95%) y el factor semiancho/std
resultante:

| N | df | $t_{0.975}$ | factor semiancho ($t/\sqrt N$) | vs. N=5 |
|---|---|---|---|---|
| 2 | 1 | 12.706 | 8.984 | 7.2x más ancho |
| 3 | 2 | 4.303 | 2.484 | 2.0x más ancho |
| 5 | 4 | 2.776 | 1.241 | referencia |
| 10 | 9 | 2.262 | 0.715 | ~0.58x |
| 30 | 29 | 2.045 | 0.373 | ~0.30x |

**N=2 es estadísticamente débil** (IC ~7x más ancho que N=5, y la propia
estimación de $s$ con 2 puntos es muy inestable). N=3 ya es razonable
(2x más ancho que N=5, no catastrófico). Rendimientos decrecientes claros
entre N=5 y N=30.

## Hallazgo real en el código: las repeticiones no se pueden mezclar por bin

`aggregate_organ_doses.py` (vista `resultados_riesgo_estocastico_repeticiones.csv`)
solo cuenta una repetición para el IC de una fila `(categoría, offset)` si
**las 24 combinaciones** (3 especies × 8 bins) de ese offset están
completas en esa repetición — si falta una sola (ej. GCR_He bin7), la
repetición entera se descarta para esa fila, aunque el resto de bins ya
tuviera 5 repeticiones completas. **Consecuencia:** no se puede dar "N=3
solo a los bins pesados y N=5 al resto" y esperar que el IC final use N=5
en la parte barata — el N efectivo colapsa al mínimo común de todos los
bins de esa especie/offset. Si se quiere un N distinto por bin, hay que
cambiar `aggregate_organ_doses.py` para propagar incertidumbre término a
término (`combine_bins()` ponderado con su propio N por `(especie,bin)`),
no exigir repetición completa — no implementado.

**Verificado en datos reales (2026-09-16):** con el estado de la cola de
ese momento, `resultados_riesgo_estocastico_repeticiones_pooled_todas_las_reps.csv`
daba `n_repeticiones=1` en las 42 filas — **ninguna combinación tenía
todavía 2 repeticiones completas**, así que el criterio de precisión de
abajo no se podía aplicar aún con datos reales.

## Aporte externo: MC convergence / batch means (resumen y matiz para este proyecto)

Se recibió una recomendación externa (fuera de este repo) con buenos
puntos de estadística de Monte Carlo, resumidos y adaptados aquí:

- El ruido MC de una corrida escala como $1/\sqrt{N_{eventos}}$. Para una
  publicación, no hace falta N=30 repeticiones si se puede *demostrar*
  que el IC ya es angosto frente a la diferencia científicamente
  relevante — más fuerte que justificar un N fijo en abstracto.
- Peligro de **optional stopping**: decidir N mirando continuamente los
  resultados hasta que "se vea bien" sesga la conclusión. Hay que fijar
  el criterio de precisión (ej. "aceptamos N si el semiancho del IC95%
  es menor al X% de la dosis media") **antes** de mirar el primer IC
  real, no después.
- Sugerencia: usar las repeticiones existentes como *batches* y, variando
  también `n_events`, mostrar empíricamente que $\sigma \propto
  1/\sqrt{N_{eventos}}$ — una figura de convergencia es un argumento
  metodológico más fuerte que "elegimos 5 porque alcanza".

**Matiz importante para este proyecto, no mencionado en el consejo
externo:** en Geant4 (transporte partícula por partícula) el costo de
cómputo escala ~linealmente con `n_events`, igual que con el número de
repeticiones — el costo total es aproximadamente
$N_{eventos} \times N_{repeticiones} \times \text{costo/evento}$,
**independiente de cómo se reparta el producto**. "Más eventos, menos
repeticiones" NO ahorra cómputo total en este proyecto (a diferencia de
otros contextos de MC donde sí puede ahorrar) — la única excepción es el
overhead fijo por corrida (inicialización de geometría/`coilGeometry`,
~10-24s medido en los bins baratos), insignificante frente a los bins
caros (GCR_He bin6/7, horas) que son los que más pesan en el presupuesto
real. Conclusión: el valor de este enfoque para este proyecto es
**metodológico/de credibilidad** (demostrar convergencia esperada, dar un
criterio no arbitrario), no una forma de reducir el costo de cómputo que
ya tienen restringido.

**Experimento de convergencia propuesto (barato, no implementado
todavía):** por cada combinación especie/fase (ver sección siguiente, hasta
6 grupos), correr 1 combo representativo con `n_events` = 2500/5000/10000/
20000 y 3 semillas por nivel (12 corridas chicas por grupo, ~72 en total
si se hacen los 6) y graficar el std entre semillas vs. `n_events` —
confirma o refuta el comportamiento esperado, y en particular si
SEP_p-mínimo (evento históricamente más chico, posible distribución de
dosis más *spiky*/cola pesada) necesita más eventos/repeticiones que los
demás grupos para converger igual de bien.

## Contexto que motivó la pregunta: expansión a 6 combinaciones especie/fase

Aparte de la pregunta de "cuántas repeticiones", surgió una pregunta de
**alcance**: el barrido de producción (`SPECIES_PHASE` en
`run_organ_sweep.py`) usa hoy **solo 3 combinaciones especie/fase** — el
caso más peligroso por especie (`GCR_H: min, GCR_He: min, SEP_p: max`) —
de las **4 combinaciones físicas reales** que dan los 6 CSV de OLTARIS
(GCR mínimo/máximo solar, SEP máximo=Oct1989/mínimo=Feb1956-LaRC). Esto
**no es un bug**: fue una decisión de alcance explícita del 2026-09-10
("Ronda 1" del análisis de riesgo estocástico, priorizar el peor caso por
especie) documentada en `docs/bitacora/activeshield_sim_historia.md` y en
`geant4/ActiveShield_Sim/README.md` línea ~231 — pero nunca se revisó si
expandirla, y el equipo ahora (2026-09-17) indica que sí necesita los 6
casos (GCR mín/máx × SEP máx/mín) para el paper.

**Verificado 2026-09-17: la expansión todavía NO está implementada** —
`SPECIES_PHASE` sigue con las 3 entradas de siempre en el código de
producción. Falta, como mínimo:

- `run_organ_sweep.py`: generalizar `SPECIES_PHASE` a 6 pares
  `(especie, fase)` y agregar un filtro `--only-phase` (hoy solo filtra
  por especie/bin/posición).
- `energy_bins.py`: generalizar `SPECIES_RANGE` (hoy 3 entradas, un CSV
  fijo por especie) a 6, y reconfirmar que el rango >99.9% de flujo/
  fluencia siga siendo válido para los espectros de máximo/mínimo que
  todavía no se usaron en este pipeline (GCR máximo, SEP mínimo).
- `infra/coordinator/db.py`: columna `phase` nueva en `jobs` (con
  migración idempotente, mismo patrón que `cpu_score`/`connected_s`), y
  el `UNIQUE(species, bin_index, offset_x_m, repeticion)` tiene que
  incluir `phase` — si no, `GCR_H-mínimo-bin3-offset0-rep0` y
  `GCR_H-máximo-bin3-offset0-rep0` colisionarían como el mismo job.
- `infra/worker/worker.py` (`build_command()`): pasar `--only-phase` al
  invocar `run_organ_sweep.py`.
- `seed_full_sweep.py`/`aggregate_organ_doses.py`: generar/agregar los 6
  grupos en vez de 3 (el CSV de resultados de `run_organ_sweep.py` ya
  trae una columna `fase` por fila, eso ayuda a `aggregate_organ_doses.py`
  a distinguir sin cambios de formato de salida).
- **Imagen Docker nueva** — el worker corre el código empaquetado en la
  imagen (`COPY . .` del Dockerfile); el cambio de scripts Python no le
  llega a ningún worker Docker hasta reconstruir/publicar y que cada
  worker actualice (y recordar que `tania` no puede auto-actualizarse
  hoy por el gap de socket de Podman, ver `infra/OPERATIONS_LOG.md`).
  Workers sin Docker (`bryam-local`, vía `GUIA_WORKER_LOCAL.md`) solo
  necesitan `git pull` — el binario C++ no cambia (`/gun/phase max|min`
  ya existe como comando, no hace falta recompilar).

## Recomendación (no decidida por el equipo todavía)

Combinando ambos hilos — precisión estadística y alcance de 6 casos —,
la sugerencia sobre la mesa (pendiente de aprobación del equipo) es:

- **Mantener N=5 para los 3 casos ya en curso** (GCR_H-mín, GCR_He-mín,
  SEP_p-máx) — costo hundido, es el resultado principal del paper, no
  vale la pena bajarle precisión ahora.
- **N=3 como default para los 3 casos nuevos** (GCR_H-máx, GCR_He-máx,
  SEP_p-mín), ajustado según el experimento de convergencia — si
  SEP_p-mínimo sale más ruidoso que los demás, subir su N puntualmente,
  no el de los otros 5 grupos.
- Costo resultante: 600 (actual) + 120×3=360 (nuevos) = **960 corridas**,
  contra 1200 de aplicar N=5 uniforme a los 6 grupos, y contra 480 de una
  propuesta alternativa (N=2 uniforme) que se descartó por ser
  estadísticamente débil (ver tabla de arriba).

## Pendiente real (nada de esto está cerrado)

1. **Fijar el criterio de precisión/IC objetivo del paper ANTES de
   decidir N final** — evitar optional stopping. Ejemplo de criterio a
   proponer: "aceptamos N si el semiancho del IC95% de
   `D_equivalente_..._Sv` es menor al X% de la media, para las
   categorías/posiciones que se comparan en el paper".
2. **Correr el experimento de convergencia** (barato, ~72 corridas para
   los 6 grupos) para validar $\sigma \propto 1/\sqrt{N_{eventos}}$ y
   detectar si algún grupo (sospecha: SEP_p-mínimo) necesita trato
   distinto.
3. **Decidir si de verdad se expande a 6 combinaciones especie/fase** y,
   si sí, implementar el soporte de `phase` (schema + scripts) antes de
   sembrar cualquier job nuevo — no implementado todavía (ver arriba).
4. Una vez que alguna combinación `(categoría, offset)` alcance N≥2 real
   con las 24 combinaciones completas, recalcular
   `resultados_riesgo_estocastico_repeticiones*.csv` y mirar el CV real
   antes de comprometerse a un N final.
