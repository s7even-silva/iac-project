# Incertidumbre de una sola corrida y su autodiagnóstico

**Fecha:** 2026-10-01.

**Estado:** método implementado y validado de forma exploratoria. La
validación formal es P2, en `plan_piloto.md`.

**Para quién:** el equipo y la sección de métodos del paper.

Este documento registra:
- cómo `ActiveShield_Sim` estima la incertidumbre estadística de una dosis
  con **una sola corrida**;
- cómo esa misma corrida decide si su incertidumbre es confiable;
- la evidencia de que el mecanismo funciona.

Todo lo que se cita es reproducible con los scripts y archivos de la
sección 7.

---

## 1. Problema

Hasta septiembre de 2026 cada punto del barrido se repetía 5 veces, y la
barra de error salía de la dispersión entre repeticiones. Eso tenía tres
problemas:
- cuesta 5 inicializaciones;
- con 5 valores, la desviación estándar es muy incierta;
- no había justificación formal para elegir 5 ([`validez_estadistica_runs.md`](https://github.com/s7even-silva/iac-project/blob/v1-archivo/docs/bitacora/validez_estadistica_runs.md), v1).

El primer intento de obtener el error desde una sola corrida fue el
«Camino B» (Fase 7). Sumaba por órgano las varianzas de cada vóxel, y así
ignoraba que un mismo evento deposita en muchos vóxeles a la vez
(covarianza positiva). Por eso subestimaba el error entre 2 y 9 veces
(sección 5.2).

## 2. Estimador por evento

### 2.1 Definiciones

Un evento de Geant4 es un primario. Sea M el número de eventos simulados
en la corrida, **incluidos los que no depositan nada**. Para una categoría
c, sea x_i la energía que deposita el evento i:

    x_i = Σ_o w_{c,o} · e_{i,o}

- e_{i,o} es la energía que deposita el evento i en el órgano o (suma
  sobre sus vóxeles, ponderada por el peso de traza).
- w_{c,o} es el peso del órgano en la categoría: 1 para los órganos de la
  categoría y la fracción de médula roja para los sitios de esponjosa.

Se acumulan las sumas de potencias S_k = Σ_i x_i^k, para k = 1…4.

    media por primario   x̄ = S1 / M
    varianza muestral    s² = (S2 − S1²/M) / (M − 1)
    error estándar       SE = sqrt(s² / M)
    dosis por primario   R = x̄ / m_c,  SE(R) = SE / m_c

m_c es la masa de la categoría: m_c = Σ_o w_{c,o}·m_o.

La clave es que x_i se forma **sumando dentro del evento antes de
elevar al cuadrado**. Así S2 incluye las covarianzas entre vóxeles y entre
órganos de la categoría, y s² estima sin sesgo la varianza de x cuando los
eventos son independientes y la varianza es finita.

### 2.2 Independencia de los eventos

En Geant4 multihilo, el hilo maestro genera las semillas de cada evento a
partir de la semilla de la corrida. Por eso los eventos son realizaciones
independientes, sin importar en qué hilo corren. Ver el
[modelo MT de Geant4](https://geant4.web.cern.ch/documentation/pipelines/master/bftd_html/ForToolkitDeveloper/OOAnalysisDesign/Multithreading/mt.html).

La independencia también se verificó empíricamente:
- **Por lotes:** al partir una corrida en lotes contiguos, intercalados o
  aleatorios por `event_id`, la dispersión entre lotes es la misma
  (sección 5.3).
- **Entre semillas:** se compararon 10 corridas con semillas distintas
  (sección 5.2).

### 2.3 Implementación

El código está en `geant4/ActiveShield_Sim/src/EventStatsRunAction.cc` y
se controla con los comandos `/eventStats/*`.

**Acumulación por evento:**
- `EventStatsRun::RecordEvent` lee el mapa de hits **del evento** de la
  malla de scoring `PhantomMesh/energyDeposit`, antes de que el
  `G4ScoringManager` lo acumule.
- Traduce cada vóxel a su órgano con los mismos archivos de ICRP 110 que
  `ICRP110UserScoreWriter`, suma por órgano y luego por categoría, y
  actualiza S1…S4.
- También actualiza el número de eventos con depósito (`n_nonzero`) y el
  mayor x_i con su `event_id`.

**Fusión de hilos y checkpoints:**
- Los acumuladores de cada hilo se suman en `G4Run::Merge`.
- Hay un acumulador por tramo de `event_id`, y los checkpoints M_k son
  acumulados («eventos con id < M_k»). Así no dependen de cómo se
  repartan los eventos entre hilos.

**Categorías:** salen de `scripts/write_event_categories.py`, la misma
definición que usa `aggregate_organ_doses.py`, para no tener dos fuentes de
verdad.

**Salidas adicionales:**
- Totales por evento de cada categoría (`perEventFile`), para la
  covarianza escudo/control con semillas comunes.
- Número de trazas cortadas por el límite de longitud del
  `MagnetEnvelope`.

**Exactitud (test T4, ctest `event_stats`):**
- S1 por órgano coincide con `ICRP110.out`.
- S1…S4 y `n_nonzero` coinciden con los recalculados desde el archivo por
  evento, con un error relativo de 1e-12.
- La VOV coincide con la recalculada.
- Los checkpoints son acumulados.

## 3. Autodiagnóstico: cuándo es confiable el SE de una corrida

En promedio, s² no tiene sesgo. Pero una corrida individual puede no
contener los eventos raros y grandes que dominan la varianza. En ese caso
**subestima** su SE y su IC95 no cubre el valor verdadero. Esto pasa con
colas pesadas: órganos chicos, energías cerca del corte del casco y
fragmentación.

Cada corrida reporta, por categoría y checkpoint, tres diagnósticos:

1. **VOV**, la varianza relativa de la varianza:

       VOV = (S4 − 4·S1·S3/M + 6·S1²·S2/M² − 3·S1⁴/M³) / (S2 − S1²/M)² − 1/M

   Es la usada en MCNP desde los «diez chequeos estadísticos» de Forster,
   Pederson y Booth. Depende de los momentos tercero y cuarto, así que
   reacciona a los eventos grandes y raros mucho antes que el error
   relativo. Debería decrecer como 1/M. **El criterio VOV < 0.1 viene de
   esa literatura y se fijó antes de mirar nuestros datos.**
2. **`n_nonzero`**, el número de eventos con depósito en la categoría.
3. **`max_J / S1`**, la fracción del total que aporta el mayor evento.

**Regla propuesta.** El SE de una corrida es utilizable para una categoría
si se cumplen dos condiciones:
- **VOV < 0.1**;
- **`n_nonzero` ≥ N_min**. El candidato es N_min ≈ 200; se eligió
  **después** de ver los datos de la sección 5.3, así que tiene que
  confirmarse con datos nuevos en P2 y no puede presentarse como validado.

Si una categoría no las cumple, se agregan eventos a la misma corrida; con
los checkpoints se ve si la VOV baja como 1/M. No se agregan repeticiones.
**Las repeticiones no compran precisión:** la precisión depende del total
de eventos, y una corrida de R·M eventos equivale a R corridas de M.

## 4. Diseño de la validación

Las métricas se definieron antes de correr; el diseño está en el docstring
de cada script. Para un conjunto de K «corridas» independientes de M
eventos:

- **ρ = sqrt(media_k SE_k²) / SD_k(x̄_k).** Compara el error que predice
  una corrida con la dispersión real entre corridas. Debería valer 1. El
  IC95 de ρ sale de χ² con K−1 grados de libertad, suponiendo normalidad
  de las medias, por la [aproximación de Wilson-Hilferty](https://www.itl.nist.gov/div898/handbook/prc/section2/prc231.htm).
  Con colas pesadas, ese IC es optimista.
- **Cobertura:** fracción de corridas cuyo IC95 normal (x̄_k ± 1.96·SE_k)
  contiene la media de las **otras** K−1 corridas. Aun con un SE exacto,
  su valor esperado es 2Φ(1.96/sqrt(1+1/(K−1))) − 1: 0.933 con K=8 y
  0.948 con K=80. Se reporta junto al valor observado.
- **Subestimación grave:** fracción de corridas con SE_k < ½·SD real.

Las «corridas» se obtuvieron de dos maneras:
- (a) semillas independientes, con una inicialización de Geant4 cada una;
- (b) una corrida grande partida por `event_id` en K lotes disjuntos de
  M eventos. Es equivalente por la independencia de la sección 2.2 y
  permite K grande sin pagar K inicializaciones.

## 5. Resultados

Configuración común:
- Geant4 11.4.2, physics list `Shielding`, fantoma AM (ICRP 110) completo.
- Fuente isótropa con ley coseno sobre una esfera de radio ≈1.37–1.39 m,
  dentro de una nave reducida (radio 0.6 m, semilongitud 1.0 m).
- Sin bobinas ni campo, fantoma en x=0.
- Código: commit `57fa5d1` (rama `plan-piloto-scorer-por-evento`).
  - Las corridas de las secciones 5.2–5.3 se hicieron con el mismo scorer
    antes de agregar S3/S4/VOV al C++.
  - La VOV de la sección 5.4 se calculó en Python desde los totales por
    evento, con la misma fórmula; T4 verifica que coincida con la del C++.

### 5.1 Exactitud de la implementación

Test T4 aprobado (sección 2.3).

### 5.2 Semillas independientes (`prueba_atajo_intrarun.py`)

GCR_H de 1778 MeV, casco de 0.001 cm, K=10 semillas de M=20 000 eventos.

| Categoría | n_nonzero por corrida | ρ scorer por evento [IC95] | ρ Camino B |
|---|---|---|---|
| total_body | 1376 | 0.86 [0.47, 1.25] | 0.11 |
| remainder_tissues | 1190 | 0.95 [0.52, 1.38] | 0.17 |
| red_bone_marrow | 489 | 0.95 [0.52, 1.38] | 0.28 |
| lung | 162 | 1.33 [0.73, 1.94] | 0.34 |
| colon | 96 | 1.04 [0.57, 1.51] | 0.46 |
| stomach | 44 | 0.86 [0.47, 1.25] | 0.34 |
| breast | 8 | 1.03 [0.56, 1.49] | 0.37 |

**Conclusión:**
- El estimador por evento es compatible con 1 en las 7 categorías.
- El Camino B subestima el error entre 2 y 9 veces.

### 5.3 Lotes en casos difíciles (`prueba_lotes.py`)

Casco real de 1.5 cm de Al, que conserva el corte en ~65 MeV y los
secundarios del casco.

| Caso | Partícula y energía | Eventos | Por qué es difícil |
|---|---|---|---|
| sep70_casco | p, 70 MeV | 4·10⁵ | Justo sobre el corte del casco: casi nada llega a órganos profundos |
| sep150_casco | p, 150 MeV | 4·10⁵ | Penetración parcial |
| he1000_casco | α, 1 GeV/n | 2·10⁵ | Fragmentación nuclear |
| h10000_casco | p, 10 GeV | 2·10⁵ | Cascadas hadrónicas |
| h10000_casco_rep | p, 10 GeV, otra semilla | 4·10⁵ | Réplica, agregada después de ver el caso anterior |

Lotes de M = 2500, 5000, 10 000, 20 000 y 50 000, con K ≥ 8. Selección con
M=5000 (todas las filas en `resultados/lotes_casco_2026-10-01.csv`):

| Caso | Categoría | K | n_nonzero/lote | Error relativo real | ρ [IC95] | Cobertura | SE < ½SD |
|---|---|---|---|---|---|---|---|
| sep70 | total_body | 80 | 259 | 0.064 | 1.03 [0.87, 1.19] | 0.93 | 0.00 |
| sep70 | lung | 80 | 0.9 | 5.2 | 1.01 [0.85, 1.17] | 0.25 | 0.96 |
| sep70 | red_bone_marrow | 80 | 3.5 | 1.5 | 0.94 [0.79, 1.09] | 0.45 | 0.66 |
| sep150 | total_body | 80 | 376 | 0.058 | 1.00 [0.84, 1.15] | 0.96 | 0.00 |
| sep150 | red_bone_marrow | 80 | 82 | 0.17 | 1.02 [0.86, 1.18] | 0.91 | 0.00 |
| sep150 | breast | 80 | 0.9 | 1.4 | 1.00 [0.84, 1.15] | 0.52 | 0.57 |
| he1000 | total_body | 40 | 580 | 0.064 | 1.05 [0.82, 1.28] | 0.97 | 0.00 |
| he1000 | red_bone_marrow | 40 | 162 | 0.12 | 1.11 [0.87, 1.36] | 0.95 | 0.00 |
| he1000 | lung | 40 | 56 | 0.27 | 0.79 [0.62, 0.97] | 0.82 | 0.05 |
| h10000 | total_body | 40 | 534 | 0.12 | 0.85 [0.66, 1.04] | 0.90 | 0.00 |
| h10000 rep. | total_body | 80 | 530 | 0.10 | 1.05 [0.88, 1.21] | 0.93 | 0.00 |
| h10000 rep. | red_bone_marrow | 80 | 171 | 0.23 | 0.96 [0.81, 1.11] | 0.86 | 0.03 |
| h10000 rep. | colon | 80 | 39 | 0.47 | 0.95 [0.81, 1.10] | 0.75 | 0.36 |

**Lectura:**
- **ρ es compatible con 1 en casi todos los casos y categorías,** incluso
  con menos de un evento con depósito por lote. Es lo esperable: s² no
  tiene sesgo y el promedio de SE² recupera la varianza.
- **La primera corrida de 10 GeV dio ρ = 0.65–0.85 en las categorías
  grandes.** Se investigó antes de aceptar o rechazar nada:
  - con lotes intercalados o aleatorios, la SD entre lotes volvió a
    0.90–1.07 de la teórica, frente a 1.22 con lotes contiguos;
  - la réplica con otra semilla dio ρ = 0.94–1.05 con cobertura de
    0.93–0.95.

  Se interpreta como una fluctuación. Se informa igual, porque el caso se
  agregó después de ver los datos.
- **La cobertura de una corrida individual cae cuando hay pocos eventos
  con depósito.** Ese es el fallo que el autodiagnóstico tiene que
  detectar.

### 5.4 Validación del autodiagnóstico (`prueba_lotes.py diagnose`)

Cada lote se trata como una corrida que se juzga a sí misma por su VOV y
su `n_nonzero`. Se agrupan todos los lotes de todos los casos, categorías
y M (`resultados/diagnostico_vov_casco_2026-10-01.csv`):

| Estrato | Lotes | Cobertura observada | Cobertura esperada con SE exacto | SE < ½SD |
|---|---|---|---|---|
| VOV < 0.1 | 2708 | 0.935 | 0.947 | 0.012 |
| VOV < 0.1 y n_nonzero ≥ 200 | 1632 | 0.943 | 0.946 | 0.003 |
| VOV < 0.1 y n_nonzero 50–199 | 856 | 0.921 | 0.948 | 0.022 |
| VOV < 0.1 y n_nonzero < 50 | 220 | 0.932 | 0.948 | 0.036 |
| VOV ≥ 0.1 | 5552 | 0.671 | 0.948 | 0.401 |
| VOV ≥ 0.1 y n_nonzero < 50 | 4551 | 0.623 | 0.948 | 0.467 |
| n_nonzero ≥ 200, sin mirar la VOV | 1870 | 0.944 | 0.946 | 0.003 |

**Conclusión:**
- **El criterio VOV < 0.1 de MCNP, fijado de antemano, separa las
  corridas confiables de las que no lo son.** Las que lo cumplen tienen una
  cobertura de 0.935 frente a 0.947 esperada, y solo el 1.2% subestima su
  SE a menos de la mitad. Las que no lo cumplen cubren 0.67 y el 40%
  subestima su SE a la mitad.
- Al agregar n_nonzero ≥ 200, la cobertura coincide con la esperada
  (0.943 frente a 0.946).
- En el estrato con VOV < 0.1 y 50–199 eventos con depósito queda una
  subcobertura de ~2.7 puntos. Por eso la regla propuesta combina ambos
  criterios.

## 6. Límites y pendientes (P2)

**Límites de esta validación:**
- **Configuración:** sin campo ni bobinas, en x=0, con una nave reducida y
  4 partículas/energías. El estimador es general (solo supone eventos
  independientes con varianza finita), pero la frecuencia de colas pesadas
  y el N_min necesario cambian con el campo, la posición y la geometría.
  Eso se confirma en P2 con la configuración de producción.
- **Lotes no independientes entre sí en la tabla 5.4:** las categorías
  comparten eventos y los distintos M comparten lotes. El número de lotes
  sobrestima el tamaño efectivo de la muestra, así que las cifras son
  descriptivas, no una prueba con nivel controlado.
- **N_min ≈ 200 es post hoc.** Hay que fijarlo (D4) y confirmarlo con
  corridas nuevas. Lo mismo vale para cualquier umbral sobre `max_J/S1`.
- **IC normal:** con asimetría fuerte, la cobertura de un IC simétrico
  puede quedar por debajo del valor nominal aun con un SE correcto. Con
  colas muy pesadas hay que considerar un IC asimétrico o una
  transformación.
- **Varianza infinita:** si la distribución de x tuviera varianza infinita
  (cola de potencia con exponente ≤ 3), ningún SE sería válido. La
  pendiente de la cola, el décimo chequeo de MCNP, no se calcula todavía.
  Se puede agregar a partir del archivo por evento.

**Pendientes antes de citar el método como validado (P2):**
1. Fijar D4: VOV < 0.1, N_min y, si se usa, el límite de `max_J/S1`.
2. Repetir la validación con campo, bobinas, la esfera de P1 y posiciones
   fuera del eje, con SEP, alfas y una energía alta, y un K dimensionado
   para la precisión buscada.
3. Integrar `/eventStats` en `run_organ_sweep.py` y en el protocolo del
   coordinator, para que cada trabajo reporte sus diagnósticos.

## 7. Reproducibilidad

Desde `geant4/ActiveShield_Sim/build`:

```bash
ctest -R event_stats                                    # T4/T5
python3 ../tests/scorer_por_evento/prueba_atajo_intrarun.py --out-dir OUT_A --seeds 10 --events 20000
for c in sep70_casco sep150_casco; do
  python3 ../tests/scorer_por_evento/prueba_lotes.py run --out-dir OUT_B --case $c --events 400000 --threads 2
done
for c in he1000_casco h10000_casco; do
  python3 ../tests/scorer_por_evento/prueba_lotes.py run --out-dir OUT_B --case $c --events 200000 --threads 2
done
python3 ../tests/scorer_por_evento/prueba_lotes.py run --out-dir OUT_B --case h10000_casco_rep --events 400000 --threads 7
python3 ../tests/scorer_por_evento/prueba_lotes.py analyze --out-dir OUT_B
python3 ../tests/scorer_por_evento/prueba_lotes.py diagnose --out-dir OUT_B
```

- Las semillas están fijas en cada script: `BASE_SEED` y `SEEDS`.
- Los resultados versionados están en
  `geant4/ActiveShield_Sim/tests/scorer_por_evento/resultados/`.
- Los resultados de corridas MT no son idénticos bit a bit entre máquinas
  (orden de las sumas). Las conclusiones no dependen de eso.

## 8. Texto propuesto para el paper (borrador)

> **Statistical uncertainty.** Organ and tissue doses were scored per
> primary history: for each event, the energy deposited in all voxels of a
> tissue (with red-marrow fractions for spongiosa) was summed before
> accumulating the first four power sums S1–S4 over all M simulated
> primaries, including those that deposited no energy. The standard error
> of the mean dose per primary was obtained from the sample variance of
> these per-history totals, which accounts for the correlation between
> voxels hit by the same history; summing per-voxel variances instead
> underestimated the standard error by factors of 2–9 in our tests. Each
> run assessed the reliability of its own standard error with the relative
> variance of the variance (VOV) and the number of histories with non-zero
> deposit, following the statistical checks of MCNP [Pederson et al.
> 1997]; a tissue estimate was accepted only if VOV < 0.1 and at least
> N_min histories contributed. We validated this procedure against the
> dispersion of independent runs (10 seeds) and of up to 160 disjoint
> batches of single long runs for protons (70 MeV–10 GeV) and helium
> (1 GeV/n): the ratio of predicted to observed standard deviation was
> consistent with unity, and runs passing the VOV criterion achieved
> 93.5% empirical coverage of nominal 95% intervals (94.7% expected for
> the leave-one-out reference), versus 67% for runs failing it.

N_min y las cifras finales se reemplazan con las de P2 antes de enviar.

## Referencias

- Pederson, S. P., Forster, R. A., Booth, T. E. (1997). *Confidence
  interval procedures for Monte Carlo transport simulations.* Nuclear
  Science and Engineering 127(1).
  [doi:10.13182/NSE97-A1921](https://www.tandfonline.com/doi/abs/10.13182/NSE97-A1921);
  [OSTI 411647](https://www.osti.gov/biblio/411647).
- Forster, R. A., Pederson, S. P., Booth, T. E. *Ten new checks to assess
  the statistical quality of Monte Carlo solutions in MCNP.*
  [OSTI 10120110](https://www.osti.gov/biblio/10120110-ten-new-checks-assess-statistical-quality-monte-carlo-solutions-mcnp).
- X-5 Monte Carlo Team. *MCNP — A General Monte Carlo N-Particle Transport
  Code, Version 5*, LA-UR-03-1987, cap. 2 (chequeos estadísticos, VOV).
  [PDF](https://mcnp.lanl.gov/pdf_files/TechReport_2003_LANL_LA-UR-03-1987Revised212008_SweezyBoothEtAl.pdf).
- [Geant4: modelo de multihilo y semillas por evento](https://geant4.web.cern.ch/documentation/pipelines/master/bftd_html/ForToolkitDeveloper/OOAnalysisDesign/Multithreading/mt.html).
- [NIST/SEMATECH e-Handbook, incertidumbre de la desviación estándar](https://www.itl.nist.gov/div898/handbook/prc/section2/prc231.htm).
