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
(`field/production/crewhat_elmer_fullscale.map`, ya no requerido
explícitamente) — antes de este cambio, ninguna combinación mencionaba
qué campo específico era "el de producción" fuera de la CLI. Motivo: ver
la entrada "Error de campo vs. error de dosis en Elmer" más abajo —
Biot-Savart sobreestima dosis 36-48% frente a Elmer en la misma
configuración porque trata cada bobina como un filamento con núcleo de
6,7cm, mucho menor que el winding pack real (**0,67m, CORC — no 1,43m/cinta
12mm, ver corrección más abajo**), y la región de la nave no está lo
bastante lejos del arreglo (radio Halbach 8m) para que esa aproximación
sea buena ahí. Elmer resuelve la distribución de corriente real sobre la
sección del conductor. `field/production/crewhat_niac_max.map`
(Biot-Savart) se conserva para comparación, ya no es el default. **Sin
verificar todavía en vivo la combinación exacta Elmer+coilGeometry dentro
de `run_organ_sweep.py`** (cada pieza se probó por separado — Elmer a
mano, coilGeometry con Biot-Savart en el piloto de 8 bins — pero no las
tres juntas en el lanzador real): verificar con `--limit 1` antes de un
barrido real.

**Corrección importante (2026-09-12): el arreglo de 8 bobinas siempre fue
CORC, nunca la cinta 12mm — descubierto al preparar estos archivos para
subir a git.** `field/examples/crewhat_halbach_array_pilot.json` (el
único config de arreglo que existe, usado para TODO el trabajo de
arreglo documentado arriba — geometría, GDML, campo Biot-Savart, ambas
corridas Elmer r1/r2, el ablation de patrón angular, y el campo Elmer a
escala real de hoy) tiene `material: "crewhat_corc_homogenized"` y
`winding_pack_side_m: 0.67` — es la variante **CORC**, no la cinta 12mm
(`crewhat_tape_homogenized`, 1,43m) que la bitácora de "Conductor —
decisión: construir ambas opciones" (más arriba) dice que se empieza a
probar primero. Esa decisión sí se siguió para los **pilotos de una sola
bobina** (existen ambas variantes: `crewhat_ellipse_tape12mm_pilot.json`
y `crewhat_ellipse_corc_pilot.json`, con Elmer corrido para la cinta en
`crewhat_elmer_tape12mm{,_r2,_r3}`) — pero **el arreglo completo de 8
bobinas nunca se ensambló con la cinta 12mm, solo con CORC**. Ningún
resultado del arreglo (Biot-Savart, Elmer, ablation, ni la comparación de
dosis Biot-Savart-vs-Elmer de hoy) es de la cinta 12mm — todos son de
CORC. No es un error introducido hoy, es cómo se venían generando estos
archivos desde el 2026-09-10; simplemente nadie lo había verificado
explícitamente contra el JSON fuente hasta ahora. Pendiente real: si el
paper quiere reportar también el arreglo con la cinta 12mm (la opción de
mayor Ic, preferida en la decisión original), hay que generarlo desde
cero — geometría, malla, GDML, Biot-Savart y, si se quiere comparar,
Elmer — no existe ningún archivo de eso todavía.

**Archivos de producción versionados en git, `field/production/`
(2026-09-12):** antes, `.map`/GDML vivían solo en `field/generated/`/
`build/` (ambos excluidos de git a propósito, ver más abajo) — cualquiera
que clonara el repo tenía que instalar Elmer/Gmsh y regenerar todo desde
cero para poder correr `run_organ_sweep.py`, aunque no fuera a cambiar
nada del campo o la geometría. `field/production/` es una excepción
deliberada y acotada a esta carpeta (`!field/production/**` en
`.gitignore`, que de otro modo ignora todo `*.map` globalmente) — no
cambia el criterio para `field/generated/`, que sigue siendo
scratch/regenerable y no se versiona. Contiene, con sus manifiestos
SHA256: `crewhat_elmer_fullscale.map`/`.field-manifest.json` (campo de
producción actual), `crewhat_niac_max.map`/`.field-manifest.json`
(Biot-Savart, para comparación), `crewhat_corc_array.gdml` +
`.manifest.json` + `_materials.json` + `_config.json` (geometría sólida
CORC de las 8 bobinas — nombrado explícitamente `corc`, no genérico
`array`, precisamente por la corrección de arriba). 12MB en total. Los
defaults de `run_organ_sweep.py` (`DEFAULT_FIELD_MAP`/
`DEFAULT_COIL_GEOMETRY`) apuntan aquí, no a `build/`/`field/generated/`.

**El `.map` de Elmer, de cubo a caja anisotrópica (2026-09-12, dos
correcciones seguidas):** el dominio mallado real es `X:±11,8m,
Y:±13,8m, Z:±7,8m` — no es un cubo, porque el arreglo Halbach tampoco lo
es (vive en el plano XY, radio 8m, mucho más extendido ahí que a lo
largo de Z, el eje de la nave). Primer intento: 7,2m cúbico (muy poco
margen sobre la esfera fuente de la nave, ~6,94m — un usuario lo notó).
Segundo intento: 7,6m cúbico (más margen, pero seguía limitado por el
eje más corto). **Un usuario señaló el problema de fondo**: un `.map`
cúbico no solo desperdicia margen en X/Y, sino que además el anillo de
bobinas (y desde hoy, su sólido físico real vía
`/spacecraft/coilGeometry`) se sale de un cubo de 7,6m en X/Y — cualquier
secundario cargado que llegara ahí leía campo cero exactamente donde
debería haber campo fuerte cerca del conductor, un hueco físico real, no
solo cosmético. El formato `.map` que lee Geant4
(`TabulatedMagneticField.cc`) ya soporta `nx/ny/nz` y `dx/dy/dz`
independientes por eje — solo `elmer_array_to_map.py` forzaba un cubo.
**Corregido:** `--half-size` ahora acepta 1 valor (cubo, retrocompatible)
o 3 (`X Y Z`). El `.map` actual usa X=11,3m/Y=13,3m/Z=7,6m — margen
~0,5m contra el límite real de malla en X/Y, 0,235m en Z, 0,66m sobre la
esfera fuente. Reusa la misma solución Elmer ya calculada, sin remallar
ni resolver de nuevo. Verificado: 700 de 82.720 nodos (0,85%) rellenados
por estar dentro de un conductor, dentro del 5% que
`_fill_conductor_gaps()` tolera; el campo máximo en la grilla ahora es
6,25T (esa región, cerca de las bobinas, ni se muestreaba con el cubo).
**Verificado en vivo con Geant4 (2026-09-12):** el `.map` anisotrópico ya
corrió sin problema en la producción real de Bryam (ver más abajo) —
docenas de corridas exitosas (`exit_code 0`) con `coilGeometry` +
`fieldMap` juntos, el escenario que faltaba probar.

**Piloto de 8 bins (1 por bin, GCR_H, posición 0), con la configuración
final (14 hilos, bobinas incluidas, 10000 eventos reales) — hallazgo
crítico para el presupuesto de tiempo, tabla completa:**

| Bin | Energía (MeV/amu) | Tiempo real |
|---|---|---|
| 0 | 17,8 | 21,6s |
| 1 | 56,2 | 21,8s |
| 2 | 177,8 | 34,1s |
| 3 | 562,3 | 72,6s |
| 4 | 1778,3 | 275,3s |
| 5 | 5623,4 | 730,4s |
| 6 | 17782,8 | 1909,5s (31,8 min) |
| 7 | 56230,4 | **5141,1s (85,7 min)** |

El costo **no es uniforme entre bins** — cada bin de energía tarda
aproximadamente 2,3-2,7x el anterior. Los bins 6-7 solos (2 de 8) se
comen ~80% del tiempo total de las 8 bins de una posición (suma completa
~2,28h) — cualquier presupuesto de tiempo para el barrido debe usar esta
curva real, no un promedio plano.

**Producción real de Bryam (`--only-positions 2,3,4`, 72 corridas, sin
repeticiones), en curso desde 2026-09-12 01:48, lanzada automáticamente
al terminar el piloto:**

- **GCR_H completo: 24/24, 23.233,5s = 6,45h** — muy cerca de la
  proyección ingenua (3× el piloto de 1 posición ≈ 6,84h, dado que son
  las mismas 8 bins en 3 posiciones).
