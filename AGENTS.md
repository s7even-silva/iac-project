# AGENTS.md

Este archivo documenta el proyecto para quien colabore en él (compañeros de equipo) y para futuras sesiones de asistentes de programación. Complementa a `README.md` (que cubre entorno y compilación) explicando el **por qué** de las decisiones y el estado actual de la metodología.

## Qué es este proyecto

Simulación GEANT4 (curso IAC 2026) de dosis de radiación espacial sobre un astronauta, usando eventos de rayos cósmicos galácticos (GCR) y de partículas solares (SEP). Ver `README.md` para el setup del entorno (conda, GEANT4 11.4.2) y compilación.

## Bitácora histórica del piloto GCR_SEP_Sim (2026-09-05)

**Antes:** el estudio comparaba 4 escenarios fijos de **blindaje pasivo** (capas de aluminio + polietileno alrededor del astronauta) combinados on/off con un campo magnético placeholder, sin variar su intensidad.

**En ese piloto:** se estudia el **blindaje activo** (campo magnético). Este barrido sigue implementado para referencia; no es el esquema de producción de ActiveShield_Sim. Las variables son:

1. **Tipo de evento × fase solar** (4 combinaciones): GCR y SEP, cada uno en fase solar máxima y mínima.
2. **Intensidad del campo magnético**: de 7.0 a 10.0 T en pasos de 0.5 T (7 valores).
3. **Posición del astronauta** dentro de la nave: a lo largo de un eje, en 0, 0.7, 1.4, 2.1 y 2.8 m desde el centro.

Con esto se busca determinar qué intensidad de campo atenúa mejor la dosis, y cómo el riesgo radiológico varía según dónde esté ubicado el astronauta dentro de la nave, para los casos extremos de radiación (GCR/SEP máx/mín).

**Por qué:** cambio de enfoque del equipo — ya no interesa comparar blindaje pasivo, sino caracterizar la efectividad de un escudo magnético activo variable, que es más representativo de un sistema de protección activo a bordo.

**Qué se conserva:** el código del blindaje pasivo (capas Al/polietileno) **no se borró**, solo queda desactivado por defecto y fuera del barrido nuevo — se puede reactivar más adelante si el equipo lo necesita.

## Estado vigente de ActiveShield_Sim (2026-09-08)

La implementación parte del ejemplo oficial ICRP110; `GCR_SEP_Sim` sigue
como piloto de referencia. Instrucciones técnicas en
[README de ActiveShield_Sim](geant4/ActiveShield_Sim/README.md) y justificación,
fuentes y pendientes en
[decisiones del modelo](geant4/ActiveShield_Sim/docs/modelo_realista.md).

**Implementado:**
- **Elmer (2026-09-09), actualización que sustituye las limitaciones históricas
  del piloto descritas más abajo:** `field/mesh_exterior.py` genera aire global
  a partir de las superficies del conductor swept, conservando sus tetraedros
  y comprobando interfaz/volumen. `field/build_coilsolver.py` compila un módulo
  local desde fuente Elmer fijado por revisión y SHA256: restringe la selección
  y coloreado de cortes a elementos activos del conductor, excluyendo aire.
  `examples/elmer_pilot.sif` requiere `CoilSolverRestricted.so`, prescribe
  corriente total (100 A), `Single Coil Cut=True`, normalización puntual False
  y aborto si el sistema lineal no converge. El instalador no compila este
  módulo automáticamente. Comparación de tres vueltas: FEM/BS central de
  0,184 a 0,951; no certifica convergencia ni Geom14 completo.
  `compare_elmer.py` audita puntos exteriores al hilo, con distancia explícita
  y sensibilidad a regularización. Regenerar mallas de `mesh_swept_air.py`
  anteriores al fix de IDs globalmente únicos. Instrucciones/evidencia en
  [validación Elmer](field/ELMER_VALIDATION.md).

- Piloto `field/generate_dh.py`: Double Helix cerrado y paramétrico, CAD y
  recorrido de corriente común; cobre circular de ensayo, no cinta YBCO/Geom14.
  `compute_field.py` genera una referencia Biot–Savart regularizada, no FEM ni
  campo válido dentro del devanado. `prepare_domain_sweep.py` prepara 2A/4A/8A
  con costes y macros PreInit. Alcance y criterios en [field/DOMAINS.md](field/DOMAINS.md).
- `field/generate_array.py`, `compute_field_array.py`, `audit_array.py`:
  ensamblan varias bobinas DH (barrel + endcaps) en un solo GDML/mapa de
  campo por superposición, reutilizando `generate_dh.py`/`compute_field.py`
  sin modificarlos. Material del conductor HTS homogeneizado y trazable
  (`field/examples/hts_tape_materials.json`) en vez de cobre puro. Detalle,
  dimensiones tomadas de ARSSEM y qué es extrapolación propia en
  [field/GEOM14_STATUS.md](field/GEOM14_STATUS.md).
- `field/mesh_swept.py`: mallado directo de tetraedros estructurados a lo
  largo de la curva espinal (sin pasar por triangulación 2D de
  OpenCASCADE/Gmsh), único método que completa el mallado del arreglo real
  de Geom14 (60 vueltas) — `generate_mesh.py`/HXT nunca terminaba en esa
  geometría (se atasca en la etapa 2D, confirmado con timing por etapa).
  6,24M tetraedros del arreglo completo en 62,5s, ~2,6% de error de volumen.
  Detalle en [field/README.md](field/README.md) y
  [field/GEOM14_STATUS.md](field/GEOM14_STATUS.md).
- Sección transversal rectangular real de la cinta HTS (brecha 2,
  implementado 2026-09-09): `tape_width_m`/`tape_thickness_m` opcionales en
  el JSON de una bobina activan un rectángulo orientado radialmente en vez
  del disco circular equivalente, tanto en CAD (`generate_dh.py`/
  `generate_array.py`) como en el mallado swept de producción
  (`mesh_swept.py:ribbon_tetrahedra`) — retrocompatible, sin cambios para
  cualquier config sin esas claves. `conductor_radius_m` se sigue exigiendo
  siempre porque alimenta el núcleo regularizado de Biot-Savart, aparte de
  la forma CAD/malla. Validado con el toro analítico y con la espina real
  del barrel de producción (2,55M tetraedros, 0,004% de error de volumen).
  **No activado en `geom14_array_pilot.json`:** la cinta de 50mm no cabe en
  la separación radial actual del piloto (20mm) — redimensionarla es
  trabajo de la brecha 1 (coordinar los ~10 parámetros del devanado), no
  algo que se resuelve solo en el generador. Detalle completo en
  [field/GEOM14_STATUS.md](field/GEOM14_STATUS.md), brecha 2.
- **Fix (2026-09-09):** `scripts/install.sh --with-elmer` invocaba `cmake`
  para compilar Elmer sin activar `geant4_env` primero — `cmake` viene de
  `environment.yml` (conda-forge), no se instala aparte en el sistema, así
  que este paso podía fallar con "cmake: command not found" en una distro
  sin `cmake` de sistema (p. ej. con `--skip-system`). Corregido para
  activar/desactivar `geant4_env` alrededor de la compilación de Elmer,
  igual que ya hacía la verificación final del script para los otros dos
  proyectos Geant4.
- **Fix (2026-09-09):** `scripts/install.sh` instalaba Miniconda con
  `-b` (modo batch, necesario para correr sin interacción), que instala el
  binario pero **no** ejecuta `conda init` — deja `conda`/`conda activate`
  inutilizables en cualquier terminal nueva del usuario, incluso después
  de reiniciarla (confirmado: reportado tras probar el script en otra
  máquina). El resto del script no lo sufría porque hace su propio
  `source .../conda.sh` explícito, pero eso solo dura la ejecución del
  script, no queda para sesiones futuras del usuario. Corregido: el script
  ahora corre `conda init <bash|zsh>` (detectado por `$SHELL`) tras
  instalar, de forma idempotente (comprueba primero si el bloque de conda
  ya está en `.bashrc`/`.zshrc`, para no reportarlo de más en
  reinstalaciones ni en el caso de una Miniconda ya instalada antes de
  este fix). El usuario debe abrir una terminal nueva (o volver a abrir la
  actual) después de instalar para que `conda` quede disponible.
- **Fix (2026-09-09):** `conda env create` fallaba en una máquina nueva
  con "the following channels have not been accepted" — desde 2025,
  conda exige aceptar los Términos de Servicio de los canales `defaults`
  (`pkgs/main`, `pkgs/r`) antes de resolver **cualquier** entorno, incluso
  uno cuyo `environment.yml` solo lista `conda-forge`: la instalación base
  trae `defaults` en su configuración global de canales aparte de lo que
  pida el `.yml` del proyecto. Corregido: el script corre `conda tos
  accept` para esos dos canales antes de crear `geant4_env`/
  `py313_bootstrap` (con aviso, no error fatal, si la versión de conda
  instalada no trae el subcommand `tos`, relativamente nuevo).
- **Fix (2026-09-09):** compilar GCR_SEP_Sim/ActiveShield_Sim fallaba en
  una máquina nueva con `Could NOT find EXPAT`, y tras agregar `expat`,
  luego con `Could NOT find ZLIB` — mismo patrón, no un caso aislado.
  Causa raíz real: conda-forge publica **7 variantes de build distintas**
  de `geant4=11.4.2` (`noqt_*`, `qt_*`, y `py310`…`py314` con bindings de
  Python), y `environment.yml` no fijaba cuál — el solver de conda elige
  libremente según la máquina. Cada variante trae un juego distinto de
  dependencias transitivas: las variantes `py3xx` declaran `expat`/`zlib`/
  `freetype` (paquetes de desarrollo completos) directamente, mientras que
  `noqt_*`/`qt_*` solo declaran las libs de runtime (`libexpat`/`libzlib`)
  — sin los headers, `Geant4Config.cmake` (que llama `find_dependency` a
  `CLHEP`, `EXPAT`, `ZLIB`, `XercesC`, `Freetype`, `HDF5` de forma
  incondicional en esta build, y también `X11`/`Qt6`/`OpenGL` porque
  `vis_raytracer_x11`/`qt`/`vis_opengl_x11` están `ON`) falla en cascada,
  un paquete a la vez, según cuál falte primero. Confirmado leyendo
  directamente el `Geant4Config.cmake` instalado. Corregido: todas esas
  dependencias de desarrollo (`expat`, `zlib`, `clhep=2.4.7.2` — versión
  exacta que exige `find_dependency(CLHEP 2.4.7.2 EXACT CONFIG)` —,
  `xerces-c=3.3.0`, `freetype`, `hdf5`, `xorg-libx11`, `qt6-main`)
  agregadas explícitamente a `environment.yml`, en vez de depender de qué
  variante de `geant4` resuelva el solver o de agregar paquetes uno a uno
  cada vez que aparezca un error nuevo. Verificado con `conda create
  --dry-run` que resuelve sin conflictos.
