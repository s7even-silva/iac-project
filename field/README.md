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

**Piloto Elmer disponible:** `mesh_exterior.py` añade aire exterior al conductor
swept sin volver a triangular el CAD helicoidal. `build_coilsolver.py` compila
un módulo local que corrige la selección de cortes de corriente en presencia
de aire. `examples/elmer_pilot.sif` requiere ese módulo y prescribe 100 A.
Secuencia, evidencia, fuentes y límites: [validación Elmer](ELMER_VALIDATION.md).
El piloto no equivale a una solución validada del arreglo completo Geom14.

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
requiere GLU (`libGLU.so.1`) y las librerías X11 libXrender, libXcursor, libXft
y libXinerama, paquetes del sistema. Una instalación mínima de Ubuntu (WSL) no
las trae, y entonces `import gmsh` falla con «libXrender.so.1: cannot open
shared object file». En Ubuntu: `sudo apt install libglu1-mesa libgl1
libxcursor1 libxft2 libxinerama1 libxrender1` (`scripts/install.sh` ya lo
hace). El wheel de Gmsh trae su biblioteca propia; estas dependencias del
sistema no las instala `venv`.
Los manifiestos registran plataforma, Python y Gmsh; conservarlos junto con
los resultados y fijar sistema/contenedor si se necesita identidad entre máquinas.
**Elmer no forma parte de este venv.** `scripts/install.sh --with-elmer`
(desde la raíz del repo) lo compila desde fuente en `~/.local/elmerfem`
(configurable con `ELMER_PREFIX`) — no hay paquete Elmer en conda-forge, y
el PPA oficial solo cubre versiones específicas de Ubuntu/Debian, no
"cualquier distro" como el resto de este instalador. Es un paso opcional
(15-30+ min de compilación). Elmer se compila con el toolchain de conda-forge
de `geant4_env`, que no puede enlazar el BLAS/LAPACK del sistema: los toma
del propio entorno (`libblas`/`liblapack` en `environment.yml`; el
instalador los agrega a entornos creados antes). Sin ellos, CMake falla con
"Could NOT find BLAS". Después se compila el módulo local con
`python3 field/build_coilsolver.py`; el instalador no lo ejecuta automáticamente.
Ver [flujo FEM del piloto](ELMER_VALIDATION.md). Los parámetros y la validación
del arreglo de producción siguen pendientes.

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

## Preselección del radio de la esfera fuente (P1, paso 1)

`preselect_source_radius.py` evalúa el campo Biot-Savart del arreglo de forma
analítica, sin dominio finito. Para cada radio candidato traza hacia atrás
protones de varias rigideces desde la esfera fuente (ley coseno) y mide la
fracción de direcciones que vuelven a cruzar la esfera o quedan atrapadas:
esa fracción es el error de la fuente isótropa, por el teorema de Liouville.
También reporta la cola ∫B⊥·dl. Las trayectorias de corriente salen de
`generate_ellipse_array.py` sobre `production/crewhat_corc_array_config.json`;
`--check-map production/crewhat_niac_max.map` verifica que reproducen el
mapa versionado.

```bash
.venv/bin/python generate_ellipse_array.py production/crewhat_corc_array_config.json /tmp/crewhat_arr
.venv/bin/python preselect_source_radius.py /tmp/crewhat_arr/array_current_paths.json studies/salida.json \
    --radii 6.94 11 12 14 16 20 --rigidities-gv 0.15 0.25 0.36 0.71 1.5 \
    --n-tail 1000 --n-track 1000 --processes 6 --check-map production/crewhat_niac_max.map
```

Resultado del 2026-10-01 (K=1): `studies/p1_preseleccion_radio_2026-10-01.json`.
Con la disposición de NIAC (2026-10-31, radios de 14 a 32 m):
`studies/p1_preseleccion_radio_niac_2026-10-31.json`. La lectura de los dos
está en `docs/bitacora/plan_piloto.md` (P1).

## Disposición de NIAC (v2, P1 paso 0)

`examples/crewhat_niac_array.json` es el arreglo de la v2 (D9 en
`docs/bitacora/plan_piloto.md`): la misma bobina elíptica (semiejes 4 y 2 m)
en el mismo anillo de 8 m que el arreglo K=1, con dos cambios:

- **Sentido de corriente:** θ_k = 90° − φ_k (`theta_deg_pattern`), que deja
  el hábitat casi sin campo, como pide NIAC.
- **Bobinado rectangular** de 0.67 m radial × 0.32 m axial, con densidad
  efectiva de 3.755 g/cm³ para que cada bobina pese 15.6 t.

