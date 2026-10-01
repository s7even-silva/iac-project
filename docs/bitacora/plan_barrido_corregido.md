# Plan del barrido corregido (propuesta, 2026-09-30)

Contexto: la auditoría del 2026-09-30 (`auditoria_2026-09-30.md`) dejó sin
ninguna dosis físicamente válida. La malla de scoring no seguía al fantoma
y todos los primarios apuntaban al origen. Hay que volver a simular todo.
Este documento propone cómo hacerlo aprovechando el plan estadístico
(`plan_estadistico.md`) y lo aprendido. **Todo esto es propuesta: ninguna
de las decisiones marcadas como pendientes está tomada.**

Principio: como hay que volver a correr todo de cualquier forma, ya no
aplica el argumento del plan para no cambiar el diseño a mitad del
barrido ("costo de revalidación", Fase 0, alternativa B). Es el momento de
adoptar las opciones más eficientes y robustas.

## 1. Cambios obligatorios antes de cualquier corrida

1. **Ley coseno como default** (`/gun/angularDistribution cosine`, ya
   implementado como opción).
2. **Malla de scoring que siga al fantoma** (ya corregido en las plantillas).
3. **Scorer nuevo** (requisitos R1–R11 de la auditoría). El mínimo para
   producción:
   - R1, acumulación por evento: da el error estándar correcto y permite
     R=1 por corrida;
   - R2, Q(L) más espectro de LET por órgano;
   - R5, pesos de traza (G4PSEnergyDeposit ya multiplica por el peso;
     comprobado en el código fuente de Geant4);
   - R6, contadores de trazas cortadas;
   - R9, procedencia.

   Recomendados: R3 (tipo de partícula), R4 (origen del secundario), R11
   (tiempo por evento). Opcional: R7 (fluencia alrededor del fantoma).
4. **Coordinator:** exigir procedencia (rechazar resultados sin commit,
   hash del binario y modo angular) y un esquema de semillas versionado
   sin colisiones. La fórmula actual admite como máximo 500 combinaciones;
   hay una guarda que aborta.

## 2. Energías: núcleo de respuesta por partícula (recomendado)

La Fase 0, alternativa B del plan estadístico, propuso una grilla común
para reutilizar respuestas entre espectros. Ahora conviene llevarla más
lejos: calcular una **función de respuesta R(E)** por partícula en una
grilla de energías fijas, e integrar cada espectro después:

```
D_s = ∫ R(E) Φ_s(E) dE    (R interpolada en log-log entre los puntos de la grilla)
```

- **Protones:** un solo núcleo sirve para GCR_H min, GCR_H max, SEP_p max
  (octubre de 1989) y SEP_p min (febrero de 1956).
- **Alfas:** un solo núcleo sirve para GCR_He min y max.
- **Los 6 casos especie/fase salen del post-proceso sin transporte extra.**
  Eso resuelve la decisión pendiente de "expandir de 3 a 6 casos".

**Grilla no uniforme.** El casco de 1.5 cm de Al (≈4 g/cm²) frena protones
y alfas por debajo de ~70 MeV/nucleón. La Fase 8 (con apuntado radial)
encontró que el 99% de la dosis de SEP está entre 65 y 300 MeV, y que el
binning log-uniforme no converge para SEP_p ni con 128 bins. Propuesta
inicial, a validar:

| Partícula | Rango | Puntos |
|---|---|---|
| Protón | 0.01–50 MeV | 3 (solo confirmar que la dosis es ~0) |
| Protón | 50–500 MeV | 10 (zona de SEP y del corte del escudo) |
| Protón | 0.5–300 GeV | 8 |
| Alfa | 10–50 MeV/n | 2 |
| Alfa | 50–500 MeV/n | 8 |
| Alfa | 0.5–100 GeV/n | 6 |

Son unos 21 puntos de protón y 16 de alfa. La interpolación de R(E) tiene
error de segundo orden, frente al de primer orden del valor constante por
bin que se usa hoy.

**Validación (equivale a la Fase 8):** en x=0, comparar la grilla N contra
una grilla 2N intercalada (que reutiliza los N puntos ya corridos) para
los 6 espectros. Presupuesto: el de la Fase 8 (≤2.5 pp en el endpoint).

**Alternativa:** muestrear la energía dentro de cada bin según el
espectro (requisito R8). No tiene error de discretización, pero ata cada
corrida a un solo espectro: pierde la reutilización entre los 6 casos,
salvo que se guarde la energía de cada evento y se repondere después.

## 3. Configuraciones

- **Posiciones:** las 5 actuales (0–4 m). Recortarlas sigue siendo una
  opción del equipo, no una necesidad.
