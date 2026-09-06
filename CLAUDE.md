# CLAUDE.md

Este archivo documenta el proyecto para quien colabore en él (compañeros de equipo) y para futuras sesiones de Claude. Complementa a `README.md` (que cubre entorno y compilación) explicando el **por qué** de las decisiones y el estado actual de la metodología.

## Qué es este proyecto

Simulación GEANT4 (curso IAC 2026) de dosis de radiación espacial sobre un astronauta, usando eventos de rayos cósmicos galácticos (GCR) y de partículas solares (SEP). Ver `README.md` para el setup del entorno (conda, GEANT4 11.4.2) y compilación.

## Bitácora del cambio de metodología (2026-09-05)

**Antes:** el estudio comparaba 4 escenarios fijos de **blindaje pasivo** (capas de aluminio + polietileno alrededor del astronauta) combinados on/off con un campo magnético placeholder, sin variar su intensidad.

**Ahora:** el estudio gira en torno al **blindaje activo** (campo magnético) exclusivamente. Las variables que se barren son:

1. **Tipo de evento × fase solar** (4 combinaciones): GCR y SEP, cada uno en fase solar máxima y mínima.
2. **Intensidad del campo magnético**: de 7.0 a 10.0 T en pasos de 0.5 T (7 valores).
3. **Posición del astronauta** dentro de la nave: a lo largo de un eje, en 0, 0.7, 1.4, 2.1 y 2.8 m desde el centro.

Con esto se busca determinar qué intensidad de campo atenúa mejor la dosis, y cómo el riesgo radiológico varía según dónde esté ubicado el astronauta dentro de la nave, para los casos extremos de radiación (GCR/SEP máx/mín).

**Por qué:** cambio de enfoque del equipo — ya no interesa comparar blindaje pasivo, sino caracterizar la efectividad de un escudo magnético activo variable, que es más representativo de un sistema de protección activo a bordo.

**Qué se conserva:** el código del blindaje pasivo (capas Al/polietileno) **no se borró**, solo queda desactivado por defecto y fuera del barrido nuevo — se puede reactivar más adelante si el equipo lo necesita.

## Estructura de `geant4/GCR_SEP_Sim/`

Proyecto GEANT4 en C++ (CMake), ejecutable `gcrsim`. Piezas clave:

- `DetectorConstruction` / `DetectorMessenger`: geometría `World → ShipHull (aluminio, 0.3 cm) → ShipInterior (vacío) → Phantom`. El campo magnético, cuando está activo, está **confinado al interior de la nave** (no a todo el mundo, como antes). Comandos nuevos: `/detector/astronautX <cm>` (posición del astronauta), `/detector/hullThicknessCm <cm>` (espesor del casco). Comandos de blindaje legado (`/detector/shield`, `/detector/alThickness`, `/detector/polyThickness`) siguen existiendo pero no se usan en el barrido nuevo.
- `PrimaryGeneratorAction` / `GeneratorMessenger`: comando nuevo `/gun/phase max|min` para elegir la fase solar, además de `/gun/model GCR|SEP` ya existente.
- `data/`: 6 archivos de espectro de energía, uno por combinación modelo×fase (`gcr_proton_solarmax.csv`, `gcr_proton_solarmin.csv`, `gcr_alpha_solarmax.csv`, `gcr_alpha_solarmin.csv`, `sep_proton_solarmax.csv`, `sep_proton_solarmin.csv`). **Son placeholders** (max y min son idénticos por ahora) — pendiente reemplazarlos con datos reales (OMERE/SPENVIS/CREME96/Badhwar-O'Neill) antes de sacar conclusiones científicas.
- `macros/legacy/`: las 4 macros de escenarios de blindaje pasivo (`escenario1-4`), conservadas para referencia pero ya no reflejan el esquema de resultados actual.
- `scripts/run_sweep.py`: corre automáticamente las 140 combinaciones del barrido (4 evento×fase × 7 campo × 5 posición), con semillas aleatorias fijas por corrida para reproducibilidad. Soporta `--n-events` y `--limit` (nota: `--limit N` corre las primeras N combinaciones en el orden del barrido, no necesariamente una por cada modelo/fase) para hacer una corrida piloto antes del barrido completo. También soporta `--repeats` (repeticiones por combinación, para estadística) y `--only-model GCR|SEP` (repartir el barrido en equipo, ver README.md). El manifiesto (`sweep_manifest.csv`) y el CSV de resultados se escriben por append, corrida por corrida, así que un corte a la mitad no pierde lo ya corrido; resume está activado **por defecto** y salta las combinaciones `(índice, repetición)` que ya tengan `exit_code 0` en el manifiesto — usar `--no-resume` para forzar rehacer todo desde cero (ver sección correspondiente en README.md).
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

- **Reemplazar los 6 CSV placeholder de `data/` con espectros reales por fase solar.** Modelos elegidos: **Badhwar-O'Neill 2020** (GCR, vía [OLTARIS](https://oltaris.larc.nasa.gov/)) y **ESP-PSYCHIC** (SEP, vía [SPENVIS](https://www.spenvis.oma.be/)) — CREME96 se descartó porque su componente de GCR está anclado a datos de 1986-87, más viejo que Badhwar-O'Neill. Checklist de qué exportar de cada herramienta: [`docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md).
- **Dosis absoluta pendiente de implementar.** El artículo necesita Gy/día o Sv/año, no solo comparación relativa. Hoy `RunAction.cc` calcula dosis por los `N` eventos simulados (`/run/beamOn N`), sin normalizar por el flujo físico real — falta agregar un factor de escala `(flujo_real_integrado × área_esfera_fuente × tiempo_exposición) / N` una vez que se tengan las unidades exactas de los exports de OLTARIS/SPENVIS (ver checklist).
- Medir el tiempo del barrido completo con `--n-events 10000` real antes de dejarlo corriendo desatendido (un piloto con 200 eventos tomó ~2s/corrida; a 10000 eventos cada corrida será más lenta, sobre todo por la physics list `Shielding` — corran un piloto con el `--n-events` real primero para estimar el total de las 140 corridas).

## Reglas de trabajo en este repositorio

- **Documentación siempre al día:** cualquier cambio de código, metodología o proceso de equipo debe venir acompañado de la actualización correspondiente en `README.md` y/o `CLAUDE.md` en el mismo cambio (no como tarea pendiente para después). Si un commit modifica comportamiento (flags nuevos, cambios de esquema de datos, nuevos pasos de flujo de trabajo), la documentación se actualiza junto con el código, no en un commit aparte ni "cuando haya tiempo".
- **Sin coautoría en commits:** no incluir línea de `Co-Authored-By` (ni ninguna otra atribución de coautoría) en los mensajes de commit de este repositorio, sin importar quién o qué haya generado el cambio.
