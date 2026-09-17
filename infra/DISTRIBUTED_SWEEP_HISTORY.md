> Bitácora histórica extraída de `AGENTS.md` el 2026-09-16 (reorganización
> para reducir el tamaño de ese archivo). Cubre el diseño original y el
> primer despliegue del sistema coordinator/worker para distribuir el
> barrido de dosis por órgano de `ActiveShield_Sim` entre varias máquinas
> voluntarias: grano de job, esquema de la base de datos, protocolo
> worker↔coordinator, imagen Docker, despliegue en GCP, y los primeros
> jobs poblados. Para el registro cronológico de incidentes/fixes
> posteriores en producción, ver [`infra/OPERATIONS_LOG.md`](OPERATIONS_LOG.md).
> Para instrucciones operativas vigentes, ver [`infra/README.md`](README.md)
> y [`infra/deploy/README.md`](deploy/README.md).

# Cómputo distribuido para el barrido de ActiveShield_Sim (2026-09-12)

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

