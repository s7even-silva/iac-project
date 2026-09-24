# Registro de operaciones e incidentes del coordinator/worker

> Bitácora histórica extraída de `AGENTS.md` el 2026-09-16 (reorganización
> para reducir el tamaño de ese archivo). Es la continuación cronológica de
> [`infra/DISTRIBUTED_SWEEP_HISTORY.md`](DISTRIBUTED_SWEEP_HISTORY.md) —
> bugs reales de producción, rondas de revisión del instalador de Windows,
> cambios de esquema/criterio de asignación de jobs, incidentes de cómputo
> perdido, y sus fixes, del 2026-09-12 en adelante. Útil como referencia
> al diagnosticar un problema nuevo del coordinator: muchos síntomas ya
> ocurrieron antes y están documentados aquí con su causa raíz real. Para
> instrucciones operativas vigentes (no historia), ver
> [`infra/README.md`](README.md) y [`infra/deploy/README.md`](deploy/README.md).

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
arriba); con mediciones reales ya observadas en ese momento
(`bryam-local` 4.461, `bryam-parrot` 4.334, `eddy-laptop` 1.247), 0.5
resultaba demasiado permisivo — excluía solo máquinas extremadamente
lentas, no protegía bin6/7 de terminar en workers mediocres. 3.0 deja
pasar a las dos máquinas más rápidas conocidas y excluye explícitamente
a `eddy-laptop` de esos bins.

