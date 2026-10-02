# AGENTS.md

Este archivo documenta el proyecto para quien colabore en él (compañeros de
equipo) y para futuras sesiones de asistentes de programación. Complementa a
`README.md` (entorno, compilación, estructura) explicando el **por qué** de
las decisiones y el estado actual de la metodología.

## Qué es este proyecto

Simulación Geant4 (curso IAC 2026) de la dosis por órgano de un astronauta
(fantoma ICRP110) dentro de una nave con blindaje magnético activo CREW HaT,
frente a rayos cósmicos galácticos (GCR) y partículas solares (SEP). El
resultado buscado es la efectividad del escudo, η = 1 − D_escudo/D_control,
por órgano, especie, energía y posición, con incertidumbre justificada.

## v1 y v2

El 2026-10-01 el proyecto se reordenó:

- **v2 (`main`):** el barrido corregido. Parte de la
  [auditoría del 2026-09-30](docs/bitacora/auditoria_2026-09-30.md), que
  encontró que las dosis de la v1 no son válidas (malla de scoring fija en el
  origen, apuntado radial de los primarios, esfera fuente que corta las
  bobinas, vista por órgano inflada ×N). Nada se produce antes de aprobar
  los pilotos P0–P6.
- **v1:** tag `v1.0-piloto` (commit `82fadd8`, 2026-09-28) y rama `v1`.
  Incluye el piloto esférico `GCR_SEP_Sim`, el barrido de 600 corridas, los
  pilotos Fases 7–10 y la bitácora completa de esa etapa.
- **`v1-archivo`** (tag en `707d762`): `main` justo antes de la limpieza.
  Tiene la versión más reciente (ya corregida por la auditoría) de todo lo
  que salió de `main`: `plan_estadistico.md`, `validez_estadistica_runs.md`,
  `scripts/pilots/`, resultados v1, scripts de siembra del coordinator,
  `useful-examples/`, etc. Los enlaces de los documentos v2 a material v1
  apuntan aquí.
- Los resultados de las ramas `results/*` quedaron en los tags
  `v1/fase7-intrarun`, `v1/fase8-n200-preseedfix` y `v1/fase8-prod`.
- **La rama `infra/distributed-sweep` sigue viva:** la VM del coordinator la
  clona al arrancar (`infra/deploy/cloud-init-coordinator.yaml`). No
  borrarla ni convertirla en tag.

El 2026-10-02 la historia se reescribió para quitar las líneas
`Co-Authored-By`/`Claude-Session` que 7 commits tenían contra la regla de
abajo. El contenido de cada rama y tag quedó idéntico, pero cambiaron los
hashes de casi todos los commits: los citados en los documentos vigentes se
actualizaron (por ejemplo `57fa5d1` → `3535d62` en el método de
autodiagnóstico). Un hash viejo que aparezca en la bitácora de la v1 ya no
existe en el repo. Quien tenga un clon anterior debe hacer
`git fetch --force --tags` y `git reset --hard origin/<rama>` (o clonar de
nuevo).

## Estado del plan piloto (2026-10-01)

Plan vigente: [`docs/bitacora/plan_piloto.md`](docs/bitacora/plan_piloto.md)
(P0–P6, decisiones D1–D8). Especificación del barrido:
[`docs/bitacora/plan_barrido.md`](docs/bitacora/plan_barrido.md).

- **Camino crítico:** P1 → mapa Elmer final → P3/P4/P5 → P6 → barrido. El
  mapa Elmer es bloqueante y requiere una máquina con más RAM que la de
  desarrollo (~5 GB; la solución anterior llegó a 7.3 GB).
- **P1, paso 1 hecho** (`field/preselect_source_radius.py`): con la esfera
  fuente de 6.94 m, un tercio de las direcciones a 67 MeV está mal
  representado. Candidatos para Elmer: **12, 14 y 16 m**; el mapa tendrá que
  cubrir ±14–17 m en z (hoy ±7.6 m).
