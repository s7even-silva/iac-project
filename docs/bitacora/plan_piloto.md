# Plan piloto previo al barrido corregido

La auditoría del 2026-09-30 (`auditoria_2026-09-30.md`) invalidó todas las
dosis de producción y de los pilotos anteriores. Este documento define los
pilotos que tienen que aprobarse **antes** de empezar el barrido nuevo.
Los detalles técnicos y de cálculo del barrido están en
[`plan_barrido.md`](plan_barrido.md).

**Reglas:**

1. Ninguna cifra de diseño (puntos de energía, eventos por punto, radio de
   la esfera, dominio del campo) es una decisión hasta que la apruebe su
   piloto.
2. Cada criterio de aceptación se fija **antes** de ver los datos del
   piloto, y no se cambia después de verlos.
3. Un resultado sin incertidumbre no aprueba nada. Si el intervalo es
   demasiado ancho, el resultado es inconcluso. Fijar de antemano tamaños
   y número de evaluaciones; si se amplía M según lo observado, usar una
   confirmación independiente de tamaño fijo o un método secuencial con
   cobertura controlada. Repetir IC95 hasta que uno apruebe no conserva 95%.
4. Las corridas de un piloto se pueden reutilizar en el barrido solo si se
   hicieron con la configuración ya congelada (regla de la Fase 10 de
   `plan_estadistico.md`).

## Verificaciones ya hechas (2026-09-30 y 2026-10-01)

| Verificación | Resultado |
|---|---|
| Monte Carlo independiente (Python) del algoritmo del generador, 4·10⁶ primarios, fluencia en esferas de 30 cm | Ley coseno: fluencia / [N/(πR²)] = 0.990, 1.014, 1.025 y 1.000 en x = 0, 1, 2 y 4 m (uniforme). Apuntado radial: 803, 24.6, 6.1 y 1.5 (inflado en todas las posiciones). |
| Normalización dentro de Geant4: cruces y longitud de traza de protones de 1778 MeV en una caja de 50 cm en x=1.5 m, sin casco ni bobinas ni campo, 10⁶ primarios, filtro 1000–1800 MeV | Cruces / esperado = **1.010 ± 0.020**; traza / esperada = 1.019. Con filtro estrecho (1770–1790 MeV) faltaba un 4%: primarios que interactúan y salen de la ventana. |
| Malla de scoring corregida: x=1 m frente a x=0, sin campo, ley coseno | 0.91 (~10% de incertidumbre), compatible con 1. Antes del arreglo era ~1/1000. |
| Dosis de cuerpo entero en el fantoma desnudo, protones de 1778 MeV | Con 10⁶ primarios: 8.25e-5 Gy/día, **1.72** veces la dosis de pura ionización (Bethe, 2.06 MeV·cm²/g). Con 4·10⁴ primarios: 1.83, compatible. La normalización está verificada, así que la diferencia probablemente viene de las interacciones nucleares. Se confirma en P0. |

Todos estos números son reproducibles con los macros y scripts de
`geant4/ActiveShield_Sim/tests/verificacion_fuente/` (ver su README).

## Decisiones bloqueantes (antes de cualquier piloto)

Cada decisión bloquea únicamente los pilotos indicados en su fila. D8 es
condicional al análisis temporal; no impide validar la dosis integrada.
Registrar también el control: para aislar el efecto magnético se conserva
la misma geometría/materiales con `fieldScale=0`; quitar bobinas compara
otro sistema y exige un contraste separado.

