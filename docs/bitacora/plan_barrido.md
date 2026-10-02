# Barrido corregido: especificación técnica y de cálculo

Especificación del barrido que reemplaza al de 600 (invalidado por la
auditoría del 2026-09-30). **No empieza hasta cumplir la condición de
`plan_piloto.md`.** Los valores marcados como *(P#)* o *(D#)* los fija ese
piloto o esa decisión (sección 9).

## 1. Configuración física a congelar después de los pilotos

| Elemento | Valor | Fuente |
|---|---|---|
| Physics list | `Shielding` + `G4StepLimiterPhysics` | `ICRP110phantoms.cc` |
| Nave | cilindro G4_Al, radio 4.5 m, semilongitud 5 m, casco 1.5 cm; cabina de aire 0.001 g/cm³ | `run_organ_sweep.py` |
| Bobinas | `field/production/crewhat_corc_array.gdml` (radio 5.67–10.34 m, z ±4.34 m) | GDML versionado |
| Campo | mapa Elmer del dominio aprobado en P1, global, B=0 fuera del mapa | *(P1)*, sha256 en procedencia |
| Esfera fuente | radio aprobado en P1 | *(P1)* |
| Dirección de entrada | ley coseno respecto a la normal interior | D1 |
| Fantoma | ICRP110 AM (y AF si D5) | *(D5)* |
| Malla de scoring | alineada con el fantoma: `translate/xyz {offset_x_mm} 0 0`; dimensiones propias de cada sexo (AM: 254×127×222, 2.137×2.137×8 mm) | plantillas |
| Posiciones | *(D6)*; hoy 0–4 m sobre +x | |
| Límite de longitud de traza | 3·2·R_esfera en `MagnetEnvelope`, con contador de trazas cortadas | R6 |

Cualquier cambio físico de esta tabla después de empezar define otra
configuración: conservar sus datos separados y revalidar antes de combinarlos.
El control magnético conserva nave y bobinas con `fieldScale=0`.

## 2. Muestreo de la fuente y normalización

**Muestreo:** posición uniforme sobre la esfera de radio R, con normal
**n**; dirección **d** = −cosα·**n** + sinα(cosψ·**u** + sinψ·**v**), con
cosα = √ξ₁ y ψ = 2πξ₂ (ley coseno: densidad de cosα igual a 2cosα).

**Peso físico:** para un flujo omnidireccional Φ(E) isótropo (partículas
por cm², por día en GCR y por evento en SEP), la tasa de partículas que
entran a una superficie convexa es (Φ/4)·4πR² = πR²Φ. Cada primario
simulado representa entonces πR²·Φ/N partículas reales.

**Verificado (2026-09-30 y 2026-10-01):**
- **Monte Carlo independiente:** fluencia uniforme igual a N/(πR²), con
  error ≤2.5% en x = 0–4 m.
- **Dentro de Geant4:** cruces de una caja de prueba igual a 1.010 ± 0.020
  del valor esperado.

Detalle en `plan_piloto.md`.

**Unidades:**

| Caso | Unidad del espectro | Unidad de la dosis |
|---|---|---|
| GCR | partículas/(MeV/n·día·cm²) | por día |
| SEP | partículas/(MeV/n·cm²) | por evento completo; GCR y SEP no se suman |

Para alfas, la energía del generador es MeV/n × 4 y el espectro se
integra en MeV/n.

## 3. Integración espectral (curva de respuesta)

**Respuesta por punto:** R_j es la dosis por primario en el punto de
energía E_j (Gy/primario), para un órgano o categoría, posición y
configuración dados.

**Interpolación lineal en ln E** (lineal en R_j, admite R_j = 0): para
E_j ≤ E ≤ E_{j+1}, con t = ln(E/E_j)/ln(E_{j+1}/E_j),

```
R(E) = (1−t)·R_j + t·R_{j+1}
```

Esto define funciones base h_j(E) ("sombreros" en ln E), con Σ_j h_j = 1.

**Dosis del caso s:**

```
D_s = Σ_j w_sj · R_j,     w_sj = πR² ∫ h_j(E) Φ_s(E) dE
```

- Los pesos w_sj **no dependen de la simulación**: se precalculan
  integrando numéricamente el producto h_j·Φ_s (Φ_s lineal a trozos entre
  los puntos de OLTARIS, como en `energy_bins.py`), con una subdivisión
  fina y verificada (sección 8, T7).
- **Fuera de la grilla:** no extrapolar automáticamente ni imponer cero
  por ausencia de depósitos. Validar las colas mediante transporte o una
  cota de su contribución a la dosis contra D3. La fracción de flujo omitida
  por sí sola no acota la dosis; si la cota no basta, ampliar la grilla.
  El test T7 se aplica al intervalo cubierto por las funciones base; las
  colas se contabilizan por separado.
- **Esquema alternativo** (log-log, si P4 lo prefiere): no es lineal en
  R_j, así que su varianza se propaga por el método delta.
- **Si un caso usa grilla propia** (bins constantes por tramos, salida
  posible de P4): w_sj = πR²·∫_bin Φ_s y R_j es la respuesta muestreada
  en el bin con la energía distribuida según Φ_s (R8).

## 4. Magnitudes dosimétricas

- **Dosis absorbida por órgano o categoría:** D_T = Σ edep / m_T. Para
  categorías, la energía de cada evento se suma entre sus órganos antes de
  acumular (R1). Médula ósea roja: e = Σ_o f_o·e_o, con f_o la fracción de
  médula roja de `*_spongiosa.dat`.
- **Dosis equivalente con Q(L)** (ICRP 60, recomendada para astronautas
  por ICRP 123): H_T = Σ_pasos edep·Q(L) / m_T, con L el LET no restringido
  en agua, en keV/µm:
  - Q = 1 si L < 10;
  - Q = 0.32L − 2.2 si 10 ≤ L ≤ 100;
  - Q = 300/√L si L > 100.

  Se guarda además la energía por órgano en bins de LET, para poder
  aplicar otras funciones de calidad en el post-proceso.
- **Dosis equivalente con w_R de ICRP 103** (por especie primaria): solo
  para comparar con el barrido viejo.
- **Magnitud ponderada por tejidos con Q(L)** (dosis equivalente efectiva
  en la terminología espacial; si D5 incluye AF):
  `E = Σ_T w_T · (H_T^AM + H_T^AF)/2`, con los w_T de ICRP 103:
  - 0.12: médula ósea roja, colon, pulmón, estómago, mama y restantes;
  - 0.08: gónadas;
  - 0.04: vejiga, esófago, hígado y tiroides;
  - 0.01: superficie ósea, cerebro, glándulas salivales y piel.

  La suma da 1.00.

  **Restantes:** media **aritmética** de 13 órganos por sexo (suprarrenales,
  región extratorácica, vesícula biliar, corazón, riñones, ganglios
  linfáticos, músculo, mucosa oral, páncreas, próstata ♂ o útero ♀,
  intestino delgado, bazo y timo). **Mama:** tejido glandular. **Colon:**
  ICRP 103 lo define como media ponderada del intestino grueso superior e
  inferior; verificar los pesos exactos en ICRP 103 antes de implementar.
  Implementar la tabla en un módulo con tests contra la suma de w_T y la
  lista de órganos.

  Etiquetar esta magnitud por su definición Q(L): no confundirla con la
  dosis efectiva de ICRP 103 basada en w_R. ICRP 123 distingue el enfoque
  espacial con Q del sistema general con w_R
  ([fuente](https://www.icrp.org/publication.asp?id=ICRP+Publication+123)).
  La aproximación de médula `Σ f_o e_o` supone igual dosis en los
  componentes de espongiosa; no es dosimetría esquelética validada. P0 debe
  comprobarla por separado antes de tratarla como referencia para médula.

## 5. Estimadores estadísticos

**Por punto j** (para cada órgano o categoría), con N_j primarios
**simulados**, incluidos los que no depositan nada, y e_i la energía
(ponderada por el peso de traza) del evento i:

```
R̂_j   = S1 / (m · N_j)                         S1 = Σ e_i,  S2 = Σ e_i²
s_j²  = (S2 − S1²/N_j) / (N_j − 1)
Var(R̂_j) = s_j² / (m² · N_j)
```

El scorer de `ICRP110.out` cuenta en N solo los eventos con depósito y
acumula por voxel. **Scorer nuevo implementado (2026-10-01):** comandos
`/eventStats/*` (`EventStatsRunAction.cc`). Suma el depósito de cada evento
por órgano y por categoría antes de acumular S1/S2, cuenta en M todos los
primarios y escribe, por checkpoint, S1–S4, eventos con depósito, mayor
contribución de un solo evento y la VOV de MCNP (autodiagnóstico del SE; ver
`metodo_autodiagnostico_incertidumbre.md`). Opcionalmente escribe los totales por evento
de las categorías (R12) y cuenta las trazas cortadas por el límite de
longitud (R6). Las categorías salen de `scripts/write_event_categories.py`,
la misma definición que usa el agregador. Aún no se usa en
`run_organ_sweep.py` ni en los pilotos históricos.

**Por caso** (puntos con semillas distintas, independientes):

```
Var(D_s)       = Σ_j w_sj² · Var(R̂_j)
Cov(D_s, D_s') = Σ_j w_sj · w_s'j · Var(R̂_j)   (casos que comparten la curva)
```

Esta covarianza es obligatoria al comparar casos (por ejemplo, mínimo
frente a máximo solar, Fase 15).

**Escudo frente a control:** η = 1 − D₁/D₀, con

```
Var(η) ≈ V₁/D₀² + D₁²·V₀/D₀⁴ − 2·D₁·C₀₁/D₀³
```

Esta forma evita dividir por D₁=0. Si D₀ no está separado de cero, el método
delta no está justificado; usar un intervalo de razón apropiado (p. ej.
Fieller) o declarar el contraste inconcluso, sin forzar un IC finito.

Con CRN se exige identidad del primario por `event_id` (especie, energía,
posición, dirección y peso), verificada en un test. Geant4 MT asigna semillas
por evento, pero la misma semilla maestra no prueba por sí sola esa identidad
para cualquier modo de ejecución, configuración del RNG o generador.
C₀₁ se estima con pares alineados por ID, nunca por orden de escritura.
Para N pares independientes en un punto, `Cov(R̂₀,R̂₁)=cov(x₀,x₁)/N`,
donde x son las contribuciones de dosis por evento; luego se pondera por
w_j² y se suma sobre puntos independientes.
Para eso hace falta que el scorer guarde **los totales por evento de las
categorías** (requisito adicional R12: un archivo de N × categorías).
Referencia: [modelo MT de Geant4](https://geant4.web.cern.ch/documentation/pipelines/master/bftd_html/ForToolkitDeveloper/OOAnalysisDesign/Multithreading/mt.html).

**Intervalos:** normal con 1.96·SE si P2 valida el estimador y N es
grande; t de Student si la varianza viene de pocas repeticiones (Fase 14).
M grande no basta con depósitos raros: exigir los diagnósticos de P3.
La varianza del endpoint ponderado se calcula sobre el total por evento,
o con toda la matriz de covarianzas entre órganos; sumar solo varianzas
de órganos omite las correlaciones de una misma cascada. Para AM y AF
independientes, `Var((H_AM+H_AF)/2)=(Var(H_AM)+Var(H_AF))/4`.
No publicar IC total si falta un punto o una varianza; R=1 requiere un
estimador por evento validado. Fijar tamaño y evaluaciones antes de la
confirmación para evitar selección por parada opcional.

**Equivalencia (P1, P4, P5):** se aprueba si el IC95 de la diferencia cae
completo dentro de ±B (equivale a dos pruebas unilaterales con α = 2.5%
cada una).

**Multiplicidad:** endpoints primarios definidos en D2; los demás se
reportan como secundarios con IC, sin interpretar la cobertura conjunta
(Fase 19).

## 6. Asignación de eventos

1. **Piso por punto:** M_j ≥ M_min,j *(P3)*: el menor M donde pasan los
   diagnósticos de convergencia (D4).
2. **Asignación eficiente:** minimizar el costo total Σ_j c_j·M_j sujeto a
   Var(D_s) ≤ V*_s para todos los casos s y categorías primarias, donde
   V*_s sale de H ≤ criterio. Es un problema convexo y se resuelve
   numéricamente.
   - **Forma cerrada** para un objetivo ponderado: M_j ∝ σ_j·√(Σ_s λ_s·w_sj²) / √c_j.
   - **Un solo caso:** se reduce a la de la Fase 9, M_j ∝ |w_j|·σ_j / √c_j.
3. **Verificación con η:** P6 confirma con η que la asignación alcanza.

Ningún punto queda por debajo de su piso, cueste lo que cueste.

## 7. Cómputo distribuido

**Trabajo:** `(partícula, grilla, índice de energía, posición, fieldScale,
sexo, repetición)`. Requiere una tabla nueva en el coordinator; no se
reutilizan `jobs` ni `jobs_v2`.

**Semillas v2:**
- seed1 = BASE_V2 + 2·k y seed2 = seed1 + 1, con k asignado en un registro
  versionado e inmutable de claves de trabajo. Nuevas claves reciben índices
  al final del registro, sin reenumerar productos cartesianos: agregar una
  posición a un bucle interno desplaza los trabajos siguientes.
- BASE_V2 distinta de las bases históricas y de las de los pilotos.
- En escudo y control, el mismo k para el mismo punto: así se implementa
  la CRN.
- Un test verifica unicidad entre trabajos independientes y pilotos,
  rango permitido por el RNG y repetición intencional solo en parejas CRN
  declaradas o retries del mismo trabajo (no nuevas réplicas).

**Procedencia exigida** en la salida y en el manifiesto; el coordinator
rechaza con 422 los resultados que no la traigan o que no coincidan:
- commit de git y hash del binario;
- sha256 del mapa y del GDML;
- modo angular y radio de la esfera;
- physics list, sexo, M y semillas;
- número de hilos y versión de Geant4.

**Worker:** imagen nueva construida desde el commit congelado. Los workers
con código viejo deben fallar de forma explícita (el macro trae comandos
nuevos).

**Agregación:**
- un solo script versionado, con control de duplicados (ya implementado);
- rechazo de mezclas de grilla o de procedencia;
- salida con contribución de cada punto a la dosis y a la varianza
  (Fase 13);
- salida de R̂_j y Var(R̂_j) por punto, órgano o categoría, posición y
  configuración, no solo de D_s: la necesita el post-proceso temporal
  (sección 10) y cualquier otro espectro que se quiera aplicar después.

## 8. Verificaciones automáticas (tests)

| # | Test | Qué protege |
|---|---|---|
| T1 | Distribución de cosα de los primarios = 2cosα (prueba KS con un macro de geantinos) | Muestreo angular |
| T2 | Caja de prueba: cruces / esperado dentro de 3σ (hoy 1.010 ± 0.020) | Normalización πR² |
| T3 | Sin campo: dosis en x=1 m equivalente a x=0 | Alineación de la malla |
| T4 | Scorer por evento: S1 igual a la edep total; N igual a los primarios; S1/S2 de categoría iguales a los del archivo por evento; checkpoints acumulados | Estimador R1. **Implementado:** `tests/scorer_por_evento/test_t4_t5.py` (ctest `event_stats`). La comparación de la varianza con la dispersión entre semillas es la prueba exploratoria de P2, no un test |
| T5 | `ICRP110UserScoreWriter` divide por `joule` y agrega por órgano solo los depósitos de energía; otras magnitudes se vuelcan en su unidad | Unidades. **Implementado** (mismo test que T4) |
| T6 | Agregador: dosis por primario (sin factor N), duplicados, energía fuera de grilla, N inconsistente, grillas mezcladas | **Implementado:** `tests/python/test_agregador_y_pesos.py`. Falta el caso de bins o puntos ausentes |
| T7 | Σ_j w_sj / (πR²) = ∫Φ_s en el rango, con error relativo menor que 1e-6 | Pesos espectrales. **Implementado** para la grilla actual de bins (mismo archivo que T6); repetir con las funciones base de la curva de respuesta cuando existan |
| T8 | Unicidad de semillas | Independencia |
| T9 | El coordinator rechaza resultados sin procedencia válida | Mezcla de versiones |
| T10 | Mismos primarios por event_id con CRN; reproducibilidad con binario/entorno/RNG fijados y tolerancia documentada para reducciones flotantes MT | Reproducibilidad |
| T11 | Tabla de w_T: la suma da 1 y los órganos coinciden con la lista de ICRP 103 | Dosis efectiva |
| T12 | Perfil temporal de SEP: Σ_k Φ(E, t_k)·Δt reproduce la fluencia del evento usada en la sección 2, y la dosis acumulada final iguala a D_s del evento completo | Post-proceso temporal (sección 10) |

## 9. Parámetros pendientes

| Parámetro | Lo fija |
|---|---|
| Radio de la esfera y dominio del mapa de campo | P1 |
| Puntos de energía por partícula, esquema de interpolación y grillas propias por caso, si hacen falta | P4 |
| M_min,j y c_j | P3 |
| M_j finales | P3 + P6 |
| Uso de CRN | P6 |
| Parámetros del sesgo de fuente | P5 |
| Validez de R=1 | P2 |
| Presupuesto B, umbrales de convergencia, tolerancia de P0 | D3, D4, D7 |
| Endpoint primario y δ_η | D2 |
| AF | D5 |
| Posiciones | D6 |
| Fuente del perfil temporal de cada SEP y modelo de espectro por intervalo | D8 |

**Estimación de costo:** Σ_trabajos (c_j·M_j + ~45 s de inicialización),
con c_j de P3. No se da un número antes de P3.

## 10. Post-proceso temporal de SEP (tasa de dosis)

La sección 2 da la dosis SEP del evento completo. Para obtener la tasa de
dosis, su pico, la dosis acumulada en el tiempo o la peor ventana de 24 h,
no hace falta simular de nuevo: R̂_j no depende del espectro, así que basta
con cambiar los pesos.

**Cálculo:** con el espectro omnidireccional Φ(E, t_k) del intervalo k
(partículas/(MeV/n·cm²·s)) y duración Δt_k,

```
w_j(t_k) = πR² ∫ h_j(E) Φ(E, t_k) dE
Ḋ(t_k)   = Σ_j w_j(t_k) · R̂_j                 (Gy/s en el intervalo k)
D(t)     = Σ_{k: t_k ≤ t} Ḋ(t_k) · Δt_k        (dosis acumulada)
```

La dosis por día de un SEP se reporta como esta curva (o su máximo en una
ventana de 24 h). La dosis total dividida por la duración del evento no
se usa: esconde el pico.

**Incertidumbre:** todos los intervalos usan las mismas R̂_j, así que sus
errores están correlacionados y no se suman en cuadratura por intervalo:

```
Cov(Ḋ_k, Ḋ_l) = Σ_j w_j(t_k) · w_j(t_l) · Var(R̂_j)
Var(D(t))     = Σ_j [Σ_{k: t_k ≤ t} w_j(t_k)·Δt_k]² · Var(R̂_j)
```

A esto se suma la incertidumbre del propio perfil temporal (calibración del
instrumento y ajuste del espectro), que no es Monte Carlo y se reporta por
separado.

**Espectro por intervalo** (D8):

- **Forma variable (preferida):** ajustar un espectro en cada intervalo a
  los canales de energía disponibles. Un SEP real cambia de forma durante
  el evento (en general se endurece al inicio y se ablanda al final).
- **Forma constante (aproximación):** escalar el espectro OLTARIS del
  evento con un solo canal integral, Φ(E, t) = f(t)·Φ_OLTARIS(E). Si se usa,
  se reporta como aproximación.
- En ambos casos, la fluencia integrada en el tiempo tiene que reproducir
  la fluencia del evento usada en la sección 2 (test T12), o se documenta
  la diferencia y su causa.

**Datos a verificar antes de implementar** (D8):

- **Octubre de 1989:** flujos de protones de GOES. Confirmar qué satélites,
  canales (integrales o diferenciales), cadencia y calibración existen para
  esa fecha.
- **Febrero de 1956:** anterior a los satélites. Solo hay monitores de
  neutrones en tierra, así que su perfil temporal no puede salir de GOES.
  Decidir si ese caso se queda solo con la dosis del evento completo.
- **Unidades:** GOES reporta intensidad por estereorradián. El paso a flujo
  omnidireccional supone isotropía y hay que comprobarlo contra la
  definición de cada canal, igual que en la sección 2.
- **Órbita:** GOES está en órbita geoestacionaria, dentro de la
  magnetosfera. Evaluar si el blindaje geomagnético afecta a los canales de
  menor energía antes de usarlos como flujo interplanetario.

**Requisitos:**

- el agregador guarda R̂_j y Var(R̂_j) por punto (sección 7);
- la grilla de protones tiene que estar validada también para los
  espectros extremos del evento (criterio adicional de P4 en
  `plan_piloto.md`).