- **Scorer por evento** (`/eventStats/*`, `EventStatsRunAction.cc`),
  integrado en `run_organ_sweep.py --event-stats`. Validado: el SE de una
  sola corrida es insesgado cuando VOV < 0.1 y hay ≥200 eventos con
  depósito (este umbral se fijó a posteriori y debe confirmarse en P2). El
  "Camino B" histórico subestimaba el SE entre 2 y 9 veces. Método y
  validación en
  [`metodo_autodiagnostico_incertidumbre.md`](docs/bitacora/metodo_autodiagnostico_incertidumbre.md).
  **Todavía no en el coordinator/workers.**
- **P0 listo para correr** (`tests/p0_normalizacion/`): tabla de
  referencia ICRP 116 por órgano extraída, órganos definidos como ICRP
  (colon con recto; médula roja equivalente). Tolerancia D7: ±10% en
  órganos grandes y ±15% en mama y tiroides, a ≥100 MeV/n. Falta que el
  equipo apruebe D7. El zip de datos de ICRP no se versiona (derechos de
  autor).
- **Decisiones de equipo pendientes:** máquina para Elmer, D2 (δ_η, efecto
  mínimo detectable), D3, D4, D7.
- **Coordinator sin actualizar e imagen Docker nueva pendiente**: se hacen
  cuando los pilotos fijen la configuración.

## Índice de documentación

- [`docs/bitacora/plan_piloto.md`](docs/bitacora/plan_piloto.md) — pilotos
  P0–P6, decisiones bloqueantes, verificaciones hechas (normalización de la
  fuente: 1.010 ± 0.020), criterio de cada piloto fijado de antemano.
- [`docs/bitacora/plan_barrido.md`](docs/bitacora/plan_barrido.md) —
  configuración congelada, normalización, integración espectral, Q(L),
  estimadores y covarianzas (CRN para η), semillas v2, procedencia, tests
  T1–T12, post-proceso temporal de SEP.
- [`docs/bitacora/metodo_autodiagnostico_incertidumbre.md`](docs/bitacora/metodo_autodiagnostico_incertidumbre.md)
  — incertidumbre de una sola corrida y su autodiagnóstico, con borrador
  para el paper.
- [`docs/bitacora/referencias_paper.md`](docs/bitacora/referencias_paper.md)
  — referencias del paper (ICRP 116, Yeom et al. 2020, VOV de MCNP) y para
  qué se cita cada una.
- [`docs/bitacora/auditoria_2026-09-30.md`](docs/bitacora/auditoria_2026-09-30.md)
  — bugs de la v1 y requisitos del scorer (R1–R12).
- [`docs/bitacora/revision_2026-10-01.md`](docs/bitacora/revision_2026-10-01.md)
  — revisión local de código y documentos.
- [`docs/bitacora/activeshield_sim_historia.md`](docs/bitacora/activeshield_sim_historia.md)
  — historia del diseño (por qué CREW HaT, Elmer, `Shielding`, bins). Útil
  para justificar decisiones en el paper.
- [`geant4/ActiveShield_Sim/docs/modelo_realista.md`](geant4/ActiveShield_Sim/docs/modelo_realista.md)
  — justificación física, fuentes, hallazgos de la auditoría y mejoras.
- [`geant4/ActiveShield_Sim/docs/checklist_espectros_reales.md`](geant4/ActiveShield_Sim/docs/checklist_espectros_reales.md)
  — procedencia de los espectros OLTARIS.
- [`field/README.md`](field/README.md), `field/CREWHAT_STATUS.md`,
  `field/ELMER_VALIDATION.md` — pipeline de campo y su validación.
- [`infra/README.md`](infra/README.md), [`infra/deploy/README.md`](infra/deploy/README.md),
  [`infra/GUIA_VOLUNTARIOS.md`](infra/GUIA_VOLUNTARIOS.md),
  [`infra/GUIA_WORKER_LOCAL.md`](infra/GUIA_WORKER_LOCAL.md) — operación del
  coordinator y los workers.
