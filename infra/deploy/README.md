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
python -m pytest -q infra/worker/test_worker.py infra/coordinator/test_coordinator.py
for script in infra/deploy/*.sh; do bash -n "$script"; done
```

Los mocks prueban ausencia de efectos con `-WhatIf`, validación de flags,
conservación/borrado explícito de datos, fallo del daemon y del respaldo,
autocopia, argumentos Azure y fallos GCP. No sustituyen una prueba Windows real.

Resultado de esta revisión: 12 escenarios PowerShell con mocks y 4 pruebas Bash
con CLI simulados aprobados; 30 pruebas existentes de worker/coordinator aprobadas.
Estas últimas se ejecutaron con las dependencias fijadas de
`infra/coordinator/requirements.txt` en un venv temporal bajo `/tmp`, sin cambiar
el entorno del proyecto. Sintaxis de los cuatro PowerShell y tres Bash validada.