- **Fix (2026-09-09):** `scripts/install.sh --with-elmer` se quedaba
  estancado (reportado: bastante tiempo sin avanzar, en otra máquina) en
  `Checking whether MPI_IN_PLACE is supported with .../mpif90` durante la
  compilación de Elmer. Ese chequeo (`cmake/Modules/
  testMPIcapabilities.cmake` del propio Elmer) no es un simple
  `try_compile` — es un `try_run` que compila **y ejecuta** un programa
  MPI real (`MPI_Init`/`MPI_Allreduce`/`MPI_Finalize`). Programas OpenMPI
  triviales pueden colgarse indefinidamente ahí en ciertas configuraciones
  de red de un solo nodo (problema conocido y documentado en issues
  oficiales de OpenMPI, no específico de este proyecto). Este proyecto
  nunca corre `ElmerSolver` distribuido — toda corrida hasta ahora fue de
  un solo proceso, con el propio log confirmando "Running one task
  without MPI parallelization" — así que `WITH_MPI` no aportaba ninguna
  capacidad que se use. Corregido: `-DWITH_MPI:BOOLEAN=FALSE` en la
  compilación de Elmer, eliminando el chequeo (y el riesgo de cuelgue) de
  raíz. `WITH_OpenMP` no se toca — es paralelismo de memoria compartida,
  no relacionado con el transporte de red de OpenMPI que causaba esto.
- **Fix (2026-09-09):** compilar Elmer (`--with-elmer`) fallaba en una
  máquina Ubuntu al enlazar `libelmersolver.so` con `cannot find
  /lib64/libm.so.6` / `libmvec.so.1` — error real de linker, no una
  advertencia. Causa raíz: `environment.yml` fijaba `gcc_linux-64`/
  `gxx_linux-64` (compiladores C/C++ de conda-forge) pero nunca
  `gfortran_linux-64` — Elmer es mayormente Fortran, así que sin un
  `gfortran` de conda en el `PATH`, CMake caía al `/usr/bin/f95` del
  sistema, mezclando ese compilador con el C/C++ de conda-forge en el
  mismo link final. Ambos toolchains asumen sysroots distintos: el de
  conda-forge trae uno propio con convención `/lib64` (estilo RHEL), pero
  Debian/Ubuntu guarda esas libs en `/usr/lib/x86_64-linux-gnu/` — de ahí
  el "no such file". Corregido: `gfortran_linux-64=15.2.0` agregado a
  `environment.yml` (misma versión que `gcc`/`gxx_linux-64`, para que los
  tres compiladores vengan de un único toolchain consistente). Verificado
  con `conda create --dry-run`, resuelve sin conflictos.

  **Ese fix por sí solo no bastó** (encontrado inmediatamente después,
  misma máquina, con `gfortran_linux-64` ya instalado y confirmado en
  versión 15.2.0): `--with-elmer` seguía fallando, ahora con "Could not
  determine the Fortran compiler version" / "GNU Fortran major version is
  too old, should be at least 7". Causa: como con `g++`/`gcc`
  (`GXX_BIN` ya lo resolvía con un fallback explícito, ver más abajo),
  los paquetes `*_linux-64` de conda-forge NO exponen binarios llamados
  simplemente `gcc`/`g++`/`gfortran` en el `PATH` — solo los nombres con
  prefijo largo (`x86_64-conda-linux-gnu-cc`/`-c++`/`-gfortran`). La
  llamada a `cmake` para Elmer nunca pasaba `-DCMAKE_Fortran_COMPILER` (ni
  `-DCMAKE_C_COMPILER`) explícito, así que CMake auto-detectaba y seguía
  cayendo al `/usr/bin/f95`/`gfortran` del sistema sin importar que el de
  conda ya estuviera instalado — el mismo problema de fondo del fix
  anterior, sin resolver del todo. Corregido: `GCC_BIN`/`GFORTRAN_BIN`
  (mismo patrón que el `GXX_BIN` ya existente: ruta larga de conda con
  fallback al nombre corto del sistema si no existe) pasados explícitamente
  como `-DCMAKE_C_COMPILER`/`-DCMAKE_Fortran_COMPILER` en la compilación
  de Elmer, junto al `-DCMAKE_CXX_COMPILER` que ya se pasaba.
- **Fix (2026-09-10):** `--with-elmer` volvía a fallar en otra máquina
  nueva (una VM), otra vez con "Could not determine the Fortran compiler
  version" / "GNU Fortran major version is too old" — con `gfortran` de
  conda ya resuelto correctamente por el fix anterior (`GFORTRAN_BIN`
  apuntaba bien, `--version` reportaba 15.2.0). Causa raíz distinta esta
  vez, confirmada reproduciendo a mano el `try_run` que usa el propio
  chequeo de versión de Elmer (`cmake/Modules/testGFortranVersion.cmake`
  compila y **ejecuta** un programa de prueba, no confía en
  `CMAKE_Fortran_COMPILER_VERSION`): cualquier binario enlazado con el
  compilador de conda-forge abortaba al ejecutarse con "CPU ISA level is
  lower than required", no con un error de compilación. El `Scrt1.o` del
  sysroot de conda-forge trae una nota ELF (`GNU_PROPERTY_X86_ISA_1_NEEDED`)
  que exige hasta `x86-64-v3`; esta VM (KVM/Oracle) expone `avx2`/`bmi2`
  en `/proc/cpuinfo` pero le faltan `fma`/`f16c`/`lzcnt`/`osxsave` —
  también requeridos por v3 — así que el dynamic linker del sistema
  (`ld.so`, que reporta él mismo "x86-64-v2 (supported, searched)")
  rechaza el binario en tiempo de ejecución. `try_run` no distingue
  "compilador viejo" de "el binario no puede ni arrancar aquí", de ahí el
  mensaje engañoso. Ni `-march=x86-64-v2` ni `-Wl,-z,x86-64-v2` en la
  compilación del usuario cambian la nota (viene del `Scrt1.o` precompilado
  del sysroot, no del objeto propio); el `Scrt1.o` del sistema, en cambio,
  solo exige baseline y el gfortran del sistema (misma versión 15.2.0)
  funciona sin problema. Corregido: antes de compilar Elmer, `install.sh`
  reproduce la misma prueba compile+run con el compilador de conda: si
  falla, cae automáticamente a `gcc`/`g++`/`gfortran` del sistema solo
  para Elmer (que no enlaza contra ningún paquete conda de Geant4/CLHEP,
  así que esto no reintroduce el problema de sysroots mezclados del primer
  fix de Elmer). El resto del proyecto (`GXX_BIN`/`GCC_BIN`/`GFORTRAN_BIN`
  para Geant4) sigue igual, sin tocar. Verificado en esa VM: Elmer compila,
  `ElmerSolver --version` corre, y el binario final exige solo
  `x86-64-baseline` (confirmado con `readelf -n`).
- **Fix (2026-09-10), corrige una afirmación sin verificar del fix
  anterior:** ese mismo día se descubrió que `GCR_SEP_Sim`/`ActiveShield_Sim`
  compilados por el paso de "verificación final" de `install.sh` (que usa
  `GXX_BIN`, el compilador largo de conda) **tampoco podían ejecutarse**
  en esa VM — mismo síntoma exacto que Elmer, "CPU ISA level is lower than
  required", confirmado con `readelf -n` (exige hasta x86-64-v3). El
  comentario del fix anterior afirmaba que "GXX_BIN/GCC_BIN/GFORTRAN_BIN
  deben seguir en conda para Geant4 mismo" — nunca se verificó
  empíricamente esa necesidad, solo se asumió por analogía con el problema
  real de Elmer. Repitiendo el mismo diagnóstico (compilar y **correr** el
  binario, no solo compilarlo) se confirmó que **no hay tal necesidad**:
  a diferencia de Elmer (que compila su propio C/C++/Fortran desde cero,
  donde sí importa un triplete de compiladores consistente), estos dos
  proyectos solo compilan un puñado de `.cc` propios que enlazan contra
  bibliotecas `.so` ya compiladas de Geant4/CLHEP — el enlazado dinámico
  no exige que el compilador cliente comparta sysroot con la librería.
  `g++` del sistema (el mismo que ya recomiendan, sin verificar hasta
  ahora, los comandos manuales de este archivo y de cada README) compila,
  enlaza y **ejecuta** sin problema. Corregido: los dos `cmake` de la
  verificación final de `install.sh` usan `g++` a secas en vez de
  `$GXX_BIN`. `GXX_BIN` en sí no se tocó — Elmer lo sigue usando para su
  propio build desde fuente, donde el diagnóstico original si aplica.
- Elmer FEM instalado (`scripts/install.sh --with-elmer`, brecha 3) y
  corriendo (`CoilSolver` + `WhitneyAVSolver` + `MagnetoDynamicsCalcFields`,
  `field/examples/elmer_pilot.sif`), con dos bugs reales de `.sif`
  corregidos (`Normalize Coil Current`, `Relative Permeability` — ver
  GEOM14_STATUS.md). `field/generate_elmer_domain.py` y
  `field/mesh_swept_air.py` (nuevo) generan el dominio aire+conductor por
  dos caminos distintos (CAD/OpenCASCADE vs. tetraedros estructurados sin
  Gmsh 2D); `field/elmer_to_map.py` (nuevo) remuestrea el resultado a la
  grilla que Geant4 lee. **Sin validar todavía contra Biot-Savart en la
  geometría real de la doble hélice** por ninguno de los dos caminos — ver
  GEOM14_STATUS.md brecha 3/4 para el detalle completo de por qué. No
  bloquea el proyecto: el piloto de Geant4 usa Biot-Savart
  (`compute_field.py`), ya validado y en uso.
- Exportación STEP (2026-09-09): `generate_dh.py`/`generate_array.py`
  escriben también `dh.step`/`array.step` (con `step_sha256` en el
  reporte) junto al `.brep` existente — mismo sólido ya validado, para
  importar en herramientas de terceros con mallador propio (p. ej. Ansys
  Maxwell, que no comparte el límite de triangulación 2D de
  OpenCASCADE/Gmsh en geometrías de muchas vueltas). Detalle de por qué
  esta vía y no exportar solo la trayectoria en GEOM14_STATUS.md brecha 3.
  **La versión gratuita Ansys Student no alcanza para nuestra geometría**:
  límite oficial de 64.000 elementos de malla 3D, superado ya por el
  piloto de una sola bobina (76.176 tetraedros con nuestro mallador) y
  muchísimo más por el arreglo de producción (6,24M) — ver GEOM14_STATUS.md
  brecha 3 para el detalle y la alternativa de licencia académica.
