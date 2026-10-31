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
   [`plan_estadistico.md`](https://github.com/s7even-silva/iac-project/blob/v1-archivo/docs/bitacora/plan_estadistico.md), v1).

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
| D2 | Endpoint primario y δ_η. **Decidido (2026-10-31): δ_η = 10 pp; primario, la dosis equivalente efectiva con Q(L) (ICRP 123); secundario, la médula roja.** Ver «Endpoint (D2)» abajo | P5, P6 |
| D3 | Presupuesto B de error de dosis por caso especie/fase y por categoría, para las pruebas de equivalencia. **Decidido (2026-10-31): B = δ_η/4 = 2.5% de la dosis sin escudo** | P1, P4, P5 |
| D4 | Umbrales de los diagnósticos de convergencia. **Decidido (2026-10-31): al menos 200 eventos con depósito, VOV < 0.1 y ningún evento con más del 10% del total**, por categoría. Criterio de P2 en P2 | P2, P3 |
| D5 | Fantoma AF sí o no (dosis efectiva completa). **Sí (2026-10-31)**, lo pide el endpoint de D2. Cómo correrlo sin duplicar todo: propuesta de simulación en dos etapas (P7) | Diseño del barrido |
| D6 | Posiciones (las 5 actuales u otra elección) | P1, P6, barrido |
| D7 | Tolerancia con ICRP 116 para P0. **Decidido (2026-10-31): ±10% en órganos grandes y ±30% en mama y tiroides, a ≥100 MeV/n**: en los dos casos, unas 2 veces el error de la propia referencia (ver «Base de la tolerancia D7» en P0) | P0 |
| D8 | Perfil temporal de SEP: fuente de datos de cada evento (GOES para oct. 1989; feb. 1956 no tiene datos satelitales), forma del espectro variable o constante, y qué casos lo llevan (`plan_barrido.md`, sección 10) | Criterio temporal de P4 y tasa de dosis SEP; no bloquea la dosis del evento completo |
| D9 | Disposición y masa de las bobinas. **Decidido (2026-10-04): producción con la disposición de NIAC** (hallazgo A4 de la auditoría). **Cerrado (2026-10-31):** el sentido de corriente de cada bobina y la sección y densidad del bobinado (B9) quedan como supuestos propios declarados; los autores de NIAC no respondieron. Geometría generada y versionada. Ver «Disposición de las bobinas (D9)» abajo | Mapa de Elmer de P1, D6, barrido |

**Relación entre D2, D3 y D7.** δ_η (D2) es la diferencia mínima de
efectividad escudo/control que el estudio tiene que poder resolver.
δ_η = 10 pp equivale a una diferencia de dosis igual al 10% de la dosis
sin escudo.

- **D3 puede derivarse de D2,** como en [`plan_estadistico.md`](https://github.com/s7even-silva/iac-project/blob/v1-archivo/docs/bitacora/plan_estadistico.md) (v1):
  B = δ_η/4, es decir 2.5 pp con δ_η = 10 pp. Fijar D2 desbloquea
  entonces D3 y con eso P1, P4 y P5.
- **D7 es otra cosa.** Mide la exactitud de la dosis absoluta frente a una
  referencia externa. En η = 1 − D₁/D₀ un error de normalización común a
  escudo y control se cancela, así que D7 afecta sobre todo a los
  resultados absolutos (Gy/día, Sv, riesgo). Afecta a η solo si el error
  depende de la energía y el escudo cambia el espectro.

Los valores de D2, D3 y D4 están además en
`geant4/ActiveShield_Sim/scripts/design_parameters.py`: los scripts de
análisis los importan de ahí y no los repiten.

**Endpoint (D2, decidido 2026-10-31).**
- **Primario:** η de la dosis equivalente efectiva,
  E = Σ_T w_T·(H_T^AM + H_T^AF)/2, con H_T calculada con el Q(L) de ICRP 60
  y los w_T de ICRP 103 (`plan_barrido.md`, sección 4). Es el enfoque que
  ICRP 123 recomienda para astronautas, en lugar de los w_R de ICRP 103.
- **Secundario:** médula roja (equivale a los órganos hematopoyéticos,
  BFO), con su IC95 y sin garantía de precisión.
- **A declarar en el paper:**
  - E no es la dosis efectiva de ICRP 103 (que usa w_R);
  - tampoco es la «NASA effective dose» de NASA-STD-3001, que usa el Q de
    NASA y el modelo femenino de 35 años para ambos sexos. La comparación
    con los límites de NASA (600 mSv de carrera; 250 mSv para el SEP de
    diseño, la suma de los eventos de octubre de 1989) es aproximada;
  - la médula roja se aproxima como Σ f_o·e_o (`plan_barrido.md`).
- **Antecedentes** (detalle en `referencias_paper.md`): NASA-STD-3001
  limita la dosis efectiva; Ferrone (2020, Geant4, fantomas de ambos sexos)
  reporta dosis efectiva; Ambroglini, Battiston y Burger (2016) reportan
  dosis equivalente en BFO y piel. Ninguno declara un δ de diseño. Sus
  reducciones van de ~20% a ~50% según el escudo, con incertidumbres de
  ~3–5% en la dosis. Esas incertidumbres equivalen a un IC95 de η de
  ±6–8 pp, así que δ_η = 10 pp (IC95 de ±5 pp) está a la par o algo por
  encima de su precisión.

**Cambiar δ_η más adelante (procedimiento, 2026-10-31).** El equipo puede
querer bajar δ_η (por ejemplo, a 5 pp). Es válido si se hace así:
1. **Declararlo antes** de ver el resultado que decide, con fecha y
   motivo. Lo que no vale es agregar eventos hasta que algo salga
   significativo (regla 3).
2. **Editar `DELTA_ETA`** en `design_parameters.py`; B = δ_η/4 se recalcula
   solo (1.25% con 5 pp).
3. **Revisar las equivalencias del método con el nuevo B:** radio (P1),
   grilla de energías (P4), sesgo (P5) y resolución del mapa. **Desde hoy
   esos pilotos reportan además el resultado con B = 1.25%**
   (`B_SECONDARY`; chequeo secundario declarado de antemano, que no
   decide): si ya pasan, no hay que rehacerlos.
4. **Si todas pasan, extender el barrido:** corridas nuevas con claves de
   trabajo nuevas al final del registro de semillas (`plan_barrido.md`,
   «Semillas v2»), la misma clave para escudo y control (CRN). Se
   combinan sumando S1, S2 y N. Costo: (δ_viejo/δ_nuevo)² − 1 veces lo ya
   corrido, es decir 3 veces más para pasar de 10 a 5 pp.
5. **Si alguna falla, cambia la configuración congelada:** un radio o un
   mapa nuevos obligan a rehacer el barrido; una grilla más fina solo
   agrega puntos.

Para que el cambio salga barato, conviene elegir desde ahora la
configuración con margen: por ejemplo, el radio que ya pase con 1.25%.

### Disposición de las bobinas (D9, decidido 2026-10-04)

**Decisión.** La producción usa la disposición de CREW HaT tal como la
describe el reporte NIAC, no el patrón Halbach K=1 que se simuló hasta
ahora. El motivo está en el hallazgo A4 de
[`auditoria_2026-09-30.md`](auditoria_2026-09-30.md): K=1 pone un dipolo
uniforme de 0.54 T dentro de la nave, y CREW HaT está diseñado para lo
contrario, un campo suprimido en el hábitat (§2, p. 8 del reporte). K=1
queda como variante de comparación. La masa de las bobinas se corrige a la
vez (hallazgo B9), porque las dos cosas regeneran el GDML.

**Supuestos de la geometría (P1, paso 0).** Se consultó por correo a los
autores de NIAC por el sentido de corriente y la sección; sin respuesta al
2026-10-31, los dos quedan como supuestos propios declarados, a citar así en
el paper.

- **Orientaciones:** las de la fig. 3.1(b) (p. 10), cardinales en planos
  radiales y diagonales en planos tangenciales. Dato de la fuente.
- **Sentido de la corriente de cada bobina:** el reporte no lo da.
  Candidato: θ_k = 90° − φ_k (polaridad que rota en sentido opuesto a la
  posición), la única asignación continua compatible con esas
  orientaciones. En el chequeo exploratorio con Biot-Savart
  (`field/studies/disposicion_bobinas_2026-10-04.py`) da |B| = 0 en el
  centro y 0.013 T de media a 2 m, como pide NIAC. Supuesto propio
  declarado.
  `generate_ellipse_array.py` ya lo admite con `theta_deg_pattern`, sin
  cambiar código.
- **Radio:** 8 m (§3.1, p. 12), el que ya usamos.
- **Sección y masa (B9):** 0.67 m radial × 0.32 m axial (40 vueltas de
  cable de 8 mm por capa, 67 capas), con densidad efectiva de 3.755 g/cm³,
  ajustada a las 15.6 t por bobina de la tabla de §4.10.2 (p. 49) con el
  volumen CAD (4.1544 m³). Supuesto propio declarado. La sección cuadrada de
  la v1 pesa 77.9 t.

**P1, paso 0: hecho (2026-10-31).** Configuración
`field/examples/crewhat_niac_array.json`; GDML versionado en
`field/production/crewhat_niac_array.gdml` (procedimiento en
`field/README.md`, «Disposición de NIAC»). Verificado: 8 bobinas de
15 599 kg en Geant4 (malla de 4.1541 m³ frente a 4.1544 m³ del CAD), sin
solapamientos con el casco, la cabina ni entre bobinas; material hasta
10.37 m del centro (10.34 m en x/y, ±4.34 m en z). Con Biot-Savart, |B| = 0
en el eje (z = 0, 3 y 5 m), 0.007–0.019 T a 2 m del eje y 0.33–0.43 T junto
al casco (4.5 m).

**Qué cambia en los pilotos.**

- **P1, paso 0 (nuevo):** generar CAD, malla y GDML de la disposición de
  NIAC con la masa corregida; verificar solapamientos con el casco, masa
  importada en Geant4 y |B| en el eje.
- **P1, paso 1 (rehacer):** la preselección del radio de la esfera fuente
  se hizo con K=1. Repetirla con la disposición nueva (Biot-Savart, unos
  40 minutos). Los candidatos de 12, 14 y 16 m pueden cambiar.
- **P1, paso 2:** el mapa de Elmer en el dominio grande se resuelve para la
  disposición de NIAC. Si la máquina lo permite, también para K=1, para
  la comparación.
- **P1, fase de comparación (nueva, después del paso 2):** η a x = 0 para
  NIAC y para K=1, con ley coseno, escudo y control con números
  aleatorios comunes, en energías donde el campo actúa (candidatas: GCR_H a
  562 MeV y SEP_p entre 100 y 200 MeV). El margen que cuenta como
  diferencia se fija antes con D3. Sirve para el paper (cuánto importa la
  disposición) y como respaldo si NIAC resultara claramente peor; no
  cambia la decisión de producción sin una decisión de equipo nueva.
- **Anisotropía:** con la disposición final, comparar desplazamientos del
  fantoma en dos direcciones (por ejemplo +x y la diagonal, a 2 y 4 m)
  antes de fijar D6. Con K=1 el campo central es un dipolo en +x y la
  Fase 7 del ablation midió hasta 1.64× de variación angular de |B| a
  4.5 m; con la disposición de NIAC la simetría es otra y hay que medirla.

**Lo que no cambia.** El scorer, P0 y P2 no usan el campo. Las dosis de la
v1 ya eran inválidas por A1–A3. El ablation del 2026-09-10 sigue siendo
válido como medida de uniformidad, pero ya no respalda la elección de
producción.

## Requisitos técnicos bloqueantes

Antes de los pilotos que los necesitan (detalle en `plan_barrido.md`):

- **Mapa de campo final con el dominio que fije P1. Es el bloqueante del
  camino crítico.** Desde el 2026-10-31 es un mapa de Biot-Savart
  volumétrico validado con Elmer (P1, paso 2). Lo que sigue en este punto
  es la historia de por qué Elmer solo no alcanzaba. La esfera fuente actual (≈6.94 m) queda
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
  se hicieron en una de 15 GB + 11 GB de swap. **Desde el 2026-10-31 hay
  acceso al laboratorio de la facultad** (más de 30 PCs de 32 GB, sin red
  entre ellas, algunas horas de día): cada solve tiene que caber en una
  sola PC. Estrategia en el `README.md` raíz, «Cómputo en el laboratorio de
  la facultad».
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
- **Base de la tolerancia D7 (propuesta, 2026-10-01; falta que el equipo la
  apruebe):**
  - **Incertidumbre de la propia referencia (ICRP 116):** según §4.4.2 y
    §4.7.2, el error estadístico relativo de los coeficientes es menor
    que 5% en la mayoría de los órganos, y llega a 15% en órganos chicos
    como la tiroides. Esto vale para protones y helio, con PHITS como
    código primario. La validación con GEANT4 tuvo menos de 4% sobre
    20 MeV.
  - **Diferencias entre códigos:** según §4.4.3, en casi todos los casos
    fueron mucho menores que esa incertidumbre estadística, con muy buen
    acuerdo sobre 10 MeV. Para helio (§4.7.3), PHITS y FLUKA dan un
    acuerdo «satisfactorio». Los valores de referencia son el promedio
    de los códigos, después suavizado.
  - **Geant4 independiente:** con Geant4 10.04 (QGSP_BIC_HP) y fantomas
    mesh, el cociente frente a ICRP 116 en geometría ISO queda «mayormente
    entre 0.9 y 1.1» sobre 100 MeV/u, para protones y helio. Ese cociente
    incluye además la diferencia de anatomía entre fantomas (Yeom et al.
    2019, *Nucl. Eng. Technol.* 52(7):1545,
    [PMC11210835](https://pmc.ncbi.nlm.nih.gov/articles/PMC11210835/)).
  - **Propuesta:** a ≥100 MeV/n, el IC95 del cociente dentro de
    [0.90, 1.10] para los órganos grandes: pulmón, colon, pared del
    estómago, médula roja e hígado. Hay dos razones independientes que
    llevan al mismo número:
    - es aproximadamente 2σ del error de la propia referencia (≤5% en
      órganos grandes);
    - coincide con la banda 0.9–1.1 que obtuvo otro grupo con Geant4.
  - **Órganos chicos (mama y tiroides): ±30% (decidido el 2026-10-31).**
    Misma regla que en los órganos grandes: unas 2 veces el error de la
    propia referencia, que en órganos chicos llega a 15% a 1σ (§4.4.2). La
    propuesta anterior, ±15%, pedía más precisión que la de ICRP y
    duplicaba P0. ICRP 116 no fija tolerancias por órgano; esta banda no
    mide exactitud fina, sino que detecta errores gruesos (una definición
    de órgano o una masa mal asignada), que en órganos chicos son el error
    más probable. Un órgano chico fuera de ±30% también hace fallar P0
    hasta que se explique.
  - Los demás órganos de `organos_p0.py` son descriptivos.
  - Entre el corte del casco y 100 MeV/n, todo es descriptivo.

> **Nota: qué se compara en P0.** Se comparan órganos individuales que
> ICRP 116 tabula, cada uno con su definición: pulmones, colon, pared del
> estómago, mama, médula roja, hígado, etc. **No** se usa la categoría
> `remainder_tissues` de `write_event_categories.py`. Esa categoría es una
> agregación por masa propia de este proyecto, y ICRP calcula sus
> «tejidos restantes» de otra forma (media aritmética de los órganos).
> Tampoco se usa `total_body`. Diferencias que hay que respetar
> (`tests/p0_normalizacion/organos_p0.py`):
> - **Colon:** en ICRP 116 incluye la pared del recto (RC + LC + RSig). La
>   categoría `colon` del proyecto no la incluye.
> - **Médula roja:** verificado en ICRP 116 (§3.4 y párrafo 116). Se toma
>   como la dosis en la esponjosa de cada hueso, promediada con peso igual
>   a la masa de médula activa. Es lo mismo que pesar con la fracción de
>   médula roja, así que se puede comparar directamente.

  - **Tabla de referencia, lista (2026-10-01):**
    `tests/p0_normalizacion/referencias/icrp116_organos_iso_am.csv`.
    Contiene 28 órganos, protones y helio, ISO, fantoma masculino, en
    pGy·cm². Se extrajo del material suplementario v2 de ICRP 116
    (`p116jaicrp_40_2_5_conversion_coefficients_suppl_data_ver2.zip`, que
    no se versiona por derechos de autor). Se verificó contra la Tabla
    impresa: pulmones a 1 GeV, 579 pGy·cm².
  - **Dosis efectiva** (Tablas A.6 y A.11): transcrita como control
    secundario. Necesita el fantoma AF (D5).
  - **Parámetros fijados (2026-10-31), antes de correr:** las 8 energías de
    `POINTS` en `p0_icrp116.py` (protones de 100, 300, 1000, 3000 y
    10 000 MeV; helio de 100, 1000 y 10 000 MeV/n), 3·10⁶ eventos por
    energía y una semilla por energía. En el laboratorio va una energía por
    PC (`--points`).
  - **Costo estimado de P0** (8 energías, esta máquina de 8 núcleos):
    ~4–5 h. Lo fijan los órganos grandes: con ±30%, mama y tiroides no
    piden eventos extra (con ±15% eran ~9–10 h).

    Achicar la esfera fuente alrededor del fantoma desnudo reduce el costo
    cerca de la mitad.
  - **Tabla de referencia:** en
    [ICRP 116](https://www.icrp.org/publication.asp?id=icrp+publication+116),
    anexos de coeficientes ISO para AM. Hay que transcribirla a un CSV
    versionado con fuente y unidades (pGy·cm²).
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

0. **Geometría de NIAC (nuevo, 2026-10-04):** disposición y masa de las
   bobinas según el reporte NIAC; ver «Disposición de las bobinas (D9)».
   Todo lo que sigue se hace sobre esta geometría.
1. **Preselección:** un mapa Biot-Savart en un dominio grande da la cola
   ∫B⊥·dl fuera de cada radio candidato. Se descartan los radios donde esa
   cola puede desviar de forma apreciable a las partículas de menor
   rigidez de interés. **Hecha el 2026-10-01 con el patrón K=1; hay que
   repetirla con la geometría del paso 0 (hallazgo A4).** Ver «Resultado
   de la preselección» más abajo.
2. **Mapa y validación (cambiado el 2026-10-31).**
   - **Mapa:** Biot-Savart volumétrico (`field/compute_field_volumetric.py`),
     sin dominio finito. Cuadratura de 6 × 3 filamentos con error medido
     ≤0.32% junto a las bobinas y ≤0.08% en el hábitat. El paso de la
     grilla se fija con `--check-points` y con la dosis del paso 3.
   - **Validación con Elmer, de una sola bobina.** Con μr = 1 el problema
     es lineal y el arreglo es la suma de bobinas iguales. Además, el
     ensayo grueso del arreglo mostró que, en el hábitat, el error de
     Elmer (~0.1 T) tapa el campo, que es un resto de cancelaciones.
     - 2–3 corridas por PC con malla y caja crecientes, con corriente
       uniforme (`Normalize Coil Current = True`);
     - se comparan con Biot-Savart junto a la bobina y en líneas radiales
       (`field/validate_volumetric_field.py`). Cada PC corre un nivel con
       `field/elmer_una_bobina.sh`.
     - En dos niveles gruesos de la laptop, la mediana del error de Elmer
       bajó de 22% a 15% junto a la bobina y de 82% a 29% en las líneas
       radiales: va hacia Biot-Savart y todavía no convergió.
     - **Laboratorio (2026-10-31), niveles A (margen 4 m) y D (margen 8 m),
       aire de 0.20 m:**
       - la mediana del error bajó de 7.8% a 5.8% junto a la bobina y de
         42% a 9.4% en las líneas radiales;
       - el cambio de A a D es mayor que lo que le falta a D: cumple el
         criterio para la caja.
       - Faltan B (margen 6 m) y C (aire 0.15 m) para cerrar la caja con
         tres puntos y probar la malla.
   - **Criterio, fijado antes:** la diferencia con Biot-Savart se achica al
     refinar Elmer y, en la corrida más fina, queda dentro del cambio entre
     las dos corridas más finas de Elmer.
   - **Paso del mapa:** con 0.5 m, la interpolación se equivoca en 4.7%
     (p95) en el hábitat; se propone 0.25 m.
   - **Mapa candidato generado (2026-10-31):** ±30 m, paso de 0.25 m, en
     208 s con 20 hilos en el laboratorio.
     - Error de interpolación en el hábitat: 1.2% (p95); fuera de 12 m,
       0.03%.
     - Campo máximo en las caras: 6.3 mT.
     - Falta la validación con Elmer y el paso 3.
   - **Antecedente** (frontera `AV=0`): Biot-Savart y Elmer diferían hasta
     un 40% hacia los extremos en z. Ensayo grueso con NIAC en la
   laptop (2026-10-31; `field/README.md`, «Elmer en el laboratorio»): los
   signos coinciden con Biot-Savart, pero |B| difiere entre 31% y 62% dentro
   del anillo, frente a 2–15% con K=1 a igual resolución. Con NIAC, el campo
   del hábitat es un resto de cancelaciones, así que la convergencia de
   malla y dominio va a pesar más que con K=1.
3. **Convergencia de la dosis:** x=0 y una posición fuera del eje, en las
   energías más sensibles al campo (cerca del corte del escudo), para
   R₁ < R₂ < R₃.
4. **Comparación de disposiciones (nuevo, 2026-10-04):** η a x = 0 con la
   disposición de NIAC y con K=1; detalle en «Disposición de las bobinas
   (D9)».

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

> **Nota (2026-10-04):** esta preselección usó el patrón K=1, que dejó de
> ser la geometría de producción (hallazgo A4). El método sigue valiendo;
> los números se rehacen con la disposición de NIAC (hecho el 2026-10-31,
> ver «Preselección con la disposición de NIAC» más abajo).

**Chequeo exploratorio de la cola con NIAC (2026-10-31; no es la
preselección).** Script: `field/studies/cola_campo_niac_k1_2026-10-31.py`
(salida en el `.txt` homónimo). Usa la misma métrica A (p90 de ∫u×B dl
hacia atrás, 2000 pares por radio) para las dos disposiciones:

| R (m) | 12 | 14 | 16 | 18 | 20 | 22 | 24 | 28 | 32 |
|---|---|---|---|---|---|---|---|---|---|
| K=1 (T·m) | 0.43 | 0.17 | 0.09 | 0.05 | 0.04 | 0.02 | 0.02 | 0.01 | 0.005 |
| NIAC (T·m) | 1.38 | 0.82 | 0.56 | 0.39 | 0.28 | 0.20 | 0.16 | 0.10 | 0.06 |

- NIAC llega a la cola que K=1 tiene a 12, 14 y 16 m recién hacia 18,
  23 y 28 m.
- **Pero la cola no predice las reentradas** (ver «Métrica», más abajo).
  La preselección real con NIAC, con la métrica B, mueve los radios
  bastante menos (resultado más abajo). Esta tabla queda solo como
  registro.

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

#### Preselección con la disposición de NIAC (paso 1, 2026-10-31)

Misma configuración y método que la de K=1 (1000 pares por radio y
rigidez), sobre las trayectorias de corriente de
`field/examples/crewhat_niac_array.json`. Resultados:
`field/studies/p1_preseleccion_radio_niac_2026-10-31.json`. Tardó unos 45
minutos con 7 procesos. Bobinas (material) hasta **10.37 m** del centro.

```bash
# Desde field/
.venv/bin/python preselect_source_radius.py generated/crewhat_niac_array/array_current_paths.json \
    studies/p1_preseleccion_radio_niac_2026-10-31.json --radii 14 16 18 20 22 24 28 32 \
    --rigidities-gv 0.15 0.25 0.36 0.71 1.5 --n-tail 1000 --n-track 1000 --processes 7
```

| R (m) | ∫B⊥·dl mediana / p90 (T·m) | 12 MeV (0.15 GV) | 33 MeV (0.25 GV) | 67 MeV (0.36 GV) | 238 MeV (0.71 GV) | 831 MeV (1.5 GV) |
|---|---|---|---|---|---|---|
| 14 | 0.44 / 0.82 | 4.2% | 0.9% | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] |
| 16 | 0.29 / 0.55 | 0.8% | 0.1% [0.0, 0.6] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] |
| 18 | 0.21 / 0.37 | 0.4% [0.2, 1.0] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] |
| 20–32 | ≤0.16 / ≤0.27 | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] | 0 [0, 0.4] |

Todos los pares malos fueron reentradas; ninguno quedó atrapado.

**Lectura.**
- **Frente a K=1, NIAC corre los radios unos 2–4 m, no más.** Con K=1, a
  12 m había 1.9%, 0.5% y 0.1% en las tres primeras columnas, y a 14 m solo
  0.1% en la de 12 MeV. NIAC a 16 m queda algo mejor que K=1 a 12 m, y
  NIAC a 20 m, como K=1 a 14 m.
- **La cola ∫B⊥·dl engaña:** es 2–3 veces la de K=1 al mismo radio, pero
  las reentradas no crecen en esa proporción. Confirma que la métrica que
  vale es la de reentradas.
- **Candidatos para los pasos 2–3: 14, 16 y 18 m** (R₁ < R₂ < R₃), con el
  mismo criterio que con K=1: a 67 MeV, cerca del corte del casco, no hay
  reentradas desde 14 m. 20 m queda como reserva si se exige la columna de
  12 MeV. Elegir entre ellos corresponde a D3 y al paso 3.
- **Consecuencia para Elmer:** el mapa tiene que cubrir unos ±19 m (con R₃
  = 18 m), y la frontera `AV=0` quedar más lejos. Con aire uniforme de
  0.30 m no cabe en una PC de 32 GB: una caja de ±22 m son unos 13 M de
  tetraedros, unos 40 GB con los 3.1 KB por tetraedro medidos. Ver la
  estrategia en el `README.md` raíz.
- **Costo en Geant4:** la fracción de primarios que tocan el fantoma cae
  como 1/R². A 16 m es unas 5 veces menor que a 6.94 m.

### P2 — Validación del estimador de incertidumbre por evento

Repite la Fase 7 con el scorer nuevo.

**Diseño fijado el 2026-10-31, antes de correr.**

- **Objetivo:** confirmar que el SE de una sola corrida (S1/S2 por evento)
  es confiable cuando la corrida pasa D4, para usar R=1 en el barrido.
  Como el barrido es monoenergético por punto y D4 se revisa en cada
  corrida, el resultado vale para todos los espectros.
- **Dos partes** (resuelve la contradicción entre «sin campo» y «con
  campo»):
  - **P2a, sin esperar el mapa:** configuración de control (la misma
    geometría sin campo, que es la mitad del barrido). Geometría de NIAC
    (`field/production/crewhat_niac_array.gdml`), casco de 1.5 cm, esfera
    fuente de 16 m (candidato central de P1), fantoma AM en x = 0, ley
    coseno.
  - **P2b, con el mapa final:** SEP_p 150 MeV con campo, mismos criterios.
- **Casos de P2a**, uno por cada régimen de colas:

  | Caso | Por qué |
  |---|---|
  | SEP_p 70 MeV | Justo sobre el corte del casco (~65 MeV): llegan pocos primarios y depositan mucho. Es la cola más pesada medida (un evento con el 57% del pulmón). |
  | SEP_p 150 MeV | Régimen típico de SEP, colas moderadas. Es también el caso de P2b, que así se compara con su versión sin campo. |
  | GCR_He 1 GeV/n | Carga 2 (4 veces la ionización) y fragmentación nuclear. |
  | GCR_H 10 GeV | Cascadas hadrónicas: eventos raros con depósitos enormes. |

- **Tamaño:**
  - Una corrida larga por caso, partida por `event_id` en **K = 40 lotes
    disjuntos** de M eventos. Cada lote equivale a una corrida
    independiente (método de la prueba por lotes, más abajo). Con 40 lotes,
    la dispersión real entre lotes se conoce con ±22% (IC95); con 20 sería
    ±30%.
  - **M** se fija antes con una sonda que solo mide la fracción f de
    eventos con depósito en cuerpo entero (no mira el SE): M = 400/f, es
    decir unos 400 eventos con depósito por lote en cuerpo entero. Las
    categorías chicas tendrán menos; ahí decide D4.
  - **La sonda es de 2·10⁵ eventos (2026-10-31).** Con 10⁴, como decía
    antes este punto, la esfera de 16 m daba solo ~4 eventos con depósito
    en SEP de 150 MeV. Con 2·10⁵ hubo 113 (f = 5.7·10⁻⁴), así que M = 7·10⁵
    y N = 2.8·10⁷: 1.5 h en 6 hilos de la laptop. Es un cambio de
    dimensionamiento, no de criterio.
  - La misma corrida se reparte también en 160 lotes de M/4 (~100 eventos
    con depósito), sin costo extra, para ver que D4 rechaza esos lotes y
    que sin D4 la cobertura cae.
- **D4 (fijado):** el SE de una corrida o lote se acepta, por categoría,
  si se cumplen las tres condiciones:
  1. al menos 200 eventos con depósito (cobertura de 0.90–1.00 desde ~200
     en la prueba por lotes del 2026-10-01);
  2. VOV < 0.1 (criterio de MCNP; con VOV < 0.1 la cobertura fue 93.5%);
  3. ningún evento aporta más del 10% del total (`max_J/S1 ≤ 0.10`):
     detecta un evento que domina el total, cosa que el conteo de eventos
     no ve.

  En el barrido, una corrida que no pasa D4 en una categoría recibe más
  eventos hasta pasar, o esa categoría se reporta como no resuelta.
- **Criterio de aprobación (fijado)**, por caso, con los lotes que pasan
  D4:
  - **a) Cobertura ≥ 0.90:** fracción de pares (lote, categoría) cuyo IC95
    (media ± 1.96 SE) contiene la media de la corrida completa. Lo
    esperado es ~0.95; 0.90 equivale a subestimar el SE en ~16%.
  - **b) Calibración:** en cada categoría con al menos 10 lotes que pasan
    D4, ρ = sqrt(media(SE²))/s_between ≥ 0.75. Solo se exige el lado
    bajo, porque sobrestimar el SE es conservador. Con 40 lotes, un
    estimador correcto queda bajo 0.75 con probabilidad ~0.2% por
    categoría.
  - **c) Descriptivo:** cobertura de los lotes que no pasan D4. Se espera
    menor, y eso muestra que D4 sirve.
  - Si P2 falla, se investigan las colas y el scorer antes de tocar los
    umbrales. Cambiarlos exige una corrida confirmatoria nueva, de tamaño
    fijo (regla 3).
