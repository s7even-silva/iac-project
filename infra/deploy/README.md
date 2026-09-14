# Instalación y retirada del worker (Windows)

Usar PowerShell como administrador **con la misma cuenta que instaló el worker**.
Ejecutar los archivos del checkout actualizado; `uninstall-worker.ps1` queda como
entrada compatible que delega en `install-worker.ps1` del mismo directorio.

```powershell
.\infra\deploy\install-worker.ps1                         # instalar / actualizar
.\infra\deploy\install-worker.ps1 -Action Uninstall -WhatIf # revisar sin ejecutar
.\infra\deploy\install-worker.ps1 -Action Uninstall         # retirar solo worker
.\infra\deploy\install-worker.ps1 -Action Uninstall -RemoveDockerAutostart
```

La retirada pide confirmación, elimina el contenedor, las tareas watchdog/reanudación
y la marca de pausa. Conserva `geant4-worker-data`, logs y respaldos. No contacta
al coordinator ni descarga imágenes. Si Docker está instalado pero no responde,
aborta: iniciar Docker Desktop antes de reintentar. Un fallo de un comando no se
presenta como éxito; tras un fallo parcial se puede reejecutar.

Opciones adicionales, **destructivas**, elegidas por quien ejecuta:

```powershell
# Eliminar también identidad y resultados pendientes del worker:
.\infra\deploy\install-worker.ps1 -Action Uninstall -RemoveWorkerData
# Retirar Docker Desktop (afecta TODOS sus proyectos y volúmenes):
.\infra\deploy\install-worker.ps1 -Action Uninstall -RemoveWorkerData -RemoveDocker
# Además retirar WSL del usuario y desactivar sus características de Windows:
.\infra\deploy\install-worker.ps1 -Action Uninstall -RemoveWorkerData -RemoveDocker -RemoveWSL
```

