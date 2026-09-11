# Ficha de la bobina CREW HaT: implementación vs. fuente verificada

Actualizado 2026-09-10. Igual que `GEOM14_STATUS.md` para Geom14: este
documento distingue datos verificados en el reporte NIAC Phase I completo
(D'Onghia, NTRS 20250002403) y la tesis de maestría 2024 (Ziyang Hang,
MINDS@UW 1793/85233) de decisiones/extrapolaciones propias del equipo.
Cifras exactas con cita de página/sección en
[`ELMER_VALIDATION.md`](ELMER_VALIDATION.md), sección "CREW HaT: datos
verificados para el generador CAD" — este documento se enfoca en el estado
de la implementación, no repite esas citas.

## Qué implementa `generate_ellipse.py` hoy

Una sola bobina elíptica cerrada, con sección transversal cuadrada
homogeneizada (representando el winding pack completo, no un conductor
individual) — no las 8 bobinas del arreglo Halbach completo, y no la
nave/hábitat.

| Parámetro | Valor del piloto | Origen |
|---|---|---|
| Semieje mayor / menor | 4 m / 2 m | Tabla 3.1, reporte NIAC (dato real) |
| Lado del winding pack (cinta 12mm) | 1,43 m | Tabla 2.7, tesis 2024 (dato real, optimizado) |
| Lado del winding pack (CORC) | 0,67 m | Tabla 2.8, tesis 2024 (dato real, optimizado) |
| Forma de la sección | Cuadrada | **Supuesto propio, no dato de la fuente** — ver más abajo |
| Corriente | 1×10⁷ A | Tabla 3.1 — es ampere-vuelta total del sistema, no corriente de un conductor |
| Radio de regularización Biot-Savart | 0,143 m / 0,067 m | Elegido como 10% del lado del winding pack — **provisional, sin validar** |
| Material CAD | Cobre puro (placeholder) | Igual que el piloto DH original — pendiente el material HTS homogeneizado real |

Genera `ellipse.brep`/`ellipse.step`/`ellipse.geo`, `current_path.json`
(mismo esquema que `generate_dh.py`, compatible sin cambios con
`compute_field.py`) y `materials.json`. Validado: volumen CAD coincide con
la estimación analítica perímetro×área en <0,1% para ambas variantes
(cinta 12mm: 39,62 m³; CORC: 8,70 m³) — ver `field/tests/test_ellipse.py`.

## Decisiones de modelado propias, marcadas explícitamente

**1. Sección transversal cuadrada.** Ninguna fuente da una segunda
dimensión del winding pack (solo un "grosor" escalar) — la tesis calcula
ese grosor sumando perímetro capa por capa (Ec. 2.10-2.12, p. 35), sin
descomponerlo en ancho×alto. Modelar como sección cuadrada de lado igual
al grosor reportado es la aproximación más simple posible, no una
verificada contra la geometría real del winding pack de la tesis. Si en
algún momento se encuentra una segunda dimensión (ej. en una figura del
reporte/tesis no capturada por el texto extraído), esto debe corregirse.

**2. Radio de regularización de Biot-Savart, sin validar.** `_conductor_
profile()` reutilizado de `generate_dh.py` necesita un
`conductor_radius_m` para el núcleo regularizado de `compute_field.py`
— pero ahí representa el radio real de un hilo delgado (1,2cm en el piloto
DH, mucho menor que la escala de la bobina). Aquí, el "conductor" es el
winding pack completo, de escala comparable al propio semieje menor de la
elipse (2m) — un solo filamento con núcleo suavizado es una aproximación
mucho más débil cerca de la bobina que en el piloto DH. Se eligió
arbitrariamente 10% del lado del winding pack como radio de
regularización, **sin ninguna validación de que esto dé un campo razonable
cerca de la bobina** — antes de usar el mapa de campo de esta geometría
para dosimetría, hay que revisar si esta aproximación de filamento único
sigue siendo válida, o si hace falta un modelo de múltiples filamentos
distribuidos por la sección (más fiel a una distribución de corriente
verdaderamente volumétrica).

