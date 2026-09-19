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

## Elección recomendada de `delta` para blindaje vs. control

`delta` **no debe salir del piloto**. El piloto estima la varianza y permite calcular cuánto `M` hace falta; si `delta` se eligiera después de ver el efecto del piloto, el criterio de precisión quedaría condicionado por los propios datos.

La literatura de blindaje espacial sirve para **anclar la escala** de `delta`, aunque no existe un umbral universal equivalente a una “mínima diferencia clínicamente importante” para blindaje magnético. En estudios Geant4/SR2S se han reportado contribuciones del campo magnético del orden de:

- ~10% para configuraciones de campo moderado (~6.3 Tm);
- ~20–25% para una configuración toroidal de ~8 Tm;
- ~45% para configuraciones de ~23 Tm;
- de forma general, contribuciones del campo del orden de 10–50%, dependiendo de configuración, masa y métrica.

Como referencia adicional, trabajos recientes de blindaje pasivo con Geant4 e ICRP110 obtienen reducciones de dosis efectiva que varían ampliamente (aprox. 7–44% según material, espesor, quality factor y modulación solar). Esto confirma que diferencias del orden de decenas de puntos porcentuales son físicamente plausibles, pero que el umbral relevante depende del objetivo de diseño.

### Valor primario recomendado para este proyecto

Para la comparación principal **shield vs. no-shield**, adoptar provisionalmente:

\[
\boxed{\delta_\eta = 10\ \text{puntos porcentuales}}
\]

donde:

\[
\eta = 1-\frac{D_{\rm shield}}{D_{\rm control}}.
\]

Entonces el criterio de precisión sería:

\[
\boxed{H_{\eta,95}\le 5\ \text{puntos porcentuales}}
\]

Esto significa que el estudio debe poder resolver razonablemente una reducción de dosis de 10 puntos porcentuales.

**Interpretación:** `delta_eta = 10 pp` no afirma que 10% sea un umbral biológico o clínico universal. Es un **umbral de resolución científica/ingenieril** para este estudio, escogido porque se sitúa cerca del extremo inferior de efectos magnéticos publicados y evita exigir una precisión innecesariamente extrema.

### Alternativas

**Más estricta — `delta_eta = 5 pp`:**

\[
H_{\eta,95}\le2.5\text{ pp}
\]

Ventaja:
- permite diferenciar configuraciones de blindaje muy parecidas.

Limitación:
- si todo lo demás permanece igual, reducir el semiancho objetivo de 5 pp a 2.5 pp requiere aproximadamente 4 veces más historias Monte Carlo, porque `H ∝ 1/sqrt(M)`.

**Más laxa — `delta_eta = 15–20 pp`:**

Ventaja:
- reduce sustancialmente el costo computacional.

Limitación:
- puede ser demasiado gruesa para detectar efectos en el extremo bajo de lo publicado (~10–20%);
- podría declarar “indistinguibles” configuraciones con diferencias físicamente interesantes.

### Decisión que debe congelarse

- [ ] Definir el endpoint primario exacto al que aplica `delta_eta` (por ejemplo, dosis equivalente efectiva total, dosis equivalente de órgano prioritario u otra magnitud).
- [ ] Adoptar formalmente `delta_eta = 10 pp` como criterio primario, o documentar otra elección antes del Piloto B.
- [ ] Registrar que el piloto **no se utilizará para redefinir `delta_eta` según el efecto observado**.
- [ ] Permitir criterios secundarios más estrictos para comparaciones entre dos diseños de shield cercanos, sin cambiar retrospectivamente el criterio primario.

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

# Secuencia de validación y calibración antes de producción

Antes de liberar el barrido final, el trabajo se organiza en **cuatro etapas previas**, cada una con una función distinta y en un orden que evita optimizar una discretización que luego pudiera descartarse.

