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
- Conversión `field/generate_mesh.py` → `.msh` → `field/mesh_to_gdml.py`
  → GDML con componentes y materiales separados. Requiere tetraedros de
  primer orden y grupos físicos con asignación explícita en JSON.
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
- GCR ISO-15390 y SEP ESP-PSYCHIC vía SPENVIS, ambas fases solares. Los exports
  físicos siguen siendo necesarios como pesos aunque las energías se simulen
  por bins. El scorer actual no calcula por sí solo dosis absoluta o equivalente.
- Mantener material de devanados, soportes y crióstato en el modelo final:
  la contribución pasiva y los secundarios pueden aumentar o reducir dosis.

**Propuestas y pendientes (no decisiones finales):**
- El usuario indica un plan previo de 12 bobinas. Geom14 de ARSSEM es la
  recomendación inicial; el arreglo exacto, materiales, dimensiones, vueltas,
  corriente y límites críticos del conductor siguen por definir. Bobinas y
  mapa físico **todavía no implementados**.
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
- `data/`: 6 archivos de espectro de energía, uno por combinación modelo×fase (`gcr_proton_solarmax.csv`, `gcr_proton_solarmin.csv`, `gcr_alpha_solarmax.csv`, `gcr_alpha_solarmin.csv`, `sep_proton_solarmax.csv`, `sep_proton_solarmin.csv`). **Son placeholders** (max y min son idénticos por ahora) — pendiente reemplazarlos con datos reales antes de sacar conclusiones científicas. **Estos 6 archivos ya NO se versionan directamente** (ver `.gitignore`) — son el destino generado por `scripts/select_spectrum_source.py <fuente>` a partir de `data/sources/<fuente>/*.csv`, que sí se versiona y es la fuente de verdad. Fuentes disponibles hoy: `spenvis/` (activa, ISO-15390+ESP-PSYCHIC) y `oltaris_oct1989/` (preparada, vacía salvo su README, para cuando se apruebe OLTARIS — ver README.md sección 0.6). `SpectrumSampler` es agnóstico a la fuente (solo lee dos columnas energía/flujo), así que cambiar de fuente no toca código C++, solo qué CSV se copia a `data/`.
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

- **Reemplazar los 6 CSV placeholder de `data/sources/spenvis/` con espectros reales por fase solar.** Modelos elegidos, ambos vía **SPENVIS** (mismo registro para las dos partes): **ISO-15390** para GCR, **ESP-PSYCHIC** para SEP. (Se había planeado Badhwar-O'Neill 2020 vía OLTARIS para GCR, pero la cuenta de OLTARIS quedó pendiente de aprobación sin tiempo estimado — se cambió a ISO-15390, ya activo en SPENVIS, para no bloquear el trabajo; CREME96 se descartó antes porque su componente de GCR está anclado a datos de 1986-87.) Checklist de qué exportar de cada modelo: [`docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md).
- **Decisión SEP en firme por ahora: ESP-PSYCHIC/SPENVIS, no el evento histórico de octubre de 1989 vía OLTARIS.** Son conceptualmente distintos (percentil estadístico sobre duración de misión vs. medición real de un evento puntual), no una simple sustitución de herramienta — no asumir que "Oct-1989" se puede insertar en el flujo SPENVIS ya armado. Si se aprueba OLTARIS, la carpeta `data/sources/oltaris_oct1989/` ya está preparada (con su propio README) para activar ese cambio con costo bajo — ver README.md sección 0.6 para el procedimiento exacto y por qué `SpectrumSampler` no necesita cambios de código para esto.
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