**Importante, no confundir con lo anterior: esos números no son fijos
en el tiempo, son la lectura de un momento puntual.** `cpu_score()`
(`worker.py`) se corre **una sola vez al arrancar el proceso del
worker**, no en cada heartbeat (ver su propio docstring: "el hardware
no cambia en caliente") — así que cada reinicio del worker puede medir
un número distinto, sobre todo en una VM (como `bryam-local`,
VirtualBox) que comparte CPU física real con el host: el benchmark mide
throughput agregado bajo la contención real del momento exacto del
arranque, no una propiedad fija del hardware. Confirmado el
2026-09-15: `bryam-local` (14 vCPUs) aparecía en `cpu_score=3.692`, por
debajo de `bryam-parrot` (solo 8 vCPUs, `cpu_score=4.247`) — inversión
real, no un bug de lectura, explicada por la misma contención (más
procesos del benchmark compitiendo por menos CPU física real disponible
en el host da *peor* throughput agregado, la pérdida de eficiencia bajo
carga que este benchmark existe para capturar, ver la entrada original
de `cpu_score`). Verificado que `bryam-local` llevaba encadenando
corridas de `GCR_He bin7` sin pausa desde su registro inicial — el
worker nunca se reinició a sabiendas del usuario; el número simplemente
refleja lo que midió el benchmark en el momento en que ese proceso
arrancó, que puede no coincidir con mediciones anteriores de la misma
máquina. `REFERENCE_CPU_SCORE=4.461` en `db.py` es la constante fija
elegida el 2026-09-14 a partir de UNA de esas lecturas — no se
recalcula ni necesita cambiar solo porque una lectura posterior de la
misma máquina dé un número distinto; sigue siendo un punto de
referencia válido para escalar estimaciones. **Riesgo real que esto
expone, no resuelto aquí:** `bryam-local` a 3.692 está peligrosamente
cerca de `MIN_CPU_SCORE=3.0` — un reinicio futuro bajo más contención
podría dejarla por debajo del umbral y excluirla de bin6/7 sin que nada
haya cambiado en el hardware real. Sin mitigación implementada (ej. no
recalcular en cada reinicio, o promediar varias mediciones) — anotado
como pendiente, no urgente mientras `bryam-local` siga corriendo sin
reiniciarse.

**Aplicado también retroactivamente en la DB real**
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

### Tres correcciones más el mismo día: estimado visible en jobs done, hora de completado, y bug real de migración (2026-09-14)

**`estimated_duration_s` desaparecía justo al terminar un job — exactamente
cuando más interesa compararlo con `actual_duration_s`.** `GET
/api/v1/jobs` (`app.py`) solo lo calculaba para `status IN ('claimed',
'running')`; extendido a incluir `'done'` — `claimed_by` se conserva en
la fila después de completarse (`record_result()` nunca lo limpia), así
que sigue disponible para recalcular con el `cpu_score` **actual** de
ese worker (no el que tenía en el momento exacto de esa corrida en
particular, que no se guarda por separado — una limitación aceptada, no
resuelta). Dashboard: la celda de "Duración" para un job `done` ahora
muestra `actual_duration_s` (etiquetado "real") junto al estimado
(etiquetado "est."), permitiendo ver de un vistazo qué tan buena fue la
estimación para esa corrida específica.

**Campo "Completado" agregado al detalle expandible, junto a
`claimed_at`/`created_at`** — pedido del usuario tras preguntar si la
columna "Actualizado" (que usa `updated_at`) es la hora de completado o
otra cosa. Verificado leyendo el código antes de asumir: para el caso
normal (job termina bien, sin reintentos), `updated_at` SÍ es
exactamente el momento en que `record_result()` lo marcó `'done'` — nada
lo vuelve a tocar después. Decisión explícita del usuario: no duplicar
como columna nueva en la tabla (ya que el valor coincide con
"Actualizado" hoy), sino como campo adicional en el detalle expandible,
con nombre explícito y un tooltip que aclara la equivalencia — más claro
de un vistazo sin ensuciar la tabla principal con una columna redundante.
Solo aparece cuando `status === "done"` (para otros estados, "Completado"
no tiene sentido).

**Bug real encontrado en producción al aplicar el deploy de la ronda
anterior — no del mecanismo de `connected_s` en sí, sino de agregar una
columna nueva a jobs YA en curso.** El usuario reportó "la columna
Duración volvió a 0" tras el restart del servicio. Investigado con
datos crudos, no asumido: `connected_s` es una columna nueva
(`DEFAULT 0`) — dos jobs que ya llevaban horas `running` ANTES del
deploy (job 6, GCR_He bin7, `claimed_at` ~2.6h antes; job 137, GCR_He
bin6, ~40min antes) quedaron con `connected_s=0` por la migración, y
solo empezaron a acumular desde el momento del restart — a los ~10-13
minutos de haber reiniciado, mostraban solo esos ~10-13 min de progreso,
no las horas reales que ya llevaban. El mecanismo en sí funcionaba bien
hacia adelante (los ~760s/~817s ganados en esos minutos eran correctos)
— el problema fue específico de la transición job-en-curso→columna
nueva, no repetible salvo que se agregue otra columna con el mismo
patrón a jobs activos. Efecto práctico real: esto los hacía parecer
MENOS avanzados de lo que estaban, así que si acaso los protegía de un
reencolado prematuro, no los ponía en riesgo — pero sí hacía el número
mostrado incorrecto. **Corregido manualmente en la DB real** (decisión
explícita del usuario, ya que no hay heartbeats históricos exactos que
recuperar): `connected_s = tiempo de pared desde claimed_at` para esos
2 jobs específicos, como mejor aproximación disponible (razonable dado
que ninguno se había reencolado, así que probablemente estuvieron
conectados casi todo ese tiempo). Verificado tras la corrección: job 6
pasó a 9596s/21597s estimado (~44%), job 137 a 4261s/8666s (~49%) —
números coherentes con lo que el usuario reportó haber visto antes del
deploy. **Lección para futuros deploys que agreguen columnas con estado
acumulado a `jobs`:** si hay jobs `claimed`/`running` en el momento del
deploy, revisar si necesitan la misma corrección manual — no es
automático, hay que acordarse de hacerlo cada vez.

**Pregunta aparte del usuario, investigada y descartada como bug:** dos
workers (`bryam-parrot`, `laptop-fabiola`) aparecían corriendo jobs de
repetición 2 mientras repetición 0 todavía tenía 7 pending y repetición
1 tenía 28 — parecía violar el orden `repeticion ASC` recién arreglado.
Verificado con los datos reales: los 28 pending de repetición 1 eran
**todos** bin6/7 o SEP_p bin0/1, todos con `min_ram_gb=8.0` exigido —
`bryam-parrot` tenía solo 1.61GB de RAM libre en ese momento y
`laptop-fabiola` 4.89GB, ninguno alcanzaba el mínimo. Comportamiento
correcto, no un bug: exactamente lo que el usuario ya había pedido antes
("si una laptop no tuviera jobs de la repetición actual adecuados,
recién pasar a la siguiente") — sin nada elegible en repetición 1 por
falta de RAM libre, el sistema correctamente ofreció lo mejor disponible
en repetición 2 en vez de dejar al worker sin trabajo. El problema real,
si lo hay, es de esas dos laptops teniendo poca RAM libre en ese
momento — externo al coordinator, no algo que corregir ahí.

**Consecuencia real de esa misma investigación: SEP_p bin0/bin1
compartían los umbrales de GCR pese a ser mucho más baratos —
corregido con umbrales propios.** El usuario notó, viendo por qué esos
28 jobs de repetición 1 quedaban inaccesibles, que `SEP_p` bin0/bin1
tenían exactamente el mismo `min_ram_gb=8.0`/`min_cpu_score=3.0` que
`GCR_H` bin6 o `GCR_He` bin7 — pese a que `REFERENCE_TIMINGS_S` (`db.py`)
ya mostraba que son muchísimo más livianos: SEP_p bin0 = 832.4s
(~13.9min), bin1 = 368.5s (~6.1min), contra GCR_H bin6 = 1820.4s
(~30min) o GCR_He bin7 = 18780.4s (~5.2h). Ambos umbrales venían del
mismo `needs_resources`/`MIN_RAM_GB`/`MIN_CPU_COUNT`/`MIN_CPU_SCORE`
compartidos en `job_priority_and_requirements()`, sin distinguir cuánto
más pesado era cada caso. **Corregido con `SEP_MIN_RAM_GB=2.0`/
`SEP_MIN_CPU_COUNT=2`/`SEP_MIN_CPU_SCORE=1.0`**, separados de
`MIN_RAM_GB`/`MIN_CPU_COUNT`/`MIN_CPU_SCORE` (que siguen aplicando solo
a GCR_H/GCR_He) — deja pasar a casi cualquier worker real conocido
(incluso `eddy-laptop`, `cpu_score=1.247`), sin bajar a 0/0/0 del todo
por si alguna máquina fuera genuinamente muy limitada. **Aplicado
también retroactivamente** (mismo criterio que el ajuste de
`MIN_CPU_SCORE` anterior): `UPDATE` directo en la VM real sobre los 44
jobs `pending` de SEP_p bin0/bin1 — verificado vía la API pública, sin
cambiar `jobs_pending` total ni afectar los 3 jobs `running`.

### Bug real de producción: un job pesado sin umbral terminó en el worker más lento (2026-09-14)

**Reportado por el usuario con un caso real: `eddy-laptop` (`cpu_score
1.247`, el más lento de los workers conocidos) reclamó `job_id=137`
(GCR_He bin6, repetición 2), estimado en ~7h en esa máquina.** Verificado
leyendo la fila real en la DB de producción: `min_ram_gb=0.0`,
`min_cpu_count=0`, `min_cpu_score=0.0` — sin ningún umbral, así que
`claim_next_job()` lo ofrecía a cualquier worker sin filtrar. El
emparejamiento por `cpu_score` (`pick_job_for_worker()`, ver la entrada
"Criterio de asignación de jobs" más arriba) solo reordena ENTRE
candidatos ya elegibles del mismo grupo `(repeticion, priority)` — nunca
excluye a un worker lento si de todos modos es el único que preguntó en
ese momento, y sin ningún umbral, cualquier worker califica.

**Alcance real, verificado con una consulta completa, no solo este job:**
27 jobs en total (bin6/7 de GCR_H/GCR_He, bin0/1 de SEP_p) tenían
`min_cpu_score=0` — 26 ya `done` (sin consecuencia práctica a esta
altura, probablemente cayeron en máquinas capaces por casualidad) y
`job_id=137` era el único todavía `running`. Estos son remanentes de un
lote de siembra anterior a que `job_priority_and_requirements()`
existiera con su forma actual — el `UPDATE` retroactivo de la ronda
anterior (que corrigió 123 jobs `pending` sin `min_cpu_score`) no los
alcanzó porque en ese momento estos ya estaban `done`/`running`, fuera
del filtro `WHERE status='pending'` que se usó entonces.

**Sin mecanismo para cancelar un job remoto específico — limitación de
diseño ya documentada, confirmada de nuevo aquí.** El worker solo hace
polling saliente, sin canal de entrada (ver "El coordinator no tiene
ningún canal para instruir a un worker remoto..." más arriba) — no
existe un endpoint "detener este job en esa máquina". **Decisión
explícita del usuario, dado que el avance perdido era mínimo (38.6min
conectados de ~7h estimadas):** no tocar el worker `eddy-laptop` en
absoluto — sigue corriendo su copia local de Geant4 sin que el
coordinator lo sepa. Solo se reencoló el job (`status='pending'`,
`claimed_by=NULL`, `connected_s=0`, `attempt` preservado en 2) para que
otro worker lo reclame de inmediato. Cuando `eddy-laptop` eventualmente
termine su corrida local y suba el resultado, `submit_result()` lo
rechaza con `409` (otro worker ya es dueño) — descartado limpiamente por
el fix de manejo de `HTTPError` ya aplicado hoy mismo (ver "Bug de logs
corregido de paso" más arriba), sin cómputo real perdido salvo esos
38.6min y sin ningún dato corrupto.

**Corregido de raíz:** `job_id=137` actualizado con
`min_ram_gb=8.0`/`min_cpu_count=4`/`min_cpu_score=3.0` (mismos umbrales
que sus jobs hermanos de bin6), para que la próxima asignación ya no
pueda caer en un worker sin la capacidad mínima. Los 26 casos `done` se
dejan tal cual — no hay nada que corregir en un job ya completado.
Pendiente real, no resuelto en este cambio: no hay una garantía
automática de que un futuro `seed_full_sweep.py --bins ...` con alcance
parcial, o una `replicate_repeats.py` corrida antes de que
`job_priority_and_requirements()` tuviera su forma actual, no vuelva a
producir jobs sin umbral — la corrección fue puntual sobre los 27 casos
encontrados, no un cambio de esquema que lo prevenga estructuralmente
(ej. un `NOT NULL DEFAULT` con un valor mínimo, o una validación en
`insert_job()` que rechace `min_cpu_score=0` para bins conocidos como
pesados).

### Remote-kill de un job en curso (2026-09-14)

**Pedido directo del usuario tras el incidente de arriba:** poder
detener un job a mitad de una corrida y reasignarlo, sin depender de
esperar el heartbeat vencido ni tocar el worker a mano. Pidió
explícitamente reusar el mecanismo de auto-actualización Docker "si es
que es necesario", y que el mecanismo NO se muestre en el dashboard.

**Investigado antes de diseñar: el mecanismo de auto-actualización no
sirve para esto, y no hay nada real que "reusar" de ahí más allá del
patrón de hilo separado.** `auto_update()` solo se revisa una vez por
vuelta del loop principal, ANTES de pedir el siguiente job (`if
os.environ.get("WORKER_AUTO_UPDATE"...) and auto_update(worker_id):` en
`run_worker_loop()`) — nunca mientras un job corre. `run_job()` bloquea
el hilo entero en `process.communicate()` hasta que el subprocess de
Geant4 termina solo; nada revisa nada más durante ese tiempo. El propio
protocolo de standby (candidato, `flock`, rename atómico) resuelve un
problema distinto por completo — reemplazar el CONTENEDOR/imagen, no
interrumpir un SUBPROCESS que ya está corriendo dentro de uno — así que
no hay lógica de esa parte que se pudiera reusar directamente. Lo único
genuinamente reusable es el patrón "hilo daemon separado corriendo en
paralelo al trabajo bloqueante" que ya usa `heartbeat_loop()` — y eso es
exactamente lo que se necesitaba de todos modos.

**Diseño: la señal viaja en la respuesta del heartbeat ya existente, no
por un endpoint de polling nuevo.** El worker ya manda heartbeat cada
30s desde su propio hilo (`heartbeat_loop`, ya corriendo en paralelo a
cualquier job activo desde antes de este cambio) — agregar la
verificación ahí es gratis en tráfico de red, y el hilo ya existe
exactamente donde hace falta (corriendo en paralelo al
`subprocess.communicate()` bloqueante de `run_job()`).

- **`jobs.cancel_requested`** (columna nueva, migración idempotente) — un
  flag sobre el job, no un `status` nuevo: el job sigue `'running'` hasta
  que el worker reporte el resultado real (cancelado = fallo), igual que
  cualquier otro desenlace — evita que el dashboard, `pick_job_for_worker`,
  `requeue_stale_jobs`, etc. tengan que aprender un valor de `status`
  más.
- **`request_job_cancel(job_id)`** (`db.py`) — acción administrativa,
  exige `status IN ('claimed','running')` con `claimed_by` no vacío
  (nada que cancelar en un job `pending`/`done`/`failed`); devuelve el
  `worker_id` que recibirá la señal, o `None` si no aplica.
- **`cancelled_job_for_worker(conn, worker_id)`** — job_id del job activo
  de ese worker si tiene `cancel_requested=1`, `None` si no. Recibe una
  conexión existente (se llama DENTRO de la transacción de
  `touch_heartbeat()`, no abre la suya propia) — un worker nunca tiene
  más de un job `claimed`/`running` a la vez, así que no hace falta que
  mande su `job_id` en el heartbeat para desambiguar cuál.
- **`touch_heartbeat()` devuelve `{"cancel_job_id": int | None}`** en vez
  de un `bool` — cambio de contrato deliberado (verificado que ningún
  test existente asumía el `bool` viejo, los 78 tests previos siguen
  pasando sin tocar). `POST /api/v1/workers/{id}/heartbeat` (`app.py`)
  expone ese campo en la respuesta JSON.
- **`POST /api/v1/jobs/{job_id}/cancel`** (`app.py`, nuevo) — `404` si el
  job no existe, `409` si no está `claimed`/`running` con worker
  asignado, `200` con `{job_id, claimed_by, status: "cancel_requested"}`
  si acepta. Fuera de `_PUBLIC_PATHS` — ya protegido por
  `X-Worker-Token` si `WORKER_TOKEN` llega a activarse, mismo criterio
  que cualquier otro endpoint administrativo.
- **`_cancel_event`** (`worker.py`, nuevo, `threading.Event` a nivel de
  módulo) — un worker corre un solo job a la vez (loop secuencial, ya
  confirmado), así que un solo `Event` de proceso alcanza, sin indexar
  por `job_id`. `heartbeat_loop()` lo activa si `heartbeat()` devuelve un
  `cancel_job_id` no nulo (no ambiguo: el coordinator solo lo manda si
  hay un job de ESE worker marcado, nunca el de otro). `run_job()` lo
  limpia al EMPEZAR cada job nuevo (no al terminar el anterior — evita
  una condición de carrera donde el hilo watcher todavía no terminó de
  actuar cuando el hilo principal llega al final de `run_job()`).
- **Hilo watcher dedicado dentro de `run_job()`** (mismo patrón que
  `heartbeat_loop`, con su propio `stop_watching` para no seguir vivo
  entre jobs) — sondea `_cancel_event` cada 1s mientras
  `process.communicate()` bloquea el hilo principal; al verlo activo,
  manda `SIGTERM` al process group directamente. El `finally` existente
  (que ya hacía `SIGTERM`→espera→`SIGKILL` para el caso de una excepción
  normal) queda intacto como red de seguridad si el proceso no responde
  al primer `SIGTERM` del watcher — sin duplicar lógica de matado, solo
  se agregó el disparador nuevo.
- **`cancel_job.py`** (`infra/coordinator/`, nuevo) — a diferencia de
  `seed_jobs.py`/`set_worker_image.py` (escriben directo a la SQLite del
  servicio, pensados para correr en la VM), este pasa por la API real
  (`requests.post` contra `--coordinator-url`, default el de
  producción): la señal tiene que llegar al PROCESO del coordinator ya
  corriendo, no solo a su archivo de base de datos, para que el próximo
  heartbeat la recoja a tiempo — un `UPDATE` directo sobre una copia de
  la DB, o incluso sobre la DB real sin pasar por el proceso, funcionaría
  igual (SQLite se lee fresco en cada request), pero ir por la API es
  más simple y no exige acceso SSH a la VM para usarlo.

**A propósito NO en `dashboard.html`** (pedido explícito del usuario) —
el dashboard es de solo lectura, sin autenticación; un botón de cancelar
ahí sería una acción destructiva expuesta a cualquiera con el link.

**Verificado en vivo, no solo con tests unitarios:** servidor `uvicorn`
real — `POST /cancel` en un job `running` devuelve `200` y marca el
flag; el heartbeat del worker asignado inmediatamente después devuelve
`cancel_job_id` correcto; `cancel` sobre un job desconocido da `404`;
sobre uno `pending` sin worker asignado da `409`; `cancel_job.py` mismo
probado end-to-end contra ese servidor con los mismos tres casos.
`run_job()` probado con un subprocess real de larga duración (`sleep
30`, no Geant4) — el test mide tiempo de reloj real y confirma que
termina en <10s en vez de esperar los 30s completos, prueba de que el
`SIGTERM` del watcher efectivamente mata el proceso, no solo que la
lógica "se ve bien" en el código. 6 tests nuevos en `test_coordinator.py`
(53 en total) cubren `request_job_cancel`/`cancelled_job_for_worker`/el
nuevo contrato de `touch_heartbeat` y que `cancel_requested` se limpia
al reportar el resultado (para que el siguiente intento del mismo
`job_id` no nazca ya marcado). 1 test nuevo en `test_worker.py` (32 en
total) cubre el flujo completo
worker-side.

**Limitación aceptada, no resuelta aquí:** la tardanza real hasta que el
subprocess muere es de hasta `HEARTBEAT_INTERVAL_S` (30s), no
instantánea — aceptable para el caso de uso real (reasignar un job de
horas, 30s de margen es irrelevante), pero no serviría para un caso que
necesitara corte inmediato. Reducir el intervalo de heartbeat solo para
esto no se consideró necesario — nadie pidió un corte más rápido que
eso.


### Revisión de cancelación y relevo Docker (2026-09-14)

Sustituye la descripción anterior de `_cancel_event` global: se usa contexto
por ejecución y comparación de job_id, capturado antes del heartbeat. Evita
respuestas tardías que cancelaban el siguiente job/intento. `active_job_id`
opcional en heartbeat selecciona el job correcto si hay varias asignaciones.
TERM tiene 2s de gracia seguido de KILL para el grupo, con manejo de proceso
ya terminado; la latencia incluye heartbeat, red y watcher, no un máximo duro
de 30s. Se limpia cancel_requested en timeout y al reclamar el nuevo intento.
Avisos /fail se persisten en pending_failures y bloquean nuevas asignaciones
hasta confirmación, preservándose con el volumen en reinicios y auto-update.
La API de cancelación comparte WORKER_TOKEN, sin rol administrativo separado;
no poner botón en dashboard no constituye control de acceso.

Revisado también el commit del relevo Docker: si replace(commit) funciona pero
falla el fsync del directorio, el sucesor ya autorizado no se elimina durante
rollback. El padre se retira y la recuperación del journal sigue el commit.
Fuentes e instrucciones actuales en infra/README.md e infra/deploy/README.md.

Revisión adicional de auto-update/outbox (2026-09-14): se añadieron escenarios
Docker A→B→A→B, caída del padre antes/después del commit y entrega pendiente
rechazada con 503 al padre y aceptada por el sucesor. Corregido borrado de outbox
por HTTP transitorio: conservar/reintentar 401/429/5xx; archivar rechazos finales
y vencimientos en unconfirmed_results, sin afirmar que el coordinator reasignó
el job solo por un reloj local. Escritura de CSV/manifiesto con temporales/fsync,
metadata final y preservación de entrada previa; reintento entre jobs. Detalles
y límites de los ensayos en infra/deploy/README.md.

### Bug real de producción: `install-worker.ps1` colgado antes de `[Paso 1/3]` -- Task Scheduler sacado del camino crítico (2026-09-14)

**Reportado con captura de pantalla real, diagnóstico externo preciso
verificado antes de aplicar nada.** Un voluntario corrió el instalador
para actualizar y la ventana quedó congelada antes de imprimir
`[Paso 1/3]` -- justo entre el banner inicial y el primer paso numerado.
Verificado leyendo el código exacto de esa región: `Unregister-
ScheduledTask -TaskName $ResumeTaskName -Confirm:$false -ErrorAction
SilentlyContinue` corría **incondicionalmente** ahí, sin importar si
`$isResume` era `true` o `false` -- en una actualización normal (el caso
real reportado) esa tarea nunca existió, así que no había nada que
desregistrar, pero la llamada se hacía de todos modos. `-ErrorAction
SilentlyContinue` no protege contra un cuelgue real del cmdlet (solo
suprime el error normal de "la tarea no existe") -- causa exacta en esa
PC específica sin confirmar (Task Scheduler local en estado raro,
WMI/CIM lento, antivirus interceptando la llamada), pero irrelevante
para el fix: cualquier causa queda cubierta.

**Primer intento, descartado explícitamente por el usuario: aislar la
llamada con un timeout (`Start-Job`+`Wait-Job`) sin cambiar CUÁNDO se
llama.** Funciona, pero dejaba `Get-ScheduledTask -TaskName
$ResumeTaskName` como la forma de detectar `$isResume` -- **ese mismo
cmdlet, con el mismo riesgo de cuelgue, seguía corriendo en cada
ejecución normal** para decidir si era una reanudación. El usuario pidió
explícitamente un fix permanente que sacara Task Scheduler del camino
crítico por completo, no solo mitigar el síntoma con un timeout.

**Rediseño completo aplicado, en 5 piezas, tal como las especificó el
usuario:**

1. **`-ResumeAfterWsl` (switch, parámetro interno no documentado en
   `.PARAMETER`)** reemplaza `Get-ScheduledTask -TaskName
   $ResumeTaskName -ErrorAction SilentlyContinue` para detectar
   `$isResume` -- la propia Scheduled Task de resume (`Register-
   ResumeTask`) pasa este flag como argumento al invocar el script tras
   el reinicio. Una ejecución normal (instalación nueva sin reinicio, o
   actualización) ya **no consulta Task Scheduler en absoluto** para
   decidir esto.
2. **`Unregister-ScheduledTaskSafe -TaskName $ResumeTaskName` tras el
   banner, ahora condicional a `$isResume`** (antes incondicional, la
   causa directa del cuelgue reportado) -- solo se intenta desregistrar
   cuando de verdad hay algo que limpiar.
3. **`Register-WatchdogTask` separada en dos funciones**:
   `Update-WatchdogScript` (escribe/actualiza `watchdog.ps1` en su ruta
   estable dentro de `$LogDir`, se llama SIEMPRE) y `Register-
   WatchdogTask` (registra la Scheduled Task en sí, solo en instalación
   nueva). Una actualización ya **no vuelve a tocar Task Scheduler para
   el watchdog** -- la tarea de la instalación original ya apunta a esa
   misma ruta estable, así que recoge el contenido nuevo de
   `watchdog.ps1` en su próximo disparo (login o el intervalo de 30 min)
   sin necesitar registrarse de nuevo. A diferencia del primer intento
   descartado (que sacrificaba refrescar el watchdog en cada
   actualización como tradeoff permanente), esta vía SÍ sigue
   actualizando el contenido del watchdog en cada actualización -- solo
   deja de tocar la Scheduled Task, que es la parte que puede colgarse.
4. **`Register-ScheduledTask -Force` sin `Unregister-ScheduledTask`
   previo**, tanto para la tarea de resume como para el watchdog --
   `-Force` ya reemplaza una tarea existente del mismo nombre, el
   desregistro previo nunca fue necesario.
5. **`$ResumePendingFile` (`resume.pending` en `$LogDir`)** hace
   tolerante la reanudación a una tarea huérfana -- si Windows llegara a
   fallar al desregistrar `$ResumeTaskName` (paso 2, todavía protegido
   con `Unregister-ScheduledTaskSafe` con timeout, ya no crítico si
   tarda), esa tarea podría disparar el script de nuevo en un login
   FUTURO sin relación con el reinicio original. `Register-ResumeTask`
   crea el marcador antes de reiniciar; el flujo principal lo exige
   ADEMÁS de `-ResumeAfterWsl` para aceptar la reanudación como real, y
   lo borra al consumirla -- una tarea huérfana que dispare después
   encuentra el marcador ausente y sale de inmediato sin instalar ni
   actualizar nada.

**`Unregister-ScheduledTaskSafe` (el helper con timeout del primer
intento) se conserva**, no se descarta -- sigue siendo la forma correcta
de hacer la limpieza real que aún hace falta (`Uninstall-Worker`
desregistrando ambas tareas; el paso 2 de arriba) — esos puntos ya no
son críticos para completar la instalación si Task Scheduler tarda,
así que el timeout ahí es una mejora de robustez adicional, no la
defensa principal.

**Bug de testing real encontrado y corregido en el proceso, no solo el
fix de producción:** `Start-Job` arranca un runspace/proceso completamente
nuevo -- un mock de `Unregister-ScheduledTask` definido en el scope del
test **nunca era visible dentro del Job**, confirmado verificándolo de
forma aislada (`$global:events` dentro del job daba `$null`). El test
existente pasaba igual porque no había ningún assert verificando que la
desregistración *ocurriera* de verdad, solo que el escenario completo no
lanzara una excepción -- un test que pasaba sin probar nada real.
Corregido reemplazando `Unregister-ScheduledTaskSafe` completa (no solo
el cmdlet) por una versión síncrona sin `Start-Job` dentro del test, y
agregando asserts nuevos que sí verifican `task:watchdog`/`task:resume`
en los eventos capturados.

**Segundo bug de testing encontrado al escribir el test nuevo para
`-ResumeAfterWsl`/`$ResumePendingFile`:** un `return` dentro de
`Invoke-Expression` **no sale de la función que la invoca** -- solo
termina la evaluación de esa cadena, el resto del cuerpo de la función
sigue normal (confirmado con un experimento aislado mínimo). El primer
diseño del test asumía que `return` cortaría camino igual que en el
flujo real de nivel superior (donde sí termina el script completo) --
corregido verificando en cambio que el código que va DESPUÉS del
`return` (`$isResume = ...`) nunca llegó a ejecutarse
(`Test-Path variable:isResume`), que es la forma correcta de observar el
mismo efecto sin depender de una semántica de `return` que
`Invoke-Expression` no reproduce.

**3 tests nuevos/reforzados en `test_worker_lifecycle.ps1` (20 en
total, antes 17):** dos asserts nuevos en el escenario ya existente de
`Uninstall-Worker` exitoso (`task:watchdog`/`task:resume` genuinamente
invocados); un escenario nuevo completo para `-ResumeAfterWsl` con tres
casos -- tarea huérfana (`-ResumeAfterWsl` sin marcador, `$isResume`
nunca se fija), reanudación real (`-ResumeAfterWsl` con marcador,
`$isResume=true`, marcador se borra), y ejecución normal (sin el flag,
`$isResume=false`). Sintaxis validada de punta a punta tras el
rediseño completo.

### Worker "elite": salta el orden de repetición para aprovechar una máquina muy rápida conectada toda la noche (2026-09-14)

**Pedido explícito del usuario:** `tania` (`cpu_score=18.07`, más de 4x
el segundo mejor worker conocido, `bryam-parrot` con 4.2) se mantendría
conectada toda la noche — el usuario quiso asegurar avance en los jobs
más pesados del barrido (GCR_He bin6/7 sobre todo) aprovechando esa
ventana, sin importar la repetición. El emparejamiento por `cpu_score`
ya existente (`pick_job_for_worker()`, ver entrada de arriba "Criterio
de asignación de jobs") solo reordena **dentro** de un
`(repeticion, priority)` ya fijado por el orden estricto de
repeticiones en serie (ver "Bug real corregido: repeticiones corriendo
en paralelo") — así que aunque `tania` sea rapidísima, si la repetición
más baja con trabajo pendiente solo tenía jobs livianos, eso era lo
único que se le podía ofrecer, sin importar cuánto trabajo pesado
esperaba en repeticiones más altas.

**`ELITE_WORKER_CPU_SCORE_THRESHOLD = 10.0`** (`db.py`, nuevo,
confirmado con el usuario) — deliberadamente muy por encima de
`FAST_WORKER_CPU_SCORE_THRESHOLD` (4.461, la máquina de referencia):
deja fuera a cualquier worker "rápido" normal conocido (el siguiente
mejor tras `tania` es 4.2, muy por debajo). `claim_next_job()` ahora
bifurca antes de fijar `(repeticion, priority)`: un worker con
`cpu_score` real (no el fallback "infinito" de un worker sin
telemetría — verificado explícitamente con `worker["cpu_score"] is not
None`, para que "infinito" nunca califique como élite por accidente)
igual o mayor a ese umbral se salta el orden por repetición por
completo y recibe directamente el job pendiente con mayor
`REFERENCE_TIMINGS_S` de **todo el sistema** (cualquier repetición),
siempre que sus recursos (`min_ram_gb`/`min_cpu_count`/`min_cpu_score`)
alcancen — reusa `pick_job_for_worker()` sin modificarlo (ya hace
`max(candidates, key=weight)` para cualquier worker "rápido", y un
worker élite siempre lo es), solo cambia el conjunto de candidatos que
se le pasa (todos los `pending` elegibles, no solo los del grupo ya
fijado). Un worker no-élite nunca entra a esta rama — el fix de
repeticiones en serie sigue intacto para todos los demás.

**5 tests nuevos en `test_coordinator.py` (59 en total):** un worker
élite cruza a una repetición más alta cuando ahí está el job más
pesado; elige el más pesado entre varias repeticiones con pesos
mezclados (no solo la repetición más alta ni la de inserción más
reciente); un worker sin `cpu_score` (`None`, cae a "infinito"
internamente) nunca se trata como élite y sigue el camino normal; un
worker élite sigue respetando los umbrales de recursos del job (recibe
el siguiente más pesado que sí pueda satisfacer si el más pesado de
todos exige más RAM de la que tiene libre). Desplegado en producción
con el mismo procedimiento de siempre (`git pull` + `systemctl restart
geant4-coordinator`) — cambio puro de `db.py`, sin migración de schema
ni imagen Docker nueva.

### Bug real de producción: cómputo huérfano tras un reencolado manual sin señalizar al worker (2026-09-15)

**Reportado por el usuario con datos exactos del dashboard:** `laptop-liz`
mostraba heartbeat vivo (hace 5s), 98.7% CPU, 33.8h de antigüedad — pero
**sin ningún job `claimed`/`running` asignado en la DB**. Investigado:
`GET /api/v1/jobs` confirmó que los 4 jobs `running` del sistema
pertenecían a otros workers (`laptop-fabiola`, `tania`, `bryam-local`,
`eddy-laptop`); `laptop-liz` no tenía ninguno.

**Causa raíz, consecuencia directa no anticipada de una intervención
manual anterior en esta misma sesión:** minutos antes, se habían
reencolado a mano 3 jobs de `laptop-liz` (134/470/472) con un `UPDATE`
directo sobre la SQLite de producción (mismo patrón ya usado para el
job huérfano `job_id=3` documentado más arriba) — ese `UPDATE` cambia
lo que la DB *dice*, pero **no manda ninguna señal al proceso worker
real**. El remote-kill (`cancel_job.py`) sí se había intentado antes de
eso, pero solo puede cancelar el job que el coordinator identifica como
el ACTIVO de ese worker (`cancelled_job_for_worker()`) — con 3 jobs
asignados a la vez a `laptop-liz` (un estado ya fuera de lo normal, un
worker solo debería tener uno), la cancelación remota no alcanzó a
todos. Resultado: `laptop-liz` siguió corriendo el subprocess de Geant4
de uno de esos 3 jobs sin enterarse de que el coordinator ya se lo
había reencolado a otro worker — cómputo real corriendo sin ningún job
que lo reclame en la base de datos.

**Diagnóstico intentado, limitación real encontrada:** el usuario pidió
identificar CUÁL de los 3 jobs seguía corriendo antes de decidir
reasignarlo (evitar perder ese cómputo). Investigado: el worker YA
manda su `active_job_id` real en cada heartbeat
(`_active_cancel`/`heartbeat()` en `worker.py`, existente desde el
diseño de remote-kill) — pero `touch_heartbeat()` en `db.py` solo lo
usaba DENTRO de la misma transacción para decidir si cancelar
(`cancelled_job_for_worker(conn, worker_id, active_job_id)`), sin
persistirlo nunca. No había ninguna forma de consultar por API qué job
cree un worker que tiene activo — la única opción era adivinar o
acceder a la máquina.

**Corregido:** `workers.active_job_id`/`active_job_reported_at`
(columnas nuevas, migración idempotente) — `touch_heartbeat()` ahora
escribe `active_job_id` TAL CUAL llega en cada heartbeat, a diferencia
de `ram_free_gb`/`cpu_load_pct`/`image_digest` (que usan `COALESCE` y
conservan el último valor si el heartbeat no trae uno nuevo):
`active_job_id` debe reflejar el estado real ACTUAL, incluyendo `NULL`
explícito cuando el worker no tiene nada corriendo — conservar el
último valor conocido habría ocultado exactamente este bug (un worker
sin job real seguiría mostrando el último `active_job_id` que alguna
vez reportó). `list_workers()`/`GET /api/v1/workers` ya usan
`SELECT *`/`row_to_dict()` sin filtrar columnas, así que el campo queda
expuesto sin tocar `app.py`. 1 test nuevo en `test_coordinator.py` (60
en total): confirma que un `active_job_id=None` explícito borra el
valor anterior, no lo conserva.

**Sin resolver todavía cuál de los 3 jobs (134/470/472) es el que
`laptop-liz` sigue corriendo** — este fix agrega la instrumentación
para diagnosticarlo (una vez desplegado, el próximo heartbeat de
`laptop-liz` lo revelará vía `GET /api/v1/workers`), pero no reasigna
nada todavía; eso es el paso siguiente una vez confirmado el valor
real. Cuando ese subprocess termine y el worker intente subir el
resultado sin tener el job asignado, `submit_result()` lo rechazará con
`409` — descartado limpiamente por el fix de manejo de `HTTPError` ya
documentado más arriba ("Bug de logs corregido de paso"), sin dato
corrupto, solo el cómputo de esa corrida específica perdido si no se
reasigna a tiempo.

### Bug real de `aggregate_organ_doses.py`: repeticiones parciales mezcladas al calcular std/barra de error (2026-09-15)

**Pedido del usuario: un CSV que use SOLO la repetición 0 (sin mezclar
con otras), y desconfianza correcta sobre el `resultados_riesgo_
estocastico_repeticiones.csv` generado antes** ("no me sirve
promediado, quiero std/barra de error con las 5 runs"). Investigando el
código para dar el CSV de rep0, se encontró un bug real en la vista de
estadística entre repeticiones (no en la vista pooled, que sí es
correcta para su propósito de mejor punto estimado).

**Causa raíz:** el bucle que arma `d_eq_gcr_by_rep`/`d_eq_sep_by_rep`
por repetición hacía `if key_rep not in n_events_by_run_rep: continue`
— esto saltaba silenciosamente cualquier combinación `(especie,bin)`
faltante de una repetición, en vez de excluir la repetición ENTERA de
ese cálculo. Con las repeticiones 1-3 parcialmente completas en
producción (ver "Bug real de producción: cómputo huérfano" arriba, y
el estado real de la cola: rep0=120/120 done, rep1=103/120, rep2=100/120,
rep3=1/120), el script armaba un promedio "Frankenstein" por repetición
— cada una usando solo los bins que le tocaron llegar — y reportaba
`n_repeticiones=4` como si las 4 fueran comparables, cuando en realidad
ninguna salvo la 0 estaba completa. El std/CV resultante mezclaba
repeticiones con cobertura desigual sin ningún aviso.

**Corregido:** una repetición ahora solo se incluye en el cálculo de
std/SEM/IC95%/CV de una fila `(categoría, offset_x_m)` si tiene **todas**
las combinaciones `(especie, bin_idx)` necesarias para ese offset —
verificado con `all((rk, rep) in n_events_by_run_rep for rk in
run_keys)` antes de usarla, no combinación por combinación. `n_repeticiones`
en el CSV de salida ahora refleja cuántas repeticiones **realmente
completas** entraron en ESA fila específica (`n_complete_reps`), no
`len(reps_seen)` global (que solo contaba "en cuántas apareció al menos
un dato"). El mensaje final ya no advierte solo si `len(reps_seen) < 2`
(engañoso, contaba repeticiones parciales como si fueran completas) —
ahora imprime cuántas repeticiones aparecen en los CSV de entrada,
aclarando explícitamente que cada fila usa solo las completas.

**Verificado con un caso sintético** (3 repeticiones completas para una
sola combinación): `n_repeticiones=3` con std real (no vacío). **Con
los datos reales de producción** (solo rep0 completa hoy): las 30 filas
(6 categorías × 5 offsets) dan `n_repeticiones=1`, std/SEM/IC95%/CV en
blanco como corresponde (`n<2`) — antes del fix, daban `n_repeticiones=4`
con una "barra de error" calculada sobre datos parciales sin avisar.

**Archivos regenerados en `geant4/ActiveShield_Sim/resultados/`**,
renombrados explícitamente para no confundir cuál es cuál:
`resultados_organo_agregados_rep0.csv`/`resultados_riesgo_estocastico
_rep0.csv`/`_repeticiones_rep0.csv` (solo repetición 0, filtrada a mano
antes de pasarla al script — pedido explícito del usuario, sin mezclar)
vs. `..._pooled_todas_las_reps.csv` (todas las repeticiones disponibles,
sumando eventos para el mejor punto estimado, sin barra de error válida
todavía porque ninguna combinación tiene ≥2 repeticiones completas). Se
eliminaron los CSV generados antes del fix (`resultados_organo_
agregados_completo.csv` y el `resultados_riesgo_estocastico*.csv` sin
sufijo de esa corrida) por tener el `n_repeticiones`/std incorrectos.

**Pendiente real, no resuelto aquí:** cuando las repeticiones 1-4 se
completen del todo, volver a correr `aggregate_organ_doses.py` sobre el
conjunto completo para obtener la barra de error real de 5 repeticiones
que el usuario pidió — hoy solo hay 1 repetición completa, matemáticamente
no hay std que calcular todavía.

### Dashboard: columnas ordenables y filtros de inclusión/exclusión multi-valor (2026-09-16)

**Pedido explícito del usuario, con la aclaración correcta de que es un
cambio de solo frontend:** los `<select>` de un solo valor por columna
(especie/bin/offset/repetición) no permitían elegir varios a la vez ni
excluir — el caso concreto que motivó el pedido fue "no quiero ver los
bins 6 y 7". Confirmado antes de tocar nada: el dashboard ya trae todos
los jobs de una sola vez vía `GET /api/v1/jobs` y filtra/ordena en el
propio navegador — nada de esto requiere tocar `db.py`/`app.py` ni pedir
nada nuevo al servidor.

**Filtros multi-select con include/exclude:** cada columna filtrable
(Estado, Especie, Bin, Offset X, Repetición) pasó de un `<select>` a un
dropdown propio (`.msel`) con un checkbox por valor posible y un toggle
Incluir/Excluir arriba — `MSEL_STATE[field] = {mode, values: Set}`,
donde `values` vacío (en cualquier modo) significa "sin filtro", el
mismo default de antes. `matchesMsel()` reemplaza las comparaciones
directas de valor único que tenía `matchesFilters()`. Botones "Todos"/
"Ninguno" dentro de cada panel para no tener que clickear cada opción
una por una. Un solo panel abierto a la vez (cierra los demás al abrir
uno, y al hacer click fuera).

**Columnas ordenables por click en el header, ascendente/descendente:**
`ID, Estado, Especie, Bin, Offset X, Rep., Asignado a, Duración,
Intento, Actualizado` — las mismas columnas de la tabla, ver la captura
que dio el usuario. Un solo click ordena ascendente, un segundo click en
la misma columna invierte a descendente, un tercer click **vuelve al
orden por defecto** (no a un estado arbitrario) — implementado como
`sortState.field = null` en vez de fijar explícitamente
`{field:"status", dir:"asc"}`, para que el default (ver abajo) sea
exactamente el mismo camino de código que corría antes de que las
columnas fueran ordenables, no una reconstrucción aproximada.

**Orden por defecto preservado exactamente como pidió el usuario:**
estado como primera condición (`running`/`claimed` primero, luego
`failed`, `pending`, `done` al final) y `job_id` descendente como
segunda condición — es el mismo `statusOrder` que ya existía, ahora
nombrado `DEFAULT_STATUS_ORDER` y reutilizado tanto para el default como
para lo que ordena la propia columna "Estado" cuando se clickea
explícitamente. La columna "Duración" ordena por el mismo número que ya
se muestra en pantalla (`connected_s` para un job activo,
`actual_duration_s` para uno `done`, ver `runningCellHtml()`) — para que
"ordenar por duración" no confunda mostrando un criterio distinto al que
el usuario ve en la celda. Desempate: por `job_id` en la dirección que
esa columna esté ordenada (no siempre descendente) cuando el usuario
elige la columna explícitamente — solo el default implícito usa el
desempate `job_id DESC` original.

**Verificado sin navegador headless disponible en este entorno:** HTML
balanceado (parser propio, sin tags huérfanos), JS sintácticamente
válido (`node --check`), y la lógica pura de filtrado/ordenamiento
(`sortValueFor`/`compareJobs`/`matchesMsel`) extraída y corrida con
datos sintéticos en Node — confirmado el orden por defecto exacto, ambas
direcciones de una columna numérica, exclusión de bins 6/7 (el caso
concreto pedido), inclusión de varias especies, y que "sin filtro"
sigue mostrando todo. Desplegado actualizando solo `dashboard.html` en
la VM (`git pull`, sin `systemctl restart` — `GET /dashboard` sirve el
archivo con `FileResponse`, leído del disco en cada request, no
cacheado en memoria del proceso).

**Simplificado el mismo día, dos correcciones de UX pedidas tras probarlo:**
(1) el toggle explícito Incluir/Excluir se quitó — el usuario señaló que
alcanza con un solo botón "Seleccionar todo"/"Deseleccionar todo": para
excluir bins 6/7 se selecciona todo y se desmarcan esos dos, para
incluir solo un subconjunto se deselecciona todo y se marcan los que
interesan. `MSEL_STATE[field]` pasó de `{mode, values}` a un `Set`
simple; el botón cambia su propio label según si ya está todo marcado
(`allSelected`), sin necesitar dos botones separados. (2) **bug real
encontrado al probarlo**: el panel se cerraba solo cada vez que se
marcaba un checkbox — el listener global `document.addEventListener
("click", cerrarTodo)` (necesario para cerrar el dropdown al hacer click
afuera) capturaba también los clicks *dentro* del panel abierto, porque
el evento burbujea hasta `document` sin que nada lo detuviera ahí (solo
el botón que abre el dropdown llamaba `stopPropagation()`, no el panel
en sí). Pedido explícito del usuario: poder marcar varios checkboxes
seguidos sin que la ventana se cierre después de cada uno. Corregido
con `panel.addEventListener("click", e => e.stopPropagation())` sobre
el panel completo — un click en cualquier checkbox o en "Seleccionar
todo" ya no llega al listener global. El filtrado en vivo (ya
funcionaba, sin bug) se conserva intacto: cada `change` de un checkbox
sigue llamando `renderJobs()` de inmediato.

**Orden multi-columna, mismo día, pedido explícito del usuario:**
"¿qué pasa si quiero ordenar las especies de manera descendente y los
bins de manera ascendente?" — con el diseño anterior (`sortState` como
un único `{field, dir}`), clickear una columna nueva descartaba
cualquier orden ya activo en otra. Corregido: `sortState` pasa a ser
una **lista** de `{field, dir}`, no un solo criterio — clickear un
header nuevo lo agrega al final (prioridad más baja que las columnas ya
activas), clickear uno ya activo rota su dirección (asc→desc) sin
moverlo de posición, y un tercer click en esa misma columna la saca de
la lista por completo sin tocar las demás. `sortJobs()` recorre la
lista en orden, probando cada criterio hasta encontrar uno que
desempate — mismo desempate final por `job_id` que ya existía.
`updateSortHeaderUI()` muestra el número de prioridad (▲1, ▼2, ...)
junto a la flecha **solo cuando hay más de un criterio activo** — con
una sola columna, se ve exactamente igual que antes (▲/▼ sin número),
para no ensuciar el caso común. Lista vacía (`sortState.length === 0`)
sigue siendo "usar el default" (estado con orden fijo, luego `job_id`
descendente), igual que antes. Verificado con datos sintéticos en Node:
`species desc, bin_index asc` da exactamente el resultado pedido (SEP_p
antes que GCR_He antes que GCR_H, y dentro de cada especie los bins en
orden ascendente); la secuencia de clicks agregar→rotar→quitar deja
intactas las columnas que no se tocaron.

### Bug real de producción grave: `requeue_stale_jobs()` nunca reencolaba un job estancado con heartbeat vivo — 10.1h de cómputo perdidas (2026-09-16)

**Reportado por el usuario con datos exactos, tras haber pedido
explícitamente "esperar y monitorear antes de matar nada":** el job 141
(`GCR_He bin7`, el más caro del barrido) en el worker `tania`
(`cpu_score=18.07`, la máquina más rápida conocida) llevaba
`connected_s=36368s (10.1h)` contra una estimación de `5331s (1.48h)`
— **682% del estimado**, muy por encima del umbral de reencolado por
progreso (`ESTIMATE_SAFETY_FACTOR=2.5x ≈ 3.7h`). El worker seguía
reportando heartbeat vivo (`seconds_since_heartbeat` siempre <30s) pero
`cpu_load_pct=17.3%` sostenido — la CPU había dejado de trabajar
activamente en la simulación. Un Monitor armado para vigilar el caso se
detuvo silenciosamente al terminar la sesión anterior (sin dejar
ninguna notificación de cierre), así que nadie —ni el sistema
automático, ni el monitor manual— actuó durante esas horas.

**Causa raíz real, no el bug de "cutoff SQL demasiado largo" ya
corregido antes (ver "Bug real encontrado por el primer test..." más
arriba, ese fix seguía siendo insuficiente):** el `WHERE` de SQL en
`requeue_stale_jobs()` exigía `w.last_heartbeat < cutoff` —es decir,
heartbeat **vencido**— como condición de entrada antes de que CUALQUIER
fila llegara a evaluarse en Python. Pero `progress_exhausted`
(¿`connected_s` excede la estimación con margen?) es una condición
**completamente independiente** de si el heartbeat sigue vivo —
`heartbeat_loop()` corre en su propio hilo daemon separado (ver
"Worker, endurecido..." más arriba) y sigue latiendo con total
normalidad aunque el hilo principal, bloqueado en
`process.communicate()` esperando al subprocess de Geant4, esté
genuinamente colgado. Un heartbeat vivo nunca implica que el trabajo
avanza — pero el filtro SQL asumía lo contrario, así que un job
estancado con heartbeat sano **nunca podía reencolarse**, sin importar
cuánto tiempo pasara.

**Un test existente codificaba directamente el comportamiento
incorrecto** (`test_requeue_by_progress_exhausted_even_with_recent_
heartbeat_is_not_triggered`, ya en la suite desde el diseño original del
2026-09-14) — afirmaba explícitamente que "progress_exhausted por sí
solo no reencola sin que también haya vencido el heartbeat", exactamente
la suposición errónea que causó la pérdida real. El test pasaba porque
el código hacía lo que el test esperaba, no porque el diseño fuera
correcto.

**Corregido:** el `WHERE` de SQL ya no filtra por heartbeat en absoluto
— trae **todos** los jobs `claimed`/`running` sin acotar por edad de
heartbeat (el costo extra es despreciable, la cola tiene como mucho un
puñado de jobs activos a la vez, uno por worker conectado), y dejar que
el filtro fino en Python evalúe ambas condiciones independientes
(`progress_exhausted`, `abandoned`) sobre cada fila sin excepción. Test
renombrado y corregido a `test_requeue_by_progress_exhausted_triggers_
even_with_recent_heartbeat` — ahora confirma el comportamiento correcto
(`job_id in requeued`), documentando explícitamente el caso real de
producción que lo motivó. `last_error` del reencolado ya no dice
genéricamente "heartbeat vencido" — distingue "progreso agotado
(connected_s excede estimación×margen)" de "heartbeat vencido
(abandonado)" de "sin worker/heartbeat registrado", para que un futuro
diagnóstico como este no tenga que adivinar cuál de las dos condiciones
independientes disparó el reencolado. 55 tests siguen pasando (más el
renombrado, mismo total).

**Job 141 no se tocó manualmente** — el fix desplegado deja que el
propio ciclo automático de `requeue_stale_jobs()` (cada
`REQUEUE_SWEEP_INTERVAL_S=300s`) lo reencole solo en el siguiente
barrido tras el despliegue, sin necesitar un `UPDATE` ad-hoc en la VM.
Las 10.1h de cómputo real en `tania` se pierden sin remedio (no hay
forma de recuperar avance de un proceso que nunca reportó resultado
parcial) — el costo real de este bug, no solo un riesgo teórico.
Pendiente real: investigar por separado **por qué** el proceso de
Geant4 dentro de `tania` dejó de usar CPU activamente durante tanto
tiempo (loop infinito no cubierto por el límite de pista existente,
deadlock de I/O, proceso zombie) — este fix corrige que el coordinator
detecte y reencole el estancamiento, no la causa de que `tania` se
estancara en primer lugar; sin acceso a esa máquina para inspeccionar
el proceso real, la causa exacta queda sin confirmar.

**Reproducido en vivo, mismo día:** al desplegar el fix, `requeue_stale_
jobs()` reencoló el job 141 correctamente en el primer barrido tras el
reinicio (`last_error="requeued: progreso agotado..."`) — pero `tania`
**no tomó ningún job nuevo**, porque el proceso local seguía creyendo
que corría el job 141 (mismo patrón ya documentado de "cómputo huérfano
tras un reencolado manual sin señalizar al worker", más arriba: el
`UPDATE` del coordinator cambia la DB, nunca le llega al proceso real).
Resuelto reasignando el job 141 a `tania` temporalmente (`force_claim`
directo en la VM) con `cancel_requested=1`, para que el mecanismo de
remote-kill ya existente pudiera entregarle la señal en su próximo
heartbeat — funcionó: `last_error="cancelado por el operador
(exit_code=-15)"`, y `tania` retomó el job por su cuenta con
`cpu_load_pct=76.5%` (trabajando activamente de verdad, contra el 17.3%
sostenido de las 10+ horas anteriores) — confirma que el proceso viejo
estaba genuinamente atascado, no simplemente "lento".

### Investigación de la causa física, y robustez contra colgados sin diagnóstico visible (2026-09-16)

**Pedido explícito del usuario tras el incidente:** investigar por qué
pasa esto (no solo reaccionar), y hacer el sistema más robusto contra el
caso — "los logs no ayudan porque no muestran nada".

**Diagnóstico de por qué los logs no ayudaban, confirmado leyendo el
código real, no solo supuesto:** dos causas independientes, ambas
reales:
1. El macro de Geant4 (`MACRO_TEMPLATE` en `run_organ_sweep.py`) corría
   con `/event/verbose 0` — **cero** salida por evento hasta el resumen
   final del `beamOn`. Aunque alguien hubiera podido leer el log en vivo,
   estaría genuinamente vacío durante un colgado real: no hay diferencia
   observable entre "progresando normal" y "atascado" con ese nivel de
   verbosidad.
2. `worker.py` capturaba el stdout del subprocess con
   `subprocess.PIPE` + `process.communicate()` — un pipe que **solo
   entrega su contenido completo al terminar el proceso**, imposible de
   inspeccionar mientras sigue corriendo. Aunque el punto 1 no existiera,
   nadie podría haber leído "las últimas líneas ahora mismo".

**Hipótesis de causa física investigada, no confirmada al 100%:** el
límite de pista existente (`envelopeMaxTrackLength`, ver el fix de
2026-09-13 para partículas atrapadas) protege contra el caso de energía
**baja** (radio de giro diminuto, pista individual dando muchas vueltas)
— pero el job 141 era `GCR_He bin7`, la energía **más alta** de todo el
barrido (~225 GeV cinéticos reales, `56230.4 MeV/amu × A=4`). A esa
energía, con la physics list `Shielding` (modelos hadrónicos completos),
un núcleo de He de 225 GeV puede generar cascadas de secundarios
extensas (espalación, producción de piones) — el límite de pista acota
la longitud de **una** pista, no la **cantidad** de pistas ni el tiempo
total de un evento; una cascada suficientemente compleja podría tardar
un tiempo desproporcionado sin que ninguna pista individual exceda el
límite. **No se pudo reproducir de forma controlada** (el checkout local
no tenía `field/production/*.map` disponible para replicar el campo
real) ni confirmar contra el log real del intento colgado (se perdió al
matarlo — vivía en un `tempfile.TemporaryDirectory()` ya borrado) — se
documenta como hipótesis fundamentada, no como causa confirmada.

**Corregido, en tres piezas, todas necesarias juntas (confirmado con el
usuario antes de implementar — bloquea publicar imagen Docker nueva):**

1. **Progreso real en el log**: `MACRO_TEMPLATE` gana
   `/run/printProgress {print_progress_every}` — calculado como
   `max(1, n_events // 50)` (~50 líneas de progreso por corrida sin
   importar el tamaño: una corrida barata no se ahoga en logs, una cara
   tiene progreso frecuente). Se prefirió sobre `/event/verbose 1`
   (mucho más verboso, potencialmente desordenado con 8 threads
   escribiendo en paralelo) — el comando estándar de Geant4 para
   exactamente este propósito.

2. **stdout a archivo real, no a un pipe en memoria**: `_run_job()` en
   `worker.py` redirige el subprocess a `work/worker_stdout.log` (no
   `subprocess.PIPE`) y usa `process.wait()` en vez de
   `process.communicate()` — necesario para poder leer "las últimas
   líneas ahora mismo" mientras el proceso sigue corriendo.
   `_current_geant4_log_path()` busca el log real que escribe
   `run_organ_sweep.py` (`work/logs_organ/*.log`, con `--limit 1` hay a
   lo sumo uno) y cae al `worker_stdout.log` como fallback si no existe
   todavía. `tail_log()`/`get_active_log_tail()` (nuevo) leen las
   últimas `_LOG_TAIL_LINES=40` líneas, tolerante a que el archivo no
   exista aún o desaparezca a mitad de lectura (carrera real contra el
   cleanup del `TemporaryDirectory` al terminar el job, no hipotética).

3. **Watchdog de progreso automático dentro del propio worker**: el
   hilo `_watch_for_cancel()` (ya existía para remote-kill) ahora
   también vigila el tamaño del log activo cada
   `_STALL_CHECK_INTERVAL_S=30s` — si no crece en absoluto durante
   `_STALL_TIMEOUT_S=20min` (muchísimo más generoso que el intervalo de
   progreso esperado incluso para GCR_He bin7, la corrida más cara del
   barrido, ~85min con progreso periódico; muchísimo más corto que las
   10+ horas que tardó en detectarse el caso real), el worker se mata a
   sí mismo (`terminate_process_group`, mismo mecanismo ya usado para
   cancelación) y reporta el fallo con el tail del log adjunto — **sin
   depender de que el coordinator lo detecte por `connected_s`** (que
   puede tardar horas si el heartbeat sigue vivo, exactamente el bug de
   arriba) **ni de que un operador lo note a mano**. El worker se
   auto-corrige.

**Log bajo demanda desde el coordinator (pedido explícito del
usuario, complementario al watchdog — diagnóstico manual, no
automático):** mismo patrón que remote-kill, viaja en la respuesta del
heartbeat existente porque el worker está detrás de NAT sin puerto
expuesto — el coordinator no puede alcanzarlo directamente.
`jobs.log_requested`/`log_tail`/`log_tail_updated_at` (columnas nuevas,
migración idempotente); `request_job_log()`/`log_requested_for_worker()`
(`db.py`) espejan `request_job_cancel()`/`cancelled_job_for_worker()`
exactamente; `touch_heartbeat()` devuelve ahora
`{"cancel_job_id", "request_log"}` (cambio de contrato, todos los
llamadores/tests actualizados). Nuevos endpoints: `POST
/jobs/{id}/request-log` (administrativo, dispara la solicitud — mismo
criterio que `/cancel`, **a propósito NO en `dashboard.html`** por la
misma razón que remote-kill: acción de diagnóstico sin autenticación no
va en un link compartible) y `POST /jobs/{id}/log` (el worker sube el
tail, rechaza con `409` si el job ya no le pertenece — mismo criterio de
propiedad que `submit_result()`). `report_log()`/`heartbeat()` en
`worker.py`: si `request_log=true` en la respuesta, sube el tail con un
`POST` aparte (no en el mismo heartbeat, para no inflar el caso común
donde nadie lo pidió). Nuevo `infra/coordinator/request_job_log.py`
(script CLI, mismo estilo que `cancel_job.py`) — pide el log y hace poll
a `GET /jobs` hasta que `log_tail_updated_at` cambie, sin necesitar una
segunda invocación manual.

**Verificado, no solo escrito:** 66 tests del coordinator pasan
(7 nuevos: `request_job_log`/`log_requested_for_worker`/
`save_job_log_tail`, más 2 tests existentes de `touch_heartbeat()`
actualizados al nuevo contrato de retorno) y 54 del worker (7 nuevos:
`tail_log`, `get_active_log_tail`, el flujo completo de
`heartbeat()`→`report_log()`, y el watchdog probado con un **subprocess
real** — `sleep 30` que nunca escribe a su log, con umbrales de prueba
acortados vía `monkeypatch`, confirmado matado en ~3.4s en vez de
esperar los 30s completos). Verificado contra `fastapi` real instalado
(no solo `ast.parse`), no solo los 5 tests que dependían de `app.py` que
suelen fallar en este entorno por falta de esa dependencia.

**Pendiente, bloqueante para que esto llegue a producción:** publicar
imagen Docker nueva (el cambio de `_run_job()` a redirigir stdout a
archivo, más el watchdog, viven en `worker.py`) y coordinar con cada
voluntario que actualice cuando termine su corrida actual — mismo
procedimiento ya establecido para publicaciones anteriores (`cpu_score`,
persistencia de resultados). El coordinator (`db.py`/`app.py`) sí se
puede desplegar de inmediato con el procedimiento normal (`git pull` +
`systemctl restart`) sin esperar a la imagen — los workers viejos
simplemente nunca ven `request_log=true` como `true` de forma útil (no
tienen `report_log()`) hasta que actualicen, sin romper nada mientras
tanto.

### `MIN_CPU_SCORE` subido de 3.0 a 5.0: excluir `bryam-local` de bin6/7 (2026-09-16)

**Pedido explícito del usuario:** `bryam-local` (`cpu_score=3.692` en su
lectura más reciente) seguía calificando para `bin6`/`bin7` de
GCR_H/GCR_He con el umbral anterior (3.0) — pero esos bins estiman
~7h en esa máquina, demasiado según el usuario. El propio valor de 3.0
venía de lecturas de `cpu_score` **de otro momento** (2026-09-14:
`bryam-local` 4.461, `bryam-parrot` 4.334) — ya desactualizadas, ver la
entrada de arriba sobre por qué `cpu_score` cambia entre reinicios del
worker (no es una propiedad fija del hardware, se mide una sola vez al
arrancar bajo la contención real de ese momento).

**Corregido:** `MIN_CPU_SCORE = 5.0` en `seed_full_sweep.py` (valor
elegido explícitamente por el usuario) — con los `cpu_score` reales
observados hoy (`tania` 18.07, `laptop-liz` 5.24, `bryam-parrot` 4.25,
`bryam-local` 3.69, `laptop-fabiola` 3.59, `eddy-laptop` 0.7), deja
pasar solo a `tania` y `laptop-liz` para los bins más pesados. Aplicado
también retroactivamente en la DB real (mismo patrón ya usado para el
cambio anterior de 0.5→3.0): `UPDATE` directo sobre los 73 jobs
`pending` de bin6/7 que aún tenían `min_cpu_score < 5.0` — verificado
vía la API pública sin cambiar `jobs_pending` total ni afectar los jobs
`running` (ninguno pertenecía a `bryam-local`, que además está offline
en este momento). Un job ya en curso no se ve afectado por este cambio
retroactivo -- solo los que todavía no fueron reclamados.

**Riesgo ya documentado, sigue aplicando:** si `bryam-local` se reinicia
en algún momento futuro bajo menos contención y su `cpu_score` sube por
encima de 5.0, volvería a calificar sin que nadie lo decidiera
explícitamente — mismo riesgo latente ya anotado en la entrada de
`cpu_score` variando entre reinicios, sin mitigación implementada
(recalcular el score en cada reinicio sigue siendo por diseño, no un
bug).

### Revisión del diagnóstico de corridas y watchdog

Esta actualización sustituye la política histórica de terminación automática
tras 20 minutos sin crecimiento del log: el default es ahora
`WORKER_STALL_ACTION=warn`, con umbral configurable
`WORKER_STALL_TIMEOUT_S=1200` y reloj monotónico. `kill` es optativo y requiere
calibración con inicializaciones/eventos lentos; silencio no demuestra cuelgue.
El barrido imprime progreso cada evento por defecto (`--print-progress-every`).

Las solicitudes de logs quedan vinculadas a un ID único y al intento del job,
tanto en el heartbeat como al subir y consultar la respuesta. Se rechazan
respuestas obsoletas; un log vacío sí confirma recepción. El worker limita la
lectura a 64 KiB y comprueba errores HTTP. El dashboard presenta el último log
como texto escapado, con intento/fecha, sin acciones administrativas nuevas.
Actualizar ambos extremos del protocolo; clientes antiguos sin estos IDs no
pueden subir logs. Detalles de operación en `infra/README.md`.

### Digest ausente en dashboard: recuperación por heartbeat

El worker enviaba `image_digest` solo al registrarse: una detección inicial
fallida dejaba el dashboard sin dato aunque Docker se recuperase. Ahora cada
heartbeat vuelve a detectarlo y enviarlo; el coordinator ya conserva el último
valor conocido cuando recibe null. Esto no habilita auto-update sin socket ni
sin identidad verificable: `auto_update()` sigue requiriendo un digest local.
Publicar `latest` no activa por sí solo una actualización: se requiere anunciar
el digest de manifiesto validado en el coordinator. Un dato ausente en la tabla
no demuestra por sí solo ni una imagen antigua ni auto-update deshabilitado.

### Instrumentación de silencio del worker

`infra/worker/diagnostics.py` muestrea CPU por hilo/árbol de procesos y recursos
Linux. El aviso del watchdog conserva diez muestras, estados de espera, pilas
kernel disponibles y artefactos acotados bajo el volumen persistente, vinculados
a job/intento/digest. Máximo tres capturas por intento; no subida automática.
`ICRP110PhantomActionInitialization.cc` incorpora una acción begin/end por evento
activada por `G4_EVENT_DIAGNOSTICS_DIR`, que el worker fija en su espacio temporal.
No altera scoring ni limita pasos. Las pilas nativas C++ requieren diagnóstico
supervisado posterior; los permisos ausentes se registran sin terminar Geant4.
Detalles y límites de conservación en `infra/README.md`.

### Auto-actualización con Podman: falta el socket, no una contradicción de diseño (2026-09-16)

**Pregunta directa del usuario tras un incidente real:** `tania` (el
worker más rápido, `cpu_score=18.07`) volvió a reclamar el job 141 tras
un remote-kill con la MISMA imagen vieja — ¿contradice esto la mecánica
de auto-actualización "entre jobs" ya documentada? Investigado leyendo
el código real (`auto_update()` en `worker.py`, líneas 914+), no
repitiendo la documentación de sesiones anteriores sin verificar: el
mecanismo sí existe, sí se invoca correctamente justo antes de pedir el
siguiente job (`run_worker_loop()`, nunca a mitad de una simulación), y
la imagen Docker actual sí trae la etiqueta
`org.iac.worker-update-protocol=1` que `auto_update()` exige. No hay
contradicción de diseño.

**Causa raíz real, confirmada con `podman inspect geant4-worker` en
`tania` (pedido explícitamente al usuario y verificado dato por
dato):** `tania` corre el worker con **Podman**, no Docker —
`NetworkMode: pasta`, `CgroupManager: systemd`, rutas
`.local/share/containers/storage/overlay-containers/...`,
`io.container.manager: libpod` en las Annotations, todos indicadores
exclusivos de Podman. El `podman run` original (traducido a mano del
`docker run` de `GUIA_VOLUNTARIOS.md`, que nunca menciona Podman) nunca
montó ningún socket dentro del contenedor (`"Mounts": []` en el
inspect). `docker_client.py` (usado exclusivamente por `auto_update()`)
habla directo al Docker Engine API sobre `/var/run/docker.sock` vía
HTTP crudo (`http.client`/`socket` de la stdlib, sin CLI) — sin ese
socket montado, `DockerClient.available()` (`GET /_ping`) falla de
inmediato, así que `self_image_digest()` devuelve `None`, y
`auto_update()` se rinde en su primer chequeo (`if current_digest is
None: return False`) **antes de comparar nada**, sin loguear ningún
error visible. Confirmado con datos reales que sí había una
actualización pendiente para aplicarse: digest corriendo en el
contenedor (`639b183c...`, del propio `podman inspect`) distinto del
digest deseado publicado en el coordinator (`c9a61529...`, de
`GET /api/v1/health`).

**Mismo bug ya documentado para `image_digest: null` en el dashboard**
(ver "Digest ausente en dashboard" más arriba) — la diferencia es que
en `tania` este fallo silencioso no solo deja un campo de telemetría en
blanco, sino que bloquea la auto-actualización real por completo.

**La API que usa `auto_update()` es Docker Engine API estándar sin
nada específico de la implementación de Docker** (`/_ping`,
`/containers/{id}/json`, `/images/{ref}/json`, rename, etc., verificado
leyendo `docker_client.py` completo) — Podman expone exactamente esta
misma API en modo compatibilidad vía `podman system service`, pensado
justo para este caso. `self_container_id()` (el otro prerequisito de
`auto_update()`) ya funciona en `tania` sin cambios, por su tercer
fallback (`hostname` como ID si matchea 12/64 hex) — confirmado:
`hostname=08976dbb9e96`. Solo faltaba el socket.

**Fix entregado al usuario, no aplicado por este asistente** (`tania`
la administra otra persona, probablemente `alexander` según las rutas
del inspect) — habilitar `systemctl --user enable --now podman.socket`
(persiste entre reinicios, rootless) y recrear el contenedor con
`-v $XDG_RUNTIME_DIR/podman/podman.sock:/var/run/docker.sock` agregado
al mismo `podman run` de siempre. Pendiente real: si algún otro
voluntario también usa Podman en vez de Docker (nadie más confirmado
hasta ahora), tendrá el mismo problema — `GUIA_VOLUNTARIOS.md` sigue
documentando solo el comando `docker run`, sin una nota equivalente
para Podman; no agregada todavía porque `tania` es, por ahora, el único
caso real conocido.

### Bug real de robustez: el worker no distingue "mi entorno está roto"
de "esta simulación falló" — 18 jobs quemados en cadena (2026-09-15)

**Reportado por el usuario:** `bryam-local` corrió solo el `nohup env
... python3 infra/worker/worker.py &` de `GUIA_WORKER_LOCAL.md` sin el
paso previo `conda activate geant4_env`, y esto causó "muchos jobs
marcados como fallidos" — el usuario lo señaló correctamente como un
bug, no solo un error de operación puntual.

**Mecanismo confirmado leyendo el código real (`_run_job()` en
`worker.py`):** `main()` (línea 1204+) solo verifica que
`RUN_ORGAN_SWEEP` y el binario `ICRP110phantoms` **existan en el
filesystem** (líneas 1205-1209) — ninguna de las dos comprobaciones
depende de `LD_LIBRARY_PATH`/`G4*DATA`, así que el worker arranca y se
registra sin problema incluso sin el entorno conda activado.
`subprocess.Popen(cmd, ...)` (línea 1079) también arranca sin error —
el binario existe, el problema es que **al ejecutarse** no encuentra
las bibliotecas dinámicas de Geant4 ni sus datasets, y sale casi de
inmediato con `returncode != 0`. Eso cae en la rama de la línea 1179
(`if process.returncode: raise RuntimeError(...)`) → capturado por el
`except` genérico de la línea 1188 → `report_failure()`. El worker
nunca distingue esta causa (entorno roto, afecta a CUALQUIER job que
reciba) de un fallo genuino de una simulación específica (ej. un bug de
física en un bin particular) — sigue el loop normal
(`run_worker_loop()`) y pide el siguiente job de inmediato, repitiendo
el mismo fallo en segundos por cada uno.

**Alcance real, confirmado consultando `GET /api/v1/jobs` por
`claimed_by=ba49a04b-...` (worker_id real de `bryam-local`, no
confundir con un `worker_id` viejo de `9386d5c3-...` encontrado en un
`~/.geant4-worker/worker_id` local de otra sesión/máquina, sin relación
con este incidente):** 18 jobs cayeron a `failed` definitivo (3
intentos agotados cada uno, todos con exit_code=1 y sin llegar a
completar ninguna corrida real) — job 141 (ya repuesto antes por el
incidente de remote-kill, ver arriba) más 17 más:
258/262/278/282/286/290/294/446/450/454/522/526/530/534/538/542/546,
mezcla de GCR_H/GCR_He/SEP_p en varios bins y offsets, todos repetición
2/3. **Repuestos manualmente a `pending` con `attempt=0`** (mismo
criterio que job 141: el fallo fue de entorno, no de cómputo real, así
que no debían contar contra el límite de 3 intentos) vía `gcloud
compute ssh` a la VM del coordinator.

**Segundo fallo de job 141, encontrado porque el usuario lo señaló
explícitamente tras el barrido inicial** ("hay un fallido más que se te
ha pasado por alto") — la primera pasada de este incidente solo
consultó el estado en un instante dado; entre reponer job 141 (por el
incidente de remote-kill, ANTES de saber del entorno roto) y confirmar
que `bryam-local` ya tenía el entorno activado, la máquina volvió a
tomar el 141 todavía sin `conda activate`, lo falló otra vez con el
mismo `exit_code=1` característico, y agotó sus 3 intentos frescos de
nuevo. Repuesto una segunda vez a `pending`/`attempt=0`. Verificado tras
esto que no quedan más jobs `failed` bajo el `worker_id` de
`bryam-local` (`GET /api/v1/jobs` filtrado por `claimed_by`, 0
resultados) — lección para revisar de nuevo cualquier incidente similar
después de confirmar que la causa raíz ya se corrigió, no solo antes.

**Corregido en el código (2026-09-15), las dos ideas que habían quedado
pendientes en el párrafo anterior:**

1. **Self-check real del entorno antes de registrarse**
   (`check_geant4_environment()`, nuevo en `worker.py`, llamado desde
   `main()` antes de `run_worker_loop()`). Corre el binario real
   (`ICRP110phantoms`) con un macro trivial (`/run/initialize`, sin
   `beamOn`) y un timeout de 20s. **Diagnóstico verificado en vivo, no
   supuesto** — sin `conda activate geant4_env`, el binario SÍ arranca
   (las bibliotecas dinámicas se resuelven por RPATH embebido, no
   dependen de `LD_LIBRARY_PATH` en runtime, al contrario de lo que se
   había asumido inicialmente), pero Geant4 aborta con `SIGABRT` (exit
   134) al no encontrar `G4ENSDFSTATEDATA` y el resto de los datasets
   `G4*DATA` — reproducido con `env -i`, mensaje exacto `"G4ENSDFSTATEDATA
   environment variable must be set"` seguido de `"*** Fatal Exception
   *** core dump ***"`. Con el entorno activado, el mismo comando
   termina limpio en exit 0. `/run/initialize` sin `beamOn` ya dispara
   la carga de datasets — no hace falta ninguna corrida real para
   detectar esto. Si el chequeo falla, `main()` sale con `sys.exit()`
   antes de registrarse — el worker nunca aparece en el coordinator, y
   nunca reclama ningún job real con el entorno roto.
2. **Detección de fallos consecutivos rápidos** (`_CONSECUTIVE_FAST_FAILURES_LIMIT=5`,
   `_FAST_FAILURE_MAX_DURATION_S=60.0`, en `run_worker_loop()`) — red de
   seguridad complementaria al self-check: cubre el caso de que el
   entorno se rompa DESPUÉS de arrancar (ej. una reinstalación de conda a
   mitad de vida del proceso), no solo al inicio. `run_job()`/`_run_job()`
   ahora devuelven `(exito: bool, duracion_s: float)` en vez de `None`
   (cambio de contrato, ningún test existente dependía del valor viejo).
   5 fallos seguidos de menos de 60s cada uno (la firma real observada:
   18 jobs fallando en segundos, sin ningún éxito de por medio) detienen
   el worker con `sys.exit()` y un mensaje explícito, en vez de seguir
   pidiendo jobs indefinidamente. Un solo éxito de por medio resetea el
   contador — un fallo real y aislado de una simulación específica nunca
   dispara esto por sí solo.

10 tests nuevos en `test_worker.py` (65 en total, todos pasan): el
self-check detecta exit 0/134/timeout correctamente, `main()` sale sin
llamar a `register()` si el entorno falla, la racha se detiene en el
umbral exacto, y un éxito de por medio la resetea sin falsos positivos.
Cambio puro de `worker.py` — **requiere publicar imagen Docker nueva**
para que los workers Docker existentes lo reciban (mismo procedimiento
de coordinación ya establecido: cada voluntario actualiza cuando su
corrida actual termine). La guía (`GUIA_WORKER_LOCAL.md`) sigue
recomendando `conda activate geant4_env` como primer paso — el
self-check ahora es la red de seguridad si igual se olvida, no un
reemplazo de seguir la guía.

### Bug real de producción: jobs "fantasma" acumulando progreso tras un reinicio del proceso worker (2026-09-15)

**Reportado por el usuario, con diagnóstico propio correcto antes de
pedir el fix:** cuando el PROCESO del worker muere y se reinicia
(apagado/encendido de la PC, crash, `docker rm`+recreate) sin liberar
primero el job que tenía activo, el proceso nuevo simplemente pide el
siguiente — dejando el job viejo huérfano en `claimed`/`running` bajo el
mismo `worker_id`. El usuario señaló correctamente que esto es distinto
de un simple corte de red (ahí el mismo proceso sigue vivo y retoma el
MISMO `job_id` al reconectar, nunca hay dos jobs activos a la vez), y que
como Geant4 no guarda estados intermedios, el progreso del job huérfano
ya se perdió por completo — no tiene sentido que su `connected_s` siga
"avanzando" en el dashboard, y no debería esperar el timeout normal de
abandono para reencolarse.

**Confirmado en vivo con datos reales de `bryam-local`** (que sufrió
exactamente este patrón varias veces la misma sesión, por reinicios
repetidos de su propio proceso worker): 2 jobs `claimed`/`running`
simultáneos bajo el mismo `worker_id` (job 141, viejo, `connected_s`
subiendo sin trabajo real; job 446, el real, `active_job_id` reportado
en el heartbeat). Causa raíz exacta en `_accrue_connected_time()`
(`db.py`): el `UPDATE jobs SET connected_s = connected_s + ? WHERE
claimed_by=? AND status IN ('claimed','running')` no filtraba por
`job_id` — sumaba tiempo a **todos** los jobs activos de ese
`worker_id`, no solo al que el proceso real está trabajando.

**Corregido usando `active_job_id`, telemetría que el worker YA manda en
cada heartbeat** (`_active_cancel` en `worker.py`, agregada en la sesión
anterior para el mecanismo de remote-kill, nunca antes usada para esto):
- `_accrue_connected_time()` ahora solo suma tiempo al job cuyo
  `job_id == active_job_id` cuando ese campo viene informado — un worker
  sin esa telemetría todavía (versión vieja) cae al comportamiento
  anterior sin cambios, mismo criterio conservador que `ram_free_gb`/
  `cpu_score` ausentes en otras partes del coordinator.
- `requeue_orphaned_jobs_for_worker()` (nuevo en `db.py`), llamado dentro
  de la misma transacción de `touch_heartbeat()` (después de resolver
  `cancel_job_id`/`request_log` sobre el job activo real, para que esas
  señales nunca compitan con un huérfano): reencola de inmediato
  cualquier job `claimed`/`running` de ese worker que NO sea su
  `active_job_id` reportado — `pending` si le quedan intentos (mismo
  criterio que `record_failure()`, incluyendo limpiar `claimed_by`),
  `failed` si los agotó (conservando `claimed_by`/`claimed_at`, igual que
  cualquier otro job que agota sus intentos en el resto del
  coordinator). `last_error` deja explícito que fue un reencolado
  automático por esta causa, no una cancelación ni un timeout de
  abandono. `POST /workers/{id}/heartbeat` expone la lista de
  `job_id` reencolados en su respuesta (`requeued_orphan_job_ids`,
  automático vía `{"ok": True, **result}`, sin tocar `app.py`).

5 tests nuevos en `test_coordinator.py` (72 en total): un job huérfano
deja de acumular `connected_s` mientras el real sí lo hace; el huérfano
se reencola en el mismo heartbeat que lo revela; respeta
`max_attempts` (cae a `failed` conservando la asignación, no a
`pending`); un worker sin `active_job_id` no reencola nada. Cambio puro
de `db.py`/`app.py` — **no requiere imagen Docker nueva**, se despliega
con el procedimiento normal (`git pull` + `systemctl restart
geant4-coordinator`).

### 7 procesos `ICRP110phantoms` huérfanos en `tania`, hasta 24h vivos, ~800% CPU sumado (2026-09-20)

**Reportado por el usuario, vía el agente de la sesión del coordinator**
(que tenía acceso al journal de `uvicorn` y a la DB, no a `tania`
directamente): 7 PIDs del binario pesado de Geant4 seguían corriendo
dentro del contenedor de `tania` — entre 1h y 24h vivos, sumando
~800% CPU (8 núcleos completos) — pese a que el coordinator ya daba esos
jobs por `failed`/cancelados. Mientras tanto, el job realmente activo en
ese momento (148) solo podía usar los núcleos que sobraban, no los 10
hilos pedidos (`--threads 10`).

**Diagnóstico colaborativo entre dos sesiones (esta y la del
coordinator), con evidencia real, no supuesta:**

- `terminate_process_group()` en `worker.py` ya usaba `os.killpg()`
  (mata el grupo de procesos completo, no solo el PID padre) desde antes
  de este incidente — reproducido localmente con un árbol de 2 niveles
  (proceso Python padre → `subprocess.run` hijo, `sleep` como sustituto
  de `ICRP110phantoms`) y con un `SIGTERM` real interrumpiendo
  `process.wait()`: en ambos casos el `killpg` mató correctamente todo
  el árbol, sin dejar huérfanos. El diagnóstico inicial de "la
  cancelación solo mata el proceso padre" **no reproduce** con el código
  del repo.
- La sesión del coordinator correlacionó los 7 timestamps de arranque de
  esos jobs (del 15-sep) contra la edad real de cada PID huérfano — las
  diferencias coinciden casi exactamente (616 vs. 618 min, 85 vs. 85 min,
  etc.), y confirmó en el journal que el worker de `tania` SÍ mandó
  `POST /fail` entre 4 y 31s después de cada `cancel`, lo cual solo pasa
  después de que `terminate_process_group()`/`watcher.join()` ya
  corrieron — es decir, el worker estaba vivo y completó la ruta de
  cancelación, no murió a mitad de camino. Las demás causas de huérfanos
  en otras máquinas (reinicios de worker, timeout de heartbeat) sí dejan
  al binario limpio porque el contenedor entero termina.
- Conclusión: el `killpg` sí se disparó en `tania` específicamente, pero
  no alcanzó al nieto. Sospechoso, no confirmado con un `ps` real
  todavía: `tania` corre **Podman rootless con `NetworkMode: pasta`**
  (mismo incidente ya documentado arriba, "Auto-actualización con
  Podman" — misma máquina, mismo digest de imagen vieja `639b183c...`),
  que puede intercalar procesos de red en el árbol de forma que rompa la
  asunción de que el nieto queda en el mismo grupo de sesión que
  `run_organ_sweep.py`. Pendiente: comparar el `pgid` real de un
  huérfano contra el `pgid`/`sid` de su `run_organ_sweep.py` padre
  (`ps -o pid,ppid,pgid,sid,lstart,cmd`) para confirmar o descartar esto
  — dato que solo puede traer quien tenga acceso directo a `tania`.

**Fix aplicado, independiente del diagnóstico raíz exacto** (`worker.py`,
`cleanup_orphaned_simulations()`): un barrido que mata cualquier
`ICRP110phantoms` cuyo `cwd` (vía `/proc/<pid>/cwd`) está dentro de un
directorio `geant4-job-*` — el prefijo único que solo `worker.py` crea
(`tempfile.TemporaryDirectory` en `_run_job()`) para cada intento.
Diseño revisado dos veces con el equipo antes de esta forma final:

1. **No alcanza con correr esto solo al arrancar** — los 7 huérfanos de
   `tania` se acumularon a lo largo de ~19h con el *mismo* proceso
   worker vivo todo el tiempo (heartbeats continuos, sin reinicio). Por
   eso corre también periódicamente, en cada vuelta del loop principal
   en que este worker no tiene ningún job propio activo (`job is None`,
   justo antes de dormir hasta el siguiente poll) — nunca compite con
   una simulación legítima en curso de este mismo worker.
2. **No filtrar solo por nombre de binario en toda la máquina** — en un
   worker sin contenedor (`bryam-local` corre `worker.py` directo contra
   su build ya compilado) eso mataría una corrida manual legítima del
   usuario, ajena por completo al worker. Acotar por `cwd` dentro de
   `geant4-job-*` evita ese falso positivo por diseño: ningún proceso
   ajeno a este worker corre nunca ahí.

Verificado con un test real (no simulado): un proceso `sleep` como
sustituto del binario, uno dentro de `geant4-job-*` (debe morir) y otro
en un directorio normal (nunca debe tocarse) — ambos casos se comportan
como se espera. `infra/worker/test_worker.py`, 71 tests en total.
Cambio puro de `worker.py` — no requiere imagen Docker nueva, aplica con
el procedimiento normal de actualización del worker.

### Revisión previa al push de jobs_v2 (2026-09-20)

Corregidos: arranque v2 enviado por error a `/jobs/{id}/start`; colisiones de
outbox/fallos entre IDs v1/v2 (v2 usa prefijo propio, legados v1 conservados);
heartbeat de v2 que podía recibir cancelación/log de v1 con el mismo ID;
reencolado v2 basado en updated_at aun con heartbeat vivo, sin transacción
ni límite de intentos. Ahora exige heartbeat vencido y respeta max_attempts.
Resultados v2 verifican también fase. Seed valida bins/eventos positivos.

**Bug propio introducido en esta misma revisión, encontrado y corregido
antes de comitear:** `claim_next_job_v2()` había quedado con el fallback de
`cpu_score` desconocido en `0.0` en vez de `float("inf")` — invertía el
criterio ya establecido en `db.py` v1 (`claim_next_job()`, comentario
explícito ahí: "un worker sin `cpu_score` real... no debe bloquearse por
`min_cpu_score`"). Con `0.0`, exactamente el worker que menos telemetría
tiene de sí mismo (versión vieja, o el benchmark de arranque falló)
quedaba bloqueado de cualquier job que pidiera `min_cpu_score > 0` — al
revés de lo previsto. Revertido a `float("inf")`, mismo criterio que v1.

La limpieza global por cwd `geant4-job-*` quedó desactivada: no prueba propiedad
ni que otro worker haya terminado. Sigue la terminación del grupo subprocess
propio por cancelación. Para recuperar limpieza automática se necesita un registro
persistente de propietario e identidad de proceso (incluido starttime), no un
filtro por nombre. El contador no suma señales no verificadas.

El barrido rechaza resume sobre CSV con esquema antiguo o grilla diferente antes
de escribir, evitando columnas corridas y saltar combinaciones de otra grilla.
Conservar esas salidas y usar otro directorio; no se migran ni borran resultados.
Revisión local: no despliegue, cambios de jobs ni push.

### Bug real de producción: `_migrate_jobs_add_phase()` vació la tabla `jobs` al desplegar jobs_v2 (2026-09-24)

**Contexto:** primer despliegue de `jobs_v2` en la VM (código en `main`
desde antes, nunca desplegado hasta hoy). Tras `git pull` + `systemctl
restart geant4-coordinator`, el servicio entró en crashloop:
`_migrate_jobs_add_phase()` (agregada hace semanas para backfillear
`phase`, pensada como no-op en cualquier DB ya migrada) se disparó de
nuevo, renombró `jobs`→`jobs_pre_phase_migration`, creó la `jobs` nueva,
copió las 600 filas, y **falló en su último paso**
(`DROP TABLE jobs_pre_phase_migration`) con
`sqlite3.IntegrityError: FOREIGN KEY constraint failed` — `results.job_id
REFERENCES jobs(job_id)` bloquea el DROP de una tabla que sigue teniendo
ese nombre lógico referenciado, algo que nunca se había ejercitado porque
esta migración jamás se había vuelto a disparar sobre una DB ya migrada
en producción real. El proceso murió a mitad de la transacción; el WAL no
llegó a aplicar el rollback completo antes de que systemd reiniciara el
servicio, dejando `jobs` vacía (0 filas) y `jobs_pre_phase_migration` con
las 600 filas originales intactas — **`/api/v1/jobs` y `/health` mostraban
`jobs_done: 0`, pero ningún dato se había perdido realmente.**

**Recuperado sin pérdida:** con el servicio detenido, se re-ejecutó a mano
la copia `jobs_pre_phase_migration → jobs` (mismo backfill de `phase` que
el código original), se verificó fila a fila contra la tabla vieja y que
ningún `results.job_id` quedara huérfano, y solo entonces se hizo el DROP
(esta vez sin FK bloqueante, porque ya no había una segunda tabla con el
nombre lógico `jobs` en juego). 600/600 filas recuperadas bit a bit
(status/phase/species/bin_index/etc. idénticos a la copia de respaldo
tomada antes del despliegue). Dos backups completos de la DB de
producción tomados en el proceso (`/var/lib/geant4-coordinator/backups/`),
ninguno necesitó usarse para restaurar.

**Causa raíz sin corregir todavía:** `_migrate_jobs_add_phase()` no debería
poder volver a disparar su rama de migración sobre una DB que ya tiene
`phase` en `jobs` — el propio código ya tiene ese guard
(`if "phase" in cols: return`) al principio de la función, así que el
disparo real implica que, en el momento exacto del restart, `jobs`
todavía no tenía `phase` (consistente con que esta era la primera vez que
esta versión del código corría contra la DB de producción real desde que
se agregó esa columna hace semanas — la migración nunca se había
ejecutado ahí antes de hoy). El bug real y no corregido es que el DROP
final no tolera la FK de `results` apuntando al nombre `jobs` durante la
ventana en que la tabla vieja ocupa ese nombre renombrado — cualquier
migración futura de forma similar (rename+recreate+copy+drop) sobre una
tabla referenciada por FK debería probarse primero contra una copia real
de la DB de producción, no solo contra fixtures de test sintéticos
(los 65+ tests existentes nunca ejercitan esto porque parten de una DB
nueva, sin la tabla vieja post-rename en juego).

**Corregido de raíz (mismo día):** `_migrate_jobs_add_phase()` ahora hace
`PRAGMA foreign_keys=OFF` antes del rename y lo deja así hasta el final de
la migración (dentro de la misma transacción; `get_conn()` siempre vuelve
a ponerlo `ON` en la próxima conexión) — el `DROP TABLE` ya no puede
volver a fallar contra ninguna DB, migrada o no.

### Bug propio en el seed de jobs_v2 de Fase 8: worker sintético duplicado (2026-09-24)

Al sembrar `jobs_v2` con las 64 corridas ya hechas standalone por Bryam
(ver Fase 8 en `docs/bitacora/plan_estadistico.md`), `seed_fase8_tanda1_v2.py`
creó un `worker_id` sintético nuevo (literal `"bryam-local"`) para dejar
trazabilidad de ese trabajo retro-registrado — sin notar que la máquina
real de Bryam ya tenía una identidad registrada desde el barrido v1
original (`ba49a04b-c669-4011-a5b5-a2803825f6af`, label `bryam-local`,
`bryam-VirtualBox`, 2026-09-13). Resultado: dos entidades con el mismo
nombre visible en el dashboard, una de ellas (la sintética) apareciendo
brevemente como `ONLINE` justo después de crearse (cualquier worker recién
registrado tiene `seconds_since_heartbeat` bajo, sin relación con si vaya
a mandar heartbeats reales alguna vez).

**Corregido:** los 64 `jobs_v2`/`results_v2` se reasignaron al
`worker_id` real (`UPDATE ... SET claimed_by=/worker_id=`, dentro de una
transacción, verificado que cero filas quedaron con el `worker_id`
sintético antes de borrarlo) y el worker sintético se eliminó.
`seed_fase8_tanda1_v2.py` ahora usa el `worker_id` real como constante y
solo registra un worker nuevo (con advertencia explícita) si de verdad no
existe todavía — nunca sobrescribe un worker real preexistente con datos
mínimos falsos.

De paso, se limpió un tercer artefacto no relacionado: un `worker_id`
sin `label`/`hostname` (`00000000-0000-0000-0000-000000000000`, `OFFLINE`
desde antes de esta sesión, cero jobs/results referenciándolo en ninguna
tabla, verificado antes de borrarlo) — registro basura de origen
desconocido, sin relación con el trabajo de hoy.

### Bug real de producción: `204 No Content` con body rompía el polling de jobs (2026-09-24)

**Encontrado validando la imagen candidata de `jobs_v2` con un canario**
(coordinator de prueba aislado, DB propia, nunca contra producción — ver
la nota de convención más abajo): un worker real corriendo la imagen
candidata quedaba atrapado en un loop de
`('Connection aborted.', ConnectionResetError(104, 'Connection reset by
peer'))` en cada poll, sin poder tomar ningún job aunque hubiera uno
`pending` sembrado explícitamente para la prueba. El mismo patrón exacto
ya estaba en los logs de la VM de producción desde el despliegue de
`jobs_v2` esa misma mañana, sin que se hubiera investigado a fondo
todavía.

**Causa raíz:** `/api/v1/jobs/next` y `/api/v1/jobs/v2/next` devolvían
`JSONResponse(status_code=204, content=None)` cuando no había trabajo —
eso serializa el literal `"null"` (4 bytes) como cuerpo, violando el
`Content-Length=0` que un `204 No Content` exige por definición.
`@app.middleware("http")` (`require_worker_token()`, `BaseHTTPMiddleware`
por dentro) reenvía esa respuesta, y el conflicto se manifiesta en el
servidor como `h11._util.LocalProtocolError: "Too much data for declared
Content-Length"` — el cliente (`worker.py`, vía `requests`) nunca ve un
`204` limpio, solo la conexión reseteada a mitad, y entra en su
reintento normal, pero sin avanzar nunca.

**Por qué no se había detectado antes:** el endpoint v1 usa este mismo
patrón desde que existe, pero casi siempre hay algún job `pending` en
producción real, así que el camino "cola vacía" rara vez se ejercitaba.
El endpoint v2 se agregó en `5541a04` y nunca se había desplegado contra
un coordinator real hasta hoy — el bug estaba latente desde su creación,
sin ningún test que lo cubriera (los tests existentes llaman
`db.claim_next_job()` directo, nunca pasan por la capa HTTP/middleware
real donde vivía el problema).

**Corregido:** `Response(status_code=204)` (sin `content`) en vez de
`JSONResponse(status_code=204, content=None)`, en ambos endpoints. Test
de regresión nuevo (`test_next_job_204_has_no_body_through_middleware`,
`infra/coordinator/test_coordinator.py`) usando `TestClient` real (no
`db.py` directo) para ejercitar el middleware completo — confirmado que
falla sin el fix (`resp.content == b'null'`) y pasa con él. Requiere
`httpx` (dependencia de `fastapi.testclient.TestClient`, no listada en
`requirements.txt` — es dependencia de test, no de producción, mismo
criterio que `pytest`, documentado en el docstring del archivo).

**Validado end-to-end con el canario tras el fix:** el mismo worker
(imagen `candidate-0fad4ba`) tomó el job de prueba, corrió Geant4 real
(142 filas de órgano), y reportó `done` sin ningún reintento. Confirmado
también que `self_image_digest()` funciona correctamente cuando el
socket de Docker está montado — el `image_digest` reportado coincidió
exactamente con el digest real de la imagen publicada en GHCR.

**Convención de despliegue seguida** (ver "El checklist anterior... era
incorrecto: publicar y validar el candidato primero, activar el digest
después" en `infra/DISTRIBUTED_SWEEP_HISTORY.md`): la imagen candidata
se publicó a un tag separado (`candidate-0fad4ba`, no `:latest`) y se
validó contra un coordinator de prueba con su propia DB — en ningún
momento se tocó el coordinator de producción ni su `worker_image_digest`
durante esta validación. Ese fue precisamente el proceso que permitió
encontrar este bug antes de activarlo para workers reales.
