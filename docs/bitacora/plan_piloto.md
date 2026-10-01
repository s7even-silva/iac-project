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
3. Un resultado sin incertidumbre no aprueba nada. Si el intervalo de
   confianza es demasiado ancho para decidir, se agregan eventos; no se
   declara éxito.
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

| # | Decisión | Qué bloquea |
|---|---|---|
| D1 | Ley coseno como modo de producción | Todo |
| D2 | Endpoint primario (por ejemplo, dosis efectiva o una categoría) y δ_η (el plan propone 10 pp) | P5, P6 |
| D3 | Presupuesto B de error de dosis por caso especie/fase y por categoría, para las pruebas de equivalencia | P1, P4, P5 |
| D4 | Umbrales de los diagnósticos de convergencia (fracción máxima de un solo evento, mínimo de eventos con depósito, rango aceptable de SE_within/s_between) | P2, P3 |
| D5 | Fantoma AF sí o no (dosis efectiva completa) | Diseño del barrido |
| D6 | Posiciones (las 5 actuales u otra elección) | P1, P6, barrido |
| D7 | Tolerancia con ICRP 116 para P0 | P0 |

## Requisitos técnicos bloqueantes

Antes de los pilotos que los necesitan (detalle en `plan_barrido.md`):

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
- **Criterio:** dentro de la tolerancia D7. ICRP 116 se calculó con otros
  códigos y physics lists; diferencias de este orden no implican error.
- **Resultado esperado:** acuerdo dentro de la tolerancia, y que el factor
  ~1.8 sobre la pura ionización a 1.8 GeV quede explicado por las
  interacciones nucleares.
- **Bloquea:** todo resultado absoluto. Si falla, hay un error de
  normalización o de física que resolver antes de seguir.

### P1 — Dominio del campo y radio de la esfera fuente

Decidido: se amplían. El piloto fija cuánto.

1. **Preselección:** un mapa Biot-Savart en un dominio grande da la cola
   ∫B⊥·dl fuera de cada radio candidato. Se descartan los radios donde esa
   cola puede desviar de forma apreciable a las partículas de menor
   rigidez de interés.
2. **Elmer:** dominios crecientes. Comparar el campo interior entre ellos
   (efecto de la frontera `AV=0`; hoy Biot-Savart y Elmer difieren hasta
   un 40% hacia los extremos en z). Requiere una máquina con más de ~8 GB
   de RAM.
3. **Convergencia de la dosis:** x=0 y una posición fuera del eje, en las
   energías más sensibles al campo (cerca del corte del escudo), para
   R₁ < R₂ < R₃.

- **Criterio:** se acepta el menor radio cuya diferencia con el siguiente
  pasa la prueba de equivalencia con presupuesto D3.
- **Resultado esperado:** un radio y un dominio documentados con sus datos
  de convergencia, más el mapa de campo final versionado con su hash.
- **Bloquea:** P3–P6 y el barrido. Cambiar el campo después invalida todo.

### P2 — Validación del estimador de incertidumbre por evento

Repite la Fase 7 con el scorer nuevo.

- **Diseño:** 3–4 combinaciones (incluidas SEP y una energía alta), 5
  semillas independientes por combinación, varios M.
- **Métrica:** SE_within (intra-run) frente a s_between (entre semillas),
  por órgano y categoría.
- **Criterio:** el cociente dentro del rango D4.
- **Resultado esperado:** cociente ≈ 1. Con la acumulación por evento, el
  estimador es exacto por construcción, a diferencia del 0.48 del método
  anterior.
- **Bloquea:** usar R=1 en el barrido. Si falla, el barrido necesita
  repeticiones.

### P3 — Costo y convergencia por punto de energía

- **Diseño:** en x=0, con la configuración de P1, la grilla candidata de
  energías, checkpoints M = 2500, 5000, 10000 y 20000.
- **Métricas por punto:** costo por evento c_b; SE·√M estable entre
  checkpoints; diagnósticos de colas pesadas (D4).
- **Resultado esperado:** c_b crece fuerte con la energía (en el barrido
  viejo GCR_He bin 7 tardaba ~5 h por cada 10⁴ eventos). Puede haber colas
  pesadas en dos zonas: a baja energía (pocas partículas penetran) y a alta
  (cascadas).
- **Criterio:** se fija M_min por punto como el menor M donde pasan todos
  los diagnósticos.
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
- **Criterio:** H_η,95 ≤ δ_η/2 (D2).
- **Resultado esperado:** saber si los M de P3 alcanzan para η y si CRN
  reduce la varianza.
- **Bloquea:** los M finales del barrido.

## Dependencias

```
D1–D7 + scorer nuevo
   ├─ P0 (normalización)
   ├─ P1 (dominio y radio) ─┬─ P3 (costo y convergencia) ─┬─ P6 (η)
   └─ P2 (estimador)       ─┘   P4 (energías) ────────────┤
                                P5 (sesgo) ────────────────┘
```

## Condición para empezar el barrido

- [ ] D1–D7 decididas y registradas, con fecha anterior a los datos de los
      pilotos.
- [ ] Scorer nuevo y coordinator con procedencia, con tests.
- [ ] P0–P6 aprobados, con resultados y datos versionados.
- [ ] Parámetros pendientes de `plan_barrido.md` (sección 9) completos.