- **Costo:** del orden de 10³ núcleo-hora para los 4 casos (la sonda lo
  precisa), una sesión del laboratorio. Script: `tests/scorer_por_evento/p2_estimador.py` (2026-10-31),
  con un test sintético (`test_p2_analisis.py`). Cada caso puede ir en su
  PC:
  - `sonda` mide f y fija M;
  - `run` corre los 40·M eventos;
  - `analyze` aplica D4 y los criterios a y b, con los umbrales de
    `design_parameters.py`.

  En b, la SD entre lotes se calcula con todos los lotes y el SE solo con
  los que pasan D4: la SD es la dispersión real de una corrida de M
  eventos, y quitar los lotes con eventos grandes la achicaría.
- **Resultado esperado:** compatibilidad con 1. S2 por evento permite un
  estimador insesgado de la varianza bajo independencia y varianza finita;
  no hace exacta la varianza estimada ni valida automáticamente un IC normal.
- **Bloquea:** usar R=1. Si falla, investigar el scorer y las colas antes
  de elegir más repeticiones; no extrapolar el factor histórico 0.08/0.48.

#### Costo estimado de P2 con cuerpo entero (2026-10-01)

Medido con sondas de 3000 eventos en la geometría de producción actual
(mapa Elmer, bobinas, esfera de 6.94 m, x=0, 8 hilos), con ~20 s de
inicialización descontados. Es un orden de magnitud: la esfera de P1 (12–16 m)
bajará la fracción de eventos con depósito entre 3 y 5 veces.