**3. Margen de seguridad de curvatura, 1,2x, no validado como criterio de
producción.** Una elipse tiene su radio de curvatura mínimo en los
extremos del semieje mayor: `ρ_min = b²/a`. Con a=4m, b=2m: ρ_min=1m. La
media-anchura del winding pack de cinta 12mm (0,715m) pasa el margen de
1,2x que exige `controls()` (necesita <0,833m), pero con menos holgura que
los márgenes "4x" que usa `generate_dh.py` para el piloto DH — la elipse
real de CREW HaT es geométricamente ajustada para esta sección transversal
tan gruesa. 1,2x es un valor elegido para permitir generar la geometría
real sin inventar dimensiones más conservadoras; no hay todavía un chequeo
de calidad de malla que confirme que ese margen es suficiente en la
práctica (¿la sección se deforma o autointerseca sutilmente cerca de los
extremos, aunque el sólido global se cierre sin error?).

## Mallado y conversión: implementado y validado (2026-09-10)

Confirmada la hipótesis de más arriba: el pipeline estándar de Gmsh 2D/3D
(`generate_mesh.py`, el mismo mallador simple usado antes de que
`mesh_swept.py` existiera para sortear el atasco de la Double Helix)
**completa sin problema** sobre esta geometría — no hace falta ningún
workaround de tetraedros estructurados, porque una sola elipse no tiene la
curvatura cerrada que atasca la triangulación 2D de OpenCASCADE en la
Double Helix de muchas vueltas.

| Variante | Tetraedros | Tiempo 3D | Volumen malla vs. CAD |
|---|---:|---:|---:|
| Cinta 12mm | 38.513 | 0,087 s | 39,6176 vs 39,6240 m³ (0,016% de diferencia) |
| CORC | 57.190 | 0,102 s | — (mismo orden de magnitud de error) |

0,016% es sustancialmente mejor que el 3,06% documentado para el piloto DH
— esperable: una sección cuadrada es fácil de representar exactamente con
tetraedros lineales, a diferencia de una sección circular aproximada por
facetas.

**Conversión a GDML e importación en Geant4, validadas de punta a punta**:
`mesh_to_gdml.py` convierte sin cambios (mismo contrato que Geom14).
Importado con éxito vía `/spacecraft/coilGeometry`
(`field/examples/import_crewhat_ellipse.mac`), con validación cruzada en
cada paso:
- Sin solapamientos (`Checking overlaps for volume coil_placement_1
  (G4TessellatedSolid) ... OK!`).
- Masa importada por Geant4 (354.974 kg, cobre placeholder) coincide con
  volumen CAD × densidad (39,62 m³ × 8960 kg/m³ ≈ 355.000 kg) dentro del
  mismo margen de discretización de la malla.
- Sonda geantino cruzando el conductor real (no el hueco central de la
  elipse) mide exactamente 1,43 m de trayecto dentro de `coil_placement_1`
  — coincide exactamente con el grosor del winding pack configurado.

**Ubicación de prueba, no arreglo final validado**: la bobina se colocó
con su centro desplazado 8m del eje de la nave (`center_m: [8,0,0]`),
coherente con el radio Halbach verificado (R_Halbach=8m es el radio del
círculo donde se ubican los **centros** de las 8 bobinas, no el tamaño de
cada bobina — interpretación razonada del término "Halbach Torus", no un
dato literal de una tabla). La orientación (plana en XY, normal a lo largo
del eje de la nave) y el ángulo de las otras 7 bobinas siguen sin
definir — ver más abajo. Con `shipRadius` escalado a 4,5m (el valor
decidido para CREW HaT), esta ubicación específica SÍ se solaparía con el
casco (punto más cercano de la bobina al eje ≈3,29m, menor que 4,5m) — la
macro de prueba usa deliberadamente la nave por defecto (2,8m) para
aislar la validación de importación del problema, todavía pendiente, del
arreglo completo de 8 bobinas.

## Campo Biot-Savart: calculado y validado sobre esta geometría (2026-09-10)

`compute_field.py` no necesitó ningún cambio (mismo esquema genérico ya
confirmado) — genera el mapa `.map` directamente desde el
`current_path.json` de la elipse. Validaciones hechas:

- **Orden de magnitud correcto**: campo en el centro de la bobina de cinta
  12mm, 2,41 T, frente a 2,22 T de la estimación analítica de un lazo
  circular equivalente (radio `sqrt(a·b)`) — ~8% de diferencia, razonable
  dado que una elipse real no es exactamente ese lazo circular. Dirección
  puramente axial (Z), como corresponde al centro de una espira plana.
  Caída de campo fuera de eje también sensata (2,41 T en el centro → 1,16 T
  a 2m de altura). Regresión capturada en `test_field_at_center_matches_
  equivalent_loop_estimate` (`field/tests/test_ellipse.py`).
- **Propiedad geométrica real, no un bug**: cualquier punto en el mismo
  plano que la espira (Z=0 global aquí, esté o no sobre el eje de simetría)
  tiene campo puramente perpendicular a ese plano — cada contribución de
  Biot-Savart `dl × r̂` es normal al plano cuando ambos vectores están
  contenidos en él. Esto causó un error real de diseño de prueba (ver
  abajo) antes de identificarse; capturado como regresión en
  `test_field_purely_axial_within_the_loops_own_plane`.
- **Importado y probado en Geant4 con una partícula cargada real**
  (`field/examples/import_crewhat_ellipse_field.mac`): un protón de 9,9 GeV
  (energía elegida para un radio de giro ~15m, mucho mayor que la escala de
  la bobina — `ActiveShield_Sim`, a diferencia de `GCR_SEP_Sim`, **no
  tiene** protección `G4UserLimits`/`StepLimiterPhysics` contra partículas
  atrapadas, ver AGENTS.md; una energía baja aquí, con un campo real de
  ~2,4 T, arriesgaba el mismo incidente de +27 minutos ya documentado)
  muestra una deflexión real y sustancial (hasta -77,9 mm en Y) al cruzar
  la región de campo, sin quedar atrapado. **Primer intento de prueba
  fallido, honesto de registrar**: lanzar la sonda exactamente por el eje
  central de la bobina (`(8,0,z)`) dio una "deflexión" de escala
  nanométrica — no un fallo del pipeline, sino la propiedad geométrica de
  arriba (`v` paralelo a `B` ahí, fuerza de Lorentz nula). Corregido
  apuntando la sonda a un punto fuera de eje y fuera del plano de la
  bobina (`(10,0,-3)`, confirmado con `field_at()` directo que ahí `B`
  tiene una componente transversal real de ~0,4 T).
- **Núcleo de regularización sin validar**: se generó el mapa (half-size
  14m, spacing 0,5m) y se usó para la prueba de deflexión de arriba, pero
  el valor elegido (10% del winding pack) sigue sin comparación contra un
  modelo de múltiples filamentos u otra referencia — la deflexión medida
  es una demostración de que el pipeline funciona, no una validación de
  que esa cifra sea físicamente correcta cerca de la bobina.

## Arreglo de las 8 bobinas: implementado con patrón Halbach dipolar (2026-09-10)

`field/generate_ellipse_array.py` (análogo a `generate_array.py`, reutiliza
`controls()` de `generate_ellipse.py` sin modificarlo) genera las N bobinas
del toro Halbach. **El patrón angular es un supuesto propio del equipo, no
un dato de NIAC/tesis** — confirmado por dos rondas de búsqueda dirigida
que ninguno de los dos documentos da una tabla de ángulos ni siquiera un
conteo de cuántas de las 8 bobinas son "radiales" vs. "tangenciales" (esa
distinción, Sección 5.3.3 del reporte NIAC p.61, es para el **montaje
mecánico-estructural**, no necesariamente la fase electromagnética). Se
aplicó en su lugar la fórmula estándar de un arreglo Halbach **dipolar**
(K=1) de la ingeniería de imanes: con N elementos a posición angular
`φ_k=2πk/N`, el momento magnético de cada uno rota al doble de esa
velocidad, `θ_k=2φ_k` — la misma regla usada en imanes Halbach de MRI y
onduladores de aceleradores. Todas las N bobinas son del mismo tipo en
este piloto (no la posible mezcla radial/tangencial real de CREW HaT, que
no hay datos para reconstruir).

