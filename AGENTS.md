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
- Fantoma fijo, centrado en el eje a media longitud; no barrido de posición.
- **Bins de energía + reponderación** para producción. La decisión ya está
  tomada; faltan bordes/rango, especies, N/bin, orquestador y estimación de
  incertidumbre por órgano. No portar muestreo continuo como plan de producción.
- **Gmsh + Elmer + Python** para calcular y exportar el campo. No implementar
  un Halbach uniforme ficticio; no inventar dimensiones/corrientes de bobinas.
  Elmer todavía no está instalado/configurado por este flujo: el venv cubre
  mallado y conversión, no la solución FEM ni sus dependencias nativas.
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
- Mantener material de devanados, soportes y crióstato en el modelo final:
  la contribución pasiva y los secundarios pueden aumentar o reducir dosis.

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
  No se ha añadido aún la capa ni una interfaz de escenarios.
- Elegir física de producción (`QGSP_BIC_HP` actual vs `Shielding` del piloto).
- La posible novedad del artículo requiere revisión bibliográfica; calcular B
  dentro o fuera de Geant4 no demuestra por sí mismo una contribución novedosa.

## Estructura de `geant4/GCR_SEP_Sim/`

Proyecto GEANT4 en C++ (CMake), ejecutable `gcrsim`. Piezas clave:

- `DetectorConstruction` / `DetectorMessenger`: geometría `World → ShipHull (aluminio, 0.3 cm) → ShipInterior (vacío) → Phantom`. El campo magnético, cuando está activo, está **confinado al interior de la nave** (no a todo el mundo, como antes). Comandos nuevos: `/detector/astronautX <cm>` (posición del astronauta), `/detector/hullThicknessCm <cm>` (espesor del casco). Comandos de blindaje legado (`/detector/shield`, `/detector/alThickness`, `/detector/polyThickness`) siguen existiendo pero no se usan en el barrido nuevo.
- `PrimaryGeneratorAction` / `GeneratorMessenger`: comando nuevo `/gun/phase max|min` para elegir la fase solar, además de `/gun/model GCR|SEP` ya existente.
- `data/`: 6 archivos de espectro de energía, uno por combinación modelo×fase (`gcr_proton_solarmax.csv`, `gcr_proton_solarmin.csv`, `gcr_alpha_solarmax.csv`, `gcr_alpha_solarmin.csv`, `sep_proton_solarmax.csv`, `sep_proton_solarmin.csv`). **Son placeholders** (max y min son idénticos por ahora) — pendiente reemplazarlos con datos reales antes de sacar conclusiones científicas. **Estos 6 archivos ya NO se versionan directamente** (ver `.gitignore`) — son el destino generado por `scripts/select_spectrum_source.py <fuente>` a partir de `data/sources/<fuente>/*.csv`, que sí se versiona y es la fuente de verdad. Fuentes en `data/sources/`: `spenvis/` (plan B, ISO-15390+ESP-PSYCHIC, ya no es la fuente activa) y `oltaris/` (activa desde 2026-09-08: BON2020 para GCR, evento histórico Oct 1989/Feb 1956-LaRC para SEP — carpeta y README pendientes de poblar con los exports reales, ver checklist). `SpectrumSampler` es agnóstico a la fuente (solo lee dos columnas energía/flujo), así que cambiar de fuente no toca código C++, solo qué CSV se copia a `data/`.
- `macros/legacy/`: las 4 macros de escenarios de blindaje pasivo (`escenario1-4`), conservadas para referencia pero ya no reflejan el esquema de resultados actual.
- `scripts/run_sweep.py`: corre automáticamente las 140 combinaciones del barrido (4 evento×fase × 7 campo × 5 posición), con semillas aleatorias fijas por corrida para reproducibilidad. Soporta `--n-events` y `--limit` (nota: `--limit N` corre las primeras N combinaciones en el orden del barrido, no necesariamente una por cada modelo/fase) para hacer una corrida piloto antes del barrido completo. También soporta `--repeats` (repeticiones por combinación, para estadística) y `--only-model GCR|SEP` (repartir el barrido en equipo, ver README.md). El manifiesto (`sweep_manifest.csv`) y el CSV de resultados se escriben por append, corrida por corrida, así que un corte a la mitad no pierde lo ya corrido; resume está activado **por defecto** y salta las combinaciones `(índice, repetición)` que ya tengan `exit_code 0` en el manifiesto — usar `--no-resume` para forzar rehacer todo desde cero (ver sección correspondiente en README.md). El default de `--n-events` (y el `BASE_SEED`) vienen de `geant4/sweep_config.py`, compartido entre proyectos — ver ese archivo antes de hardcodear un número de eventos "oficial" en un script nuevo. Los parámetros específicos de esta geometría (campo uniforme, posiciones del astronauta) NO están ahí a propósito, porque `ActiveShield_Sim` tendrá un espacio de parámetros distinto (bobinas Halbach) una vez que exista — `ActiveShield_Sim` todavía no tiene lanzador por bins: faltan la definición de energías/configuraciones y los pesos físicos. Su lector de mapa ya existe; no confundirlo con un mapa físico validado.
- Resultados: `resultados_dosis_sweep.csv` (columnas `modelo,fase,field_T,astronaut_x_m,n_eventos,edep_MeV,masa_kg,dosis_Gy`), una fila por corrida.

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