| Etapa | Pregunta principal | Qué valida | Qué reutiliza |
|---|---|---|---|
| **Validación del estimador intra-run** | ¿Podemos confiar en la incertidumbre calculada dentro de una sola run? | `SE_within`, acumuladores por evento y comportamiento Monte Carlo | `s_between` de las runs históricas |
| **Convergencia del binning energético** | ¿8 bins representan suficientemente bien el espectro y la respuesta física? | error de discretización 8→16, y 16→32 si hace falta | resultados 8-bin ya existentes |
| **Calibración del número de eventos por bin** | Con el binning definitivo, ¿cuánto `M_b` necesita cada bin? | relación `SE(M)`, costo por evento y asignación de historias | resultados de las dos etapas anteriores |
| **Comprobación de precisión shield/control** | ¿La configuración estadística elegida permite resolver el efecto científico mínimo? | `eta`, `H_eta`, `delta_eta` y posible utilidad de CRN | `M_b` ya fijado y binning definitivo |
| **Producción definitiva** | Ejecutar el barrido completo bajo el protocolo congelado | resultados finales | puede incorporar datos previos solo si fueron generados bajo el protocolo definitivo |

Flujo recomendado:

\[
\boxed{
\text{validar incertidumbre intra-run}
\rightarrow
\text{validar binning}
\rightarrow
\text{calibrar }M_b
\rightarrow
\text{validar endpoint}
\rightarrow
\text{producción}
}
\]

### Por qué este orden es importante

El error de discretización energética y el error Monte Carlo son fuentes distintas:

\[
\text{error numérico por binning}
\neq
\text{ruido Monte Carlo}.
\]

Aumentar `M` reduce el ruido Monte Carlo, pero **no corrige** un binning insuficiente. Por eso no conviene fijar definitivamente `M_b` ni validar el endpoint shield/control antes de comprobar que la discretización energética es adecuada.

### Regla metodológica

- `delta_eta` se fija **antes** de comprobar la precisión del endpoint shield/control.
- La validación técnica del estimador puede hacerse todavía con energías del esquema de 8 bins porque evalúa el estimador de incertidumbre y la ley `1/sqrt(M)`, no la suficiencia de la cuadratura espectral.
- Si 8 bins resultan insuficientes, **no se pierde** la validación del estimador intra-run; lo que debe recalibrarse es `M_b` sobre la malla definitiva.
- La comprobación del endpoint shield/control se hace únicamente después de congelar el binning.
- Una simulación de validación puede incorporarse a producción solo si coincide exactamente con el protocolo definitivo.

# Fase 7 — Validación del estimador de incertidumbre intra-run

## Objetivo

Comprobar que la incertidumbre estadística calculada dentro de una sola run es correcta y que el Monte Carlo sigue el comportamiento esperado:

\[
SE(M)\propto\frac{1}{\sqrt{M}}.
\]

Esta fase **no fija todavía el `M_b` definitivo de producción**. Su objetivo es validar la maquinaria estadística que permitirá usar `R=1` de forma defendible en las simulaciones futuras.

## Cómo reutiliza las simulaciones históricas

Las runs ya terminadas no guardaron `S2` ni información evento-a-evento, por lo que no puede reconstruirse retrospectivamente `SE_within`. Sin embargo, donde existen varias seeds independientes sí puede calcularse:

\[
s_{\rm between}=SD(\hat\mu_1,\ldots,\hat\mu_R).
\]

Una nueva run instrumentada a `M=10000` produce:

\[
SE_{\rm within}.
\]

Ambas cantidades estiman la misma escala de ruido de una run de 10000 historias:

\[
SE_{\rm within}\approx s_{\rm between}.
\]

Así, las simulaciones históricas funcionan como **referencia externa de validación** y reducen el número de nuevas repeticiones instrumentadas necesarias.

## Diseño recomendado

Seleccionar unas pocas combinaciones representativas y difíciles, priorizando aquellas con `R>=3` histórico.

Para cada una:

- usar 2–3 seeds instrumentadas;
- ejecutar hasta `M_max = 20000`;
- guardar checkpoints acumulados en:
  - 2500;
  - 5000;
  - 10000;
  - 20000 eventos.

