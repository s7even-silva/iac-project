# Mallado y conversión de geometría para Geant4

Estado 2026-09-08: **conversión implementada y probada de extremo a extremo**.
El ejemplo es un anillo de cobre y un soporte de aluminio situados fuera del
hábitat. No representa una bobina Double Helix, REBCO, Geom14 ni un diseño
aceptado del imán. Ese ejemplo no calcula campo ni prescribe corrientes.
Ahora existe además un **piloto Double Helix paramétrico**, con circuito cerrado,
CAD y campo de referencia Biot–Savart regularizado. No es todavía Geom14 ni
una solución Elmer. Ver [alcance, fuentes y plan de dominios](DOMAINS.md).

## Secuencia nueva: Double Helix de ensayo

Ejecutar desde la raíz, tras preparar el entorno indicado abajo:

```bash
# 1. JSON de parámetros → CAD, fuente Gmsh, materiales y recorrido de corriente.
field/.venv/bin/python field/generate_dh.py \
  field/examples/dh_pilot.json field/generated/dh

# 2. CAD → malla tetraédrica del conductor (puede tardar).
field/.venv/bin/python field/generate_mesh.py \
  field/generated/dh/dh.geo field/generated/dh/dh.msh \
  --dependency field/generated/dh/dh.brep \
  --dependency field/examples/dh_pilot.json

# 3. Malla + materiales → geometría transportable por Geant4.
field/.venv/bin/python field/mesh_to_gdml.py \
  field/generated/dh/dh.msh field/generated/dh/materials.json \
  field/generated/dh/dh.gdml

# 4. Recorrido + corriente → mapa de referencia en tesla.
field/.venv/bin/python field/compute_field.py \
  field/generated/dh/current_path.json field/generated/dh/dh.map \
  --half-size 6 --spacing 0.5

# 5. Preparar la propuesta de convergencia, sin lanzar mapas ni eventos.
field/.venv/bin/python field/prepare_domain_sweep.py \
  field/generated/dh/current_path.json field/generated/domain_study \
  --enclosing-radius 10 --spacing 0.5
```

El paso 4 usa la curva del paso 1 y puede ejecutarse independientemente de 2–3.
No calcula B a partir del GDML ni del material cobre. Los 0.5 m son una grilla
gruesa para comprobar el flujo, **no resolución aceptada para producción**.
El radio A=10 m del paso 5 ilustra 20/40/80 m; no es una dimensión adoptada.
Revisar `domain_plan.json` antes de ejecutar `bash .../generate_maps.sh`:
los mapas que excedan un millón de nodos requieren aumentar explícitamente
`--max-points` en el comando, una vez revisados almacenamiento y tiempo.

En los manifiestos quedan hashes y parámetros. Comparar el volumen CAD de
`current_path.json` con volumen/masa de `dh.manifest.json`; refinar la malla
si la discrepancia no cumple el presupuesto de error acordado. Refinar también
`control_points_per_turn` (curva CAD) y `field_segments` (integración del campo).
El mallado exitoso no sustituye el chequeo de solapamientos en Geant4.

Validación del piloto en el entorno fijado: 13 pruebas Python aprobadas, incluida
espira circular analítica, signo de corriente, cierre del circuito, coherencia
del volumen CAD y orden de escritura del mapa. Dos generaciones CAD produjeron
BREP idéntico en este entorno. El ejemplo mallado produce 119558 triángulos
exteriores, volumen 0.01037638 m³ y masa de cobre 92.9723 kg frente a
0.01070421 m³ de CAD (**3.06% de diferencia**). Es una tolerancia de ensayo,
no aceptación para Geom14; habrá que refinar curvatura/tamaño y comparar masas.
La macro `field/examples/import_dh.mac` carga ambos archivos y lanza un geantino
para comprobar navegación; no mide deflexión magnética ni dosis.
Probada con Geant4 11.4.2: campo global leído, pieza de 92.9723 kg importada sin
solapamientos detectados, y geantino entrando en `coil_placement_1` y saliendo
de nuevo al vacío. Ejecutarla desde `geant4/ActiveShield_Sim/build` con
`./ICRP110phantoms ../../../field/examples/import_dh.mac`.

