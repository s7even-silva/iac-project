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

### Estimación de memoria del arreglo completo: incorrecta, corregida al intentarlo (2026-09-10)

La estimación original de esta sección (~14,5GB de pico, basada en
extrapolar la razón de **envolventes geométricas** entre una bobina y el
arreglo, ~42x) resultó demasiado pesimista — el método de extrapolación
tenía un error real: el padding (2,0m) se suma de forma **fija**, no
proporcional, así que la razón correcta es la de **volumen de dominio ya
mallado** (que sí incluye ese padding fijo), no la de las envolventes
geométricas crudas del conductor. Al intentarlo directamente (con el
límite de cgroup como red de seguridad, no como excusa para no probar):
el dominio real del arreglo completo resultó ser solo ~9,9x el de una
sola bobina, no 42x.

**Resultado real, con los mismos parámetros gruesos ya usados con
seguridad para una bobina** (padding=2,0/air-size=0,3): mallado del aire
en 8,9s con **1,3GB** de pico (1.003.567 tetraedros de aire); `ElmerSolver`
con las 8 bobinas (8 `Component`, cada uno con su propio `Coil Normal`
correcto según la fórmula ya confirmada) completó **"ALL DONE"** en 148s
con **3,4GB** de pico — muy por debajo de cualquier límite, y del total
de RAM+swap de la VM (15GB+12GB). Contabilidad real de systemd, no
estimada.

**Validación física, mejor que la esperada**: comparado contra la
superposición de Biot-Savart de las 8 bobinas (`compare_elmer_array.py`,
mismo principio que `compute_field_ellipse_array.py` pero contra el VTU
de Elmer), 7 puntos dentro de la región de protección (radio 0-4m) dan
**2,4%-15,4% de error**, con las direcciones coincidiendo exactamente en
todos — mejor que el 15,6%-54,8% de la bobina individual con la misma
malla gruesa. Tiene sentido: dentro del anillo, el campo total está
dominado por la contribución conjunta de las 8 bobinas (un régimen más
parecido a campo lejano de cada una), donde tanto FEM como el modelo de
filamento regularizado son más confiables que cerca de una sola bobina
aislada. Este resultado también confirma indirectamente que las 8 señales
de `Coil Normal` son correctas — un signo equivocado en cualquiera habría
producido direcciones erráticas o errores mucho mayores, no un ajuste
tan limpio en los 7 puntos.

**Lección sobre la propia estimación**: extrapolar de una razón de
envolventes geométricas crudas, en vez de medir directamente o razonar
sobre cómo escala el padding fijo, llevó a una sobreestimación de ~4x del
riesgo real. La estrategia de seguridad (límite de cgroup) seguía siendo
correcta como red de contención — pero no debió usarse como razón para
no intentarlo directamente cuando el costo de comprobarlo era bajo.

### Refinamiento del arreglo completo: límite real encontrado (2026-09-10)

Con memoria de sobra confirmada por la corrida gruesa (3,4GB de 27GB
disponibles), se intentó refinar como ya funcionó para la bobina
individual (`padding=3,0/air-size=0,15`). Esta vez sí se encontró un
límite real, no una sobreestimación:

| padding (m) | air-size (m) | tetraedros de aire | pico mallado | pico solve | resultado |
|---|---:|---:|---:|---:|---|
| 2,0 | 0,30 | 1.003.567 | 1,3GB | 3,4GB | 2,4%-15,4% de error (referencia) |
| **3,0** | **0,15** | **10.262.870** | **11,9GB** | **no intentado** | **demasiado grande — el mallado solo ya casi agota el límite de 13GB** |
| **2,5** | **0,20** | **3.773.365** | **4,9GB** | **12GB, 596s (~10 min)** | **2,3%-11,2% de error** |

`padding=3,0/air-size=0,15` (la combinación que funcionó bien para una
sola bobina) generó **10 veces más tetraedros** que la configuración
gruesa para el arreglo completo — el mallado por sí solo llegó a 11,9GB,
y por la misma razón de escala ya observada (el solve necesita ~2-2,5x lo
que necesita el mallado para un conteo de tetraedros comparable), intentar
el solve ahí habría apuntado a ~25-30GB, superando la capacidad total de
la VM. **No se intentó el solve con esa malla.**

