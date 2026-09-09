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

**`mesh_size_m`/`mesh_min_size_m` deben escalar con `conductor_radius_m`,
pero encontrar el valor correcto no fue inmediato (confirmado 2026-09-08,
ver `_provenance` del JSON) — dos fallos distintos, no uno:**
- Copiar el `0.006` (6 mm) de `dh_pilot.json` sin escalar, con el radio de
  conductor 10× más delgado de la cinta HTS (1,22 mm equivalente), dejó la
  malla más grande que el propio conductor: el paso 2 (mallado) se quedó
  colgado más de 5 minutos sin terminar.
- Escalar a `conductor_radius_m/2` (0,61 mm) evitó ese colgado, pero produjo
  un error distinto de Gmsh (`Identical points in triangulation`) — la malla
  quedó demasiado fina *relativa al tamaño global de la bobina* (radio 1 m),
  no al conductor: 0,06% del radio de bobina, frente a 1,2% en el piloto
  original que sí funciona.
- Con `mesh_size_m = conductor_radius_m` (1,22 mm, sin dividir entre 2) el
  mallado del arreglo de 3 bobinas (barrel de 934 m de longitud de
  conductor + 2 endcaps) **tampoco terminó** — se dejó correr casi 5
  minutos sin señal de progreso ni error, mismo patrón que el primer
  intento colgado, y se mató manualmente. **El mismo valor sí funciona**
  para el arreglo de 2 bobinas simples (3 vueltas cada una) del test
  automatizado `field/tests/test_array.py` — la variable que cambia no es
  solo `conductor_radius_m`, sino también cuántas vueltas/longitud total
  tiene la curva a mallar.
- **Estado real al 2026-09-08: no hay un `mesh_size_m` confirmado que
  funcione para el arreglo completo de Geom14 (60 vueltas en el barrel).**
  `generate_array.py` (CAD) y `audit_array.py` (consistencia numérica) sí
  están validados con esta geometría real — el mallado a `.msh`/GDML del
  arreglo de producción sigue pendiente de resolver, probablemente
  necesite reducir `turns`/`field_segments` del barrel real, o investigar
  parámetros de Gmsh más allá de `mesh_size_m` (algoritmo de malla,
  tolerancias de OpenCASCADE). No tratar esto como bloqueante de las
  brechas 3-4 (Elmer, ver `GEOM14_STATUS.md`), que no dependen de esta
  malla de conversión a GDML.

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
**Elmer no forma parte de este venv ni se ha instalado/configurado en este cambio.**
Su versión, solver y parámetros se fijarán al implementar la solución FEM.

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
