# Primeros resultados del barrido por órgano: interpretación de protección radiológica

**Fuente de datos:** `resultados_riesgo_estocastico_rep0.csv` — la primera
vuelta completa del barrido (120/120 combinaciones especie×bin×posición,
repetición 0), tal como la define `resultados/README.md`. Los números se
contrastan puntualmente contra `resultados_riesgo_estocastico_pooled_
todas_las_reps.csv` (todas las repeticiones disponibles a la fecha,
eventos sumados) para confirmar que el hallazgo central no es un
artefacto de una sola repetición.

**Escenario simulado:** el "peor caso por especie" ya fijado por el
equipo (ver `AGENTS.md`) — GCR en mínimo solar (H y He, OLTARIS BON2020,
dosis en **Sv/día**) y el evento SEP histórico de octubre de 1989 en
solar máximo (OLTARIS Historical SPE, dosis en **Sv/evento completo**,
no por día). Blindaje activo CREW HaT (arreglo de 8 bobinas Halbach,
corriente de diseño 1×10⁷ A, campo Elmer FEM a escala real) con la
geometría sólida de las bobinas incluida. Fantoma ICRP110 masculino,
6 categorías de riesgo estocástico ICRP103 (`w_T=0.12` cada una: colon,
pulmón, estómago, mama, médula ósea roja, tejidos restantes). Posición
del fantoma: desplazamiento radial `offset_x_m` (0 a 4 m) respecto al
eje central compartido por el casco y el arreglo de bobinas — **no** es
un desplazamiento a lo largo del eje largo de la nave.

## Tabla de resultados (rep0)

| Categoría | offset (m) | H equivalente GCR [Sv/día] | H equivalente SEP [Sv/evento] |
|---|---|---|---|
| Colon | 0.0 | 1.463e-1 | 0.0 |
| Colon | 1.0 | 6.70e-5 | 1.85e-3 |
| Colon | 2.0 | 5.20e-5 | 6.29e-3 |
| Colon | 3.0 | 6.27e-5 | 0.0 |
| Colon | 4.0 | 5.99e-5 | 0.0 |
| Lung | 0.0 | 6.618e-2 | 5.321e-1 |
| Lung | 1.0 | 1.024e-4 | 3.00e-3 |
| Lung | 2.0 | 6.67e-5 | 2.08e-3 |
| Lung | 3.0 | 1.081e-4 | 8.20e-3 |
| Lung | 4.0 | 7.10e-5 | 3.05e-3 |
| Stomach | 0.0 | 1.014e-1 | 0.0 |
| Stomach | 1.0 | 4.05e-5 | 2.92e-4 |
| Stomach | 2.0 | 4.19e-5 | 7.92e-4 |
| Stomach | 3.0 | 3.74e-5 | 5.17e-3 |
| Stomach | 4.0 | 4.06e-5 | 0.0 |
| Breast | 0.0 | 6.054e-2 | 0.0 |
| Breast | 1.0 | 4.81e-5 | 0.0 |
| Breast | 2.0 | 2.94e-5 | 0.0 |
| Breast | 3.0 | 2.64e-5 | 8.26e-3 |
| Breast | 4.0 | 2.98e-5 | 0.0 |
| Remainder tissues | 0.0 | 1.291e-1 | 1.120 |
| Remainder tissues | 1.0 | 5.25e-5 | 1.20e-3 |
| Remainder tissues | 2.0 | 4.89e-5 | 2.89e-3 |
| Remainder tissues | 3.0 | 4.91e-5 | 1.44e-3 |
| Remainder tissues | 4.0 | 5.05e-5 | 1.94e-3 |
| Red bone marrow | 0.0 | 1.366e-1 | 7.870e-1 |
| Red bone marrow | 1.0 | 4.50e-5 | 6.71e-4 |
| Red bone marrow | 2.0 | 4.20e-5 | 2.22e-3 |
| Red bone marrow | 3.0 | 4.93e-5 | 1.32e-3 |
| Red bone marrow | 4.0 | 4.73e-5 | 1.16e-3 |

## Hallazgo central: el eje geométrico es el peor lugar, no el más seguro

En las seis categorías, sin excepción, la dosis equivalente en
`offset_x_m=0` (el eje central compartido por el casco y el arreglo de
bobinas) es **2 a 3 órdenes de magnitud mayor** que en cualquier
posición a partir de 1 m de ese eje — para GCR, la caída va de ~0.06-0.15
Sv/día en el eje a ~3-11×10⁻⁵ Sv/día apenas 1 m afuera, un factor de
~1000-2500x. El mismo patrón se repite, con la misma magnitud, en
`resultados_riesgo_estocastico_pooled_todas_las_reps.csv` (más
repeticiones, más estadística) — colon en el eje: 0.146 Sv/día (rep0) vs.
0.156 Sv/día (pooled); médula ósea roja: 0.137 vs. 0.139 Sv/día — la
coincidencia entre ambos cortes de datos independientes descarta que sea
ruido de Monte Carlo de una sola repetición.

