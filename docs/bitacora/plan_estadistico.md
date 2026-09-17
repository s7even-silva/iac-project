# Plan estadístico y de simulación — Geant4 / IAC

**Estado:** actualizado con el trabajo realizado hoy  
**Objetivo:** documentar el flujo completo desde el estado actual del barrido hasta el análisis final publicable, incluyendo decisiones estadísticas, alternativas más robustas, limitaciones y criterios de aceptación.

---

## 0. Convenciones y principios

### Notación

- `R`: número de **repeticiones independientes** de una misma combinación física.
- `M`: número de **eventos primarios** por repetición (`n_events`).
- `b`: bin energético.
- `o`: offset/posición.
- `g`: órgano.
- `s`: caso físico `(species, phase)`.
- `mu_hat[s,b,o,g]`: estimación de la respuesta por primario de un bin.
- `W[s,b]`: peso físico/espectral del bin.
- `D_hat[s,o,g]`: dosis final reponderada sobre bins.

### Principio estadístico central

El objetivo no es fijar arbitrariamente un `R` universal, sino controlar la incertidumbre de la cantidad física final:

\[
\hat D_{s,o,g} = \sum_b W_{s,b}\hat\mu_{s,b,o,g}
\]

y demostrar que la incertidumbre Monte Carlo asociada es suficientemente pequeña respecto de un criterio definido **antes** de usarla para decidir si se continúa simulando.

### Qué cubre el IC y qué no

Los intervalos de confianza discutidos aquí cuantifican principalmente **incertidumbre estadística Monte Carlo**. No incluyen automáticamente:

- incertidumbre del mapa de campo;
- incertidumbre geométrica de Geom14;
- composición de materiales;
- corriente/campo real;
- physics list;
- production cuts;
- discretización energética;
- incertidumbre de espectros GCR/SEP;
- aproximaciones del modelo físico.

Estas fuentes se tratan aparte en las fases de sensibilidad y validación.

---

# Fase 0 — Auditar qué escenarios requieren transporte Geant4 nuevo

## Objetivo

Evitar correr simulaciones físicamente redundantes.

## Estado actual

- [x] Confirmado que el barrido de producción actual contiene solo tres casos:
  - `GCR_H / min`
  - `GCR_He / min`
  - `SEP_p / max`
- [x] Confirmado que la expansión a seis casos todavía no había formado parte del barrido original.
- [x] Revisado `GeneratePrimaries()`:
  - posición y dirección comunes;
  - `GCR_H` y `SEP_p` usan ambos protones;
  - `GCR_He` usa alfa;
  - geometría, campo y physics list no dependen de especie/fase.
- [x] Confirmado que, con `fixedEnergyMeV`, la fase no cambia el transporte salvo mediante la **energía representativa de los bins**.
- [x] Verificado que los bins de fases distintas usan grillas energéticas diferentes.
- [x] Verificado que `GCR_H` y `SEP_p`, aunque comparten partícula y geometría de emisión, **no tienen bins representativos coincidentes**.
- [x] **Descartada la fusión directa de los bancos de transporte `GCR_H`/`SEP_p`.**

## Conclusión

Los tres casos nuevos:

- `GCR_H / max`
- `GCR_He / max`
- `SEP_p / min`

requieren transporte nuevo bajo la discretización energética actual.

## Alternativas

### A. Mantener grillas específicas por espectro — recomendada por ahora
Ventaja:
- respeta la discretización actual y los rangos que contienen >99.9% del flujo.

Limitación:
- impide reutilizar directamente respuestas entre fases porque las energías representativas son distintas.

### B. Construir una grilla energética común para min/max
Podría permitir calcular un único response kernel por partícula y reponderarlo después a múltiples espectros.

Ventaja:
- potencial reducción grande de simulaciones futuras.

Limitaciones:
- requeriría rediseñar el binning;
- habría que repetir/validar parte del trabajo existente;
- puede necesitar más bins para representar adecuadamente todos los espectros;
- introduciría una nueva fuente de error de interpolación/rebinning.

**No se recomienda introducir este cambio en medio del barrido actual salvo que el ahorro esperado compense claramente el costo de revalidación.**