**Elmer es el siguiente paso electromagnético pendiente**, no un comando oculto
de esta secuencia. Faltan dominio exterior FEM, J volumétrica, solver y exportador
de su solución; el mapa de referencia permite desarrollar y comprobar esas piezas.

## Ensamblaje multi-bobina: barrel + endcaps (Geom14)

Extiende la secuencia de una sola bobina a un arreglo (barrel + endcaps),
sin repetir su geometría: reutiliza `controls()` de `generate_dh.py` sin
modificarla, una vez por bobina del arreglo. Ver
[field/GEOM14_STATUS.md](GEOM14_STATUS.md) para las dimensiones exactas
tomadas de ARSSEM (y cuáles son extrapolación, no dato publicado) y el
material homogeneizado del conductor HTS.

```bash
# 1. JSON con N bobinas (barrel + endcaps) → un solo CAD/GDML ensamblado.
field/.venv/bin/python field/generate_array.py \
  field/examples/geom14_array_pilot.json field/generated/geom14_array

# 2. CAD → malla tetraédrica (una malla para las N bobinas juntas).
field/.venv/bin/python field/generate_mesh.py \
  field/generated/geom14_array/array.geo field/generated/geom14_array/array.msh \
  --dependency field/generated/geom14_array/array.brep \
  --dependency field/examples/geom14_array_pilot.json

# 3. Malla + materiales → GDML con un Physical Volume por bobina.
field/.venv/bin/python field/mesh_to_gdml.py \
  field/generated/geom14_array/array.msh field/generated/geom14_array/materials.json \
  field/generated/geom14_array/array.gdml

# 4. Mapa de campo por superposición (suma Biot-Savart de cada bobina).
field/.venv/bin/python field/compute_field_array.py \
  field/generated/geom14_array/array_current_paths.json field/generated/geom14_array/array.map \
  --half-size 15 --spacing 0.5
```

`field/examples/geom14_array_pilot.json` es el primer arreglo de validación:
**una** bobina de barrel + **una** de endcap a cada extremo (3 bobinas, no
las 12 del arreglo Halbach completo) — sigue la brecha 5 de
`GEOM14_STATUS.md` al pie de la letra: validar la interacción entre tipos de
bobina antes de replicar al arreglo completo. El paso 1, con los parámetros
de ese JSON (60 vueltas en el barrel), tardó varios minutos en esta máquina
— las operaciones booleanas de OpenCASCADE escalan mal con el número de
vueltas; para iterar rápido en desarrollo, bajar `turns`/`field_segments`
temporalmente (probado con `turns: 3` y una malla más gruesa, termina en
menos de un minuto) y solo usar los valores reales para la corrida final.

**Causa raíz encontrada y corregida (2026-09-08): dos bugs distintos, ninguno
era `mesh_size_m`.** El colgado del mallado con geometrías de muchas vueltas
se investigó a fondo variando `turns` de forma aislada y controlada (no
solo probando valores de `mesh_size_m` a ciegas), lo que llevó a dos
hallazgos reales:

1. **`generate_dh.py`/`generate_array.py` cortaban la curva helicoidal en un
   número FIJO de 8 tramos, sin importar cuántas vueltas tuviera la bobina**
   (`np.linspace(..., 9)` hardcodeado). Con pocas vueltas cada tramo cubre
   menos de una vuelta y el disco barrido (`addPipe`) no se autointersecta
   dentro de su propio tramo; con más vueltas (confirmado en 7+, con la
   geometría del piloto de una sola bobina) cada tramo cubre una vuelta
   completa o más, el disco barrido se autointersecta dentro del tramo, y
   la fusión booleana de OpenCASCADE (`occ.fuse`) nunca converge — no
   lanza error, simplemente no termina. **Corregido:** el número de cortes
   ahora escala con `turns` (`max(8, ceil(turns/0.5))`), manteniendo cada
   tramo por debajo de ~0,5 vueltas sin importar cuántas tenga la bobina
   completa.