| # | Decisión | Qué bloquea |
|---|---|---|
| D1 | Ley coseno como modo de producción | Todo |
| D2 | Endpoint primario (por ejemplo, dosis efectiva o una categoría) y δ_η (el plan propone 10 pp) | P5, P6 |
| D3 | Presupuesto B de error de dosis por caso especie/fase y por categoría, para las pruebas de equivalencia | P1, P4, P5 |
| D4 | Umbrales de los diagnósticos de convergencia (fracción máxima de un solo evento, mínimo de eventos con depósito, rango aceptable de SE_within/s_between) | P2, P3 |
| D5 | Fantoma AF sí o no (dosis efectiva completa) | Diseño del barrido |
| D6 | Posiciones (las 5 actuales u otra elección) | P1, P6, barrido |
| D7 | Tolerancia con ICRP 116 para P0 | P0 |
| D8 | Perfil temporal de SEP: fuente de datos de cada evento (GOES para oct. 1989; feb. 1956 no tiene datos satelitales), forma del espectro variable o constante, y qué casos lo llevan (`plan_barrido.md`, sección 10) | Criterio temporal de P4 y tasa de dosis SEP; no bloquea la dosis del evento completo |

## Requisitos técnicos bloqueantes

Antes de los pilotos que los necesitan (detalle en `plan_barrido.md`):

- **Mapa de campo final (Elmer) con el dominio que fije P1. Es el
  bloqueante del camino crítico.** La esfera fuente actual (≈6.94 m) queda
  dentro del arreglo de bobinas (material hasta ≈10.5 m del centro), y el
  `.map` de producción se trunca en ±11.3/±13.3/±7.6 m con 0.16–0.40 T en
  sus caras. Para encerrar las bobinas, la esfera tiene que medir más de
  ≈10.5 m, y eso exige un mapa Elmer en un dominio mayor que el actual.
  Toda corrida con campo (P1 paso 3, P3, P4, P5, P6 y el barrido) depende
  de ese mapa y se invalida si el campo cambia después. Sin campo pueden
  avanzar P0 (fantoma desnudo), P2 (estimador) y los tests.
  **Requiere hardware que hoy no está asegurado:** el solve a escala real
  con padding 3.5 m tuvo un pico de 7.3 GB, y un dominio mayor necesitará
  más. La máquina de desarrollo actual tiene ~5 GB; los solves anteriores
  se hicieron en una de 15 GB + 11 GB de swap. Hay que asignar una máquina
  (o una VM temporal de memoria alta) antes de que P1 pueda cerrar.
- **Scorer por evento (R1):** S1/S2 por órgano y categoría con el total de
  cada evento, y N = todos los primarios (incluidos los que no depositan).
  Necesario para P2–P6.
- **Diagnósticos por punto:** eventos con depósito, mayor contribución de
  un solo evento y checkpoints de M. Necesario para P3.
- **Energía muestreada dentro de un estrato (R8):** necesario para la
  referencia de P4.
- **Totales por evento de las categorías (R12):** necesario para CRN en P6.
- **Q(L) y espectro de LET (R2), pesos (R5), contadores de trazas
  cortadas (R6), procedencia (R9):** necesarios antes de cualquier
  corrida reutilizable en el barrido.
- **Tests automáticos** de las verificaciones de arriba como regresión
  (`plan_barrido.md`, sección 8).

**Estado (2026-10-01).** Hechos:
- R1, los diagnósticos por punto, R12 y R6: comandos `/eventStats/*`; ver
  `plan_barrido.md`, sección 5.
- Tests T4/T5 (ctest `event_stats`) y T6/T7 (`tests/python`).

Pendientes:
- R2, R5, R8, R9;
- tests T1–T3 y T8–T12;
- la integración en el coordinator. La de `run_organ_sweep.py` ya está
  hecha (`--event-stats`).

## Pilotos

### P0 — Normalización absoluta contra una referencia externa

- **Objetivo:** confirmar que la dosis absoluta por unidad de fluencia es
  correcta, no solo la fluencia.
- **Diseño:** fantoma AM desnudo (sin casco, bobinas ni campo), fuente
  isótropa con ley coseno, protones y alfas en 4–6 energías entre
  100 MeV/n y 10 GeV/n.
- **Referencia:** coeficientes de conversión fluencia→dosis absorbida por
  órgano de ICRP 116, irradiación isótropa (ISO).
