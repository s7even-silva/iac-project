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

## Bitácora: inicio del proyecto de geometría real (2026-09-07)

`GCR_SEP_Sim/` sigue siendo un **placeholder deliberado** (esfera + campo
uniforme + tejido homogéneo) usado como pipeline de referencia para probar
estadística, barrido y reproducibilidad — no la geometría de producción.

Se abrió `geant4/ActiveShield_Sim/` para la geometría real que va al
artículo: nave cilíndrica **ARSSEM (5.6 × 10 m, ya implementada)**, arreglo
de bobinas **Halbach** (número, dimensiones y posición dentro de la nave aún
sin definir por el equipo — ver `ActiveShield_Sim/README.md`, paso 3) y
fantoma dosimétrico **ICRP110** (142 órganos, no una esfera de tejido
homogéneo, ya centrado en el eje de la nave a media longitud).
Parte del ejemplo oficial de Geant4 `ICRP110_HumanPhantoms` (ya validado
corriendo de punta a punta en este repo) en vez de extender `GCR_SEP_Sim`,
porque ese ejemplo ya trae su propio `World` y el fantoma vóxel funcionando
— es más barato agregar nave+bobinas como volúmenes hijos de ese `World` que
extraer la lógica de vóxeles e insertarla en el `DetectorConstruction`
actual. Ver `geant4/ActiveShield_Sim/README.md` para el estado detallado,
diferencias de API frente a `GCR_SEP_Sim` (fuente `/gps/` vs `G4ParticleGun`,
scoring por mesh vs. acumulador manual, physics list `QGSP_BIC_HP` vs.
`Shielding`) y los próximos pasos concretos de implementación.

**Decisiones de equipo ya tomadas que aplican a este proyecto nuevo:**
- Fantoma en una sola posición, en el eje del cilindro, a media longitud
  (no barrido de posición) — declarar la anisotropía del campo Halbach
  (protege peor por los "caps") como limitación en el artículo.
- Modelo GCR = ISO-15390, SEP = ESP-PSYCHIC, ambos vía SPENVIS, ambas fases
  solares — igual que en `GCR_SEP_Sim` (ver checklist y README.md, sección
  "Fechas de referencia para la fase solar").

**Pendiente de decidir con el equipo (no asumir, no implementar todavía):**
- **Número, dimensiones y posición de las bobinas Halbach dentro de
  `ShipInterior`** — bloquea directamente el paso 3 de `ActiveShield_Sim`
  (geometría de las bobinas, y con ella la clase de campo custom).
- Si el campo Halbach se modela nativamente en Geant4 (geometría de bobinas
  real + campo no uniforme calculado analíticamente, evaluado en tiempo real
  durante el tracking — la opción que da la novedad real del paper: rigidez
  magnética integrada, scorer de fluencia sobre el propio conductor HTS) o
  se importa un mapa de campo tabulado/precalculado externamente. Ver la
  explicación técnica completa (cómo Geant4 aplica un campo custom, y por
  qué el material de las bobinas y el campo que producen son dos cosas
  independientes que hay que conectar explícitamente) en
  `ActiveShield_Sim/README.md`, paso 3.
  **Antecedentes investigados (ver README.md para detalle y citas):**
  ni siquiera **CREW HaT** (la referencia que el equipo daba por calcada)
  modela el campo dentro de Geant4 — calcula el Halbach vía Biot-Savart+RK4
  en un trazador propio, y usa Geant4 aparte solo para la dosis final con
  blindaje simplificado. **ARSSEM** (mismo nombre que la nave del equipo)
  sí modela material real de bobinas + descompone dosis campo/material,
  pero en GEANT3 con campo uniforme confinado, no Halbach analítico. **SR2S**
  es el antecedente más fuerte en Geant4 real (vía GRAS) para secundarios de
  blindaje activo, pero con topología toroidal, no Halbach. Ningún estudio
  combina Halbach nativo en Geant4 + material HTS real + scorer de fluencia
  sobre el conductor — esa combinación sería la contribución novedosa real,
  si se logra implementar (b) del paso 3 de forma nativa.