---

# Fase 1 — Congelar el criterio de precisión estadística

## Objetivo

Definir qué significa “suficientemente preciso” **antes** de usar los nuevos IC para decidir cuántas simulaciones correr.

## Estado actual

- [x] `aggregate_organ_doses.py` calcula ahora `ic95_half_width_pct`.
- [x] El cálculo se añadió sin modificar las vistas anteriores.
- [ ] Falta fijar formalmente el umbral `X`.
- [ ] Falta documentar el criterio en `AGENTS.md` o documento metodológico equivalente.

## Criterio propuesto

\[
H_{\%}=100\frac{H}{|\bar D|}
\]

donde `H` es el semiancho del IC95%.

Aceptar precisión cuando:

\[
H_{\%}\le X
\]

### Mejor opción

Vincular `X` con una diferencia físicamente relevante `delta`, por ejemplo:

\[
H \le \frac{\delta}{2}
\]

en lugar de elegir 5% solo por conveniencia.

## Casos cercanos a cero

Si `D_bar ≈ 0`, el porcentaje relativo deja de ser útil.

Alternativas:

- [ ] definir tolerancia absoluta;
- [ ] normalizar respecto a una dosis de referencia/control;
- [ ] establecer criterio específico para órganos/bins de dosis muy baja.

## Limitación metodológica

El criterio ya no puede presentarse como una preregistración hecha antes de **todos** los datos porque ya existen resultados del barrido actual.

Debe documentarse honestamente como:

> criterio prospectivo fijado antes de usar las nuevas repeticiones/expansión para decisiones adaptativas.

---

# Fase 2 — Permitir R_b diferente por bin y no descartar trabajo útil

## Objetivo

Evitar que una repetición parcialmente incompleta invalide todos los demás bins que sí terminaron.

## Estado actual

- [x] Implementada una vista adicional: `resultados_riesgo_estocastico_por_bin.csv`.
- [x] Implementada `combine_bins_by_bin()`.
- [x] Cada bin usa solo las repeticiones donde ese bin existe correctamente.
- [x] Implementado:

\[
V_b=W_b^2\frac{s_b^2}{R_b}
\]

- [x] Implementado:

\[
\operatorname{Var}(\hat D)=\sum_b V_b
\]

- [x] Implementados grados de libertad efectivos Welch–Satterthwaite:

\[
\nu_{\rm eff}=
\frac{(\sum_bV_b)^2}
{\sum_b\frac{V_b^2}{R_b-1}}
\]

- [x] Verificado el cálculo contra una implementación manual independiente.
- [x] Las vistas antiguas permanecen intactas.

## Regla crítica

- Si `R_b >= 2`, se puede estimar varianza entre runs para ese bin.
- Si `R_b = 1`, el bin puede contribuir a la **media**, pero no aporta una estimación observada de varianza.

## Estado actual de bins R_b=1

- [x] Los bins sin varianza se listan explícitamente en `bins_R1_sin_varianza`.
- [ ] **No usar el IC combinado como IC final publicable mientras bins materialmente importantes tengan R_b=1.**

### Importante

Si bins con `R_b=1` se incluyen en la media pero se les asigna varianza cero, la varianza total queda **subestimada**.

Por tanto:

- `SE=0` o un IC incompleto en esta situación **no significa precisión infinita**;
- significa que falta una fuente de varianza no estimable con los datos actuales.

## Alternativa más conservadora

Exigir repeticiones globalmente completas.

Ventaja:
- análisis simple;
- fácil de explicar.

Limitación:
- desperdicia datos válidos;
- actualmente elimina offsets completos porque falta un único bin.

## Recomendación

Mantener ambas vistas:

1. **vista conservadora por repeticiones completas** como control;
2. **vista por-bin Welch** como análisis principal eficiente.

---

# Fase 3 — Explotar correctamente los resultados ya existentes

## Estado de producción conocido

- 600 jobs totales del barrido original.
- 529 `done`.
- 67 `pending`.
- 4 `failed`.
- Las pendientes se concentran en bins 6/7 de GCR-H y GCR-He.
- Los cuatro `failed` agotaron intentos, pero pueden reponerse manualmente.

