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

## Índice de documentación

Este archivo se reorganizó el 2026-09-16 para reducir su tamaño (venía con
~4700 líneas de bitácora acumulada). El contenido no se borró — se movió a
archivos por tema, todos verbatim de lo que decía `AGENTS.md` antes de este
cambio. Este archivo ahora es un resumen + índice; para el detalle completo
(decisiones exactas, fechas, cifras, comandos reproducibles) seguir los
enlaces:

- **[`docs/bitacora/activeshield_sim_historia.md`](docs/bitacora/activeshield_sim_historia.md)**
  — diseño y evolución de `ActiveShield_Sim`: geometría/física, CREW HaT
  (bobinas Halbach), campo Elmer FEM vs. Biot-Savart, bins de energía y
  dosis por órgano.
- **[`infra/DISTRIBUTED_SWEEP_HISTORY.md`](infra/DISTRIBUTED_SWEEP_HISTORY.md)**
  — diseño original del sistema coordinator/worker (grano de job, esquema
  de datos, protocolo, Docker, despliegue inicial en GCP).
- **[`infra/OPERATIONS_LOG.md`](infra/OPERATIONS_LOG.md)** — registro
  cronológico de incidentes de producción del coordinator/worker y sus
  fixes (2026-09-12 en adelante) — **el primer lugar donde buscar** si un
  síntoma en el coordinator o un worker parece nuevo; es probable que ya
  haya ocurrido antes con su causa raíz documentada.
- **[`geant4/ActiveShield_Sim/docs/modelo_realista.md`](geant4/ActiveShield_Sim/docs/modelo_realista.md)**
  — justificación física, fuentes y pendientes del modelo.
- **[`geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md`](geant4/GCR_SEP_Sim/docs/checklist_espectros_reales.md)**
  — checklist de los espectros OLTARIS usados como fuente física.
- **[`docs/bitacora/validez_estadistica_runs.md`](docs/bitacora/validez_estadistica_runs.md)**
  (2026-09-16/17) — por qué no hay justificación formal para N=5
  repeticiones, tabla de IC95% por N, el acoplamiento real en
  `aggregate_organ_doses.py` que impide N distinto por bin, y el estado
  (sin implementar todavía) de expandir el barrido a las 6 combinaciones
  especie/fase (hoy son solo 3, el peor caso por especie). **Sin decisión
  final del equipo** — ver "Pendiente real" en ese documento.
- **[`infra/README.md`](infra/README.md)**, **[`infra/deploy/README.md`](infra/deploy/README.md)**,
  **[`infra/GUIA_VOLUNTARIOS.md`](infra/GUIA_VOLUNTARIOS.md)**,
  **[`infra/GUIA_WORKER_LOCAL.md`](infra/GUIA_WORKER_LOCAL.md)** —
  instrucciones operativas vigentes (no historia) para correr/administrar
  el coordinator y los workers.
- **[`README.md`](README.md)** — setup de entorno y compilación.

## Estado vigente de ActiveShield_Sim (resumen)

> Historia completa, con fechas, cifras y justificación de cada decisión,
> en [`docs/bitacora/activeshield_sim_historia.md`](docs/bitacora/activeshield_sim_historia.md).

`ActiveShield_Sim` parte del ejemplo oficial ICRP110 (fantoma con órganos
reales, a diferencia del piloto esférico de `GCR_SEP_Sim`). Estado actual:

- **Geometría/campo:** cilindro `G4_Al` de 1.5cm de casco, blindaje activo
  vía `/spacecraft/coilGeometry` (masa/secundarios de las bobinas) +
  `/spacecraft/fieldMap` (mapa regular con interpolación trilineal, global,
  independiente de fronteras materiales). Blindaje pasivo (`addPassiveLayerCm`)
  conservado pero desactivado por defecto.
- **Bobina de producción: CREW HaT**, no Geom14/ARSSEM (que sigue como
  propuesta en paralelo, sin implementar el arreglo completo de 12
  bobinas). CREW HaT es un Halbach Torus de 8 bobinas elípticas
  (diseño NIAC Phase I): conductor CORC homogeneizado (el arreglo de
  producción **nunca usó la cinta de 12mm**, solo pilotos de una bobina la
  probaron), nave escalada a `shipRadius=4.5m`/`shipHalfLength=5m`.
- **Campo de producción: Elmer FEM a escala real**
  (`field/production/crewhat_elmer_fullscale.map`), no Biot-Savart —
  Biot-Savart sobreestima la dosis ~36-48% frente a Elmer en la misma
  configuración porque trata cada bobina como un filamento con núcleo
  regularizado mucho menor que el winding pack real.
  `field/production/crewhat_niac_max.map` (Biot-Savart) se conserva solo
  para comparación. Archivos de producción (`.map`/GDML + manifiestos
  SHA256) versionados en `field/production/` (excepción explícita en
  `.gitignore`); `field/generated/`/`build/` siguen sin versionar.
- **Physics list de producción: `Shielding`** (no `QGSP_BIC_HP`), vía
  `G4PhysListFactory`.
- **Barrido de dosis por órgano/riesgo estocástico**: `/gun/fixedEnergyMeV`
  fuerza energía monoenergética (reemplaza el muestreo continuo de
  `SpectrumSampler` para este propósito); `scripts/energy_bins.py` calcula
  8 bins log-espaciados por especie (GCR_H, GCR_He, SEP_p) dentro del rango
  que cubre >99.9% del flujo/fluencia real; `run_organ_sweep.py` corre
  `especie × bin × posición(offsetX) × repetición`; `aggregate_organ_doses.py`
  combina con ponderación radiobiológica ICRP103 (w_R por especie) sobre 6
  categorías de riesgo estocástico (w_T=0.12 c/u, incluyendo médula ósea
  roja verificada contra `AM_spongiosa.dat`).
