# Cómo prestar tu PC para las runs del barrido de ActiveShield_Sim

Esto le presta CPU a tu computadora para correr simulaciones de Geant4
mientras la tengas encendida. No modifica ni borra nada tuyo — corre
completamente aislado dentro de un contenedor Docker.

Hoy la cola tiene runs de los bins 6 y 7 (los más pesados) de **GCR_He**
y **SEP_p** en las posiciones que quedaron pendientes — no es solo
GCR_He. Más adelante se van a agregar también **5 repeticiones por
combinación** (con semillas distintas) para poder calcular media,
desviación estándar e intervalo de confianza — mismo mecanismo, solo
más runs en la cola; no requiere que cambies nada de tu lado.

## 1. Instalar Docker (una sola vez)

**Linux (Ubuntu/Debian/Parrot):**
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```
Cierra sesión y vuelve a entrar (o reinicia) para que el permiso de grupo
tome efecto.

**Windows/Mac:** instalar [Docker Desktop](https://www.docker.com/products/docker-desktop/)
normal, abrirlo una vez para que arranque el motor.

## 2. Correr el worker (un solo comando)

```bash
docker run -d --name geant4-worker --restart unless-stopped \
  -e COORDINATOR_URL=http://34.134.100.224:8000 \
  -e WORKER_LABEL=<tu-nombre> \
  ghcr.io/s7even-silva/iac-project/geant4-worker:latest
```

Cambia `<tu-nombre>` por algo que te identifique (ej. `laptop-juan`) — así
sabemos de quién es cada run si algo falla.

**La primera vez tarda unos minutos** en descargar la imagen (~5GB,
incluye Geant4 ya compilado). Después de eso, arranca en segundos.

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
```bash
docker stop geant4-worker
```
Para retomar después:
```bash
docker start geant4-worker
```
Para quitarlo del todo:
```bash
docker rm -f geant4-worker
```

**¿Puedo darle menos CPU o RAM para no ralentizar mi PC mientras trabajo?**
Sí, dos formas:

- **Limitar cuántos núcleos usa Geant4** (recomendado, más simple):
  ```bash
  docker run -d --name geant4-worker --restart unless-stopped \
    -e COORDINATOR_URL=http://34.134.100.224:8000 \
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
    -e COORDINATOR_URL=http://34.134.100.224:8000 \
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
- http://34.134.100.224:8000/api/v1/health — resumen general
- http://34.134.100.224:8000/api/v1/workers — lista de quién está
  conectado ahora mismo (verás tu `WORKER_LABEL` ahí)