- **Métrica:** cociente simulado/ICRP por energía y órgano, con IC95.
- **Criterio:** IC95 completo del cociente dentro de `1 ± D7`, con órganos,
  energías y comparaciones primarias fijados antes de correr. Registrar la
  tabla ISO/AM exacta y sus unidades (dosis absorbida, no efectiva).
  ICRP 116 se calculó con otros
  códigos y physics lists; diferencias de este orden no implican error.
- **Resultado esperado:** acuerdo dentro de la tolerancia. La atribución
  del factor ~1.8 a interacciones nucleares es una hipótesis: requiere
  diagnóstico de procesos o una comparación física controlada y no es
  un resultado exigido al piloto.
- **Bloquea:** todo resultado absoluto. Si falla, hay un error de
  normalización o de física que resolver antes de seguir.

### P1 — Dominio del campo y radio de la esfera fuente

Decidido: se amplían. El piloto fija cuánto. Herramienta disponible
(2026-10-01): `/spacecraft/sourceSphereRadius <R> m` en Geant4, y
`aggregate_organ_doses.py --source-sphere-radius-m <R>` en el agregador
(los dos tienen que coincidir).

1. **Preselección:** un mapa Biot-Savart en un dominio grande da la cola
   ∫B⊥·dl fuera de cada radio candidato. Se descartan los radios donde esa
   cola puede desviar de forma apreciable a las partículas de menor
   rigidez de interés. **Hecha el 2026-10-01; ver «Resultado de la
   preselección» más abajo.**
2. **Elmer:** dominios crecientes. Comparar el campo interior entre ellos
   (efecto de la frontera `AV=0`; hoy Biot-Savart y Elmer difieren hasta
   un 40% hacia los extremos en z). Requiere una máquina con más de ~8 GB
   de RAM.
3. **Convergencia de la dosis:** x=0 y una posición fuera del eje, en las
   energías más sensibles al campo (cerca del corte del escudo), para
   R₁ < R₂ < R₃.

- **Criterio:** fijar por separado dominio/resolución del mapa, radio y
  límite de trazas; variar uno por vez y confirmar la configuración conjunta.
  Se acepta un radio si concuerda con los dos radios mayores probados,
  dentro del presupuesto D3. Todos deben encerrar los materiales y caber
  en el mundo. Hoy el límite de traza es proporcional al radio: variarlos
  juntos confundiría convergencia de la fuente con pérdida de trayectorias.
- **Resultado esperado:** un radio y un dominio documentados con sus datos
  de convergencia, más el mapa de campo final versionado con su hash.
- **Bloquea:** P3–P6 y el barrido. Cambiar el campo después invalida todo.

#### Resultado de la preselección (paso 1, 2026-10-01)

Script: `field/preselect_source_radius.py`. Resultados:
`field/studies/p1_preseleccion_radio_2026-10-01.json`.

**Configuración:**
- Campo Biot-Savart del arreglo CORC, evaluado de forma analítica en
  cualquier punto, sin dominio finito.
- Trayectorias de corriente regeneradas desde
  `field/production/crewhat_corc_array_config.json`. Reproducen
  `crewhat_niac_max.map` con un error relativo máximo de 4·10⁻¹³ en 300
  nodos.
- 1000 pares (P, d) por radio y rigidez, con P uniforme en la esfera y d
  según la ley coseno.
- Tarda unos 40 minutos con 6 procesos.

**Métrica.** La cola ∫B⊥·dl que proponía el plan no es el criterio
adecuado. Por el teorema de Liouville, una desviación fuera de R no altera
la intensidad isótropa en la esfera. Lo que introduce error es otra cosa:
que la trayectoria que llega a (P, d), trazada hacia atrás, no venga del
infinito. Hay dos casos:
- vuelve a cruzar la esfera, y entonces la fuente cuenta dos veces esa
  partícula;
- queda atrapada.

Se reporta la fracción de esos pares, con IC95 de Wilson. La cola
∫B⊥·dl queda en el JSON solo como referencia.