### ⚠️ Corrección real de diseño (2026-09-19): "checkpoints acumulados" es inviable en Geant4

El diseño de arriba ("guardar checkpoints acumulados", varios `/run/beamOn`
sucesivos dentro de la misma sesión de macro, confiando en que el scorer
acumularía entre ellos) se implementó primero y **resultó estar mal
concebido, no solo caro** — verificado con datos reales, no solo por
lectura de código:

- Hipótesis original: como no se encontró ningún `G4VScoringMesh::ResetScore()`
  invocado por defecto ni por el proyecto, se asumió que el scorer
  acumulaba entre `/run/beamOn` sucesivos de la misma macro.
- **La hipótesis era incorrecta.** Confirmado en un log real (`grep "###
  Run"` sobre 4 `beamOn` sucesivos mostró `Run 0`, `Run 1`, `Run 2`,
  `Run 3`): en Geant4, **cada `/run/beamOn` inicia un `G4Run` nuevo e
  independiente**, con su propio ciclo de vida de scoring desde cero —
  la ausencia de un reset explícito no implica acumulación; cada Run
  simplemente empieza limpio por diseño del framework, sin relación con
  el anterior.
- Evidencia empírica que lo confirmó: el "edep total" de los
  "checkpoints" sucesivos **no era monótono creciente**
  (`M=2500→1.14e-10 J`, `M=5000→6.88e-11 J` — bajó, algo matemáticamente
  imposible si de verdad fuera acumulado, ya que edep no puede
  disminuir al agregar eventos no-negativos). Cada "checkpoint" medía en
  realidad un lote de eventos distinto y no relacionado con el anterior.