## Estado del análisis local actual

- [x] La vista por-bin recupera 30 filas.
- [x] La vista conservadora recupera 18 filas.
- [x] Las 12 filas adicionales corresponden a offsets 0.0/1.0 que antes se descartaban.
- [x] En las 18 filas comunes, el punto estimado coincide a precisión numérica.
- [ ] Importar/sincronizar las repeticiones completadas que aún no estén disponibles en el dataset local de agregación.
- [ ] Recalcular distribución real de `R_b` por bin después de la sincronización.
- [ ] Identificar bins que continúan en `R_b=1`.
- [ ] Identificar qué bins dominan la incertidumbre total.

## Decisión sobre los 71 jobs restantes

No terminarlos solo por “costo hundido”.

### Regla recomendada

Correr primero los jobs necesarios para que:

1. todo bin materialmente relevante tenga al menos `R_b >= 2`, y
2. el IC total cumpla el criterio de Fase 1.

Después evaluar si las repeticiones adicionales reducen incertidumbre lo suficiente para justificar su costo.

### Alternativa robusta

Completar los 600/600 y conservar `R=5` para todos los bins.

Ventaja:
- dataset más homogéneo;
- análisis más simple;
- mejor estimación de varianza entre runs.

Limitación:
- los jobs restantes están concentrados precisamente en los bins más caros.

---

# Fase 4 — Generalizar formalmente la dimensión phase

## Estado actual

- [x] Añadida columna `phase` en `db.py`.
- [x] Migración real probada con datos preexistentes simulados.
- [x] Backfill correcto de los tres casos originales.
- [x] Nuevo `UNIQUE` incluye cinco columnas.
- [x] Migración idempotente.
- [x] `run_organ_sweep.py` generalizado a `(species, phase)`.
- [x] `energy_bins.py` generalizado a `(species, phase)`.
- [x] `aggregate_organ_doses.py` generalizado a `(species, phase, bin_index)`.
- [x] `seed_full_sweep.py` actualizado.
- [x] `replicate_repeats.py` actualizado.
- [x] `import_local_results.py` actualizado.
- [x] `worker.py` actualizado.
- [x] Tests coordinator: 72/72.
- [x] Tests worker: 65/65.
- [x] Verificado que los índices/semillas de las 120 combinaciones actuales no cambian.
- [x] Verificado que nuevas combinaciones deben **agregarse al final**, nunca intercalarse.
- [ ] Cambios aún no desplegados en la VM de producción.
- [ ] Falta decidir cuándo ampliar `SPECIES_PHASE` a los tres casos nuevos.
- [ ] Hacer backup de DB antes de migrar producción.
- [ ] Ejecutar migración en staging o snapshot antes de producción.
- [ ] Verificar que los 529 resultados existentes conservan su identidad después de la migración.

---

# Fase 5 — Añadir incertidumbre intra-run para simulaciones futuras

## Objetivo

Permitir que una sola run de `M` eventos produzca una estimación propia de incertidumbre Monte Carlo.

## Opción recomendada: acumuladores por evento

Para cada órgano/bin almacenar:

\[
N,\qquad S_1=\sum_iX_i,\qquad S_2=\sum_iX_i^2
\]

y opcionalmente:

- `n_nonzero`;
- `max_event_contribution`.

Entonces:

\[
\bar X=\frac{S_1}{N}
\]

\[
s^2=
\frac{
S_2-S_1^2/N
}{
N-1
}
\]

\[
SE_{\rm run}=\frac{s}{\sqrt N}
\]

## Checklist

- [ ] Definir qué constituye exactamente `X_i`: contribución total del **evento primario completo**, incluyendo secundarios.
- [ ] No tratar tracks/steps del mismo primario como observaciones independientes.
- [ ] Añadir acumuladores al scorer.
- [ ] Añadir salida persistente de `N`, `S1`, `S2`.
- [ ] Añadir tests unitarios con datos sintéticos.
- [ ] Verificar igualdad del punto estimado con el scorer anterior.
- [ ] Verificar costo de CPU adicional.
- [ ] Verificar que el I/O adicional sea despreciable.