2. **El algoritmo de mallado 3D de Gmsh usado por `generate_mesh.py`
   (`Mesh.Algorithm3D = 1`, Delaunay) se cuelga indefinidamente en sólidos
   barridos largos, delgados y muy curvados** — confirmado aislando el
   problema: con 7 vueltas mallaba en segundos, con 8 vueltas (mismos
   demás parámetros, incluido el fix del punto 1) nunca terminaba pese a
   más de 90s de espera sin ningún mensaje de progreso. Cambiar a
   `Mesh.Algorithm3D = 10` (HXT, el algoritmo 3D moderno de Gmsh, más
   robusto para este tipo de geometría) malló la misma geometría de 8
   vueltas en ~8 segundos. **Corregido:** `generate_mesh.py` ahora usa HXT.

Ninguno de los tres valores de `mesh_size_m` que se probaron antes de este
diagnóstico (6 mm sin escalar, `conductor_radius_m/2`, `conductor_radius_m`)
era la causa real — cada uno tocaba una variable irrelevante al problema
verdadero. La lección: cuando un proceso se cuelga sin error (no lanza
excepción, no hay mensaje), variar un solo parámetro a la vez con casos
mínimos reproducibles (aquí, aislar `turns` en el pilot de una sola bobina
en vez de depurar directamente sobre el arreglo de 3) encuentra la causa
mucho más rápido que ajustar por intuición el primer parámetro sospechoso.

Con ambos fixes, geometrías de tamaño intermedio (confirmado hasta 8 vueltas,
~25 m de conductor, HXT en ~8 s) mallan sin colgarse — ver
`field/tests/test_field.py::test_mesh_patch_count_scales_with_turns` para la
prueba de regresión, con timeout real de subprocess para que un regreso de
cualquiera de los dos bugs falle el test en vez de colgar la suite.

**Límite de escala real con HXT (2026-09-08, abandonado a favor de una vía
distinta):** mallar el arreglo real de Geom14 (barrel de 60 vueltas, ~934 m
de conductor) con HXT nunca terminó en varios intentos (6+ minutos sin
converger, con progreso real de memoria pero sin llegar a completar la
etapa 2D de Gmsh, confirmado con timing por etapa 1D/2D/3D) — el aislamiento
posterior mostró que ni un algoritmo 2D distinto, ni tramos más cortos, ni
seccionar el conductor en cuatro arcos resolvían el atasco: el propio paso
de triangulación 2D de OpenCASCADE es el límite, no un parámetro ajustable.

**Solución adoptada: `field/mesh_swept.py`, mallado directo por tetraedros
estructurados, sin pasar por OpenCASCADE/Gmsh 2D en absoluto.** En vez de
construir un sólido CAD y triangular su superficie, muestrea la curva
espinal con refinamiento adaptativo (control de sagita), calcula marcos de
rotación mínima a lo largo de la curva (evita torsión acumulada en un lazo
cerrado), genera anillos de nodos alrededor de cada sección transversal
circular, y triangula cada prisma en 3 tetraedros con verificación de
orientación (determinante positivo) y de volumen. El arreglo completo de
Geom14 (barrel 60 vueltas + 2 endcaps, 3 bobinas) generó **6,24 millones de
tetraedros en 62,5 segundos**, con error de volumen de ~2,6% respecto al CAD
analítico (dentro del guardrail de 5% del propio script, y comparable al
3,06% ya aceptado como tolerancia de ensayo en el pipeline original). Test
de regresión con un toro analítico (volumen exacto conocido) en
`field/tests/test_swept.py`.

