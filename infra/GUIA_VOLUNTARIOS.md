# Cómo prestar tu PC para las runs del barrido de ActiveShield_Sim

Esto le presta CPU a tu computadora para correr simulaciones de Geant4
mientras la tengas encendida. La simulación en sí corre completamente
aislada dentro de un contenedor Docker, sin acceder ni modificar tus
documentos personales. El instalador automático (ver más abajo) sí
instala y configura software en tu PC (WSL2, Docker Desktop) para poder
correr ese contenedor — no toca nada tuyo más allá de eso.

Hoy la cola tiene runs de los bins 6 y 7 (los más pesados) de **GCR_He**
y **SEP_p** en las posiciones que quedaron pendientes — no es solo
GCR_He. Más adelante se van a agregar también **5 repeticiones por
combinación** (con semillas distintas) para poder calcular media,
desviación estándar e intervalo de confianza — mismo mecanismo, solo
más runs en la cola; no requiere que cambies nada de tu lado.

## Windows: instalador automático (recomendado)

Si estás en Windows, hay un script que hace todos los pasos de abajo
por ti — verifica requisitos, instala WSL2 y Docker Desktop si faltan,
los configura para arrancar solos, y deja el worker corriendo y
conectado. Requiere permisos de administrador (te lo va a pedir Windows
con el aviso normal de UAC).

