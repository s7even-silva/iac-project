# Cómputo distribuido

Rama `infra/distributed-sweep`. Coordinator FastAPI + SQLite WAL y worker
Geant4, reutilizando `scripts/install_compute_node.sh` sin modificarlo.
La arquitectura genérica con imágenes separadas de Elmer/Geant4 es una fase
posterior; este worker ejecuta únicamente el lanzador Geant4 existente.

## Producción (en vivo)

- **Coordinator:** `http://34.134.100.224:8000` (VM `e2-micro` en GCP,
  Always Free Tier, `us-central1-a` — ver `infra/deploy/`. Azure quedó
  bloqueado por una restricción de plataforma en la suscripción del
  usuario, no algo resoluble desde este repo; el script de Azure sigue
  listo para cuando eso se resuelva).
- **Imagen del worker:** `ghcr.io/s7even-silva/iac-project/geant4-worker:latest`.
- **Para reclutar gente que preste CPU (sin el proyecto instalado):** ver
  [`infra/GUIA_VOLUNTARIOS.md`](GUIA_VOLUNTARIOS.md) — Docker, un solo
  `docker run`, sin configuración adicional.
- **Para compañeros de equipo que ya tienen el proyecto compilado**
  (conda `geant4_env` + `ActiveShield_Sim/build` ya hechos): ver
  [`infra/GUIA_WORKER_LOCAL.md`](GUIA_WORKER_LOCAL.md) — mismo worker,
  sin Docker, corre directo contra su build.
- Detalle de qué jobs están poblados hoy en AGENTS.md, sección "Cómputo
  distribuido para el barrido de ActiveShield_Sim".

## Coordinator

```bash
python3 -m venv /tmp/coord_venv
/tmp/coord_venv/bin/pip install -r infra/coordinator/requirements.txt
cd infra/coordinator
/tmp/coord_venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

En otra terminal, desde `infra/coordinator`:

```bash
/tmp/coord_venv/bin/python seed_jobs.py --species SEP_p --bin-index 1 --offset-x-m 1 --n-events 100
curl http://127.0.0.1:8000/api/v1/health
```

La base de datos y los resultados viven en `infra/coordinator/data/`, ignorado
por Git y Docker. `COORDINATOR_DB` permite usar una base distinta para pruebas.
Copiar ese directorio para respaldarlo. Un proceso uvicorn es suficiente en
este primer corte. No exponerlo a Internet sin la restricción de acceso ya
acordada (VPN/firewall); no hay autenticación implementada.

## Worker local y Docker

Dos vías, mismo worker (`infra/worker/worker.py`), mismo protocolo:

- **Sin Docker, contra producción, para compañeros con el proyecto ya
  compilado:** ver [`GUIA_WORKER_LOCAL.md`](GUIA_WORKER_LOCAL.md) — receta
  completa (activar `geant4_env`, lanzar en background con `nohup`,
  monitorear, detener). Lo que sigue aquí es solo la prueba rápida local
  contra un coordinator en `127.0.0.1` (para desarrollo del propio
  coordinator/worker, no para sumar cómputo real al barrido).

```bash
COORDINATOR_URL=http://127.0.0.1:8000 WORKER_THREADS=1 \
WORKER_ID_FILE=/tmp/local-worker.id WORKER_ONCE=1 \
python3 infra/worker/worker.py

docker build -f docker/Dockerfile.geant4-worker -t geant4-worker:test .
docker run --rm --network host \
  -e COORDINATOR_URL=http://127.0.0.1:8000 \
  -e WORKER_LABEL=docker-test -e WORKER_ONCE=1 -e WORKER_THREADS=1 \
  geant4-worker:test
