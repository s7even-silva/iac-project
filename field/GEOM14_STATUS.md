# Ficha del imán: referencia ARSSEM frente a implementación

Actualizado 2026-09-08. **Geom14 es la base de referencia elegida, no una
geometría completa ya implementada ni una ficha constructiva cerrada.**
El JSON `examples/dh_pilot.json` se identifica expresamente como
`computational_pilot_not_geom14`. El generador solo admite ese estado.

## Cambiar el physics list de ActiveShield_Sim (Shielding vs. QGSP_BIC_HP)

Mecánicamente es un cambio de pocas líneas en `ICRP110phantoms.cc`: reemplazar
`#include "QGSP_BIC_HP.hh"` + `new QGSP_BIC_HP()` por `G4PhysListFactory` +
`GetReferencePhysList("Shielding")`, igual que ya hace `GCR_SEP_Sim/main.cc`.
Ambas son `G4VModularPhysicsList`, así que el resto del código no cambia.

Un detalle que sí hay que replicar si se hace este cambio (o si se agrega
campo magnético confinante con cualquier lista): `GCR_SEP_Sim` registra
además `G4StepLimiterPhysics()` para que `SetUserMaxTrackLength()` funcione
y evite partículas atrapadas girando en el campo (ver nota técnica en
`AGENTS.md`) — no es específico de `Shielding`, hace falta con cualquier
lista si el campo puede confinar partículas indefinidamente.

**Ventajas/desventajas:** `Shielding` está diseñada específicamente para
problemas de blindaje de radiación (la recomendación oficial de Geant4 para
este tipo de estudio) y tiene buena cobertura de neutrones de baja energía,
pero es más cara computacionalmente. `QGSP_BIC_HP` (heredada del ejemplo
oficial de ICRP110) usa Binary Cascade, preciso en el rango de energías
típico de dosimetría médica/de fantomas — tiene precedente directo para
"dosis por órgano en un fantoma humano". Ninguna es objetivamente superior
para este caso; lo que sí importa (ya señalado en la sección de más abajo)
es que ambos proyectos comparen bajo la misma lista si sus resultados se van
a poner uno junto al otro — mezclar listas entre `GCR_SEP_Sim` y
`ActiveShield_Sim` invalidaría esa comparación aunque cada uno por separado
sea razonable. Decidir cuál usar en producción, con benchmarks reales, sigue
pendiente y no bloquea el trabajo de geometría del imán.

## Referencias publicadas y pendientes