Los dos son supuestos propios declarados: los autores de NIAC no
respondieron (2026-10-31). La sección rectangular se declara con
`winding_pack_radial_m` (en el plano de la bobina) y `winding_pack_axial_m`
(a lo largo de su normal); sin esas claves se mantiene la sección cuadrada
`winding_pack_side_m` de la v1.

```bash
# Desde field/
.venv/bin/python generate_ellipse_array.py examples/crewhat_niac_array.json generated/crewhat_niac_array
.venv/bin/python generate_mesh.py generated/crewhat_niac_array/halbach_array.geo \
  generated/crewhat_niac_array/halbach_array.msh \
  --dependency generated/crewhat_niac_array/halbach_array.brep --dependency examples/crewhat_niac_array.json
.venv/bin/python mesh_to_gdml.py generated/crewhat_niac_array/halbach_array.msh \
  generated/crewhat_niac_array/materials.json generated/crewhat_niac_array/halbach_array.gdml
# Desde geant4/ActiveShield_Sim/build: importación, masas y solapamientos
./ICRP110phantoms ../../../field/examples/import_crewhat_niac_array.mac
```

Verificado el 2026-10-31 (unos 2 minutos en la laptop):

- 8 bobinas de 4.1541 m³ de malla (4.1544 m³ de CAD) y 15 599 kg cada una
  en Geant4;
- sin solapamientos con el casco, la cabina ni entre bobinas;
- material hasta 10.34 m del eje en x e y, y ±4.34 m en z;
- |B| Biot-Savart: 0 en el eje, 0.007–0.019 T a 2 m del eje y
  0.33–0.43 T junto al casco (4.5 m).

El GDML y sus manifiestos están en `production/crewhat_niac_array.*`.

**Elmer:** `examples/crewhat_niac_array.sif` es el `.sif` de este arreglo
(`Coil Normal = −(cos θ_k, sin θ_k, 0)`, la misma regla de signo del
piloto K=1). `mesh_exterior.py --padding X Y Z` acepta un margen por eje:
el arreglo mide ±4.34 m en z frente a ±10.34 m en x e y, y con un margen
único, empujar las caras z hasta ±20 m llevaría x e y a ±26 m.

**Cola del campo:** `studies/cola_campo_niac_k1_2026-10-31.py` compara la
cola Biot-Savart de NIAC y de K=1 fuera de la esfera fuente, para elegir
los radios que hay que trazar en el paso 1 de P1.

## Biot-Savart volumétrico (mapa de la v2, 2026-10-31)

**Por qué.** En todo el dominio μr = 1, que es el mismo supuesto del `.sif`
de Elmer. Con corrientes dadas y sin materiales magnéticos, el campo es
exactamente la integral de Biot-Savart de la densidad de corriente.

El error de los mapas Biot-Savart de la v1 venía de poner toda la corriente
de cada bobina en un solo filamento con núcleo regularizado, cuando el
bobinado mide 0.67 × 0.32 m. Lejos, eso apenas importa; cerca del bobinado,
sí.

`compute_field_volumetric.py` reparte la corriente de cada bobina en
n_radial × n_axial filamentos paralelos con la misma corriente (vueltas en
serie dan densidad uniforme), ubicados como el rectángulo del CAD. Cada
segmento usa la fórmula exacta del tramo recto, salvo dentro de un núcleo
del área del filamento, donde usa el perfil de un alambre uniforme. Así, en
el interior del bobinado (conductor sólido) el campo queda finito.

No hay caja ni frontera: el mapa puede ser tan grande como pida la esfera
fuente.

```bash
# Desde field/. Mapa (el tiempo es solo de esta generación; Geant4 lee el
# .map igual que antes, con la misma interpolación trilineal). Las
# trayectorias de corriente están versionadas, así que no hace falta Gmsh:
.venv/bin/python compute_field_volumetric.py production/crewhat_niac_array_current_paths.json \
  generated/mapa_bs_niac/niac_bs_30m_0.25.map --half-size 30 --spacing 0.25 --filaments 6 3 \
  --check-points 1000
# Repartido entre 4 PCs: cada una calcula su cuarta parte de los planos z...
.venv/bin/python compute_field_volumetric.py production/crewhat_niac_array_current_paths.json \
  parte1.npz --half-size 30 --spacing 0.25 --filaments 6 3 --part 1 4   # 2, 3 y 4 en las otras
# ...y una sola PC junta las partes (en cualquier orden) en el .map:
.venv/bin/python compute_field_volumetric.py production/crewhat_niac_array_current_paths.json \
  generated/mapa_bs_niac/niac_bs_30m_0.25.map --merge parte*.npz --check-points 1000
# Autoconvergencia y, en el laboratorio, comparación con Elmer:
.venv/bin/python validate_volumetric_field.py generated/crewhat_niac_array/array_current_paths.json \
  salida.json --filaments 3 2 6 3 12 6 24 12 [--vtu elmer_grueso.vtu elmer_fino.vtu]
```