- [`infra/OPERATIONS_LOG.md`](infra/OPERATIONS_LOG.md) — incidentes de
  producción del coordinator/worker y sus fixes. **Primer lugar donde
  buscar** si un síntoma parece nuevo.

## Estado vigente de `ActiveShield_Sim`

Detalle de interfaces en
[`geant4/ActiveShield_Sim/README.md`](geant4/ActiveShield_Sim/README.md).

- **Base:** ejemplo oficial ICRP110 (fantoma voxelizado con órganos reales).
- **Geometría:** cilindro `G4_Al` con 1.5 cm de casco, nave a escala CREW
  HaT (`shipRadius=4.5m`, `shipHalfLength=5m`). Blindaje pasivo
  (`addPassiveLayerCm`) conservado pero desactivado por defecto.
- **Bobinas: CREW HaT**, Halbach Torus de 8 bobinas elípticas (diseño NIAC
  Phase I), conductor CORC homogeneizado. El arreglo de producción **nunca
  usó la cinta de 12 mm**. Geom14/ARSSEM queda como propuesta no
  implementada.
- **Campo: Elmer FEM a escala real**
  (`field/production/crewhat_elmer_fullscale.map`). Biot-Savart trata cada
  bobina como un filamento con núcleo regularizado mucho menor que el
  winding pack real; `crewhat_niac_max.map` se conserva solo para comparar.
  La cifra histórica "Biot-Savart da 36–48% más dosis" **no se reprodujo**
  (0.93 ± 0.08 a 562 MeV): no citarla. Los `.map`/GDML de producción y sus
  manifiestos SHA256 se versionan en `field/production/` (excepción en
  `.gitignore`).
- **Physics list:** `Shielding`, vía `G4PhysListFactory`.
- **Fuente:** espectros OLTARIS (BON2020 para GCR, eventos históricos Oct
  1989 / Feb 1956 para SEP), energía fija por bin
  (`/gun/fixedEnergyMeV`), ley coseno (`/gun/angularDistribution cosine`)
  sobre una esfera de radio configurable (`/spacecraft/sourceSphereRadius`).
  El default sigue siendo `radial` solo para reproducir la v1.
- **Barrido:** `run_organ_sweep.py` corre `especie × bin × posición ×
  repetición`; `aggregate_organ_doses.py` combina con `π R² Φ`, `w_R`
  (ICRP 103) y las 6 categorías con `w_T = 0.12`. Los defaults (8 bins,
  posiciones 0–4 m) son de la v1; los de la v2 los fijan los pilotos.

### Partículas atrapadas en el campo

Una partícula cargada de baja energía puede quedar girando indefinidamente
en el vacío de `MagnetEnvelope` (caso real: un SEP_p de ~19 keV corrió más
de 10 h). Se corta con `G4UserLimits::SetUserMaxTrackLength()` en
`MagnetEnvelope` (3 × diámetro de la esfera fuente, escala sola) más
`G4StepLimiterPhysics` registrado en `ICRP110phantoms.cc`, sin el cual el
límite no se respeta. Si una corrida es anormalmente lenta tras cambiar la
geometría o el campo, este es el primer sospechoso. El scorer por evento
cuenta las trazas cortadas así (`truncated_tracks`): en SEP de 300 MeV es
el 1.9% de los primarios, a revisar en P1.

## Cómo compilar

En el entorno conda `geant4_env` la variable `$CXX` está vacía (el entorno
no instala el compilador de conda-forge) y `cmake` se resuelve al del
sistema, que no encuentra las dependencias del entorno por su cuenta. Hay
que pasar el compilador del sistema y el prefijo explícitamente (con
`geant4_env` activado, para que `$CONDA_PREFIX` no esté vacío):

    cd geant4/ActiveShield_Sim
    cmake -S . -B build -DCMAKE_CXX_COMPILER=g++ -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
    cmake --build build -j$(nproc)
    ctest --test-dir build --output-on-failure

