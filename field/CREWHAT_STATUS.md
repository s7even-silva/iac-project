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

## Lo que aún no existe

- **Arreglo de las 8 bobinas** (análogo a `generate_array.py`/
  `geom14_array_pilot.json`): no implementado. Requiere, además del
  generador de una bobina (ya hecho), el patrón angular de las 8 bobinas
  en el toro Halbach — no dado por ninguna fuente (ver
  `ELMER_VALIDATION.md`), tendría que aplicarse como fórmula estándar de
  Halbach dipolar, marcada explícitamente como tal.
- **Mallado swept / Elmer**: no probado sobre esta geometría. `mesh_swept.py`
  está acoplado a `generate_dh.py` específicamente (importa su `controls()`
  y `has_tape_section()`) — necesita el mismo tipo de generalización que ya
  se aplicó aquí (reutilizar `_conductor_profile`), no reescribirse desde
  cero, antes de poder mallar esta bobina con tetraedros estructurados en
  vez de mallar todo el sólido vía Gmsh 2D/3D estándar (que, al ser una
  sola elipse sin curvatura tan cerrada como la Double Helix, quizás sí
  complete sin el workaround de `mesh_swept.py` — no probado todavía).
- **Material HTS real**: el CAD usa cobre puro placeholder, no el material
  homogeneizado de la cinta YBCO/CORC (análogo a
  `hts_tape_materials.json` de Geom14, con su propia composición).
- **Nave/hábitat**: `shipRadius`/`shipHalfLength` ya son configurables
  (ver AGENTS.md) y se decidió escalar a 4,5m, pero la longitud axial del
  hábitat no está dada por ninguna fuente — sigue siendo una decisión
  pendiente del equipo, no resuelta por este generador.
- **Comparación cinta vs. CORC**: ambas variantes generan geometría
  correctamente (este documento), pero no se ha corrido ningún cálculo de
  campo (Biot-Savart ni Elmer) sobre ninguna de las dos todavía.
