# Cómo prestar tu PC para las corridas de GCR_He (bin6/bin7)

Esto le presta CPU a tu computadora para correr simulaciones de Geant4
mientras la tengas encendida. No modifica ni borra nada tuyo — corre
completamente aislado dentro de un contenedor Docker.

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
sabemos de quién es cada corrida si algo falla.

**La primera vez tarda unos minutos** en descargar la imagen (~5GB,
incluye Geant4 ya compilado). Después de eso, arranca en segundos.

## 3. Ya está — no hay que hacer nada más

El contenedor:
- Se conecta solo al servidor central y pide trabajo.
- Corre una simulación real (puede tardar de minutos a **varias horas**
  según qué combinación le toque — los bins 6 y 7 son los más caros del
  barrido).
- Cuando termina, sube el resultado automáticamente y pide el siguiente.
- Con `--restart unless-stopped`: **si reinicias tu PC, el contenedor
  vuelve a arrancar solo** y retoma donde estaba (no pierde nada — si
  estaba a mitad de una simulación cuando apagaste, esa simulación en
  particular se pierde y el servidor se la vuelve a asignar a quien esté
  disponible, pero todo lo ya terminado y subido queda guardado para
  siempre).

## Preguntas frecuentes

**¿Si apago mi PC a mitad de una corrida se pierde algo del proyecto?**
No. Solo se repite esa corrida puntual (el servidor detecta que dejaste
de responder y se la ofrece a otra persona). Nada de lo ya subido se
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
  — la simulación tarda más pero deja el resto de tu PC libre).

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
terminar cada corrida (unos KB), no tráfico constante. Sí necesita estar
conectado, simplemente no importa la velocidad.

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