`-RemoveDocker` exige `-RemoveWorkerData`: el desinstalador oficial destruye los
contenedores, imágenes y volúmenes locales, no solo los nuestros. Se comprueban
las rutas oficiales de instalación global y por usuario y el código de salida.
No se borran automáticamente directorios residuales ni credenciales `~/.docker`.
[Referencia oficial Docker](https://docs.docker.com/desktop/uninstall/).

`-RemoveWSL` retira el paquete Store del usuario actual y desactiva
`Microsoft-Windows-Subsystem-Linux` y `VirtualMachinePlatform`, sin reiniciar
automáticamente. Puede afectar otras aplicaciones y requiere reinicio manual.
Si se detecta Docker Desktop instalado exige retirarlo también. No desregistra
distribuciones Linux, borra sus discos ni desinstala paquetes de otros usuarios.
Esto es intencional: `wsl --unregister` borra permanentemente los datos de la
distribución ([Microsoft](https://learn.microsoft.com/en-us/windows/wsl/basic-commands#unregister-or-uninstall-a-linux-distribution)).

## Resultados pendientes y migración

`worker.py` guarda identidad y `pending_results/` en `/var/lib/geant4-worker`.
Conservar solo `worker_id` era insuficiente. La actualización ahora detiene el
contenedor antiguo sin volumen, copia **todo** ese directorio a
`%ProgramData%\Geant4Worker\legacy-data-<UUID>` y lo restaura en el volumen antes
de arrancar el reemplazo. Si la copia falla, conserva el contenedor detenido.
Si falla la restauración, conserva el respaldo y aborta; recuperar ese directorio
en el volumen antes de reintentar la instalación. Los respaldos no se borran con
`-RemoveWorkerData` (esa opción borra el volumen, no los archivos del host).

La retirada de un contenedor antiguo también respalda ese directorio cuando no
se pidió borrar datos, pero **no lo restaura automáticamente al reinstalar**:
recuperarlo en `geant4-worker-data` antes de iniciar otro worker. El instalador
solo monta ese volumen en `/var/lib/geant4-worker`; se comprueba nombre y destino.

La persistencia no es una confirmación de entrega: un worker debe volver a
arrancar para reintentar los resultados y el coordinator puede rechazarlos tras
vencer su plazo. Una simulación interrumpida se repite; su progreso en memoria no
se conserva. La lógica de outbox/timeout de `worker.py` no se modificó.

## Auto-actualización de workers Docker: protocolo revisado

La identidad Docker se obtiene desde `/proc/self/mountinfo` o cgroups, con
fallback solo a hostnames que tengan formato de ID. La prueba real con
`--network host` mostró que `platform.node()` puede devolver el hostname de la
PC; no se usa ese nombre para inspeccionar/eliminar contenedores. Si no se
puede identificar el contenedor, la actualización se desactiva sin adivinar.

El diseño anterior tenía fallos de relevo: el heartbeat del padre podía
confirmar falsamente al hijo; el hijo ya podía reclamar jobs antes de ser
aceptado; su nombre temporal rompía pausa/watchdog/desinstalación; los fallos
de start podían dejar reemplazos huérfanos. Esta revisión sustituye ese protocolo.

1. Entre jobs, consultar `worker_image_digest` y comparar **digest de manifiesto
   del registro**, no `docker inspect .Image` (ID de configuración de imagen).
   Para referencias fijadas `repo@sha256:...` se usa ese digest; para tags se
   consulta `RepoDigests`. Un registro con puerto conserva su nombre completo.
2. Descargar el candidato y exigir la etiqueta de imagen
   `org.iac.worker-update-protocol=1`. Imágenes antiguas sin standby se rechazan;
   no sirve para actualizar automáticamente a cualquier imagen histórica.
3. Crear el candidato sin restart automático inicial, con el mismo volumen,
   socket, variables, límites y labels. El nuevo token sustituye al de cualquier
   actualización anterior. Se exige volumen persistente; `--rm`, redes custom
   y comandos/user/workdir personalizados requieren actualización manual. Los
   valores por defecto ausentes/vacíos de Docker se normalizan (por ejemplo
   `User` omitido en imagen y `User=""` en contenedor no son una personalización).
4. El candidato valida binario/scripts, identidad y digest, envía **su propio**
   heartbeat y comprueba el HTTP de respuesta. Solo entonces escribe una
   confirmación atómica con nonce e ID de contenedor en el volumen. No registra
   otra instancia, no toca el outbox ni pide jobs durante esta espera.
5. El padre verifica esa confirmación y que el candidato siga running. Renombra
   el padre a `...-retired-...`, entrega el nombre original al hijo y conserva la
   política de reinicio original en este. Publica el commit del relevo en disco,
   desactiva su propio restart y termina limpiamente (sin hacerse `docker rm -f`).
6. Un `flock` compartido durante toda la vida activa impide dos lectores/escritores
   del outbox y dos procesos solicitando jobs con el mismo volumen. Tras salir
   el padre, el hijo adquiere el lock, registra su digest nuevo, recupera resultados
   pendientes y trabaja. Elimina el contenedor retirado sin forzarlo.

Si falla la preparación, se elimina el candidato y se restaura el nombre del
padre; los fallos de transporte se tratan como errores, no como éxito. Un timeout
de `create` se limpia por el nombre determinista. Si falla el rollback, se aborta
sin pedir más jobs y se necesita revisar Docker. Tras un crash y reinicio del
padre, el journal permite deshacer la preparación o retirarse si ya hubo commit.
El restart original del padre se conserva hasta commit precisamente para poder
recuperarlo. No se arrancan por fuerza contenedores pausados por el usuario.

El journal `update-<nonce>.{request,ready,commit}` es pequeño y queda en el volumen
para recuperación; **no borrar `worker.lock` ni journals mientras exista un
contenedor asociado**. No es un checkpoint de Geant4: reiniciar el host durante
una simulación pierde su progreso en memoria. La política de recuperación de jobs
sigue siendo la del coordinator.

Un intento fallido espera cinco minutos antes de volver a descargar. El worker
puede seguir tomando jobs con su imagen actual; la autoactualización no impone
una barrera global de versión al barrido. `WORKER_AUTO_UPDATE=0` la desactiva.
El instalador acepta `-WorkerAutoUpdate 0`, conserva ese valor en actualizaciones
y conserva la imagen actual si no se pasa `-WorkerImage` explícitamente; así un
instalador con pin antiguo no revierte una autoactualización ya hecha.

### Orden de publicación y activación

**Corregido el checklist anterior:** no activar en el coordinator un digest que
aún no existe en el registro. Preparar la actualización antes de publicar no
significa anunciarla a todos los workers antes de que pueda descargarse.

1. Revisar código/documentación, ejecutar las pruebas aisladas y aprobar el código
   antes del push. No usar el coordinator de producción para pruebas Docker.
2. Construir/publicar el candidato inmutable y comprobar su digest de manifiesto
   y su etiqueta de protocolo. Validarlo en un worker canario con un coordinator
   de prueba. La primera instalación de este mecanismo exige actualizar
   manualmente los workers antiguos que todavía no lo incluyen.
3. Actualizar el pin del instalador y su distribución tras reinicios. El fallback
   histórico `$InstallScriptCommit` sigue necesitando un commit publicado correcto.
4. **Después de validar el candidato publicado**, activar el digest en la SQLite
   real del servicio. `--db` (o `COORDINATOR_DB`) es obligatorio al modificarlo y
   la DB debe existir, para no escribir silenciosamente una DB local distinta:

   ```bash
   python3 infra/coordinator/set_worker_image.py --db /var/lib/geant4-coordinator/coordinator.db sha256:<64-hex>
   python3 infra/coordinator/set_worker_image.py --db /var/lib/geant4-coordinator/coordinator.db --show
   # Frenar nuevos intentos de actualización (no revierte un relevo en curso):
   python3 infra/coordinator/set_worker_image.py --db /var/lib/geant4-coordinator/coordinator.db --clear
   ```

   Esa ruta corresponde al `cloud-init` del repo; confirmar la ruta en la
   configuración del servicio real. No ejecutar contra otra copia de la DB.
5. Comparar `/health` y `/workers.image_digest`, comprobar jobs/resultados y que
   pausa/reanudación encuentren el nombre original. Volver a una versión previa
   requiere otro digest compatible con protocolo 1, o actualización manual.

El socket Docker mantiene el permiso amplio ya aceptado por el equipo. Esta
revisión no activa ningún digest en producción ni publica imágenes externas.
Referencia de los campos y operaciones:
[Docker Engine API](https://docs.docker.com/reference/api/engine/version/v1.47/).

## Errores corregidos en esta revisión

- Primera instalación: consultar configuración ya no invoca Docker si falta el CLI.
- Actualización: conserva URL, token, hilos, límite `--cpus` y memoria cuando no
  se pasan explícitamente; evita copiar el instalador sobre sí mismo. Los scripts
  auxiliares se toman primero del directorio local, conservando su versión.
- Virtualización: un hipervisor ya presente no se interpreta como BIOS desactivado.
- Pausa: `pause-worker.ps1` sin argumentos pausa; un fallo de Docker se comunica.
  Al reanudar, no se borra la marca hasta que `docker start` tenga éxito.
- Azure: acepta `--location valor` y `--vm-size valor` como en su ejemplo; se quitó
  una instrucción inválida (`az vm open-port --source-address-prefixes`).
- GCP: rechaza proyecto `(unset)`; los fallos al crear reglas de firewall abortan
  antes de crear la VM, en lugar de ocultarse con `|| true`.
- HTTPS: valida dominio/root, consulta IPv4 con timeout y HTTP con errores,
  acepta cualquiera de los registros A del dominio, permite repetir la importación
  de la clave GPG sin prompt y valida Caddy antes de reiniciarlo. Un fallo del
  firewall GCP tampoco se oculta.

## Límites de la revisión

No se ejecutaron desinstalaciones reales en Windows ni se desplegó infraestructura.
Las pruebas PowerShell usan mocks y PowerShell 7 en Linux; falta comprobar en una
VM Windows el ciclo instalar/pausar/retirar/reinstalar y las variantes de WSL.
No se garantiza conservar opciones arbitrarias de un `docker run` manual
(por ejemplo cpuset o mounts adicionales); solo los parámetros soportados.

El camino histórico `irm | iex` aún descarga la autocopia y auxiliares desde el
commit fijado en `$InstallScriptCommit`, que no incluye esta revisión. Para usar
estos cambios y conservarlos tras reinicio, ejecutar los **archivos locales del
checkout actualizado**; actualizar el pin cuando se publique un commit probado.

`cloud-init-coordinator.yaml` sigue clonando una rama mutable y no configura
WORKER_TOKEN; los provisionadores exponen 8000. Es el flujo de prueba existente,
no una configuración de producción autenticada/reproducible. No se cambiaron
credenciales, VM ni reglas existentes durante esta revisión.

## Verificación local sin despliegue

```bash
python -m unittest discover -s infra/deploy/tests -p 'test_*.py'
pwsh -NoProfile -File infra/deploy/tests/test_worker_lifecycle.ps1
python -m pytest -q infra/worker infra/coordinator
for script in infra/deploy/*.sh; do bash -n "$script"; done
```

Los mocks prueban ausencia de efectos con `-WhatIf`, validación de flags,
conservación/borrado explícito de datos, fallo del daemon y del respaldo,
autocopia, argumentos Azure y fallos GCP. No sustituyen una prueba Windows real.

Las pruebas normales incluyen un servidor HTTP sobre socket Unix temporal (sin
Docker real) y bloqueo entre procesos. Requieren permiso para crear sockets
locales. Prueba opcional adicional:

```bash
RUN_DOCKER_UPDATE_E2E=1 python -m pytest -q infra/worker/test_update_docker_e2e.py
```

Construye dos imágenes **locales de ensayo** desde una imagen worker ya instalada
(sin recompilar Geant4), inicia una API ficticia en localhost y comprueba relevo
exitoso y rechazo del heartbeat del candidato. No ejecuta jobs de simulación, no
accede al coordinator real y no publica imágenes. La resolución/pull del registro
se sustituye por tags locales en este ensayo; las operaciones create/start/rename,
políticas de reinicio, lock, identidad compartida y limpieza usan Docker real.
Contenedores, volumen e imágenes tienen nombres aleatorios de prueba y se retiran
al terminar; no se hace prune. No sustituye un canario con digest publicado ni
una validación real de Windows/Docker Desktop.

Resultado final de la revisión (2026-09-13): **64 pruebas Python aprobadas**;
las dos pruebas Docker opt-in se ejecutaron aparte y **ambas aprobaron** con
Docker Engine 29.8.0 en Linux (relevo y rechazo real del heartbeat del candidato).
Además, 16 escenarios PowerShell simulados y 4 pruebas Bash aprobaron; sintaxis
PowerShell validada. La integración detectó y permitió corregir dos casos que
los mocks no cubrían: hostname compartido con red host y `User` ausente frente
a cadena vacía. Se confirmó la limpieza de contenedores, imágenes etiquetadas y
volúmenes de ensayo, y que el servicio previo seguía activo. No se cambió la DB
real ni se publicó imagen externa. Quedan como condiciones del despliegue el
canario con digest del registro real y la prueba en Windows/Docker Desktop.