```

`--network host` corresponde a la prueba local en Linux. `WORKER_ONCE=1`
termina después de procesar un job; sin ese parámetro, continúa consultando.
`BUILD_DIR` apunta al build compilado (default `ActiveShield_Sim/build`).
`WORKER_THREADS` limita los hilos pedidos a Geant4 (`=1` explícito arriba, a
propósito, para una prueba rápida y predecible). Sin fijarlo, el default real
(2026-09-13, corrige un bug donde caía silenciosamente a 1 sin importar la
máquina) es `os.cpu_count()` leído *dentro* del contenedor -- todos los CPUs
que Docker le asignó, no un número fijo. No establece un límite de memoria
del contenedor. Para uso continuo montar un volumen en `/var/lib/geant4-worker`
y usar `--restart unless-stopped`.

Cada job identifica `(species, bin_index, offset_x_m, repeticion)`. El worker
usa `--only-species`, `--only-bins`, `--only-positions`, `--limit 1`,
`--repeats 1` y el nuevo `--repetition-start`. Este último conserva el default
0 y la fórmula original de semillas; no cambia los barridos anteriores.

Cada intento crea un directorio temporal con enlaces al ejecutable y datos
ICRP, sin escribir en los CSV del build original. Usa `--no-resume` para que
un resultado local viejo no sustituya una asignación nueva. Los resultados
se filtran por la identidad del job; un CSV con solo cabecera se considera
fallo. El coordinator verifica identidad, número de eventos y manifiesto.
Las entregas tienen rutas distintas y se aceptan solo si el job sigue asignado
al worker, evitando sobrescribir un resultado aceptado con una entrega tardía.

## Heartbeat y recuperación

El worker envía heartbeat en un hilo independiente también durante la
simulación (default cada 30 s, `HEARTBEAT_INTERVAL_S`). El coordinator revisa
cada 300 s (`REQUEUE_SWEEP_INTERVAL_S`) y reencola tras 6 horas sin heartbeat
(`STALE_JOB_TIMEOUT_S`). Al agotar `max_attempts` marca `failed`, también
cuando los intentos fallan por desaparición del worker.

Para pruebas aisladas se pueden usar intervalos de 1 s y timeout de 8 s;
no cambiar esos defaults de producción. Interrumpir el worker mientras el
job está `running`, comprobar `pending` tras vencer el heartbeat, y arrancar
otro worker para completarlo. SIGTERM termina también el grupo del proceso
simulador; SIGKILL de un contenedor elimina sus procesos. Matar solo el proceso
Python local con SIGKILL puede dejar hijos vivos: detener también su grupo.
Una partición de red todavía puede causar cómputo duplicado; no es una garantía
de ejecución exactamente una vez.

```bash
python -m pytest infra/coordinator/test_coordinator.py infra/worker/test_worker.py
```

## Cancelar un job en curso (remote-kill)

`python3 infra/coordinator/cancel_job.py <job_id>` termina el subprocess
de Geant4 de un job `claimed`/`running`, sin esperar a que el worker se
desconecte o el heartbeat venza. Útil para reasignar un job pesado que
cayó en un worker más lento de lo que convenía (ver AGENTS.md, "Bug real
de producción: un job pesado sin umbral..."), sin tener que apagar esa
máquina a mano ni esperar horas.

Mecanismo (no un endpoint que mate el proceso directo, el coordinator no
tiene ningún canal de entrada al worker): el comando marca
`jobs.cancel_requested=1` vía `POST /api/v1/jobs/{id}/cancel`; el próximo
heartbeat de ese worker (hilo separado, corriendo en paralelo al
subprocess — ya existía para esto, ver arriba) trae la señal en su
respuesta; un hilo watcher dedicado dentro de `run_job()` la ve y mata el
process group del subprocess. La recepción espera el próximo heartbeat
(`HEARTBEAT_INTERVAL_S`, 30s por defecto), más latencia de red, hasta 1s
del watcher y hasta 2s de gracia antes de SIGKILL. No hay un límite de
30s garantizado si la red falla. El job se reporta como fallo
("cancelado por el operador") y se reencola solo si le quedan intentos —
mismo mecanismo que cualquier otro fallo, sin lógica especial de
reencolado.

**Se pierde TODO el avance de esa corrida** — no hay checkpointing en
Geant4/`run_organ_sweep.py`, así que solo tiene sentido cancelar cuando
el tiempo conectado real ya invertido es bajo frente al estimado (columna
"Duración"/"Tiempo conectado" del dashboard, o `GET /api/v1/jobs`, antes
de decidir).

**A propósito no está en `dashboard.html`**. Esto no es una barrera de
autorización: el endpoint usa el mismo `WORKER_TOKEN` del resto de la API;
si está desactivado, también puede invocarse por HTTP sin token. No se
añadió un rol de administrador separado en esta revisión. El script acepta
el token desde `WORKER_TOKEN` o `--worker-token`.

Revisión de concurrencia (2026-09-14): cada ejecución tiene su propio Event y
contexto; el heartbeat captura ese contexto antes del HTTP y compara `job_id`
al regresar. Una respuesta tardía no cancela otra ejecución, ni siquiera otra
del mismo job. `active_job_id` opcional selecciona la señal correcta si hay
asignaciones antiguas con el mismo worker; los clientes anteriores siguen siendo
compatibles. Timeout y nueva asignación limpian `cancel_requested`.

Los avisos `/fail` se escriben atómicamente en `pending_failures/`, dentro del
volumen persistente. Se reintentan tras reinicio y antes de pedir otro job o
iniciar una actualización Docker. Un fallo de red/401/5xx conserva el aviso;
404/409 confirma que ya no corresponde a un intento activo. Esto evita dejar
un job cancelado huérfano mientras el worker toma otro. No borrar ese directorio
al actualizar. Cancelar consume un intento, no garantiza asignación a otra PC,
y el último intento termina en `failed`, no en `pending`.

La cancelación puede competir con la finalización normal: si el proceso ya
terminó, su resultado completo puede aceptarse. No se publica CSV parcial como
resultado exitoso de un proceso cancelado. No se añadieron checkpoints.

## Qué ve el coordinator de cada worker (y qué no)

El coordinator solo sabe lo que el worker le reporta explícitamente al
registrarse (`POST /workers/register`) y en cada heartbeat (`POST
/workers/{id}/heartbeat`, por defecto cada 30s aunque no haya job) — no
hay acceso remoto al host más allá de eso, ni SSH, ni inspección de
procesos ajenos al propio worker:

- `hostname`, `cpu_count` (`os.cpu_count()`), `ram_gb` (total, de
  `/proc/meminfo` `MemTotal`) — enviados una vez al registrar.
- `ram_free_gb` (`MemAvailable`, no `MemFree` — la estimación del kernel
  de RAM realmente disponible sin entrar a swap) y `cpu_load_pct` (load
  average de 1 minuto normalizado por núcleos, no un muestreo instantáneo
  de `/proc/stat`) — se reenvían en **cada** heartbeat, así que sí se
  actualizan en vivo mientras el worker está ocioso o corriendo un job.
  Consultables en `GET /api/v1/workers`.
- **No se mide ancho de banda de red** en absoluto.

Un job puede declarar `min_ram_gb`/`min_cpu_count` (`seed_jobs.py
--min-ram-gb --min-cpu-count`, default 0 = cualquier worker) —
`claim_next_job()` en `db.py` solo ofrece el job a un worker cuya
telemetría en vivo (`ram_free_gb`, no `ram_gb` total) alcance, para no
mandar un bin caro a una VM voluntaria con poca RAM libre en ese momento.
Un worker que nunca mandó telemetría (versión vieja) no queda bloqueado:
cae a comparar contra `ram_gb` total.

Pendiente después del primer corte: despliegue protegido, publicación en
GHCR, versionado de imágenes por digest en jobs, medición de ancho de
banda si se necesita filtrar por eso, y jobs Elmer.

Validación de la revisión (2026-09-14): 106 pruebas Python aprobadas, incluidas
API uvicorn local con subprocess resistente a SIGTERM y dos escenarios Docker
reales aislados. También aprobaron 17 escenarios PowerShell con mocks y 4 Bash.
Se verificó la limpieza de los recursos Docker de ensayo. No se publicó imagen,
no se hizo push ni se modificaron jobs/DB de producción. Sigue pendiente validar
Windows/Docker Desktop y un canario con digest publicado antes del despliegue.

### Diagnóstico de logs y política de silencio (revisión)

`request_job_log.py JOB_ID` solicita las últimas 40 líneas (lectura limitada
 a 64 KiB). Cada solicitud lleva un ID único y el número de intento del job:
el coordinator rechaza subidas tardías, de otro intento o de una solicitud
sustituida. El comando espera esa respuesta exacta, incluso si el log está
vacío. El dashboard muestra el último log recibido, escapado como texto, con
su intento y fecha; no solicita logs ni cancela jobs desde la página.

Actualizar coordinator y workers para usar este protocolo: un worker antiguo
sin ID de solicitud/intento recibirá rechazo al subir logs. La migración SQLite
es automática. Esto no publica ni actualiza imágenes por sí solo.

El barrido usa `/run/printProgress 1` por defecto; puede cambiarse con
`run_organ_sweep.py --print-progress-every N` (N positivo). No aumenta
`/event/verbose`. Un evento largo o la inicialización todavía pueden permanecer
sin salida: el crecimiento del archivo tampoco certifica avance físico.

El monitor de silencio usa tiempo monotónico y estas variables del worker:

- `WORKER_STALL_ACTION=warn` (default): avisa una vez por período de silencio;
  conserva el proceso. `off` desactiva esa alerta.
- `WORKER_STALL_TIMEOUT_S=1200` (default): umbral positivo en segundos.
- `WORKER_STALL_ACTION=kill`: terminación y reporte de fallo mediante el flujo
  normal de reintentos. Usar solo tras calibrar el umbral con tiempos de
  inicialización y de eventos en las especies/bins y equipos más lentos.

Los 20 minutos son una heurística operativa, no un límite físico validado.
Esta política sustituye el comportamiento anterior de matar automáticamente
por falta de bytes. La cancelación explícita del operador sigue disponible.

### Captura automática de diagnóstico

Al avisar por silencio, el worker guarda un JSON en el volumen de identidad:
`/var/lib/geant4-worker/diagnostics/job-ID-attempt-N-UUID.json`. Incluye las diez
últimas muestras (intervalo normal 30 s), CPU real por hilo (100 % = un núcleo),
árbol de procesos, estados/wchan, E/S, memoria, presión y contadores cgroup v2.
La primera muestra no tiene porcentaje; procesos desaparecidos o permisos
insuficientes se registran como datos no disponibles. Los contadores cgroup
corresponden al montaje visible en el contenedor y requieren interpretar deltas.

Incluye job/intento, comando, digest detectado, macros con semillas y tails de
logs/eventos (64 KiB por archivo). Tres capturas como máximo por job/intento;
los diagnósticos de intentos distintos se conservan hasta su limpieza manual.
No se suben al coordinator. El volumen debe mantenerse al recrear el contenedor.

El worker configura `G4_EVENT_DIAGNOSTICS_DIR` en el subprocess. La nueva acción
Geant4 registra begin/end por run/event/thread, con reloj monotónico y un archivo
por hilo. Un begin sin end en la cola capturada identifica un evento pendiente;
no demuestra bloqueo. Fuera del worker se activa creando un directorio y fijando
esa variable. Hace falta recompilar Geant4; no cambia semillas ni scoring.

La captura no detiene ni adjunta un debugger: intenta leer las pilas de kernel
de `/proc/PID/task/TID/stack`, que pueden no estar permitidas. **No son pilas C++**.
Para diagnosticar un deadlock nativo aún puede requerirse una captura supervisada
con debugger y símbolos. No se habilita ptrace ni se instala gdb automáticamente.
Fallar al capturar no cancela la corrida; `kill` sigue siendo una política optativa.