**Conversión a GDML (`mesh_to_gdml.py`) también optimizada (2026-09-09):**
la función `boundary()` (extraer la superficie exterior de los tetraedros)
estaba en Python puro (diccionario + `sorted()` por cara) y tomaba 10+
minutos sin terminar sobre los ~25M caras del arreglo completo. Vectorizada
con NumPy: comparar filas completas con `np.unique(..., axis=0, ...)`
seguía siendo ~15× más lento que codificar cada terna de vértices ordenada
como una sola clave entera (base > máximo id de nodo, codificación
biyectiva) y usar `np.unique` en 1D (benchmarked: 106s → 6,5s en 25M filas).
Mismas correcciones aplicadas al resto de `convert()` (deduplicación de
nodos usados, verificación de finitud de coordenadas) que también hacían
listas/comprensiones Python sobre ~1,4M nodos. Resultado: de 10+ minutos sin
terminar a **3m16s** para el GDML completo (700 MB, ~4,2M triángulos de
superficie) — el resto del tiempo es I/O real (escribir y luego volver a
leer un archivo de 700MB para su hash SHA256), no cómputo Python. Validado
con hash SHA256 idéntico entre corridas sucesivas antes/después de cada
optimización (mismo resultado exacto, solo más rápido). No bloquea seguir
con las brechas 3-4 (Elmer), que no dependen de esta conversión a GDML.

**No confundir un ensamblaje mallado con éxito con un arreglo geométricamente
válido**: `generate_array.py` no comprueba solapamientos entre bobinas
distintas (solo dentro de cada bobina, igual que `generate_dh.py`) — ese
chequeo lo hace Geant4 al importar (`CheckOverlaps` en
`ICRP110PhantomConstruction.cc`), que ya itera automáticamente sobre todas
las piezas hijas del GDML, sin haber requerido ningún cambio de C++ para
soportar múltiples bobinas en vez de una.

## Entorno Python aislado

**Por qué un venv separado y no instalar esto en `geant4_env`:** el entorno
conda de Geant4 ya tiene versiones fijadas y sensibles (11.4.2, con su propio
historial de problemas de toolchain documentado en `AGENTS.md`/`README.md`
raíz). Mezclar ahí las dependencias de mallado (Gmsh, NumPy, y lo que
requiera Elmer más adelante) arriesga romper esa instalación por conflictos
de versión, sin ningún beneficio a cambio: `field/` y Geant4 no comparten
imports de Python en tiempo de ejecución, solo intercambian archivos
(GDML, mapas de campo) por disco. Aislarlos en un venv propio, con versión
de Python fijada aparte (3.13.5), evita ese riesgo por completo.

Desde la raíz del repositorio, con Python 3.13 (validado con **3.13.5**):

```bash
python3 field/bootstrap.py
source field/.venv/bin/activate
python -m pip check
```

También se puede usar siempre `field/.venv/bin/python` sin activar el entorno.
El bootstrap crea `field/.venv`, instala `requirements.txt` y comprueba imports.
Las versiones fijadas son **Gmsh 4.15.2** y **NumPy 2.3.3**. No modifica el
entorno conda de Geant4. `.python-version` registra el parche validado para
herramientas como pyenv; no descarga Python automáticamente. El bootstrap
acepta Python 3.13.x, pero para repetir exactamente el entorno usado aquí
instalar 3.13.5. No ejecutar el bootstrap con el Python de conda si es de
otra versión.

El entorno local y `field/generated/` están excluidos de Git. Se versionan
scripts, dependencias, geometría fuente, materiales, tests y documentación.
El equipo recrea su entorno; no copia ni versiona el directorio virtual.