## Ventajas

- usa información de miles de historias;
- permite `R=1` con cuantificación MC;
- evita depender de `R=3` o `R=5` para estimar toda la varianza;
- casi no aumenta almacenamiento si solo se guardan acumuladores.

## Limitaciones

- no recupera información evento-a-evento de las runs ya terminadas;
- depende de que las historias primarias sean las unidades adecuadas;
- CLT puede ser lento si la distribución por historia tiene colas extremas.

---

# Fase 6 — Alternativa: batch means

## Cuándo usarla

Si modificar el scorer por evento resulta costoso o riesgoso.

Ejemplo:

\[
10000 = 20\times500
\]

Generar 20 estimadores de batch y usar:

\[
SE=\frac{s_{\rm batch}}{\sqrt{20}}
\]

## Checklist

- [ ] Garantizar independencia RNG entre batches.
- [ ] Garantizar que cada batch contiene historias completas.
- [ ] Confirmar que el scorer resetea/acumula correctamente.
- [ ] Medir overhead por reinicio.
- [ ] Comparar resultado con el método de `S1,S2,N`.

## Ventajas

- no requiere almacenar eventos individuales;
- útil para detectar colas pesadas;
- permite bootstrap sobre batches.

## Limitaciones

- más overhead;
- menos eficiente estadísticamente que usar todos los eventos directamente;
- implementación más propensa a errores de reset/acumulación.

---

# Fase 7 — Piloto de convergencia respecto de M

## Objetivo

Determinar cuántos eventos necesita realmente cada tipo de bin.

## Diseño recomendado

Usar runs largas con checkpoints:

\[
M=2500,\ 5000,\ 10000,\ 20000
\]

pero ejecutar solo:

\[
R_{\rm pilot}=3
\]

streams independientes hasta 20 000.

Costo:

\[
3\times20000=60000
\]

eventos por combinación piloto, frente a:

\[
3(2500+5000+10000+20000)=112500
\]

si se ejecutaran por separado.

Ahorro aproximado: 46.7%.

## Checklist

- [ ] Implementar checkpoints acumulados.
- [ ] Mantener la misma secuencia RNG dentro de cada stream.
- [ ] Usar tres seeds independientes entre streams.
- [ ] Calcular `SE(M)`.
- [ ] Evaluar:

\[
SE(M)\sqrt M \approx \text{constante}
\]

- [ ] Examinar estabilidad del punto estimado.
- [ ] Identificar casos con convergencia anómala.

## Limitación importante

Los checkpoints dentro de una misma run están correlacionados.

No deben analizarse como cuatro observaciones independientes.

## Alternativa más robusta

Correr cada tamaño `M` con seeds completamente nuevas.

Ventaja:
- independencia total entre puntos.

Limitación:
- ~1.9x más eventos respecto del esquema con checkpoints.

---

# Fase 8 — Seleccionar inteligentemente los casos piloto

## No hacer el piloto en todas las combinaciones por defecto

Seleccionar, como mínimo:

- [ ] un caso típico;
- [ ] un bin de alto costo;
- [ ] un órgano con baja deposición;
- [ ] un caso de alta energía;
- [ ] un caso SEP-min una vez habilitado;
- [ ] un punto donde el peso espectral del bin sea importante.

## Alternativa robusta

Piloto separado para todos los seis casos `(species, phase)`.

Ventaja:
- máxima cobertura.

Limitación:
- mayor costo y probablemente redundancia parcial.

---

# Fase 9 — Elegir M_b por bin

## Objetivo

No asignar automáticamente 10 000 eventos a todos los bins si no es necesario.

Con:

\[
V(D)=\sum_bW_b^2\frac{\sigma_b^2}{M_b}
\]

y costo por evento `c_b`, una asignación eficiente satisface aproximadamente:

\[
M_b\propto\frac{|W_b|\sigma_b}{\sqrt{c_b}}
\]

## Checklist

- [ ] Medir tiempo/evento por bin.
- [ ] Estimar `sigma_b`.
- [ ] Calcular peso `W_b`.
- [ ] Estimar contribución de cada bin a la varianza final.
- [ ] Fijar `M_b` antes de producción.
- [ ] Documentar los `M_b` definitivos.