- **GCR_He, en curso — resultando MÁS caro que GCR_H a la misma energía
  nominal, no igual como se había proyectado antes de tener datos
  reales:** bin2 (177,8 MeV/amu nominal) tarda 111-122s aquí, vs 34,1s en
  GCR_H — ~3,5x más. Bin3 (562,3 MeV/amu nominal) tarda 422-441s vs
  72-95s en GCR_H — ~5x más. Explicación (no solo observación): el
  `/gun/fixedEnergyMeV` es MeV/**amu**, y `ICRP110PhantomPrimaryGenerator
  Action.cc` multiplica por el número de masa (`kineticEnergy =
  keMeVPerNucleon * A * MeV`) — para GCR_He (A=4) la energía cinética
  real simulada es **4x la de GCR_H a la misma etiqueta de bin** (ej. el
  bin2 de GCR_He corre en realidad a ~711 MeV, no 177,8 MeV), así que
  cuesta lo que costaría ese rango de energía real, consistente con el
  patrón de la tabla de arriba. Implica que el total de GCR_He
  probablemente supere las ~6,45h de GCR_H, no las iguale — sin cifra
  final todavía (bins 4-7 de GCR_He, los más caros, sin correr aún).
- **SEP_p, sin empezar** — rango 0,01-300 MeV (sin el multiplicador ×A,
  A=1), su bin más caro (~300 MeV) cae entre el bin2 y bin3 de GCR_H en
  costo — se espera barato (minutos, no horas) para las 24 combinaciones
  juntas, pero sigue siendo una proyección, no medido.
- **Decisión (2026-09-12): bin7 de GCR_He se salta por ahora, se corre
  aparte después con cómputo distribuido.** El bin6 de GCR_He ya costó
  7105,6s/7910,5s (~2h) por corrida — extrapolando el mismo factor de
  crecimiento (~2,3-2,8x por bin), el bin7 (energía real ~225.000 MeV,
  la más alta de todo el barrido) podría rondar 5-6h por corrida, ~15-18h
  para las 3 posiciones — sin confirmar, es una extrapolación, no una
  medición. Implementado `--skip-bins` en `run_organ_sweep.py` (lista de
  `bin_index` a omitir, combinable con `--only-positions`) para poder
  seguir con el resto del barrido (SEP_p) sin esperar esas horas. Un
  script de este mismo cambio detectó cuándo terminó el bin6
  (índices 72-74, GCR_He, posiciones 2-4) y relanzó automáticamente con
  `--skip-bins 7`, sin perder ninguna corrida ya hecha (mismo mecanismo
  de resume). El bin7 de GCR_He (posiciones 2,3,4) queda pendiente,
  planeado para correrse por separado — candidato natural para probar
  cómputo distribuido en una sola tanda de 3 corridas caras, en vez de
  todo el barrido.

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

### Instalación mínima para nodos de cómputo (2026-09-12)

`scripts/install_compute_node.sh` (nuevo) — para una máquina que solo va
a CORRER los barridos ya existentes (voluntarios, CI, VMs), no a
regenerar geometría/campo. Verificado, no supuesto: los 7 build strings
de `geant4=11.4.2` en conda-forge se agrupan en 3 familias (`noqt_*`,
`qt_*`, `py3xx_*`) que comparten exactamente la misma física/GDML/datos —
extraje y comparé el `Geant4Config.cmake` real de una build `qt_` y una
`noqt_` directamente (sin instalar un entorno completo para la segunda,
solo el `.conda` del paquete): la única diferencia es
`Geant4_qt_FOUND ON` vs `OFF`, que decide si el config exige
Qt6Core/Gui/Widgets/OpenGLWidgets al configurar cmake. `environment.yml`
dejaba `geant4=11.4.2` sin fijar variante (el mismo patrón que ya había
causado el bug histórico de EXPAT/ZLIB) y por eso terminó resolviendo a
`qt_1bf189c_1` en esta máquina, con `qt6-main` y ~32 paquetes
transitivos de la pila Qt/X11 desktop (dbus, fontconfig, wayland,
xcb-util-*, etc.) — medido: ~400MB instalados de más, sin necesitarlos
nunca para correr en modo batch.

**`environment.headless.yml`** (nuevo) fija `geant4=11.4.2=noqt_*`
explícitamente y quita `qt6-main` — `conda create --dry-run` confirma que
resuelve sin ninguno de esos ~32 paquetes. `xorg-libx11` se mantiene: el
`vis_raytracer_x11` del config sigue en `ON` incluso en el build noqt (no
depende de la variante qt/noqt), así que X11 sigue siendo requerido —
mucho más liviano que Qt6 completo, pero no se puede quitar sin
recompilar Geant4 con esa opción apagada (fuera de alcance).

**`-DWITH_GEANT4_UIVIS=OFF`** — ya existía en `ActiveShield_Sim/
CMakeLists.txt` (heredado del ejemplo oficial, nunca usado hasta ahora);
agregado el mismo patrón a `GCR_SEP_Sim/CMakeLists.txt` para paridad.
Evita pedir los componentes `ui_all`/`vis_all` de `find_package(Geant4
...)` — no hacen falta para correr en modo batch, y el build noqt no
tiene Qt6 para satisfacerlos de todos modos.

**Verificado de punta a punta, no solo que compila:** creé
`geant4_env_headless` de verdad, compilé los dos proyectos con
`-DWITH_GEANT4_UIVIS=OFF`, `ctest` pasa, y — la prueba que realmente
importa — corrí la misma configuración exacta (semilla, energía, campo,
eventos) que ya había corrido antes en el entorno completo con Qt:
**dosis idéntica bit a bit** (8,0049e-08 Gy en ambos). El build noqt da
el mismo resultado físico, no es una aproximación.

**No incluye** `field/.venv` ni Elmer — un nodo de cómputo no regenera
geometría/campo, usa directamente `field/production/` (ya versionado en
git, ver más arriba). Si algún día se necesita regenerar algo en la
misma máquina, seguir usando `scripts/install.sh` completo, no este.

**Sobre si convendría una rama de git aparte para esto:** no — un script
adicional en la misma rama (lo que se hizo) no tiene el riesgo de
divergencia/reconciliación que sí tuvo el trabajo paralelo de Bryam/Eddy
en `ActiveShield_Sim` esta misma sesión (dos implementaciones del mismo
lanzador, una se descartó al hacer merge). Una rama serviría si el plan
fuera cambiar el comportamiento de la rama principal de forma
incompatible por un tiempo — aquí el objetivo es que cualquiera, en
`main`, elija entre `install.sh` (completo) o `install_compute_node.sh`
(mínimo) según lo que necesite, sin que uno le oculte cambios al otro.

## Cómputo distribuido para el barrido de ActiveShield_Sim (2026-09-12)

**Por qué:** el reparto manual entre 2 laptops (`--only-positions`) llegó a
un límite concreto — el bin7 de GCR_He (3 corridas, offsets 2/3/4) se
proyectó en 5-6h por corrida y se decidió diferirlo explícitamente para
"correrse aparte después con cómputo distribuido" (ver la entrada de arriba,
"Piloto de 8 bins"/"Decisión bin7 de GCR_He"). El equipo (con acceso a
GitHub Education/crédito de nube) decidió construir un coordinator/worker
reusable en vez de resolver solo esas 3 corridas ad-hoc, en una rama nueva
(`infra/distributed-sweep`) para no interferir con quien sigue corriendo el
barrido normal en `main`.

**Diseño, implementado en `infra/`:**
- **Grano del job = una sola combinación** `(species, bin_index,
  offset_x_m, repeticion)`, no una posición completa (24 combinaciones) —
  el costo por combinación varía ~250x (20s a 85min, ver tabla de arriba),
  así que empaquetar por posición mezclaría jobs baratos y carísimos,
  perdiendo el paralelismo real que se necesita para el caso urgente
  (aislar cada corrida de bin7 a su propia VM).
- **Coordinator** (`infra/coordinator/`): FastAPI + SQLite (WAL, claim
  atómico vía `BEGIN IMMEDIATE` para que dos workers no reciban el mismo
  job), con endpoints `register/heartbeat/jobs/next/start/result/fail/
  health`. Una tarea de fondo reencola a `pending` cualquier job
  `claimed`/`running` cuyo worker no dé heartbeat en 6h — umbral generoso
  a propósito, porque una corrida legítima de bin6/7 tarda horas y un
  timeout corto duplicaría cómputo caro en vez de solo esperar de más.
  `infra/coordinator/seed_jobs.py` puebla la cola escribiendo directo a la
  SQLite (no expuesto por HTTP, para no abrir esa superficie sin
  autenticación — ver riesgos abajo).
- **Worker** (`infra/worker/worker.py`): hace poll al coordinator, traduce
  el job recibido a `run_organ_sweep.py --only-species X --only-positions Y
  --only-bins Z --limit 1`, y al terminar filtra
  `resultados_organo_sweep.csv` a solo las filas de ese job antes de
  subirlo (el CSV se acumula entre jobs por el resume propio del script —
  nunca se sube completo, o se reportarían de nuevo resultados de jobs
  anteriores de ese mismo worker).
- **`--only-species`/`--only-bins` en `run_organ_sweep.py` no se tocaron
  desde esta rama** — coincidencia real de trabajo paralelo (mismo patrón
  ya documentado más arriba para "Segundo grupo de datos"): esta rama
  necesitaba exactamente ese filtro para el worker, y Bryam lo agregó en
  `main` el mismo día (commit `13b31f9`, motivado por su propio hallazgo —
  `--skip-bins 7` saltaba el bin7 de las 3 especies, no solo de GCR_He) con
  `--only-bins` además, más directo que construir el complemento con
  `--skip-bins` como se había planeado aquí originalmente. Al detectarlo
  (esta rama estaba fast-forward un commit detrás de `main`), se descartó
  la implementación propia duplicada de `--only-species` y se rebaseó sobre
  `main`, adoptando la de Bryam sin cambios — `worker.py` usa
  `--only-bins` directo. Ningún archivo de producción se modifica desde
  esta rama; `install_compute_node.sh` y `field/production/*` se reusan
  sin cambios.
- **`--repetition-start` en `run_organ_sweep.py`** (nuevo, aditivo): el
  worker necesitaba pedir exactamente la repetición del job (no siempre
  desde 0) sin barrer repeticiones anteriores — `for rep in
  range(args.repetition_start, args.repetition_start + args.repeats)` en
  vez de `range(args.repeats)`. Con `--repeats 1` (lo que usa el worker)
  corre solo ese índice exacto. Único cambio de esta rama a un archivo de
  producción, además de `--only-species`/`--only-bins` ya mencionados
  (esos sí vinieron de `main`, ver arriba).
- **Docker** (`docker/Dockerfile.geant4-worker`): reusa
  `scripts/install_compute_node.sh --skip-system` tal cual (no reescrito),
  con `COPY . .` para traer el repo completo — incluye `field/production/`
  ya versionado, así que la imagen no necesita Elmer/Gmsh ni regenerar
  campo/geometría. `ARG BASE_IMAGE=ubuntu:24.04` permite reconstruir rápido
  reusando una imagen ya compilada como base (`--build-arg
  BASE_IMAGE=geant4-worker:previa`) cuando solo cambia una capa posterior
  a la compilación (ej. `entrypoint.sh`) — evita recompilar Geant4 desde
  cero (~10 min) por un cambio de una línea. `docker/entrypoint.sh` activa
  `geant4_env_headless` explícitamente antes del `CMD`, porque un
  contenedor no interactivo no carga el `.bashrc` donde vive el `conda
  init` que el script ya deja configurado. El `ctest` del script corre en
  build time como gate: si algo no compila, el `docker build` falla ahí,
  no en producción.
  - **Bug real encontrado y corregido probando la imagen de verdad:** el
    `entrypoint.sh` inicial tenía `set -euo pipefail` alrededor de `source
    conda.sh && conda activate` — los scripts que Geant4/conda-forge
    instala en `etc/conda/activate.d/` (ej.
    `activate-geant4-data-abla.sh`, que exporta `G4ABLADATA`) referencian
    variables sin inicializar antes de asignarlas, un patrón estándar de
    conda que no es compatible con `set -u`. El contenedor fallaba al
    arrancar con `G4ABLADATA: unbound variable`, antes de llegar siquiera
    a ejecutar el worker. Corregido: `set +u` / `set -u` alrededor
    únicamente del `source`+`conda activate`, dejando `-e`/`pipefail`
    activos en el resto del script.
  - Dos bugs de ruta encontrados antes de ese: `/opt/miniconda3`
    hardcodeado no existe (`install_compute_node.sh` usa
    `$MINICONDA_DIR`, default `$HOME/miniconda3` — como root en el
    contenedor, `$HOME=/root`, no `/opt`); y descargas de
    `conda.anaconda.org` cortándose a mitad de paquetes grandes de datos
    de Geant4 (no un bug de código, red intermitente del entorno de
    build) — mitigado con un `.condarc` con `remote_max_retries: 10`
    antes de invocar el script.
- **Worker, endurecido tras la primera ronda de pruebas:** cada intento
  corre en un directorio de trabajo propio (`tempfile.TemporaryDirectory`,
  symlinks al binario/datos ya compilados en `BUILD_DIR` — no copia los
  ~5GB del build) para que dos intentos consecutivos del mismo worker
  nunca compartan ni pisen el CSV/manifiesto del otro. Heartbeat corre en
  un hilo daemon separado (`heartbeat_loop`, intervalo propio
  `HEARTBEAT_INTERVAL_S`) del loop principal de poll/ejecutar — necesario
  porque una corrida de bin6/7 puede tardar horas: sin esto, el worker
  nunca mandaría heartbeat mientras el subprocess corre, y el coordinator
  lo reencolaría de forma prematura pese a estar vivo. El subprocess corre
  en su propio grupo de procesos (`start_new_session=True` +
  `os.killpg`) para que un `SIGTERM` (`docker stop`) termine también al
  binario de Geant4, no solo al script Python padre.
- **Coordinator, endurecido en el mismo sentido:** `submit_result` ahora
  valida que las filas del CSV subido correspondan exactamente al job
  asignado (especie, bin, offset, repetición, n_events) antes de
  aceptarlo — rechaza con 422 si no coinciden, en vez de confiar
  ciegamente en lo que sube el worker. Cada intento de subida escribe a un
  subdirectorio único (`results/job_{id}/{uuid4().hex}/`) para que un
  worker reencolado por timeout que termina reportando tarde no pueda
  sobreescribir los archivos de un intento ya aceptado como `done`
  (verificado con test: la segunda subida es rechazada con 409 y los
  archivos originales quedan intactos). `DB_PATH`/`STALE_JOB_TIMEOUT_S`
  configurables por variable de entorno, útil para aislar la base de una
  corrida de pruebas de la de producción.
- **Telemetría en vivo y matching de requisitos (2026-09-13), a pedido
  del usuario tras preguntar qué puede ver el coordinator de cada
  voluntario.** Antes, `register()` solo mandaba `cpu_count`/`ram_gb`
  (total, una sola vez al arrancar) y el scheduler entregaba el job de
  mayor prioridad a cualquiera sin comparar recursos. Ahora:
  - Cada heartbeat (default cada 30s, ya en hilo separado — ver arriba)
    reenvía `ram_free_gb` (`/proc/meminfo` `MemAvailable`, no `MemFree`
    — la estimación del kernel de RAM realmente disponible sin swap) y
    `cpu_load_pct` (load average de 1 min normalizado por núcleos, sin
    agregar `psutil`) — visible en el nuevo `GET /api/v1/workers`.
  - `jobs.min_ram_gb`/`min_cpu_count` (default 0, `seed_jobs.py
    --min-ram-gb --min-cpu-count`): `claim_next_job()` en `db.py` solo
    ofrece el job a un worker cuya telemetría **en vivo** (RAM libre
    ahora mismo, no RAM instalada) alcance — evita mandar un bin caro
    (ej. GCR_He bin7) a una VM voluntaria con poca RAM libre en ese
    momento. Un worker sin telemetría (versión vieja) no queda
    bloqueado: cae a comparar contra `ram_gb` total.
  - **Explícitamente NO se agregó**: medición de ancho de banda de red
    (no hay ningún test de velocidad), ni ningún acceso al host más allá
    de lo que el propio proceso del worker decide leer y enviar por HTTP
    — nada de SSH, inspección de otros procesos, o telemetría push desde
    el coordinator hacia el worker. Detalle completo, con qué campos
    exactos se ven y por qué, en `infra/README.md`, sección "Qué ve el
    coordinator de cada worker (y qué no)".
  - Verificado con 6 tests nuevos (19 en total, todos pasan): worker por
    debajo de RAM/CPU mínima no recibe el job, worker que sí cumple lo
    recibe, worker sin telemetría cae a RAM total, heartbeat actualiza
    telemetría en vivo, heartbeat sin telemetría no borra la anterior.
    Probado también por HTTP end-to-end (no solo a nivel de función):
    `seed_jobs.py --min-ram-gb 8` seguido de dos workers con distinta
    `ram_free_gb` — el de RAM insuficiente recibe `204`, el otro recibe
    el job con sus columnas `min_ram_gb`/`min_cpu_count` visibles.

**Dónde corre el coordinator y las imágenes del worker:** el coordinator es
liviano (solo orquesta, no computa) y se recomienda correrlo en una VM
pequeña propia (misma cuenta de crédito educativo que los workers), no en
una plataforma serverless (Vercel no sirve — necesita un proceso de larga
duración con disco persistente para la SQLite). La imagen del worker se
publica en GHCR (gratis con GitHub, integrado a Actions) y cada VM worker
corre `docker run -d --restart unless-stopped -e COORDINATOR_URL=...
ghcr.io/<usuario>/geant4-worker:<tag>` sin necesitar el repo clonado aparte.

**Verificado end-to-end de punta a punta (2026-09-12/13), incluyendo Docker
real — ya no solo local sin contenedor:**
- 16 tests de `infra/coordinator/test_coordinator.py` + 3 de
  `infra/worker/test_worker.py` pasan (19 en total): registro, claim
  atómico bajo concurrencia simulada con hilos, ciclo completo
  pending→done, rechazo de un worker que reporta un job que no es suyo
  (409), reencolado por heartbeat vencido, límite de reintentos agotados
  (`failed` tras 3 intentos), rechazo de una subida tardía que intenta
  sobreescribir un resultado ya aceptado, que `start` exige que el
  worker que lo marca sea el mismo que lo reclamó, y (2026-09-13) el
  matching de requisitos mínimos de RAM/CPU con telemetría en vivo (ver
  entrada de arriba).
- **Imagen Docker construida y corriendo el worker real de punta a
  punta**: `docker build -f docker/Dockerfile.geant4-worker .` completa
  (compila Geant4 headless + ambos binarios con `ctest` como gate) y el
  worker, corriendo dentro del contenedor (`--network host` contra un
  coordinator en el host), reclamó un job de prueba (`SEP_p bin1
  offset_x_m=1.0, n_events=100`), ejecutó `run_organ_sweep.py` de verdad
  dentro de Geant4, generó **142 filas de dosis por órgano**, las filtró y
  las subió — el coordinator las guardó en disco y marcó el job `done`.
  Este es el escenario que antes de este cambio nunca se había probado
  (Elmer+coilGeometry+Docker+coordinator juntos).
- Imagen final consolidada como `geant4-worker:latest` (los tags
  intermedios de iteración del build se descartaron).

**Riesgos aceptados explícitamente en este primer corte (no resueltos, ver
`seed_jobs.py`/`app.py` para el detalle):**
- **Sin autenticación de workers** — cualquiera con la URL del coordinator
  puede registrarse y reclamar/reportar jobs. Aceptable mientras el
  coordinator no tenga IP pública sin restricción (VPN/firewall/IP
  allowlist); si se expone públicamente, agregar un `shared_secret` por
  variable de entorno antes.
- **Sin backup automático** de `infra/coordinator/data/` (SQLite +
  resultados subidos) — mitigación manual (copiar el directorio) hasta que
  el volumen lo justifique. Decisión ya tomada de no usar S3/R2 en esta
  fase.
- El reencolado por heartbeat vencido puede, en el peor caso, duplicar
  cómputo si un worker legítimo tarda más que el umbral de 6h sin poder
  mandar heartbeat (ej. red caída pero el proceso sigue vivo) — se prefirió
  este riesgo (poco probable, y el costo es "recomputar", no perder datos)
  sobre un timeout corto que reencolaría corridas de horas que iban a
  terminar bien. El heartbeat en hilo separado (ver arriba) reduce aún más
  la probabilidad de este caso: ya no depende de que el loop principal
  esté libre para mandar heartbeat.

**Desplegado en producción real (2026-09-13):**
- **Imagen publicada en GHCR** (manual, no vía workflow todavía):
  `ghcr.io/s7even-silva/iac-project/geant4-worker:latest`.
- **Coordinator corriendo 24/7 en una VM real** — no en Azure: la
  suscripción "Azure for Students" del usuario rechazó la creación de
  cualquier VM en `East US` y `West US 2` con el mismo error de
  plataforma en los tres intentos (`RequestDisallowedByAzure: This
  policy maintains a set of best available regions... contact
  support`), incluso con `Microsoft.Compute`/`Network`/`Storage` ya
  registrados — es una restricción de cuenta que solo soporte de Azure
  puede levantar, no algo resoluble reintentando o cambiando de región.
  Se migró a **GCP Always Free Tier** (`e2-micro`, zona `us-central1-a`,
  dentro del límite gratuito permanente — no consume el crédito de
  prueba de $300). `infra/deploy/provision_gcp_coordinator.sh` (nuevo,
  paralelo a `provision_azure_coordinator.sh` que queda listo para
  reintentar si Azure resuelve el bloqueo) crea la regla de firewall y
  la VM con el mismo `cloud-init-coordinator.yaml` (formato estándar,
  funciona igual en ambos proveedores). URL pública:
  `http://34.134.100.224:8000`.
- **11 jobs reales pendientes en la cola** (poblados directamente en la
  VM vía SSH, `COORDINATOR_DB` apuntando a
  `/var/lib/geant4-coordinator/coordinator.db` porque el servicio corre
  como usuario `coordinator`, no con el default de `db.py`):
  - 2 de `GCR_He bin6` (offsets 0,1 — el resto de ese bin ya lo corrió
    Bryam fuera del coordinator, confirmado leyendo
    `resultados/organ_sweep_manifest_bryam.csv`).
  - 5 posiciones completas de `GCR_He bin7` (prioridad 20, la más
    alta — el caso que motivó esta infraestructura desde el principio,
    nunca corrido por nadie), con **requisito mínimo `min_ram_gb=8`,
    `min_cpu_count=4`** (actualizado vía `UPDATE` directo sobre los
    jobs ya poblados, no un flag de `seed_jobs.py` en este caso — el
    usuario preguntó explícitamente por el riesgo de que una laptop
    débil se lleve la run más pesada; `claim_next_job()` ya filtraba
    por telemetría en vivo desde el cambio anterior, solo faltaba
    usarlo en estos jobs).
  - 4 de `SEP_p bin6`/`bin7` (offsets 0,1 en cada uno — el resto de
    esos dos bins ya lo corrió Bryam, mismo manifiesto; SEP_p es mucho
    más rápido que GCR_He en el mismo bin, así que sin requisito de
    RAM/CPU, prioridad 5, la más baja de las tres especies).
  - GCR_H bin6/7 en offsets 2,3,4 ya estaban completos antes de este
    cambio (confirmado por el mismo manifiesto); offsets 0,1 de GCR_H y
    cualquier otra combinación dependen del manifiesto de Eddy, no
    versionado — quedan sin poblar hasta confirmar su estado real.
  - **Sembrado del barrido completo + importación de trabajo local ya
    hecho, herramientas listas (2026-09-13) — dos rondas de corrección
    antes de llegar al diseño final.** Decisión final del equipo: la
    repetición 0 se completa con una mezcla de trabajo local (Bryam,
    Joel) y coordinator (bin6/7), pero **las 4 repeticiones adicionales
    van COMPLETAS a la cola distribuida — las 120 combinaciones en cada
    una, no solo bin6/7**. Para que `replicate_repeats.py` (ver más
    abajo) pueda clonar una plantilla de 120 hacia esas repeticiones, la
    repetición 0 en la base de datos del coordinator necesita las 120
    filas — no solo sembradas, sino con el estado real de cada una
    (`done` para lo ya corrido, `pending` solo para lo que de verdad
    falta).
    - **Primer intento, incorrecto:** `seed_full_sweep.py` sembraba las
      120 combinaciones completas como `pending`, sin contar que **69
      de esas 120 ya están corridas por Bryam localmente** (offsets
      2,3,4, todos los bins salvo GCR_He bin7, versionadas en
      `resultados/organ_sweep_manifest_bryam.csv`) y **el resto de bins
      0-5 (offsets 0,1) los corrió Joel localmente** — a quien se le
      pidió explícitamente NO tocar bin6/7, por eso su trabajo no
      aparece en ningún CSV del repo todavía (no lo ha subido) pero sí
      cuenta como hecho. Sembrar eso como `pending` habría hecho que
      algún voluntario recorriera ese trabajo desde cero.
    - **Corregido con dos piezas, no una:** `seed_full_sweep.py` ganó
      `--bins` (lista de `bin_index`, default: los 8) para poder acotar
      el sembrado inicial si hiciera falta, y **`infra/coordinator/
      import_local_results.py`** (nuevo) marca como `done` el trabajo
      YA HECHO localmente, a partir de un `resultados_organo_sweep_*
      .csv`/`organ_sweep_manifest_*.csv` real (mismo formato que ya sube
      `worker.py`, no uno nuevo) — reusa exactamente el mismo camino que
      seguiría un worker real: `force_claim_job()` (nuevo en `db.py`,
      asigna un `job_id` específico sin pasar por la selección por
      prioridad de `claim_next_job()`) + `mark_running()` +
      `db.record_result()`, con un `worker_id` determinista
      (`local-<label>`, ej. `local-bryam`) registrado como cualquier
      otro worker. Mismas validaciones que `submit_result()` en
      `app.py` (especie/bin/offset/repeticion/n_events deben coincidir
      con el job) y mismo directorio de resultados
      (`results/job_{id}/...`) — ningún esquema paralelo.
      `get_job_by_combo()` (nuevo en `db.py`) busca por la clave natural
      en vez de por `job_id`, ya que un CSV local solo conoce la
      combinación, no el id interno que le tocó al sembrarla.
    - **Flujo real, en orden:** `seed_full_sweep.py --n-events 10000`
      (120 combinaciones completas, todas `pending` salvo las 11 que ya
      estaban en curso) → `import_local_results.py --worker-label
      bryam --results-csv .../resultados_organo_sweep_bryam.csv
      --manifest-csv .../organ_sweep_manifest_bryam.csv` (marca 69 como
      `done`, verificado con el CSV real del repo — segunda corrida
      idempotente, 0 nuevas) → mismo comando con `--worker-label joel`
      cuando suba sus CSV. Lo que queda `pending` tras eso son
      exactamente las combinaciones que de verdad faltan: bin0-6 en
      offsets 0,1 (trabajo de Joel, pendiente de subir) y bin7 en
      offsets 0,1 más GCR_He bin7 en 2,3,4 (las 3 corridas urgentes que
      motivaron esta infraestructura desde el principio) — confirmado
      con una prueba end-to-end que siembra, importa el CSV real de
      Bryam, y verifica el desglose exacto por bin.
    - Prioridad y requisitos mínimos por especie en `seed_full_sweep.py`,
      no un criterio único para las tres — GCR_H/GCR_He: `priority =
      bin_index` (bin7 primero) y `min_ram_gb=8`/`min_cpu_count=4` desde
      `bin_index>=6`, justificado por la curva de costo real medida
      (energía real = MeV/amu × número másico, ver "GCR_He... resultando
      MÁS caro que GCR_H a la misma energía nominal"). **SEP_p,
      prioridad invertida** (`priority = 7 - bin_index`, requisito de
      RAM/CPU en `bin_index<=1`) — el usuario confirmó en producción que
      sus corridas de energía **baja** tardan notablemente más que las
      de energía alta, el patrón opuesto al de GCR_H/GCR_He. Sin una
      tabla de tiempos fina bin-a-bin para SEP_p todavía — esto solo
      captura la dirección del efecto, no la magnitud exacta.
  - **5 repeticiones, herramienta lista (2026-09-13):**
    `infra/coordinator/replicate_repeats.py` (nuevo) lee todos los jobs
    ya sembrados en una repetición base (`repeticion=0` por defecto) y
    crea las mismas combinaciones para `N` repeticiones adicionales,
    preservando `species`/`bin_index`/`offset_x_m`/`n_events`/
    `priority`/`min_ram_gb`/`min_cpu_count` de cada job original —
    `python3 replicate_repeats.py --repeats 4` agrega repeticiones 1-4
    sin tener que volver a escribir cada llamada a `seed_jobs.py` a
    mano. Idempotente por el mismo `UNIQUE(species, bin_index,
    offset_x_m, repeticion)` que ya usa `insert_job()` — correrlo dos
    veces no duplica nada, verificado. No cambia el mecanismo de
    ejecución en sí: el worker ya soportaba pedir una repetición
    específica (`run_organ_sweep.py --repetition-start`, ver más
    arriba) y el identificador de "en qué pasada está" cada job ya
    existe como columna `repeticion`, visible en `GET /api/v1/jobs`. La
    decisión de **cuándo** poblar (esperar a que termine la primera
    pasada completa vs. sembrar ya las 4 adicionales) se deja al
    criterio de quien administre la cola en cada momento — la
    herramienta no fuerza un orden.
- **Primer worker de producción real corriendo** (no una prueba
  descartable): `docker run -d --name geant4-worker-test ...` desde la
  máquina del usuario contra la VM de GCP, ya reclamó y está corriendo
  el primer job real (`GCR_He bin7 offset_x_m=0.0`).
- **`infra/GUIA_VOLUNTARIOS.md`** (nuevo): instrucciones para reclutar
  compañeros que presten CPU — instalar Docker, un solo `docker run`,
  aclara explícitamente que apagar/prender la PC no pierde trabajo
  (`--restart unless-stopped` + reencolado por heartbeat vencido ya
  documentado arriba), cómo pausar (`docker stop`) sin desinstalar nada,
  y cómo limitar recursos si no quieren ceder toda la PC
  (`WORKER_THREADS` para límite lógico de Geant4, `--cpus`/`--memory`
  de Docker para límite duro del contenedor).

**Worker local sin Docker, para compañeros de equipo (2026-09-13):**
`GUIA_VOLUNTARIOS.md` asume que quien presta CPU no tiene el proyecto
instalado (por eso pide instalar Docker). Para quien sí lo tiene —
cualquiera del equipo con `geant4_env` + `ActiveShield_Sim/build` ya
compilados desde antes — eso es trabajo de más: el mismo `worker.py`
corre directo contra el build existente, sin imagen que descargar ni
motor de contenedores que instalar. Documentado en
[`infra/GUIA_WORKER_LOCAL.md`](infra/GUIA_WORKER_LOCAL.md) (nuevo):
`git checkout` de esta misma rama (el worker no vive en `main` todavía),
`conda activate geant4_env`, y `nohup ... & disown` con
`WORKER_THREADS=$(nproc)` para no perder el paralelismo de la tabla de
tiempos ya medida (14 hilos) — sin esto, correr con el default de
`worker.py` (`WORKER_THREADS=1`) haría que una run de varias horas tardara
mucho más de lo esperado. `WORKER_ID_FILE` apunta a `$HOME` en vez del
default pensado para el contenedor Docker (`/var/lib/geant4-worker/`, que
requiere root). Verificado en vivo, no solo escrito: corrido así en la
máquina del usuario contra el coordinator real de GCP, reclamó
automáticamente `GCR_He bin7 offset_x_m=0.0` (la run de mayor prioridad
de la cola) y quedó `running` confirmado por `GET /api/v1/jobs`.
`infra/README.md` distingue ahora las dos vías (Docker para reclutar
gente sin el proyecto instalado, esta guía para el equipo) en vez de
tener un único ejemplo de prueba local contra `127.0.0.1`.

**Cuarta ronda de revisión externa de `install-worker.ps1` (2026-09-13),
4 puntos, todos bugs/gaps reales:**

- **`$InstallScriptCommit` seguía apuntando a `5abd0fc`** pese a que el
  script cambió sustancialmente en la tercera ronda — si alguien lo
  corría vía `irm ... | iex` y necesitaba reiniciar por WSL2, `Save-
  SelfCopy` habría descargado esa versión vieja para continuar tras el
  reinicio, exactamente el escenario que ese pin existe para evitar.
  Corregido: actualizado al SHA completo de 40 caracteres del commit que
  introduce estos mismos fixes (no se puede apuntar al commit anterior,
  porque este cambio modifica el propio archivo).
- **La migración a volumen persistente (tercera ronda) no cubría un
  worker instalado con la versión anterior, bug real de lógica:**
  `Install-WorkerContainer` comparaba solo el config-hash contra la
  etiqueta del contenedor existente — un worker viejo (sin el volumen
  `geant4-worker-data`, de antes de ese fix) podía tener el mismo hash
  igual, así que el instalador lo reportaba como "ya configurado,
  correcto" y nunca migraba nada. Corregido con `Test-
  WorkerVolumeMounted` (revisa `docker inspect --format
  '{{range .Mounts}}...'`), ahora parte de la condición de "no tocar".
  Además, antes de eliminar ese contenedor viejo, `Save-LegacyWorkerId`
  rescata su `worker_id` real (`docker exec ... cat
  /var/lib/geant4-worker/worker_id`) y lo restaura dentro del volumen
  nuevo (`docker run --rm -v geant4-worker-data:/data busybox sh -c
  'echo -n ... > /data/worker_id'`) antes de arrancar el contenedor
  reemplazante — sin esto, la primera actualización de cualquier
  voluntario que ya tuviera un worker corriendo desde antes de la
  tercera ronda le habría hecho perder su identidad/historial en el
  Coordinator igual, el mismo problema que ese fix se propuso resolver.
- **La pausa (`worker.paused`, tercera ronda) solo la respetaba el
  watchdog, no el propio instalador:** si alguien pausaba el worker y
  volvía a correr `install-worker.ps1` (ej. para actualizar), el script
  podía crear/arrancar el contenedor de nuevo sin que nadie lo pidiera,
  deshaciendo la pausa. Corregido: `Install-WorkerContainer` comprueba
  `Test-WorkerPaused` al principio y retorna sin tocar nada si existe
  `worker.paused`; el flujo principal salta `Test-WorkerRegistered`/
  `Register-WatchdogTask` en ese caso (no tendría sentido verificar que
  algo esté corriendo cuando a propósito no se tocó).
- **No existía un comando accesible y con nombre claro para pausar/
  reanudar** — solo `pause-worker.ps1 pause`/`pause-worker.ps1 resume`
  (parámetro posicional, fácil de escribir mal u olvidar) y ninguna
  copia local automática (había que volver a descargarlo del repo cada
  vez). Corregido: nuevo `resume-worker.ps1` (wrapper trivial sobre
  `pause-worker.ps1 resume`, sin duplicar lógica) y `install-worker.ps1`
  ahora descarga ambos a `C:\ProgramData\Geant4Worker\` (mismo `$LogDir`
  ya usado para logs, escribible sin elevación extra una vez creado por
  este instalador que sí corre elevado) — `Save-PauseResumeScripts`,
  llamada desde `Save-SelfCopy`, así que quedan disponibles tanto tras
  una instalación normal como tras una reanudación por reinicio.
  `GUIA_VOLUNTARIOS.md` actualizada con la ruta fija en vez de "descarga
  el script primero".

23 tests siguen pasando (los 4 fixes son PowerShell puro, no tocan
`infra/coordinator`/`infra/worker`).

**Quinta ronda de revisión externa (2026-09-13), 3 problemas reales más
2 mejoras menores — la primera de estas rondas que también toca
`infra/coordinator/app.py`, no solo el instalador:**

- **`Save-LegacyWorkerId` (cuarta ronda) usaba `docker exec`, que
  necesita el contenedor CORRIENDO.** El caso que ese fix existe para
  cubrir es exactamente lo contrario — un contenedor de una instalación
  anterior que el voluntario pudo haber dejado detenido. Corregido:
  `docker cp` en vez de `docker exec` — lee el archivo directo del
  filesystem del contenedor sin necesitar ningún proceso corriendo
  dentro. Verificado que la lógica de reintento/limpieza del archivo
  temporal (`$env:TEMP`) funciona tanto si el contenedor está corriendo
  como detenido.
- **`C:\ProgramData\Geant4Worker` no es necesariamente escribible por un
  usuario normal.** El comentario del fix de pausa (tercera/cuarta
  ronda) asumía que `pause-worker.ps1`/`resume-worker.ps1` (que corren
  SIN elevación — el voluntario no debería necesitar "Run as
  administrator" solo para pausar) podían escribir ahí sin más, pero eso
  depende de las ACL resultantes de cada PC en particular, nunca
  garantizado. Corregido: el archivo de estado (`worker.paused`) se
  movió a `%LOCALAPPDATA%\Geant4Worker\` (perfil del propio usuario,
  siempre escribible sin elevación) — separado del resto (logs,
  self-copy, Scheduled Tasks), que sigue en `%ProgramData%` porque sí
  necesita privilegios de administrador. `install-worker.ps1` corre
  elevado con `RunLevel Highest` conservando el usuario actual (no un
  token de `SYSTEM` distinto, ver `-UserId $env:USERNAME` en
  `Register-ResumeTask`/`Register-WatchdogTask`), así que
  `$env:LOCALAPPDATA` sigue resolviendo al perfil correcto incluso
  dentro del instalador elevado.
- **La comprobación de heartbeat "reciente" (segunda ronda) dependía del
  reloj de la PC voluntaria, bug de diseño de sistema distribuido, no
  solo un detalle.** `Test-WorkerRegistered` parseaba
  `last_heartbeat` (hora del Coordinator) y lo comparaba contra
  `(Get-Date)` de la PC Windows local — un reloj desfasado (adelantado,
  atrasado, zona horaria mal configurada) podía hacer que un worker
  recién conectado pareciera viejo, o uno realmente caído pareciera
  reciente. Corregido en el lado correcto: `GET /api/v1/workers` en
  `app.py` ahora calcula `seconds_since_heartbeat`/`online` con el reloj
  del **servidor** (mismo umbral de 300s que ya usaba
  `count_workers_online()` para `/health`, ahora compartido en vez de
  duplicado con criterios distintos) y los devuelve ya resueltos; el
  instalador solo lee `match.online`, sin ningún cálculo de fecha propio.
  Esto también arregla de una vez el bug de `status` "online" indefinido
  documentado arriba — `/workers` ya no depende de esa columna para
  decidir si un worker está vivo.
- **Mejora menor: comprobación explícita de arquitectura x86-64**
  (`Test-ArchitectureSupported`, vía `$env:PROCESSOR_ARCHITECTURE`) antes
  de descargar nada — tanto el instalador de Docker Desktop
  (`/win/main/amd64/...`) como la imagen del worker son solo
  linux/amd64; una PC Windows ARM64 (ej. Surface Pro X) fallaría a medias
  con un error genérico en vez de un mensaje claro desde el principio.
- **Mejora menor: comprobación de RAM total** (`Test-EnoughRam`, mínimo
  4GB vía `Get-CimInstance Win32_ComputerSystem`) junto a la ya
  existente de espacio en disco — evita que una PC con muy poca RAM
  "instale bien" y falle recién horas después, a mitad de una
  simulación, con un síntoma difícil de diagnosticar para un voluntario.
- **Revisado y descartado explícitamente: reemplazar `busybox` (usado
  para restaurar el `worker_id` rescatado dentro del volumen nuevo) por
  `$WorkerImage`.** El usuario señaló correctamente que `busybox` era
  una imagen adicional sin fijar por digest, una segunda cadena de
  suministro a verificar sin necesidad. Corregido: se usa `$WorkerImage`
  (la misma imagen del worker, ya fijada por SHA256, ya descargada por
  el `docker pull` de unas líneas antes) con `--entrypoint sh` para el
  contenedor descartable que escribe el archivo.

23 tests siguen pasando; agregado y verificado en vivo (servidor real
con `uvicorn`, no solo a nivel de función) que `GET /api/v1/workers`
calcula `online`/`seconds_since_heartbeat` correctamente: un worker con
heartbeat de hace 2h aparece `online: false` pese a que su columna
`status` guardada sigue diciendo `"online"` — confirma que el fix
resuelve la inconsistencia entre `/workers` y `/health` documentada
arriba. No se agregó un test de `pytest` para este cálculo porque
`app.py` no tiene suite propia con `TestClient`/`httpx` (la suite
existente prueba `db.py` directamente y valida los endpoints por HTTP
real en vivo, patrón ya establecido — agregar `httpx` solo para esto no
se justificó).

**Bug real de producción, encontrado por un voluntario (2026-09-13):
`WORKER_THREADS` caía silenciosamente a 1 sin importar la máquina.**
Una captura de pantalla de Docker Desktop de `laptop-fabiola` (16
núcleos) mostró el contenedor al 100% de UN SOLO núcleo — no era una
config que ella hubiera tocado. Causa real: `worker.py` tenía
`WORKER_THREADS = int(os.environ.get("WORKER_THREADS", "1"))` — default
hardcodeado de 1 hilo — e `install-worker.ps1` solo mandaba la variable
`WORKER_THREADS` al `docker run` si el voluntario pasaba
`-WorkerThreads` explícitamente (`if ($WorkerThreads -gt 0)`); sin eso,
la variable nunca llegaba al contenedor y `worker.py` caía a su default
de 1. El docstring del parámetro decía "Default: todos los detectados
por Docker" — nunca fue cierto. Cualquier voluntario que instalara sin
conocer ese flag (la mayoría, ya que ninguna guía lo menciona como
obligatorio) corría Geant4 en 1 solo núcleo sin saberlo, multiplicando
por N el tiempo real de cada corrida.

**Corregido en `worker.py`, no en el instalador de Windows.** Primera
idea descartada: detectar `$env:NUMBER_OF_PROCESSORS` en PowerShell y
pasarlo siempre — rechazada porque eso lee los núcleos del **host**
Windows, no necesariamente los que Docker Desktop le asigna al
contenedor (depende de la configuración de recursos de Docker Desktop,
o de `--cpus` si el voluntario lo usó) — podría pedirle a Geant4 más
hilos de los que el contenedor realmente tiene disponibles. Corregido
en la fuente correcta: `WORKER_THREADS = int(os.environ.get
("WORKER_THREADS") or (os.cpu_count() or 1))` — sin la variable
explícita, usa `os.cpu_count()` leído DESDE DENTRO del contenedor, la
única fuente que ve los CPUs reales asignados ahí. `install-worker.ps1`
solo cambió su docstring (ya no promete algo falso) y un comentario
explicando por qué el fix no vive ahí — el código de paso de la
variable no cambió, sigue mandándola solo cuando el voluntario pide un
límite explícito.

**No aplicado en caliente a los workers ya corriendo — decisión
explícita, con análisis de costo real.** Aplicar el fix a un worker
existente exige recrear su contenedor (nueva imagen con el `worker.py`
corregido), lo que mata cualquier corrida en curso dentro de él — se
reencola sola tras el timeout de heartbeat (6h), pero se pierde el
avance ya hecho. Verificado el estado real antes de decidir: `job 3`
(`bryam-local`, GCR_He bin7) llevaba **330 minutos (5,5h)** corriendo,
`job 2` (`laptop-juan`, GCR_He bin6) **200 min**, `job 37`/`38`
(`fabiola`/`bryam-parrot`, GCR_H bin5) **96 min** — recrear cualquiera
de esos ahora tiraría horas de cómputo real por un fix de rendimiento
que no es urgente. **Decisión: cada voluntario actualiza (vuelve a
correr `install-worker.ps1`, que descarga la imagen nueva) recién
cuando su corrida actual termine sola**, no de inmediato — verificable
sin preguntar mirando `GET /api/v1/jobs` (el job de esa persona pasa de
`running` a `done`) o el propio log del contenedor
(`docker logs -f geant4-worker` deja de mostrar la simulación y pide el
siguiente job). El coordinator no tiene ningún canal para instruir a un
worker remoto a actualizarse — el worker solo hace polling saliente, sin
canal de entrada — así que esto requiere coordinación humana directa
con cada persona, no algo que se automatice desde el servidor.

**Segundo problema real detectado al revisar el fix anterior: `os.cpu_count()`
tampoco es la fuente correcta, no respeta `--cpus`.** El usuario lo señaló
directamente — verificado en vivo: `docker run --cpus=2` sobre un host de 8
núcleos, `os.cpu_count()` seguía reportando 8 dentro del contenedor. Razón:
`--cpus` es una cuota de **tiempo** de CPU vía cgroups (throttling), no una
reducción del número de CPUs que el kernel expone al proceso — Linux no
oculta núcleos por eso. Afecta dos cosas a la vez: el nuevo default de
`WORKER_THREADS` (le pediría a Geant4 más hilos de los que el contenedor
puede sostener bajo cuota) y el propio `cpu_count` que se reporta a
`/workers` (un voluntario usando `-Cpus 2` para ceder menos aparecería con
el total de su máquina, no los 2 reales — engañoso para cualquiera
decidiendo a quién ofrecer un job según `min_cpu_count`). Corregido con
`available_cpu_count()` (nuevo en `worker.py`): lee el límite real del
cgroup (`/sys/fs/cgroup/cpu.max`, cgroups v2; `cfs_quota_us`/
`cfs_period_us`, v1) y solo cae a `os.cpu_count()` si no hay límite
(`"max"`) o no hay cgroup que leer (ej. corriendo sin Docker, ver
`GUIA_WORKER_LOCAL.md`). Usado tanto para `WORKER_THREADS` como para
`cpu_count` en `register()` — `cpu_load_pct()` NO se tocó a propósito
(sigue con `os.cpu_count()`): el load average de Linux siempre refleja
carga sobre todos los núcleos físicos del host sin importar la cuota del
cgroup, así que normalizarlo por el límite del contenedor distorsionaría
esa métrica, no la corregiría. Verificado en vivo con la imagen reconstruida:
sin límite ve 8 (el host completo), con `--cpus=2` ve 2, con `--cpus=3.5`
(fraccional) redondea hacia abajo a 3 — no le pide a Geant4 más hilos de
los que puede sostener. 3 tests siguen pasando.

**Imagen Docker reconstruida con ambos fixes, verificada, aún NO
publicada en GHCR — decisión explícita del usuario, coordinación
pendiente.** `docker build --build-arg BASE_IMAGE=geant4-worker:latest`
(reusa la capa ya compilada de Geant4, no recompila desde cero — segundos,
no minutos) produjo `geant4-worker:threads-fix` local. `install-worker.ps1`
sigue fijado al digest viejo (`db57b43f...`) a propósito: publicar ahora
significaría que la próxima persona en (re)instalar recibe automáticamente
el fix, pero el objetivo es que cada voluntario actualice cuando SU
corrida actual termine, no todos a la vez sin coordinar. Publicar en GHCR
y actualizar el digest en `install-worker.ps1` queda como paso explícito
posterior, no automático.

**Aclaración de identidad, no un error de archivo: Eddy y Joel son la
misma persona (nombre completo Eddy Joel).** El archivo subido a `main`
como `organ_sweep_manifest_eddy.csv`/`resultados_organo_sweep_eddy.csv`
tiene rutas internas (`macro_path`, `log_path`) que dicen
`/home/joel/proyecto_IAC/...` — ambos nombres son correctos, ninguno es
un error de quien lo subió. El `worker_id` usado al importar
(`local-joel`) quedó así por cómo se refirió el usuario a esta persona
en el momento de importar, antes de que se aclarara la equivalencia de
nombres — no se corrigió a `local-eddy` después (decisión explícita del
usuario: no vale la pena re-tocar la VM solo por el nombre interno,
ninguna combinación cambia de estado por esto). Contenido real: 26
combinaciones (`GCR_H` bins 0-6, `GCR_He` bins 0-5, offsets 0,1) —
**ningún SEP_p**, y falta `GCR_He bin6`. Importado con
`import_local_results.py --worker-label joel` en la VM real: 22 marcadas
`done` (las 4 restantes las tomó un worker real del coordinator en el
intervalo entre sembrar e importar, mismo patrón no problemático que con
el trabajo de Bryam — se recorren de nuevo, sin pérdida de nada).
**Estado de la cola tras importar ambos aportes (Bryam + Eddy/Joel): 97 done,
7 running, 16 pending** — lo que queda pendiente es exactamente lo
genuinamente sin cubrir: 11 combinaciones de `SEP_p` (bins 0-5, offsets
0,1 — nadie las ha corrido todavía, ni localmente ni en el coordinator) y
las 5 de `bin7` que motivaron esta infraestructura desde el principio
(`GCR_H` offsets 0,1 + `GCR_He` offsets 2,3,4).

**Investigación adicional antes de dar el fix por cerrado, a pedido del
usuario: ¿el paralelismo real de Geant4 MT es genuino, o `WORKER_THREADS`
correcto sin más termina "solo usando 1 núcleo" igual?** Verificado en
vivo con `top -H` dentro del contenedor durante un `beamOn` real (GCR_He
bin5, 10000 eventos, `--threads 8`): a los 15s (fase de inicialización de
geometría/scoring por hilo) solo el hilo maestro mostraba CPU real, los 7
workers en `sleeping` — parecía confirmar la sospecha. Pero a los 35-40s
(dentro del `beamOn` real), los 8 hilos aparecieron en estado `R`
(running) con CPU repartida entre todos (17,6%-76,5% cada uno, sumando
cerca de los 8 cores completos) — la medición anterior solo había
capturado el arranque, no el trabajo real. **Conclusión: no hay un
segundo bug de serialización oculto — Geant4 MT reparte eventos
correctamente entre hilos una vez que `/run/numberOfThreads` recibe el
valor correcto.** El único problema real seguía siendo el `WORKER_THREADS`
hardcodeado a 1 ya corregido arriba.

**`cpu_score`: benchmark de capacidad de cómputo real, para priorizar A
QUIÉN se asigna el trabajo más caro, no solo si "tiene suficientes
núcleos".** Motivación del usuario: `cpu_count`/`min_cpu_count` (ya
existentes) cuentan núcleos, pero dos máquinas con el mismo conteo pueden
rendir muy distinto (VM compartida vs. laptop dedicada, generación de CPU
distinta) — hace falta medir velocidad real, no solo cantidad. Diseño,
con dos decisiones explícitas del usuario:
- **Multi-proceso, no single-thread:** simula la carga real de una
  corrida de Geant4 (todos los núcleos ocupados a la vez, con la
  contención de caché/memoria y el throttling térmico que eso implica)
  en vez de medir el pico teórico aislado de un solo core — más
  representativo del caso real que se quiere priorizar.
- **`multiprocessing`, no `threading`:** el GIL de Python serializaría
  cualquier intento de paralelismo con hilos en código Python puro — el
  mismo tipo de bug recién corregido en Geant4/`WORKER_THREADS`, ahora
  evitado a propósito en el propio script de medición.

`cpu_score()` (nuevo en `worker.py`): `multiprocessing.Pool` con
`WORKER_THREADS` procesos, cada uno hace 3M iteraciones fijas de
`sqrt(sin(x)²+1)` (elegido por ser aritmética de punto flotante pura,
sin numpy ni dependencias nuevas; fijo en cantidad de trabajo, no en
tiempo, para que el trabajo realizado sea idéntico entre máquinas), mide
el throughput agregado real (`ops_totales / tiempo_wall_clock`) y lo
normaliza contra `_BENCHMARK_REFERENCE_OPS_PER_SEC` (4,77M ops/s — el
throughput de UN proceso, medido, no supuesto, en la máquina donde se
escribió este benchmark) para dar un número relativo comparable entre
workers. **El score agregado NO escala 1:1 con el conteo de núcleos, y
no debería** — la máquina de referencia (8 cores reales) dio un score
agregado de ~5,7, no ~8,0: esa pérdida de eficiencia bajo procesos
compitiendo por caché/scheduler es precisamente lo que este benchmark
existe para capturar, no un error de calibración. Se corre **una sola
vez al arrancar** el worker (no en cada heartbeat — el hardware no
cambia en caliente), antes de `register()`; tarda ~0.9s, medido, no
retrasa el arranque de forma notoria. Nunca bloquea el registro del
worker si falla (`try/except` amplio, cae a `None` con log explícito).

**Verificado con el contenedor real reconstruido, no solo en Python
suelto:** sin límite, 8 threads → score 4,855; con `--cpus=2` (mismo
mecanismo de `available_cpu_count()` ya verificado arriba), 2 threads →
score 2,26 — proporcional y coherente, confirma que el benchmark
respeta la misma cuota de cgroup que ya respeta `WORKER_THREADS`.

**Esquema y asignación, con migración explícita porque la VM real ya
tenía datos.** `cpu_score` (worker) y `min_cpu_score` (job) agregados al
`SCHEMA` de `db.py` — pero `CREATE TABLE IF NOT EXISTS` no altera una
tabla que ya existía antes de este cambio, y la VM real ya tenía 97 jobs
`done` reales que no se podían perder recreando la base. Corregido con
`_MIGRATIONS` (nuevo en `init_db()`): `ALTER TABLE ... ADD COLUMN`
idempotente (maneja `"duplicate column"` para poder llamarse en cada
arranque sin fallar) — verificado con una prueba que simula el esquema
viejo con datos reales, confirma que sobreviven intactos y que correr la
migración dos veces no falla. `claim_next_job()` filtra también por
`min_cpu_score <= cpu_score` del worker, con el mismo criterio ya usado
para RAM/CPU: un worker sin `cpu_score` (versión vieja, o el benchmark
falló) no queda bloqueado — cae a "infinito" (cualquier `min_cpu_score`
pasa), igual que `ram_free_gb` ausente cae a `ram_gb` total.
`seed_jobs.py` gana `--min-cpu-score`; `seed_full_sweep.py` usa
`MIN_CPU_SCORE = 0.5` en los mismos bins ya marcados como caros (bin7
para GCR_H/He, bin0-1 para SEP_p) — deliberadamente bajo/prudente
frente al ~5,7 de la máquina de referencia, sin mediciones reales
todavía de qué score reportan las máquinas del equipo; ajustar una vez
que se observen valores reales vía `GET /api/v1/workers`.
`replicate_repeats.py` copia `min_cpu_score` del job base, igual que ya
hace con `min_ram_gb`/`min_cpu_count`. 3 tests nuevos (26 en total):
worker lento con muchos núcleos no recibe el job, worker rápido sí lo
recibe, worker sin `cpu_score` no queda bloqueado.

**Publicado en GHCR (2026-09-13), digest actualizado en
`install-worker.ps1`.** El usuario reconstruyó la imagen desde su propia
terminal (mismo `Dockerfile.geant4-worker`, `--build-arg
BASE_IMAGE=ghcr.io/.../geant4-worker:latest` para reusar la capa ya
compilada de Geant4) y la publicó con `docker push` — un primer intento
falló con `unauthenticated` (el login de `ghcr.io` guardado en su
terminal había expirado o dejó de ser válido, no relacionado con el
código), resuelto generando un Personal Access Token nuevo (scope
`write:packages`) y volviendo a autenticar. Digest resultante,
verificado accesible públicamente sin autenticación (`docker manifest
inspect`, `linux/amd64`) antes de actualizar el pin:
`sha256:78cce5255237fe3296bcd985fc04c8675ed98d46d07dd20cef7f0ea70f1ac461`
— reemplaza al digest anterior (`db57b43f...`) en `$WorkerImage` de
`install-worker.ps1`. Contiene ambos fixes de esta sesión juntos
(`WORKER_THREADS`/`available_cpu_count()` + `cpu_score`), como se
decidió (una sola publicación coordinada, no dos separadas).

**Migración aplicada en producción (2026-09-13).** Repo actualizado en
la VM (`git fetch`+`reset --hard` a `2a8a8db`), backup de
`coordinator.db` tomado antes por precaución
(`coordinator.db.backup-pre-cpuscore`), y `systemctl restart
geant4-coordinator` corrido — confirmado con `GET /api/v1/workers`
mostrando `cpu_score: null` en los 5 workers reales (ninguno tiene la
imagen nueva todavía, esperado) y `GET /api/v1/health` con
`jobs_done: 108` intacto, sin pérdida de datos.

**Aún no aplicado a ningún worker en producción** — cada voluntario debe
volver a instalar/actualizar recién cuando su corrida actual termine
sola, no de inmediato (ver más abajo el rediseño del instalador que
facilita esto).

**Bug real de pérdida de datos, encontrado en producción (2026-09-13),
corregido de raíz — no solo documentado.** Investigando por qué
`bryam-parrot` (worker local del usuario, sin Docker) aparecía inactivo
pese a tener jobs recientes: `job 38` (`GCR_H bin5 offset1.0`) llevaba
horas en `running` sin heartbeat reciente del todo — el propio log local
(`~/.geant4-worker/worker.log`) mostró la causa exacta: la simulación
**sí terminó exitosamente** (`142 filas de organo encontradas`), pero
justo al momento de subir el resultado la red se cayó
(`Network is unreachable`, duró varios minutos) — `report_result()`
lanzaba `requests.RequestException` sin ningún reintento, `run_job()` lo
capturaba como si la simulación misma hubiera fallado, e intentaba
`report_failure()` (que también fracasó, misma red caída). El CSV real
vivía solo en un `tempfile.TemporaryDirectory()` que se autoborraba al
salir del `with` — **5,5 horas de cómputo real perdidas por un corte de
red transitorio**, sin ningún mecanismo de recuperación. Reencolado
manualmente en la VM (`UPDATE jobs SET status='pending' WHERE
job_id=38`) mientras se corregía el bug de raíz — otro worker lo
reclamó y recompute casi al instante.

**Corregido en dos capas, no solo con más reintentos en memoria** (esos
alcanzan para un corte de segundos, no de varios minutos como el real):
1. `report_result()` (`worker.py`) ahora **persiste el resultado a
   disco ANTES de intentar cualquier subida** (`PENDING_RESULTS_DIR`,
   mismo volumen persistente que `WORKER_ID_FILE` — sobrevive
   `docker rm -f` y reinicios del propio worker) y solo lo borra tras
   una subida confirmada. Reintentos con backoff mientras tanto para el
   caso común (corte breve, se resuelve en segundos).
2. Si los reintentos no alcanzan, el archivo YA está a salvo —
   `retry_pending_results()` (nuevo, llamado al arrancar el worker y en
   cada vuelta ociosa del loop principal) retoma cualquier resultado
   pendiente de una sesión anterior, sin importar cuánto duró el corte
   ni si el propio worker se reinició varias veces entre medio.

**El plazo para insistir es un timestamp ABSOLUTO, no relativo — punto
señalado explícitamente por el usuario, cambia el diseño.** Un
contador de intentos o un backoff relativo (ej. "reintenta 5 veces y
ríndete") no tiene sentido aquí: lo que decide si vale la pena seguir
insistiendo es cuánto tiempo de reloj real pasó desde que el job dejó de
tener heartbeat, comparado contra el mismo `STALE_JOB_TIMEOUT_S` (6h)
que usa el coordinator para reencolar — pasado ese punto, el coordinator
ya le dio el job a otro worker, y seguir insistiendo en subir el
resultado viejo solo arriesgaría pisar uno ya aceptado. `created_at`
(epoch real, `time.time()`) se guarda en `data.json` junto al resultado
persistido; tanto los reintentos en `report_result()` como
`retry_pending_results()` comparan contra `created_at +
stale_job_timeout_s`, no contra un contador — un worker que se reinicia
diez veces durante el mismo corte de red conserva el plazo correcto, ni
más ni menos tiempo del que ya había consumido antes de reiniciarse.

**El umbral real se consulta al coordinator, no se duplica como env var
— decisión explícita del usuario, aprovechando que la imagen nueva
aún no se había publicado.** `GET /api/v1/health` ahora expone
`stale_job_timeout_s` (nuevo campo, lee `db.STALE_JOB_TIMEOUT_S`
directamente); `get_stale_job_timeout_s()` (nuevo en `worker.py`) lo
consulta una sola vez al arrancar, con fallback al mismo default local
(6h) solo si el coordinator no responde ni para esta consulta. Si
alguien cambia `STALE_JOB_TIMEOUT_S` en el coordinator más adelante,
todos los workers lo ven solos, sin tener que reconfigurar una variable
de entorno en cada máquina por separado.

7 tests nuevos en `test_worker.py` (10 en total): reintento con éxito
limpia el archivo persistido; deadline vencido durante el intento en
curso se rinde sin loop infinito, dejando el archivo intacto;
`retry_pending_results()` retoma un resultado de una "sesión anterior"
simulada y lo sube; un resultado cuyo deadline ya venció se descarta sin
ni siquiera intentar la subida (`mock_post.assert_not_called()`). 23
tests del coordinator siguen pasando.

**Instalador de Windows rediseñado como un único script universal
(2026-09-13), a pedido del usuario** — antes de esto, Fabiola y
laptop-juan (que instalaron con el `docker run` manual de
`GUIA_VOLUNTARIOS.md`, no con `install-worker.ps1`) no tenían ninguna
vía simple para recibir la imagen nueva sin volver a escribir el
comando `docker run` completo a mano. En vez de mantener un segundo
script "solo para actualizar", **el mismo `install-worker.ps1` ahora
detecta el caso automáticamente**:
- Si ya existe un contenedor `geant4-worker` en la PC (sin importar si
  lo creó este script o el `docker run` manual — `Get-
  ExistingWorkerEnvValue` lee `docker inspect geant4-worker --format
  '{{json .Config.Env}}'` directo, funciona igual en ambos casos), el
  script asume que Docker/WSL2 ya funcionan (evidenciado por el
  contenedor mismo) y **salta** todas las verificaciones de
  arquitectura/Windows/virtualización/RAM y la instalación de
  WSL2/Docker Desktop — va directo a `Test-CoordinatorReachable` +
  `Install-WorkerContainer`, que ya sabe no recrear el contenedor si el
  hash de config no cambió (mecanismo existente, sin tocar).
- Si no existe ningún contenedor, seguro es la primera instalación:
  corre el flujo completo de siempre, sin cambios.

**Label interactivo con default de usuario, no de máquina** — segundo
pedido del usuario. Antes, sin `-WorkerLabel`, el default silencioso era
`$env:COMPUTERNAME` (poco legible, ej. `DESKTOP-A1B2C3`), y personalizarlo
exigía la sintaxis incómoda de `[scriptblock]::Create(...)` documentada
en `GUIA_VOLUNTARIOS.md`. `Resolve-WorkerLabel` (nuevo) resuelve en este
orden: (1) `-WorkerLabel` explícito siempre gana; (2) si ya existe un
worker en la PC, reusa su label real tal cual, sin preguntar — así
Fabiola/laptop-juan conservan su nombre actual al actualizar sin hacer
nada especial; (3) si es la primera instalación sin label explícito,
`Read-Host` pregunta el nombre, con `$env:USERNAME` (usuario de Windows,
más reconocible que el nombre de máquina) como default si se deja
vacío. **Bug real encontrado probando esto de forma aislada, no en el
diseño en sí:** `$PSBoundParameters` dentro de una función se refiere a
los parámetros de *esa función*, no a los del script que la llama —
`Resolve-WorkerLabel` inicialmente intentaba leerlo directamente y
`-WorkerLabel` explícito nunca ganaba. Corregido pasando `-WasSpecified`
(`$PSBoundParameters.ContainsKey('WorkerLabel')`, evaluado en el script
top-level donde sí es correcto) y `-CurrentValue` como parámetros
explícitos de la función. Verificado con los 3 casos por separado
(explícito gana, reusa el existente, pregunta con default de usuario)
simulando `docker`/`Read-Host` — sin infraestructura de PSScriptAnalyzer
o pytest para PowerShell en este repo, se probó extrayendo y evaluando
las funciones relevantes de forma aislada con `pwsh`.

**`Cpus`/`MemoryLimit` deliberadamente NO se preservan al actualizar**
(decisión explícita del usuario) — si alguien limitó su worker con
`-Cpus 2` la primera vez y actualiza sin volver a pasarlo, vuelve a
"sin límite", igual que hoy. Distinto del label: preservar límites
exigiría leer `HostConfig.NanoCpus`/`Memory` del contenedor (no solo
`Env`), más complejidad para un caso que se decidió no cubrir en esta
ronda.

`GUIA_VOLUNTARIOS.md` actualizada: el link de `irm | iex` sirve ahora
tanto para instalar como para actualizar (mismo comando), y se agregó
una nota explícita para quienes instalaron con Docker manual de que el
instalador de PowerShell también les sirve para actualizar sin repetir
el `docker run` completo.

**Auto-actualización Docker (2026-09-13), revisión antes de publicar:**
El primer diseño se corrigió antes del despliegue: el heartbeat del padre
confirmaba falsamente al candidato, dos procesos podían reclamar jobs con la
misma identidad, el nombre temporal rompía watchdog/pausa y se confundían ID
interno de imagen y digest de manifiesto (pueden coincidir en algún artefacto,
pero no son intercambiables).

La prueba Docker real encontró además que con `--network host` el hostname
puede ser el de la PC: se identifica el contenedor por mountinfo/cgroups, no
por asumir `platform.node()==ID`.

El protocolo vigente exige la etiqueta de imagen
`org.iac.worker-update-protocol=1`, candidato en standby con heartbeat HTTP propio
confirmado mediante nonce/ID en el volumen, commit atómico y `flock` de toda la
vida activa sobre `worker.lock`. El padre entrega el nombre original al hijo,
conserva restart hasta commit (recuperación ante crash), desactiva su restart y
sale limpiamente; el hijo adquiere el lock antes de registro/outbox/jobs. Se
conservan montajes, límites, entorno y labels; configuraciones custom no soportadas
se rechazan para actualización manual. Fallos de preparación limpian el candidato
y restauran al padre; rollback fallido exige intervención antes de volver a pedir
jobs. El journal persistente distingue reinicios anteriores/posteriores al commit.

`WORKER_AUTO_UPDATE=0` sigue siendo el interruptor. `install-worker.ps1` añade
`-WorkerAutoUpdate`, conserva este valor y la imagen ya actualizada salvo selección
explícita de `-WorkerImage`. Se evita degradar un worker al pin antiguo del script.
`set_worker_image.py` exige DB existente explícita al modificar (`--db` o
`COORDINATOR_DB`) y valida el digest completo. El checklist anterior que anunciaba
un digest antes de publicar la imagen era incorrecto: **publicar y validar el
candidato primero, activar el digest deseado después**, usando un canario y API de
prueba. No probar contra producción: la prueba histórica anterior dejó un job
huérfano (`135`, reencolado entonces), precisamente por usar el coordinator real.

Guía vigente, operaciones soportadas, recuperación, límites y comandos de pruebas
en [infra/deploy/README.md](infra/deploy/README.md). El socket mantiene los permisos
amplios aceptados previamente; no se ha activado configuración ni publicado imagen
externa en esta revisión. Las imágenes locales de ensayo no son releases.

**Pendiente, no bloqueante:** publicar la imagen con el fix de
persistencia de resultados (bug del `job 38`) junto con
`WORKER_THREADS`/`cpu_score`/auto-actualización de imagen — **ya NO es
solo una mejora de rendimiento, es una corrección de pérdida de datos
real**, sube la prioridad de esta publicación; coordinar con cada
voluntario que actualice cuando termine su corrida actual (con
auto-actualización activada, esto podría dejar de ser necesario para
publicaciones futuras, pero la primera activación sigue siendo manual);
publicar el resto de imágenes vía un workflow de GitHub Actions en
general (hoy es push manual); reintentar Azure cuando soporte resuelva
el bloqueo de región (opcional, GCP ya cubre la necesidad inmediata); y
confirmar con Eddy/Joel si las 11 combinaciones faltantes de SEP_p y el
`GCR_He bin6` de offsets 0,1 los tiene pendientes de correr/subir, o si
nunca los corrió (para saber si esas 11 de SEP_p deben quedar en la cola
distribuida a propósito, cosa que ya parece ser el caso dado que nadie
las ha corrido en ningún lado).

**Bug real, encontrado 2026-09-13, corregido en la quinta ronda de
revisión (ver más abajo):** `GET /api/v1/workers` mostraba
`status: "online"` de forma indefinida para cualquier worker que alguna
vez mandó un heartbeat exitoso — `touch_heartbeat()`/`upsert_worker()`
solo escriben `status='online'`, nada ponía `'offline'` cuando el
heartbeat dejaba de llegar. Encontrado en vivo: el worker de prueba
(`test-prod-verificacion`, detenido hace más de una hora) seguía
apareciendo `"online"` en `/workers` mientras `/health`'s
`workers_online` (que sí filtra por `last_heartbeat` reciente, ver
`count_workers_online()`) correctamente mostraba 0 — inconsistencia
entre los dos endpoints, no un fallo del conteo en sí. En ese momento se
eliminó el registro a mano (`DELETE FROM workers WHERE worker_id=...`)
en vez de arreglar el bug de raíz. Resuelto de verdad más abajo, como
parte de un fix más grande (el instalador de Windows necesitaba el mismo
cálculo con el reloj del servidor, no solo `/workers`).

**Revisión externa de `install-worker.ps1`/`uninstall-worker.ps1`
(2026-09-13), varios bugs reales corregidos.** El usuario pidió una
revisión de robustez/seguridad antes de distribuir el instalador
masivamente — no solo sintaxis (ya validada con `pwsh`+PSScriptAnalyzer
al escribirlo). Hallazgos reales, todos corregidos:

- **Windows 10/11 build mínimo desactualizado**: el script aceptaba
  build 19041+ (mínimo histórico de WSL2), pero Docker Desktop actual
  exige más (Windows 10 22H2/19045+, Windows 11 23H2/22631+) — una PC
  podía pasar el chequeo del script y aun así fallar en Docker Desktop.
  Corregido: `Test-WindowsVersionSupported` distingue Windows 10/11 y
  usa los mínimos reales.
- **`wsl --version` nunca se comprobaba**: si `wsl --status` ya
  funcionaba, el script asumía "listo" sin revisar si esa instalación
  estaba desactualizada (<2.1.5, causa conocida de fallos de arranque
  de Docker Desktop según la propia documentación de Docker). Corregido:
  `Test-Wsl2Ready` ahora también compara versión y corre `wsl --update`
  si hace falta.
- **`wsl --install` no distinguía fallo real de "pide reinicio"**:
  cualquier código de salida no-éxito se interpretaba como "necesita
  reiniciar", lo que podía reiniciar la PC en bucle ante un fallo real
  (sin red, Windows Update bloqueado, permisos). Corregido: solo el
  exit code `3010` (`ERROR_SUCCESS_REBOOT_REQUIRED`, documentado) se
  trata como reinicio pendiente; cualquier otro lanza error explícito.
  Además, un contador persistido en disco limita a 3 intentos de
  auto-resume antes de rendirse con un mensaje claro.
- **`Restart-Computer -Force` sin avisar**: podía cerrar trabajo no
  guardado del voluntario (documentos, navegador) sin consentimiento.
  Corregido: `Read-Host` pide confirmación explícita antes de reiniciar
  (con opción de posponer — la tarea de resume ya queda programada
  igual), y se advierte guardar el trabajo abierto primero.
- **PATH no se refrescaba tras instalar Docker Desktop**: un PowerShell
  ya abierto antes de la instalación no ve el PATH de máquina
  actualizado, así que `docker info` podía fallar por "comando no
  encontrado" aunque la instalación fuera exitosa. Corregido:
  `Sync-PathWithDockerCli` relee el PATH del registro (máquina+usuario)
  después de instalar.
- **Éxito reportado aunque el worker nunca se conectara**: si
  `Test-WorkerRegistered` devolvía `$false`, el resultado se descartaba
  (`| Out-Null`) y el script igual imprimía "=== Listo. ===". Corregido:
  ahora lanza error y detiene el script si el worker no se confirma
  registrado.
- **Verificación de registro solo por label, no por identidad real**:
  un registro viejo muerto con el mismo `WorkerLabel` (de una
  instalación anterior en la misma PC) podía hacer que la comprobación
  pareciera exitosa sin que el worker nuevo se hubiera conectado de
  verdad. Corregido: se lee el `worker_id` real desde dentro del
  contenedor (`docker exec ... cat /var/lib/geant4-worker/worker_id`) y
  se verifica ese ID específico, con heartbeat reciente.
- **`docker pull` sin reintentos ni distinción de causa**: un timeout de
  red real (`failed to fetch oauth token`, confirmado en vivo con un
  voluntario) daba el mismo error genérico que un problema de permisos
  del paquete (que sí ocurrió antes de hacerlo público, ver más abajo).
  Corregido: `Invoke-DockerPullWithRetry` reintenta 3 veces ante fallos
  de red, pero falla inmediato y con mensaje distinto si detecta
  `unauthorized`/`denied` (problema de permisos, no de red — nada que
  el voluntario pueda arreglar reintentando).
- **Instalador de Docker Desktop sin verificar firma**: se descargaba y
  ejecutaba como administrador confiando solo en HTTPS/DNS. Corregido:
  `Get-AuthenticodeSignature` debe dar `Valid` y el firmante debe
  mencionar "Docker" antes de ejecutar el instalador.
- **Auto-resume apuntaba a la rama mutable**: el código que corre
  después de un reinicio se volvía a descargar de
  `infra/distributed-sweep` tal cual estuviera en ese momento, no
  necesariamente la misma versión que arrancó la instalación. Corregido:
  fijado a un commit concreto (`$InstallScriptCommit`, actualizar a mano
  cuando el script cambie de verdad).
- **Watchdog solo en `AtLogOn`**: si Docker Desktop se caía horas
  después del login, nadie lo notaba hasta el siguiente inicio de
  sesión. Corregido: se agregó un segundo trigger recurrente cada 30
  minutos (además del de login), sin reemplazar `--restart
  unless-stopped` del contenedor (que sigue siendo la primera línea de
  defensa para el contenedor en sí; el watchdog cubre que Docker Desktop
  — el motor — siga arriba).
- **`docker rm -f` incondicional en cada re-ejecución**: volver a correr
  el instalador podía tirar una simulación de horas en curso solo por
  recrear el contenedor sin necesidad. **No resuelto todavía** — el
  script sigue eliminando y recreando siempre; comparar configuración
  antes de recrear queda pendiente (bajo impacto porque
  `--restart unless-stopped` hace que la mayoría de re-ejecuciones sean
  intencionales, no accidentales).
- **Mensaje "no modifica ni borra nada tuyo" engañoso**: el script sí
  instala/configura software (WSL2, Docker Desktop, entradas de
  registro, Scheduled Tasks) — corregido el texto en el propio script y
  en `GUIA_VOLUNTARIOS.md` para decir explícitamente qué se instala,
  aclarando que no accede a documentos personales, en vez de implicar
  que no toca nada del sistema.
- **`-Cpus`/`-MemoryLimit` agregados** (parámetros opcionales, sin
  límite por defecto — decisión del usuario: no sorprender a nadie con
  un límite que no pidió) para pasar `--cpus`/`--memory` a `docker run`,
  cubriendo el hallazgo de "un voluntario puede encontrarse su laptop al
  100%" sin forzarlo por defecto.

**Autenticación por token compartido, implementada en el código pero
NO activada todavía en la VM de producción (decisión explícita, para no
interrumpir la corrida en curso de Bryam sin coordinar antes):**
`app.py` gana un middleware que exige el header `X-Worker-Token` en
todos los endpoints salvo `/health` (y docs), activo solo si
`WORKER_TOKEN` (variable de entorno) no está vacío — vacío por defecto,
mismo comportamiento sin auth que antes, para no romper tests/desarrollo
local. `worker.py` usa una `requests.Session()` compartida que agrega el
header automáticamente si `WORKER_TOKEN` está en su entorno (evita tener
que acordarse de agregarlo a cada una de las 7 llamadas HTTP por
separado). `install-worker.ps1` gana `-WorkerToken` para pasarlo al
`docker run`. **Para activarlo de verdad**: reconstruir y publicar la
imagen en GHCR, coordinar con quien ya tenga workers corriendo para que
agreguen `-e WORKER_TOKEN=...` antes de activar el requisito en el
servidor (si no, sus workers dejan de poder reportar resultados a mitad
de una corrida), y solo entonces configurar `WORKER_TOKEN` en el
systemd de la VM (`cloud-init-coordinator.yaml` sigue sin esa variable
hoy).

**Aclarado (2026-09-13): el paquete GHCR privado y el error de WSL2 de
un voluntario fueron dos problemas independientes, no la misma causa.**
El código de diagnóstico opaco de Docker Desktop que vio un voluntario
ocurría ANTES de llegar a `docker pull` (falla de arranque del motor,
causa real: WSL2) — el paquete privado (confirmado con `curl` sin token:
401; con el flujo real de auth de Docker Registry v2, `ghcr.io/token` +
manifest: sí funcionaba, así que en realidad ya estaba público para
cuando se verificó, el usuario lo había cambiado momentos antes) habría
dado un síntoma distinto (`unauthorized`/`denied` en el pull), no el
error de WSL2. Ambos se corrigieron por separado: visibilidad del
paquete a público (acción del usuario en GitHub) y validación real de
WSL2/version en el script.

**Segunda ronda de revisión externa (2026-09-13), 7 puntos más
corregidos — la primera ronda no era suficiente para distribución
amplia:**

- **Bug crítico: el reinicio pospuesto no detenía el script.**
  `Register-ResumeTask` registraba la tarea de resume y retornaba
  normalmente sin importar la respuesta del usuario a "¿reiniciar
  ahora?" — el flujo principal seguía de inmediato a
  `Install-DockerDesktop` sobre un sistema donde WSL2 todavía no estaba
  operativo (por eso se había llegado ahí). Corregido: `exit 0`
  inmediatamente después de programar la tarea, reinicie el usuario
  ahora o después.
- **Heartbeat "reciente" nunca se verificaba de verdad.**
  `Test-WorkerRegistered` solo comprobaba que el campo `last_heartbeat`
  existiera (`if ($match -and $match.last_heartbeat)`), sin calcular su
  antigüedad — un registro viejo con heartbeat de horas atrás también
  "pasaba". Corregido: se parsea el timestamp ISO8601 (mismo formato de
  `now_iso()` en `db.py`) y se exige que tenga ≤90s de antigüedad
  (margen sobre el intervalo de heartbeat real de 30s).
- **`docker rm -f` incondicional en cada re-ejecución, ya no.** Antes
  recreaba el contenedor sin condición alguna — volver a correr el
  instalador mientras una simulación llevaba horas la mataba
  innecesariamente. Corregido: `Get-DesiredWorkerConfigHash` calcula un
  hash SHA256 de toda la config deseada (imagen, URL, label, threads,
  token, límites), se guarda como label Docker del contenedor
  (`geant4-worker-config-hash`), y solo se recrea si el hash cambió o el
  contenedor no estaba corriendo — si nada cambió, no se toca.
- **`:latest` reemplazado por digest fijo.** Para reproducibilidad
  científica (saber exactamente qué versión del worker produjo cada
  resultado), `-WorkerImage` ahora tiene como default
  `geant4-worker@sha256:db57b43f...` en vez de `:latest` — actualizar
  este hash a mano cuando se publique una imagen nueva de verdad
  (`docker buildx imagetools inspect` para obtenerlo).
- **Detección de versión de WSL dependía del idioma de Windows,
  eliminada.** La versión anterior parseaba la salida de `wsl --version`
  buscando literalmente `"WSL version:"` — en un Windows configurado en
  español (el caso real de los compañeros) esa cadena no aparece igual,
  así que la detección fallaba silenciosamente sin decir nada.
  Corregido: se corre `wsl --update` siempre (es idempotente, no hace
  nada si ya está al día — comportamiento documentado de `wsl.exe`), sin
  parsear ningún texto localizado, y ahora sí se revisa su exit code.
- **`Sync-PathWithDockerCli` solo se llamaba tras instalar Docker
  nuevo.** Si Docker Desktop ya estaba instalado desde antes (el caso de
  los compañeros que ya tenían todo), el script nunca refrescaba el
  PATH de ese proceso de PowerShell — podía seguir sin ver `docker`
  aunque la instalación previa hubiera sido exitosa. Corregido: se
  llama siempre al principio de `Start-DockerAndWait`, no solo dentro de
  `Install-DockerDesktop`.
- **Token sobre HTTP sin cifrar — resuelto con HTTPS real, no
  aplazado.** El usuario señaló correctamente que mandar
  `X-Worker-Token` por HTTP plano es contradictorio (el token viaja
  igual de expuesto que si no existiera). Implementado **Caddy como
  reverse proxy con TLS automático** (Let's Encrypt) delante del
  coordinator: `infra/deploy/setup_https.sh` (nuevo) instala Caddy en la
  VM ya viva sin recrearla ni tocar el servicio `geant4-coordinator`
  (que sigue escuchando en `127.0.0.1:8000` sin cambios) — verificado en
  vivo, sin interrumpir a los workers ya conectados en ese momento
  (`bryam-parrot`, `bryam-local`; `jobs_running` se mantuvo en 3 durante
  todo el proceso). Dominio: `coordinator.vlaboratory.org` (dominio
  propio del usuario en Cloudflare, registro DNS tipo A → IP de la VM,
  proxy de Cloudflare en modo "DNS only" para que la validación HTTP-01
  de Let's Encrypt llegue directo a la VM). Certificado emitido
  correctamente (confirmado en `journalctl -u caddy`:
  `"certificate obtained successfully"`). `install-worker.ps1` y
  `GUIA_VOLUNTARIOS.md` actualizados para usar
  `https://coordinator.vlaboratory.org` como default — el puerto 8000
  HTTP sigue abierto en paralelo (workers ya activos con la IP vieja
  siguen funcionando sin tocar nada) hasta migrar a todos y cerrarlo.
  **El token (`WORKER_TOKEN`) sigue sin activarse en la VM real** —
  ahora que hay HTTPS, activar el token es el siguiente paso lógico,
  pero sigue pendiente de coordinar con quien ya tiene workers corriendo
  (mismo motivo que antes: no interrumpir sus corridas de horas).

**Nota real sobre `gcloud` desde dentro de la propia VM:** el paso de
`setup_https.sh` que intenta crear la regla de firewall (`gcloud compute
firewall-rules create ...`) falla dentro de la VM con "insuficientes
scopes de autenticación" — las VMs de GCE no traen credenciales de
usuario con permisos de gestión de proyecto por defecto. Ese paso está
en el script con manejo de error explícito (no aborta el resto), pero en
la práctica hay que crear la regla de firewall desde una máquina con
`gcloud` autenticado como usuario (no desde la VM misma), como se hizo
aquí.

**Tercera ronda de revisión externa (2026-09-13) — dos fixes de la
segunda ronda se habían quedado a medias, más 3 bugs nuevos reales:**

- **`worker_id` no era persistente de verdad.** Se leía desde
  `/var/lib/geant4-worker/worker_id` **dentro** del contenedor, pero sin
  ningún volumen montado ahí — un `docker rm -f` (que el propio script
  ejecuta cuando la config cambia, ver fix de la ronda anterior) borraba
  ese filesystem junto con el contenedor, y la misma PC volvía a
  aparecer como worker nuevo, sin conservar su identidad ni su historial
  de heartbeats. Corregido: volumen Docker **nombrado**
  (`geant4-worker-data`, no un bind mount a una ruta del host) montado
  en `/var/lib/geant4-worker` — sobrevive a `docker rm -f`, solo se
  pierde si alguien borra el volumen explícitamente.
- **Dos fixes de la ronda anterior no se habían aplicado de verdad,
  detectado al releer el código:** la detección de WSL2 seguía buscando
  el texto literal `"WSL version:"` (dependiente del idioma de Windows,
  exactamente el bug que se creía resuelto) y `Sync-PathWithDockerCli`
  seguía llamándose solo una vez, dentro de `Install-DockerDesktop`, no
  también al principio de `Start-DockerAndWait` como decía el commit
  anterior. Ambos corregidos ahora de verdad — `wsl --update`
  incondicional e idempotente sin parsear texto, con su exit code
  revisado; `Sync-PathWithDockerCli` se llama siempre en
  `Start-DockerAndWait`, cubriendo también a quien ya tenía Docker
  Desktop instalado desde antes.
- **Bug real de UX: el watchdog deshacía un `docker stop` voluntario.**
  El watchdog (cada 30 min) no distinguía "el contenedor está detenido
  porque se cayó" de "el usuario lo detuvo a propósito" — cualquier
  `docker stop geant4-worker` se revertía solo en ≤30 min, haciendo
  falsa la promesa de la guía de poder pausar cuando se quiera.
  Corregido con un archivo de pausa explícito
  (`%ProgramData%\Geant4Worker\worker.paused`) que el watchdog respeta
  sin tocar el contenedor mientras exista. Nuevo
  `infra/deploy/pause-worker.ps1` (`pause`/`resume`) para no exigirle al
  usuario recordar la ruta del archivo ni mezclar `docker stop` directo
  con el watchdog.
- **Verificación de espacio en disco añadida** antes de `docker pull`
  (`Test-EnoughDiskSpace`, mínimo 10GB) — antes, una PC con poco disco
  descubría el problema recién al final de una descarga de ~5GB, en vez
  de fallar rápido con un mensaje claro al principio.
- **`$InstallScriptCommit` verificado y corregido — apuntaba a una
  versión desactualizada del propio script.** El hash fijo para el
  auto-resume post-reinicio (`5abd0fc`, del commit anterior a *todos*
  los fixes de robustez de esta sesión) habría hecho que cualquiera que
  necesitara reiniciar continuara la instalación con una versión rota
  del script — exactamente el escenario que ese pin pretendía evitar.
  Corregido a un SHA completo de 40 caracteres del commit real que
  contiene estos fixes (no un short hash de 7).
- **Riesgo documentado, no resuelto a propósito:** `WorkerToken`, si se
  usa, queda visible en texto plano en los argumentos de la Scheduled
  Task de resume (legible con `schtasks /query /tv` por cualquiera con
  acceso a esa PC). Aceptable mientras `WORKER_TOKEN` no esté activado
  en producción (ver más abajo); si se activa alguna vez, cifrar esto
  con DPAPI/Credential Manager antes de tratarlo como control de acceso
  real entre partes no confiables — decisión explícita del usuario de no
  resolverlo ahora, para no invertir en algo que no está en uso.

## ¿Qué es `WORKER_TOKEN` y por qué no está activado?

Es un secreto compartido simple: si el coordinator arranca con la
variable de entorno `WORKER_TOKEN` puesta, exige que todo request (salvo
`/health`) traiga el header `X-Worker-Token` con ese mismo valor — sin
eso, responde `401`. Sin `WORKER_TOKEN` configurado (el estado actual de
la VM real), esa validación está completamente desactivada: cualquiera
con la URL del coordinator puede registrarse como worker, leer jobs, o
subir resultados, sin ninguna credencial.

**No es necesario activarlo para que el barrido funcione** — el diseño
entero (grano de job, reencolado por heartbeat, resultados con ruta
única por intento) ya asume que los workers son de confianza, no que
hace falta autenticarlos. Es una medida de defensa en caso de que la URL
del coordinator se filtre más allá del equipo (por ejemplo, si queda
indexada por un buscador, o alguien la comparte sin querer) — sin token,
esa persona podría contaminar la cola con resultados falsos o
sobrecargarla con registros basura; con token, no.

**Por qué sigue sin activarse:** activarlo hoy requeriría coordinar con
todos los que ya tienen un worker corriendo (Bryam en sus dos laptops,
más los voluntarios que se sumaron después) para que agreguen
`-e WORKER_TOKEN=...`/`-WorkerToken ...` a su comando **antes** de que el
servidor empiece a exigirlo — si se activa primero en el servidor, todos
esos workers empezarían a fallar con `401` a mitad de corridas que
pueden durar horas. El código ya está listo en `app.py`/`worker.py`/
`install-worker.ps1` desde la segunda ronda de revisión; falta solo la
coordinación operativa, no más desarrollo.

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

### Resultados de `ActiveShield_Sim` versionados en `resultados/` (2026-09-12)

Hasta ahora, los resultados reales del barrido (`organ_sweep_manifest.csv`,
`resultados_organo_sweep.csv`, los agregados) vivían solo dentro de
`build/`, excluido de git — **horas de cómputo real solo en el disco de
esta VM, sin respaldo**. `.gitignore` ya tenía la excepción para esto
desde antes (`!geant4/**/resultados/*.csv`, pensada originalmente para
`GCR_SEP_Sim`, nunca usada todavía por ningún proyecto) — se aplicó por
primera vez aquí, no es una convención nueva. `geant4/ActiveShield_Sim/
resultados/` ya tiene el primer corte real: `organ_sweep_manifest_bryam.csv`,
`resultados_organo_sweep_bryam.csv` (crudo), `resultados_organo_agregados_bryam.csv`,
`resultados_riesgo_estocastico_bryam.csv`/`_repeticiones_bryam.csv`
(agregados, corridos con `aggregate_organ_doses.py`) — sufijo `_bryam`
porque es el aporte de una sola persona, mismo criterio que
`resultados_dosis_sweep_GCR.csv`/`_SEP.csv` de `GCR_SEP_Sim`. **Es un
corte parcial** (falta el bin7 de GCR_He, diferido para cómputo
distribuido, y falta el aporte de Eddy) — se vuelve a subir cuando haya
más. Los archivos `.out` crudos por corrida y los logs se quedan solo en
`build/` (no versionados) — no aportan nada que las CSV ya no tengan
(son la fuente de la que se parsean), y `.out`/`.log` ya están
ignorados globalmente por otro motivo (LaTeX/generales) sin excepción
para `resultados/`.

**Cómo esto se acopla con Docker (en desarrollo, ver `install_compute_node.sh`
más abajo para la instalación mínima que el contenedor usaría):** el
contenedor no necesita saber nada de git — monta un volumen local
(`docker run -v ./salida:/build_output ...`, `run_organ_sweep.py
--build-dir /build_output`) y escribe el mismo formato de CSV de
siempre. Quien recibe esos archivos los copia a
`geant4/ActiveShield_Sim/resultados/resultados_organo_sweep_<nombre>.csv`
y hace commit/push (o PR, si no se le da acceso de escritura directo) —
ningún cambio de esquema, es el mismo archivo que ya produce
`run_organ_sweep.py` hoy. `aggregate_organ_doses.py --results
"resultados/*.csv"` (glob, ya soportado) junta el trabajo de cualquier
número de personas/contenedores en una sola pasada. **Deliberadamente
no se diseñó ningún mecanismo de auto-push con credenciales dentro de
la imagen** — un token de escritura horneado en un contenedor Docker
compartido es un secreto compartido; más seguro que cada quien suba su
propio archivo con su propia cuenta.


## Reglas de trabajo en este repositorio

- **Documentación siempre al día:** cualquier cambio de código, metodología o proceso de equipo debe venir acompañado de la actualización correspondiente en `README.md` y/o `AGENTS.md` en el mismo cambio (no como tarea pendiente para después). Si un commit modifica comportamiento (flags nuevos, cambios de esquema de datos, nuevos pasos de flujo de trabajo), la documentación se actualiza junto con el código, no en un commit aparte ni "cuando haya tiempo".
- **Sin coautoría en commits:** no incluir línea de `Co-Authored-By` (ni ninguna otra atribución de coautoría) en los mensajes de commit de este repositorio, sin importar quién o qué haya generado el cambio.

### Continuación del primer corte distribuido

El worker mantiene heartbeat durante las simulaciones, usa un directorio
independiente por intento y selecciona la repetición exacta mediante el flag
aditivo `run_organ_sweep.py --repetition-start` (default 0, semillas originales).
`WORKER_THREADS` y `WORKER_ONCE` facilitan las pruebas locales. El coordinator
valida la identidad del CSV/manifiesto y guarda entregas en rutas únicas para
que un worker reasignado no sobrescriba resultados aceptados. Los timeouts
alcanzan `failed` cuando agotan los intentos. Las pruebas aisladas usan
`COORDINATOR_DB`, `STALE_JOB_TIMEOUT_S` y `REQUEUE_SWEEP_INTERVAL_S`; no se
reduce el timeout de seis horas por defecto. Flujo y límites en
[infra/README.md](infra/README.md). Elmer, nube y publicación GHCR quedan fuera
del primer corte local acordado.

### Revisión del ciclo de vida del worker (2026-09-13)

`infra/deploy/install-worker.ps1 -Action Uninstall` integra la retirada, con
`-WhatIf` y confirmación; el script separado delega en él. Por defecto conserva
el volumen y resultados pendientes. `-RemoveWorkerData`, `-RemoveDocker`,
`-RemoveWSL` y `-RemoveDockerAutostart` son opciones explícitas; Docker exige
aceptar borrar datos y WSL no desregistra distribuciones. La migración antigua
ahora respalda/restaura TODO `/var/lib/geant4-worker`, no solo `worker_id`.
Corregidos errores de primera instalación, preservación de configuración,
autocopia, pausa/reanudación y provisionadores Bash. Instrucciones, recuperación,
fuentes y límites de validación en [infra/deploy/README.md](infra/deploy/README.md).
No se cambió la lógica de resultados pendientes de `worker.py`. Las pruebas de
retirada son con mocks, sin validación real en Windows ni despliegue de nube.

Validación final de auto-update (2026-09-13): 64 pruebas Python + 2 escenarios
Docker reales aislados aprobados; 16 escenarios PowerShell con mocks y 4 Bash
aprobados. Docker Engine 29.8.0 reveló dos fallos adicionales ya corregidos:
identidad con red host y defaults ausentes/vacíos (`User`). Recursos de ensayo
retirados, sin jobs/API/DB de producción. Canario con digest publicado y pruebas
Windows/Docker Desktop siguen siendo requisitos antes del despliegue general.

### Dashboard de solo lectura del barrido (2026-09-14)

`infra/coordinator/dashboard.html` — página HTML+CSS+JS vanilla que
consulta `/api/v1/health`, `/api/v1/jobs` y `/api/v1/workers` para mostrar
el estado del barrido: tarjetas de resumen, tabla de workers (online,
RAM/CPU, `cpu_score`, digest de imagen) y tabla de jobs con filtros
(status/especie/repetición/worker asignado) y detalle expandible por fila.
Solo lectura, sin ningún botón de escritura. Servida por el propio
coordinator en `GET /dashboard` (`app.py`, agregada a `_PUBLIC_PATHS`).

**Diseño original descartado tras probarlo en vivo:** se planeó como
Artifact de Claude Code con `fetch()` directo al coordinator desde el
navegador del visitante, con `CORSMiddleware` como único cambio de
backend — así se implementó primero, pero la CSP del sandbox donde corre
un Artifact bloquea `fetch()`/XHR hacia cualquier host fuera de un
allowlist fijo de CDNs (cdnjs, jsdelivr, fonts.googleapis); un dominio
propio como `coordinator.vlaboratory.org` nunca pasa esa lista sin
importar las cabeceras CORS del servidor — error real en consola:
"Refused to connect because it violates the document's Content Security
Policy", no un fallo de CORS (que sí funcionaba, verificado). Esa
restricción no se había verificado antes de diseñar sobre esa base.
Corregido sirviendo la página desde el propio coordinator (mismo origen
que la API, sin CORS ni CSP cross-origin de por medio) — el
`CORSMiddleware` ya no cumple ningún propósito así que se quitó (menos
superficie expuesta, dado el riesgo ya aceptado de "sin autenticación de
workers"). Detalle completo en [infra/DASHBOARD_PLAN.md](infra/DASHBOARD_PLAN.md).

### Bug real corregido: repeticiones corriendo en paralelo, no en serie (2026-09-14)

**Encontrado en producción, no en revisión de código:** verificando el
estado real de la cola tras un pedido explícito del usuario ("las
repeticiones deben correr en serie, no en paralelo"), se confirmó que
`claim_next_job()` (`db.py`) nunca había considerado `repeticion` al
elegir el siguiente job — ordenaba solo por `priority DESC, job_id ASC`.
Con las 600 combinaciones ya sembradas (`seed_full_sweep.py` +
`replicate_repeats.py`, 5 repeticiones de 120 cada una), esto significaba
que un worker libre podía tomar cualquier job pendiente de cualquier
repetición, sin importar si las anteriores ya habían terminado. Estado
real confirmado antes del fix: la repetición 0 todavía tenía 8 jobs
`pending`, mientras las repeticiones 1, 2, 3 y 4 ya tenían un job cada
una en `running` — exactamente el comportamiento que no se quería.

**Corregido:** `ORDER BY repeticion ASC, priority DESC, job_id ASC` en
`claim_next_job()` — un worker libre siempre recibe primero un job de la
repetición más baja que todavía tenga trabajo `pending`, sin importar la
prioridad de especie/bin de una repetición más alta. Dentro de la misma
repetición, el orden por prioridad se conserva igual que antes (bin7
antes que bin0, etc., ver la tabla de costos reales más arriba). 2 tests
nuevos en `test_coordinator.py` (29 en total): uno reproduce el bug real
(repetición baja con prioridad baja gana sobre repetición alta con
prioridad alta) y otro confirma que el desempate por prioridad dentro de
una misma repetición sigue funcionando.

**Los 4 jobs que ya estaban `running` fuera de orden se dejan terminar**
(decisión explícita del usuario) — ya llevaban avance real de cómputo;
reencolarlos habría perdido ese trabajo sin necesidad. El fix aplica
hacia adelante: ningún job nuevo se asigna fuera de secuencia desde este
cambio. No se tocó `replicate_repeats.py`/`seed_full_sweep.py` — ninguno
de los dos asume nada sobre el orden de asignación, solo siembran filas.

**Job huérfano encontrado y corregido en la misma revisión (2026-09-14):**
verificando si `bryam-local` podía detenerse tras terminar una corrida,
se encontró `job_id=3` (GCR_He bin7 offset 0.0m, repetición 0) atascado
en `status='running'` desde hacía 10.6h sin ningún avance, con
`last_error="liberado manualmente: worker detenido a proposito"` — texto
que no aparece en ningún script del repo (`grep` explícito, sin
resultados), así que es edición manual directa sobre la DB de producción
que quedó a medias: alguien escribió el `last_error` pero nunca cambió
`status` de vuelta a `pending` ni limpió `claimed_by`. Este tipo de job no
lo detecta `requeue_stale_jobs()` porque ese chequeo mira el heartbeat del
worker asignado, no cuánto avanza el job en sí — y el worker (`bryam-local`)
seguía online y con heartbeat normal (solo trabajando en otro job distinto
mientras tanto). Corregido con un `UPDATE` directo vía `sqlite3` de Python
en la VM (no hay `sqlite3` CLI instalado ahí): `status='pending'`,
`claimed_by=NULL`, `claimed_at=NULL`, conservando `attempt=2` (le queda 1
intento de los 3 antes de `failed`) y reemplazando `last_error` por una
nota que documenta el requeue manual. No hay ningún script administrativo
dedicado a esto en el repo todavía — pendiente si se repite el patrón: un
`release_job.py` explícito sería más seguro que un `UPDATE` ad-hoc cada
vez.

### Dashboard: columna de antigüedad del worker (2026-09-14)

A pedido del usuario, `infra/coordinator/dashboard.html` gana una columna
"Antigüedad" en la tabla de workers, junto a "Último latido" — usa
`registered_at` (ya devuelto por `GET /api/v1/workers`, sin cambios de
backend) formateado como duración relativa (min/h/d). **Nota real sobre
qué mide este campo, no solo cosmética:** `registered_at` se fija en el
primer `INSERT` de esa identidad de worker y el `ON CONFLICT ... DO
UPDATE` de `upsert_worker()` nunca lo sobrescribe — como `worker_id` vive
en el volumen Docker persistente (ver "Worker, endurecido..." más arriba),
sobrevive a reinicios del contenedor. Por eso "Antigüedad" es tiempo desde
el primer registro de esa identidad, **no** tiempo conectado sin
interrupciones — un worker offline hace horas sigue acumulando
antigüedad. Aclarado con un tooltip en la celda (`title="registrado el
... · no descuenta tiempo offline"`) en vez de una columna separada de
"tiempo online acumulado", que exigiría trackear sesiones de
conexión/desconexión — dato que el coordinator no guarda hoy.

### Sexta ronda de revisión externa: `NativeCommandError` bajo PowerShell 5.1 abortaba el instalador (2026-09-13)

**Bug real reportado por un voluntario ("Joel"), con log completo y
diagnóstico propio verificado antes de aplicar el fix.** Con
`$ErrorActionPreference = "Stop"` (global, ver el inicio del script) y
**Windows PowerShell 5.1** (`powershell.exe`, no `pwsh` — lo que de hecho
ejecutan las Scheduled Tasks que este mismo script registra), un comando
nativo que escribe a stderr y se redirige con `*>`/`2>&1` se convierte en
un `NativeCommandError` que **sí** respeta `ErrorActionPreference` — a
diferencia de PowerShell 7.2+, donde ese mismo patrón ya no aborta el
script (cambio de comportamiento documentado oficialmente por Microsoft
entre versiones). El síntoma real visto en el log: `docker info` fallaba
como se esperaba (Docker Desktop recién instalado, el motor todavía no
había arrancado) y esa falla esperada abortaba el instalador ENTERO antes
de llegar a `Start-Process "Docker Desktop.exe"` — el propio chequeo que
debía **detectar** "el motor no está listo todavía" era lo que terminaba
la instalación.

**Corregido exactamente como propuso el usuario, sin cambiar el `Stop`
global** (sigue siendo correcto para errores reales del instalador) —
aislado a los puntos específicos donde se invoca un comando nativo que se
espera que falle durante una comprobación: nueva `Test-
DockerEngineRunning` (aísla `$ErrorActionPreference = "Continue"`
solo alrededor de `docker info *> $null`, restaurando el valor previo en
`finally`), reemplazando las llamadas directas a `docker info` en
`Start-DockerAndWait` (chequeo inicial y dentro del loop de espera),
`Test-LinuxContainersMode` (chequeo previo agregado por consistencia) y
`Uninstall-Worker` (mensaje de error explícito). El watchdog embebido
(generado como script de texto para su propia Scheduled Task, sin scope
compartido con el instalador) recibió su propia copia idéntica de la
función, por el mismo motivo por el que ya duplicaba otra lógica antes.

**Segundo bug encontrado releyendo el propio fix antes de darlo por
completo, no reportado por nadie:** la primera versión de
`Test-DockerEngineRunning` solo tenía `try`/`finally`, sin `catch` — el
`Continue` neutraliza un `NativeCommandError` (error no terminante), pero
una excepción real de PowerShell (terminante) se sigue propagando pese al
`finally`, que solo restaura `$ErrorActionPreference` antes de que la
excepción siga su curso hacia el llamador. Verificado escribiendo un test
que mockea `docker` con `throw` directo (no un `ErrorRecord` de comando
nativo) — sin `catch`, ese caso habría fallado. Corregido agregando
`catch { return $false }` a ambas copias de la función (la real y la del
watchdog embebido): la función pasa a ser una barrera total, nunca
propaga ningún tipo de error hacia quien la llama.

**Test nuevo en `test_worker_lifecycle.ps1`**, agregado a la lista de
funciones extraídas del AST (`Test-DockerEngineRunning` faltaba ahí y
rompió el test existente al empezar a llamarse desde `Uninstall-Worker`
en una ronda anterior — corregido agregándola a esa lista): dos
escenarios bajo `$ErrorActionPreference = 'Stop'` — un `NativeCommandError`
real simulado con `$PSCmdlet.WriteError()` + `$LASTEXITCODE=1` (el caso
que motivó todo el fix) y una excepción de PowerShell genuina simulada
con `throw` (el segundo bug, el que exigía `catch`) — ambos deben
devolver `$false` sin propagar el error ni dejar `$ErrorActionPreference`
alterado. 17 escenarios de ciclo de vida pasan en total (antes 16).

**Tercer bug encontrado por el usuario releyendo GitHub, el mismo patrón
ya visto varias veces en esta sección — `$InstallScriptCommit` quedó
desactualizado otra vez, en el propio commit que lo introducía la vez
anterior.** El commit que aplicó el fix de `Test-DockerEngineRunning`
(ver arriba) dejó el pin apuntando todavía a `38e5ee6` — una versión
**anterior** de 874 líneas, sin `Test-DockerEngineRunning` (confirmado
leyendo ese commit exacto). El riesgo es el mismo que motivó el pin en
primer lugar, pero en sentido inverso: un voluntario que corra el script
**actual** vía `irm ... | iex` (sin archivo local, así que `Save-SelfCopy`
no tiene nada propio que preservar) y necesite reiniciar por WSL2
continuaría tras el reboot descargando `$InstallScriptUrl` apuntando al
commit viejo — un **downgrade involuntario** a la versión sin el fix de
`NativeCommandError`, justo a mitad de la instalación que ese fix existe
para no abortar. Alcance real: `Save-PauseResumeScripts` deriva su
`$baseUrl` del mismo `$InstallScriptCommit` (línea con
`https://raw.githubusercontent.com/.../$InstallScriptCommit/infra/deploy`),
así que `pause-worker.ps1`/`resume-worker.ps1` quedaban expuestos al
mismo problema, sin necesitar un fix aparte — un solo pin cubre los tres
archivos.

**Corregido:** `$InstallScriptCommit` actualizado al SHA completo del
commit que introduce `Test-DockerEngineRunning`
(`26507d0f175528a6e63834b69bd490abcc796669`, ya en el remoto antes de
este cambio, así que apuntar a él no es circular). Verificado en vivo,
no solo leído: `curl` a
`raw.githubusercontent.com/.../26507d0f.../infra/deploy/install-worker.ps1`
devuelve el archivo real con `Test-DockerEngineRunning` presente (2
copias, la real y la del watchdog embebido) — confirma que el pin
resuelve a la versión correcta antes de dejarlo así. Este archivo en sí
todavía no puede autorreferenciarse (un commit no puede apuntar a su
propio SHA antes de existir) — quien lea este commit y note que el pin
ya no es el HEAD más reciente debe confirmar primero, con el mismo
`curl`, que el commit señalado sigue conteniendo `Test-
DockerEngineRunning` antes de asumir que hace falta otra actualización.

**Cuarto bug, señalado por el usuario mientras revisaba el fix anterior:
el mismo patrón de `NativeCommandError` bajo `Stop` no estaba aislado
solo en `docker info`, sino repetido en ~10 funciones más.** El usuario
preguntó puntualmente por `Invoke-DockerPullWithRetry` (`docker pull
... 2>&1` bajo `Stop`, capturando `$LASTEXITCODE` para decidir si
reintentar) — verificado en vivo con el mismo tipo de `ErrorRecord` que
simula un `NativeCommandError` real: `$output = docker pull ... 2>&1`
bajo `Stop` también aborta el script antes de que la lógica de
reintento pueda actuar, exactamente el mismo bug. Auditando el resto del
archivo con el mismo criterio (comando nativo + inspección posterior de
`$LASTEXITCODE`/salida, sin `try/catch` propio, bajo el `Stop` global)
aparecieron más de 10 sitios vulnerables: `Install-Wsl2` (`wsl
--install`), `Test-LinuxContainersMode` (`docker info --format`),
`Invoke-DockerPullWithRetry` (`docker pull`), `Get-ExistingWorkerEnvValue`/
`Test-WorkerVolumeMounted`/`Test-DockerSockMounted` (`docker inspect`),
`Save-LegacyWorkerData` (`docker stop`/`docker cp`), `Install-
WorkerContainer` (`docker ps`/`inspect`/`rm`/`volume create`/`create`/
`cp`/`run`/`logs`, la función con más sitios), `Uninstall-Worker` (`docker
ps`/`stop`/`rm`/`volume ls`/`volume rm`), `Test-WorkerRegistered` (`docker
exec`), y la detección `$isUpdate` a nivel de script junto con el bloque
`if ($isUpdate) {...}` que preserva la config existente (dos `docker
inspect` más). Ninguno de estos tenía su propio `try/catch` local — todos
dependían solo de que el comando nativo terminara con un exit code
distinto de 0, sin contar con que un stderr real bajo PS 5.1 los
convertiría en excepción terminante primero.

**Corregido con un helper único, `Invoke-NativeCommand`** (reemplaza el
`try/finally` que antes vivía solo dentro de `Test-DockerEngineRunning`,
ahora esa función es un one-liner que lo llama) en vez de repetir el
mismo aislamiento de `$ErrorActionPreference` en cada función — recibe
un scriptblock con la invocación nativa exacta (preservando la
redirección de cada call site, `2>&1`/`2>$null`/`*> $null` según lo que
ya tenía) y devuelve `{Output, ExitCode}` ya resueltos bajo `Continue`,
con `catch` propio para una excepción de PowerShell genuina (mismo
segundo bug ya corregido antes en `Test-DockerEngineRunning`). Cada uno
de los ~15 call sites vulnerables (contando cada llamada `docker`/`wsl`
dentro de las funciones listadas arriba) se reemplazó por una invocación
a este helper. Los que ya estaban dentro de su propio `try/catch`
(`Test-Wsl2Ready`, ambas llamadas a `wsl`) y los que corren en el
watchdog embebido bajo `SilentlyContinue` (ya inmune por diseño, no por
accidente) se dejaron sin tocar — no lo necesitan.

**Test actualizado, no solo el código de producción:** `Invoke-
NativeCommand` agregado a la lista de funciones extraídas del AST en
`test_worker_lifecycle.ps1` (el bloque `if ($isUpdate) {...}` que el test
ya extraía y ejecutaba vía `Invoke-Expression` ahora llama a este helper
internamente, así que sin agregarlo el test habría fallado con "función
no encontrada" — mismo patrón de bug ya visto antes en esta ronda con
`Test-DockerEngineRunning`, corregido esta vez de forma preventiva antes
de ejecutar el test, no después de que fallara). El mock de `docker`
del test para el escenario `NativeCommandError` (`$PSCmdlet.WriteError()`)
imprimía ruido en consola (texto rojo del `ErrorRecord`) al pasar ahora
por la indirección adicional de `& $ScriptBlock` dentro de
`Invoke-NativeCommand` — investigado y confirmado que es un artefacto
cosmético exclusivo del mock (`WriteError()` emite al stream de error de
PowerShell, que `*> $null` no intercepta de la misma forma que
intercepta el stderr real de un proceso nativo; verificado por separado
con un comando nativo real fallando bajo el mismo helper: cero ruido).
Corregido silenciando ese stream solo en la línea del test que invoca el
escenario (`2>$null` en la llamada, no dentro del mock) — no es un
síntoma de ningún problema en el código real.

**`$InstallScriptCommit` pendiente de actualizar una vez más tras este
commit** — mismo patrón ya documentado dos veces en esta sección: el pin
debe apuntar al commit que introduce este fix, no a uno anterior. Se
actualiza en un commit separado inmediatamente después de este, con el
SHA real ya confirmado (no un supuesto) antes de fijarlo, siguiendo
exactamente el procedimiento de verificación (`curl` al raw URL del SHA
elegido, confirmar que `Invoke-NativeCommand` aparece) ya usado las dos
veces anteriores.

**Warning de PSScriptAnalyzer detectado en VSCode: `Uninstall-Worker`
llama `ShouldProcess` sin declarar `SupportsShouldProcess` propio.** La
función usa `$PSCmdlet.ShouldProcess(...)` (para el `-WhatIf`/`-Confirm`
de `-Action Uninstall`) pero nunca tuvo su propio
`[CmdletBinding(SupportsShouldProcess)]` — dependía de heredar `$PSCmdlet`
del `CmdletBinding(SupportsShouldProcess)` a nivel de script (linea 111).
**Verificado en un script de prueba aislado, no asumido, que esa
herencia SI funciona en tiempo de ejecucion** (una funcion sin
`CmdletBinding` propia, llamada desde el scope de nivel superior de un
script que si lo tiene, hereda su `$PSCmdlet` correctamente — confirmado
con y sin `-WhatIf`) — no era un bug funcional, la instalacion real
nunca estuvo en riesgo. Pero `PSScriptAnalyzer` analiza cada funcion de
forma aislada y no puede rastrear esa herencia entre scopes, de ahi el
falso positivo. Corregido agregando `[CmdletBinding(SupportsShouldProcess)]`
+ `param()` directo a `Uninstall-Worker` (mejor practica de todos modos:
una funcion que usa `ShouldProcess` deberia declararlo explicitamente, no
depender de heredarlo) — verificado que el comportamiento real no cambia
(mismo script de prueba, con la funcion interna declarando su propio
`CmdletBinding`: `-WhatIf` y la ejecucion normal dan resultados
identicos) y que las variables de script (`$RemoveDocker`,
`$RemoveWorkerData`, etc., leidas por nombre sin ser parametros) siguen
resolviendo bien con `param()` vacio. Confirmado con `Invoke-ScriptAnalyzer`
real (no solo lectura manual): 12 hallazgos totales antes, 11 despues,
exactamente el `PSShouldProcess` desaparecido y ningun hallazgo nuevo.
17 escenarios de `test_worker_lifecycle.ps1` (que ya ejercitan `-WhatIf`/
`-Confirm:$false` sobre esta funcion) siguen pasando sin cambios.

### Estimación de duración por `cpu_score`, y timeout de reencolado dinámico (2026-09-14)

**Motivación, pregunta directa del usuario:** con `cpu_score` ya expuesto
por cada worker desde antes, ¿se puede usar para estimar cuánto debería
tardar un job en un worker dado, y usar esa estimación como base para
los timeouts de reencolado en vez de un único `STALE_JOB_TIMEOUT_S` fijo
de 6h para cualquier combinación especie/bin/worker? El usuario confirmó
un dato clave antes de construirlo: la tabla de tiempos por bin ya
documentada más arriba ("Piloto de 8 bins") se midió siempre con el
mismo `WORKER_THREADS` en `bryam-local`, así que su `cpu_score` actual
(4.461, confirmado vía `GET /api/v1/workers`) es una base válida para
escalar — no hace falta corregir por número de núcleos aparte, porque
`cpu_score` ya se mide bajo el mismo régimen de paralelismo real que
Geant4 MT usa en producción (comentario propio de `cpu_score()` en
`worker.py`: "bajo carga sostenida con todos los núcleos ocupados a la
vez").

**Todo esto vive en el coordinator (`infra/coordinator/db.py`/`app.py`),
no en el worker** — no requiere publicar ninguna imagen Docker nueva; se
despliega con el mismo procedimiento de siempre (`git reset --hard` +
`systemctl restart geant4-coordinator`). El `cpu_score` que usa ya lo
reportan los workers actuales sin cambios. **Nota real encontrada al
verificar antes de implementar:** de los 7 workers registrados en
producción hoy, solo `bryam-local` tiene `cpu_score` real — los demás
(`laptop-juan`, `bryam-parrot`, `laptop-fabiola`, `laptop-liz`) tienen
`cpu_score: null` (versión de imagen anterior a ese benchmark, o worker
local sin Docker). El diseño trata esto como caso explícito de
"sin estimación disponible", no como error — ver abajo.

**`REFERENCE_TIMINGS_S`** (`db.py`, nuevo): tabla `(especie, bin_index) →
segundos`, derivada de datos REALES —
`geant4/ActiveShield_Sim/resultados/organ_sweep_manifest_bryam.csv`,
promedio de 3 repeticiones por combinación (offsets 2/3/4) — no de los
números sueltos en prosa de la sección "Piloto de 8 bins" (que solo
cubría GCR_H, posición 0). Cubre los 8 bins de GCR_H y SEP_p, y 7 de 8
de GCR_He. **GCR_He bin7 es la única extrapolación, marcada como tal en
el propio código:** `bryam-local` nunca lo corrió (ver "bin7 de GCR_He
se salta por ahora" más arriba) — se aplicó el mismo factor de
crecimiento bin6→bin7 medido en GCR_H (×2.565) sobre el bin6 real de
GCR_He (7321.2s), dando ~18780s (~5.2h), coherente con la proyección de
"5-6h por corrida" ya documentada a partir del mismo patrón.

**`estimate_job_duration_s(species, bin_index, worker_cpu_score)`**
(`db.py`, nuevo): `referencia × (REFERENCE_CPU_SCORE / cpu_score_worker)`.
Devuelve `None` explícitamente (nunca cero, nunca una excepción) si no
hay referencia para esa combinación o el worker no tiene `cpu_score` —
mismo patrón que `claim_next_job()` ya usa para `min_cpu_score` ausente.

**`requeue_stale_jobs()` reescrito para timeout por-job, no un cutoff
único para toda la tabla:** antes, una sola resta de tiempo (`time.time()
- STALE_JOB_TIMEOUT_S`) se aplicaba a todos los jobs `claimed`/`running`
en el `WHERE` de SQL. Ahora ese valor fijo sigue siendo el **piso
mínimo** (nunca se reencola antes de eso, protección base sin cambios),
pero si hay una estimación válida para esa combinación especie/bin en
el worker asignado, el timeout real usado es
`max(STALE_JOB_TIMEOUT_S, estimación × ESTIMATE_SAFETY_FACTOR)` —
`ESTIMATE_SAFETY_FACTOR = 2.5`, deliberadamente generoso porque
`cpu_score` es un benchmark de un solo momento al arrancar el worker, no
captura throttling térmico sostenido ni contención real de un host
compartido, y la propia tabla de referencia ya tiene hasta ~15% de
dispersión entre repeticiones en la misma máquina/bin. Se trae a Python
el set de candidatos bajo el cutoff más laxo posible (el piso fijo) y se
filtra fila por fila con su propio timeout — más simple y correcto que
expresar un timeout dinámico por fila dentro del `WHERE` de SQL. Un
worker sin `cpu_score` (o una combinación sin referencia) cae
automáticamente al piso fijo de siempre, sin ningún caso especial en el
llamador.

**`GET /api/v1/jobs` gana `estimated_duration_s`** (`app.py`): `None`
para jobs `pending`/`done`/`failed` (no aplica) o si no hay estimación
posible; calculado a partir del `cpu_score` del worker que tiene
asignado el job ahora mismo. **Dashboard** (`dashboard.html`): nuevo
campo "Tiempo estimado" en el detalle expandible de cada job, con
tooltip explicando la base del cálculo — nuevo formateador `fmtSpan()`
(segundos → s/min/h), distinto de `fmtAgo()`/`fmtDuration()` ya
existentes (que formatean "hace cuánto" desde un timestamp, no una
duración absoluta en segundos).

**6 tests nuevos en `test_coordinator.py` (35 en total):** escalado
correcto por `cpu_score` (mitad de score → el doble de tiempo estimado),
`None` sin `cpu_score` o sin referencia para la combinación, un job caro
(bin7) en un worker con heartbeat vencido más allá del piso fijo pero
DENTRO del timeout estimado con margen no se reencola, un job barato
(bin0) con heartbeat apenas vencido sigue protegido por el piso fijo
aunque la estimación sola sea más corta, y un worker sin `cpu_score`
cae al comportamiento de siempre (piso fijo). Verificado también en
vivo (servidor local real, no solo a nivel de función): un worker
registrado con el mismo `cpu_score` de referencia reclamó un job GCR_H
bin7 y `GET /api/v1/jobs` devolvió `estimated_duration_s: 4669.7` —
exactamente el valor de la tabla, sin escalar, como se espera cuando el
score coincide con la referencia.

**Bug de logs corregido de paso, encontrado investigando la primera
pregunta del usuario (subida tardía tras reasignación) mientras se
diseñaba esto:** verificado con lectura de código, no solo supuesto, que
el flujo real para "worker A se desconecta con un job en curso, el
coordinator lo reasigna a worker B, B termina primero, y luego A
recupera conexión e intenta subir su resultado viejo" **no pierde datos**
(el resultado de A se persiste en `PENDING_RESULTS_DIR` antes de
cualquier intento de red, y `record_result()` en `db.py` ya rechaza con
`409` una subida cuyo `claimed_by` no coincide, protegido por un test
existente) — pero el log intermedio era confuso: `report_result()`
(`worker.py`) solo capturaba `ConnectionError`/`Timeout`, no
`requests.HTTPError`, así que un `409` se propagaba sin capturar hasta
`run_job()`, que lo trataba como si la SIMULACIÓN hubiera fallado y
llamaba a `report_failure()` — que a su vez también era rechazado (A ya
no es dueño del job) y ese segundo fallo se tragaba en silencio con solo
un `print`. El archivo con el resultado real de A quedaba en
`PENDING_RESULTS_DIR` sin borrarse, y se descartaba recién en la
siguiente vuelta ociosa del loop vía `retry_pending_results()` (que sí
tenía el manejo correcto desde antes) — sin pérdida de datos, pero con
un log que decía "no se pudo reportar fallo al coordinator" en vez de la
causa real. **Corregido:** `except requests.HTTPError` agregado a
`report_result()`, mismo tratamiento que ya tenía `retry_pending_results()`
para este caso (descartar el pending file con un log que dice la causa
real: "probablemente otro worker ya lo completó"). 1 test nuevo en
`test_worker.py` (31 en total) que reproduce el `409` exacto y confirma
que el archivo se descarta sin reintentar. **Este fix SÍ vive en
`worker.py`, así que requiere publicar una imagen Docker nueva para que
los workers Docker existentes lo reciban** (decisión explícita del
usuario de incluirlo en este cambio de todos modos, sabiendo eso) — los
workers Docker actuales no lo notan hasta que les ocurra este caso raro
específico, y seguirán funcionando correctamente (sin pérdida de datos)
mientras tanto, solo con el log confuso de antes.

### Dashboard: tiempo en curso y duración real de cada job (2026-09-14)

**Dos pedidos seguidos del usuario tras ver el tiempo estimado:** (1)
"solo ver el tiempo estimado no es muy útil, también serviría ver cuánto
tiempo lleva corriendo el job en específico" — resuelto con
`claimed_at`, ya devuelto por `GET /api/v1/jobs` sin ningún cambio de
backend, solo cálculo en el dashboard; (2) "¿también sería útil
almacenar el tiempo de runs en los datos de los jobs completados?" — al
revisar el código para responder, se confirmó que **ese dato ya se
guardaba desde antes** (`results.duration_s`, insertado por cada
`record_result()` exitoso desde que existe la tabla) pero **ningún
endpoint lo había expuesto nunca** — no hacía falta agregar
almacenamiento nuevo, solo exponer lo que ya existía.

**`list_jobs()` (`db.py`) gana `actual_duration_s`** vía subquery
correlacionada (`SELECT ... FROM results WHERE job_id=j.job_id ORDER BY
submitted_at DESC LIMIT 1`) — el `duration_s` de la subida MÁS RECIENTE
de ese job, no la primera: un job con reintentos tiene una fila en
`results` por cada intento (exitoso o no, ver `record_result()`), y la
más reciente es siempre la que corresponde al estado actual del job
(record_result()/record_failure() son lo último que corre en cada
intento). `None` para un job que nunca completó un intento
(pending/failed sin ninguna subida). `row_to_dict()` en `app.py` ya
pasa cualquier columna del `SELECT` sin cambios — no hizo falta tocar
`app.py` para exponer el campo en `GET /api/v1/jobs`.

**Dashboard, columna "Duración" (antes "En curso"), ampliada para
cubrir ambos casos, no solo uno nuevo al lado del otro:**
`runningCellHtml()` ahora resuelve tres estados — job en curso (tiempo
transcurrido desde `claimed_at`, comparado contra `estimated_duration_s`
con color de aviso si supera el 80%/100% del estimado, ya implementado
antes), job `done` (`actual_duration_s` real, etiquetado "real" para no
confundirlo con una estimación), o ninguno de los dos (`—`). Mismo
patrón agregado al detalle expandible ("Corriendo desde" / "Tiempo
estimado" / "Duración real" juntos, para comparar de un vistazo).

**2 tests nuevos en `test_coordinator.py` (37 en total):** un job con un
intento fallido seguido de uno exitoso expone el `duration_s` del
intento exitoso (más reciente), no el del fallido; un job sin ningún
resultado subido da `None`. Verificado también en vivo (servidor local
real): un job `done` sembrado con `duration_s=91.3` devuelve
`actual_duration_s: 91.3` y `estimated_duration_s: null` en la misma
respuesta que un job `claimed` en paralelo muestra lo inverso —
confirma que ambos campos se excluyen mutuamente como se diseñó (uno
aplica a jobs con worker activo, el otro a jobs ya completados).

**Mejora futura, no implementada ahora, mencionada solo como
observación:** con `actual_duration_s` ahora expuesto, una vez que se
acumulen suficientes duraciones reales de producción (más allá del
manifiesto de `bryam-local` usado para `REFERENCE_TIMINGS_S`),
`REFERENCE_TIMINGS_S` podría recalcularse a partir de datos reales de
múltiples workers en vez de una sola máquina — no es parte de este
cambio, solo queda anotado como posibilidad habilitada por este mismo
dato.

### Progreso en vivo de `docker pull` y pasos numerados de la instalación (2026-09-14)

**Pedido del usuario: la descarga de la imagen (~5GB, lo que más tarda
de toda la instalación y lo que más depende de la conexión del
voluntario) no mostraba ninguna señal de avance hasta terminar del
todo.** `Invoke-DockerPullWithRetry` capturaba toda la salida de `docker
pull` en una variable y solo la volcaba al log línea por línea DESPUÉS
de que el comando completo terminara — un voluntario con internet lento
veía el instalador "colgado" varios minutos sin ninguna pista de que
seguía trabajando.

**Investigado antes de implementar: `docker pull` no tiene una bandera
de progreso estructurado (`--format json` no existe para este
subcomando)** — confirmado leyendo `docker pull --help`. La barra de
porcentaje que se ve en una terminal interactiva normal viene de que
Docker reescribe la misma línea con retornos de carro (`\r`), algo que
no sobrevive intacto al pasar por el pipeline de objetos de PowerShell.
La alternativa de leer el stream JSON crudo del Docker Engine API
(confirmado por separado que sí trae `progressDetail.current/total` por
capa, vía `curl --unix-socket`) se descartó para este script porque
exigiría un cliente HTTP contra el socket/named pipe en PowerShell —
mucho más complejo que lo que amerita esta mejora, y sin ganancia real
sobre la opción elegida.

**Corregido con `Invoke-NativeCommand { docker pull ... 2>&1 |
ForEach-Object { Write-InstallLog "  $_"; $_ } }`**: cada línea que
Docker emite (una por evento real: "Pulling fs layer", "Downloading",
"Download complete", "Pull complete" por capa) se loguea EN VIVO al
llegar, no se acumula para el final — verificado en vivo con una imagen
real (`node:20-slim`, ~190MB) que las líneas efectivamente llegan
escalonadas en el tiempo (t=2.8s, t=4.3s, ... t=20.8s), no todas de
golpe al terminar. No es una barra de porcentaje agregada (decisión
explícita, ver pregunta al usuario) — es el progreso real y ya
estructurado que Docker genera por capa, sin inventar un parser de texto
frágil propio. `$output` se sigue poblando igual que antes (el
`ForEach-Object` re-emite cada línea con `$_` al final del bloque)
para que la detección de `unauticated`/`denied` y la lógica de
reintento de más abajo no cambien. Verificado end-to-end con las tres
rutas reales de la función (éxito, reintento transitorio con imagen
inexistente, error de permisos con `docker` mockeado): las tres siguen
funcionando igual que antes de este cambio, solo que ahora con log en
vivo en vez de solo al final.

**Progreso TOTAL de la instalación, no solo de la descarga:** nuevo
`Write-InstallStep` (junto a `Write-InstallLog`) antepone `[Paso N/M]`
a los hitos principales del flujo — 8 pasos en una instalación nueva
(verificar requisitos, WSL2, Docker Desktop, modo Linux containers,
Coordinator alcanzable, imagen+contenedor, worker registrado, watchdog),
3 en una actualización (Coordinator alcanzable, imagen+contenedor,
worker registrado — se salta WSL2/Docker Desktop porque `$isUpdate` ya
implica que funcionan). `$script:TotalInstallSteps` se fija una vez al
principio de cada rama (`if (-not $isUpdate) {...} else {...}`) porque
tienen conteos distintos; `Register-WatchdogTask` corre en ambos flujos
pero solo se anuncia como paso numerado en la instalación nueva (no
cuenta para el total de 3 de la actualización).

**Segundo tema, no relacionado con progreso — corregido a partir de una
revisión externa detallada del propio `$InstallScriptCommit`:** un
usuario señaló con precisión el problema real de fondo: un archivo no
puede contener el SHA del commit que lo contiene a sí mismo (cambiar el
hash cambia el contenido → cambia el commit → invalida el hash recién
puesto — ciclo sin punto fijo). Confirmado exactamente como lo describió:
el pin del commit `23ab311...` en sí mismo decía `InstallScriptCommit =
"1e38a334..."` (el commit ANTERIOR, no el propio) — inevitable con este
diseño, no un descuido corregible con más cuidado. El propio usuario
notó que esto ya no era grave para el caso real que importa (reinicio
inmediato durante una instalación en curso): el commit anterior señalado
YA contenía el fix relevante en cada caso verificado hasta ahora, así
que un voluntario reanudando tras un reinicio nunca terminó recibiendo
código roto — el diseño cumple su propósito práctico pese a la
imposibilidad matemática de la autorreferencia exacta.

**Solución de raíz aplicada, tal como la propuso el usuario:** el
problema real no es el pin en sí, es que dependía de él en el camino
NORMAL de instalación. `GUIA_VOLUNTARIOS.md` recomendaba `irm ... | iex`
(ejecución directa en memoria, sin archivo en disco) como método
principal — con eso, `$PSCommandPath` es `$null`, `Save-SelfCopy` no
tiene ningún archivo propio que copiar, y cae a redescargar del pin fijo
(el único lugar donde el problema de la autorreferencia importa de
verdad). Cambiado a **descargar primero con `Invoke-WebRequest`, ejecutar
después** (`.\install-worker.ps1`) en los tres comandos de la guía
(instalar/actualizar, desinstalar) — con esto, `$PSCommandPath` siempre
apunta al archivo real ya en disco, `Save-SelfCopy` simplemente lo copia
tal cual, y el pin deja de usarse en el camino normal. `$InstallScriptCommit`
se conserva como red de seguridad SOLO para quien decida usar `irm | iex`
de todos modos (documentado explícitamente en el comentario del propio
código, con la limitación matemática explicada para que quede claro por
qué en ese caso excepcional el pin puede señalar al commit anterior, no
al propio, y por qué eso sigue siendo aceptable). El costo de esta
solución es un paso extra en el comando documentado (`Invoke-WebRequest`
+ `.\install-worker.ps1` en vez de una sola línea `irm | iex`) — aceptado
a cambio de eliminar la circularidad del camino normal por completo, tal
como lo pidió el usuario.

**Tres detalles menores corregidos tras revisión externa del cambio
anterior, ninguno funcional:**

- **Comentario desactualizado en `Invoke-DockerPullWithRetry`:** decía
  "corregido con Tee-Object", pero el código final usa `ForEach-Object`
  + `Write-InstallLog` + `$_` (un primer intento sí usó `Tee-Object`,
  descartado antes del commit porque no aportaba nada sobre el patrón
  actual). Corregido el texto para que coincida con el código real.
- **Progreso "retrocede" visualmente tras un reinicio por WSL2:**
  `$isResume` entra por la misma rama de 8 pasos que una instalación
  nueva (el proceso que se reinició no llegó más allá del paso de WSL2,
  y el proceso nuevo — una Scheduled Task en una sesión de PowerShell
  distinta — no tiene forma de heredar en qué paso iba el anterior). Ver
  `[Paso 1/8]` de nuevo después de un reinicio parece que la instalación
  "retrocedió", aunque no rompe nada (las verificaciones son
  idempotentes y rápidas la segunda vez). **No se intentó fabricar un
  número de paso heredado** (sería peor: un número inventado sin
  relación real con el trabajo restante) — se aclaró en texto, con un
  mensaje explícito antes de reiniciar el conteo explicando que los
  pasos se repiten pero deberían ser rápidos porque WSL2/Docker Desktop
  ya quedaron listos la vez anterior.
- **El contador no llega al total cuando el worker está pausado:**
  `Test-WorkerPaused` corta el flujo en el paso 2 de 8 (o 2 de 3 en
  actualización) — nunca llega a "confirmar registro"/"watchdog" porque
  no aplican mientras está pausado. El denominador representa el flujo
  normal, no todas las salidas alternativas — aclarado con una línea
  explícita en el mensaje final ("Listo (worker pausado)") en vez de
  intentar ajustar el total a posteriori (los pasos ya logueados con el
  total original no se pueden reescribir, y cambiar el denominador solo
  para el mensaje final habría sido inconsistente con lo ya impreso
  arriba).

17 escenarios de `test_worker_lifecycle.ps1` siguen pasando; verificado
con `Invoke-ScriptAnalyzer` que el conteo de hallazgos no cambió (11
antes y después).

### Bug real de producción: `UnauthorizedAccess` en dos máquinas tras el cambio a descargar-y-ejecutar (2026-09-14)

**Reportado con captura de pantalla real**: dos voluntarios corrieron el
comando nuevo de `GUIA_VOLUNTARIOS.md` (`Invoke-WebRequest ... -OutFile
install-worker.ps1` seguido de `.\install-worker.ps1`, ver la entrada
anterior sobre eliminar `irm | iex`) y ambos recibieron `No se puede
cargar el archivo ... porque la ejecucion de scripts esta deshabilitada
en este sistema` / `PSSecurityException: UnauthorizedAccess`.

**Causa raíz, consecuencia directa no anticipada del cambio anterior:**
`irm ... | iex` nunca pasa por la política de ejecución de scripts de
Windows en absoluto — evalúa el código directo en la sesión actual, no
"ejecuta un archivo .ps1". Un `.ps1` real guardado en disco sí queda
sujeto a esa política, y `Restricted` (el default de fábrica en la
mayoría de instalaciones de Windows, incluyendo ambas máquinas
reportadas) bloquea la ejecución de **cualquier** script sin firmar, no
solo este — el mismo síntoma ocurriría con cualquier `.ps1` de
cualquier origen en esas PCs. Este riesgo no se había considerado al
diseñar el cambio a descargar-y-ejecutar (motivado por resolver la
autorreferencia circular de `$InstallScriptCommit`, ver la entrada
anterior) — se evaluó la ganancia (elimina la circularidad) sin
verificar el costo real de abandonar `iex`.

**Corregido:** `Set-ExecutionPolicy -Scope Process -ExecutionPolicy
Bypass -Force` agregado como primera línea de los tres bloques de
comando de la guía (instalar, actualizar, desinstalar) — patrón oficial
de Microsoft para correr un script puntual sin firmar sin cambiar la
política de la PC de forma permanente. `-Scope Process` es deliberado,
no `-Scope CurrentUser`/`LocalMachine`: el cambio de política vive solo
en el proceso de PowerShell actual (una variable de entorno interna),
se pierde solo al cerrar esa ventana, sin dejar la PC del voluntario con
una política más permisiva de forma indefinida para cualquier otro
script futuro. Aclarado también en el texto que reabrir una ventana
nueva de PowerShell para pasar `-WorkerLabel`/`-Cpus`/`-MemoryLimit`
exige repetir el `Set-ExecutionPolicy` de nuevo, ya que `-Scope Process`
no persiste entre ventanas — sin esta aclaración, alguien que cerrara la
ventana entre el primer comando y el de personalizar el label habría
vuelto a pegar exactamente el mismo error reportado.

### Limpieza de identidades, criterio de asignación por cpu_score, y bug real de reencolado (2026-09-14)

**Cinco pedidos del usuario en la misma sesión, atendidos en orden:
identidades, criterio de asignación, `image_digest` faltante, horas
conectadas, y el bug de reencolado que esos dos últimos puntos
terminaron revelando.**

**Limpieza de `local-bryam`/`local-joel`, no eran "workers fantasma"
sino registros administrativos que ya cumplieron su propósito.**
Verificado antes de tocar nada: `import_local_results.py` los crea a
propósito (`worker_id` determinista `local-<label>`, ver "Segundo grupo
de datos" más arriba) para atribuir trabajo corrido FUERA del
coordinator — no es un bug, es el mecanismo de reparto de equipo. El
usuario pidió reasignar ese trabajo a la identidad real de cada persona
(`bryam-local` para lo de `local-bryam`, `eddy-laptop` para lo de
`local-joel`) y borrar los registros administrativos, ya que esa
distinción ya no aporta nada útil en el dashboard. Aplicado en la VM
real con una migración atómica (`BEGIN IMMEDIATE`): `UPDATE jobs SET
claimed_by=...`/`UPDATE results SET worker_id=...` para las 68 filas de
`local-bryam` y 22 de `local-joel` (confirmado 1:1 en ambas tablas antes
de tocar nada), **luego** `DELETE FROM workers` — en ese orden, porque
`results.worker_id` tiene `FOREIGN KEY REFERENCES workers(worker_id)`
con `PRAGMA foreign_keys=ON` activo: borrar primero habría fallado o
dejado referencias rotas. Verificado post-migración: 6 workers reales
(antes 8), `jobs_done` intacto.

**Criterio de asignación de jobs: hoy no es cpu_score, es
`repeticion ASC, priority DESC, job_id ASC`** (ver el fix de repeticiones
en serie, más arriba) — `min_cpu_score`/`min_ram_gb`/`min_cpu_count` son
umbrales mínimos pasa/no-pasa, nunca fueron un criterio de *orden* entre
workers elegibles. El usuario pidió explícitamente que los bins pesados
(6/7) se dirijan preferentemente a los mejores `cpu_score` — no solo que
se excluya a los muy lentos.

**Emparejamiento dinámico implementado (`pick_job_for_worker()`,
`db.py`), sin romper el orden de repetición/prioridad ya decidido.** El
modelo es *pull* (el worker pide, el coordinator ofrece), no hay forma
de "reservar" un job pesado para un worker rápido que aún no preguntó —
solo se puede decidir QUÉ dar cuando alguien ya está preguntando.
`claim_next_job()` ahora hace esto en dos pasos: (1) fija primero
`(repeticion, priority)` exactamente como antes, sin tocar ese orden —
nunca salta a un grupo distinto solo por tener un job mejor emparejado,
eso reintroduciría el bug de repeticiones en paralelo; (2) **dentro**
de ese grupo, si hay más de un candidato (offsets distintos del mismo
bin, o GCR_H/GCR_He compartiendo el mismo `bin_index`/`priority`), un
worker con `cpu_score >= REFERENCE_CPU_SCORE` (4.461, "rápido") recibe
el job MÁS PESADO del grupo (mayor `REFERENCE_TIMINGS_S`); uno más lento
recibe el MÁS LIVIANO. Sin una categoría "media" a propósito — con solo
un puñado de workers reales activos, fragmentar más no mejora el
emparejamiento. 3 tests nuevos verifican: worker rápido prefiere GCR_He
sobre GCR_H al mismo bin (más pesado), worker lento prefiere GCR_H
(más liviano), y el emparejamiento nunca cruza a otra repetición aunque
ahí hubiera un job "mejor" para ese worker.

**`MIN_CPU_SCORE` subido de 0.5 a 3.0** (`seed_full_sweep.py`) — el
valor anterior era deliberadamente bajo/prudente por falta de datos
reales al calibrarlo (ver la entrada original de `cpu_score`, más
arriba); con mediciones reales ya observadas (`bryam-local` 4.461,
`bryam-parrot` 4.334, `eddy-laptop` 1.247), 0.5 resultaba demasiado
permisivo — excluía solo máquinas extremadamente lentas, no protegía
bin6/7 de terminar en workers mediocres. 3.0 deja pasar a las dos
máquinas más rápidas conocidas y excluye explícitamente a `eddy-laptop`
de esos bins. **Aplicado también retroactivamente en la DB real**
(decisión explícita del usuario, no solo el código para sembrados
futuros): verificado que los 388 jobs `pending` en producción tenían
`min_cpu_score=0.0` en TODOS los casos — incluidos bin6/7, que sí
tenían `min_ram_gb`/`min_cpu_count` correctos pero nunca recibieron el
`min_cpu_score` del código, sembrados con una versión anterior del
script antes de que ese campo existiera. `UPDATE` directo en la VM
(mismo criterio que `job_priority_and_requirements()`: GCR_H/GCR_He
`bin_index>=6`, SEP_p `bin_index<=1`) — 123 jobs actualizados (79 GCR +
44 SEP_p), verificado vía la API pública sin cambiar `jobs_pending`.

**`image_digest` sigue en `null` para TODOS los workers, incluido
`eddy-laptop` (que sí corre la imagen nueva, confirmado por su
`cpu_score` real) — investigado, causa real identificada, decisión
explícita de NO arreglarlo esta sesión.** Confirmado que `null` es
CORRECTO para `bryam-local`/`bryam-parrot` (ambos workers locales sin
Docker — `hostname` es un nombre de máquina real tipo `bryam-VirtualBox`/
`parrot`, no un ID de contenedor corto; `DOCKER.available()` da `False`
sin socket que consultar, por diseño). Para `eddy-laptop`
(`hostname=DESKTOP-NNMBV76`, sí corre Docker, `cpu_score=1.247` confirma
que sí ejecuta `register()` completo) es un bug real: `self_container_id()`
(`worker.py`) intenta tres métodos para encontrar su propio container ID
desde dentro (mountinfo de `/etc/hostname`/`/etc/hosts`/`/etc/resolv.conf`,
luego `/proc/self/cgroup`, luego el fallback de asumir que `hostname` ES
el ID si matchea el patrón hex de 12/64 caracteres) — los tres fallan en
el entorno real de Docker Desktop/WSL2 de esa máquina específica (el
tercer fallback nunca puede funcionar ahí porque `DESKTOP-NNMBV76` no es
hexadecimal). Sin `container_id`, `self_image_digest()` devuelve `None`
sin error, silenciosamente. **Decisión explícita del usuario: documentar
como bug conocido y no arreglarlo ahora** — sin acceso a esa máquina
específica para verificar en vivo cuál de los tres métodos falla y por
qué (el layout de filesystem que Docker Desktop expone dentro del
contenedor en Windows/WSL2 puede diferir del Linux nativo que estos
regex asumen), un fix sin poder probarlo en la máquina real es
arriesgado. No bloquea nada — el resto de la telemetría (`cpu_score`,
`cpu_count`, heartbeat) funciona normalmente para ese worker.

**Bug real encontrado investigando el pedido de "horas conectadas":
`STALE_JOB_TIMEOUT_S` (el piso fijo) dominaba casi siempre sobre la
estimación, dejando el timeout real en 5-6h sin importar qué tan barato
fuera el job.** Caso real reportado por el usuario: `laptop-eddy` se
conectó ~1h anoche con un job estimado en ~2h, se desconectó, y el
dashboard siguió mostrando el job como `running` con "7.3h/2h est."
durante horas — `max(STALE_JOB_TIMEOUT_S, estimación×2.5)` con
`STALE_JOB_TIMEOUT_S=6h` y estimación=2h da `max(6h, 5h)=6h`: el piso
fijo gana casi siempre, porque `estimación×2.5` rara vez supera 6h salvo
para los bins más caros del barrido. El mecanismo de "no contar tiempo
offline dos veces" en sí SÍ funcionaba bien (`age_s = ahora -
last_heartbeat`, sin doble conteo) — el problema real era el valor del
piso, no la fórmula de edad.

**Rediseño completo con dos condiciones independientes para reencolar,
en vez de un único timeout mezclando dos propósitos distintos:**

1. **Progreso agotado**: `jobs.connected_s` (columna nueva — tiempo
   REAL conectado acumulado mientras el job está activo, no tiempo de
   pared) supera `estimación × ESTIMATE_SAFETY_FACTOR (2.5, sin
   cambios)`. Comparar contra `connected_s` en vez de tiempo de pared es
   justamente lo que resuelve el pedido del usuario: un worker que se
   apaga no gasta presupuesto de progreso mientras está apagado — antes,
   el `age_s` de la fórmula anterior técnicamente tampoco lo hacía mal
   (medía desde el último heartbeat, no acumulaba doble), pero mezclaba
   "cuánto ha avanzado" con "cuánto tiempo de pared pasó", dos preguntas
   distintas.
2. **Abandono**: tiempo de pared SIN heartbeat (`age_s`, la métrica
   correcta para ESTA pregunta específica) supera
   `_abandon_timeout_s()` = `clamp(estimación × ABANDON_FACTOR, 
   ABANDON_FLOOR_S, ABANDON_CEILING_S)`. Tres rondas de ajuste con el
   usuario antes de fijar los números: factor `×4` se descartó por
   exagerado (bin7 ~5.2h → ~21h de espera); `×2` con techo de 10h
   quedó como decisión final, con el propio usuario dando el
   razonamiento del techo ("8h de dormir + 2h de buffer para
   reconectar"). `ABANDON_FLOOR_S=1h` protege un job barato de
   reencolarse por un simple lag de red breve. Sin estimación disponible
   (worker sin `cpu_score`, o combinación sin referencia), cae
   directo a `STALE_JOB_TIMEOUT_S` — única red de seguridad para ese
   caso, sin cambios de comportamiento ahí.

Se reencola si CUALQUIERA de las dos se cumple — son preguntas
independientes ("¿ya debería haber terminado?" vs. "¿alguien sigue ahí
en absoluto?"), no una sola fórmula intentando responder ambas a la vez.
`STALE_JOB_TIMEOUT_S` bajado de 6h a 5h (pedido explícito del usuario al
revisar el nuevo diseño) — sigue siendo la red de seguridad para
combinaciones sin estimación, ya no el valor que domina el caso común.

**`jobs.connected_s`, cómo se acumula:** `touch_heartbeat()` ahora lee
el `last_heartbeat` ANTERIOR del worker antes de sobreescribirlo, calcula
el intervalo transcurrido, y lo suma (recortado a
`MAX_HEARTBEAT_ACCRUAL_S=120s`, 4× el intervalo real de heartbeat de
30s) al job `claimed`/`running` de ese worker — un gap mayor a eso
indica una desconexión real en el medio (red caída, PC suspendida), y
ese hueco no debe contar como tiempo conectado. Se resetea a 0 cada vez
que un job vuelve a `pending` (`record_result`/`record_failure` con
reintentos restantes, o `requeue_stale_jobs()`) — el siguiente intento
empieza su propio progreso desde cero, no arrastra el de un intento
fallido anterior. Migración `ALTER TABLE jobs ADD COLUMN connected_s
REAL NOT NULL DEFAULT 0` (idempotente, mismo patrón que las anteriores).

**Bug real encontrado por el primer test que reproducía el caso real
(no por revisión de código): el cutoff del `WHERE` de SQL en
`requeue_stale_jobs()` usaba `max()` en vez de `min()` de los dos pisos
posibles, excluyendo de entrada candidatos que el criterio fino en
Python sí debía evaluar.** Con `STALE_JOB_TIMEOUT_S=5h` (mucho mayor que
`ABANDON_FLOOR_S=1h` en el caso típico), el filtro SQL exigía heartbeat
vencido por 5h completas antes de traer la fila a Python — así que un
job cuyo umbral de abandono REAL era de solo ~1h (bin barato) nunca
llegaba a evaluarse, porque el filtro grueso ya lo había descartado.
Corregido a `min(STALE_JOB_TIMEOUT_S, ABANDON_FLOOR_S)` — el cutoff SQL
debe ser el MÁS CORTO posible entre los criterios, no el más largo, para
no excluir de más. 9 tests nuevos cubren el diseño completo (37→46 en
total): escalado de `_abandon_timeout_s()` entre piso/techo, el
escenario real reproducido explícitamente (bin6 con heartbeat vencido
2h se reencola sin esperar las 5h fijas), acumulación de `connected_s`
por heartbeat con y sin tope, reset a 0 al volver a `pending`, y que
`connected_s` alto por sí solo NO reencola sin que también haya vencido
el heartbeat (las dos condiciones son sobre timestamps distintos, no
intercambiables).

**Dashboard actualizado para mostrar tiempo conectado, no tiempo de
pared, como métrica principal de un job en curso** — la columna
"Duración" (antes solo `elapsedSinceClaim`) ahora usa `connected_s`
como número principal, con el tiempo de pared disponible en el tooltip
para quien lo quiera ver. Mismo criterio de color (`near-estimate`/
`over-estimate`) pero comparado contra `connected_s`, no contra tiempo
desde `claimed_at`. Detalle expandible gana "Tiempo conectado" y
renombra el campo de pared a "Asignado desde (pared)" para dejar
explícita la distinción entre ambos. `connected_s` ya viaja en
`GET /api/v1/jobs` sin tocar `app.py` — mismo patrón que
`actual_duration_s`, `SELECT j.*` en `list_jobs()` ya lo incluye
automáticamente al agregarse la columna.

**Sexto pedido, mismo día: las runs reales tardan un poco más que la
estimación mostrada — margen de sobreestimación aplicado directamente
sobre el número, no sobre el timeout de reencolado.** Ejemplo real del
usuario: GCR_He bin7 estimado en ~5.2h tomó ~5.7h reales, ~10% más.
Distinto de `ESTIMATE_SAFETY_FACTOR` (tolerancia antes de reencolar,
nunca cambiaba el número mostrado) y de `ABANDON_FACTOR` (margen para
que alguien reconecte, no de cómputo) — ninguno de los dos resolvía
"quiero que el número que veo ya venga con colchón". Nuevo
`DISPLAY_OVERESTIMATE_FACTOR = 1.15` aplicado directamente dentro de
`estimate_job_duration_s()` (después de escalar por `cpu_score`) — como
tanto el dashboard como `requeue_stale_jobs()` llaman a esa misma
función, el margen se propaga a ambos automáticamente sin tocarlos por
separado. Con esto, GCR_He bin7 al `cpu_score` de referencia pasa de
mostrar 5.22h a 6.00h. 2 tests actualizados/nuevos: el test de escalado
por `cpu_score` ya existente ahora incluye el factor en su cálculo
esperado, y uno nuevo confirma explícitamente que la estimación al
`cpu_score` de referencia exacto ya no es igual al número crudo de
`REFERENCE_TIMINGS_S` (47 tests en total, todos pasan).