- **Reemplazar los 6 CSV placeholder de `data/sources/` con espectros reales por fase solar.** Modelos elegidos, ambos vía **OLTARIS** (acceso aprobado 2026-09-08, reemplaza el plan intermedio con SPENVIS): **Badhwar-O'Neill 2020** para GCR (periodos históricos de mínimo/máximo solar), **evento histórico** para SEP (Oct 1989 = máximo, Feb 1956 ajuste LaRC = mínimo — no el modelo probabilístico ESP-PSYCHIC). CREME96 se había descartado antes porque su componente de GCR está anclado a datos de 1986-87; ISO-15390/SPENVIS y ESP-PSYCHIC/SPENVIS quedaron como plan B si OLTARIS no se aprobaba a tiempo, ya no es el camino activo. Checklist de qué exportar de cada modelo: [`docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md).
- **Dosis absoluta pendiente de implementar.** El piloto calcula Gy por los
  N eventos simulados. Producción requiere respuestas por bin y ponderación
  con flujo GCR (incluye tiempo) o fluencia SEP por evento (sin tiempo extra).
  Los factores de área y ángulo dependen de la definición del export y del
  muestreo entrante: no multiplicar un flujo omnidireccional por el área de
  una esfera sin derivar esa normalización. Ver la fórmula y condiciones en
  `geant4/ActiveShield_Sim/docs/modelo_realista.md`. Gy y Sv no son equivalentes.
- Medir el tiempo del barrido completo con `--n-events 10000` real antes de dejarlo corriendo desatendido (un piloto con 200 eventos tomó ~2s/corrida; a 10000 eventos cada corrida será más lenta, sobre todo por la physics list `Shielding` — corran un piloto con el `--n-events` real primero para estimar el total de las 140 corridas).
- **Bins ya acordados para ActiveShield_Sim.** Pendientes de implementación:
  respuesta por energía/especie/órgano, pesos físicos y su incertidumbre.
  El piloto conserva su barrido anterior; no usar sus corridas como si fueran
  respuestas monoenergéticas. Ver el documento de decisiones enlazado arriba.


## Reglas de trabajo en este repositorio

- **Documentación siempre al día:** cualquier cambio de código, metodología o proceso de equipo debe venir acompañado de la actualización correspondiente en `README.md` y/o `AGENTS.md` en el mismo cambio (no como tarea pendiente para después). Si un commit modifica comportamiento (flags nuevos, cambios de esquema de datos, nuevos pasos de flujo de trabajo), la documentación se actualiza junto con el código, no en un commit aparte ni "cuando haya tiempo".
- **Sin coautoría en commits:** no incluir línea de `Co-Authored-By` (ni ninguna otra atribución de coautoría) en los mensajes de commit de este repositorio, sin importar quién o qué haya generado el cambio.