Tests: `ctest` (mapa de campo, capas pasivas, scorer por evento T4/T5),
`python3 -m pytest geant4/ActiveShield_Sim/tests/python`,
`field/.venv/bin/python -m unittest discover -s field/tests` y
`python3 -m pytest infra/worker infra/coordinator`.

**Nodo de cómputo:** `scripts/install_compute_node.sh` instala Geant4 sin
Qt6 (`environment.headless.yml`, build `noqt_*`) y compila con
`-DWITH_GEANT4_UIVIS=OFF`. Se verificó que da la dosis idéntica bit a bit al
build con Qt. No incluye `field/.venv` ni Elmer.

## Cómputo distribuido

Diseño original e historia en el tag `v1-archivo`
(`infra/DISTRIBUTED_SWEEP_HISTORY.md`); operación vigente en
[`infra/README.md`](infra/README.md).

- **Coordinator** FastAPI + SQLite (`infra/coordinator/`) en una VM de GCP
  Always Free, **sin IP pública** desde 2026-09-27: HTTPS por Cloudflare
  Tunnel, SSH por IAP, egreso por Cloud NAT. Dashboard de solo lectura en
  `GET /dashboard`.
- **Worker** (`infra/worker/worker.py`): hace poll, traduce el job a una
  invocación de `run_organ_sweep.py` y sube el resultado. Imagen Docker en
  GHCR (instalador Windows `infra/deploy/install-worker.ps1`) o local
  contra un build compilado (`infra/GUIA_WORKER_LOCAL.md`).
- **Dos esquemas de jobs:** `jobs` (v1, grilla fija de 8 bins) y
  `jobs_v2` (`db_v2.py`, grilla parametrizable con `n_bins` en el `UNIQUE`,
  sube S1/S2/N). El barrido v2 se sembrará en `jobs_v2` con
  `seed_full_sweep_v2.py --n-bins` cuando los pilotos fijen los parámetros.
  Antes hay que llevar `--event-stats` y la ley coseno a los workers.
- **Mecanismos operativos:** reencolado por progreso agotado o abandono,
  estimación de duración por especie/bin escalada por `cpu_score`,
  remote-kill y log bajo demanda vía heartbeat (el worker solo hace polling
  saliente).
- **`WORKER_TOKEN`:** autenticación por secreto compartido, implementada
  pero **no activada**. Activarla exige que todos los workers agreguen el
  token antes que el servidor; si no, fallan con `401` a mitad de corridas
  largas. Falta solo la coordinación con el equipo.
- **Riesgos aceptados:** sin autenticación de workers por defecto, sin
  backup automático de la base, posible cómputo duplicado ante un timeout
  de abandono vencido.

## Reglas de trabajo en este repositorio

- **Documentación siempre al día:** cualquier cambio de código, metodología o proceso de equipo debe venir acompañado de la actualización correspondiente en `README.md` y/o `AGENTS.md` en el mismo cambio (no como tarea pendiente para después). Si un commit modifica comportamiento (flags nuevos, cambios de esquema de datos, nuevos pasos de flujo de trabajo), la documentación se actualiza junto con el código, no en un commit aparte ni "cuando haya tiempo".
- **Sin coautoría en commits:** no incluir línea de `Co-Authored-By` (ni ninguna otra atribución de coautoría) en los mensajes de commit de este repositorio, sin importar quién o qué haya generado el cambio.
- **Números con protocolo:** puntos de energía, bins, eventos o radios se proponen como candidatos con su protocolo estadístico; no se fijan sin validación (ver `plan_piloto.md`).
- **Material v1:** no reintroducir en `main` archivos de la v1; enlazarlos con URL al tag `v1-archivo`.