## Alternativa simple

Mantener:

\[
M_b=10000\quad\forall b
\]

Ventaja:
- simplicidad;
- comparabilidad;
- menor riesgo de bugs.

Limitación:
- puede desperdiciar grandes cantidades de cómputo.

---

# Fase 10 — Elegir estrategia de producción para los tres casos nuevos

Hay 3 casos nuevos × 8 bins × 5 offsets = **120 combinaciones físicas por repetición**.

## Opción A — R=1 + incertidumbre intra-run — recomendada si Fase 5 funciona

- Barrido nuevo: 120 jobs.
- Cada job produce estimador + incertidumbre interna.
- Repeticiones extra solo en subconjunto de validación.

### Validación hasta R=3

Un offset por caso nuevo:

\[
3\times8\times2=48
\]

jobs adicionales.

Total:

\[
120+48=168
\]

### Validación hasta R=5

\[
120+96=216
\]

jobs.

## Opción B — R=3 completo

\[
3\times8\times5\times3=360
\]

jobs.

Ventaja:
- no depende de modificar scorer.

Limitación:
- `df=2`;
- la estimación de varianza entre runs es muy inestable.

## Opción C — R=5 completo

600 jobs nuevos.

Ventaja:
- diseño simple y homogéneo.

Limitaciones:
- costo máximo;
- `R=5` sigue siendo una muestra pequeña;
- repite cinco veces bins muy caros.

## Opción D — R=1 sin incertidumbre interna

**No recomendada para resultados principales.**

Ventaja:
- costo mínimo.

Limitación grave:
- no permite cuantificar adecuadamente el ruido MC de una combinación nueva.

---

# Fase 11 — Validar empíricamente el método R=1

## Objetivo

Demostrar que la incertidumbre estimada dentro de una run predice la dispersión observada entre runs independientes.

Para un conjunto validado:

\[
s_{\rm between}
\]

versus:

\[
SE_{\rm within}
\]

Esperamos compatibilidad aproximada:

\[
s_{\rm between}\approx SE_{\rm within}
\]

## Checklist

- [ ] Elegir combinaciones representativas.
- [ ] Incluir bins caros.
- [ ] Incluir SEP-min.
- [ ] Comparar ratios `s_between / SE_within`.
- [ ] Definir criterio de compatibilidad antes de evaluar.
- [ ] Investigar cualquier discrepancia sistemática.

## Alternativa robusta

`R=5` en varios offsets/casos.

Limitación:
- mayor costo.

---

# Fase 12 — Análisis final por bin

Para cada `(species, phase, bin, offset, organ)`:

\[
\hat\mu_b
\]

y:

\[
V_b
\]

Después:

\[
\hat D=\sum_bW_b\hat\mu_b
\]

\[
V(\hat D)=\sum_bW_b^2V_b
\]

si los bins son independientes.

## Checklist

- [ ] Verificar independencia de seeds entre bins/repeticiones.
- [ ] Validar uniformidad/registro de `n_events`.
- [ ] No asignar varianza cero a un bin `R_b=1` sin marcarlo como incompleto.
- [ ] Guardar contribución individual de cada bin a dosis.
- [ ] Guardar contribución individual de cada bin a varianza.
- [ ] Identificar bins dominantes.

---

# Fase 13 — Construcción del IC95% final

## Caso 1 — Varianza estimada mediante repeticiones

Usar Welch–Satterthwaite cuando `R_b` difiere.

\[
IC_{95}=
\hat D
\pm
t_{0.975,\nu_{\rm eff}}
SE_D
\]

## Caso 2 — Varianza intra-run basada en miles de eventos

Con tamaño efectivo grande y comportamiento MC regular:

\[
IC_{95}\approx
\hat D\pm1.96SE_D
\]

## Limitaciones

- el CLT puede converger lentamente con colas pesadas;
- `R=3` o `R=5` no permiten diagnosticar bien normalidad entre runs;
- un IC MC no cubre incertidumbres sistemáticas.

## Alternativa robusta