- **Escudo frente a control:** el endpoint primario del plan es
  η = 1 − D_escudo/D_control. Hace falta el control, con `fieldScale 0` y
  las bobinas presentes para aislar el efecto magnético. Usar las mismas
  semillas en ambos (CRN, Fase 10) y medir si la correlación reduce la
  varianza de η.
- **Fantoma:** AM. AF (requisito R10) solo en las configuraciones que se
  reporten, o completo si el equipo decide reportar dosis efectiva.

Total con la grilla propuesta: (21 + 16) energías × 5 posiciones × 2
(escudo/control) = **370 trabajos** con AM. Con el esquema anterior,
cubrir 6 casos habría sido 6 × 8 × 5 × 2 = 480 trabajos con 8 bins, y
SEP_p necesitaba 64 o más.

## 4. Número de eventos por punto (Fase 9)

`M_b ∝ |W_b| σ_b / √c_b`, con:

- `W_b`: peso de cada punto, como el máximo de su contribución sobre los
  espectros que lo usan;
- `σ_b`: del scorer por evento;
- `c_b`: costo por evento medido.

**Referencia de costo real:** el barrido de 600 (apuntado radial, 10000
eventos, máquinas voluntarias heterogéneas) sumó unas **58 h por
repetición** (120 corridas). Dominan las energías más altas: GCR_He bin 7
~5 h por corrida, bin 6 ~2 h; GCR_H bin 7 ~1.3 h. Esos puntos pesan poco en
la dosis, que es justo donde `M_b` ahorra más.

Con ley coseno el costo por evento cambia: llegan menos primarios al
fantoma, pero más chocan con las bobinas. En las pruebas del 2026-09-30
(7 hilos) se midieron ~8 ms/evento a 562 MeV con campo y ~36 ms/evento a
1.8 GeV sin campo. **No hay medición todavía en las energías altas**, así
que no es posible dar un tiempo total confiable. Hace falta el piloto de
costo (paso 2 del orden propuesto).

## 5. Reducción de varianza

Con ley coseno, solo ~0.3% de los primarios cruza el fantoma.

- **Sesgo de la fuente dependiente de la energía (recomendado).** A alta
  energía las trayectorias casi no se curvan: muestrear direcciones
  preferentemente hacia el fantoma y asignar el peso
  `pdf_real/pdf_sesgada`. Es insesgado, y la ganancia es grande justo en
  los puntos más caros. A baja energía, donde el campo desvía, se mantiene
  la ley coseno sin sesgo.
- **Dos etapas** (espacio de fases en una superficie alrededor del
  casco): la etapa 1, que es la cara por las cascadas en las bobinas, se
  reutiliza para las 5 posiciones y para AM/AF. Es más compleja; evaluarla
  si el piloto de costo muestra que la etapa de bobinas domina.
- **Monte Carlo inverso: descartado.** Geant4 solo tiene procesos adjuntos
  electromagnéticos, sin física hadrónica.

## 6. Geometría de la fuente y del campo (decisión pendiente)

La esfera fuente (6.94 m) corta las bobinas, y el mapa se trunca con
0.16–0.40 T en sus caras (frontera `AV=0`). Hay dos opciones:

- **(a)** Producir con la esfera actual y documentarlo como limitación.
- **(b)** Ampliar antes el dominio Elmer: dimensionarlo con Biot-Savart,
  correrlo en una máquina con más de 8 GB de RAM, re-exportar el mapa y
  agrandar la esfera.

(b) es más correcta, pero tiene que hacerse antes de la producción: cambiar
el mapa después invalida todo de nuevo.

## 7. Estadística

- R=1 por punto, con el error estándar intra-run del scorer por evento
  (Fase 11, opción A).
- Subconjunto de validación con R=3 en una posición (Fases 7/12, ahora
  con el estimador exacto).
- IC por propagación `V(D) = Σ W_b² V_b` (Fases 13/14) y criterio
  H_η,95 ≤ 5 pp (Fases 1/10).

## Orden propuesto

1. Decisiones del equipo: ley coseno como default, opción (a) o (b) de la
   sección 6, grilla de energías, AF sí o no, endpoint primario y δ_η.
2. Cambio de C++ (scorer R1–R11, sesgo de fuente) con tests, más el
   coordinator (procedencia, semillas v2, tabla de trabajos con
   `(partícula, energía, grilla, posición, fieldScale, sexo, rep)`) y una
   imagen nueva de worker.
3. Piloto de costo: ~10 energías × 1000 eventos, x=0, escudo, en local.
   Da `c_b`.
4. Piloto de σ y de grilla: N frente a 2N en x=0. Da `M_b` y valida la
   grilla.
5. Sembrar la producción en el coordinator y correrla.
6. Validación R=3, análisis con η, y repetir la Fase 7 con el estimador
   nuevo.
