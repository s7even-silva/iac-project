# Cómputo distribuido local (primer corte)

Rama `infra/distributed-sweep`. Coordinator FastAPI + SQLite WAL y worker
Geant4, reutilizando `scripts/install_compute_node.sh` sin modificarlo.
No despliega nube, no publica imágenes, no ejecuta los jobs caros de GCR_He.
La arquitectura genérica con imágenes separadas de Elmer/Geant4 es una fase
posterior; este worker ejecuta únicamente el lanzador Geant4 existente.

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

Activar el entorno Geant4 de la máquina y ejecutar el worker con un Python
que tenga `infra/worker/requirements.txt`. Debe heredar las variables G4 de
los datasets, además de encontrar las bibliotecas del ejecutable compilado.

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
`WORKER_THREADS` limita los hilos pedidos a Geant4 (default 1); no establece
un límite de memoria del contenedor. Para uso continuo montar un volumen en
`/var/lib/geant4-worker` y usar `--restart unless-stopped`.

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

Pendiente después del primer corte: despliegue protegido, publicación en GHCR,
versionado de imágenes por digest en jobs, requisitos CPU/RAM y jobs Elmer.