- Conversión `field/generate_mesh.py` → `.msh` → `field/mesh_to_gdml.py`
  → GDML con componentes y materiales separados. Requiere tetraedros de
  primer orden y grupos físicos con asignación explícita en JSON.
  `mesh_to_gdml.py` vectorizado con NumPy (2026-09-09): de 10+ minutos sin
  terminar a 3m16s en el arreglo real (6,24M tetraedros → GDML de 700MB),
  hash SHA256 idéntico al resultado sin optimizar.
- Importación `/spacecraft/coilGeometry` (PreInit): coloca piezas teseladas
  directamente en `MagnetEnvelope`, comprueba límites, cobertura del mapa
  y solapamientos. El ejemplo Cu/Al es una prueba de conversión, no el imán real.
- Entorno separado `field/.venv`, creado con `python3 field/bootstrap.py`;
  Python 3.13 (validado 3.13.5), Gmsh 4.15.2 y NumPy 2.3.3 fijados.
  No instalar esas dependencias en `geant4_env`. Entorno y `field/generated/`
  excluidos de Git; versionar fuentes, materiales y scripts. Manifiestos
  con hashes/versiones junto a salidas. Ver [guía](field/README.md).
- Exterior en vacío `G4_Galactic`; aire de cabina y tejidos ICRP110 conservados.
- Cilindro de dimensiones exteriores 5.6 × 10 m, casco `G4_Al` de **1.5 cm**
  (sustituye 5 cm), tapas planas. Referencia radiológica de Al, no casco de
  aleación Al 2219 ni diseño estructural validado.
- **Implementado 2026-09-10:** `shipRadius`/`shipHalfLength` (antes
  constantes C++ fijas, `2.8*m`/`5.*m`) ahora son comandos de mensajero
  (`/spacecraft/shipRadius <m>`, `/spacecraft/shipHalfLength <m>`, mismo
  patrón que `hullThickness`), con esos mismos valores como default para
  no alterar ninguna corrida de Geom14 ya hecha. Necesario para evaluar
  CREW HaT (ver más abajo): su radio de referencia (`R_sc=4.5 m`, NIAC
  Phase I, asumiendo el diámetro de SpaceX Starship) es mayor que el
  actual — antes exigía editar C++ y recompilar para comparar tamaños de
  nave; ahora es una línea de macro, reversible sin recompilar.
- `World → MagnetEnvelope → {ShipHull, ShipInterior → fantoma}`. Casco y
  cabina son hermanos; las futuras bobinas externas serán hijas de
  `MagnetEnvelope`, nunca del interior presurizado.
- Lector de mapas regulares con interpolación trilineal; campo global vía
  `ConstructSDandField`, independiente de las fronteras materiales. Sin
  mapa, campo apagado. `G4CachedMagneticField` no es lector/interpolador.
- Mundo mínimo de semilado 10 m, configurable y ampliado según límites del
  mapa más 1 m. **No es una extensión física validada**: fuera del mapa B=0;
  se exige comprobar convergencia de dominio, malla, interpolación y tracking.
- Haz de prueba monoenergético a -6 m, fuera del casco. Los 1000 eventos de
  las macros originales son historias de partículas, no 1000 corridas.

**Decisiones confirmadas por el equipo:**
- ~~Fantoma fijo, centrado en el eje a media longitud; no barrido de
  posición.~~ **Revertido 2026-09-10, por dos motivos independientes que
  llegaron el mismo día:** (1) el usuario pidió ver cómo varía la dosis
  equivalente en los órganos de mayor riesgo estocástico de cáncer según
  la posición del fantoma dentro de la nave — implementado como
  `/spacecraft/phantomPositionCm <cm>`, desplazamiento a lo largo del eje
  Z (el eje largo del cilindro); (2) el campo Halbach de CREW HaT ya
  validado resultó ser genuinamente no uniforme (0,42-0,72 T dentro del
  anillo, asimetría discreta de 8 pliegues) — implementado como
  `/spacecraft/phantomOffsetX|Y <m>`, desplazamiento en la sección
  transversal XY. Los dos comandos son independientes y se combinan sin
  conflicto (ejes distintos); ambos con default 0 (retrocompatibles, cero
  cambio de comportamiento sin macro nueva). `phantomOffsetX|Y` es solo
  infraestructura de posicionamiento — el barrido en sí (rango, N de
  puntos, integración con el pipeline de bins de dosimetría) sigue sin
  implementar; ver `field/CREWHAT_STATUS.md`. `phantomPositionCm` sí tiene
  un barrido completo, ver más abajo ("Dosis por órgano y equivalente").
- **Bins de energía + reponderación** para producción. **Implementado
  2026-09-11 para el análisis de riesgo estocástico** (ver la entrada de
  "Dosis por órgano y equivalente" más abajo): bordes/rango (>99,9% del
  flujo real por especie), especies (GCR_H, GCR_He, SEP_p) y N/bin
  decididos ahí, `scripts/energy_bins.py` y `/gun/fixedEnergyMeV`. Sigue
  pendiente para el **barrido de producción completo** (el que compara
  blindaje pasivo/activo con las 8 bobinas a distintas configuraciones,
  distinto del análisis de riesgo estocástico ya implementado): orquestador
  a esa escala mayor y estimación de incertidumbre por órgano.
- **Gmsh + Elmer + Python** para calcular y exportar el campo. No implementar
  un Halbach uniforme ficticio; no inventar dimensiones/corrientes de bobinas.
  Elmer se instala por `scripts/install.sh --with-elmer`; el venv cubre
  mallado y conversión, no las dependencias nativas. La validación FEM del
  arreglo completo sigue pendiente; el flujo del piloto está enlazado arriba.
- **GCR vía OLTARIS (Badhwar-O'Neill 2020)** y **SEP vía OLTARIS (Historical
  SPE)** — ambas fuentes cambiaron de SPENVIS a OLTARIS el 2026-09-08, al
  aprobarse el acceso a esa cuenta (ver "Cambio de fuente" en el checklist).
  GCR usa los periodos históricos de mínimo/máximo solar de BON2020; SEP usa
  eventos históricos puntuales, no el modelo probabilístico ESP-PSYCHIC:
  **máximo = Oct 1989** (peor caso estándar en 5-100 MeV), **mínimo = Feb
  1956, ajuste LaRC** (el más pequeño de los eventos catalogados en OLTARIS
  con fluencia >30 MeV comparable, ~1×10⁹ p/cm² frente a ~4-19×10⁹ de los
  demás — ver checklist para la comparación completa y sus fuentes). Elegir
  "sin evento" para SEP mínimo se descartó: da dosis ≈0 y anula la
  comparación de efectividad del campo para ese cuarto de la matriz de
  escenarios. Los exports físicos siguen siendo necesarios como pesos aunque
  las energías se simulen por bins. El scorer actual no calcula por sí solo
  dosis absoluta o equivalente.
- **Prioridad de exportación (2026-09-08): primero solo los casos de mayor
  dosis por especie** — GCR en mínimo solar (flujo GCR más alto) y SEP en
  Oct 1989 (evento máximo). GCR máximo solar y SEP mínimo (Feb 1956) quedan
  diferidos, no bloquean la primera corrida de producción; se completan
  después si hay tiempo. Ver checklist para el detalle de qué 3 archivos
  (no 6) se exportan primero.
- **Los 6 espectros reales completados (2026-09-10).** GCR máximo tuvo una
  limitación de fecha: BON2020 en OLTARIS no acepta fechas más allá de enero
  de 2023 (confirmado al intentar la ventana real del máximo del ciclo 25,
  ene 2024–jul 2025), así que se usó 14-15/01/2023 en su lugar — la mejor
  aproximación disponible en la herramienta, no el pico real (que según
  NOAA/SWPC fue más tarde). SEP mínimo (Feb 1956, ajuste LaRC) se exportó sin
  problemas. Con esto **ya no hace falta `--priority-only`**:
  `select_spectrum_source.py oltaris` (sin `--only`) y `run_sweep.py` (sin
  `--priority-only`) corren el barrido completo de 140 combinaciones —
  probado con un piloto de las 4 combinaciones modelo×fase, todas con dosis
  físicamente coherentes (GCR mayor en mínimo que en máximo, SEP mayor en
  Oct1989 que en Feb1956). Detalle completo en el checklist.
- Mantener material de devanados, soportes y crióstato en el modelo final:
  la contribución pasiva y los secundarios pueden aumentar o reducir dosis.
