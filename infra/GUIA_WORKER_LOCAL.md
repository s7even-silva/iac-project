# Cómo correr un worker sin Docker (laptops del equipo, proyecto ya instalado)

Esta guía es para compañeros que **ya clonaron este repo y ya compilaron
`ActiveShield_Sim`** (siguieron `README.md`/`scripts/install.sh` en algún
momento) — no para voluntarios externos sin nada instalado. Si tu caso es
ese segundo, usa [`GUIA_VOLUNTARIOS.md`](GUIA_VOLUNTARIOS.md) (Docker, un
solo comando, no necesita el repo compilado). Esta vía **no usa Docker en
absoluto** — corre el worker directo contra tu build ya compilado, así que
no hay imagen de ~5GB que descargar ni motor de contenedores que instalar.

## Requisitos (si ya compilaste el proyecto antes, ya los tienes)

- El repo clonado, con `geant4/ActiveShield_Sim/build/ICRP110phantoms`
  compilado (ver `README.md` de ese proyecto si te falta).
- El entorno conda `geant4_env` (de `scripts/install.sh`).
- El paquete `requests` de Python — normalmente ya está disponible en el
  Python del sistema; si no, `pip install -r infra/worker/requirements.txt
  --user`.

No hace falta instalar nada nuevo más allá de eso.

## 1. Traer el código del worker

El worker (`infra/worker/worker.py`) vive en la rama `infra/distributed-sweep`,
no en `main` todavía. Traerla no toca tu `main` ni requiere mergear nada:

```bash
cd iac-project   # tu clon existente
git fetch origin
git checkout -b infra/distributed-sweep origin/infra/distributed-sweep
```

(Si ya tenías esa rama localmente, `git checkout infra/distributed-sweep &&
git pull` alcanza.) Tu `build/` de `ActiveShield_Sim` no está versionado en
git, así que cambiar de rama no lo toca ni lo invalida.

## 2. Activar el entorno y lanzar el worker

```bash
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate geant4_env

mkdir -p "$HOME/.geant4-worker"
nohup env \
  COORDINATOR_URL=https://coordinator.vlaboratory.org \
  WORKER_LABEL=<tu-nombre> \
  WORKER_ID_FILE="$HOME/.geant4-worker/worker_id" \
  WORKER_THREADS=$(nproc) \
  python3 infra/worker/worker.py > "$HOME/.geant4-worker/worker.log" 2>&1 &
disown
```

- `conda activate geant4_env` es necesario para que el binario encuentre
  las librerías de Geant4 (`LD_LIBRARY_PATH`) y los datasets (`G4*DATA`) —
  sin esto el `subprocess` que lanza el worker falla al arrancar.
- `WORKER_ID_FILE` apunta a tu `$HOME` en vez del default
  (`/var/lib/geant4-worker/worker_id`, pensado para el contenedor Docker,
  que corre como root) — así tu worker conserva el mismo id entre
  reinicios sin necesitar permisos de escritura fuera de tu usuario.
- `WORKER_THREADS=$(nproc)` reproduce la configuración con la que se
  midió la tabla de tiempos real del piloto (14 hilos, ver AGENTS.md,
  sección "Piloto de 8 bins") — con menos hilos la misma run tarda
  bastante más que la estimación documentada. Bájalo si quieres dejar
  núcleos libres para seguir usando la laptop (ver más abajo).
- `nohup ... & disown` deja el worker corriendo aunque cierres la
  terminal — igual que `--restart unless-stopped` en la versión Docker,
  pero no sobrevive un reinicio de la laptop por sí solo (si reinicias,
  hay que volver a correr el comando).

Sin `WORKER_ONCE=1`, el worker sigue pidiendo trabajo indefinidamente
después de terminar cada job — igual que un voluntario de
`GUIA_VOLUNTARIOS.md`. El coordinator asigna automáticamente el job de
mayor prioridad que tus recursos (RAM libre / núcleos, reportados en vivo
en cada heartbeat) puedan cumplir — no hace falta pedir un bin específico.

## 3. Verificar y monitorear

```bash
tail -f "$HOME/.geant4-worker/worker.log"
```

O desde cualquier navegador:
- https://coordinator.vlaboratory.org/api/v1/health — resumen general
- https://coordinator.vlaboratory.org/api/v1/workers — verás tu `WORKER_LABEL` con
  `status: online` una vez que mande el primer heartbeat.

## 4. Detenerlo

```bash
pkill -f infra/worker/worker.py
```

Si te agarra a mitad de una simulación, esta mata también el proceso de
Geant4 (el worker corre el subprocess en su propio grupo de procesos).
El coordinator reencola esa run puntual a otro worker tras 6h sin
heartbeat — nada de lo ya subido se pierde, ver "Heartbeat y recuperación"
en `infra/README.md`.

## Limitar recursos (si no quieres ceder toda la laptop)

- **Núcleos lógicos que pide Geant4:** `WORKER_THREADS=<N>` en el comando
  de arriba (ej. `WORKER_THREADS=4` en vez de `$(nproc)`) — la run tarda
  más, pero deja el resto de núcleos libres.
- **Límite duro de CPU/RAM del proceso** (opcional, mismo mecanismo que ya
  usa el proyecto para las corridas de Elmer, ver AGENTS.md): envolver el
  `nohup ...` de arriba con `systemd-run --scope -p CPUQuota=400% -p
  MemoryMax=8G` (Linux con systemd). La versión Docker logra esto con
  `--cpus`/`--memory`; aquí no hay contenedor, así que si no usas
  `systemd-run`, no hay límite duro — solo el lógico de `WORKER_THREADS`.

## Diferencias con la vía Docker (`GUIA_VOLUNTARIOS.md`)

Mismo coordinator, mismos jobs, mismo protocolo de heartbeat/reencolado —
la única diferencia es que aquí el worker corre directo sobre tu Python y
tu build ya compilados en vez de dentro de una imagen. Un mismo `git
checkout` de la rama y un `conda activate` es todo lo que necesita
cualquier compañero que ya tenga el proyecto instalado; nadie tiene que
instalar Docker Desktop ni descargar la imagen de ~5GB.