Abre **PowerShell como administrador** (clic derecho → "Ejecutar como
administrador") y corre:
```powershell
irm https://raw.githubusercontent.com/s7even-silva/iac-project/infra/distributed-sweep/infra/deploy/install-worker.ps1 | iex
```

Si tu PC necesita instalar WSL2 por primera vez, Windows va a pedir
**reiniciar una vez** — el script te avisa antes de hacerlo, y al
volver a iniciar sesión continúa solo (se abre una ventana negra
mostrando el progreso, no hace falta que corras nada de nuevo).

El script te va a **preguntar** con qué nombre identificarte en el
coordinator (Enter usa tu usuario de Windows). Si prefieres saltarte la
pregunta, pásalo directo — para eso hace falta descargar el script
primero (`Guardar como` desde ese mismo link) en vez de correrlo directo
del `irm | iex`:
```powershell
.\install-worker.ps1 -WorkerLabel "laptop-juan"
```

**Si no quieres ceder toda tu PC**, puedes limitar cuánta CPU/RAM usa el
contenedor (límite duro, más estricto que `WORKER_THREADS`):
```powershell
.\install-worker.ps1 -WorkerLabel "laptop-juan" -Cpus 2 -MemoryLimit 4g
```

**Para actualizar** (hay una imagen nueva del worker, o simplemente
quieres asegurarte de tener la última): corre exactamente el mismo
comando de arriba de nuevo — el script detecta solo que ya tienes un
worker instalado (con este mismo instalador **o** con el `docker run`
manual de la sección de abajo, no importa cuál usaste la primera vez),
conserva tu nombre actual sin volver a preguntarlo, y salta directo a
descargar la imagen nueva sin repetir las verificaciones de WSL2/Docker
Desktop (ya sabe que funcionan porque tu worker ya está corriendo):
```powershell
irm https://raw.githubusercontent.com/s7even-silva/iac-project/infra/distributed-sweep/infra/deploy/install-worker.ps1 | iex
```

**Para quitar todo después** (contenedor + las tareas automáticas que
el instalador programó — Docker Desktop en sí no se desinstala):
```powershell
irm https://raw.githubusercontent.com/s7even-silva/iac-project/infra/distributed-sweep/infra/deploy/uninstall-worker.ps1 | iex
```

Si prefieres los pasos manuales (o estás en Linux/Mac), sigue leyendo.

## 1. Instalar Docker (una sola vez)

**Linux (Ubuntu/Debian/Parrot):**
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```
Cierra sesión y vuelve a entrar (o reinicia) para que el permiso de grupo
tome efecto.

**Windows — verificar WSL2 antes de instalar (evita el error más común):**
Docker Desktop en Windows necesita WSL2 para funcionar. En una PC con
Windows actualizado normalmente ya lo tiene o el instalador de Docker lo
agrega solo — pero si tu Windows lleva tiempo sin actualizarse, puede
faltar y Docker Desktop falla al abrir con un diagnóstico genérico (un
código largo tipo `FFFBB9CB-...`) que no dice "falta WSL2" directamente.
Para no toparte con eso a medias, revisa primero, en CMD o PowerShell:
```
wsl --status
```
Si da error o dice que no está instalado:
```
wsl --install
```
y **reinicia la PC** — después de eso instala Docker Desktop normal. Si
`wsl --status` ya muestra información (sin error), no hace falta hacer
nada de esto, sigue directo a instalar Docker Desktop.

**Windows/Mac:** instalar [Docker Desktop](https://www.docker.com/products/docker-desktop/)
normal, abrirlo una vez para que arranque el motor.

**Importante en Windows/Mac (no aplica a Linux):** por defecto, Docker
Desktop **no** arranca solo cuando prendes tu PC — hay que abrir la
aplicación manualmente cada vez, o el worker no puede correr aunque
tenga `--restart unless-stopped` (esa opción solo hace que el
*contenedor* se retome una vez que el motor de Docker ya esté
corriendo). Para que quede realmente automático:

1. Abrir Docker Desktop → ícono de engranaje (**Settings**) → pestaña
   **General**.
2. Activar **"Start Docker Desktop when you sign in"** (el nombre
   exacto puede variar un poco según la versión).

Con esto, el motor de Docker arranca solo al iniciar sesión en tu PC, y
el contenedor se retoma solo detrás — no hace falta abrir la ventana de
Docker Desktop para nada después de la primera vez.

## 2. Correr el worker (un solo comando)

```bash
docker run -d --name geant4-worker --restart unless-stopped \
  -e COORDINATOR_URL=https://coordinator.vlaboratory.org \
  -e WORKER_LABEL=<tu-nombre> \
  ghcr.io/s7even-silva/iac-project/geant4-worker:latest
```

Cambia `<tu-nombre>` por algo que te identifique (ej. `laptop-juan`) — así
sabemos de quién es cada run si algo falla.

**La primera vez tarda unos minutos** en descargar la imagen (~5GB,
incluye Geant4 ya compilado). Después de eso, arranca en segundos.

**Para actualizar más adelante (hay imagen nueva), en Windows con
Docker Desktop:** no hace falta repetir el `docker run` de arriba a
mano — el instalador de PowerShell de la sección anterior también sirve
para esto, sin importar que hayas instalado por este camino manual.
Corre el mismo comando de esa sección; detecta tu worker ya existente,
conserva tu `WORKER_LABEL` actual, y solo descarga la imagen nueva. En
Linux/Mac, sigue siendo el mismo `docker run` de arriba (con la misma
`<tu-nombre>` que ya usabas) — Docker reemplaza el contenedor solo si
das `docker rm -f geant4-worker` primero.

## 3. Ya está — no hay que hacer nada más

El contenedor:
- Se conecta solo al servidor central y pide trabajo.
- Corre una simulación real (puede tardar de minutos a **varias horas**
  según qué combinación le toque — los bins 6 y 7 son los más caros del
  barrido; SEP_p en esos mismos bins es bastante más rápido).
- Cuando termina, sube el resultado automáticamente y pide la siguiente
  run.
- Con `--restart unless-stopped`: **si reinicias tu PC, el contenedor
  vuelve a arrancar solo** y retoma donde estaba (no pierde nada — si
  estaba a mitad de una run cuando apagaste, esa run en particular se
  pierde y el servidor se la vuelve a asignar a quien esté disponible,
  pero todo lo ya terminado y subido queda guardado para siempre).

## Cómo se reparte el trabajo según tu PC

No todas las runs pesan igual:

- **GCR_He bin6, SEP_p bin6/bin7**: livianos a moderados. Cualquier PC
  puede tomarlos.
- **GCR_He bin7**: el más pesado (~5-6h estimadas por run). El servidor
  **solo se lo ofrece a una PC con al menos 8GB de RAM libre y 4
  núcleos disponibles en ese momento** — tu worker reporta esos datos
  automáticamente en cada heartbeat (cada 30s), sin que tengas que
  configurar nada. Si tu PC no alcanza ese mínimo, simplemente nunca te
  tocará esa run — te asignará otra cosa o esperará, sin error ni
  problema de tu lado.

## Preguntas frecuentes

**¿Si apago mi PC a mitad de una run se pierde algo del proyecto?**
No. Solo se repite esa run puntual (el servidor detecta que dejaste de
responder y se la ofrece a otra persona). Nada de lo ya subido se
pierde nunca.

**¿Puedo desconectar mi PC un día sin avisar?**
Sí, sin problema. El sistema está pensado exactamente para eso — nadie
necesita estar disponible todo el tiempo.

**¿Cómo dejo de prestar mi PC (aunque sea por un rato)?**

Si instalaste con el **instalador automático de Windows**, el propio
instalador ya dejó dos scripts listos en `C:\ProgramData\Geant4Worker\`
— no hace falta descargar nada aparte. Usa esos, no `docker stop`
directo: el instalador dejó un watchdog corriendo cada 30 min que
volvería a levantar el contenedor solo si lo detienes con `docker stop`
a secas.
```powershell
C:\ProgramData\Geant4Worker\pause-worker.ps1
```
Para retomar:
```powershell
C:\ProgramData\Geant4Worker\resume-worker.ps1
```
(Si vuelves a correr `install-worker.ps1` mientras está pausado, respeta
la pausa — no reactiva el contenedor por su cuenta.)

Si instalaste manualmente (Linux/Mac, sin el instalador de Windows):
```bash
docker stop geant4-worker
```
Para retomar después:
```bash
docker start geant4-worker
```
Para quitarlo del todo (cualquier sistema):
```bash
docker rm -f geant4-worker
```

**¿Puedo darle menos CPU o RAM para no ralentizar mi PC mientras trabajo?**
Sí, dos formas:

- **Limitar cuántos núcleos usa Geant4** (recomendado, más simple):
  ```bash
  docker run -d --name geant4-worker --restart unless-stopped \
    -e COORDINATOR_URL=https://coordinator.vlaboratory.org \
    -e WORKER_LABEL=<tu-nombre> \
    -e WORKER_THREADS=2 \
    ghcr.io/s7even-silva/iac-project/geant4-worker:latest
  ```
  (`WORKER_THREADS=2` usa solo 2 núcleos en vez de todos los disponibles
  — la run tarda más pero deja el resto de tu PC libre).

- **Limitar el contenedor directamente** (más estricto, límite duro de
  Docker):
  ```bash
  docker run -d --name geant4-worker --restart unless-stopped \
    -e COORDINATOR_URL=https://coordinator.vlaboratory.org \
    -e WORKER_LABEL=<tu-nombre> \
    --cpus=2 --memory=4g \
    ghcr.io/s7even-silva/iac-project/geant4-worker:latest
  ```
  (`--cpus=2` tope de 2 núcleos, `--memory=4g` tope de 4GB de RAM —
  ajustar según cuánto quieras reservar para ti).

**¿Necesito buena conexión a internet?**
No especialmente — el contenedor sube solo un archivo CSV pequeño al
terminar cada run (unos KB), no tráfico constante. Sí necesita estar
conectado, simplemente no importa la velocidad.

**Uso una VM y le voy a bajar la RAM/CPU después — ¿hay problema?**
Depende de cuándo pase:
- **Antes de que tome la siguiente run:** ningún problema. El servidor
  revisa tus recursos disponibles *en ese momento* cada vez que pides
  trabajo nuevo — si ya no cumples el mínimo para GCR_He bin7, no te lo
  va a ofrecer, te dará algo más liviano o esperará.
- **A mitad de una run que ya empezó:** ahí sí hay un caso a tener en
  cuenta — el servidor no vuelve a comprobar tus recursos mientras la
  simulación ya está corriendo. Si la memoria baja tanto que el proceso
  se cae, no pasa nada grave: se reporta como fallo y el servidor la
  vuelve a asignar a otra PC automáticamente (nada se pierde). Si la VM
  sigue funcionando pero mucho más lenta, la run simplemente tardará
  más de lo esperado. En cualquier caso, mejor evitarlo si puedes —
  bájale recursos a la VM entre runs, no mientras `docker logs -f
  geant4-worker` muestre una run en curso.

**¿Cómo sé si mi PC está aportando de verdad?**
Ver el log en vivo:
```bash
docker logs -f geant4-worker
```
O consultar el estado general del servidor desde cualquier navegador
(computadora o celular):
- https://coordinator.vlaboratory.org/api/v1/health — resumen general
- https://coordinator.vlaboratory.org/api/v1/workers — lista de quién está
  conectado ahora mismo (verás tu `WORKER_LABEL` ahí)