Bobinas (material) hasta **10.47 m** del centro.

| R (m) | ∫B⊥·dl mediana / p90 (T·m) | 12 MeV (0.15 GV) | 33 MeV (0.25 GV) | 67 MeV (0.36 GV) | 238 MeV (0.71 GV) | 831 MeV (1.5 GV) |
|---|---|---|---|---|---|---|
| 6.94 (actual) | 1.57 / 6.68 | 56% | 45% | 33% | 19% | 4.7% |
| 11 | 0.33 / 0.81 | 9.7% | 2.9% | 1.7% [1.1, 2.7] | 0.1% | 0 [0, 0.4] |
| 12 | 0.21 / 0.45 | 1.9% | 0.5% | 0.1% [0.0, 0.6] | 0 [0, 0.4] | 0 [0, 0.4] |
| 14 | 0.10 / 0.18 | 0.1% | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] |
| 16 | 0.05 / 0.09 | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] |
| 20 | 0.02 / 0.03 | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] |

Los valores son la fracción de pares (P, d) mal representados por la
fuente isótropa en R, con protones. Las rigideces se aplican también a
alfas: 0.71 GV equivale a ≈65 MeV/n. Todos los pares malos fueron
reentradas; solo 5 de 1000 quedaron atrapados, a 6.94 m y 0.15 GV.

**Lectura.**
- **6.94 m queda descartado.** Además de cortar las bobinas, representa
  mal un tercio de las direcciones a 67 MeV y un 5% incluso a 831 MeV.
- **11 m** está en el límite: encierra las bobinas por solo 0.5 m.
- **Candidatos para los pasos 2–3: 12, 14 y 16 m** (R₁ < R₂ < R₃). Elegir
  entre ellos corresponde a D3 y al paso 3, no a este paso.
- Bajo ~65 MeV los protones no atraviesan el casco de 1.5 cm de Al, así
  que la columna de 12 MeV es una cota conservadora.

**Implicaciones para el paso 2 (Elmer):**
- El mapa tiene que cubrir sin truncarse una esfera de 12–16 m, más el
  margen del `MagnetEnvelope`. Eso implica un semilado de al menos ~14–17 m
  **en z**, donde hoy es de 7.6 m.
- La frontera `AV=0` tiene que quedar más lejos todavía. Esto multiplica
  el volumen de la malla de aire frente al solve actual (pico de 7.3 GB).
  Por eso hace falta la máquina grande.
- Hay que subir `/spacecraft/worldHalfSize` (hoy 14 m) por encima de
  R + 0.5 m.
- El límite de traza (6R) crece con R. Variarlo por separado, como pide
  el criterio.

**Costo.** La fracción de primarios que tocan el fantoma cae como 1/R².
Con la sección media del fantoma, la fracción a 14 m es unas 4 veces menor
que a 6.94 m. Esto encarece P3 y hace más relevante P5 (sesgo de fuente).
Es una observación, no una decisión.

### P2 — Validación del estimador de incertidumbre por evento

Repite la Fase 7 con el scorer nuevo.

- **Diseño:** 3–4 combinaciones (incluidas SEP y una energía alta), 5
  semillas independientes por combinación, varios M.
- **Métrica:** para cada M por separado, `sqrt(media(SE_within²))` frente
  a `s_between` de las respuestas **por primario**, por órgano/categoría.
- **Criterio:** rango D4 e incertidumbre de la comparación predefinidos.
  Cinco semillas son una exploración, no garantizan una validación precisa
  de la varianza; dimensionar las semillas según la precisión del contraste.
- **Resultado esperado:** compatibilidad con 1. S2 por evento permite un
  estimador insesgado de la varianza bajo independencia y varianza finita;
  no hace exacta la varianza estimada ni valida automáticamente un IC normal.
- **Bloquea:** usar R=1. Si falla, investigar el scorer y las colas antes
  de elegir más repeticiones; no extrapolar el factor histórico 0.08/0.48.

#### Prueba inicial del atajo intra-run (2026-10-01, exploratoria, no es P2)

