# Limitaciones y constraints del barrido de 600 simulaciones

Este documento junta, en un solo lugar, **todas** las limitaciones
conocidas de los resultados que produce el barrido de producción de
`ActiveShield_Sim` (120 combinaciones especie×bin×posición × 5
repeticiones = 600 corridas). No es contenido nuevo: cada punto ya está
documentado en detalle en algún lugar del repositorio — este documento
solo los reúne para que nadie tenga que rearmar el cuadro completo antes
de escribir el paper. Las fuentes exactas se citan en cada sección.

## 0. Estado de cómputo vs. estado de los CSV versionados — LO MÁS URGENTE

**El coordinator reporta hoy (2026-09-24) las 600/600 corridas
completas, 0 pendientes, 0 fallidas** (`GET /api/v1/health`). Pero los
CSV agregados en este mismo directorio (`resultados_organo_agregados_
pooled.csv`, `resultados_riesgo_estocastico_pooled_todas_las_reps.csv`,
etc.) están fechados **18 de septiembre** y siguen mostrando
`n_repeticiones=1` en todas las filas de la vista de repeticiones —
reflejan una descarga parcial de hace varios días, no el barrido ya
terminado.

**Antes de citar cualquier cifra o barra de error de estos archivos en
el paper, hay que volver a descargar los resultados reales del
coordinator y regenerar los agregados** (ver el procedimiento en
`resultados/README.md`, sección "Cómo regenerar"). Todo lo que sigue en
este documento sigue aplicando igual después de regenerar — son
limitaciones metodológicas, no de completitud de descarga.

## 1. Alcance físico: solo 3 de los 4 escenarios reales

El barrido usa el "peor caso por especie" (GCR en mínimo solar, SEP en
el evento de octubre de 1989), no las 4 combinaciones físicas reales que
existen en los datos OLTARIS (GCR mínimo/máximo solar × SEP máximo/mínimo).
GCR en máximo solar y SEP mínimo (Feb. 1956, ajuste LaRC) **no están en
este dataset**. El soporte de código para la dimensión `phase` (columna
en la base de datos, `--only-phase`, generalización de
`energy_bins.py`/`aggregate_organ_doses.py`) ya está implementado y
verificado, pero **no desplegado en la VM de producción**, y el equipo
no ha decidido todavía si expandir a los 6 casos.
Fuente: `docs/bitacora/validez_estadistica_runs.md`, `docs/bitacora/plan_estadistico.md` Fase 4.

## 2. N=5 repeticiones: sin justificación estadística formal

"5" es una decisión práctica del equipo (aparece como ejemplo de
docstring y default de `replicate_repeats.py`), no el resultado de un
cálculo de tamaño de muestra ni de un objetivo de precisión declarado
de antemano. Existe una propuesta de criterio formal
(`δ_η = 10 puntos porcentuales` de reducción de dosis shield-vs-control
como diferencia científicamente relevante, exigiendo
`H_η,95% ≤ 5 puntos porcentuales` de semiancho del IC95%), pero **no ha
sido congelada ni adoptada oficialmente por el equipo**.
Fuente: `docs/bitacora/validez_estadistica_runs.md`; `docs/bitacora/plan_estadistico.md` Fase 1.

## 3. Las repeticiones todavía no dan una barra de error confiable y completa

`aggregate_organ_doses.py`, en su vista "por posición" (la más
conservadora), descarta una repetición **completa** para una fila
`(categoría, offset)` si falta una sola de las 24 combinaciones
especie×bin de ese offset — el N efectivo colapsa al mínimo común de
todos los bins. Verificado con datos reales: esto daba `n_repeticiones=1`
en todas las filas hasta la fecha del último chequeo documentado (y
sigue así en los CSV versionados hoy, ver sección 0). Existe una vista
alternativa por-bin (`resultados_riesgo_estocastico_por_bin.csv`,
Welch-Satterthwaite) que recupera más filas sin exigir repetición
global completa, pero **cualquier bin que siga en `R_b=1` no tiene
varianza observada** — combinarlo como si tuviera varianza cero
subestima la incertidumbre total, no la reduce genuinamente. No tratar
ningún IC como definitivo mientras haya bins materialmente relevantes
en `R_b=1`.
Fuente: `docs/bitacora/validez_estadistica_runs.md`; `docs/bitacora/plan_estadistico.md` Fase 2.

## 4. El estimador de incertidumbre "de una sola corrida" está descartado