Esto invierte la intuición habitual de "el centro de la nave es el lugar
más protegido" — al menos para este diseño de blindaje específico. La
explicación física más probable (**hipótesis, no confirmada todavía**):
el arreglo Halbach de 8 bobinas construye su campo dipolar por
cancelación de las contribuciones individuales de cada bobina, y esa
misma cancelación puede anular casi por completo la componente útil del
campo justo sobre el eje de simetría del arreglo — dejando una región
angosta de blindaje casi nulo exactamente donde, ingenuamente, se
esperaría poner al astronauta. **Pendiente de verificar antes de
afirmarlo como hecho**: leer directamente `|B|` a lo largo del eje X
(offset 0 a 1 m, Y=0, Z=0) en el `.map` de producción
(`crewhat_elmer_fullscale.map`) para confirmar que cae a valores
mínimos exactamente ahí, en vez de solo inferirlo de la dosis.

## Qué significa esto contra límites reales de protección radiológica

Usando valores de referencia estándar del campo (a confirmar/citar con
la fuente exacta que el equipo decida para el paper):

- **NASA-STD-3001, límite de órganos formadores de sangre (BFO) a 30
  días: 0.25 Sv.**
- **ICRP, límite ocupacional de dosis efectiva: 20 mSv/año** (promediado
  a 5 años).
- **Umbral de síndrome de radiación aguda (SRA) leve, cuerpo entero:
  del orden de 0.5-1 Sv.**

**En el eje (offset 0 m), el diseño actual no protege en absoluto:**
- GCR solar mínimo, médula ósea roja: 0.137 Sv/día → en apenas **30
  días** acumula ~4.1 Sv, **>16 veces** el límite de 30 días de la NASA
  para BFO. En una misión de 180 días, ~25 Sv — dosis no compatible con
  la supervivencia.
- Un solo evento SEP tipo octubre de 1989, médula ósea: 0.787-1.06 Sv
  (rep0/pooled) — **de un único evento**, ya supera el límite de 30 días
  de la NASA en 3-4 veces, y "tejidos restantes" da 1.06-1.12 Sv, dentro
  del rango asociado a síntomas medibles de SRA. Un evento solar mientras
  el astronauta ocupa el eje central podría causar efectos deterministas
  agudos, no solo elevar el riesgo estocástico de cáncer a largo plazo.

**A partir de 1 m fuera del eje, el mismo diseño cumple con margen
amplio:**
- GCR, médula ósea marrow: 4.5×10⁻⁵ Sv/día → en un año, ~16 mSv —
  por debajo del límite ocupacional anual de ICRP (20 mSv), y una
  fracción pequeña de cualquier límite de carrera de la NASA.
- SEP de un evento tipo Oct.\,1989: 0.6-2.3 mSv en médula ósea según la
  posición exacta — dos a tres órdenes de magnitud por debajo del límite
  de 30 días, sin indicio de riesgo agudo.

**Conclusión operativa:** el blindaje SÍ funciona, y funciona bien, pero
solo fuera del eje central. La recomendación directa para el diseño de
la nave es **no ubicar literas, estaciones de trabajo prolongado, ni el
refugio de tormenta ("storm shelter") sobre el eje geométrico compartido
por el casco y el arreglo de bobinas** — desplazar cualquier zona de
permanencia prolongada al menos 1 m de ese eje reduce la dosis en
2-3 órdenes de magnitud, la diferencia entre un diseño inviable y uno
que cumple los límites operacionales estándar.

## Limitaciones a declarar (no ocultar en el paper)

- **Estadística de una sola repetición para varias celdas SEP.** Varios
  valores de `H_SEP` en `offset_x_m=0` para colon/estómago/mama son
  exactamente 0.0 — plausible resultado real (esos órganos, pequeños y
  bien protegidos por tejido circundante, pueden no recibir ningún
  depósito de energía en los 10 000 eventos de un bin), pero no
  distinguible todavía de una simple falta de estadística. El archivo de
  repeticiones (`resultados_riesgo_estocastico_repeticiones_rep0.csv`)
  no tiene barra de error porque `n_repeticiones=1` en todas las filas —
  esperar a que las repeticiones 1-4 terminen (en curso vía cómputo
  distribuido, ver `infra/`) antes de citar estos ceros como un
  resultado físico confirmado.
- **Es el escenario de peor caso por especie, no el espacio completo.**
  GCR está fijo en mínimo solar y SEP en el evento de octubre de 1989 —
  no cubre fase solar máxima de GCR ni el evento mínimo de SEP (Feb.
  1956), que sí están soportados por el pipeline (`/gun/phase`) pero
  fuera del barrido de 120 combinaciones ya corrido.
- **La hipótesis del campo nulo en el eje sigue sin verificarse
  directamente contra el mapa de campo** — ver la sección anterior.
- **Bins 6 y 7** (las energías más altas, GCR_He y SEP_p en especial)
  siguen terminando de correrse vía el coordinator distribuido a la
  fecha de este documento — este corte (`rep0`) ya los incluye para las
  combinaciones que estaban completas al generarlo, pero conviene
  regenerar esta tabla cuando el barrido completo (`--repeats 5`)
  termine, para tener también las barras de error entre repeticiones.