Bootstrap por batches/eventos.

Ventaja:
- menor dependencia de normalidad.

Limitación:
- requiere datos por evento o batch;
- más complejidad.

---

# Fase 14 — Comparación min vs max

Con la grilla actual, min/max se simulan en energías distintas.

Por tanto, **no asumir covarianza por reutilización del mismo response kernel**.

## Checklist

- [ ] Tratar inicialmente min/max como estimaciones de transporte separadas.
- [ ] Propagar la incertidumbre de cada espectro independientemente.
- [ ] Si en el futuro se adopta una grilla común, incorporar covarianza por reutilización de responses.

---

# Fase 15 — Comparación blindaje vs control

Si la métrica científica principal es:

\[
\eta=
1-\frac{D_{\rm shield}}{D_{\rm control}}
\]

reportar directamente:

- `eta_hat`;
- IC95%;
- no basarse solo en “superposición de IC”.

## Alternativa futura: common random numbers

Usar los mismos primarios/seeds para shield y control.

Ventaja:
- puede reducir mucho la varianza de la diferencia.

Limitaciones:
- requiere análisis pareado/covarianza;
- el campo puede hacer divergir fuertemente las trayectorias;
- introducirlo ahora complicaría un pipeline ya avanzado.

---

# Fase 16 — Validar el error de discretización energética

## Riesgo

Los IC Monte Carlo pueden ser pequeños aunque el uso de 8 bins introduzca un error sistemático mayor.

## Estudio mínimo recomendado

Comparar en casos representativos:

\[
8\text{ bins}\quad \text{vs}\quad16\text{ bins}
\]

y calcular:

\[
\epsilon_{\rm binning}=
\frac{|D_{16}-D_8|}{|D_{16}|}
\]

## Checklist

- [ ] Seleccionar casos representativos.
- [ ] Incluir un espectro duro.
- [ ] Incluir SEP-min.
- [ ] Comparar dosis total.
- [ ] Comparar órganos sensibles.
- [ ] Comparar costo computacional.

## Alternativa robusta

\[
8\rightarrow16\rightarrow32
\]

hasta convergencia.

Limitación:
- costo elevado.

## Alternativa eficiente

Refinamiento adaptativo donde `mu(E)` cambia más rápidamente.

Limitación:
- mayor complejidad metodológica.

---

# Fase 17 — Incertidumbres sistemáticas y análisis de sensibilidad

## Objetivo

Evitar confundir “precisión Monte Carlo” con “exactitud física”.

## Evaluar, según disponibilidad

- [ ] intensidad del campo;
- [ ] reconstrucción geométrica Geom14;
- [ ] materiales;
- [ ] composición de bobinas;
- [ ] mapa/interpolación de campo;
- [ ] integrador/step;
- [ ] physics list;
- [ ] production cuts;
- [ ] espectros de entrada;
- [ ] binning energético.

## Prioridad

La incertidumbre MC debería quedar razonablemente por debajo de las principales incertidumbres sistemáticas.

No tiene sentido gastar mucho cómputo para reducir MC de 2% a 0.2% si el modelo geométrico tiene incertidumbre de ~10%.

---

# Fase 18 — Multiplicidad y endpoints del paper

Habrá muchas combinaciones de:

- órganos;
- offsets;
- casos físicos;
- posiblemente blindajes/configuraciones.

## Checklist

- [ ] Definir endpoints primarios.
- [ ] Definir análisis secundarios.
- [ ] Evitar interpretar cientos de IC95% como cobertura conjunta del 95%.
- [ ] Si se realizan tests de hipótesis múltiples, usar ajuste apropiado (ej. Holm).
- [ ] Preferir tamaños de efecto + IC sobre listas grandes de p-values.

---

# Fase 19 — Reproducibilidad y semillas

## Estado actual

- [x] Fórmula actual: `seed1 = BASE_SEED + 1000*rep + 2*index`.
- [x] `seed2 = seed1 + 1`.
- [x] Sin colisiones en las 120 combinaciones actuales.
- [x] Sin colisiones en la expansión prevista a 240 combinaciones.
- [x] Mismo `(rep,index)` → mismas seeds.
- [x] Retries reutilizan seeds y no cuentan como nuevas réplicas.
- [x] Los índices actuales permanecen iguales con la refactorización de `phase`.
- [x] Se verificó que las nuevas combinaciones deben anexarse al final.

