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
- `scripts/run_sweep.py`: corre automáticamente las 140 combinaciones del barrido (4 evento×fase × 7 campo × 5 posición), con semillas aleatorias fijas por corrida para reproducibilidad. Soporta `--n-events` y `--limit` para hacer una corrida piloto antes del barrido completo.
- Resultados: `resultados_dosis_sweep.csv` (columnas `modelo,fase,field_T,astronaut_x_m,n_eventos,edep_MeV,masa_kg,dosis_Gy`), una fila por corrida.

## Cómo compilar y correr

Igual que lo documentado en `README.md` (entorno conda + GEANT4 11.4.2), dentro de `geant4/GCR_SEP_Sim/`:

    rm -rf build && mkdir build && cd build
    cmake -DCMAKE_CXX_COMPILER=$CXX ..
    make -j$(nproc)

Corrida piloto del barrido (rápida, para validar que todo funciona):

    python3 ../scripts/run_sweep.py --n-events 100 --limit 4

Barrido completo (140 corridas):

    python3 ../scripts/run_sweep.py

## Pendientes conocidos

- Reemplazar los 6 CSV placeholder de `data/` con espectros reales por fase solar.
- Validar tiempos de cómputo del barrido completo (la physics list `Shielding` puede ser lenta con 10000 eventos × 140 corridas) — conviene correr el piloto primero.