Geometría 3D de cada bobina: semieje mayor (a=4m) a lo largo del eje de la
nave (Z global), semieje menor (b=2m) tangencial al anillo, centro sobre
un círculo de radio 8m (R_Halbach verificado), momento magnético (normal
al plano propio) apuntando radialmente al ángulo `θ_k` en el plano XY
global.

**Validado con las 8 bobinas reales** (`crewhat_halbach_array_pilot.json`,
conductor CORC): ángulos generados coinciden exactamente con la fórmula
analítica (posición 0°,45°,...,315°; momento 0°,90°,180°,270° repetido dos
veces). Volumen CAD total (69,59 m³) coincide exactamente con 8× el
volumen de una sola bobina (8,70 m³) — confirma que ninguna bobina se
fusionó accidentalmente con otra en el paso de `fuse` (que solo opera
dentro de cada bobina, nunca entre bobinas distintas, mismo diseño que
`generate_array.py`). Mallado (168.834 elementos, <1s), conversión a GDML
(8 componentes) e importación en `ActiveShield_Sim`
(`field/examples/import_crewhat_halbach_array.mac`) **sin ningún
solapamiento, ni entre las 8 bobinas entre sí ni con el casco** — pese a
que el generador nunca comprueba solapamientos entre bobinas en tiempo de
generación (el chequeo real ocurre al importar en Geant4, mismo principio
ya documentado para el arreglo DH). Masa por bobina (~77.932 kg cobre
placeholder) consistente con volumen×densidad. Regresión en
`field/tests/test_ellipse_array.py` (4 bobinas, más rápido que las 8
reales, mismo camino de código).

- **Campo Biot-Savart superpuesto sobre las 8 bobinas, calculado y
  validado (2026-09-10)**: `field/compute_field_ellipse_array.py`
  (adaptador nuevo, no modifica `compute_field_array.py` — ese está
  acoplado al esquema de config-por-bobina de `generate_array.py`, mientras
  que este arreglo usa un `coil_template` único compartido; misma lógica
  de superposición, solo el lector de esquema es distinto). **Resultado
  físico central de todo este ejercicio, no solo una prueba de humo**: el
  patrón dipolar de Halbach funciona como se espera —
  - **Dentro del anillo** (radio 0 a 4,5m, la región de protección real
    con la nave escalada a CREW HaT): campo razonablemente uniforme,
    puramente en una dirección (X en este piloto), magnitud entre 0,42 y
    0,72 T en los puntos probados (centro, ejes, diagonales dentro del
    radio de la nave).
  - **Fuera del anillo**: cae de 2,27 T justo en el radio de las bobinas
    (r=8m) a 0,09 T en el borde del dominio (r=14m) — comportamiento de
    caída esperado.
  - **Simetría de 180° exacta**: `B(2,2,0) = B(-2,-2,0)` — la simetría de
    punto que debe tener un campo dipolar, confirmada con precisión
    numérica completa (no aproximada).
  - Regresión en `test_dipole_field_pattern_inside_vs_outside_the_ring`
    (`field/tests/test_ellipse_array.py`), con 4 bobinas por velocidad.
  - **Sigue siendo Biot-Savart regularizado, no Elmer/FEM** — mismas
    salvedades que la bobina individual: el núcleo de regularización
    (10% del winding pack, sin validar) sigue siendo la limitación
    principal para confiar en el campo cerca de las bobinas mismas, no
    en la región de protección donde se hizo esta validación.
- **Elmer FEM**: no probado sobre esta geometría todavía, ni para una
  bobina ni para el arreglo completo. Dado el historial de esta sesión
  con el piloto DH (ver `ELMER_VALIDATION.md`): mallar el dominio de aire
  alrededor de 8 bobinas será sustancialmente más pesado en memoria que
  una sola — antes de intentarlo, conviene repetir con esta geometría el
  mismo tipo de barrido de convergencia (padding × air-size) ya hecho
  para el piloto DH, y estar preparado para que el arreglo completo no
  quepa en una máquina de recursos limitados, igual que pasó con las
  combinaciones más finas del barrido DH.

## Material HTS real: implementado para ambas opciones de conductor (2026-09-10)