## Pendiente

- [ ] Añadir `assert`/test automático de unicidad de seeds.
- [ ] Guardar metadatos de reproducción:
  - `job_id`;
  - `seed1`;
  - `seed2`;
  - `species`;
  - `phase`;
  - energía;
  - bin;
  - offset;
  - `n_events`;
  - Geant4 version;
  - image digest;
  - physics list;
  - hash de campo;
  - hash/geometría;
  - commit Git.

---

# Fase 20 — Despliegue seguro de los cambios hechos hoy

Los cambios están actualmente solo en el working tree local.

## Checklist antes de producción

- [ ] Revisar diff completo.
- [ ] Ejecutar nuevamente todos los tests.
- [ ] Commit limpio y versionado.
- [ ] Backup/snapshot de DB de producción.
- [ ] Registrar commit actualmente desplegado.
- [ ] Desplegar primero schema compatible sin ampliar todavía `SPECIES_PHASE`.
- [ ] Ejecutar migración.
- [ ] Confirmar que los 600 jobs originales conservan:
  - IDs;
  - species;
  - phase backfilled;
  - bin;
  - offset;
  - repetición;
  - seed/index lógico.
- [ ] Verificar `/health`.
- [ ] Verificar workers.
- [ ] Ejecutar agregador sobre datos existentes.
- [ ] Comparar bit a bit los resultados antiguos.
- [ ] Solo después habilitar los tres casos nuevos.
- [ ] Añadir nuevas combinaciones **al final** del orden.
- [ ] Comprobar que ninguna seed histórica cambia.

---

# Fase 21 — Secuencia operativa recomendada desde hoy

## Etapa A — cerrar el análisis del barrido existente

- [ ] Sincronizar todos los resultados `done` disponibles.
- [ ] Recalcular `R_b` real.
- [ ] Calcular qué bins tienen `R_b=1,2,3,4,5`.
- [ ] Calcular contribución de cada bin a dosis.
- [ ] Calcular contribución de cada bin a varianza.
- [ ] Fijar `X` / `delta`.
- [ ] Decidir qué jobs de los 67 pending y 4 failed son realmente necesarios.
- [ ] Reencolar solo los necesarios o, alternativamente, completar los 600.

## Etapa B — preparar el método futuro

- [ ] Implementar incertidumbre intra-run.
- [ ] Validarla con tests.
- [ ] Implementar checkpoints.
- [ ] Ejecutar piloto de convergencia.
- [ ] Seleccionar `M_b`.

## Etapa C — expansión a tres casos nuevos

- [ ] Desplegar soporte `phase`.
- [ ] Añadir:
  - `GCR_H/max`;
  - `GCR_He/max`;
  - `SEP_p/min`.
- [ ] Ejecutar `R=1` completo si la incertidumbre intra-run está validada.
- [ ] Ejecutar `R=3` en subconjunto de validación.
- [ ] Extender a `R=5` solo si el criterio predefinido falla.

## Etapa D — validaciones numéricas/físicas

- [ ] 8 vs 16 bins.
- [ ] Sensibilidad a parámetros principales.
- [ ] Validación contra literatura/caso de referencia.
- [ ] Comparación blindaje/control.

## Etapa E — análisis final y paper

- [ ] Generar tabla final por caso/offset/órgano.
- [ ] Reportar estimación puntual.
- [ ] Reportar IC95%.
- [ ] Reportar `H_%`.
- [ ] Reportar método usado para varianza.
- [ ] Reportar `R_b` / `M_b`.
- [ ] Marcar cualquier resultado sin varianza suficiente.
- [ ] Reportar estudio de convergencia.
- [ ] Reportar estudio de discretización energética.
- [ ] Separar explícitamente error MC de incertidumbre sistemática.

---

# Camino estadístico recomendado para el paper

## 1. Respuesta por bin

\[
\hat\mu_b
\]