Script: `geant4/ActiveShield_Sim/tests/scorer_por_evento/prueba_atajo_intrarun.py`.
Resumen: `tests/scorer_por_evento/resultados/atajo_intrarun_K10_M20000_2026-10-01.csv`.
El diseño se fijó antes de correr, en el docstring del script.

**Diseño:**
- Fantoma AM desnudo, sin campo.
- Nave reducida (esfera fuente ≈1.37 m) para que ~7% de los primarios
  toquen el fantoma.
- GCR_H a 1778 MeV, ley coseno.
- K=10 semillas de M=20000 eventos cada una.
- ρ = sqrt(media SE²)/s_between, por categoría.
- IC95 de ρ ≈ ×[0.55, 1.45], por χ² con 9 g.l. y suponiendo normalidad.

| Categoría | Eventos con depósito por semilla | ρ scorer por evento [IC95] | ρ Camino B (histórico) |
|---|---|---|---|
| total_body | 1376 | 0.86 [0.47, 1.25] | 0.11 |
| remainder_tissues | 1190 | 0.95 [0.52, 1.38] | 0.17 |
| red_bone_marrow | 489 | 0.95 [0.52, 1.38] | 0.28 |
| lung | 162 | 1.33 [0.73, 1.94] | 0.34 |
| colon | 96 | 1.04 [0.57, 1.51] | 0.46 |
| stomach | 44 | 0.86 [0.47, 1.25] | 0.34 |
| breast | 8 | 1.03 [0.56, 1.49] | 0.37 |

**Lectura:**
- Con M=20000, los 7 IC del scorer por evento contienen 1.
- El Camino B subestima el SE entre 2 y 9 veces, por ignorar la
  correlación entre vóxeles del mismo evento. Su rango es compatible con el
  factor histórico 0.08/0.48 y confirma por qué había que abandonarlo.
- En el checkpoint M=5000, total_body da 0.63 [0.34, 0.92]. Es 1 de 14
  intervalos, no independientes entre sí. Con pocos eventos con depósito
  (~340), las colas pesan más.
- **No aprueba R=1:**
  - es un solo punto, sin campo y a una sola energía;
  - el IC solo detecta errores gruesos;
  - la aproximación χ² supone normalidad.

  P2 tiene que incluir SEP, energías bajas cerca del corte, la geometría
  con campo y un número de semillas dimensionado con D4.

#### Prueba por lotes en casos difíciles (2026-10-01, exploratoria)

> Método completo, autodiagnóstico por VOV (criterio de MCNP) y su
> validación: [`metodo_autodiagnostico_incertidumbre.md`](metodo_autodiagnostico_incertidumbre.md).
> Resultado clave: las corridas con VOV < 0.1 cubren el 93.5% (esperado
> 94.7%), y las que no lo cumplen, el 67%.

Script: `tests/scorer_por_evento/prueba_lotes.py`. Resumen:
`tests/scorer_por_evento/resultados/lotes_casco_2026-10-01.csv`.

**Método.** Una corrida grande se parte por `event_id` en K lotes
disjuntos de M eventos. Como los eventos son independientes, cada lote
equivale a una corrida de M eventos.

**Geometría.** Nave reducida con el casco real de 1.5 cm de Al, sin
bobinas ni campo.

**Casos:**
- SEP_p de 70 MeV (justo sobre el corte del casco) y de 150 MeV, con
  4·10⁵ eventos;
- GCR_He de 1 GeV/n, con 2·10⁵;
- GCR_H de 10 GeV, con 2·10⁵ más una réplica de 4·10⁵ con otra semilla.

**Resultado:**
- **El SE por evento no tiene sesgo.** En los 5 casos, ρ es compatible
  con 1, incluso con 0.2 eventos con depósito por lote.
- La primera corrida de 10 GeV dio ρ = 0.65–0.85 en las categorías
  grandes. La réplica dio 0.94–1.05 con cobertura de 0.94–0.95, así que
  fue una fluctuación.