**Error numérico medido (2026-10-31), 6 × 3 filamentos y 256 segmentos
por bobina, frente a 24 × 12** (`validate_volumetric_field.py`):

| Zona | Error máximo |
|---|---|
| Junto a la bobina 0 (5 cm–2 m del bobinado) | 0.32% |
| Hábitat | 0.08% |
| Líneas radiales hasta 18 m | 0.08% |

- Pasar de 256 a 512 segmentos cambia ≤0.16% junto a la bobina y ≤0.03%
  en el hábitat.
- Un solo filamento por bobina se equivoca hasta 37% junto a la bobina y
  hasta 16% en el hábitat (relativo al campo local).
- **Test analítico** (`tests/test_field_volumetric.py`): una bobina
  circular gruesa en su eje coincide con la fórmula cerrada en 2·10⁻⁵. El
  test detecta si se invierten los lados radial y axial (0.45%) o si se
  usa un solo filamento (0.15%).

**Tiempo (medido el 2026-10-31).** Se gasta solo al generar el mapa: Geant4
lo lee al inicializar e interpola igual que cualquier `.map`. Cada nodo suma
8 bobinas × 18 filamentos × 256 segmentos = 36 864 segmentos.
- **Núcleo compilado (`bs_kernel.c`).** Se compila solo con gcc y OpenMP la
  primera vez en cada máquina, queda en `generated/` y reparte los nodos
  entre hilos. En la laptop, con 8 hilos, hace 6.2·10⁸ pares segmento-nodo
  por segundo y un cuarto del mapa de ±30 m con paso de 0.25 m tarda
  5 min. Coincide con NumPy en 6·10⁻¹⁴.
- **NumPy, la versión de respaldo** si no hay gcc (o con `BS_KERNEL=numpy`).
  Está limitada por la memoria y casi no mejora con más procesos: una PC
  del laboratorio con 20 procesos hacía ~1.7·10⁷ pares por segundo en
  total, unas 3 h por cuarto de mapa.

Un mapa de **±30 m con paso de 0.25 m** (14 M nodos, ~630 MB) deja margen
para esferas fuente de hasta 30 m. Con el núcleo compilado son unos 20 min
en la laptop, y menos en una PC del laboratorio, así que alcanza con una
sola PC. Necesita `--max-points` de al menos 14 M (el valor por defecto es
20 M). El script muestra el avance por plano z, con el tiempo
que falta. En Geant4 se carga una vez por corrida: ~1 GB de RAM al leerlo
y del orden de un minuto de inicialización.

**Interpolación del mapa** (`--check-points`: trilineal como Geant4, frente
a evaluación directa, 1000 puntos por zona). Mapa de ±20 m con paso de
0.5 m (`generated/mapa_bs_niac/`):

| Zona | Mediana | p95 |
|---|---|---|
| Hábitat | 1.3% | 4.7% |
| Junto a las bobinas | 0.4% | 4.9% |
| Fuera de 12 m | 0.04% | 0.14% |

Los porcentajes son del campo local, contando solo los puntos con
|B| ≥ 10 mT. Con 0.25 m el error baja unas 4 veces y el mapa sigue siendo
barato, así que **se propone un paso de 0.25 m**; P1 lo confirma con la
dosis.

**Materiales del bobinado.** Solo importan sus propiedades magnéticas
(para el transporte, el material sigue en el GDML).
- Cobre y plata son diamagnéticos (|χ| ~ 10⁻⁵).
- El Hastelloy C-276 del sustrato es paramagnético de Curie entre 4 y
  300 K (C = 0.091 K; Lu, Choi y Zhou, *J. Appl. Phys.* 103, 064908,
  2008). A los 40 K de diseño de CREW HaT, χ ≈ 2·10⁻³.
- En el bobinado homogeneizado, el Hastelloy ocupa ~19% del volumen, así
  que χ_eff ≈ 4·10⁻⁴: cambia el campo en menos de 0.05%.
- El mismo trabajo ve agregados ferromagnéticos bajo ~10 K y un vidrio de
  espín bajo 3 K: no aplica a 40 K.
