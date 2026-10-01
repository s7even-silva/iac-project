# Barrido corregido: especificación técnica y de cálculo

Especificación del barrido que reemplaza al de 600 (invalidado por la
auditoría del 2026-09-30). **No empieza hasta cumplir la condición de
`plan_piloto.md`.** Los valores marcados como *(P#)* o *(D#)* los fija ese
piloto o esa decisión (sección 9).

## 1. Configuración física congelada

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

Cualquier cambio de esta tabla después de empezar invalida el barrido.

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
- **Fuera de la grilla:** por debajo de E_1, R = 0, solo si P4 confirma que
  E_1 está bajo el umbral de penetración. Por encima de E_n, R = R_n, y se
  reporta la fracción del flujo afectada.
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
- **Dosis efectiva** (si D5 incluye AF):
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

## 5. Estimadores estadísticos

**Por punto j** (para cada órgano o categoría), con N_j primarios
**simulados**, incluidos los que no depositan nada, y e_i la energía
(ponderada por el peso de traza) del evento i:

```
R̂_j   = S1 / (m · N_j)                         S1 = Σ e_i,  S2 = Σ e_i²
s_j²  = (S2 − S1²/N_j) / (N_j − 1)
Var(R̂_j) = s_j² / (m² · N_j)
```

El scorer de hoy cuenta en N solo los eventos con depósito y acumula por
voxel. El nuevo tiene que contar todos los primarios (R1).

**Por caso** (puntos con semillas distintas, independientes):

```
Var(D_s)       = Σ_j w_sj² · Var(R̂_j)
Cov(D_s, D_s') = Σ_j w_sj · w_s'j · Var(R̂_j)   (casos que comparten la curva)
```

Esta covarianza es obligatoria al comparar casos (por ejemplo, mínimo
frente a máximo solar, Fase 15).

**Escudo frente a control:** η = 1 − D₁/D₀, con

```
Var(η) ≈ (D₁/D₀)² · [V₁/D₁² + V₀/D₀² − 2·C₀₁/(D₀·D₁)]
```

Con CRN, el evento k usa la misma semilla en ambas configuraciones: en MT,
Geant4 genera las semillas por evento desde la semilla maestra, así que el
primario k es idéntico en las dos. C₀₁ se estima con los pares por evento.
Para eso hace falta que el scorer guarde **los totales por evento de las
categorías** (requisito adicional R12: un archivo de N × categorías).

**Intervalos:** normal con 1.96·SE si P2 valida el estimador y N es
grande; t de Student si la varianza viene de pocas repeticiones (Fase 14).

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
- seed1 = BASE_V2 + 2·k y seed2 = seed1 + 1, con k el índice del trabajo en
  la enumeración determinista del conjunto completo (las posiciones
  nuevas se agregan al final).
- BASE_V2 distinta de las bases históricas y de las de los pilotos.
- En escudo y control, el mismo k para el mismo punto: así se implementa
  la CRN.
- Un test verifica que todas las semillas sean únicas en el barrido y en
  los pilotos.

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
  (Fase 13).

## 8. Verificaciones automáticas (tests)

| # | Test | Qué protege |
|---|---|---|
| T1 | Distribución de cosα de los primarios = 2cosα (prueba KS con un macro de geantinos) | Muestreo angular |
| T2 | Caja de prueba: cruces / esperado dentro de 3σ (hoy 1.010 ± 0.020) | Normalización πR² |
| T3 | Sin campo: dosis en x=1 m equivalente a x=0 | Alineación de la malla |
| T4 | Scorer por evento: S1 igual a la edep total; N igual a los primarios; varianza igual a la de lotes | Estimador R1 |
| T5 | Magnitudes nuevas volcadas por `ICRP110UserScoreWriter`: corregir su división por `joule` (hoy la aplica a toda magnitud volcada) | Unidades |
| T6 | Agregador: dosis por primario (sin factor N), duplicados, bins o puntos ausentes, grillas mezcladas | Ya corregido; añadir tests |
| T7 | Σ_j w_sj / (πR²) = ∫Φ_s en el rango, con error relativo menor que 1e-6 | Pesos espectrales |
| T8 | Unicidad de semillas | Independencia |
| T9 | El coordinator rechaza resultados sin procedencia válida | Mezcla de versiones |
| T10 | Mismas semillas producen el mismo resultado bit a bit | Reproducibilidad |
| T11 | Tabla de w_T: la suma da 1 y los órganos coinciden con la lista de ICRP 103 | Dosis efectiva |

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

**Estimación de costo:** Σ_trabajos (c_j·M_j + ~45 s de inicialización),
con c_j de P3. No se da un número antes de P3.