## 2. Incertidumbre por bin

A partir de:

- varias runs independientes, o
- estadística intra-run.

## 3. Reponderación espectral

\[
\hat D=\sum_bW_b\hat\mu_b
\]

## 4. Propagación

\[
V(\hat D)=\sum_bW_b^2V_b
\]

## 5. IC

Welch–Satterthwaite cuando la información proviene de números diferentes de repeticiones por bin; aproximación normal cuando proviene de gran número de historias y se ha validado el régimen Monte Carlo.

## 6. Criterio de precisión

\[
H_{\%}\le X
\]

o criterio ligado a `delta`.

## 7. Validación

- convergencia con `M`;
- compatibilidad `SE_within` vs `s_between`;
- sensibilidad al binning.

## 8. Interpretación

El IC cuantifica la incertidumbre estadística del Monte Carlo condicionada al modelo, no la incertidumbre física total del experimento.

---

# Validez real del plan

## Fortalezas

- semillas reproducibles y sin colisión en el espacio actual;
- retries no contaminan `R`;
- jobs idempotentes;
- uso correcto de varianza muestral;
- Student-t correcto en análisis por repeticiones;
- posibilidad de Welch para `R_b` desigual;
- modelo por-bin aprovecha datos parciales válidos;
- separación entre punto estimado pooled y análisis de incertidumbre;
- expansión `phase` diseñada sin invalidar resultados históricos;
- tests automáticos amplios.

## Limitaciones moderadas

### R=3 o R=5
La varianza entre runs sigue siendo estimada con muy pocos grados de libertad.

Mitigación:
- usar estadística intra-run para simulaciones futuras;
- reservar `R>1` principalmente para validación.

### Normalidad / CLT
Una run puede tener contribuciones por historia muy asimétricas.

Mitigación:
- `n_nonzero`;
- `max_event_contribution`;
- batches;
- piloto de convergencia.

## Limitaciones importantes

### Bins R_b=1
No existe una estimación de varianza entre runs.

**No tratar esos bins como varianza cero.**

### Error de binning energético
Puede ser mayor que el error MC.

Debe estudiarse al menos en casos representativos.

### Incertidumbre sistemática
Los IC MC no incluyen error del modelo físico.

Debe declararse explícitamente.

---

# Decisión recomendada hoy

1. **No lanzar todavía los tres casos nuevos.**
2. Desplegar primero el soporte `phase` de forma backward-compatible.
3. Sincronizar y explotar correctamente los resultados actuales mediante la vista por-bin.
4. Fijar el criterio de precisión.
5. Determinar cuántos de los 71 jobs restantes son realmente necesarios.
6. Implementar incertidumbre intra-run.
7. Hacer un piloto pequeño de convergencia con checkpoints.
8. Fijar `M_b`.
9. Ejecutar los nuevos casos inicialmente con `R=1` si la incertidumbre intra-run ha sido validada.
10. Usar `R=3–5` únicamente en un subconjunto de validación o cuando el criterio de precisión lo requiera.
11. Antes del paper, realizar al menos un estudio de convergencia del binning energético y separar claramente incertidumbre MC de incertidumbre sistemática.

---

# Definición de “listo para publicar”

Un resultado se considera metodológicamente listo para el manuscrito cuando:

- [ ] todas las combinaciones físicas están claramente definidas;
- [ ] seeds y versión de software están registradas;
- [ ] todo bin materialmente relevante tiene una estimación de varianza válida;
- [ ] no hay bins `R_b=1` tratados como varianza cero;
- [ ] el IC95% final está correctamente propagado;
- [ ] el criterio de precisión se cumple o se declara explícitamente que no;
- [ ] el número de eventos ha pasado un chequeo de convergencia;
- [ ] el binning energético ha pasado al menos una prueba de refinamiento;
- [ ] el análisis distingue error MC de incertidumbres sistemáticas;
- [ ] retries/cancelaciones no generan doble conteo;
- [ ] resultados históricos y nuevos son reproducibles;
- [ ] cualquier análisis adaptativo tiene reglas documentadas;
- [ ] el método estadístico está descrito de forma suficiente para reproducirlo.