| Caso | Costo por evento (s·núcleo) | Eventos con depósito en cuerpo entero | Eventos por lote de ~200 depósitos | K=40 lotes (h, 8 núcleos) | K=20 lotes (h) |
|---|---|---|---|---|---|
| SEP_p 300 MeV | ~0.02 | 0.6% | 33 000 | ~1 | ~0.5 |
| GCR_H 1 GeV | 0.16 | 0.5% | 40 000 | ~9 | ~4.5 |
| GCR_He 1 GeV/n | 0.73 | 1.4% | 14 000 | ~14.5 | ~7 |
| GCR_H 10 GeV | 1.5 | 2.5% | 8 000 | ~16.5 | ~8 |

- **Los 4 casos con K=40:** ~40 h, unos 1.7 días de esta máquina.
- **Con K=20:** ~20 h. Equivale a un IC de ρ de ±30% en vez de ±22%.
- **Médula roja:** cuesta unas 2–4 veces más.
- **Observación del contador R6:** en SEP_p de 300 MeV, el 1.9% de los
  primarios se corta por el límite de longitud de traza (partículas
  atrapadas en el campo). Hay que revisarlo en P1.

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

### P7 — Simulación en dos etapas (propuesta, 2026-10-31)

Idea del equipo para correr los dos fantomas (D5) sin duplicar todo:
simular una vez lo costoso y reusarlo con cualquier fantoma. Es la técnica
de fuente de superficie o espacio de fases (en MCNP, SSW/SSR; en
radioterapia, los archivos de espacio de fases).