`field/examples/crewhat_hts_materials.json` (análogo a
`hts_tape_materials.json` de Geom14, **archivo separado, no el mismo** —
mismos tipos de capa pero espesores de fuente distinta, ver más abajo).
Reemplaza el cobre puro placeholder en `generate_ellipse.py` y
`generate_ellipse_array.py`, que ahora leen `materials_library`/`material`
del config (mismo patrón que `generate_array.py` ya usa para Geom14) —
retrocompatible: sin esas claves, siguen generando el placeholder.

- **Cinta CREW HaT homogeneizada** (`crewhat_tape_homogenized`): Hastelloy
  C-276 50µm + YBCO 1µm + Ag 3,8µm (2µm+1,8µm, dos menciones de plata en
  la Tabla 2.2 de la tesis, p.32, sumadas) + Cu 40µm = 94,8µm — **no es el
  mismo cálculo que `hts_tape_homogenized` de Geom14** (94µm, menos plata,
  más YBCO): mismos tipos de material (reutilizados sin cambios, misma
  composición elemental), pero espesores de la propia tesis de CREW HaT,
  no de la ficha SCS4050 de SuperPower. Buffer stack (0,2µm) excluido,
  mismo criterio que Geom14 (composición no publicada, masa despreciable).
  Densidad 8,95635 g/cm³.
- **CORC homogeneizado** (`crewhat_corc_homogenized`): núcleo de Cu puro
  (diámetro 3,2mm, dato geométrico exacto de la tesis, Sección 2.5.2 p.34
  — 16% del área del cable) + región anular de `crewhat_tape_homogenized`
  hasta completar el diámetro de 8mm (84% del área). **Supuesto propio, no
  dato de la fuente**: se asume que la región anular está completamente
  ocupada por el compuesto de la cinta, sin factor de relleno adicional
  entre las 48 vueltas — la tesis no da ese número (confirmado, ver
  arriba). Densidad 8,95693 g/cm³.
- Ambas fracciones másicas calculadas con precisión completa de punto
  flotante (no redondeadas a 4-6 decimales antes de combinar capas) y con
  el residuo de redondeo absorbido en la fracción de Cu — mismo problema
  que ya documentó y corrigió Geom14 (sumaba 0,999999, rechazado por la
  tolerancia estricta de `mesh_to_gdml.py`); evitado aquí desde el inicio.
- **Validado de punta a punta**: regenerados los 3 pilotos individuales y
  el arreglo de 8 bobinas con el material real; reimportados en Geant4 —
  `material=coil_mat_crewhat_tape_homogenized` /
  `coil_mat_crewhat_corc_homogenized` aparecen correctamente en el log de
  importación, con las densidades exactas calculadas arriba, sin ningún
  solapamiento nuevo. La masa apenas cambia numéricamente frente al
  placeholder (8,956-8,957 g/cm³ vs. 8,96 g/cm³ del cobre puro) porque el
  cobre domina la fracción másica de ambos compuestos — pero el GDML
  ahora lleva la composición elemental real (13 elementos), no solo cobre,
  relevante para producción de secundarios y pérdida de energía en el
  transporte de Geant4 aunque la densidad global cambie poco.

## Elmer FEM: primera corrida sobre esta geometría, con precauciones de memoria (2026-09-10)

Esta VM es Oracle VirtualBox corriendo en la laptop del usuario, con
15GB RAM + 12GB swap asignados — el barrido de convergencia del piloto DH
(ver `ELMER_VALIDATION.md`) ya había forzado apagados/reinicios reales al
agotar esos recursos con mallas de 13-28M tetraedros. Dado que esta bobina
elíptica abarca un volumen mucho mayor que el piloto DH (semieje mayor 4m
+ winding pack, frente a las pocas decenas de cm del conductor DH), se
usaron dos medidas de seguridad antes de correr nada:

1. **Límite duro de memoria vía cgroups** (`systemd-run --scope -p
   MemoryMax=6G -p MemorySwapMax=4G`): si el proceso se descontrola, muere
   contenido y rápido, sin arriesgar el resto de la VM — en vez de esperar
   al OOM killer global, que en los incidentes anteriores no evitó que la
   VM completa quedara inutilizable.