- **Dosis por órgano y equivalente, riesgo estocástico (2026-09-10/11).**
  `GCR_SEP_Sim` da dosis absoluta de cuerpo completo pero su fantoma es una
  esfera sin órganos; para dosis por órgano y equivalente (Sv) hace falta
  el fantoma ICRP110 real de `ActiveShield_Sim`. **Tres rondas de revisión**
  (dos de reducción de alcance, una de corrección de un error de diseño):
  - *Ronda 1 (2026-09-10):* dosis equivalente en los órganos de mayor
    riesgo estocástico de cáncer, en función de la posición del fantoma,
    con blindaje al máximo y el evento más peligroso de cada especie (GCR
    en mínimo solar, SEP en Oct 1989). Campo **sintético uniforme**
    (`field/generate_uniform_map.py`, evitaba el imán real de Bryam, aún
    no validado en ese momento) a 10 T, fantoma desplazado a lo largo del
    eje Z en 5 posiciones — 15 corridas.
  - *Ronda 2 (2026-09-11):* el arreglo real de 8 bobinas de CREW HaT ya
    estaba validado (ver más arriba) — se usa ese campo real en vez del
    placeholder sintético, a su **corriente de diseño máxima fija** (1×10⁷
    A por bobina, sin escalar), exportado a `.map` con
    `field/generate_ellipse_array.py` + `field/compute_field_ellipse_array.py`
    sobre `field/examples/crewhat_halbach_array_pilot.json`. Posición del
    fantoma de `phantomPositionCm` (eje Z) a **`phantomOffsetX`** (radial
    en XY, Y fijo en 0): el campo real de Bryam varía principalmente
    radial/azimutalmente respecto al anillo de bobinas. Nave a escala real
    de CREW HaT (`shipRadius=4.5m`, `shipHalfLength=5m`, este segundo valor
    supuesto propio del equipo).
  - *Ronda 3 (2026-09-11), corrige un error real, no una reducción de
    alcance:* `ICRP110PhantomPrimaryGeneratorAction` usaba `SpectrumSampler`
    para **muestreo continuo** del espectro (copiado de `GCR_SEP_Sim`) — el
    mismo método que esta sección ya tenía registrado, más abajo, como
    **"no portar como plan de producción"** para `ActiveShield_Sim` (la
    decisión de "bins de energía + reponderación" es anterior a esta
    tarea). Corregido: `/gun/fixedEnergyMeV <valor>` (nuevo) fuerza una
    energía monoenergética fija en todos los primarios de la corrida, en
    vez de muestrear — `SpectrumSampler` se conserva sin tocar y sigue
    siendo el default (sin este comando) para `primary.mac`/demos, donde
    no aplica la decisión de bins. `scripts/energy_bins.py` (nuevo) calcula
    8 bins log-espaciados por especie (decisión 2026-09-11, evaluado contra
    5/10 bins y distintos N/corrida por el costo en tiempo) dentro del
    rango que cubre >99,9% del flujo/fluencia real de cada espectro
    (calculado de los CSV reales, no el rango tabulado completo de OLTARIS
    que tiene colas irrelevantes) y el peso físico real de cada bin.
    `aggregate_organ_doses.py` combina cada `(especie,bin)` con su propio
    peso en vez de un peso único por especie. Esto **multiplica el conteo
    de corridas por 8** (de 15 a **120**: 3 especies × 8 bins × 5
    posiciones) — tensión reconocida con "menos combinaciones y menos
    tiempo"; se aceptó el costo para seguir la decisión ya tomada del
    equipo. División de trabajo: `--only-positions` (nuevo, mismo criterio
    que `--only-model` de `GCR_SEP_Sim`) reparte por posición completa —
    3 posiciones = 72 corridas (60%), 2 posiciones = 48 corridas (40%).
  **Ponderación radiobiológica (`w_R`, ICRP 103 Tabla A.3):** protón y pion
  cargado = 2, alfa = 20, por especie (no por bin de energía — esta
  ponderación simplificada de ICRP103 no depende de la energía). Limitación
  explícita: pondera por la partícula *primaria* de la corrida, no por
  partícula-en-cada-paso (un neutrón secundario hereda el `w_R` del
  primario, no el suyo propio) — resolverlo por paso requeriría un
  `SteppingAction` con filtro por tipo de partícula, fuera de alcance.
  **6 categorías de riesgo estocástico** (ICRP 103 Tabla A.1, los seis
  `w_T=0.12`): colon, pulmón, estómago, mama, médula ósea roja y "tejidos
  restantes" (remainder, un compuesto de otros 14 tejidos que ICRP103 trata
  como una sola categoría) — cada una agrupa varios `organ_id` de ICRP110
  en un solo valor ponderado por masa, no una fila por `organ_id` (versión
  anterior de este análisis). **Médula ósea roja, verificado contra
  `AM_organs.dat`/`AM_spongiosa.dat`/`OrganMasses.dat` reales
  (2026-09-11):** ICRP110 no la modela como `organ_id` propio — está
  repartida como fracción de la dosis de "spongiosa" (hueso esponjoso) en
  19 sitios esqueléticos, dada por `AM_spongiosa.dat` (fracciones
  RBM/YBM/hueso por **ID de tejido**, columna "Tissue number" de
  `AM_organs.dat`, no por `organ_id`) — masa total calculada (1,170 kg)
  coincide exactamente con el valor de referencia ICRP para el adulto
  masculino, validando la implementación. Fantoma masculino: la mama sí
  está segmentada en ICRP110 para ambos sexos, pero `w_T=0.12` es un valor
  promediado por sexo — la dosis en tejido mamario de un fantoma masculino
  es una referencia dosimétrica/geométrica, no equivalente al riesgo
  epidemiológico de cáncer de mama documentado en mujeres. Detalle de
  comandos y scripts en
  [README de ActiveShield_Sim](geant4/ActiveShield_Sim/README.md).

**Propuestas y pendientes (no decisiones finales):**
- El usuario indica un plan previo de 12 bobinas. Geom14 de ARSSEM es la
  recomendación inicial; vueltas, paso, corriente de operación y límites
  críticos del conductor siguen sin confirmar contra ARSSEM (ver
  `field/GEOM14_STATUS.md`, brechas 1 y 4). **Implementado 2026-09-08:**
  `field/generate_array.py` ensambla varias bobinas DH (reutilizando
  `generate_dh.py` sin modificarlo) en un solo GDML con material por bobina;
  `field/examples/geom14_array_pilot.json` es un primer arreglo de
  validación (1 barrel + 2 endcaps, no las 12 bobinas completas) con
  dimensiones de barrel/endcap tomadas de ARSSEM fig. 5.4 (Geom13, que
  comparte barrel con Geom14 según §4.3) — **se asume que Geom14 tiene
  endcaps por analogía con Geom12/13, el paper nunca lo confirma para
  Geom14 específicamente**. El conductor usa un material HTS homogeneizado
  trazable (`field/examples/hts_tape_materials.json`, sustrato Hastelloy +
  YBCO + Ag + Cu de una cinta 2G comercial tipo SCS4050), reemplazando el
  cobre puro del piloto de una sola bobina — este arreglo de validación
  sigue con sección circular (área equivalente a la cinta real), no la
  cinta rectangular real: el generador ya soporta la sección rectangular
  real (ver más arriba, brecha 2), pero activarla aquí exige antes
  redimensionar la separación radial del piloto (brecha 1, ver
  `field/GEOM14_STATUS.md`). El ensamblaje Geom14 completo (12 bobinas) y
  su campo físico validado (Elmer) **todavía no están implementados**.
- Comparación pasiva adicional reevaluada: A nave sola, B nave+material de
  bobinas sin campo, C con campo, D nave+capa pasiva, E híbrido opcional.
  **Confirmado factible sin código nuevo (2026-09-11)**: `addPassiveLayerCm`,
  `coilGeometry`/`fieldMap` vacíos y `fieldScale` ya cubren los 5 casos como
  combinaciones de macro — falta solo escribir las 5 macros de ejemplo, no
  una interfaz de escenarios nueva.
- **Física de producción decidida (2026-09-11): `Shielding`**, no
  `QGSP_BIC_HP` — mismo physics list que el piloto GCR_SEP_Sim, vía
  `G4PhysListFactory` en `ICRP110phantoms.cc`.
- La posible novedad del artículo requiere revisión bibliográfica; calcular B
  dentro o fuera de Geant4 no demuestra por sí mismo una contribución novedosa.