- **Lo que limita el atajo es el número de eventos con depósito por
  corrida (`n_nonzero`) y el peso del mayor evento (`max_J/S1`).** El
  promedio no tiene sesgo, pero una corrida individual puede subestimar
  mucho su SE.

| Eventos con depósito por corrida | Cobertura del IC95 de una corrida | Corridas con SE < ½ SD real |
|---|---|---|
| ≥ ~200 | 0.90–1.00 | 0 |
| ~50–150 | 0.77–0.97, según la cola | 0–0.3 |
| < ~20 | 0.12–0.80 | 0.2–0.96 |

**Ejemplo de cola pesada.** En SEP_p de 70 MeV, un solo evento aporta
el 57% del depósito en pulmón de 4·10⁵ eventos. Con 1 a 10 eventos con
depósito por corrida, la cobertura queda en 0.16–0.50.

**Consecuencia:**
- R=1 (una corrida, sin repeticiones) es válido por categoría cuando
  `n_nonzero` y `max_J/S1` pasan los umbrales D4. Con estos datos, el
  candidato para D4 es del orden de 200 eventos con depósito, a fijar
  y confirmar en P2.
- Las repeticiones no compran precisión: la precisión depende del total
  de eventos. Una sola corrida con M·R eventos rinde lo mismo que R
  corridas de M.
- El cómputo lo fija el error relativo objetivo en las categorías chicas
  (colon, estómago, mama), no la validación del SE.

### P3 — Costo y convergencia por punto de energía

- **Diseño:** en x=0, con la configuración de P1, la grilla candidata de
  energías, checkpoints M = 2500, 5000, 10000 y 20000.
- **Métricas por punto:** costo por evento c_b; SE·√M estable entre
  checkpoints; diagnósticos de colas pesadas (D4).
- **Resultado esperado:** c_b crece fuerte con la energía (en el barrido
  viejo GCR_He bin 7 tardaba ~5 h por cada 10⁴ eventos). Puede haber colas
  pesadas en dos zonas: a baja energía (pocas partículas penetran) y a alta
  (cascadas).
- **Criterio:** fijar M_min con una tanda exploratoria y confirmarlo con
  semillas independientes. Cero depósitos no demuestra dosis/varianza cero.
  Confirmar también posiciones fuera del eje y el control: el costo y las
  colas de x=0 con campo no garantizan los del resto del barrido.
- **Bloquea:** la asignación de eventos del barrido. No se reduce M en
  ningún punto sin este resultado.

### P4 — Validación de la grilla de energías por caso

- **Método candidato:** curva de respuesta R(E) por partícula, con
  integración espectral (detalle en `plan_barrido.md`, sección 3). La
  grilla de protones parte de la propuesta híbrida de la Fase 8 para
  SEP_p máx (2 puntos bajo ~65 MeV y 12 entre 65 y 300 MeV), más puntos
  por encima de 300 MeV para SEP_p mín y GCR_H. Los alfas parten de una
  grilla gruesa.
- **Referencia por caso:** muestreo continuo estratificado del espectro de
  cada uno de los 6 casos (no tiene error de discretización).
- **Métrica:** ε = D_curva/D_ref − 1 con IC95, por caso, categoría,
  posición (x=0 y una fuera del eje) y configuración (escudo y control).
- **Criterio:** prueba de equivalencia, IC95 de ε dentro de ±B (D3).
- **Refinamiento:** si un caso falla, se agregan puntos donde el indicador
  de error (grilla N frente a 2N, ponderado por Φ_s) es mayor, y se repite.
  Se prueba también el esquema de interpolación. Si un caso no converge
  con la curva compartida, usa su propia grilla, validada igual (para
  SEP_p máx, la candidata es la propuesta híbrida de 14 bins).
  La grilla refinada se confirma con una referencia independiente, sin
  reutilizar como validación los mismos datos empleados para elegirla.
  Incluir las colas omitidas: cubrir 99.9% del flujo no garantiza cubrir
  99.9% de la dosis. Una referencia estratificada comparte error Monte Carlo
  y error del modelo espectral, aunque evite la cuadratura monoenergética.