- Las corrientes de apantallamiento del REBCO superconductor no las modela
  ni este método ni el `.sif` de Elmer. Queda como supuesto declarado.

**Corriente en Elmer.** El CoilSolver de Elmer resuelve un problema de
conducción, y con `Normalize Coil Current = False` (el `.sif` K=1) reparte
la corriente como en un conductor macizo, cargada hacia el interior de cada
curva. Un bobinado de vueltas en serie tiene densidad uniforme
(«stranded»), que es lo que modela Biot-Savart volumétrico.
`examples/crewhat_niac_array.sif` usa `Normalize Coil Current = True`
(«Normalizing current density (as for stranded coil)» en el log).

**Validación con Elmer en el laboratorio (P1, paso 2): una sola bobina.**
Con μr = 1 el problema es lineal: el campo del arreglo es exactamente la
suma del campo de cada bobina, en Elmer y en Biot-Savart. Por eso alcanza
con validar una bobina (las 8 son iguales salvo rotación).

Validar el arreglo completo en Elmer no sirve para el hábitat. El ensayo
grueso del arreglo (abajo, «Elmer en el laboratorio») muestra que ahí el
campo es un resto pequeño de cancelaciones. Un error de Elmer del 10% en
cada bobina se vuelve ~0.1 T en el hábitat, donde el campo real es de
pocos mT a ~0.2 T.

Con una sola bobina el dominio es chico, así que en 32 GB cabe una malla
fina, con aire de ~0.10 m. Procedimiento:
1. 2–3 corridas por PC, con malla y caja crecientes y la corriente de
   bobina de vueltas (`Normalize Coil Current = True`).
2. Comparar con Biot-Savart volumétrico de esa misma bobina en las zonas
   de `validate_volumetric_field.py`: junto a la bobina (4 estaciones × 4
   direcciones × 6 distancias, de 5 cm a 2 m) y líneas radiales.

Criterio, fijado antes:
- la diferencia tiene que achicarse al refinar Elmer;
- en la corrida más fina, tiene que quedar dentro del cambio entre las dos
  corridas más finas (el propio error de Elmer).

El arreglo completo en Elmer queda solo como chequeo de orientación y
signos, que ya pasó (dirección igual en el casco).

**Cómo correrlo.** `elmer_una_bobina.sh` hace todo el nivel en una PC:
- malla del conductor de la bobina 0 sola (las otras siete se borran del
  CAD antes de mallar: ~2 s en vez de ~2 min), con lado de la mitad del
  aire y como mucho 0.15 m;
- módulo local de Elmer;
- aire alrededor de la bobina 0 sola (`mesh_exterior.py --groups
  crewhat_coil_0`), con `examples/crewhat_niac_single_coil.sif`;
- solve y comparación con Biot-Savart.

```bash
bash field/elmer_una_bobina.sh MARGEN_M AIRE_M          # en cada PC, un nivel
.venv/bin/python validate_volumetric_field.py --tendencia a.json b.json c.json   # al final, de grueso a fino
```

Niveles propuestos para 4 PCs. La memoria está estimada con los 3.1 KB
por tetraedro medidos:

| PC | Margen (m) | Aire (m) | Tetraedros de aire | RAM | Tiempo estimado |
|---|---|---|---|---|---|
| A | 4 | 0.20 | ~0.9 M | ~3 GB | ~10 min |
| B | 6 | 0.20 | ~2.2 M | ~7 GB | ~20 min |
| C | 6 | 0.15 | ~5.2 M | ~16 GB | ~1 h |
| D | 8 | 0.20 | ~4.3 M | ~13 GB | ~45 min |

El tiempo está extrapolado de lo medido en la laptop: ElmerSolver tarda 45 s
con 270 mil tetraedros, y se supuso que las iteraciones crecen con el tamaño
lineal. La parte de Biot-Savart de la comparación usa el núcleo compilado y
tarda segundos. Lo que domina es Elmer, que corre en un proceso; OpenMP lo
acelera solo ~12%.

A → B → D cambia solo la caja; B → C, solo la malla.

**Ensayo en la laptop (2026-10-31), error relativo de Elmer frente a
Biot-Savart (mediana / p95):**

| Nivel | Junto a la bobina | Líneas radiales |
|---|---|---|
| Margen 2 m, aire 0.4 m | 22% / 83% | 82% / 115% |
| Margen 4 m, aire 0.3 m (269 mil tetraedros) | 15% / 32% | 29% / 68% |