2. **Parámetros deliberadamente gruesos para el primer intento**
   (`--padding 2.0 --air-size 0.3`, mucho más grueso que cualquier
   configuración usada para DH) en vez de partir de una malla fina.

**Resultado real, muy por debajo de cualquier riesgo**: mallado del
dominio de aire (108.946 tetraedros) en 1,3s con pico de 186MB;
`ElmerSolver` en 16,9s con pico de **471,5MB** — confirmado con la
contabilidad de systemd, no una estimación. Ambos muy por debajo del
límite de 6GB impuesto y lejísimos de los varios GB que causaron los
apagados con el piloto DH.

**Bug real encontrado y corregido, específico de esta geometría**: usando
`Coil Normal(3) = 0 0 1` (copiado tal cual del `.sif` del piloto DH), el
campo de Elmer salió con el **signo exactamente invertido** en todas las
componentes frente a Biot-Savart (no un error de magnitud — un vector
opuesto, confirmado en los 6 puntos de sonda). Corregido a
`Coil Normal(3) = 0 0 -1`: el error relativo bajó de ~150-250% (vectores
casi opuestos) a **16%-54%**, con las direcciones ahora coincidiendo. El
error restante, creciente con la distancia (16% en el centro, 54% a 6m),
es coherente con una malla deliberadamente gruesa para este primer
intento seguro — mismo patrón de necesitar refinamiento ya documentado
para el piloto DH, no un problema nuevo.

**Advertencia para el arreglo de 8 bobinas**: cada una de las 8 bobinas
tiene una orientación distinta (rotada según el ángulo Halbach) — el signo
correcto de `Coil Normal` para cada una no es necesariamente el mismo, y
habría que verificarlo por separado para cada bobina antes de intentar
Elmer sobre el arreglo completo, no asumir que la misma corrección aplica
igual a las 8.

**Sigue pendiente**: repetir el mismo tipo de barrido de convergencia
(padding × air-size) ya hecho para el piloto DH, pero incrementando la
resolución **gradualmente y bajo los mismos límites de cgroup**, no saltar
directo a una malla fina. Solo se validó la bobina individual de cinta
12mm — CORC y el arreglo completo de 8 bobinas siguen sin probar en Elmer.

### Barrido de convergencia parcial (2026-09-10), detenido por precaución de memoria

Tres configuraciones, todas bajo el mismo límite de cgroup, midiendo pico
real de memoria vía contabilidad de systemd (no estimado):

| padding (m) | air-size (m) | tetraedros de aire | pico mallado | pico ElmerSolver | tiempo solve | error rel. [0,0,0] | error rel. [6,0,0] (más lejano) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2,0 | 0,30 | 108.946 | 186MB | 471,5MB | 16,9s | 15,6% | 54,8% |
| 2,0 | 0,15 | 772.544 | 1,0GB | 2,5GB | 105,2s | 15,6% | 54,8% |
| **3,0** | **0,15** | **1.494.641** | **1,9GB** | **4,7GB** | **222,4s** | **7,6%** | **33,5%** |

**Mismo patrón que el piloto DH**: refinar solo `air-size` (fila 2 vs. 1)
apenas cambió el error — algunos puntos incluso empeoraron levemente.
Combinar `air-size` más fino **con** `padding` más grande (fila 3) sí dio
una mejora real, aproximadamente a la mitad del error en todos los puntos.

**Detenido aquí por precaución, no por un límite alcanzado**: el
siguiente paso natural (`air-size=0,10` manteniendo `padding=3,0`)
extrapola, según cómo escaló la memoria en los tres pasos de arriba
(~3,1KB/tetraedro en el solve de la fila 3), a unos 5 millones de
tetraedros y **~15GB de pico** — peligrosamente cerca del total de RAM+
swap de esta VM (15GB+12GB). No se intentó. Refinar más allá de la fila 3
requeriría una VM con más recursos, o un enfoque de mallado más eficiente
en memoria (fuera del alcance de este documento).

**Estado**: 7,6% de error en el punto central es un resultado razonable
para una validación de método, no una cifra de producción aceptada — el
equipo debe fijar su propio presupuesto de error antes de usar este mapa
para dosimetría. Los tres pilotos completos (mesh + solve + comparación)
quedan en `field/generated/crewhat_elmer_tape12mm{,_r2,_r3}/`
(no versionado, regenerable con los comandos de este documento).