- **CREW HaT (2026-09-10): decidido desarrollar en paralelo a Geom14, no
  reemplazarlo.** Búsqueda de una configuración de bobina 100% reproducible
  que evite extrapolar los vacíos de ARSSEM; verificado leyendo el reporte
  NASA NIAC Phase I completo (D'Onghia, NTRS 20250002403) y la tesis de
  maestría 2024 (Ziyang Hang, MINDS@UW 1793/85233), no solo el abstract.
  CREW HaT es un **Halbach Torus de 8 bobinas elípticas** (no "racetrack" —
  corrección de nomenclatura, ese término aplica a SR2S, un diseño
  distinto) — fija más parámetros sin ambigüedad que Geom14: semieje mayor
  4 m, aspect ratio 2, radio Halbach 8 m, campo pico ~10 T, temperatura de
  diseño 40 K, corriente total del sistema 1×10⁷ A·vuelta (Tabla 3.1, p. 15
  del reporte NIAC).

  **Aclaración de metodología (2026-09-11): los "~10 T" son el dato de
  diseño del conductor, no el campo que recibe el fantoma.** Consistente
  con que la cinta HTS está calificada `Ic=240A **a 10T/40K**` (Tabla 2.7
  de la tesis, ver abajo) — es el campo que el propio devanado debe
  soportar en su punto de operación, no el campo dentro del hábitat. Un
  arreglo Halbach está optimizado para dar un campo **uniforme** dentro
  del anillo, no necesariamente fuerte — la magnitud se concentra cerca de
  las bobinas. A la corriente de diseño real (1×10⁷ A, sin escalar, la que
  usa `run_organ_sweep.py`), el campo calculado da **~0,4-1 T dentro de la
  nave** (donde importa para la dosis) y **~2,27 T** cerca del radio de
  las bobinas (r=8m) — el verdadero pico cerca del conductor (que podría
  acercarse a los 10 T) no es visible con este modelo: el núcleo de
  regularización de Biot-Savart está marcado como no válido justo ahí (ver
  brecha ya documentada más abajo). **Decisión del equipo:** la
  metodología cita los ~10 T como especificación de diseño del conductor
  (con su fuente), y usa el campo real simulado (~0,4-1 T) para el cálculo
  de dosis — no se escala `/spacecraft/fieldScale` para forzar 10 T dentro
  de la nave, porque eso ya no correspondería al diseño real de CREW HaT
  citado.

  **Conductor — decisión: construir ambas opciones y comparar** (no eran
  tan costosas de comparar como parecía inicialmente, ver más abajo):
  cinta YBCO 12 mm (Ic=240A a 10T/40K → ~41.667 vueltas, winding pack 1,43 m
  elíptico, Tabla 2.7 de la tesis) y cable CORC 8 mm (Ic≈3.800A →
  ~2.632 vueltas, winding pack 0,67 m elíptico, Tabla 2.8). Se empieza por
  la cinta 12 mm. (La cinta de 4 mm de la tesis, Ic=80A → ~125.000 vueltas,
  queda descartada por ahora: mismo conductor pero un orden de magnitud
  más vueltas para el mismo winding pack, sin ninguna ventaja aparente
  sobre la de 12 mm para este proyecto.)

  **Decisión de modelado clave**: a diferencia de la Double Helix de
  Geom14 (donde trazar cada vuelta es físicamente necesario para el
  mecanismo de autocancelación del campo solenoidal propio), una bobina
  elíptica de CREW HaT es N vueltas idénticas apiladas sin ese requisito
  — se modela como **un solo sólido barrido homogeneizado** (densidad de
  corriente equivalente J=I_total/área_winding_pack), no vuelta por vuelta.
  Sin esto, cualquiera de las dos opciones de conductor (41.667 o 2.632
  vueltas) sería inviable de mallar con el enfoque per-vuelta que usa
  `generate_dh.py`/`mesh_swept.py` para la Double Helix.

  **Nave**: el reporte NIAC asume R_sc=4,5 m (radio, diámetro de SpaceX
  Starship), sin fijar la longitud axial del hábitat ("permanece sin
  determinar", p. 9) — mayor que el radio actual del proyecto (2,8 m).
  **Decidido escalar la nave a 4,5 m** en vez de reescalar la bobina a
  nuestra nave, reversible sin recompilar: `shipRadius`/`shipHalfLength`
  (ver más arriba) dejaron de ser constantes C++ fijas para permitir
  volver a 2,8 m si se retoma Geom14/ARSSEM más adelante.

  **Lo que ningún documento da** (confirmado buscando explícitamente, no
  es que falte revisar más): longitud axial del hábitat, un factor de
  empaquetamiento/relleno escalar del winding pack (la tesis calcula el
  grosor capa por capa, Ec. 2.10-2.12 p. 35, no con un factor simple), y
  el patrón angular explícito de las 8 bobinas en el arreglo Halbach (solo
  describe cualitativamente bobinas "radiales" vs. "tangenciales", p. 44-45
  — el patrón angular de un Halbach dipolar de 8 elementos tendrá que
  aplicarse como fórmula estándar de ingeniería de imanes, no como dato de
  la fuente).

  **Implementado 2026-09-10:** `field/generate_ellipse.py`, una sola
  bobina elíptica cerrada con sección transversal cuadrada homogeneizada
  (representa el winding pack completo, no un conductor individual —
  ninguna vuelta se traza por separado, a diferencia de la Double Helix).
  Reutiliza `_conductor_profile()` de `generate_dh.py` sin modificarlo
  (mismo principio que `generate_array.py`). Genera ambas variantes de
  conductor con las cifras reales verificadas (winding pack de 1,43 m para
  cinta 12mm, 0,67 m para CORC) — volumen CAD validado contra la
  estimación analítica perímetro×área en <0,1% para ambas
  (`field/tests/test_ellipse.py`). **Mallado, GDML e importación en Geant4
  validados de punta a punta el mismo día**: a diferencia de la Double
  Helix, esta elipse **no necesita** el workaround de `mesh_swept.py` —
  el mallador Gmsh 2D/3D estándar (`generate_mesh.py`) completa sin
  atascarse (curvatura mucho más suave), con solo 0,016% de diferencia
  entre volumen de malla y CAD. Importado en `ActiveShield_Sim` vía
  `/spacecraft/coilGeometry` sin solapamientos, con masa y trayecto de
  sonda geantino coincidiendo exactamente con lo esperado. **Campo
  Biot-Savart también calculado y probado con una partícula cargada real
  el mismo día**: `compute_field.py` sin cambios; deflexión real medida
  (hasta -77,9 mm) en un protón de 9,9 GeV cruzando la región de campo en
  Geant4 — energía alta elegida a propósito porque `ActiveShield_Sim`, a
  diferencia de `GCR_SEP_Sim`, no tiene protección contra partículas
  atrapadas en campos fuertes. **Arreglo de las 8 bobinas implementado el
  mismo día** (`field/generate_ellipse_array.py`): patrón Halbach dipolar
  K=1 (momento magnético rotando al doble de la posición angular) — fórmula
  estándar de ingeniería de imanes aplicada como supuesto propio del
  equipo, confirmado por dos rondas de búsqueda que ni el reporte NIAC ni
  la tesis dan una tabla de ángulos ni un conteo de bobinas "radiales"
  vs. "tangenciales" (esa distinción del reporte es para el montaje
  mecánico, no la fase electromagnética). Las 8 bobinas importan en
  `ActiveShield_Sim` sin ningún solapamiento, ni entre sí ni con el casco.
  **Campo Biot-Savart superpuesto de las 8 bobinas calculado el mismo día**
  (`field/compute_field_ellipse_array.py`) — resultado físico central del
  ejercicio: el patrón dipolar de Halbach funciona como se espera, con
  campo razonablemente uniforme (0,42-0,72 T) dentro del radio de la nave
  escalada (4,5m) y cayendo a 0,09 T en el borde del dominio (14m), con
  simetría de 180° exacta. Sigue siendo Biot-Savart regularizado, no
  Elmer/FEM. **Material HTS real implementado el mismo día**
  (`field/examples/crewhat_hts_materials.json` — archivo separado de
  `hts_tape_materials.json` de Geom14, mismos tipos de capa pero espesores
  de la propia tesis de CREW HaT): compuesto homogeneizado para cinta
  12mm (Hastelloy+YBCO+Ag+Cu, 94,8µm) y para CORC (núcleo de Cu sólido
  3,2mm + región anular de cinta hasta 8mm, sin factor de relleno dado por
  la fuente — supuesto propio marcado explícitamente). Reemplaza el cobre
  placeholder en ambos generadores (retrocompatible), validado
  reimportando en Geant4 (`material=coil_mat_crewhat_tape_homogenized`/
  `_corc_homogenized` con las densidades correctas, sin solapamientos
  nuevos). **Primera corrida de Elmer FEM sobre esta geometría, el mismo
  día, con precauciones reales de memoria**: esta VM (VirtualBox en la
  laptop del usuario) ya había forzado apagados con el barrido de
  convergencia del piloto DH al agotar RAM+swap con mallas de 13-28M
  tetraedros — con la elipse (volumen mucho mayor que el conductor DH) se
  usó un límite duro de memoria vía cgroups (`systemd-run -p MemoryMax=6G
  -p MemorySwapMax=4G`) y parámetros deliberadamente gruesos para el
  primer intento. Resultado real, confirmado por la contabilidad de
  systemd: picos de 186MB (mallado) y 471,5MB (`ElmerSolver`, 16,9s) —
  muy por debajo del límite y lejísimos de los apagados anteriores.
  **Bug real encontrado**: `Coil Normal(3) = 0 0 1` (copiado del piloto
  DH) daba el campo con el signo exactamente invertido en las 6 sondas de
  validación frente a Biot-Savart — corregido a `0 0 -1`
  (`field/examples/crewhat_ellipse_pilot.sif`), bajando el error relativo
  de ~150-250% a 16%-54% (coherente con la malla deliberadamente gruesa
  de este primer intento). Cada una de las 8 bobinas del arreglo tiene
  orientación distinta — el signo correcto no se puede asumir igual para
  las 8 sin verificarlo por separado.

  **Barrido de convergencia parcial, mismo día**: refinar solo `air-size`
  apenas cambió el error (mismo patrón ya visto en el piloto DH); combinar
  `air-size` más fino con `padding` más grande sí lo redujo a la mitad
  (7,6% en el centro, 33,5% en el punto más lejano probado), con picos de
  memoria reales medidos vía contabilidad de systemd (186MB a 4,7GB según
  la configuración). **Detenido ahí por precaución**: el siguiente paso de
  refinamiento extrapola a ~15GB de pico, peligrosamente cerca del total
  de RAM+swap de esta VM — no intentado. Detalle completo, tabla del
  barrido y comandos reproducibles en `field/CREWHAT_STATUS.md`.

  **Convención de signo confirmada para una bobina rotada, el mismo día**:
  probado con una sola bobina aislada construida con la orientación real
  de la bobina k=1 de un arreglo de 8 (sin generar las otras 7, mucho más
  barato) — `Coil Normal = -normal_de_la_bobina` da el signo correcto
  también para una rotación genuina, no solo el caso sin rotar. Regla
  aplicable a las 8 sin necesitar validar cada una por separado.

  **Arreglo completo de 8 bobinas: intentado directamente, la estimación
  de memoria anterior era incorrecta.** La extrapolación de ~14,5GB se
  basaba en la razón de envolventes geométricas (~42x) entre una bobina y
  el arreglo — error real de método: el padding (2,0m) se suma fijo, no
  proporcional, así que la razón de volumen de dominio **ya mallado** es
  mucho menor (~9,9x, no 42x). Al intentarlo con el límite de cgroup como
  red de seguridad: mallado del aire en 8,9s con 1,3GB de pico;
  `ElmerSolver` con las 8 bobinas (8 `Component`, cada uno con el `Coil
  Normal` correcto de la fórmula ya confirmada) completó "ALL DONE" en
  148s con **3,4GB de pico** — muy por debajo de cualquier límite.
  Comparado contra la superposición de Biot-Savart de las 8 bobinas
  (`compare_elmer_array.py`, nuevo): **2,4%-15,4% de error** en 7 puntos
  de la región de protección, mejor que la bobina individual sola con la
  misma malla gruesa (dentro del anillo el campo está dominado por la
  contribución conjunta de las 8, un régimen más favorable). Esto también
  confirma indirectamente que las 8 señales de `Coil Normal` son
  correctas.

  **Refinamiento del arreglo completo, mismo día**: con memoria de sobra
  confirmada (3,4GB de 27GB), se intentó `padding=3,0/air-size=0,15`
  (lo que funcionó bien para la bobina individual) — esta vez sí se
  encontró un límite real: 10,26 millones de tetraedros de aire, con el
  **mallado solo ya en 11,9GB**, demasiado cerca del límite para
  arriesgar el solve. Un paso intermedio (`padding=2,5/air-size=0,20`,
  3,77M tetraedros) sí fue seguro: 12GB de pico confirmado por
  seguimiento directo del proceso durante los ~10 minutos que tardó, sin
  usar swap de forma significativa. Mejora real: **2,4%-15,4% → 2,3%-
  11,2%** — más modesta que en la bobina individual porque el resultado
  grueso ya estaba en un régimen favorable (dominado por la contribución
  conjunta de las 8 bobinas). Esta configuración es la más fina que se
  puede correr con margen de seguridad real en esta VM. Elmer **todavía
  no probado** para CORC en solitario — ver
  [`field/CREWHAT_STATUS.md`](field/CREWHAT_STATUS.md) para el detalle
  completo de brechas y las decisiones de modelado propias marcadas
  explícitamente (sección cuadrada sin segunda dimensión de la fuente,
  radio de regularización de Biot-Savart sin validar, margen de curvatura
  de la elipse). Cifras exactas con cita de página en
  [`field/ELMER_VALIDATION.md`](field/ELMER_VALIDATION.md) y comparación
  con Geom14 en [`field/GEOM14_STATUS.md`](field/GEOM14_STATUS.md).

  **Dos pendientes chicos resueltos el mismo día (2026-09-10):**
  - **Ubicación bobina-nave verificada a escala real**: se corrió el
    chequeo de solapamiento de `import_crewhat_halbach_array.mac` con
    `/spacecraft/shipRadius 4,5 m` explícito (antes solo probado con el
    valor por defecto de 2,8m) — las 8 bobinas siguen sin solaparse entre
    sí ni con el casco a la escala real decidida para CREW HaT (margen
    ~1,8m en el punto más cercano). El macro ya quedó actualizado con ese
    valor.
  - **Longitud axial del hábitat**: confirmado que ningún documento la
    da (NIAC Phase I la deja explícitamente indeterminada) — no es un
    dato pendiente de buscar más, ya se agotó la búsqueda. Se fija como
    supuesto propio explícito: `shipHalfLength=5m` (10m total), el mismo
    valor heredado de Geom14/ARSSEM, documentado como decisión consciente
    en vez de pendiente abierto.

  **Barrido de posición del fantoma: infraestructura agregada (2026-09-10),
  revierte la decisión anterior de "sin barrido de posición"** — ver la
  entrada correspondiente en "Decisiones confirmadas por el equipo" más
  abajo. `ICRP110PhantomConstruction` gana `/spacecraft/phantomOffsetX|Y
  <m>` (mismo patrón `G4GenericMessenger` que `shipRadius`), por defecto
  0 (retrocompatible, sin cambiar ninguna corrida existente). Probado con
  `geant4/ActiveShield_Sim/tests/phantom_offset.mac` a la escala real de
  nave (4,5m) con un offset de 2m: sin solapamientos. Solo la
  infraestructura de posicionamiento — el barrido en sí (rango, N de
  puntos, integración con el pipeline de bins de dosimetría) sigue sin
  implementar.

  **Ablation de patrón angular (2026-09-10), roadmap de 8 fases
  completo**: comparación del patrón dipolar K=1 suave (actual) contra
  una lectura literal "radial/tangencial alternante" de NIAC. Fase 0-1:
  `uniformity_metric.py` (nuevo) fija el criterio de comparación —
  coeficiente de variación de `|B|` sobre una grilla de la región de
  protección; `generate_ellipse_array.py` generalizado con
  `theta_deg_pattern` opcional, retrocompatible, para generar patrones
  explícitos. Baseline K=1 real (8 bobinas, escala 4,5m): media 0,571T,
  CV 0,179, máximo 0,970T (más alto que el rango 0,42-0,72T reportado
  antes, porque esta grilla más completa sí muestrea Z distinto de cero).
  Fase 2-4: se generó el patrón alternante crudo y se comparó con la
  misma grilla — **~4,5x peor en uniformidad** (CV 0,799), con un punto de
  campo casi nulo dentro de la región de protección, e igual de libre de
  solapamientos a 4,5m. **Se decidió omitir la Fase 5 (Elmer)** para este
  candidato: el margen del resultado barato ya es concluyente, no amerita
  el costo de memoria de un FEM completo (Fase 6 no aplica en consecuencia).
  **Fase 7 (gratis, sin remallar)**: `field/phase_sensitivity.py` (nuevo)
  reutiliza el campo K=1 ya calculado para medir si la fase de instalación
  del arreglo importa relativa al barrido de posición del fantoma —
  resultado: irrelevante cerca del eje (CV 0,004 a 1m), relevante cerca
  del casco (CV 0,168, hasta 64% de diferencia entre el mejor y el peor
  ángulo, a 4,5m). El patrón K=1 de producción queda respaldado
  cuantitativamente, no solo por analogía con la teoría de imanes, y con
  una caracterización explícita de cuándo la fase de instalación
  importaría. Ninguna configuración de producción cambió. Detalle, tabla
  y comandos reproducibles en `field/CREWHAT_STATUS.md`.

### Segundo grupo de datos: dos implementaciones en paralelo, resueltas por merge (2026-09-11)

**Historia real (para que no se repita el trabajo doble):** el mismo día,
en paralelo y sin saberlo, se construyeron dos lanzadores distintos para
el segundo grupo de datos. Bryam (esta sesión) hizo un lanzador rápido
(`run_sweep.py`/`spectrum_to_gps.py`/`aggregate_organ_dose.py`) que
puenteaba los 3 CSV de OLTARIS a `G4GeneralParticleSource` vía
`/gps/ene/type Arb`+`/gps/hist/point`, sin tocar C++. Eddy, en paralelo,
hizo la implementación completa y correcta: portó `SpectrumSampler.hh/.cc`
de `GCR_SEP_Sim` a `ActiveShield_Sim` de verdad (`ICRP110PhantomPrimary
GeneratorAction` reescrito, comandos `/gun/species`/`/gun/phase`/
`/gun/fixedEnergyMeV` nuevos vía `ICRP110PhantomGeneratorMessenger`),
implementó el pipeline de bins de energía que el equipo tenía acordado
desde antes pero nunca hecho (`scripts/energy_bins.py`), y escribió el
lanzador real (`scripts/run_organ_sweep.py` + `scripts/
aggregate_organ_doses.py`, 120 corridas: 3 especies × 8 bins × 5
posiciones) — ver la entrada "Dosis por órgano y equivalente, riesgo
estocástico" más arriba para el detalle completo, con tres rondas de
diseño documentadas.

**Al hacer `git pull` de esos 8 commits, se eliminó el lanzador rápido de
Bryam** (`run_sweep.py`/`spectrum_to_gps.py`/`aggregate_organ_dose.py`,
y su sección de README correspondiente) por quedar estrictamente
superado: usaba GPS en vez del `SpectrumSampler` real, muestreo continuo
en vez de los bins ya acordados, y un wR/agrupación de órganos ad-hoc
que el trabajo de Eddy ya resuelve con más rigor (médula ósea roja
verificada contra `AM_spongiosa.dat` real, no un proxy de nombre de
texto). No se perdió nada de valor: la única pieza de ese trabajo que sí
sigue vigente es el cambio de physics list (ver abajo) y la corrección
de estado de CREW HaT, ambas conservadas aquí.

**Physics list, contradicción real detectada en el merge, resuelta:**
Bryam cambió `ICRP110phantoms.cc` de `QGSP_BIC_HP` a `Shielding` el mismo
día (`G4PhysListFactory`, mismo patrón que `GCR_SEP_Sim`) — un archivo
que el trabajo de Eddy no tocó, así que el merge lo conservó sin
conflicto, pero la documentación de Eddy todavía decía "sigue siendo
QGSP_BIC_HP" (escrita antes de conocer ese cambio paralelo). Corregido
en `geant4/ActiveShield_Sim/README.md`: `Shielding` es la physics list
vigente. Recompilado y verificado con `ctest` tras el merge (2 tests,
ambos pasan).

**Corrección de estado, CREW HaT no está "completamente validado" para
dosimetría de producción** (aclarando la bitácora previa): geometría,
mallado, GDML, importación en Geant4, comparación Biot-Savart-vs-Elmer y
el ablation del patrón angular sí están hechos y son sólidos. El error
relativo Elmer-vs-Biot-Savart medido tiene dos cifras, no confundir
cuál es cuál: **7,6%-33,5% es la bobina individual sola** (malla
`padding=3,0/air-size=0,15`, validación de método) — **2,3%-11,2% es el
arreglo completo de 8 bobinas** (`padding=2,5/air-size=0,20`), que es la
geometría real de producción y da mejor error, no peor (el régimen
dentro del anillo está dominado por la contribución conjunta de las 8
bobinas, más favorable que una bobina aislada). Ninguna de las dos es
"la mejor cifra Elmer del proyecto" sin más: son dos geometrías
distintas con presupuestos de memoria distintos, y `CREWHAT_STATUS.md`
solo pone la advertencia explícita ("no una cifra de producción
aceptada — el equipo debe fijar su propio presupuesto de error antes de
usar este mapa para dosimetría") sobre la primera. Lo que sigue sin
resolver para ambas geometrías: la sección transversal cuadrada del
winding pack (supuesto propio, ninguna fuente la da) y el radio de
regularización de Biot-Savart (10% arbitrario, "sin ninguna validación
de que esto dé un campo razonable cerca de la bobina"). Es la geometría
más avanzada del proyecto, no la geometría ya certificada para publicar
dosis.

**Decisión de equipo (2026-09-11): estos dos supuestos se aceptan tal
cual para la corrida de producción, sin más trabajo de validación.** No
hay dato externo con el que contrastar ninguno de los dos (ninguna
fuente da la segunda dimensión del winding pack ni un radio de
regularización de referencia), así que seguir intentando validarlos no
es un problema de tiempo de cómputo sino de falta de dato — no
convergería con más esfuerzo. Se documentan como limitación conocida del
modelo, no como pendiente abierto. El CORC (segunda opción de conductor)
sigue sin pasar por Elmer en absoluto (ni bobina individual ni arreglo)
— la producción usa la cinta de 12mm, así que esto no bloquea, pero si
se quiere reportar CORC como alternativa validada, falta ese paso.

**Matriz pasiva/activa A-E (ver `docs/modelo_realista.md`) confirmada
como fácil de realizar sin código nuevo:** `ICRP110PhantomConstruction`
ya expone `/spacecraft/addPassiveLayerCm <material> <espesor_cm>`
(capas pasivas concéntricas), `/spacecraft/coilGeometry` y
`/spacecraft/fieldMap` (vacíos = sin bobinas/sin campo) y `fieldScale`
— los 5 casos de la matriz son combinaciones de macro de comandos ya
existentes, no requieren tocar C++. Pendiente: solo escribir las 5
macros de ejemplo (no hecho todavía en este cambio).

### Error de campo vs. error de dosis en Elmer, y extensión a escala real (2026-09-11)

**Pregunta del equipo: ¿vale la pena refinar más la malla de Elmer del
arreglo de 8 bobinas, más allá de r2 (padding=2,5/air-size=0,20,
2,3%-11,2% de error de campo)?** Se generaron por primera vez los `.map`
de las dos soluciones Elmer ya existentes (r1: padding=2,0/air-size=0,30;
r2) — nunca se habían exportado a formato Geant4, solo comparado en 7
puntos sueltos — y se corrió la misma configuración exacta (semilla,
energía, eventos) con cada una:

| Campo | Error de campo (7 puntos) | Dosis total |
|---|---|---|
| r1 | 2,4%-15,4% | 5,342e-08 Gy |
| r2 | 2,3%-11,2% | 5,426e-08 Gy |

**r1 vs r2 difieren solo ~1,6% en dosis**, muy por debajo de la
diferencia de error de campo — refinar más allá de r2 tiene rendimientos
decrecientes ya agotados, no amerita el riesgo de memoria del siguiente
paso. Resultado de convergencia citable en el paper.

**Hallazgo más importante, no buscado inicialmente:** comparando esas
mismas dos corridas contra Biot-Savart (el campo que usa la producción
real) en la misma configuración: **Biot-Savart da ~48% más dosis que
Elmer** — 30 veces la diferencia r1-vs-r2. Repetido después a escala
real de nave (shipRadius=4,5m/shipHalfLength=5m, ver abajo): **Biot-Savart
sigue dando ~36% más dosis que Elmer**. El margen que realmente importa
para el paper no es la resolución de malla, es si Biot-Savart (más
barato, el que corre `run_organ_sweep.py` hoy) es dosimétricamente
equivalente a Elmer FEM — con este dato, no está claro que lo sea.
**Advertencia explícita:** ambas comparaciones son de una sola semilla,
una sola especie/energía/posición, sin repeticiones — un indicio fuerte,
no una validación estadística lista para publicar tal cual.

**Extender el dominio de Elmer a escala real de nave: intentado
directamente, resultó barato.** El dominio de r1/r2 (padding≤2,5) solo
cubre hasta Z=±6,3-6,8m, menor que el radio de la esfera fuente a escala
real (`shipRadius=4,5m/shipHalfLength=5m` → ~6,94m, ver
`GetSourceSphereRadius()`). Se regeneró el dominio con `mesh_exterior.py
--padding 3,5 --air-size 0,30` (mismo `air-size` grueso que r1, solo más
padding) sobre el mismo conductor ya mallado: **18,5s, 3,6GB de pico,
1,56M tetraedros** (menos que r2) — mucho más barato de lo que la
extrapolación ingenua de volumen sugería. El solve completo (`ElmerGrid`
+ `ElmerSolver`, IDs de cuerpo verificados contra `case.sif` antes de
correr) tomó **~5,3 minutos, 7,3GB de pico** — cómodo dentro de esta
máquina (15GB+11GB swap). **El campo a esta escala es más preciso, no
menos**, que r1/r2 en los mismos 7 puntos (1,7%-6,3% de error vs.
Biot-Savart) — el límite artificial de un dominio más chico distorsiona
más el campo cerca de la región de interés que una malla más grande con
la misma resolución gruesa.

**Bug real encontrado y corregido al exportar el `.map` a esta escala:**
`field/elmer_to_map.py`'s `resample()` (ya usado por `compare_elmer_array.py`
solo en 7 puntos sueltos, nunca en una grilla completa) dejaba ~1% de los
nodos de una grilla regular sin valor. Diagnóstico verificado por fuerza
bruta contra todos los tetraedros (no un supuesto): esos nodos caen a
~3,4-3,8x el radio de regularización de Biot-Savart del centro de una
bobina — es decir, genuinamente dentro del volumen físico del conductor,
donde Elmer nunca calculó "aire" porque ahí hay material sólido. No es un
bug de bucketing espacial. Corregido en `field/elmer_array_to_map.py`
(script nuevo, ver abajo) rellenando esos nodos con el valor del nodo de
aire válido más cercano — justificado porque son ~1% de la grilla, todos
a un radio donde ninguna trayectoria de dosimetría del interior de la
nave pasaría (el sólido del conductor se importa aparte vía
`/spacecraft/coilGeometry` y detiene partículas ahí antes de que ese
valor de campo puntual importe). Falla explícitamente si el porcentaje de
nodos sin resolver excede 5% (mesh genuinamente roto, no solo bordes de
conductor). Verificado que no cambia nada para r1/r2 (mismo SHA256 antes
y después del fix, ya que ahí no había nodos problemáticos).

**Nuevo:** `field/elmer_array_to_map.py` — exporta una solución Elmer del
arreglo (ascii VTU) a `.map`, sin pasar por el `domain.json` que exige el
CLI de `elmer_to_map.py` (pensado para el piloto DH de una sola bobina,
no para el método `discrete_conductor_global_air` de `mesh_exterior.py`
que usan las corridas del arreglo) — reutiliza `load_vtu()`/`resample()`
de ese módulo directamente, igual que ya hacía `compare_elmer_array.py`
para puntos sueltos.

### Repeticiones, blindaje sólido y campo Elmer en `run_organ_sweep.py` (2026-09-11)

**Repeticiones, implementado:** `--repeats N` (default 1, retrocompatible)
— multiplica las 120 combinaciones por N (ej. `--repeats 5` = 600
corridas), mismo patrón de semillas que `GCR_SEP_Sim/scripts/run_sweep.py`
(`BASE_SEED + 1000*rep + 2*index`). Resume indexa por `(index,
repeticion)`, no solo `index`. **Orden repetición-mayor por defecto (no
un flag):** el bucle corre todas las combinaciones de la repetición 0
antes que cualquiera de la repetición 1 — con `--repeats 5` esto da un
primer resultado completo y usable (120 combinaciones, 1 repetición)
mucho antes de terminar las 600, en vez de tener las 120 a medio
terminar durante casi toda la corrida. El resume por `(index,
repeticion)` no depende del orden de iteración, así que esto no cambia
qué combinaciones quedan pendientes si se corta a la mitad.

`aggregate_organ_doses.py` corregido para sumar `edep_J` y `n_eventos` de
todas las repeticiones de una misma combinación antes de calcular
`R = edep/(masa*N)` (pool de eventos de Monte Carlo independientes —
estadísticamente más correcto que promediar `R` directamente) — antes de
este fix, agregar filas de repeticiones habría hecho que cada combinación
silenciosamente usara solo los datos de la ÚLTIMA repetición leída,
descartando las demás sin error. Verificado con una corrida real de 3
repeticiones: la suma de `n_eventos` da exactamente 3×N (no 3×142×N, el
bug que más importaba evitar, ya que cada repetición escribe ~142 filas
de órgano que comparten el mismo N).

**Media/std/SEM/IC95%/CV entre repeticiones, implementado (placeholder):**
nuevo `resultados_riesgo_estocastico_repeticiones.csv` — a diferencia de
la vista pooled (que suma eventos entre repeticiones y da mejor punto
estimado pero ninguna barra de error), aquí cada repetición se combina
por separado para obtener una lista de `D_equivalente` independientes,
resumida con el mismo criterio (t de Student) que
`GCR_SEP_Sim/scripts/aggregate_results.py` (tabla `T_TABLE_95` copiada,
no importada — proyectos separados, sin módulo de estadística
compartido todavía). Con `--repeats 1` (lo único corrido hasta ahora)
imprime una advertencia explícita y deja std/CV en blanco, sin romperse
— listo para cuando se corra con `--repeats ≥2` de verdad.

**Reparto de equipo, `aggregate_organ_doses.py --results` ahora acepta
varios archivos (con patrones glob):** cada persona corre su propio
`--only-positions` en su máquina, y cualquiera de los dos junta ambos CSV
en una sola pasada (`--results personaA.csv personaB.csv`) sin tener que
concatenarlos a mano evitando duplicar el encabezado. Verificado
simulando el split real (2 posiciones en un archivo, 2 distintas en
otro): el CSV agregado tiene exactamente las filas esperadas, sin
duplicar ni perder ninguna — funciona porque `--only-positions` ya
garantiza posiciones disjuntas entre personas (semillas deterministas
por índice global, asignado antes de filtrar).

**`/spacecraft/coilGeometry`, implementado (antes no se usaba en
absoluto):** decisión de equipo ya registrada más arriba ("Mantener
material de devanados, soportes y crióstato en el modelo final"),
respaldada por los papers de blindaje activo citados en
`docs/modelo_realista.md` (SR2S, Ambroglini et al.) que modelan la masa
de la bobina como parte del blindaje, no solo su campo — pero el
lanzador nunca la había usado: corría solo con el efecto del campo sobre
trayectorias, sin la masa de las bobinas ni sus secundarios. Corregido:
`--coil-geometry` (default: `field/generated/crewhat_halbach_array/
halbach_array.gdml`, verificado geométricamente idéntico —salvo ruido de
punto flotante ~1e-15— al usado para generar el mapa de campo de
producción) más `/spacecraft/worldHalfSize 14 m`. `--no-coil-geometry`
disponible para comparar sin ellas. Probado sin solapamientos.
**Costo real medido: ~10-20s → ~21-24s por corrida en los bins de
energía más baja** — las bobinas ahora generan secundarios de verdad.

**Campo de producción cambiado de Biot-Savart a Elmer FEM a escala real
(decisión de equipo, 2026-09-11):** `--field-map` ahora tiene default
(`build/crewhat_elmer_fullscale.map`, ya no requerido explícitamente) —
antes de este cambio, ninguna combinación mencionaba qué campo específico
era "el de producción" fuera de la CLI. Motivo: ver la entrada "Error de
campo vs. error de dosis en Elmer" más abajo — Biot-Savart sobreestima
dosis 36-48% frente a Elmer en la misma configuración porque trata cada
bobina como un filamento con núcleo de 6,7cm, mucho menor que el winding
pack real (~1,4m), y la región de la nave no está lo bastante lejos del
arreglo (radio Halbach 8m) para que esa aproximación sea buena ahí. Elmer
resuelve la distribución de corriente real sobre la sección del
conductor. `build/crewhat_niac_max.map` (Biot-Savart) se conserva para
comparación, ya no es el default. **Sin verificar todavía en vivo la
combinación exacta Elmer+coilGeometry dentro de `run_organ_sweep.py`**
(cada pieza se probó por separado — Elmer a mano, coilGeometry con
Biot-Savart — pero no las tres juntas en el lanzador real): el directorio
de build estaba ocupado corriendo el piloto de 8 bins (ver abajo) cuando
se hizo este cambio; verificar con `--limit 1` antes de un barrido real.

**Piloto de 8 bins (1 por bin, GCR_H, posición 0), con la configuración
final (14 hilos, bobinas incluidas, 10000 eventos reales) — hallazgo
crítico para el presupuesto de tiempo:**

| Bin | Energía (MeV/amu) | Tiempo real |
|---|---|---|
| 0 | 17,8 | 21,6s |
| 1 | 56,2 | 21,8s |
| 2 | 177,8 | 34,1s |
| 3 | 562,3 | 72,6s |
| 4 | 1778,3 | 275,3s |
| 5 | 5623,4 | 730,4s |
| 6-7 | 17780-56230 | (completar aquí cuando termine la corrida) |

El costo **no es uniforme entre bins** — cada bin de energía tarda
aproximadamente 2,3-2,7x el anterior, un factor >30x ya confirmado entre
el bin más barato y el bin5, con los dos bins más caros (los de mayor
energía, más producción de secundarios) todavía sin medir. Cualquier
presupuesto de tiempo para el barrido de 120 (o 600 con repeticiones)
corridas debe usar esta curva real, no un promedio plano — el bin7 solo
podría, extrapolando el mismo factor, tardar del orden de una hora por
corrida.

**Matriz pasiva/activa A-E: NO duplica el conteo, lo multiplica por hasta
5x, y no es necesaria completa para el resultado central.** Si el único
argumento del paper es "el blindaje magnético activo reduce la dosis",
alcanza con 2 casos (A: nave sola sin nada, C: con campo — la producción
actual), no los 5 — eso sí sería una duplicación (2x), manejable. Correr
los 5 casos completos a resolución plena (120 combinaciones × repeticiones,
cada uno) multiplicaría el costo por 5, que combinado con la curva de
costo real de arriba, probablemente no es viable en el tiempo disponible.
Recomendación: A y C a resolución plena; B/D/E (si hay tiempo) a
resolución reducida (solo los 2-3 bins que concentran ~80% del peso
físico de cada especie, ver la nota de adecuación de bins más abajo, y
solo la posición central) en vez del barrido completo — suficiente para
una comparación indicativa sin pagar el costo completo tres veces más.

## Estructura de `geant4/GCR_SEP_Sim/`

Proyecto GEANT4 en C++ (CMake), ejecutable `gcrsim`. Piezas clave:

- `DetectorConstruction` / `DetectorMessenger`: geometría `World → ShipHull (aluminio, 0.3 cm) → ShipInterior (vacío) → Phantom`. El campo magnético, cuando está activo, está **confinado al interior de la nave** (no a todo el mundo, como antes). Comandos nuevos: `/detector/astronautX <cm>` (posición del astronauta), `/detector/hullThicknessCm <cm>` (espesor del casco). Comandos de blindaje legado (`/detector/shield`, `/detector/alThickness`, `/detector/polyThickness`) siguen existiendo pero no se usan en el barrido nuevo.
- `PrimaryGeneratorAction` / `GeneratorMessenger`: comando nuevo `/gun/phase max|min` para elegir la fase solar, además de `/gun/model GCR|SEP` ya existente.
- `data/`: 6 archivos de espectro de energía, uno por combinación modelo×fase (`gcr_proton_solarmax.csv`, `gcr_proton_solarmin.csv`, `gcr_alpha_solarmax.csv`, `gcr_alpha_solarmin.csv`, `sep_proton_solarmax.csv`, `sep_proton_solarmin.csv`). **Estos 6 archivos ya NO se versionan directamente** (ver `.gitignore`) — son el destino generado por `scripts/select_spectrum_source.py <fuente>` a partir de `data/sources/<fuente>/*.csv`, que sí se versiona y es la fuente de verdad. Fuentes en `data/sources/`: `spenvis/` (plan B, ISO-15390+ESP-PSYCHIC, placeholders, ya no es la fuente activa) y `oltaris/` (**activa, completa desde 2026-09-10**: BON2020 para GCR mínimo/máximo, evento histórico Oct 1989/Feb 1956-LaRC para SEP — los 6 archivos son datos reales, verificados y probados, ver checklist). `SpectrumSampler` es agnóstico a la fuente (solo lee dos columnas energía/flujo), así que cambiar de fuente no toca código C++, solo qué CSV se copia a `data/`.
- `macros/legacy/`: las 4 macros de escenarios de blindaje pasivo (`escenario1-4`), conservadas para referencia pero ya no reflejan el esquema de resultados actual.
- `scripts/run_sweep.py`: corre automáticamente las 140 combinaciones del barrido (4 evento×fase × 7 campo × 5 posición), con semillas aleatorias fijas por corrida para reproducibilidad. Soporta `--n-events` y `--limit` (nota: `--limit N` corre las primeras N combinaciones en el orden del barrido, no necesariamente una por cada modelo/fase) para hacer una corrida piloto antes del barrido completo. También soporta `--repeats` (repeticiones por combinación, para estadística) y `--only-model GCR|SEP` (repartir el barrido en equipo, ver README.md). El manifiesto (`sweep_manifest.csv`) y el CSV de resultados se escriben por append, corrida por corrida, así que un corte a la mitad no pierde lo ya corrido; resume está activado **por defecto** y salta las combinaciones `(índice, repetición)` que ya tengan `exit_code 0` en el manifiesto — usar `--no-resume` para forzar rehacer todo desde cero (ver sección correspondiente en README.md). El default de `--n-events` (y el `BASE_SEED`) vienen de `geant4/sweep_config.py`, compartido entre proyectos — ver ese archivo antes de hardcodear un número de eventos "oficial" en un script nuevo. Los parámetros específicos de esta geometría (campo uniforme, posiciones del astronauta) NO están ahí a propósito, porque `ActiveShield_Sim` tendrá un espacio de parámetros distinto (bobinas Halbach) una vez que exista — `ActiveShield_Sim` todavía no tiene lanzador por bins: faltan la definición de energías/configuraciones y los pesos físicos. Su lector de mapa ya existe; no confundirlo con un mapa físico validado.
- Resultados: `resultados_dosis_sweep.csv` (columnas `modelo,fase,field_T,astronaut_x_m,n_eventos,edep_MeV,masa_kg,dosis_Gy,dosis_absoluta_Gy`), una fila por corrida. `dosis_Gy` es la dosis cruda sin ponderar (QA); `dosis_absoluta_Gy` es la normalización física real (Gy/día para GCR, Gy del evento completo para SEP) — ver "Dosis absoluta implementada" en Pendientes conocidos.

### Nota técnica: partículas atrapadas en el campo (importante)

Como `ShipInterior` es vacío (sin material), una partícula cargada cuyo radio de giro en el campo no la haga tocar el phantom ni el casco puede quedar circulando indefinidamente — Geant4 no la detiene por sí solo, y esto causó que una corrida de prueba tardara +27 minutos en vez de segundos. Se corrigió con `G4UserLimits::SetUserMaxTrackLength()` en `ShipInterior` (`DetectorConstruction.cc`) más `physicsList->RegisterPhysics(new G4StepLimiterPhysics())` en `main.cc` (necesario para que Geant4 realmente respete ese límite). Si en el futuro cambian la geometría o el campo y ven corridas anormalmente lentas, este es el primer sospechoso.

## Cómo compilar y correr

Dentro de `geant4/GCR_SEP_Sim/`. **Ojo:** en este entorno conda (`geant4_env`) la variable `$CXX` documentada en `README.md` está vacía (el entorno no instaló el compilador conda-forge, solo Geant4) y `cmake` se resuelve al del sistema, que no encuentra las dependencias del entorno conda por su cuenta — hay que pasarle el compilador del sistema y el prefix path explícitamente:

    rm -rf build && mkdir build && cd build
    cmake -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" ..
    make -j$(nproc)

Corrida piloto del barrido (rápida, para validar que todo funciona):

    python3 ../scripts/run_sweep.py --n-events 100 --limit 4

Barrido completo (140 corridas):

    python3 ../scripts/run_sweep.py

## Pendientes conocidos

- ~~Reemplazar los 6 CSV placeholder de `data/sources/` con espectros reales por fase solar.~~ **Hecho (2026-09-10), los 6 son reales.** Modelos: **Badhwar-O'Neill 2020** para GCR (mínimo 31/12/2019-01/01/2020, máximo 14-15/01/2023 — limitado por BON2020 en OLTARIS, ver nota arriba), **evento histórico** para SEP (Oct 1989 = máximo, Feb 1956 ajuste LaRC = mínimo — no el modelo probabilístico ESP-PSYCHIC). Detalle completo: [`docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md).
- **Dosis absoluta implementada en el piloto GCR_SEP_Sim (2026-09-09).** El
  scorer sigue calculando `dosis_Gy` (cruda, sin ponderar, por los N eventos
  mezclados de una corrida — se conserva por QA) pero `resultados_dosis_sweep.csv`
  ahora también trae `dosis_absoluta_Gy`, calculada en `RunAction::EndOfRunAction`
  acumulando energía depositada y N por especie (`GCR_H`, `GCR_He`, `SEP_p`
  — ver `PrimaryGeneratorAction::GetLastSpecies()`/`GetIntegratedFlux()`) y
  combinando:

      R[s] = edep_dep[s] (J) / (masa_fantoma_kg * N[s])         -- Gy por primario simulado de la especie s
      W[s] = pi * R_esfera_fuente_cm^2 * integral_E Flujo_s(E) dE -- primarios reales que cruzan la esfera fuente
      dosis_absoluta_Gy = suma_s R[s] * W[s]

  `integral_E Flujo_s(E) dE` es el flujo/fluencia tal cual está en el CSV de
  OLTARIS integrado por trapecios (`SpectrumSampler::GetIntegratedFlux()`),
  sin reescalar por tiempo aparte: los CSV de GCR ya vienen en
  `particles/(day*cm2)` (OLTARIS "Boundary Flux"), así que `dosis_absoluta_Gy`
  para GCR es **Gy/día**, no Gy total ni Gy/s — no multiplicar de nuevo por
  86400. Los de SEP vienen en `particles/cm2` (OLTARIS "Boundary Fluence",
  ya integrada sobre todo el evento), así que `dosis_absoluta_Gy` para SEP
  es la **dosis aguda del evento completo** (Oct 1989), sin factor de tiempo.
  `pi * R^2` es el área de sección transversal de la esfera fuente (radio =
  casco + 20 cm) — la relación estándar entre flujo omnidireccional y tasa
  de partículas reales que cruzan una superficie convexa, independiente de
  si el muestreo interno de direcciones es radial (como hoy) o con ley de
  coseno. `aggregate_results.py` ya agrega esta columna (media/std/IC95%)
  junto a `dosis_Gy`; degrada con aviso, no falla, si algún CSV viene de
  antes de este cambio y no la trae. **Limitaciones que siguen igual:**
  muestreo angular de entrada radial (no ley de coseno, simplificación del
  piloto), GCR limitado a H+He, Gy no es Sv. La fórmula completa (con bins
  de energía, para producción de `ActiveShield_Sim`) sigue en
  `geant4/ActiveShield_Sim/docs/modelo_realista.md` — ese documento describe
  un pipeline distinto (por bins/órgano), no el de este piloto.
- Medir el tiempo del barrido completo con `--n-events 10000` real antes de dejarlo corriendo desatendido (un piloto con 200 eventos tomó ~2s/corrida; a 10000 eventos cada corrida será más lenta, sobre todo por la physics list `Shielding` — corran un piloto con el `--n-events` real primero para estimar el total de las 140 corridas).
- **Bins ya acordados para ActiveShield_Sim.** Pendientes de implementación:
  respuesta por energía/especie/órgano, pesos físicos y su incertidumbre.
  El piloto conserva su barrido anterior; no usar sus corridas como si fueran
  respuestas monoenergéticas. Ver el documento de decisiones enlazado arriba.


## Reglas de trabajo en este repositorio

- **Documentación siempre al día:** cualquier cambio de código, metodología o proceso de equipo debe venir acompañado de la actualización correspondiente en `README.md` y/o `AGENTS.md` en el mismo cambio (no como tarea pendiente para después). Si un commit modifica comportamiento (flags nuevos, cambios de esquema de datos, nuevos pasos de flujo de trabajo), la documentación se actualiza junto con el código, no en un commit aparte ni "cuando haya tiempo".
- **Sin coautoría en commits:** no incluir línea de `Co-Authored-By` (ni ninguna otra atribución de coautoría) en los mensajes de commit de este repositorio, sin importar quién o qué haya generado el cambio.