Fuente: [ARSSEM](https://arxiv.org/pdf/1209.1907), §4.3, §5.1 y §6.
No mezclar el diseño electromecánico conceptual con las simplificaciones
de las configuraciones de transporte radiológico:

| Magnitud | Referencia publicada | Lo que todavía falta cerrar para nuestro arreglo |
|---|---|---|
| Topología | Concepto DH de 12 bobinas laterales (§4.3); barrel/endcaps en la familia Geom13/14 (§5.1) | Coordenadas, orientación, conexiones y disposición exacta de los extremos |
| Diámetro | DH de 2 m (§4.3); 2,04/1,35 m para barrel/endcaps Geom13 (fig. 5.4) | Distinguir diámetro útil, devanado y envolvente; elegir las dimensiones que se reproducirán |
| Longitud | Concepto de 18 m con meseta de campo de 10 m (§4.3) | Extremos y separación del casco; no sustituir 18 m por 10 m silenciosamente |
| Devanado | Estudio de ocho capas de cinta (§4.3) | Vueltas, paso, inclinación, conexiones serie/paralelo y sentido de cada capa |
| Conductor | YBCO 2G; referencia conceptual de 50 mm × 0,2 mm, película de 2 µm (§4.3) | Conductor concreto, composición completa, fracciones másicas y aislamiento |
| Operación | Estimación Ic≈10 kA a 25 K y 2,5–3 T paralelos a la cinta (§4.3) | Corriente de operación, curva Ic local, deformación y margen; Ic no es Iop |
| Protección | Estudio Geom14 con 2/4/8 T y 4/8/16 T·m (tabla 5.4) | Elegir caso de referencia y trayectorias/región de evaluación |
| Estructura | Conceptos de soporte Al, aislamiento multicapa y criogenia (§6) | Materiales, espesores, contactos y masas de nuestro modelo radiológico |

Geom14 mejora la composición YBCO respecto a Geom13. El informe no equivale a
tener en el repositorio su CAD/CoilCad, todas las coordenadas, la ley de corriente
y la composición lista para importar. Hay además una inconsistencia de unidades
en §4.3: ocho espesores de 0,2 mm suman **1,6 mm**, no 1,6 µm; no adoptar ese
valor textual como espesor sin resolver qué apilamiento describe. **Confirmado
por lectura directa del PDF (2026-09-08): esa contradicción está en el texto
original de ARSSEM tal cual, sin errata ni corrección en ningún otro lugar del
documento** — decidir con criterio propio cuál de los dos números usar (0,2 mm
por capa está citado dos veces y es internamente consistente con "8 capas";
1,6 µm aparece una sola vez y contradice esa multiplicación).

### Qué está y qué no está explícitamente bajo el rótulo "Geom14" (verificado 2026-09-08)

Lectura directa de ARSSEM confirma algo importante para no sobre-prometer
reproducibilidad: **Geom14 no tiene figura propia** (a diferencia de Geom12,
Geom13 y Geom15, que sí tienen Fig. 5.3/5.4/5.5) — se presenta únicamente en
la Tabla 5.4 (p. 69, "*Geom014 with a 2, 4 and 8 T field for the 2 m ⌀ barrel
solenoids*"), reutilizando la geometría de barrel de 2 m de diámetro y 12
bobinas descrita en §4.3, sin repetir sus dimensiones de conjunto. La única
frase del paper sobre qué distingue a Geom14 de Geom13 es literal y escueta:
"*Geom14 with respect to Geom13 has a more accurate simulation of the
composition of the YBCO tape*" — sin tabla de capas ni fracciones másicas.

Explícitamente confirmados en el texto para el diseño DH de §4.3 (que Geom14
hereda): diámetro de bobina **2 m**, **12 bobinas** en arreglo tipo Halbach,
longitud de bobina **18 m** con meseta de campo de **10 m**, **8 capas** de
cinta, ancho de cinta **50 mm**, capa YBCO activa **2 µm**, masa **0,040
kg/m**, temperatura de operación **25 K**, campo perpendicular sobre el
conductor **2,5–3 T**, Ic bajo esas condiciones **~10 000 A**. Geom14 es
**paramétrico** sobre tres campos de barrel — 2 T, 4 T, 8 T (Tabla 5.4) —
con BdL de **4 T·m** (2 T) y **16 T·m** (8 T) explícitos en el texto (el BdL
de la columna 4 T no se declara literalmente); masa de barrel usada en la
física del transporte (no la masa real del imán): **4833 kg** (BL=4 Tm) y
**19 296 kg** (BL=16 Tm), Tabla 5.6; reducción de dosis anual equivalente en
BFO frente a espacio libre: ~41% (2 T), ~42% (4 T), ~61% (8 T), Tabla 5.4.

**No disponible en el paper para Geom14 específicamente** (no es que falte
buscarlo — se confirmó su ausencia por lectura directa):
- Si el arreglo lleva endcaps DH (como Geom12/13) o es únicamente barrel.
- Separación entre las 12 bobinas y radio interior/exterior del conjunto.
- Detalle capa-por-capa de la "composición más precisa" de la cinta YBCO que
  distingue a Geom14 de Geom13 (sustrato, buffer, plata, cobre de
  estabilización, con espesores y fracciones másicas).
- Corriente de operación vinculada explícitamente a Geom14 (el único número
  cercano, 36 000 A, aparece en una figura distinta —fuerzas axiales, Fig.
  4.8— sin conexión textual clara a Geom14).
- Estructura/crióstato específico de Geom14: el detalle de soporte, MLI y
  criogenia con H₂ líquido vive en el capítulo 6, que describe el diseño
  conceptual de misión genérico **sin usar el rótulo "Geom14" en ningún
  momento** — no se puede confirmar que esos números (masa total del
  escudo ≈46 300–48 200 kg, Tabla 6.1) apliquen exactamente a esta variante.

En la práctica, "Geom14" en ARSSEM es una tabla de resultados de dosis
construida sobre la geometría de barrel ya fijada en §4.3, no una ficha
constructiva independiente y completa. Replicarlo con reproducibilidad
literal no es posible solo con este paper — los vacíos de arriba son
decisiones propias del equipo por documentar como tales, no errores de
esta investigación.

## Las cinco brechas de implementación, en orden de dependencia (2026-09-08)

Cada una bloquea la siguiente; no tiene sentido saltar el orden sin invalidar
el trabajo posterior. Los números del paper (sección de arriba) resuelven
buena parte de la brecha 1; las brechas 2-5 son trabajo de código nuevo, no
de investigación bibliográfica adicional.

1. **Fijar los parámetros dimensionales reales.** `generate_dh.py` ya es
   completamente paramétrico (acepta cualquier `radii_m`, `turns`,
   `pitch_m`, `tilt_deg`, `current_A` vía JSON) — no hace falta escribir
   código nuevo para esto, solo reemplazar los valores del piloto por los
   reales, incluyendo las decisiones propias que el paper no cierra
   (endcaps sí/no, separación entre bobinas, etc., ver sección de arriba).
   **Bloqueante técnico:** `controls()` en `generate_dh.py` valida
   invariantes geométricos entre parámetros (`r1 > 4*a`, `pitch > 4*a`,
   etc.) — meter números reales de Geom14 sin ajustarlos juntos puede fallar
   esa validación o crear autointersecciones en la CAD generada. No es
   cambiar un número, es coordinar ~10 parámetros interdependientes hacia
   un diseño geométricamente consistente.

2. **Sustituir cobre circular por la cinta YBCO/CORC real (rectangular).**
   **Implementado 2026-09-09** para CAD (`generate_dh.py`/`generate_array.py`)
   y para el mallado swept de producción (`mesh_swept.py`): declarar
   `tape_width_m`/`tape_thickness_m` en el JSON de una bobina activa la
   sección rectangular (`has_tape_section()` en `generate_dh.py`); sin
   esas claves, el generador sigue usando el disco circular de siempre, sin
   ningún cambio de comportamiento para `dh_pilot.json` ni para los pilotos
   existentes. `conductor_radius_m` se sigue exigiendo siempre, incluso con
   cinta real: alimenta el núcleo regularizado de Biot-Savart en
   `compute_field.py`, una aproximación de campo cercano independiente de
   la forma real de la sección (ver más abajo, "núcleo regularizado").

   - **CAD** (`_conductor_profile()` en `generate_dh.py`, reutilizada por
     `generate_array.py`): el ancho de la cinta se orienta a lo largo de la
     dirección radial local (ortogonalizada contra la tangente de la
     espina, Gram-Schmidt), el espesor a lo largo de la binormal resultante
     — la cara ancha de la cinta queda enfrentando el eje de la bobina,
     coherente con "campo perpendicular a la cinta" de ARSSEM §4.3. Es la
     mejor aproximación geométrica disponible sin una ley de orientación
     por vuelta publicada por ARSSEM (brecha 1 sigue sin resolver eso).
   - **Malla de producción** (`ribbon_tetrahedra()` en `mesh_swept.py`):
     usa el mismo marco de rotación mínima que `tube_tetrahedra()`
     (`frames()`), con nodos solo en el perímetro del rectángulo (sin
     grilla interior — la cinta es un rectángulo delgado, no necesita
     resolución interna para transporte GDML ni para masa). Validado contra
     el volumen analítico de un toro de sección rectangular delgada
     (`test_ribbon_torus_and_orientation`, error <0,1%) y contra la
     geometría real de producción del barrel (60 vueltas, ~936 m de
     espina): 2,55M tetraedros en 14,3 s, 0,004% de error de volumen
     respecto a `length × width × thickness` — mejor que el ~2,6% del
     círculo, porque 4 segmentos de ancho + 1 de espesor por defecto
     capturan la sección real con menos error de discretización que un
     círculo aproximado por `sectors` lados.
   - **Material:** sigue siendo el compuesto homogeneizado
     (`hts_tape_materials.json`), no capas separadas — decisión ya tomada
     como primer paso, permitida por `modelo_realista.md`; homogeneizar
     por capas separadas queda fuera de esta brecha.

   **Hallazgo nuevo, acopla esta brecha con la brecha 1:** la cinta real
   (50 mm de ancho) **no cabe** en la separación radial actual de
   `geom14_array_pilot.json` (`radii_m` de las dos hélices concéntricas
   difieren solo 20 mm; `controls()` exige `width < (r2-r1)/4 = 5 mm`, y lo
   rechaza correctamente si se intenta). Esos radios fueron elegidos para
   un conductor delgado circular (radio equivalente 1,22 mm), no para una
   cinta plana de 50 mm — activar la sección rectangular en el arreglo de
   producción real exige **primero** redimensionar `radii_m` (separación
   entre las dos hélices del Double Helix) de forma coordinada, exactamente
   el tipo de ajuste conjunto de ~10 parámetros que la brecha 1 ya advertía
   como pendiente. No se ha inventado un valor de separación nuevo — eso
   sería exactamente lo que `AGENTS.md` prohíbe ("no inventar dimensiones
   de bobinas"). La demostración de extremo a extremo (CAD → swept → GDML,
   `test_tape_section_end_to_end_cad_and_swept_agree`) usa la geometría
   pequeña de `dh_pilot.json`, con radios propios ya separados lo
   suficiente para una cinta de prueba, no el arreglo de tres bobinas real.

3. **Configurar y ejecutar Elmer.** Elmer instalado 2026-09-09 (compilado
   desde fuente vía `scripts/install.sh --with-elmer`,
   `~/.local/elmerfem/bin/ElmerSolver`). Piloto completo de una bobina
   (`dh_pilot.json`) implementado y corriendo de punta a punta:
   - **Dominio FEM**: `field/generate_elmer_domain.py` (nuevo) genera una
     esfera de aire conforme alrededor del conductor circular (fragment de
     OpenCASCADE, no boolean subtract, para compartir malla en la
     interfaz), con un campo de tamaño de malla `Distance+Threshold` de
     Gmsh — necesario porque `Mesh.MeshSizeFromCurvature` global refina
     también la esfera exterior lisa tan fino como el conductor
     milimétrico, generando un problema 3D que nunca termina (confirmado
     empíricamente: 126k nodos de superficie, 3D sin terminar en 55s+).
     Con el campo de tamaño correcto: 2,85M tetraedros en 17,7s.
   - **Densidad de corriente**: `field/examples/elmer_pilot.sif` usa
     `CoilSolver` (`Coil Closed = Logical True`) para calcular `J`
     automáticamente sobre la geometría real de la hélice — no hace falta
     invertir la parametrización a mano. Encontrado en
     `fem/tests/CoilSolverLoop/case.sif` del propio repo de ElmerCSC (vía
     búsqueda de código en GitHub), plantilla más cercana al caso de bobina
     cerrada que el ejemplo `mgdyn_steady_coils` (que usa electrodos
     abiertos, `Coil Start`/`Coil End`, no aplica a un devanado cerrado).
   - **Solver magnetostático**: `WhitneyAVSolver` (elementos de borde,
     formulación A-V) + `MagnetoDynamicsCalcFields` (recupera B desde A),
     ambos de `MagnetoDynamics.F90`, siguiendo el ejemplo oficial
     `mgdyn_steady_coils/case.sif`.
   - **Exportador a grilla regular**: `field/elmer_to_map.py` (nuevo) lee
     el VTU ascii de salida (`Ascii Output = True`, sin depender de
     vtk/pyvista — parseo por streaming con `xml.etree.iterparse`,
     necesario porque un VTU de 252 MB con `ET.parse()` completo hizo OOM
     en esta máquina de 5,7 GB de RAM corriendo justo después de
     ElmerSolver) e interpola por coordenadas baricéntricas a la misma
     grilla `.map` que ya lee `TabulatedMagneticField` en Geant4. La
     búsqueda del tetraedro que contiene cada punto usa un hash espacial
     por celdas (no una matriz de distancias `O(puntos×tetraedros)`, que
     para 2,6M tetraedros pedía ~12,5 GB) — el tamaño de celda se fija por
     el percentil 95 del tamaño de tetraedro (no la mediana), porque una
     malla graduada tiene tetraedros hasta 65x más grandes lejos del
     conductor que cerca de él, y un tetraedro grande debe indexarse en
     TODAS las celdas de su bounding box, no solo la de su centroide, o se
     pierde cobertura en la región gruesa (confirmado: cobertura subió de
     21,7% a 100% al corregir esto).

   **Dos bugs reales encontrados y corregidos en el `.sif` (2026-09-09),
   ambos copiados sin darse cuenta del propio ejemplo oficial de Elmer:**
   - `Normalize Coil Current = Logical True` faltaba. Sin ella,
     `CoilSolver.F90` salta por completo el bloque que escala la densidad
     de corriente al valor de `Desired Current Density` (`IF (.NOT.
     NormalizeCoil(Coil)) CYCLE`) y deja la corriente en la escala interna
     que resulta de resolver el potencial `CoilPot`, no la corriente física
     pedida.
   - `Permeability = 1.0` (el nombre usado en el ejemplo oficial
     `mgdyn_steady_coils/case.sif`) no es la keyword que
     `MagnetoDynamicsUtils.F90` lee — busca literalmente `Relative
     Permeability`, y si no la encuentra devuelve un tensor de
     permeabilidad **cero** (no un valor por defecto de 1.0). Con
     permeabilidad cero, `WhitneyAVSolver` resuelve un sistema
     numéricamente mal condicionado. Cambiar a `Relative Permeability =
     1.0` es el fix.
   - **Cómo se encontraron**: no por lectura de código antes de correr,
     sino por diseñar un caso de diagnóstico aislado (espira circular
     plana simple, con solución analítica exacta en el eje,
     `B_z=μ₀IR²/2(R²+z²)^1.5`) que corre en ~30s en vez de ~40min — la
     primera corrida real de la doble hélice completó sin errores pero
     dio un campo con dirección inconsistente punto a punto y magnitud
     ~2,4x el error relativo esperado; aislar la topología compleja
     (doble hélice) del resto del pipeline con la espira simple permitió
     ver que el error real era ~800.000x (cercano a 1/μ₀, confirmando la
     hipótesis de la keyword de permeabilidad) en vez de un problema de
     orientación/dirección como parecía inicialmente en la geometría
     compleja. **Lección**: para depurar un pipeline FEM caro, aislar con
     el caso más simple posible con solución analítica conocida ANTES de
     iterar sobre la geometría real cara.
   - **Validado en el caso simple** tras el fix: razón B_Elmer/B_analítico
     entre 0,92 y 0,98 cerca del conductor (antes: hasta 800.000x de
     error) — el ~5-8% de discrepancia sobrante es del orden esperado por
     discretización de malla y truncamiento del dominio (esfera de aire
     finita con `AV=0` en su cáscara exterior, no un dominio infinito real).
   - **Repetido sobre la geometría real de `dh_pilot.json`** (doble hélice,
     3 vueltas): con el mismo dominio de esfera de aire grande (radio
     1,95 m, generado por `generate_elmer_domain.py`/OpenCASCADE), el
     campo de Elmer resultó 3-6x **menor** que Biot-Savart, con la razón
     empeorando con la distancia (0,17 cerca, 0,32 lejos) en vez de
     mantenerse estable — patrón distinto y peor que la espira simple, y
     no explicado por ningún parámetro del `.sif` revisado hasta ahora
     (se descartó `Single Coil Cut`: ninguno de los dos casos lo usa).

   - **`field/mesh_swept_air.py` (nuevo, 2026-09-09):** el dominio FEM vía
     `generate_elmer_domain.py`/OpenCASCADE cuelga en la triangulación 2D
     de Gmsh para geometrías de varias vueltas — confirmado igual que la
     brecha 5 (mallado GDML), esta vez con un solenoide corto de
     diagnóstico (5 vueltas, 0,9 m de avance axial): 2D nunca termina, con
     o sin aire. Este módulo genera **ambas** regiones (`conductor` y
     `air`) con tetraedros estructurados a lo largo de la espina, evitando
     Gmsh 2D por completo, igual que `mesh_swept.py` ya hace para el
     conductor solo:
     - Un cascarón de aire (anillos concéntricos entre `conductor_radius`
       y `air_radius`) alrededor de la misma espina, con la interfaz
       conductor/aire compartiendo nodos exactos (topología conforme,
       verificado con `mesh_to_gdml.py:boundary()` sobre ambas regiones).
     - **Bug real corregido durante el desarrollo**: la primera
       descomposición de cada celda hexaédrica en 6 tetraedros usaba una
       diagonal de corte por orden de esquina local, no consistente entre
       celdas vecinas — dos hexaedros que comparten una cara la
       triangulaban con diagonales distintas, dejando caras sin pareja
       (`boundary()` lo detectó como "Duplicate or inconsistently joined
       tetrahedra"). Corregido con una convención de diagonal derivada
       únicamente de los índices globales de cada cara (el corte pasa
       siempre por la esquina de menor índice), que ambas celdas vecinas
       calculan igual sin coordinarse.
     - **Límite real descubierto, no resuelto**: `air_radius` está acotado
       por el radio de curvatura mínimo de la espina — un tubo de aire más
       ancho que la curva puede doblar se autointerseca en los retornos
       suavizados de la doble hélice (radio de curvatura mínimo medido
       ~0,0373-0,0377 m, **convergente** al refinar la espina, confirmando
       que es una propiedad geométrica real de `controls()`, no un
       artefacto de muestreo). Para `dh_pilot.json` esto limita
       `air_radius` a ~2,5x `conductor_radius_m` (cascarón de solo 1,5x de
       espesor extra) — mucho más delgado que la esfera de radio
       1,95 m (~162x el conductor) que sí completa vía OpenCASCADE. Con
       ese cascarón delgado, `AV=0` en la frontera contamina el campo
       incluso muy cerca del conductor (razón ~0,52-0,61 vs Biot-Savart,
       con diferencias de **dirección** notables, no solo magnitud) — la
       condición de frontera artificial está demasiado cerca para no
       distorsionar la solución. Revisado el código fuente de
       `WhitneyAVSolver.F90`: la condición Robin disponible (`Magnetic
       Field Strength` + `Magnetic Transfer Coefficient`) está pensada
       para inyectar un campo externo prescrito o modelar pérdidas, no
       para aproximar mejor un dominio infinito — no resuelve este límite.
       **Sí funciona y es muy rápido** (32,5 s vs. 40 min con el dominio
       CAD grande) para geometría/topología, pero no da hoy un campo
       comparable a Biot-Savart para curvas de curvatura fuerte como esta.
   - **Estado 2026-09-09**: ninguno de los dos caminos de dominio de aire
     (esfera grande vía CAD, cascarón delgado vía `mesh_swept_air.py`) da
     un campo Elmer validado contra Biot-Savart sobre la geometría real
     de la doble hélice. El camino de la esfera grande completa en tiempo
     razonable (40 min) pero da una discrepancia de dirección/magnitud sin
     diagnosticar; el camino del cascarón delgado es rápido pero
     geométricamente limitado a un dominio demasiado pequeño para esta
     curvatura. **No bloquea el proyecto**: la simulación piloto de
     Geant4 (bobina + campo) ya corre de punta a punta usando el mapa
     Biot-Savart regularizado (`compute_field.py`), que es la vía activa
     documentada — ver `geant4/ActiveShield_Sim/tests/dh_pilot.mac`.

4. **Validar el campo Elmer contra Biot-Savart** lejos del conductor (donde
   Biot-Savart es válido sin regularización), antes de confiar en el mapa
   FEM. El flujo de auditoría ya existe en miniatura (`audit_dh.py` calcula
   sondas de campo con el mismo `field_at()` de `compute_field.py`) — falta
   aplicarlo al mapa Elmer real en vez del Biot-Savart regularizado actual.
   **Validación preliminar 2026-09-09** sobre la espira circular de
   diagnóstico (no la geometría del piloto): ver detalle en brecha 3
   arriba. Falta repetir sobre `dh_pilot.json` y formalizar como script
   reutilizable (hoy es un análisis manual, no una herramienta en el repo).

5. **Convergencia de dominio/malla, y solo entonces replicar a 12 bobinas.**
   El pipeline ya sigue el orden correcto (una bobina primero, ver
   `DOMAINS.md`) — expandir a las 12 bobinas de Geom14 es repetición y
   transformación geométrica del mismo generador una vez validados los
   pasos 1-4, no una reescritura. Replicar antes de validar multiplicaría
   el costo de mallado/Elmer y propagaría cualquier error de diseño doce
   veces en vez de una. **Estado 2026-09-08:** `generate_array.py` y
   `audit_array.py` generan y auditan el arreglo de 3 bobinas (barrel + 2
   endcaps) con datos numéricos reales — CAD, volumen, masa por material, NI
   por bobina. El mallado (CAD → `.msh`/GDML) tenía dos bugs reales que
   colgaban el proceso indefinidamente en geometrías de muchas vueltas
   (ninguno era el tamaño de malla, que fue el primer sospechoso): (1) el
   número de cortes de la curva antes del barrido/fusión estaba fijo en 8
   sin importar cuántas vueltas tuviera la bobina, causando que el disco
   barrido se autointersecara dentro de un mismo tramo a partir de 7+
   vueltas y la fusión booleana de OpenCASCADE nunca convergiera; (2) el
   algoritmo de mallado 3D de Gmsh (Delaunay) se cuelga en sólidos barridos
   largos y muy curvados incluso con (1) ya corregido — cambiar al
   algoritmo HXT resolvió esto para geometrías de tamaño intermedio
   (confirmado hasta 8 vueltas / ~25 m). **Ambos corregidos**
   (`generate_dh.py`/`generate_array.py`: cortes escalados con `turns`;
   `generate_mesh.py`: `Mesh.Algorithm3D` Delaunay→HXT), con prueba de
   regresión en `field/tests/test_field.py::test_mesh_patch_count_scales_with_turns`.
   **Resuelto de raíz (2026-09-09), no era un tercer bug de la familia de
   HXT/Delaunay sino un límite real del mallado 2D de OpenCASCADE:** el
   arreglo de producción (60 vueltas, ~934 m de conductor) nunca completaba
   con HXT — timing por etapa confirmó que se atasca en la triangulación
   **2D** de Gmsh, antes siquiera de llegar a la etapa 3D (HXT). Ni cambiar
   de algoritmo 2D, ni acortar tramos, ni seccionar el conductor en cuatro
   arcos lo resolvió. **Solución: `field/mesh_swept.py`**, que abandona
   OpenCASCADE/Gmsh 2D por completo — genera directamente tetraedros
   estructurados a lo largo de la curva espinal (marcos de rotación mínima
   + anillos de sección circular), sin construir ni triangular un sólido
   CAD. El arreglo completo (barrel + 2 endcaps) generó 6,24M tetraedros en
   **62,5 segundos**, con ~2,6% de error de volumen respecto al CAD
   analítico (dentro del guardrail de 5% del script). La conversión a GDML
   (`mesh_to_gdml.py`) también se optimizó (vectorización con NumPy de la
   extracción de superficie, antes en Python puro): de 10+ minutos sin
   terminar a 3m16s para el GDML completo (700 MB, ~4,2M triángulos),
   validado con hash SHA256 idéntico al resultado sin optimizar. Detalle
   técnico completo en `field/README.md`.

El lado de Geant4 (importar GDML + leer un mapa de campo tabulado) ya está
completo y probado (`/spacecraft/coilGeometry`, `TabulatedMagneticField`) —
toda la brecha real está en generar los datos de Geom14 que Geant4 va a
consumir, no en la integración con Geant4 en sí.

## Valores que sí ejecuta el código hoy

| Parámetro del piloto | Valor |
|---|---|
| Circuitos y hélices | Un circuito cerrado, dos hélices concéntricas y retornos suavizados |
| Centro / eje | (4,0,0) m / Z |
| Radios de trayectoria | 0,35 y 0,65 m |
| Vueltas | 3 por hélice |
| Paso / inclinación | 0,30 m/vuelta / ±45° antes del suavizado |
| Avance axial del término de paso | 0,90 m; la extensión total también incluye inclinación y retornos |
| Sección / material | Circular, radio 0,012 m; cobre elemental, 8960 kg/m³ |
| Corriente | 100 A en todo el circuito, recorrido contrario en las dos hélices |
| Temperatura, Ic, crióstato, soporte, aislamiento | No modelados |
| Solver del campo | Biot–Savart regularizado en Python/NumPy; **Elmer no está configurado ni se ejecuta** |

Estos son valores de desarrollo, no una reducción a escala validada de Geom14.
Replicar esta bobina doce veces no bastaría para reproducirlo. La operación inicial
seguirá siendo magnetostática con corrientes prescritas; corrientes de apantallamiento,
transitorios y quench permanecen fuera del alcance implementado.

## Qué significa campo de protección

Es el campo exterior que atraviesan las partículas antes de llegar al hábitat.
Evaluar su distribución y `∫B_perp ds` en trayectorias representativas, además de
la respuesta radiológica. Propongo **el caso de referencia de 2 T / 4 T·m** como
primer objetivo de comparación con ARSSEM; todavía no se ha dimensionado un
devanado que lo produzca. No significa 2 T uniformes en la cabina ni en todo World.
**Confirmado por lectura directa (2026-09-08):** ARSSEM sí evalúa exactamente
el par 2 T / 4 T·m para Geom14 (Tabla 5.4, ~41% de reducción de dosis anual
equivalente en BFO frente a espacio libre), junto con 4 T y 8 T (este último
con 16 T·m explícito; el BdL de la columna 4 T no aparece declarado en el
texto). Elegir 2 T/4 T·m como primer objetivo es entonces comparar contra
el caso *más conservador* de los tres que reporta el paper, no el único
disponible — subir a 8 T/16 T·m casi duplica la reducción de dosis reportada
(~61%) a costa de más masa de barrel (19 296 kg vs. 4833 kg, Tabla 5.6).

Se deben informar por separado:

- Campo útil y uniformidad en una región explícita de protección.
- Máximo sobre el conductor, con componentes paralela/perpendicular a la cinta.
- Máximo residual en toda la cabina, con un límite de diseño aún por acordar.

El auditor actual solo informa **dos sondas puntuales**: centro de la bobina y
origen de la cabina. Para el piloto, sus módulos son aproximadamente 0,384 mT
y 0,931 µT, respectivamente. No son máximos ni demuestran protección efectiva.
El núcleo regularizado impide utilizar ese cálculo como campo exacto dentro
del conductor; el máximo del devanado queda explícitamente `null`.

## Consistencia numérica y corriente crítica

Sí, hay que comprobarla antes del arreglo completo. Conviene distinguir `ℓc`
(longitud de conductor, metros) de `Ic` (corriente crítica, amperios):

- `N I` da amperio-vueltas. En el piloto son **300 A·vueltas por hélice**;
  no se suman como escalares dos hélices recorridas en sentido contrario.
- La longitud total medida de la trayectoria es **23,6559 m**, incluidos los
  retornos y todas las vueltas. No volver a multiplicarla por N. `I ℓc` tiene
  unidades A·m; tampoco determina por sí solo B, que depende de toda la geometría.
- Comprobar `∫J·n dS = I` en secciones, continuidad `∇·J=0`, cierre de retornos,
  suma de corrientes en conexiones y asignación de corriente por cinta/cable.
- Con conductor elegido, evaluar `Ic(B,T,θ,ε)` en el devanado y la fracción
  `Iop/Ic`; el margen de corriente es `1-Iop/Ic`. Fijar el margen requerido
  y resolver el campo propio de forma consistente. No usar Ic a 77 K/campo
  propio como si fuera Ic a otra temperatura y campo aplicado.
- Comprobar longitud, sección, masa `ρV`, espesor areal y empaquetamiento; después
  convergencia de FEM, exportación, interpolación, dominio y tracking.

La [ficha de SuperPower](https://www.superpower-inc.com/specification.aspx)
ilustra por qué hay que elegir una cinta concreta: distingue sustrato,
estabilización, aislamiento y dependencia de Ic con temperatura/campo. No se ha
adoptado un producto de ese fabricante ni equiparado con el supuesto de ARSSEM.

Nueva herramienta:

```bash
field/.venv/bin/python field/audit_dh.py \
  field/generated/dh/current_path.json field/generated/dh/audit.json \
  --mesh field/generated/dh/dh.msh
```

La malla debe corresponder al mismo CAD y contener solo el conductor, en metros.
Calcula longitud, NI, masa CAD, volumen de tetraedros, diferencias y sondas de B.
El argumento opcional `--critical-current` solo calcula un cociente con un Ic
aportado por el usuario: **no selecciona una curva ni valida superconductividad**.
Sin Ic, margen y cociente quedan `null`; `production_validated` siempre es `false`.
El auditor no sustituye los chequeos topológicos del conversor ni solapamientos.

## Materiales y criogenia

El GDML DH actual contiene únicamente cobre; **no incluye crióstato**. El soporte
Al del viejo ejemplo del anillo tampoco es soporte del DH. Para el modelo real,
representar por separado el conductor compuesto, aislamiento, soporte y envolvente
térmica, con masas justificadas. No modelar toda una cinta como YBCO puro.
El concepto criogénico del informe no se traduce automáticamente en un recipiente
convencional alrededor de cada bobina: hay que escoger qué envolventes, MLI,
refrigerante y equipos entran en la geometría y justificar exclusiones.

### Material homogeneizado del conductor HTS (implementado 2026-09-08)

`field/examples/hts_tape_materials.json` deja de modelar el conductor como
cobre puro: es un compuesto homogeneizado de 4 capas de una cinta HTS 2G
comercial tipo SCS4050 (SuperPower Inc.), ponderado por **masa por unidad de
área** (densidad × espesor de cada capa, no por espesor simple — una capa
más densa aporta más fracción másica que una capa igual de gruesa pero menos
densa):

| Capa | Espesor | Densidad | Fuente |
|---|---|---|---|
| Hastelloy C276 (sustrato) | 50 µm | 8,89 g/cm³ | Ficha SuperPower confirma el rango (30/50 µm); composición y densidad de proveedores metalúrgicos (Xometry, NeoNickel) |
| YBCO (película activa) | 2 µm | 6,3 g/cm³ | ARSSEM §4.3 (más trazable a nuestra fuente primaria que el ~1 µm de literatura secundaria de SCS4050); densidad de literatura general, **no verificada para película delgada** |
| Ag (recubrimiento) | 2 µm | 10,49 g/cm³ | Literatura secundaria (SuperPower no publica este espesor) |
| Cu (estabilizador, config. SCS) | 20 µm × 2 lados = 40 µm | 8,96 g/cm³ | Dentro del rango oficial SuperPower (5–55 µm/lado) |

Espesor total homogeneizado: **94 µm** — no confundir con los "0,2 mm × 8
capas" del devanado DH conceptual de ARSSEM §4.3, que describe el apilado
completo de 8 cintas de la bobina, no el espesor de una sola cinta 2G real.

**Resultado:** densidad compuesta 8,899 g/cm³, dominado por Cu (43,3%) y Ni
del Hastelloy (29,6%) — coherente con que el sustrato estructural y el
estabilizador de cobre son, en masa, la mayor parte de una cinta HTS real;
el YBCO activo es apenas 1,5% de la masa total pese a ser la razón de ser
del conductor. Composición elemental completa en el JSON, con `_provenance`
por material.

**Limitaciones explícitas de esta aproximación** (documentar en Métodos si
se usa para resultados):
- El **buffer stack** (5 capas cerámicas de óxidos, sub-micrónico) se omite
  por completo — su composición exacta no está disponible en ninguna fuente
  pública consultada, y su masa es despreciable frente a las 4 capas
  modeladas.
- La densidad de YBCO usada (6,3 g/cm³) es un valor de literatura general
  para cristal, no verificado específicamente contra una ficha de película
  delgada depositada por los métodos que usa SuperPower.
- Los porcentajes de Hastelloy C276 usan el **punto medio** de los rangos
  publicados por proveedores (Mo 15–17%, Cr 14,5–16,5%, etc.), no una
  colada certificada específica.
- **Sección transversal rectangular disponible pero no activada en el
  arreglo de producción (brecha 2, implementado 2026-09-09).** El generador
  soporta la cinta real (50 mm × 94 µm) vía `tape_width_m`/`tape_thickness_m`
  en CAD y en el mallado swept de producción (ver brecha 2 más arriba para
  el detalle y la validación) — pero `geom14_array_pilot.json` sigue usando
  el radio equivalente de área porque su separación radial actual (`radii_m`
  a 20 mm) no admite todavía una cinta de 50 mm de ancho sin redimensionar
  el Double Helix de forma coordinada (acoplado con la brecha 1, ver arriba).
  El radio equivalente conserva la masa de conductor correctamente, no la
  forma del campo cercano al devanado; no cambia la validez del mapa
  Biot-Savart de referencia, que de todos modos no es válido cerca del
  conductor con ningún radio ni forma (ver núcleo regularizado más abajo).

## Ensamblaje multi-bobina: barrel + endcaps (implementado 2026-09-08)

`field/generate_array.py` extiende `generate_dh.py` (reutilizando `controls()`
sin modificarla) para ensamblar **varias** bobinas DH en un solo GDML, cada
una con su propio `Physical Volume` y material — necesario porque Geom14
probablemente no es una sola bobina replicada, sino un arreglo de barrel +
endcaps (ver más abajo). El código Geant4 de importación (`/spacecraft/
coilGeometry` en `ICRP110PhantomConstruction.cc`) ya iteraba sobre **todas**
las piezas hijas del GDML importado, no una sola — no requirió ningún cambio
de C++ para soportar múltiples bobinas, solo que el GDML las contuviera.

**Decisión explícita del equipo, no un dato de ARSSEM:** se asume que Geom14
tiene endcaps, igual que Geom12 y Geom13 (misma familia de diseño Double
Helix) — el paper **nunca confirma esto para Geom14 específicamente** (ver
sección de arriba, "Qué está y qué no está explícitamente bajo el rótulo
Geom14"). Es la extrapolación mejor sustentada disponible dentro de la
familia de diseños publicada, no un hecho verificado — debe citarse así en
Métodos, no como si viniera directamente del paper.

`field/examples/geom14_array_pilot.json` es el primer arreglo de validación:
**una** bobina de barrel + **una** de endcap a cada extremo (3 bobinas
totales, no las 12 del arreglo Halbach completo) — sigue la brecha 5 al pie
de la letra: validar la interacción barrel/endcap antes de replicar al
arreglo completo. Dimensiones geométricas (diámetro de barrel 204 cm,
diámetro de endcap 135 cm, longitud de endcap 200 cm) tomadas de la Figura
5.4 de ARSSEM para Geom13, que comparte el mismo barrel de 204 cm que Geom14
según §4.3 — extrapolación directa, no dato propio de Geom14. Vueltas, paso
e inclinación de cada bobina, y la corriente (100 A), siguen siendo
parámetros de desarrollo sin confirmar contra ARSSEM (brecha 1 sigue
abierta en cuanto a devanado real y corriente de operación).

`field/compute_field_array.py` extiende el cálculo de referencia
Biot-Savart por superposición: el campo total en un punto es la suma de la
contribución independiente de cada bobina (`field_at()` de
`compute_field.py`, reutilizada sin cambios, una vez por bobina). Esto es
exacto para corrientes prescritas en un medio con µr≈1 (la magnetostática es
lineal) — la misma aproximación de "corrientes prescritas" ya documentada
como punto de partida operativo más arriba, no una física nueva.

## Physics list y blindaje pasivo

`GCR_SEP_Sim` sigue usando **Shielding**. `ActiveShield_Sim` usa **QGSP_BIC_HP**.
Añadir bobinas o campo no exige cambiar ninguna de las dos. Ambas deben evaluarse
para las especies, energías y secundarios del estudio; mantener la misma lista
en todos los escenarios de una comparación. Para producción, comparar respuestas
por bin con listas candidatas, datos/benchmarks y modelos de iones; el nombre
Shielding no garantiza por sí solo menor incertidumbre.
Fuentes oficiales: [Shielding](https://geant4.web.cern.ch/documentation/dev/plg_html/PhysicsListGuide/reference_PL/Shielding.html)
y [QGSP_BIC](https://geant4.web.cern.ch/documentation/dev/plg_html/PhysicsListGuide/reference_PL/QGSP_BIC.html).
En este cambio **no se cambia la lista física**.

Antes de este cambio solo existían la propuesta de escenarios en ActiveShield_Sim
y las capas legadas en GCR_SEP_Sim. Ahora ActiveShield_Sim dispone de un adaptador
PreInit, repetible, desde el casco hacia fuera, con espesores **en centímetros**:

```text
/spacecraft/addPassiveLayerCm G4_Al 1
/spacecraft/addPassiveLayerCm G4_POLYETHYLENE 2
```

Cada capa es una envolvente cilíndrica cerrada, con tapas planas; no reduce la
cabina ni reemplaza el casco. Las capas son hermanas bajo `MagnetEnvelope`.
Se imprimen masa y densidad areal normal; se rechazan materiales fuera de Al/PE,
espesores no positivos, falta de cobertura del dominio y solapamientos detectados.
No añadir comandos deja las capas desactivadas. Se puede combinar con GDML y
`fieldScale=0/1` para casos pasivo o híbrido. Si la capa invade una bobina,
corregir dimensiones; no se recorta automáticamente.
Los espesores del ejemplo son de prueba. Comparar también a masa o densidad
areal comparable, no solo a igual espesor. Falta el orquestador completo de
escenarios por bins; este adaptador resuelve la geometría, no ese análisis.

## Qué representa el 3,06% de diferencia

Se comparó el **volumen material de la bobina**, no el tamaño de World ni el
volumen de campo:

| Representación del mismo conductor piloto | Volumen (m³) | Masa Cu (kg) |
|---|---:|---:|
| CAD OpenCASCADE | 0,01070421 | 95,9097 |
| Malla lineal / GDML | 0,01037638 | 92,9723 |

`(Vmalla/VCAD - 1) ×100 = -3,0626%`: unos **2,94 kg de cobre menos**.
Los triángulos planos aproximan las superficies curvas. El conversor conserva
el volumen de los tetraedros al extraer su frontera; la pérdida procede del
mallado geométrico, no de omitir arbitrariamente tetraedros en GDML.

Puede afectar espesores atravesados, interacciones y secundarios. **No implica
3,06% de error en dosis**: esa relación no es lineal y hay que medir convergencia
radiológica. El mapa Biot–Savart usa la curva CAD, no esa malla, por lo que la
masa perdida tampoco equivale a una disminución automática de B.

Ahora el JSON expone `mesh_min_size_m`, `mesh_size_m` (máximo) y
`mesh_points_per_circle`. Reducir los dos tamaños y aumentar el refinamiento
por curvatura, regenerar y auditar volumen/masa; luego comprobar dosis. Aumentar
solo los puntos por círculo puede no surtir efecto si el tamaño mínimo lo impide.
Así lo especifica [Gmsh, tamaños de elemento](https://gmsh.info/doc/texinfo/gmsh.html#Specifying-mesh-element-sizes).
El presupuesto de aceptación de masa/dosis final sigue pendiente; 3,06% no se
ha aceptado como precisión de producción.