**Diseño corregido, ya implementado** (`geant4/ActiveShield_Sim/scripts/pilots/run_intrarun_pilot.py`):
cada valor de `M ∈ {2500, 5000, 10000, 20000}` es ahora una **corrida
independiente completa** (un solo `/run/beamOn M`, con su propia semilla
determinista), no un checkpoint dentro de una corrida más grande — es
exactamente la "alternativa más robusta" que ya estaba prevista más abajo
en esta misma fase (ver "Alternativa robusta: correr cada tamaño M con
seeds completamente nuevas... ~1.9x más eventos"), adoptada como diseño
principal porque el esquema de checkpoints no era una opción más cara,
era inválido.

Consecuencia en el análisis: `s_between` y `SE_within` ya no se comparan
solo en `M=20000` — con este diseño, cada `M` tiene su propio conjunto de
seeds independientes, así que la comparación se calcula en **los 4
valores de M por separado**, dando una curva completa en vez de un solo
punto (ver `comparacion_se_within_vs_s_between.csv` del script). Costo:
sube de `n_combos*n_seeds` corridas a `n_combos*n_seeds*4` corridas (una
por cada M, ya no compartidas dentro de una sola corrida larga).

## Checklist

- [x] `S1`, `S2` y `N` superan tests sintéticos y de regresión (comparado contra `statistics.stdev()` con 4 casos sintéticos + caso límite N=1, ver commit del scorer).
- [x] El nuevo scorer reproduce el mismo punto estimado que el scorer anterior (verificado bit a bit antes del fix del bug de relectura de `PhantomMesh_Edep.txt` encontrado de paso el mismo día, ver `docs/bitacora/activeshield_sim_historia.md` o el propio historial de commits — ese bug era preexistente, no introducido por este cambio, y se corrigió en el mismo commit).
- [x] Script del piloto (`geant4/ActiveShield_Sim/scripts/pilots/run_intrarun_pilot.py`) implementado, probado de punta a punta localmente (combinación barata, 2 seeds) — streaming de progreso en vivo, checkpoint de que el binario tiene las columnas intra-run antes de correr el piloto completo.
- [ ] `SE_within(M)` es compatible con `s_between` (para cada M — ver corrección de diseño arriba) en una corrida real del piloto con las combinaciones representativas (`GCR_He/min/6`, `SEP_p/min/0`, `GCR_H/min/2`) — pendiente de ejecutar en una máquina de `cpu_score` alto (ej. `fcm-pc1`, ~21 vs. la referencia de 4.461), ver `geant4/ActiveShield_Sim/scripts/pilots/README.md`.
- [ ] No existe discrepancia sistemática entre ambos estimadores.
- [ ] `SE(M) * sqrt(M)` permanece aproximadamente constante.
- [ ] El punto estimado se estabiliza al aumentar `M`.
- [ ] `n_nonzero` es suficiente en los tallies relevantes.
- [ ] `max_event_contribution` no revela que una única historia domine el estimador (no implementado en el script actual — el reporte da `n` por órgano, que sirve de proxy parcial, pero no la contribución máxima de una sola historia).

## Qué información produce

1. evidencia de que `R=1 + incertidumbre intra-run` es estadísticamente utilizable;
2. una estimación preliminar de cómo escala la incertidumbre con `M`;
3. diagnóstico de colas/eventos raros;
4. una primera estimación de costos por evento.

## Qué no decide todavía

- no decide si 8 bins son suficientes;
- no fija el `M_b` final;
- no decide si `H_eta <= delta_eta/2`;
- no reemplaza la validación de discretización energética.

## Si falla

Si `SE_within` y `s_between` son incompatibles de forma sistemática, **no se pasa a producción con `R=1`** hasta identificar la causa.

Posibles causas:

- error en acumuladores;
- correlación entre eventos;
- scoring incorrecto;
- colas extremas;
- diferencias de configuración entre runs históricas y nuevas.

# Fase 8 — Convergencia del binning energético

**Implementado (2026-09-19):** `geant4/ActiveShield_Sim/scripts/pilots/run_fase8_binning.py`
— corre las grillas de 8 y 16 bins, calcula `epsilon_binning` (alcance
reducido: dosis absoluta, no el endpoint `eta` completo — ver docstring
del script) y escribe un veredicto automatizable (`auto_continue` /
`limitrofe` / `revisar`) contra el presupuesto `B_8→16 ≤ 2.5 pp` de más
abajo, vía `pilot_state.py`. Encadenable con la Fase 7 y las siguientes
mediante `run_pilot_workflow.py`. Ver `pilots/README.md`. Verificado con
una corrida de humo (1 combinación, pocos eventos) — sin resultado real
del piloto todavía, eso queda pendiente de correr en una máquina rápida.

## Objetivo

Determinar si la discretización actual de 8 bins es suficientemente precisa **antes** de optimizar `M_b` o comprobar la precisión de la comparación shield/control.

El problema es distinto del ruido Monte Carlo:

\[
D_8-D_{\rm continuo}
\]

es un error de discretización. Aumentar `M` no lo elimina.

## Diseño mínimo recomendado

Comparar, en casos preseleccionados y físicamente exigentes:

\[
8\text{ bins}
\quad\text{vs}\quad
16\text{ bins}.
\]

Si el resultado es limítrofe:

\[
16\rightarrow32.
\]

## Casos que conviene incluir

- [ ] al menos un caso GCR;
- [ ] al menos un caso SEP;
- [ ] `SEP_p/min` por su espectro duro;
- [ ] una especie alfa;
- [ ] un offset relevante;
- [ ] un endpoint/órgano sensible;
- [ ] cuando sea viable, shield y control para estudiar directamente el cambio en `eta`.

## Métricas

Para dosis:

\[
\epsilon_{\rm binning}
=
\frac{|D_{16}-D_8|}{|D_{16}|}.
\]

Para el endpoint principal shield/control:

\[
\eta_k
=
1-\frac{D_{{\rm shield},k}}
{D_{{\rm control},k}},
\]

con `k=8,16`, y:

\[
B_{8\rightarrow16}
=
|\eta_{16}-\eta_8|.
\]

## Tolerancia de diseño propuesta

Dado que el criterio primario propuesto es:

\[
\delta_\eta=10\text{ pp}
\]

y:

\[
H_{\eta,95}\le5\text{ pp},
\]

usar provisionalmente como presupuesto de error de discretización:

\[
\boxed{
B_{8\rightarrow16}\le2.5\text{ pp}
}
\]

para considerar 8 bins suficientemente estables respecto del endpoint principal.

Este valor es un **presupuesto numérico del estudio**, no un estándar universal.

## Considerar también el ruido Monte Carlo

No basta comparar dos puntos estimados. Si ambos tienen incertidumbre apreciable, evaluar:

\[
\Delta_{\rm bin}
=
\eta_{16}-\eta_8
\]

junto con su error estándar.

No declarar insuficiente el binning por una diferencia que sea compatible con puro ruido Monte Carlo.

## Reutilización de resultados existentes

- [x] Los resultados históricos de 8 bins pueden servir como lado `D_8` cuando la configuración coincide exactamente.
- [ ] Correr únicamente la malla refinada necesaria para esos casos.
- [ ] No mezclar resultados si cambió alguna otra condición física.

## Decisión

### Si 8 bins cumplen
Conservar 8 bins y continuar a calibración final de `M_b`.

### Si 8 bins no cumplen
Adoptar 16 bins como candidato.

### Si 8→16 es limítrofe o 16 no parece estable
Comprobar:

\[
16\rightarrow32.
\]

Si 16 y 32 concuerdan dentro del presupuesto, usar 16.

## Si 8 bins falla, ¿qué se conserva?

Sigue siendo válido:

- la validación de `SE_within`;
- el comportamiento `1/sqrt(M)`;
- los tests del scorer;
- tiempos por evento en energías ya estudiadas;
- la reproducibilidad de seeds.

Debe recalibrarse:

- `M_b`;
- cualquier endpoint integrado calculado sobre el binning descartado;
- la comparación final shield/control.

# Fase 9 — Calibración del número de eventos por bin

**Implementado (2026-09-19):** `geant4/ActiveShield_Sim/scripts/pilots/run_fase9_calibracion_mb.py`
— corre una corrida de sondeo por bin de la malla definitiva, mide
`sigma_b` (vía `SE_within`), `W_b` y `c_b` (costo real medido en la
máquina), y calcula `M_b` propuesto con la fórmula de abajo. Siempre
termina en veredicto `revisar` (el plan exige documentar `M_b` como
decisión de equipo, no automatizable). Ver `pilots/README.md`.

## Objetivo

Una vez congelado el binning energético, determinar cuánto `M_b` necesita cada bin para que su contribución a la incertidumbre del endpoint final sea suficientemente pequeña.

## Base estadística

Con:

\[
V(D)=\sum_bW_b^2\frac{\sigma_b^2}{M_b},
\]

y costo por evento `c_b`, una asignación eficiente satisface aproximadamente:

\[
M_b\propto\frac{|W_b|\sigma_b}{\sqrt{c_b}}.
\]

## Diseño recomendado

Usar la información obtenida en la validación del estimador y, si hace falta, ejecutar checkpoints adicionales **sobre las energías representativas del binning definitivo**:

\[
M=2500,\ 5000,\ 10000,\ 20000.
\]

Los cuatro tamaños pueden obtenerse como prefijos/checkpoints de runs largas, sin ejecutar cuatro jobs independientes por seed.

## Checklist

- [ ] Medir `SE_b(M)` para bins representativos.
- [ ] Verificar `SE(M) * sqrt(M)` en la malla definitiva.
- [ ] Medir costo por evento `c_b`.
- [ ] Calcular `W_b`.
- [ ] Estimar `sigma_b`.
- [ ] Calcular contribución `W_b^2 V_b`.
- [ ] Identificar bins que dominan la incertidumbre.
- [ ] Fijar `M_b` antes de la validación shield/control.
- [ ] Documentar los `M_b` definitivos.
- [ ] Mantener un mínimo de historias que evite tallies patológicamente escasos.

## Alternativa simple y robusta

Mantener:

\[
M_b=10000\quad\forall b.
\]

Ventajas:

- simplicidad;
- comparabilidad;
- menor riesgo de errores.

Limitación:

- puede desperdiciar mucho cómputo, especialmente en bins de alta energía costosos que contribuyen poco a la varianza final.

## Alternativa más eficiente

Asignar `M_b` utilizando `W_b`, `sigma_b` y `c_b`.

Ventaja:

- minimiza la varianza para un presupuesto computacional dado.

Limitaciones:

- pipeline más complejo;
- requiere estimaciones preliminares de `sigma_b`;
- los valores deben congelarse antes de producción para evitar decisiones post hoc.

# Fase 10 — Comprobación de precisión del endpoint shield vs. control

**Implementado (2026-09-19):** `geant4/ActiveShield_Sim/scripts/pilots/run_fase10_endpoint.py`
— corre control (`field_scale=0`) y shield (`field_scale=1`) por bin con
los `M_b` de la Fase 9, calcula `eta`, propaga `V(eta)` (sin CRN
todavía — bins/configuraciones con semillas independientes) y compara
`H_eta,95` contra `delta_eta/2=5pp`. Gate automatizable, mismo criterio
que Fase 8. Ver `pilots/README.md`.

## Objetivo

Comprobar que los `M_b` seleccionados en el Piloto A son suficientes **para la cantidad científica que se publicará**, no solo para estimar bien cada bin individual.

Definir:

\[
D_0=D_{\rm control},
\qquad
D_1=D_{\rm shield}
\]

y la reducción relativa:

\[
\eta=1-\frac{D_1}{D_0}.
\]

El criterio primario propuesto es:

\[
\boxed{H_{\eta,95}\le\frac{\delta_\eta}{2}}
\]

con:

\[
\boxed{\delta_\eta=10\text{ pp}}
\]

como propuesta inicial para la comparación principal shield/no-shield.

## Diseño mínimo recomendado

Para cada caso seleccionado:

1. ejecutar/obtener los 8 bins del control;
2. ejecutar/obtener los 8 bins con shield;
3. utilizar los `M_b` fijados por Piloto A;
4. calcular dosis total e incertidumbre propagada;
5. calcular `eta` e IC95%.

Para bins independientes:

\[
V(D_0)=\sum_bW_b^2V_{0,b}
\]

\[
V(D_1)=\sum_bW_b^2V_{1,b}.
\]

Si shield y control son independientes:

\[
V(\eta)\approx
\frac{V(D_1)}{D_0^2}
+
\frac{D_1^2V(D_0)}{D_0^4}.
\]

Entonces:

\[
H_{\eta,95}\approx1.96\sqrt{V(\eta)}
\]

cuando la aproximación normal está validada.

## Common random numbers (CRN)

Cuando sea técnicamente compatible, correr control y shield con la misma seed/estado inicial permite estimar su covarianza:

\[
V(D_0-D_1)=V(D_0)+V(D_1)-2\operatorname{Cov}(D_0,D_1).
\]

Si la covarianza es positiva, el pareamiento puede reducir sustancialmente la varianza de la diferencia.

El Piloto B debe determinar si esta estrategia realmente ayuda en presencia del campo magnético; no se asume a priori.

## Checklist

- [ ] Congelar `delta_eta` antes de inspeccionar el resultado confirmatorio del Piloto B.
- [ ] Seleccionar previamente los casos/offsets del piloto.
- [ ] Incluir al menos un caso físicamente exigente.
- [ ] Calcular `D_control`, `D_shield`, `eta` y `H_eta`.
- [ ] Comprobar `H_eta <= delta_eta/2`.
- [ ] Calcular la contribución de cada bin a la varianza de las dosis y de `eta`.
- [ ] Si el criterio falla, aumentar `M` prioritariamente en los bins que dominan la varianza.
- [ ] Probar CRN con las mismas seeds y cuantificar la correlación shield/control.
- [ ] Conservar como producción las runs del Piloto B solo si fueron generadas bajo la configuración/protocolo ya congelados.

## Si falla el criterio

No se redefine `delta_eta`.

Se identifica qué términos `W_b^2 V_b` dominan la incertidumbre y se aumenta `M_b` de forma selectiva. Bajo el régimen Monte Carlo:

\[
M_{\rm nuevo}\approx M_{\rm actual}
\left(\frac{H_{\rm actual}}{H_{\rm objetivo}}\right)^2.
\]

## Alternativa más robusta

Realizar el Piloto B con varias seeds completas por shield/control.

Ventaja:
- permite evaluar directamente variabilidad entre pares de runs.

Limitación:
- multiplica el costo; no es necesario si Piloto A ya validó la incertidumbre intra-run y el objetivo aquí es confirmar la precisión del endpoint.

---

# Fase 11 — Elegir estrategia de producción para los tres casos nuevos

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

# Fase 12 — Validar empíricamente el método R=1

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

# Fase 13 — Análisis final por bin

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

# Fase 14 — Construcción del IC95% final

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

# Fase 15 — Comparación min vs max

Con la grilla actual, min/max se simulan en energías distintas.

Por tanto, **no asumir covarianza por reutilización del mismo response kernel**.

## Checklist

- [ ] Tratar inicialmente min/max como estimaciones de transporte separadas.
- [ ] Propagar la incertidumbre de cada espectro independientemente.
- [ ] Si en el futuro se adopta una grilla común, incorporar covarianza por reutilización de responses.

---

# Fase 16 — Comparación blindaje vs control

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

# Fase 17 — Comprobación final de robustez del binning

## Objetivo

Confirmar que la decisión tomada en la Fase 8 sigue siendo adecuada en el conjunto final de resultados y que no aparece una sensibilidad inesperada del endpoint principal al refinamiento energético.

Esta fase **no sustituye** la validación temprana del binning. Es una comprobación adicional de robustez antes del manuscrito.

## Checklist

- [ ] Verificar que el binning usado en producción coincide con el validado.
- [ ] Repetir 8→16 o 16→32 en uno o más casos adicionales si los resultados finales muestran regiones especialmente sensibles.
- [ ] Reportar el cambio relativo en dosis.
- [ ] Reportar el cambio en `eta`.
- [ ] Confirmar que el error de discretización permanece por debajo del presupuesto definido.
- [ ] Si aparece una discrepancia importante, ampliar el estudio de convergencia energética y no ocultar la sensibilidad.

## Alternativa más robusta

Realizar sistemáticamente:

\[
8\rightarrow16\rightarrow32
\]

en varios casos representativos.

Limitación:

- costo computacional elevado.

# Fase 18 — Incertidumbres sistemáticas y análisis de sensibilidad

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

# Fase 19 — Multiplicidad y endpoints del paper

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

# Fase 20 — Reproducibilidad y semillas

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

# Fase 21 — Despliegue seguro de los cambios hechos hoy

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

# Fase 22 — Secuencia operativa recomendada desde hoy

## Etapa A — Consolidar el barrido existente

- [ ] Sincronizar todos los resultados `done`.
- [ ] Recalcular `R_b` real.
- [ ] Identificar bins con `R_b=1,2,3,4,5`.
- [ ] Calcular contribución de cada bin a dosis y varianza.
- [ ] Fijar formalmente `delta_eta` y el endpoint primario.
- [ ] Mantener documentados los 67 pending y 4 failed.

## Etapa B — Validar la incertidumbre intra-run

- [ ] Completar `S1`, `S2`, `N`.
- [ ] Validar con datos sintéticos.
- [ ] Ejecutar unas pocas runs instrumentadas.
- [ ] Comparar `SE_within` con `s_between` histórico.
- [ ] Verificar `1/sqrt(M)`.

## Etapa C — Validar el binning antes de optimizar M

- [ ] Seleccionar casos representativos/difíciles.
- [ ] Comparar 8 vs 16 bins.
- [ ] Si es necesario, comparar 16 vs 32.
- [ ] Congelar el binning definitivo.

## Etapa D — Calibrar `M_b` sobre el binning definitivo

- [ ] Obtener `SE_b(M)` en las energías definitivas.
- [ ] Medir `c_b`.
- [ ] Calcular `W_b^2 V_b`.
- [ ] Fijar `M_b`.
- [ ] Documentar los valores antes de continuar.

## Etapa E — Comprobar la precisión shield/control

- [ ] Ejecutar el conjunto mínimo shield/control con los `M_b` definitivos.
- [ ] Calcular `eta`.
- [ ] Calcular `H_eta`.
- [ ] Verificar:

\[
H_{\eta,95}\le\frac{\delta_\eta}{2}.
\]

- [ ] Probar CRN si es compatible.
- [ ] Si falla, aumentar `M_b` solo donde la contribución a la varianza lo justifique.

## Etapa F — Desplegar expansión y ejecutar producción

- [ ] Desplegar soporte `phase`.
- [ ] Añadir `GCR_H/max`, `GCR_He/max`, `SEP_p/min`.
- [ ] Ejecutar la estrategia seleccionada (`R=1` + intra-run, o una alternativa más conservadora).
- [ ] Usar `R=3–5` solo en subconjuntos de validación o cuando el criterio lo requiera.

## Etapa G — Validaciones finales del paper

- [ ] sensibilidad a parámetros físicos;
- [ ] validación contra literatura/caso de referencia;
- [ ] comprobación adicional del binning si aparece sensibilidad;
- [ ] separación explícita de incertidumbre MC, discretización e incertidumbre sistemática.

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

1. **No lanzar todavía el barrido completo de los tres casos nuevos.**
2. Consolidar los resultados históricos y fijar `delta_eta`/endpoint primario.
3. Validar primero el estimador de incertidumbre intra-run.
4. **Adelantar la validación del binning energético.**
5. Congelar 8, 16 o 32 bins según el resultado.
6. Recién entonces calibrar `M_b`.
7. Comprobar que la comparación shield/control cumple:

\[
H_{\eta,95}\le\frac{\delta_\eta}{2}.
\]

8. Solo después iniciar producción definitiva.
9. Utilizar las repeticiones históricas para validar `SE_within`, no como obligación de mantener `R=5` en toda la expansión.
10. Antes del paper, separar claramente:
    - incertidumbre Monte Carlo;
    - error de discretización;
    - incertidumbre del modelo físico.

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


---

# Referencias metodológicas para fijar la escala de `delta_eta`

Estas referencias **informan la escala** de efectos esperables, pero no establecen un `delta_eta` universal:

1. **Battiston et al. / SR2S (2016), _Evaluation of Superconducting Magnet Shield Configurations for Long Duration Manned Space Missions_.** En simulaciones Geant4, la contribución del campo fue ~10% para una configuración de ~6.3 Tm, ~20–25% para una configuración toroidal de 8 Tm y alcanzó ~45% alrededor de 23 Tm; el artículo discute contribuciones del campo del orden de 10–50% dependiendo de la configuración. DOI: `10.3389/fonc.2016.00097`.

2. **NASA NESC Technical Memorandum (2022), comparación de conceptos de blindaje magnético.** Resume resultados de configuraciones SR2S con reducciones field-on/field-off del orden de ~20% a 8 Tm y ~45% a 23 Tm, enfatizando que la reducción es específica de la configuración.

3. **Huo (2026), _Fluence to dose equivalent conversion coefficients for ICRP110 voxel phantoms with aluminum and polyethylene shielding using GEANT4_.** Para blindaje pasivo, las reducciones de dosis equivalente efectiva varían ampliamente según material, espesor, quality factor y modulación solar, aproximadamente desde un dígito porcentual hasta >40%. DOI: `10.1038/s41598-026-54174-z`.

**Interpretación para este proyecto:** `delta_eta = 10 pp` es un umbral de resolución ingenieril razonable para la comparación primaria shield/no-shield porque está cerca del extremo inferior de efectos magnéticos publicados. No debe describirse como un umbral clínico/biológico universal.