- **Resultados reales** (parciales, de varios contribuyentes) versionados
  en `geant4/ActiveShield_Sim/resultados/` (excepción a `.gitignore` para
  estos CSV).
- **Cómputo**: el barrido completo (600 combinaciones: 120 combinaciones ×
  5 repeticiones) se ejecuta con la infraestructura distribuida
  coordinator/worker — ver la sección "Cómputo distribuido" más abajo.

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

## Cómputo distribuido para el barrido de ActiveShield_Sim (resumen)

> Diseño original y despliegue inicial en
> [`infra/DISTRIBUTED_SWEEP_HISTORY.md`](infra/DISTRIBUTED_SWEEP_HISTORY.md).
> Historia cronológica de incidentes de producción y sus fixes (la parte
> más útil para diagnosticar algo nuevo) en
> [`infra/OPERATIONS_LOG.md`](infra/OPERATIONS_LOG.md). Instrucciones
> operativas vigentes en [`infra/README.md`](infra/README.md) y
> [`infra/deploy/README.md`](infra/deploy/README.md).

El barrido completo de dosis por órgano (600 combinaciones) se reparte
entre varias máquinas voluntarias mediante un **coordinator** (FastAPI +
SQLite, `infra/coordinator/`) y un **worker** (`infra/worker/worker.py`)
que hace poll, traduce el job recibido a una invocación de
`run_organ_sweep.py --only-species --only-bins --only-positions
--repetition-start`, y sube el resultado filtrado.

Piezas clave para administrar el sistema:

- **Grano de job**: una combinación `(species, bin_index, offset_x_m,
  repeticion)` — el costo varía ~250x entre bins (segundos a >1h), así que
  nunca se reparte por posición completa.
- **Orden de asignación**: repeticiones en serie (`repeticion ASC`, nunca
  se ofrece un job de una repetición mayor mientras queden pendientes en
  una menor), con excepción de un **worker "élite"** (`cpu_score ≥ 10`)
  que sí puede saltar el orden para tomar el job más pesado del sistema.
  Dentro de un mismo grupo, el emparejamiento por `cpu_score` favorece dar
  los bins más caros (6/7) a los workers más rápidos.
- **Reencolado automático** (`requeue_stale_jobs()`, cada
  `REQUEUE_SWEEP_INTERVAL_S`): dos condiciones independientes —
  *progreso agotado* (`connected_s` tiempo real conectado, no tiempo de
  pared, supera la estimación×margen) y *abandono* (heartbeat vencido más
  allá de un timeout dinámico basado en la estimación, acotado entre un
  piso y un techo). `STALE_JOB_TIMEOUT_S` es solo la red de seguridad
  cuando no hay estimación disponible.
- **Estimación de duración** (`estimate_job_duration_s()`): tabla de
  referencia real por especie/bin, escalada por el `cpu_score` del worker
  (medido una sola vez al arrancar el proceso — no es una propiedad fija
  del hardware, puede variar entre reinicios de la misma máquina).
- **Remote-kill** (`POST /jobs/{id}/cancel`, `infra/coordinator/cancel_job.py`)
  y **log bajo demanda** (`POST /jobs/{id}/request-log`,
  `infra/coordinator/request_job_log.py`): ambos viajan en la respuesta
  del heartbeat existente (el worker solo hace polling saliente, sin
  puerto expuesto) — no en `dashboard.html`, que es deliberadamente de
  solo lectura sin autenticación.
- **Dashboard de solo lectura**: `GET /dashboard`
  (`infra/coordinator/dashboard.html`), consulta `/api/v1/health`,
  `/api/v1/jobs`, `/api/v1/workers` — filtros multi-valor y orden
  multi-columna por header.
- **Despliegue**: coordinator en una VM de GCP Always Free Tier (Azure
  quedó bloqueado por política de cuenta), HTTPS vía Caddy/Let's Encrypt.
  Workers: imagen Docker publicada en GHCR (instalador
  `infra/deploy/install-worker.ps1` para Windows, con auto-actualización
  Docker), o `infra/worker/worker.py` corriendo local directo contra un
  build ya compilado (`infra/GUIA_WORKER_LOCAL.md`).
- **`WORKER_TOKEN`** (autenticación por secreto compartido): implementado
  en código pero **no activado** en producción — ver la sección dedicada
  más abajo.
- **Riesgos aceptados explícitamente**: sin autenticación de workers por
  defecto, sin backup automático de la base de datos, posible cómputo
  duplicado ante un timeout de abandono vencido — detalle y justificación
  en `infra/DISTRIBUTED_SWEEP_HISTORY.md`.

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

- **Validez estadística de las 5 repeticiones y expansión a 6 combinaciones
  especie/fase (2026-09-16/17, sin decidir).** El barrido de producción
  (`run_organ_sweep.py`) usa 5 repeticiones sin justificación estadística
  formal, y solo 3 de las 4 combinaciones físicas reales de OLTARIS (falta
  GCR máximo solar y SEP mínimo/Feb1956) — el equipo indicó que necesita
  los 6 casos (3 especies × 2 fases) para el paper, pero **no está
  implementado todavía** (columna `phase` en el coordinator, filtro
  `--only-phase`, imagen Docker nueva). Detalle completo, tabla de IC95%
  por N, y plan propuesto (no aprobado) en
  [`docs/bitacora/validez_estadistica_runs.md`](docs/bitacora/validez_estadistica_runs.md).
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