### Convención de signo de `Coil Normal`, validada para una bobina rotada (2026-09-10)

Antes de intentar el arreglo de 8 bobinas, se necesitaba saber si el
signo de `Coil Normal` encontrado para la bobina sin rotar (`0 0 -1` en
vez de `0 0 1`, ver arriba) sigue aplicando igual para una bobina
**rotada** (cada una de las 8 bobinas del arreglo tiene su propio eje
propio, distinto de la bobina individual ya validada — incluso la "menos
rotada" del arreglo real está a 90° de la orientación de esa bobina
individual). Probarlo con las 8 bobinas reales habría sido caro; en
cambio, se construyó **una sola bobina aislada** con la orientación real
que tendría la bobina k=1 de un arreglo n=8 (normal en dirección Y,
`halbach_orientation()` de `generate_ellipse_array.py`, sin generar las
otras 7) — mismo principio que ya usa el proyecto de aislar el caso más
simple posible antes de la geometría cara completa.

**Resultado**: con `Coil Normal = -normal_de_la_bobina` (el mismo
principio de signo invertido ya encontrado, ahora confirmado para una
rotación genuina, no solo el caso trivial sin rotar), el signo coincide
correctamente con Biot-Savart (ambos con la misma componente Y positiva
dominante) — sin necesidad de probar las 8 orientaciones una por una.
Error de magnitud 22%-72% (creciente con la distancia), coherente con la
misma malla deliberadamente gruesa (14.350 tetraedros de conductor,
padding=2,0/air-size=0,3) usada para el primer intento seguro de la
bobina sin rotar — no evidencia de un problema de signo residual, la
firma de un problema de signo sería un vector opuesto, no solo magnitud.
Pico de memoria: 345MB, 11,5s — trivial.

**Regla confirmada para el arreglo completo**: al construir el `.sif` de
las 8 bobinas, cada `Component k` debe usar
`Coil Normal = -n_k` (negativo de la dirección de momento calculada por
`halbach_orientation()`), consistente para las 8, sin necesitar validar
cada una por separado.

### Riesgo de memoria del arreglo completo: estimado, no intentado

Extrapolando de los datos medidos arriba (bobina individual, ~3,1KB de
memoria de solve por tetraedro) y la relación de volumen de dominio entre
una sola bobina y el arreglo completo (bounds del arreglo ~42x el volumen
de la envolvente de una sola bobina): mallar el aire alrededor de las 8
bobinas con los parámetros **más gruesos ya usados con seguridad** para
una sola bobina (padding=2,0/air-size=0,3) extrapola a **~4,6 millones de
tetraedros y ~14,5GB de pico** — peligrosamente cerca del total de RAM+
swap de esta VM (15GB+12GB), compitiendo además con todo lo demás en
ejecución. **No se intentó el mallado/solve del arreglo completo por esta
razón.**

**Camino recomendado, no implementado todavía**: la magnetostática con
corrientes prescritas es lineal (ya establecido para la superposición de
Biot-Savart del arreglo, `compute_field_ellipse_array.py`) — en vez de
mallar y resolver las 8 bobinas juntas en un solo dominio de Elmer
(costoso y riesgoso), se podría resolver **una sola bobina aislada** en
Elmer (con su propio dominio, ya validado arriba y en la bobina rotada de
prueba) y usar la **simetría rotacional del arreglo Halbach** para obtener
la contribución de las otras 7 rotando esa misma solución, sumando las 8
copias rotadas por superposición — evitando por completo mallar el
dominio combinado. Esto requiere interpolar y rotar la malla/campo de
Elmer numéricamente (no implementado), pero mantiene el costo de memoria
igual al de una sola bobina para las 8 evaluaciones.

## Lo que aún no existe
- **Nave/hábitat**: `shipRadius`/`shipHalfLength` ya son configurables
  (ver AGENTS.md) y se decidió escalar a 4,5m, pero la longitud axial del
  hábitat no está dada por ninguna fuente, y la ubicación de las bobinas
  relativa a ese casco más grande sigue sin resolver — ver arriba.