**Alcance de reproducibilidad:** aislar Python y fijar versiones evita cambios
accidentales de paquetes, pero no garantiza resultados idénticos entre sistemas.
Gmsh usa bibliotecas nativas, incluida su geometría OpenCASCADE, y en Linux
puede requerir GLU (`libGLU.so.1`, paquete del sistema). El wheel de Gmsh trae
su biblioteca propia; estas dependencias del sistema no las instala `venv`.
Los manifiestos registran plataforma, Python y Gmsh; conservarlos junto con
los resultados y fijar sistema/contenedor si se necesita identidad entre máquinas.
**Elmer no forma parte de este venv.** `scripts/install.sh --with-elmer`
(desde la raíz del repo) lo compila desde fuente en `~/.local/elmerfem`
(configurable con `ELMER_PREFIX`) — no hay paquete Elmer en conda-forge, y
el PPA oficial solo cubre versiones específicas de Ubuntu/Debian, no
"cualquier distro" como el resto de este instalador. Es un paso opcional
(15-30+ min de compilación) porque Elmer todavía no está integrado al flujo
del proyecto — ver `GEOM14_STATUS.md`, brecha 3, para el siguiente paso
(acoplar el ejemplo oficial `mgdyn_steady_coils` a la curva de corriente que
ya genera `generate_array.py`). Su versión, solver y parámetros de
producción se fijarán al implementar esa solución FEM.

## Ejemplo reproducible

Desde la raíz, sin necesidad de activar el venv:

```bash
field/.venv/bin/python field/generate_mesh.py \
  field/examples/conversion_demo.geo field/generated/conversion_demo.msh
field/.venv/bin/python field/mesh_to_gdml.py \
  field/generated/conversion_demo.msh field/examples/materials.json \
  field/generated/conversion_demo.gdml
field/.venv/bin/python -m unittest discover -s field/tests -v
```

Salidas regenerables:

- `conversion_demo.msh`: malla Gmsh 4.1 ASCII con tetraedros de primer orden.
- `conversion_demo.mesh-manifest.json`: hashes de fuentes/generador/malla,
  versiones y opciones de mallado.
- `conversion_demo.gdml`: superficies trianguladas cerradas por volumen material.
- `conversion_demo.manifest.json`: hashes de malla, materiales, conversor y GDML;
  volumen y masa por componente, cantidad de triángulos y versiones.

`generate_mesh.py` fija un hilo, semilla 1, orden 1, algoritmo 2D=6 y 3D=1,
y desactiva la lectura de configuración personal de Gmsh. La geometría `.geo`
controla los tamaños de malla; el ejemplo usa 0.04–0.08 m y refinamiento por
curvatura. Son parámetros de prueba, no resolución final del devanado.

Para un `.geo` que importe STEP, otros `.geo` o parámetros externos, registrar
**cada archivo dependiente** con `--dependency ruta` (repetible). El script
no descubre recursivamente dependencias; registrarlas es responsabilidad del
generador del diseño. Versionar las fuentes y conservar los manifiestos.

## Contrato de conversión

1. Entrada `.msh` con tetraedros lineales de cuatro nodos (tipo Gmsh 4).
   No se aceptan prismas, hexaedros ni elementos de orden superior. Para ellos
   hay que generar una malla de conversión compatible, no borrar nodos a mano.
2. Cada entidad de volumen debe pertenecer a **un solo Physical Volume con
   nombre**, y cada grupo debe figurar en el JSON de materiales. Un grupo
   puede contener varias entidades del mismo material.
3. Marcar explícitamente con `null` los grupos que se excluyen, por ejemplo
   el dominio de vacío del FEM. No hay un material por defecto silencioso.
4. Declarar `length_unit` como `m` o `mm`. Todas las coordenadas finales están
   en metros y en el sistema global de Geant4, compartido con el mapa magnético.
5. Definir cada material con densidad en g/cm³ y **fracciones másicas**, que
   deben sumar uno. Cada elemento requiere Z y masa atómica en g/mol.
   Los valores del ejemplo son Cu/Al elementales, no composiciones REBCO/CORC.

El conversor extrae las caras exteriores de los tetraedros por entidad,
elimina caras internas y orienta las normales hacia fuera. Conserva huecos
si están resueltos por la malla. Comprueba tetraedros degenerados/duplicados,
caras no manifold, cierre de aristas y coherencia entre volumen superficial
y tetraédrico. Esas comprobaciones no sustituyen una validación geométrica
CAD: intersecciones entre entidades se revisan también en Geant4.