- **Superficie de registro:** entre el casco y las bobinas, por ejemplo un
  cilindro de 5.5 m de radio y ±5.5 m en z (las bobinas empiezan a
  5.67 m del eje).
  - No una esfera de 2 m alrededor del fantoma: en las posiciones cerca
    del casco (x = 4 m) se saldría del hábitat, y obligaría a una etapa 1
    por posición.
  - Afuera del casco y no sobre él, para que la etapa 2 incluya el campo
    junto al casco (0.3–0.4 T): las cargas lentas que salen del casco
    giran y vuelven a entrar en centímetros.
- **Etapa 1**, una por configuración (escudo o control × especie ×
  energía): geometría completa sin fantoma. Cada partícula que cruza la
  superficie hacia adentro se guarda (tipo, energía, posición, dirección,
  tiempo, peso y `event_id` del primario) y se mata. También se guarda N,
  el total de primarios.
- **Etapa 2**, por fantoma y posición: lo que hay dentro de la superficie
  (aire, casco, fantoma y el mapa de campo).
  - Cada evento reproduce todas las partículas de un mismo `event_id`, y
    los eventos vacíos también cuentan en N. Así S1, S2 y el SE por evento
    siguen siendo válidos, porque las partículas de una misma cascada
    están correlacionadas.
  - Cada evento de la etapa 1 se usa una sola vez por fantoma, sin
    reciclar, para no subestimar la varianza.
  - CRN: la misma semilla por `event_id` en escudo y control.