- La dirección coincide (coseno ≥ 0.98).
- Elmer se acerca a Biot-Savart al refinar, y el cambio entre esos dos
  niveles (15% y 36% de mediana) es del tamaño de la distancia que le
  falta: todavía no convergió.
- Cerca del bobinado, la malla gruesa lo deja 10–30% por debajo. Junto a
  las caras de una caja chica, la frontera `AV=0` encierra el flujo y lo
  deja por encima.

## Elmer en el laboratorio (32 GB por PC)

Estrategia general en el `README.md` raíz («Cómputo en el laboratorio de
la facultad»). Desde el 2026-10-31, Elmer es la validación independiente del
mapa de Biot-Savart volumétrico (sección anterior), no el mapa de
producción. Aspectos de Elmer:

- **Por qué crece la malla.** A tamaño de aire fijo, la cantidad de
  tetraedros es proporcional al volumen de la caja. El solve de producción
  de la v1 (caja de ±11.8 × ±13.8 × ±7.8 m, aire de 0.30 m) tenía 1.56 M
  tetraedros y llegó a 7.3 GB. Una caja de ±20 m tiene 6 veces ese volumen;
  una de ±25 m, 12 veces.
- **Memoria.** Los solves anteriores usaron entre 3 y 5 KB por tetraedro
  (`CREWHAT_STATUS.md` y `docs/bitacora/activeshield_sim_historia.md`); el
  ensayo con NIAC, 3.1 KB. Con ~26 GB útiles dentro de WSL2 caben unos
  5–8 M tetraedros: con aire uniforme de 0.30 m, una caja de hasta
  ±16–19 m. Los candidatos de P1 con NIAC (14–18 m) piden un mapa de
  ±19 m con la frontera más afuera: una caja de ±22 m son unos 13 M de
  tetraedros y ~40 GB.
- **Límite de iteraciones.** `Max Iterations` es un tope, no un costo: un
  solve que converge se detiene al llegar a la tolerancia (1e-8). El tope
  solo decide cuánto corre un solve que no converge antes de abortar
  (`Abort Not Converged`). Sin precondicionador, las iteraciones crecen con
  el tamaño lineal de la malla, y cada iteración cuesta en proporción a las
  incógnitas. Con el tope de 1000 del piloto K=1, un dominio grande podía
  abortar después de horas de cálculo; el `.sif` de NIAC sube el de
  MGDynamics a 10 000. `Residual Output = 10` imprime el residuo cada 10
  iteraciones, y un residuo estancado se detiene a mano. Medido el
  2026-10-31: 87 iteraciones con 0.59 M tetraedros. Si crecen con el tamaño
  lineal, una malla 10 veces mayor pediría unas 200: el tope de 1000 ya
  alcanzaba, y 10 000 es solo un margen.
- **Ensayo grueso con NIAC (2026-10-31, laptop).** Margen de 2 m, aire de
  0.40 m: 0.53 M tetraedros de aire y 0.06 M de conductor.
  - Recursos: 72 s y 0.76 GB para mallar; `ElmerSolver` en 15–25 min con
    1.7–1.8 GB de pico (3.1 KB por tetraedro), con la laptop ocupada.
  - **Orientación correcta:** en los 7 puntos de
    `examples/crewhat_niac_array_validation_probes.json`, la dirección de
    B junto al casco coincide con Biot-Savart (coseno de 0.999 a 1.000).
  - **Magnitudes no**, comparadas con Biot-Savart volumétrico (24 × 12):
    - en la grilla del hábitat, Elmer se equivoca en ~0.1 T (mediana de
      92 mT). En (−0.5, −0.5, 0) m da 16 mT en otra dirección, cuando el
      campo real es de 4 mT;
    - junto a la bobina, el error tiene una mediana de 18%.

    Es el error de malla y de una frontera a 2 m de las bobinas,
    amplificado por las cancelaciones de NIAC.
  - **Conductor macizo frente a bobina de vueltas** (`Normalize Coil
    Current` False o True, misma malla): en el hábitat cambian 0.5 mT de
    mediana (p95 de 1.5%); junto a la bobina, hasta 17%. El modelo de
    corriente importa cerca del conductor; en el hábitat, el error de
    malla de Elmer es ~100 veces mayor.
  - 87 iteraciones de MGDynamics como conductor macizo y 72 como bobina de
    vueltas.
- **MPI.** Elmer está compilado sin MPI (`scripts/install.sh`): un solve
  usa un solo proceso. MPI dentro de una PC acelera, pero no reduce la
  memoria total, y obliga a leer la salida particionada. Entre PCs no se
  usa, porque no forman un clúster.

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