Cada componente se exporta como un `G4TessellatedSolid` con su material.
**No se exporta un tetraedro por volumen Geant4**: solo su superficie exterior,
lo que reduce el coste de navegación. Capas de materiales distintos necesitan
entidades distintas; una capa que no existe en la entrada no reaparece al convertir.

Las superficies son una aproximación facetada del CAD. El torus del ejemplo
produce ~332.392 kg frente a ~346.652 kg para el torus analítico con esos
parámetros: el ejemplo grueso sirve para probar la interfaz, no para aceptar
un error de masa del diseño final. Refinar y estudiar convergencia geométrica
antes de usar bobinas reales. El soporte rectangular reproduce 64.776 kg.

## Importar en ActiveShield_Sim

Se requiere Geant4 compilado con GDML; CMake ahora solicita ese componente
explícitamente. La instalación conda existente lo incluye.

```bash
# Con geant4_env activado, desde la raíz:
cmake -S geant4/ActiveShield_Sim -B geant4/ActiveShield_Sim/build \
  -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
cmake --build geant4/ActiveShield_Sim/build -j2
cd geant4/ActiveShield_Sim/build
./ICRP110phantoms ../../../field/examples/import_demo.mac
```

Para una macro propia, antes de `/run/initialize`:

```text
/spacecraft/coilGeometry /ruta/absoluta/conversion.gdml
```

Puede combinarse con `/spacecraft/fieldMap` y `/spacecraft/fieldScale`.
Omitir `coilGeometry` conserva el modelo sin componentes importados.
Importar materiales no activa campo; importar campo no genera materiales.

El GDML contiene un mundo de transporte `coil_transport_world` para poder
leerlo autónomamente. El código **coloca sus piezas directamente bajo
`MagnetEnvelope`**, conservando sus transformaciones; no coloca ese mundo de
vacío encima del hábitat. Se admiten componentes planos sin hijos, teselados,
según el contrato del conversor; no cualquier ensamblaje GDML arbitrario.

La carga comprueba límites de cada pieza, cobertura por el mapa si existe y
solapamientos con casco/cabina/otras piezas, con 10000 puntos por comprobación.
Un fallo detiene la inicialización. El chequeo de solapamientos es muestreado,
no una prueba matemática de ausencia de intersecciones diminutas. Si una pieza
no cabe, aumentar `worldHalfSize` o corregir su posición/dimensiones; no se
recorta para ocultar el problema. Si hay mapa, debe cubrir también las piezas.
Se imprimen material, densidad y masa por componente para contrastar el manifiesto.

## Validación y próximos pasos

Verificado en Linux x86_64, Python 3.13.5, Gmsh 4.15.2, NumPy 2.3.3 y Geant4 11.4.2:

- Nueve pruebas Python: orientación, caras compartidas, degeneración/duplicación,
  unidades m/mm, exclusión explícita, materiales inválidos, masas y determinismo.
- Repetir la generación del ejemplo produjo una malla con SHA-256 idéntico
  en este entorno. Repetir la conversión también produjo GDML idéntico.
- Compilación de ambos ejecutables Geant4 y CTest del campo aprobados.
- Importación real de dos piezas con materiales y masas coincidentes, sin
  solapamientos detectados; un geantino cruza el anillo de cobre y vuelve
  al vacío. Es una prueba de navegación, no de dosis.

Siguiente trabajo: definir el devanado y materiales reales, generar entidades
separadas por material, validar resolución geométrica, y preparar la corriente
y el dominio FEM de Elmer. La malla del FEM, el teselado radiológico y la grilla
del mapa magnético son discretizaciones distintas; no confundir sus tamaños.

Referencias de las interfaces:
[Gmsh: API y grupos físicos](https://gmsh.info/doc/texinfo/gmsh.html),
[Geant4: importación GDML](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/Detector/Geometry/geomXML.html),
[Geant4: sólidos teselados](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/Detector/Geometry/geomSolids.html).