- **Qué se pierde:** lo que el fantoma manda hacia afuera de la superficie
  y vuelve a entrar (por ejemplo, retrodispersado en las bobinas). Se
  espera pequeño, pero hay que medirlo.
- **Validación (criterio fijado antes):** comparar una etapa con dos
  etapas, escudo y control, en SEP_p 150 MeV, GCR_H 1 GeV y GCR_He
  1 GeV/n. Aprueba si el IC95 de la diferencia de dosis por categoría cae
  dentro de ±B (D3).
- **Ganancia:** la etapa 1 (campo, bobinas, casco y esfera de 14–18 m) se
  paga una vez para los dos sexos y las 5 posiciones, y queda disponible
  para cualquier fantoma futuro. La etapa 2 (el fantoma) se paga igual
  por cada caso. Cuánto se ahorra depende de cuál de las dos etapas domina
  el costo, y eso lo mide la validación.
- **Costo y trabajo:**
  - el almacenamiento (decenas a cientos de GB en todo el barrido) se mide
    en la primera corrida;
  - en Geant4 falta el registro en la superficie, un generador que lea el
    archivo agrupado por evento y la geometría de la etapa 2;
  - requiere decisión del equipo.

## Dependencias

```
D1–D9 + scorer nuevo
   ├─ P0 (normalización, sin campo)
   ├─ P1 (dominio y radio) ─┬─ P3 (costo y convergencia) ─┬─ P6 (η)
   │   └─ mapa final (BS)   │   P4 (energías) ────────────┤
   │      (lab., 32 GB/PC)  │   P5 (sesgo) ────────────────┘
   └─ P2 (estimador, sin campo) ─┘
```

**Camino crítico:** P1 (desde el paso 0, geometría de NIAC) → mapa Elmer
final → P3/P4/P5 → P6. Lo que no usa
el campo (P0, P2, scorer, tests) se adelanta en paralelo, pero ninguna
corrida con campo hecha antes del mapa final es reutilizable.

## Condición para empezar el barrido

- [ ] D1–D7 y D8 si aplica decididas y registradas antes de los pilotos afectados.
- [x] Geometría de bobinas de NIAC (disposición y masa, D9; hallazgos A4 y
      B9) generada, verificada y versionada en `field/production/`
      (2026-10-31).
- [ ] Mapa de campo final (Biot-Savart volumétrico validado con Elmer,
      dominio de P1) generado, versionado en
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
