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

## Lo que aún no existe

- **Arreglo de las 8 bobinas** (análogo a `generate_array.py`/
  `geom14_array_pilot.json`): no implementado. Requiere el patrón angular
  de las 8 bobinas en el toro Halbach — no dado por ninguna fuente (ver
  `ELMER_VALIDATION.md`), tendría que aplicarse como fórmula estándar de
  Halbach dipolar, marcada explícitamente como tal — y resolver la
  ubicación real relativa al casco de 4,5m (ver arriba).
- **Elmer FEM**: no probado sobre esta geometría todavía. Solo Biot-Savart
  regularizado (ver arriba).
- **Material HTS real**: el CAD usa cobre puro placeholder, no el material
  homogeneizado de la cinta YBCO/CORC (análogo a
  `hts_tape_materials.json` de Geom14, con su propia composición).
- **Nave/hábitat**: `shipRadius`/`shipHalfLength` ya son configurables
  (ver AGENTS.md) y se decidió escalar a 4,5m, pero la longitud axial del
  hábitat no está dada por ninguna fuente, y la ubicación de las bobinas
  relativa a ese casco más grande sigue sin resolver — ver arriba.