`padding=2,5/air-size=0,20` (paso intermedio) sí fue seguro: pico de
12GB durante el solve, confirmado por seguimiento directo del proceso
(no solo contabilidad de systemd al final, dado que el proceso tardó
~10 minutos) — dentro del límite de cgroup de 14GB, sin llegar a usar
swap de forma significativa (700MB de 10GB disponibles). Mejora real
pero más modesta que en la bobina individual: **2,4%-15,4% → 2,3%-11,2%**
(~25-30% de reducción relativa en cada punto, no a la mitad). Tiene
sentido: el resultado grueso ya era bueno porque los puntos de la región
de protección están en un régimen dominado por la contribución conjunta
de las 8 bobinas — hay menos margen de mejora ahí que cerca de una sola
bobina aislada.

**Conclusión práctica**: para este arreglo, en esta VM, `padding=2,5m/
air-size=0,20m` es la configuración más fina que se puede correr con
margen de seguridad real — no un límite artificial, sino el punto donde
el costo de memoria empieza a crecer más rápido que la mejora de
precisión que aporta.

## Nave/hábitat: ubicación de las bobinas verificada a escala real (2026-09-10)

Pendiente resuelto: se corrió `import_crewhat_halbach_array.mac` con
`/spacecraft/shipRadius 4.5 m` explícito (antes solo se había probado con
el valor por defecto de 2,8m, que no garantizaba nada sobre la escala real
decidida para CREW HaT). Resultado: las 8 bobinas (radio Halbach 8m, medio
eje menor 2m) siguen sin ningún solapamiento entre sí ni con el casco a
4,5m — el anillo se mantiene bien alejado del casco (margen ~1,8m en el
punto más cercano, 6m de radio interior de la bobina frente a 4,5m de
radio de nave), consistente con lo razonado pero no antes confirmado a
esta escala específica. Comando reproducible: el macro de
`field/examples/import_crewhat_halbach_array.mac` ya incluye
`/spacecraft/shipRadius 4.5 m`.

**Longitud axial del hábitat: sigue sin dato de ninguna fuente** (NIAC
Phase I lo deja explícitamente indeterminado, p.9) — esto no es algo que
se pueda "resolver" con más búsqueda, ya se confirmó que no existe. Se
mantiene como supuesto propio explícito del equipo: `shipHalfLength=5m`
(10m de longitud total), el mismo valor por defecto heredado de Geom14/
ARSSEM, sin ninguna base de CREW HaT específica — documentado aquí como
decisión consciente, no como pendiente indefinido, para no bloquear el
diseño del barrido de posición (ver AGENTS.md).

## Ablation de patrón angular: Fase 0 y Fase 1 (2026-09-10)

Preparación para comparar el patrón dipolar K=1 suave (actual) contra una
lectura literal "radial/tangencial alternante" del texto de NIAC §5.3.3
(ver más arriba) — sin decidir todavía cuál es mejor, solo la
infraestructura para poder medirlo. Roadmap completo de 8 fases acordado
con el equipo; esto cubre las dos primeras.

**Fase 0 — criterio de comparación fijado.** `field/uniformity_metric.py`
(nuevo): calcula media, desviación estándar y coeficiente de variación de
`|B|` sobre una grilla polar dentro del disco de la región de protección
(radio de nave, varios planos Z), reutilizando `field_at()` sin
modificarlo — misma superposición regularizada ya validada, misma
salvedad de "no es Elmer/FEM" que el resto de estos mapas. Explícitamente
`production_validated: false` y documentado como **un primer criterio
razonable, no el único posible** — el equipo puede refinarlo después, el
punto es tener un número fijo y reproducible en vez de comparar a ojo
unos pocos puntos sueltos, como se hacía hasta ahora.

**Baseline real medido** (arreglo de 8 bobinas CORC, patrón K=1, radio de
nave real 4,5m, grilla 5 radial × 8 angular × 3 planos Z={0,±2}m, 123
puntos): media 0,571T, coeficiente de variación 0,179,
rango 0,467T–0,970T. **El máximo (0,970T) es más alto que el rango
0,42-0,72T reportado antes** — no es una regresión ni un error: los 7
puntos de prueba anteriores nunca muestrearon Z=±2m ni la región angular
completa, así que no habían capturado el punto más fuerte del campo. Es
exactamente el tipo de información que esta grilla sistemática, más
completa, existe para revelar.