- **Criterio adicional, si D8 incluye el perfil temporal de SEP:** la
  misma prueba de equivalencia con los espectros instantáneos más blando y
  más duro del evento, no solo con su espectro integrado. La forma cambia
  durante el evento, y un espectro blando pesa más en las energías bajas,
  donde actúa el corte del escudo.
- **Resultado esperado:** la grilla final y el error de cada uno de los 6
  casos con su IC. Es posible que algún caso necesite más puntos que otros.
- **Bloquea:** la grilla del barrido.

### P5 — Validación de la reducción de varianza

- **Diseño:** en los puntos donde se proponga sesgar la fuente, comparar
  contra ley coseno sin sesgo.
- **Criterio:** prueba de equivalencia (D3) y ganancia de eficiencia
  medida (varianza × costo).
- **Resultado esperado:** ganancia grande a alta energía; a baja energía
  puede no convenir.
- **Bloquea:** usar el sesgo en el barrido. Sin aprobar, se usa ley coseno
  pura.

### P6 — Precisión del endpoint escudo frente a control

Equivale a la Fase 10.

- **Diseño:** un caso exigente, escudo y control con la grilla de P4 y los
  M de P3; semillas comunes (CRN) frente a independientes.
- **Métrica:** η, H_η,95 y la correlación entre escudo y control.
- **Criterio:** H_η,95 ≤ δ_η/2 (D2), con D₀ suficientemente separado de
  cero para justificar el método delta. Confirmar los casos primarios;
  un solo caso exploratorio no acredita todos los espectros/posiciones.
- **Resultado esperado:** saber si los M de P3 alcanzan para η y si CRN
  reduce la varianza.
- **Bloquea:** los M finales del barrido.

## Dependencias

```
D1–D8 + scorer nuevo
   ├─ P0 (normalización, sin campo)
   ├─ P1 (dominio y radio) ─┬─ P3 (costo y convergencia) ─┬─ P6 (η)
   │   └─ mapa Elmer final  │   P4 (energías) ────────────┤
   │      (máquina >8 GB)   │   P5 (sesgo) ────────────────┘
   └─ P2 (estimador, sin campo) ─┘
```

**Camino crítico:** P1 → mapa Elmer final → P3/P4/P5 → P6. Lo que no usa
el campo (P0, P2, scorer, tests) se adelanta en paralelo, pero ninguna
corrida con campo hecha antes del mapa final es reutilizable.

## Condición para empezar el barrido

- [ ] D1–D7 y D8 si aplica decididas y registradas antes de los pilotos afectados.
- [ ] Mapa de campo Elmer final (dominio de P1) generado, versionado en
      `field/production/` con su manifiesto y hash, y cargado en Geant4 sin
      truncamiento dentro de la esfera fuente ni del `MagnetEnvelope`.
- [ ] Scorer nuevo y coordinator con procedencia, con tests.
- [ ] P0–P4 y P6 aprobados; P5 aprobado solo si se usará sesgo (si no,
      registrar «no aplica» y usar ley coseno sin sesgo).
- [ ] Parámetros pendientes de `plan_barrido.md` (sección 9) completos.

La implementación/despliegue del nuevo protocolo del coordinator y la imagen
Docker quedan para una etapa posterior; su ausencia no impide pilotos locales.
Los scripts históricos de Fases 7–10 no implementan todavía estos gates P0–P6.

Referencias de esta revisión: [ICRP 116](https://www.icrp.org/publication.asp?id=icrp+publication+116)
(coeficientes y rangos de protones/helio) y
[NIST: incertidumbre de la desviación estándar](https://www.itl.nist.gov/div898/handbook/prc/section2/prc231.htm)
(la comparación entre semillas también tiene incertidumbre; la fórmula χ²
requiere normalidad).