- **El material real de las bobinas (REBCO/CORC + crióstato) debe estar en
  la simulación, no solo el campo que producen** — son blindaje pasivo
  incidental: absorben radiación primaria pero también la fragmentan en
  secundarios (neutrones, fotones de captura, espalación) que pueden llegar
  al fantoma con más facilidad que la radiación original. Ignorar esto
  subestima la dosis real; es el mismo efecto que el estudio SR2S documentó
  como hallazgo central para blindaje magnético activo en general.
- Consistencia numérica del imán (vueltas × corriente × Ic del conductor
  CORC/REBCO) antes de fijar la geometría de las bobinas.
- Número de eventos real: si el barrido final es por eventos totales o por
  bin de energía (monoenergético + reponderación) — afecta directamente si
  las barras de error del artículo son defendibles.

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

- **Reemplazar los 6 CSV placeholder de `data/` con espectros reales por fase solar.** Modelos elegidos, ambos vía **SPENVIS** (mismo registro para las dos partes): **ISO-15390** para GCR, **ESP-PSYCHIC** para SEP. (Se había planeado Badhwar-O'Neill 2020 vía OLTARIS para GCR, pero la cuenta de OLTARIS quedó pendiente de aprobación sin tiempo estimado — se cambió a ISO-15390, ya activo en SPENVIS, para no bloquear el trabajo; CREME96 se descartó antes porque su componente de GCR está anclado a datos de 1986-87.) Checklist de qué exportar de cada modelo: [`docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md).
- **Dosis absoluta pendiente de implementar.** El artículo necesita Gy/día o Sv/año, no solo comparación relativa. Hoy `RunAction.cc` calcula dosis por los `N` eventos simulados (`/run/beamOn N`), sin normalizar por el flujo físico real. La fórmula de escala es distinta para GCR y SEP porque no son la misma clase de cantidad:
  - **GCR** (flujo continuo): `dosis_Gy_por_dia = dosis_sim × (flujo_integrado[part/cm²/s] × área_esfera_fuente[cm²] × 86400[s/dia]) / N`.
  - **SEP** (con "Worst Case Event" de ESP-PSYCHIC, ver checklist — es la fluencia de UN evento puntual, ya integrada en el tiempo, no una tasa): `dosis_Gy_del_evento = dosis_sim × (fluencia_evento[part/cm²] × área_esfera_fuente[cm²]) / N` — sin factor de tiempo, porque la fluencia ya representa el evento completo.
  
  Falta implementar esto en `RunAction.cc` (probablemente como un factor de normalización configurable por modelo/fase, ya que cada uno de los 6 CSV de espectro real va a traer su propio valor de flujo/fluencia integrada) una vez que se tengan las unidades exactas de los exports de SPENVIS (ver checklist).
- Medir el tiempo del barrido completo con `--n-events 10000` real antes de dejarlo corriendo desatendido (un piloto con 200 eventos tomó ~2s/corrida; a 10000 eventos cada corrida será más lenta, sobre todo por la physics list `Shielding` — corran un piloto con el `--n-events` real primero para estimar el total de las 140 corridas).

## Reglas de trabajo en este repositorio

- **Documentación siempre al día:** cualquier cambio de código, metodología o proceso de equipo debe venir acompañado de la actualización correspondiente en `README.md` y/o `CLAUDE.md` en el mismo cambio (no como tarea pendiente para después). Si un commit modifica comportamiento (flags nuevos, cambios de esquema de datos, nuevos pasos de flujo de trabajo), la documentación se actualiza junto con el código, no en un commit aparte ni "cuando haya tiempo".
- **Sin coautoría en commits:** no incluir línea de `Co-Authored-By` (ni ninguna otra atribución de coautoría) en los mensajes de commit de este repositorio, sin importar quién o qué haya generado el cambio.