Se intentó validar un método para estimar la incertidumbre de una
combinación con una sola repetición (`R=1` + incertidumbre intra-run,
acumuladores S1/S2 por vóxel en el scorer C++) para poder ahorrar
cómputo en escenarios futuros. **Cerrado el 2026-09-21 con veredicto
negativo**: el estimador subestima sistemáticamente la varianza real
entre repeticiones por un factor de ~2 a ~7 (razón mediana 0.14-0.51
del valor verdadero, según combinación), porque el diseño del scorer
acumula por vóxel y no por evento, ignorando la covarianza positiva
entre vóxeles que toca un mismo primario. **Consecuencia directa para
cualquier análisis**: los campos `se_run_j`/`se_run_total_j` que trae
cada corrida individual **no deben usarse como la incertidumbre real**
de esa dosis — solo la dispersión observada **entre repeticiones**
(semillas independientes reales) es confiable hoy, y eso exige `R≥2`
efectivo, no uno solo.
Fuente: `docs/bitacora/plan_estadistico.md` Fase 7.

## 5. Discretización de energía (8 bins): convergencia todavía en validación

La Fase 8 (convergencia del binning energético, 8 vs. 16 vs. 32 bins)
está en curso, no cerrada. Primer resultado real: el peor caso medido
(GCR_H en mínimo solar) da 2.78% de diferencia entre 8 y 16 bins, justo
al borde del presupuesto fijado (2.5 puntos porcentuales) — veredicto
"límitrofe", pendiente de comprobar 16→32 antes de decidir si 8 bins
alcanzan para el paper. La barra de "ruido Monte Carlo" usada para
descartar que esa diferencia sea solo ruido estadístico (y no un efecto
real de discretización) usa un **factor de corrección extrapolado**
desde el peor caso de la Fase 7 — no es una medición directa de estos
bins específicos, está declarado así explícitamente en el código.
Fuente: `docs/bitacora/plan_estadistico.md` Fase 8.

## 6. Calibración del número de eventos por bin: pendiente

El número de eventos por bin (10 000, fijo en todo el barrido de
producción) no ha sido calibrado todavía contra un objetivo formal de
precisión (Fase 9 del plan estadístico, no iniciada/validada).
Fuente: `docs/bitacora/plan_estadistico.md` Fase 9.

## 7. Precisión de la comparación shield-vs-control: sin validar

El resultado central que el paper quiere afirmar — "el campo activo
reduce la dosis en X%" — todavía no tiene una validación formal de
precisión end-to-end (Fase 10 del plan estadístico). El criterio
propuesto en la sección 2 (`δ_η=10pp`, `H≤5pp`) no se ha aplicado
todavía a ningún par de configuraciones real (con vs. sin campo, o
activo vs. pasivo).
Fuente: `docs/bitacora/plan_estadistico.md` Fase 10.

## 8. Ponderación radiobiológica (w_R) por partícula primaria, no por secundaria

`w_R` (ICRP103, protón/pión=2, alfa=20) se asigna según la especie
primaria de la corrida, no partícula-por-partícula en cada paso — un
neutrón o fragmento secundario generado dentro del fantoma hereda el
`w_R` del primario en vez de tener el propio. Sesgo de dirección
conocida cualitativamente (afecta más a los bins de mayor energía, donde
la fragmentación nuclear es más relevante) pero no cuantificado.
Fuente: `docs/bitacora/activeshield_sim_historia.md` (sección "Ponderación radiobiológica").

## 9. Mama en fantoma masculino

El fantoma ICRP110 usado es masculino. La mama sí está segmentada
geométricamente y da una dosis físicamente válida, pero `w_T=0.12` es un
promedio poblacional por sexo — la dosis reportada para mama en este
fantoma es una referencia dosimétrica/geométrica, **no** equivalente al
riesgo epidemiológico de cáncer de mama documentado en mujeres.
Fuente: `docs/bitacora/activeshield_sim_historia.md`.

## 10. El arreglo de 8 bobinas nunca se construyó con la cinta HTS de 12mm

Toda la geometría, el campo Elmer, y las 600 corridas de producción usan
exclusivamente el conductor **CORC** homogeneizado. La cinta HTS de
12mm (la opción de mayor `I_c`, preferida en la decisión original de
"construir ambas y comparar") solo se probó en pilotos de una sola
bobina — el arreglo completo de 8 bobinas con esa cinta **no existe**
todavía. Si el paper quiere reportarla como alternativa, hace falta
generar esa geometría/campo desde cero.
Fuente: `docs/bitacora/activeshield_sim_historia.md` (corrección del 2026-09-12).

