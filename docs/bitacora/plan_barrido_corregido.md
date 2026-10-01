# Plan del barrido corregido (propuesta, 2026-09-30)

Contexto: la auditoría del 2026-09-30 (`auditoria_2026-09-30.md`) dejó sin
ninguna dosis físicamente válida. La malla de scoring no seguía al fantoma
y todos los primarios apuntaban al origen. Hay que volver a simular todo.
Este documento propone cómo hacerlo aprovechando el plan estadístico
(`plan_estadistico.md`) y lo aprendido.

**Regla de este plan:** ninguna cifra de diseño (puntos de energía,
eventos por punto, radio de la esfera, tamaño del dominio de campo) es una
decisión hasta que la valide el protocolo estadístico correspondiente,
con su criterio de aceptación fijado **antes** de ver los datos. Las
cifras que aparecen aquí son **candidatos iniciales**. Motivo: los 8 bins
de SEP se eligieron sin validar y la Fase 8 mostró que no convergían.

Como hay que volver a correr todo de cualquier forma, ya no aplica el
argumento del plan para no cambiar el diseño a mitad del barrido ("costo
de revalidación", Fase 0, alternativa B).

## 1. Cambios obligatorios antes de cualquier corrida

1. **Ley coseno como default** (`/gun/angularDistribution cosine`, ya
   implementado como opción).
2. **Malla de scoring que siga al fantoma** (ya corregido en las plantillas).
3. **Scorer nuevo** (requisitos R1–R11 de la auditoría). El mínimo para
   producción:
   - R1, acumulación por evento: imprescindible para todo el análisis
     estadístico de abajo;
   - R2, Q(L) más espectro de LET;
   - R5, pesos de traza (G4PSEnergyDeposit ya multiplica por el peso;
     comprobado en el código fuente de Geant4);
   - R6, contadores de trazas cortadas;
   - R8, energía muestreada dentro del bin: necesaria para el método de
     referencia de la sección 2;
   - R9, procedencia;
   - además, **diagnósticos de convergencia por punto**: número de eventos
     con depósito distinto de cero, mayor contribución de un solo evento,
     y S1/S2 en checkpoints de M.
4. **Coordinator:** exigir procedencia y un esquema de semillas
   versionado sin colisiones.

## 2. Energías: método candidato y su validación

### Método candidato: curva de respuesta por partícula

Calcular la respuesta R(E) por partícula (protones y alfas) en puntos de
energía fijos, e integrar cada espectro después:
`D_s = ∫ R(E) Φ_s(E) dE`. Así una sola curva de protones serviría para
GCR_H mín/máx y SEP_p mín/máx, y una de alfas para GCR_He mín/máx.

**Grilla candidata inicial** (solo punto de partida, se ajusta con el
protocolo de abajo):

- **Puntos bajos:** pocos debajo de ~65 MeV/nucleón, donde el casco de
  4 g/cm² frena casi todo.
- **Puntos densos:** entre ~65 y ~500 MeV/nucleón. Esto sigue la
  propuesta híbrida de la Fase 8 para SEP_p máx: 2 bins bajos más 12 altos
  (14 en total) dieron un error estimado de 1.03% frente a 128 bins. Esa
  cifra se estimó por interpolación, no se corrió, y el mismo documento
  advierte que el método no reproducía bien los errores reales (2.57%
  estimado frente a 3.66–4.22% medido). Además, los datos usaron apuntado
  radial.
- **Puntos altos:** log-espaciados hasta las energías de GCR.

### Pregunta que el protocolo debe responder

¿El método compartido da, **para cada uno de los 6 casos especie/fase**,
la misma dosis que un método específico para ese caso? El error puede ser
bajo en un caso y alto en otro: la misma grilla no tiene por qué servir
igual a SEP mín (hasta 2500 MeV) que a SEP máx (hasta 300 MeV) o a GCR.

### Referencia independiente por caso

Muestreo continuo estratificado del espectro de cada caso (R8): por cada
estrato de energía, la energía de cada primario se toma del espectro real
de ese caso, y el peso es el flujo del estrato. Este estimador **no tiene
error de discretización**, solo error Monte Carlo, así que sirve como
referencia exacta del método individual. La estratificación evita
desperdiciar primarios en la zona de baja energía, donde la dosis es ~0.

### Métrica y criterio

Para cada caso `s`, categoría de órgano `c` (y dosis de cuerpo completo),
posición y configuración (escudo y control):

```
ε = (D_curva − D_ref) / D_ref
```

con su IC95 propagado de ambas incertidumbres Monte Carlo (corridas
independientes).

- **Criterio de aceptación: prueba de equivalencia.** El IC95 de ε tiene
  que caer completo dentro de ±B. No basta con que ε "no sea
  significativo": un IC ancho no demuestra equivalencia, solo falta de
  información.
- **B se fija antes del piloto (decisión pendiente).** El plan solo tiene
  el presupuesto para η (2.5 pp de B_8→16, Fase 8); hay que definir el de
  dosis y cómo se traslada a η.
- Si el IC es demasiado ancho para decidir, se agregan eventos a la
  referencia o a la curva. **No se declara éxito.**

### Refinamiento adaptativo

Si un caso falla:

1. Calcular el indicador de error por intervalo de energía: la diferencia
   entre la grilla N y la 2N intercalada, ponderada por Φ_s.
2. Agregar puntos donde ese indicador es mayor para el caso que falla.
3. Repetir hasta que los 6 casos pasen.

El número final de puntos sale de este proceso, no de una estimación
previa. Hay que probar también el esquema de interpolación (log-log o
lineal en log E).

**Dónde validar:** x=0 y al menos una posición fuera del eje (el campo
cambia con la posición), escudo y control.

**Si el método compartido no pasa para algún caso,** ese caso usa su
propia grilla, validada con el mismo protocolo.

## 3. Configuraciones

- **Posiciones:** las 5 actuales (0–4 m). Recortarlas es una decisión del
  equipo.
- **Escudo frente a control:** el endpoint primario del plan es
  η = 1 − D_escudo/D_control. El control usa `fieldScale 0` con las bobinas
  presentes. Probar semillas comunes (CRN, Fase 10) y medir si la
  correlación reduce la varianza de η.
- **Fantoma:** AM, y AF según la decisión de reportar dosis efectiva.

El número total de trabajos se calcula cuando la grilla esté validada.

## 4. Eventos por punto: depende de la convergencia

Antes de asignar eventos por punto (Fase 9) hay que demostrar, para cada
punto de energía, que su estimador converge:

1. **Escalamiento:** el SE decrece como `1/√M` en los checkpoints
   (M = 2500, 5000, 10000, 20000).
2. **Sin colas pesadas:** la mayor contribución de un solo evento es una
   fracción chica del total, el número de eventos con depósito no es
   escaso, y el estimador de varianza es estable entre checkpoints. Un
   punto con colas pesadas subestima su varianza con M chico, y reducirle
   eventos sería perder información.
3. **Error intra-run validado:** el SE intra-run (scorer por evento)
   coincide con la dispersión entre semillas (repetir la Fase 7 con el
   estimador nuevo).

Solo con eso se calcula la asignación `M_b ∝ |W_b| σ_b / √c_b`, con dos
restricciones:

- un piso `M_min` por punto, que es el M donde los diagnósticos pasan;
- el resultado final tiene que cumplir el criterio de precisión de cada
  caso y categoría (H ≤ criterio, Fases 1/10).

Ningún punto recibe menos eventos por ser caro si no está demostrado que
converge con esa cantidad.

**Referencia de costo real** (para presupuestar, no para decidir M): el
barrido de 600 (apuntado radial, 10000 eventos) sumó unas 58 h por
repetición; GCR_He bin 7 ~5 h por corrida, bin 6 ~2 h; GCR_H bin 7 ~1.3 h.
Con ley coseno el costo por evento cambia y en energías altas no está
medido.

## 5. Reducción de varianza

Con ley coseno, solo ~0.3% de los primarios cruza el fantoma.

- **Sesgo de fuente dependiente de la energía** (candidato): muestrear
  direcciones preferentemente hacia el fantoma, con peso
  `pdf_real/pdf_sesgada`. Es insesgado en teoría, pero **se valida igual**:
  comparar contra ley coseno sin sesgo, en una prueba de equivalencia, en
  los puntos donde se aplique.
- **Dos etapas** (espacio de fases alrededor del casco): evaluarla si el
  piloto de costo muestra que la etapa de bobinas domina.
- **Monte Carlo inverso: descartado.** Geant4 solo tiene procesos adjuntos
  electromagnéticos, sin física hadrónica.

## 6. Esfera fuente y dominio del campo

**Decidido: se amplían.** Queda pendiente **cuánto**, con un criterio
explícito:

1. **Preselección barata:** un mapa Biot-Savart en un dominio grande da el
   ∫B⊥·dl que queda fuera de cada radio candidato. Se descartan los radios
   donde esa cola puede desviar de forma apreciable a las partículas de
   menor rigidez de interés.
2. **Prueba de convergencia de la dosis:** dosis en x=0 (y una posición
   fuera del eje) para radios y dominios crecientes R₁ < R₂ < R₃, en las
   energías más sensibles al campo (cerca del corte del escudo). Se acepta
   el menor radio para el cual la diferencia con el siguiente cae dentro
   del presupuesto, con prueba de equivalencia.
3. **Efecto de la frontera de Elmer** (`AV = 0`): comparar el campo
   interior entre dominios crecientes. Hoy, Biot-Savart y Elmer difieren
   hasta un 40% hacia los extremos en z.

El radio y el dominio elegidos, con sus datos de convergencia, quedan
documentados antes de la producción. Requiere una máquina con más de ~8 GB
de RAM para Elmer.

## 7. Estadística de producción

- R=1 por punto con el error intra-run (Fase 11, opción A), **solo si** el
  paso 3 de la sección 4 lo valida.
- Subconjunto de validación con R=3 (Fase 12).
- IC por propagación `V(D) = Σ W_b² V_b` (Fases 13/14). Con la curva de
  respuesta, los pesos de interpolación reemplazan a W_b, y las
  covarianzas entre casos que comparten puntos se propagan (Fase 15).
- Criterio H_η,95 ≤ 5 pp (Fases 1/10), con multiplicidad por los muchos
  órganos, posiciones y casos (Fase 19).

## Orden propuesto

1. **Decisiones del equipo antes de ver datos:** ley coseno como default,
   endpoint primario, δ_η, presupuesto B de dosis por caso, criterio de los
   diagnósticos de convergencia, AF sí o no.
2. **Cambio de C++** (scorer R1–R11 con diagnósticos, sesgo de fuente)
   con tests, más el coordinator (procedencia, semillas v2, tabla de
   trabajos nueva) y una imagen nueva de worker.
3. **Dominio de campo y esfera** (sección 6).
4. **Piloto de costo y convergencia por punto** (sección 4), en x=0.
5. **Piloto de validación de energías** (sección 2): curva frente a la
   referencia por caso, con refinamiento hasta pasar.
6. **Asignación de M_b** con los datos de 4 y 5.
7. Sembrar la producción en el coordinator, luego validación R=3, análisis
   con η y la Fase 7 repetida.