**Fase 1 — generador generalizado.** `generate_ellipse_array.py`:
`halbach_orientation()` acepta un `theta_override` opcional (retrocompatible,
por defecto `None` reproduce exactamente la fórmula `θ=(order_k+1)·φ` de
antes). A nivel de config, una clave opcional `theta_deg_pattern` (lista
de N ángulos en grados) reemplaza esa fórmula por un ángulo explícito por
bobina — la posición `φ_k` en el anillo nunca cambia, solo la orientación
del momento. `halbach_order_k` se mantiene como campo obligatorio del
esquema incluso con override, como registro de qué fórmula se está
desviando. El reporte (`array_current_paths.json`) ahora incluye
`angular_pattern` (`"halbach_order_formula"` o
`"explicit_theta_deg_pattern"`) y `theta_deg_pattern`, para que cada
resultado se identifique solo sin depender de a qué archivo de config
apunta. 8 tests nuevos/actualizados en `field/tests/test_ellipse_array.py`
y `field/tests/test_uniformity_metric.py` (46 tests en total en `field/`,
todos verdes).

**Fase 2 — config alternativa generada.**
`examples/crewhat_halbach_array_radial_tangential_pilot.json`: mismo
`coil_template` CORC (idéntico al piloto K=1, para que la comparación sea
sobre lo mismo salvo el patrón angular), con `theta_deg_pattern` explícito
— lectura literal de "radial/tangencial alternante": `k` par → radial
puro (`θ=φ_k`), `k` impar → tangencial puro (`θ=φ_k+90°`). CAD/malla/GDML
generados en `generated/crewhat_halbach_array_radial_tangential/`: mismo
volumen CAD total (69,586518 m³, idéntico a la 6ª cifra decimal al
piloto K=1) y prácticamente el mismo número de elementos de malla
(168.824 vs. 168.834) — confirma que cambiar el patrón angular no cambia
el costo geométrico/de malla, tal como se anticipó.

**Fase 3 — screening Biot-Savart, resultado contundente.**
`uniformity_metric.py` sobre la misma grilla que el baseline K=1 (radio
de nave 4,5m, 5 radial × 8 angular × Z={0,±2}m, 123 puntos):

| Patrón | Media (T) | Desv. est. (T) | CV | Mínimo (T) | Máximo (T) |
|---|---:|---:|---:|---:|---:|
| K=1 suave (actual) | 0,571 | 0,102 | **0,179** | 0,467 | 0,970 |
| Radial/tangencial crudo | 0,198 | 0,158 | **0,799** | 4,0×10⁻¹⁰ | 0,600 |

El patrón crudo es **~4,5x peor en uniformidad**, con **media 3x menor**
y un punto de **cancelación casi total** dentro de la región de
protección (4×10⁻¹⁰T, esencialmente cero) — no es un empate ni un
resultado ambiguo, confirma con margen amplio la predicción de la teoría
de arreglos Halbach (la fórmula suave `θ=2φ` es la que produce un dipolo
interno; una alternancia binaria cruda no sigue esa progresión y degrada
la cancelación de armónicos superiores).

**Fase 4 — solapamiento bobina-nave verificado.** Mismo chequeo que el
patrón K=1, con `shipRadius=4,5m` explícito: sin solapamientos, ni entre
bobinas ni con el casco.

**Decisión: se omite la Fase 5 (validación Elmer) para este candidato.**
El screening barato ya descarta el patrón con margen tan amplio (CV
4,5x peor, punto de campo casi nulo) que invertir ~10-15 minutos y ~12GB
de esta VM en refinar con FEM no cambiaría la conclusión — Elmer solo
tendría sentido si el screening diera un resultado competitivo o
ambiguo, que no es el caso. **Resultado del ablation**: el patrón K=1
suave, ya implementado como configuración de producción, queda respaldado
por esta comparación cuantitativa — evidencia citable para el paper de
que la elección de diseño no fue arbitraria.

**Fase 7 — sensibilidad de fase respecto al barrido de posición del
fantoma (gratis, sin remallar).** Una rotación rígida de todo el patrón
de 8 bobinas alrededor del eje Z es físicamente equivalente a consultar
el mismo campo ya calculado en un ángulo de consulta rotado — así que
`field/phase_sensitivity.py` (nuevo) reutiliza directamente el arreglo K=1
ya generado, sin ninguna geometría/malla nueva, para responder: ¿importa
hacia dónde apunta la fase del arreglo relativo a dónde se desplaza el
fantoma? Muestreo azimutal (16 ángulos) a Z=0, en varios radios:

| Radio (m) | Media (T) | CV | Peor/mejor ángulo |
|---:|---:|---:|---:|
| 1,0 | 0,524 | 0,004 | 1,01x |
| 2,0 (offset probado en `phantom_offset.mac`) | 0,546 | 0,016 | 1,05x |
| 3,0 | 0,587 | 0,036 | 1,11x |
| 4,0 | 0,658 | 0,085 | 1,31x |
| 4,5 (pared de la nave) | 0,711 | 0,168 | 1,64x |

**Conclusión práctica**: cerca del eje (menos de 2m, donde probablemente
pase la mayor parte del barrido de posición inicial) la fase de
instalación del arreglo prácticamente no importa (variación de 5% o
menos) — no hace falta coordinar la orientación del arreglo con la
posición esperada del astronauta. Cerca de la pared de la nave (4,5m) sí
importa, y bastante (hasta 64% de diferencia entre el mejor y el peor
ángulo relativo) — si el barrido de posición del fantoma eventualmente
incluye puntos cerca del casco, esto es evidencia concreta de que la fase
del arreglo relativa a esos puntos sí debería decidirse a propósito, no
dejarse arbitraria.

## Ablation de patrón angular: roadmap completo (2026-09-10)

Las 8 fases del roadmap acordado quedan resueltas (Fases 5-6 resueltas
como "omitidas deliberadamente", no como pendientes sin hacer):

| Fase | Resultado |
|---|---|
| 0 — Criterio de comparación | `uniformity_metric.py`: CV de `\|B\|` sobre grilla de la región de protección |
| 1 — Generador generalizado | `theta_deg_pattern` opcional en `generate_ellipse_array.py`, retrocompatible |
| 2 — Config alternativa | `crewhat_halbach_array_radial_tangential_pilot.json` generada, mismo costo de malla |
| 3 — Screening Biot-Savart | K=1 gana por ~4,5x en uniformidad, con margen decisivo |
| 4 — Solapamiento a escala real | Sin solapamientos para ningún patrón, a 4,5m |
| 5 — Validación Elmer | Omitida deliberadamente (screening ya concluyente) |
| 6 — Comparación contra Elmer | No aplica (depende de la Fase 5) |
| 7 — Sensibilidad de fase | Cuantificada: irrelevante cerca del eje, relevante cerca del casco |

**Resultado para el paper**: la elección del patrón dipolar K=1 suave (ya
en producción desde antes de este ablation) queda respaldada por una
comparación cuantitativa explícita, no solo por analogía con la teoría de
arreglos Halbach — y además se caracterizó cuándo la fase de instalación
del arreglo importaría (barrido de posición cerca del casco) y cuándo no
(cerca del eje). Nada de la configuración de producción cambió: el
resultado de este ablation es evidencia documentada, no un cambio de
diseño.

## Barrido de posición del fantoma: infraestructura agregada (2026-09-10)

La decisión "fantoma fijo, sin barrido de posición" (ver AGENTS.md) se
reconsideró porque el campo Halbach ya validado es genuinamente no
uniforme (0,42-0,72T dentro del anillo, asimetría discreta de 8 pliegues)
— a diferencia de la suposición más simple que probablemente motivó la
decisión original. Implementado en `ICRP110PhantomConstruction`:
`/spacecraft/phantomOffsetX <m>` y `/spacecraft/phantomOffsetY <m>`
(mismo patrón `G4GenericMessenger` que `shipRadius`/`shipHalfLength`,
estado PreInit), desplazan el `phantomContainer` dentro de
`ShipInterior`. Por defecto ambos son 0 — reproduce exactamente el
placement fijo anterior, retrocompatible con cualquier macro existente.
Sin chequeo de límites propio: se apoya en el chequeo de solapamiento
nativo de `G4PVPlacement` (mismo criterio que el resto del proyecto),
que atraparía un offset que saque el fantoma de `ShipInterior`.

Probado con `geant4/ActiveShield_Sim/tests/phantom_offset.mac`
(`shipRadius=4,5m`, `phantomOffsetX=2m`): coloca el fantoma en (2,0,0)m
sin solapamientos. **No es un barrido completo** — falta decidir cuántos
puntos y en qué rango (probablemente radial, como el piloto GCR_SEP_Sim,
0 a shipRadius-hullThickness, pero el campo de CREW HaT también varía
angularmente por su estructura de 8 pliegues, a diferencia del campo
uniforme del piloto), y falta integrarlo con el pipeline de bins de
dosimetría (todavía sin implementar) para que el barrido de posición sea
una dimensión más de ese barrido combinatorio, no un barrido aparte.