## 11. Dos supuestos de geometría sin dato externo de contraste

La sección transversal **cuadrada** del winding pack homogeneizado y el
radio de regularización de Biot-Savart (10%, usado además solo para la
comparación de método, no para la producción) son supuestos propios del
equipo — ninguna fuente (el reporte NIAC ni la tesis) da la segunda
dimensión real del devanado ni un radio de referencia. Aceptados
explícitamente como limitación conocida del modelo, no como pendiente
que más cómputo vaya a resolver.
Fuente: `docs/bitacora/activeshield_sim_historia.md`.

## 12. Elmer FEM vs. Biot-Savart: la elección de método cambia el resultado ~40%

La producción usa el campo Elmer FEM (resuelve la distribución de
corriente real sobre la sección del conductor), no Biot-Savart. En la
misma configuración, Biot-Savart da **36-48% más dosis** que Elmer —
la elección de método de cálculo de campo no es un detalle numérico
menor, cambia el resultado reportado en ese margen. Elmer se adoptó por
ser más preciso, pero sigue cargando los supuestos de la sección 11.
Fuente: `docs/bitacora/activeshield_sim_historia.md` ("Error de campo vs. error de dosis en Elmer").

## 13. El eje central como posición de mayor dosis: mecanismo sin confirmar

Los resultados (`rep0` y el agregado pooled, de forma consistente) muestran
la dosis en `offset_x_m=0` (el eje de simetría del arreglo) **2-3 órdenes
de magnitud por encima** de cualquier otra posición, para las 6 categorías
de riesgo estocástico. La explicación más probable — cancelación del
campo Halbach justo sobre su propio eje de simetría — **no se ha
confirmado leyendo directamente `|B|` a lo largo de ese eje** en el mapa
de producción; por ahora es una inferencia a partir de la dosis, no una
medición del campo.
Fuente: `resultados/INTERPRETACION_PROTECCION_RADIOLOGICA.md`.

## 14. SEP_p bin0 da dosis cero — confirmado físico, pero no generalizable a otros ceros

El bin de menor energía de SEP_p (~19 keV) deposita `edep_J=0` de forma
sistemática, confirmado tanto en un piloto dedicado como en los datos
reales de producción — ese protón no atraviesa el casco de 1.5cm de
aluminio, es un resultado físico real. **Esto no prueba que todos los
demás ceros** que aparecen en otras celdas (órgano/posición/bin) sean
igualmente físicos: cada cero debe evaluarse caso por caso contra la
estadística disponible (eventos por bin, R_b), no asumirse como
confirmado por analogía con este caso.
Fuente: `docs/bitacora/plan_estadistico.md` Fase 7 (checklist).

## 15. Cómputo 100% distribuido en hardware voluntario heterogéneo

Las 600 corridas se ejecutaron en máquinas voluntarias no dedicadas
(laptops personales, con reinicios, apagones y cortes de red
documentados en `infra/OPERATIONS_LOG.md`), coordinadas por el sistema
`coordinator`/`worker`. El protocolo (verificación de identidad del
resultado subido, rutas únicas por intento, reencolado por heartbeat
vencido) está probado para no corromper resultados silenciosamente, pero
implica que ningún resultado se generó en hardware controlado o
idéntico entre sí, y que un job marcado `done` pudo haber requerido más
de un intento tras la caída de un worker.
Fuente: `infra/OPERATIONS_LOG.md`; `infra/DISTRIBUTED_SWEEP_HISTORY.md`.

## Resumen para quien solo tenga un minuto

Antes de citar cualquier número de este barrido en el paper: (1)
regenera los CSV desde el coordinator, ya está 600/600 pero los archivos
del repo no lo reflejan todavía; (2) ningún IC95% de este dataset es
todavía definitivo — casi todo sigue en `n_repeticiones=1` en la vista
conservadora; (3) es solo 3 de 4 escenarios físicos posibles; (4) tres
fases de validación metodológica (binning, eventos/bin, precisión de la
comparación shield-vs-control) siguen abiertas; (5) el hallazgo más
llamativo del dataset (el eje central como peor posición) es robusto en
los datos pero su explicación física todavía no está confirmada
directamente contra el mapa de campo.
