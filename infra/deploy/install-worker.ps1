#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Instala y deja corriendo el worker de computo distribuido de
    ActiveShield_Sim en una PC Windows, sin que el voluntario tenga que
    hacer nada mas alla de correr este script (una o dos veces, si hace
    falta reiniciar por WSL2).

.DESCRIPTION
    Ver infra/GUIA_VOLUNTARIOS.md para el contexto del proyecto. Este
    script reemplaza los pasos manuales de esa guia (verificar WSL2,
    instalar Docker Desktop, activar su auto-inicio, correr el docker run)
    por un solo instalador idempotente:

      1. Verifica que la CPU soporte virtualizacion y que este habilitada
         en firmware (VT-x/AMD-V) -- sin esto ni WSL2 ni Docker pueden
         funcionar, y el error que dan por separado no es claro.
      2. Instala/actualiza WSL2 si hace falta. Si Windows exige reiniciar
         para terminar esa instalacion, el script se registra a si mismo
         (Scheduled Task de un solo uso, AtLogOn) para continuar
         automaticamente en el siguiente inicio de sesion -- el
         voluntario no tiene que acordarse de re-correr nada a mano.
      3. Instala Docker Desktop si no esta (instalador oficial, modo
         silencioso) y configura su auto-inicio.
      4. Arranca Docker Desktop y espera a que el motor este realmente
         operativo (no solo que el proceso exista).
      5. Verifica que corra contenedores Linux (no el modo Windows
         containers, poco comun pero posible si alguien lo cambio antes).
      6. Verifica que el Coordinator responda antes de crear el worker
         (falla rapido y claro si la URL esta mal o no hay red).
      7. Crea/actualiza el contenedor del worker (misma imagen y
         variables de entorno que la via manual de la guia).
      8. Registra un Scheduled Task recurrente (AtLogOn, todos los
         usuarios) que en cada inicio de sesion comprueba que Docker este
         listo y el contenedor corriendo, y lo vuelve a levantar si hace
         falta -- watchdog liviano, no reemplaza --restart unless-stopped
         (que sigue siendo la primera linea de defensa), es una red de
         seguridad para el caso en que Docker Desktop tarde en arrancar
         o el ajuste de auto-inicio de Docker se pierda.

    La recuperacion de UNA CORRIDA interrumpida (si la PC se apaga a
    mitad de una simulacion) la maneja el Coordinator, no este script:
    detecta que el worker dejo de mandar heartbeat y reencola esa
    combinacion a otra maquina. Este script solo se asegura de que,
    cuando la PC vuelva a estar disponible, el worker este corriendo y
    pueda pedir trabajo de nuevo -- ver infra/README.md, "Heartbeat y
    recuperacion".

.PARAMETER CoordinatorUrl
    URL del coordinator. Default: el desplegado en produccion.

.PARAMETER WorkerLabel
    Nombre para identificar esta PC en el coordinator (ver
    GET /api/v1/workers). Default: nombre de la maquina.

.PARAMETER WorkerThreads
    Nucleos logicos que el worker le pide a Geant4 por run. Default:
    todos los detectados por Docker.

.EXAMPLE
    .\install-worker.ps1
    .\install-worker.ps1 -WorkerLabel "laptop-dante" -WorkerThreads 4
#>
[CmdletBinding()]
param(
    [string]$CoordinatorUrl = "http://34.134.100.224:8000",
    [string]$WorkerLabel = $env:COMPUTERNAME,
    [int]$WorkerThreads = 0,
    [string]$WorkerImage = "ghcr.io/s7even-silva/iac-project/geant4-worker:latest"
)

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $env:ProgramData "Geant4Worker"
$LogFile = Join-Path $LogDir "install-worker.log"
$ResumeTaskName = "Geant4WorkerInstallResume"
$WatchdogTaskName = "Geant4WorkerWatchdog"
$SelfCopyPath = Join-Path $LogDir "install-worker.ps1"
$InstallScriptUrl = "https://raw.githubusercontent.com/s7even-silva/iac-project/infra/distributed-sweep/infra/deploy/install-worker.ps1"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# $MyInvocation.MyCommand.Path es $null cuando el script corre via
# "irm ... | iex" (sin archivo en disco, el metodo de instalacion de un
# solo comando que se documenta en la guia) -- en ese caso no hay nada
# que copiar con Copy-Item, hay que volver a descargarlo de GitHub para
# poder registrarlo en las Scheduled Tasks (que si necesitan un .ps1 real
# en disco, no pueden apuntar a un bloque de codigo en memoria).
function Save-SelfCopy {
    $invokedPath = $MyInvocation.PSCommandPath
    if ($invokedPath -and (Test-Path $invokedPath)) {
        Copy-Item -Path $invokedPath -Destination $SelfCopyPath -Force
    } else {
        Invoke-WebRequest -Uri $InstallScriptUrl -OutFile $SelfCopyPath -UseBasicParsing
    }
}

function Write-InstallLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

function Test-VirtualizationEnabled {
    # Get-ComputerInfo es lento (~5-10s) pero es la forma soportada de
    # leer HyperVRequirementVirtualizationFirmwareEnabled sin parsear
    # texto de systeminfo.exe, que cambia de idioma segun el Windows.
    Write-InstallLog "Verificando que la virtualizacion este habilitada en firmware (VT-x/AMD-V)..."
    try {
        $info = Get-ComputerInfo -Property "HyperV*"
        if (-not $info.HyperVRequirementVirtualizationFirmwareEnabled) {
            Write-InstallLog "Virtualizacion NO habilitada en el BIOS/UEFI de esta PC." "ERROR"
            Write-InstallLog "Hay que entrar al BIOS y activar Intel VT-x / AMD-V (Virtualization Technology) manualmente -- esto no se puede hacer desde Windows. El nombre exacto de la opcion varia por fabricante." "ERROR"
            return $false
        }
        if (-not $info.HyperVRequirementDataExecutionPreventionAvailable) {
            Write-InstallLog "Data Execution Prevention no disponible -- CPU/firmware demasiado antiguo para WSL2/Docker Desktop." "ERROR"
            return $false
        }
        Write-InstallLog "Virtualizacion OK."
        return $true
    } catch {
        Write-InstallLog "No se pudo verificar virtualizacion via Get-ComputerInfo ($_) -- se continua igual, wsl --install fallara mas claramente si de verdad falta." "WARN"
        return $true
    }
}

function Test-WindowsVersionSupported {
    # WSL2 requiere Windows 10 build 19041+ o Windows 11 (cualquier build).
    $build = [System.Environment]::OSVersion.Version.Build
    Write-InstallLog "Build de Windows detectado: $build"
    if ($build -lt 19041) {
        Write-InstallLog "Windows demasiado antiguo para WSL2 (build $build, se requiere 19041+). Hay que actualizar Windows primero via Windows Update -- este script no puede hacerlo." "ERROR"
        return $false
    }
    return $true
}

function Test-Wsl2Ready {
    try {
        wsl --status 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { return $false }
        return $true
    } catch {
        return $false
    }
}

function Register-ResumeTask {
    # Scheduled Task de un solo uso: se registra a si misma para
    # auto-eliminarse en cuanto corre una vez (Unregister-ScheduledTask
    # al inicio del script, ver mas abajo) -- no deja tareas huerfanas
    # despues del reinicio que de verdad necesitaba.
    #
    # LogonType Interactive + el usuario actual (no SYSTEM/ServiceAccount)
    # a proposito: una tarea corriendo como SYSTEM se ejecuta en una
    # sesion no interactiva y NUNCA puede mostrar ventana en el escritorio
    # del usuario, sin importar -WindowStyle -- para que el voluntario vea
    # el progreso al volver a iniciar sesion (en vez de que la PC parezca
    # no hacer nada), la tarea debe correr como su propio usuario.
    Write-InstallLog ""
    Write-InstallLog "=================================================================="
    Write-InstallLog " Este script va a reiniciar tu PC ahora."
    Write-InstallLog ""
    Write-InstallLog " Por que: Windows necesita reiniciar para terminar de activar WSL2"
    Write-InstallLog " (requisito de Docker Desktop), que se acaba de instalar."
    Write-InstallLog ""
    Write-InstallLog " Que va a pasar: al volver a iniciar sesion, se abrira SOLA una"
    Write-InstallLog " ventana negra (PowerShell) mostrando el resto de la instalacion"
    Write-InstallLog " -- instalar Docker Desktop, activarlo, y conectar el worker."
    Write-InstallLog " Puede tardar varios minutos. No cierres esa ventana hasta que"
    Write-InstallLog " diga '=== Listo. ==='."
    Write-InstallLog "=================================================================="
    Write-InstallLog ""
    Write-InstallLog "Reiniciando en 20 segundos (Ctrl+C para cancelar y reiniciar tu mismo despues -- la tarea ya queda programada)..."
    Save-SelfCopy

    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$SelfCopyPath`" " +
               "-CoordinatorUrl `"$CoordinatorUrl`" -WorkerLabel `"$WorkerLabel`" " +
               "-WorkerThreads $WorkerThreads -WorkerImage `"$WorkerImage`""
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argList
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Unregister-ScheduledTask -TaskName $ResumeTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $ResumeTaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null

    Start-Sleep -Seconds 20
    Restart-Computer -Force
}

function Install-Wsl2 {
    if (Test-Wsl2Ready) {
        Write-InstallLog "WSL2 ya esta instalado y operativo."
        return
    }
    Write-InstallLog "Instalando WSL2 (wsl --install)..."
    wsl --install --no-distribution 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
    Start-Sleep -Seconds 3
    if (Test-Wsl2Ready) {
        Write-InstallLog "WSL2 quedo operativo sin necesitar reinicio."
        return
    }
    # wsl --install pide reinicio la primera vez en la mayoria de las
    # instalaciones -- es el camino esperado, no un fallo.
    Register-ResumeTask
}

function Install-DockerDesktop {
    $dockerExe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Write-InstallLog "Docker Desktop ya esta instalado."
        return
    }
    Write-InstallLog "Descargando el instalador de Docker Desktop..."
    $installerPath = Join-Path $env:TEMP "DockerDesktopInstaller.exe"
    Invoke-WebRequest -Uri "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe" `
        -OutFile $installerPath -UseBasicParsing

    Write-InstallLog "Instalando Docker Desktop (modo silencioso, puede tardar varios minutos)..."
    # --accept-license evita el dialogo interactivo de terminos; el
    # backend queda en WSL2 (default en instalaciones nuevas).
    $proc = Start-Process -FilePath $installerPath -ArgumentList "install", "--quiet", "--accept-license" -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "El instalador de Docker Desktop termino con codigo $($proc.ExitCode)."
    }
    Remove-Item $installerPath -ErrorAction SilentlyContinue
    Write-InstallLog "Docker Desktop instalado."
}

function Set-DockerAutoStart {
    # El toggle "Start Docker Desktop when you sign in" de la UI escribe
    # una entrada de Run para el usuario actual -- se replica aqui
    # directamente para no depender de abrir la UI y hacer clic.
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    $dockerExe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    Write-InstallLog "Configurando el auto-inicio de Docker Desktop al iniciar sesion..."
    Set-ItemProperty -Path $runKey -Name "Docker Desktop" -Value "`"$dockerExe`"" -Force
}

function Start-DockerAndWait {
    param([int]$TimeoutSeconds = 180)

    $dockerExe = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    docker info 2>&1 | Out-Null
    $engineUp = ($LASTEXITCODE -eq 0)

    if (-not $engineUp) {
        Write-InstallLog "Iniciando Docker Desktop..."
        Start-Process -FilePath $dockerExe
    } else {
        Write-InstallLog "Docker Engine ya estaba operativo."
        return
    }

    Write-InstallLog "Esperando a que Docker Engine este operativo (hasta $TimeoutSeconds s)..."
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-InstallLog "Docker Engine operativo."
            return
        }
        Start-Sleep -Seconds 5
        $elapsed += 5
    }
    throw "Docker Engine no quedo operativo tras $TimeoutSeconds segundos. Revisa manualmente Docker Desktop -- puede pedir habilitar WSL2 o Hyper-V la primera vez que abre."
}

function Test-LinuxContainersMode {
    Write-InstallLog "Verificando que Docker corra contenedores Linux (no modo Windows containers)..."
    $osType = docker info --format '{{.OSType}}' 2>&1
    if ($LASTEXITCODE -ne 0 -or $osType -ne "linux") {
        Write-InstallLog "Docker esta en modo '$osType', no 'linux'. La imagen del worker es Linux (Ubuntu+Geant4) y no correra en modo Windows containers." "ERROR"
        Write-InstallLog "En el icono de Docker Desktop (bandeja del sistema), boton derecho -> 'Switch to Linux containers...'" "ERROR"
        return $false
    }
    Write-InstallLog "Modo Linux containers OK."
    return $true
}

function Test-CoordinatorReachable {
    Write-InstallLog "Verificando que el Coordinator responda en $CoordinatorUrl..."
    try {
        $resp = Invoke-RestMethod -Uri "$CoordinatorUrl/api/v1/health" -TimeoutSec 10
        Write-InstallLog "Coordinator OK: $($resp | ConvertTo-Json -Compress)"
        return $true
    } catch {
        Write-InstallLog "No se pudo contactar al Coordinator en $CoordinatorUrl -- revisa tu conexion a internet. ($_)" "ERROR"
        return $false
    }
}

function Install-WorkerContainer {
    Write-InstallLog "Descargando la imagen del worker ($WorkerImage)..."
    docker pull $WorkerImage 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
    if ($LASTEXITCODE -ne 0) { throw "docker pull fallo." }

    $existing = docker ps -a --filter "name=^geant4-worker$" --format "{{.Names}}" 2>&1
    if ($existing -eq "geant4-worker") {
        Write-InstallLog "Ya existe un contenedor 'geant4-worker' -- se elimina para recrearlo con la config actual (no pierde jobs: el Coordinator reencola cualquier corrida que tuviera asignada)."
        docker rm -f geant4-worker *> $null
    }

    $envArgs = @(
        "-e", "COORDINATOR_URL=$CoordinatorUrl",
        "-e", "WORKER_LABEL=$WorkerLabel"
    )
    if ($WorkerThreads -gt 0) {
        $envArgs += @("-e", "WORKER_THREADS=$WorkerThreads")
    }

    Write-InstallLog "Creando el contenedor del worker..."
    docker run -d --name geant4-worker --restart unless-stopped @envArgs $WorkerImage 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
    if ($LASTEXITCODE -ne 0) { throw "docker run fallo." }

    Start-Sleep -Seconds 5
    $status = docker ps --filter "name=^geant4-worker$" --format "{{.Status}}"
    if (-not $status) {
        $logs = docker logs geant4-worker 2>&1
        throw "El contenedor no quedo corriendo. Logs:`n$logs"
    }
    Write-InstallLog "Contenedor corriendo: $status"
}

function Test-WorkerRegistered {
    param([int]$TimeoutSeconds = 60)
    Write-InstallLog "Confirmando que el worker se registro en el Coordinator..."
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $workers = Invoke-RestMethod -Uri "$CoordinatorUrl/api/v1/workers" -TimeoutSec 10
            if ($workers | Where-Object { $_.label -eq $WorkerLabel }) {
                Write-InstallLog "Worker '$WorkerLabel' confirmado en el Coordinator."
                return $true
            }
        } catch {
            # Reintento silencioso durante el polling -- normal mientras
            # el worker recien esta arrancando dentro del contenedor.
            # El fallo final (si nunca se registra) ya se reporta fuera
            # de este loop.
        }
        Start-Sleep -Seconds 5
        $elapsed += 5
    }
    Write-InstallLog "El worker no aparecio en $CoordinatorUrl/api/v1/workers tras $TimeoutSeconds s -- revisa 'docker logs geant4-worker' para ver el error real." "WARN"
    return $false
}

function Register-WatchdogTask {
    # Recurrente (a diferencia de Register-ResumeTask): corre en CADA
    # inicio de sesion, no una sola vez. No reemplaza --restart
    # unless-stopped (esa sigue siendo la primera linea de defensa) --
    # es una red de seguridad para cuando Docker Desktop tarda en
    # arrancar despues del login, o el ajuste de auto-inicio de Docker
    # se pierde por alguna actualizacion.
    Write-InstallLog "Registrando el watchdog que revisa el worker en cada inicio de sesion..."
    Save-SelfCopy

    $watchdogScript = Join-Path $LogDir "watchdog.ps1"
    @"
`$ErrorActionPreference = 'SilentlyContinue'
`$LogFile = '$LogFile'
function Log(`$m) { Add-Content -Path `$LogFile -Value ("[{0}] [WATCHDOG] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), `$m) }

Start-Sleep -Seconds 30  # dar tiempo a que la sesion termine de cargar
docker info *> `$null
if (`$LASTEXITCODE -ne 0) {
    Log "Docker no operativo, iniciando Docker Desktop..."
    Start-Process -FilePath "`$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    `$elapsed = 0
    while (`$elapsed -lt 180) {
        docker info *> `$null
        if (`$LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 5
        `$elapsed += 5
    }
}
`$running = docker ps --filter "name=^geant4-worker`$" --format "{{.Status}}"
if (-not `$running) {
    Log "Contenedor geant4-worker no esta corriendo, intentando 'docker start'..."
    docker start geant4-worker *> `$null
    if (`$LASTEXITCODE -ne 0) {
        Log "docker start fallo (probablemente el contenedor no existe todavia) -- correr install-worker.ps1 de nuevo."
    } else {
        Log "geant4-worker retomado."
    }
} else {
    Log "geant4-worker ya estaba corriendo (`$running)."
}
"@ | Set-Content -Path $watchdogScript -Encoding UTF8

    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdogScript`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $WatchdogTaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    Write-InstallLog "Watchdog registrado (tarea '$WatchdogTaskName', corre en cada inicio de sesion)."
}

# --- Flujo principal ---

$isResume = [bool](Get-ScheduledTask -TaskName $ResumeTaskName -ErrorAction SilentlyContinue)

if ($isResume) {
    Write-InstallLog "=== Reanudando la instalacion despues del reinicio por WSL2 ==="
} else {
    Write-InstallLog "=================================================================="
    Write-InstallLog " Instalador del worker de computo distribuido (ActiveShield_Sim)"
    Write-InstallLog ""
    Write-InstallLog " Esto va a, en tu PC:"
    Write-InstallLog "   - Revisar que tu PC soporte virtualizacion (necesaria para Docker)."
    Write-InstallLog "   - Instalar WSL2 si no lo tienes (puede pedir reiniciar la PC UNA vez;"
    Write-InstallLog "     si pasa, la instalacion continua sola al volver a iniciar sesion)."
    Write-InstallLog "   - Instalar Docker Desktop si no lo tienes."
    Write-InstallLog "   - Descargar la imagen del worker (~5GB, solo la primera vez) y"
    Write-InstallLog "     dejarla corriendo, conectada a $CoordinatorUrl"
    Write-InstallLog ""
    Write-InstallLog " Nada de esto borra ni modifica archivos tuyos -- el worker corre"
    Write-InstallLog " aislado dentro de Docker. Log completo en: $LogFile"
    Write-InstallLog " Para quitar todo despues: infra/deploy/uninstall-worker.ps1"
    Write-InstallLog "=================================================================="
    Write-InstallLog ""
    Write-InstallLog "Coordinator: $CoordinatorUrl | Label: $WorkerLabel"
}

# Si esto es una reanudacion post-reinicio, la tarea de un solo uso ya
# cumplio su proposito -- eliminarla antes de seguir para no dejarla
# corriendo en cada login futuro (a diferencia del watchdog, que si debe
# quedar permanente).
Unregister-ScheduledTask -TaskName $ResumeTaskName -Confirm:$false -ErrorAction SilentlyContinue

if (-not (Test-WindowsVersionSupported)) { exit 1 }
if (-not (Test-VirtualizationEnabled)) { exit 1 }

Install-Wsl2
# Si Install-Wsl2 registro un reinicio, Register-ResumeTask ya llamo a
# Restart-Computer y el script no continua mas alla de este punto.

Install-DockerDesktop
Set-DockerAutoStart
Start-DockerAndWait

if (-not (Test-LinuxContainersMode)) { exit 1 }
if (-not (Test-CoordinatorReachable)) { exit 1 }

Install-WorkerContainer
Test-WorkerRegistered | Out-Null

Register-WatchdogTask

Write-InstallLog "=== Listo. El worker esta corriendo y conectado. ==="
Write-InstallLog "Ver progreso:  docker logs -f geant4-worker"
Write-InstallLog "Ver en la web: $CoordinatorUrl/api/v1/workers"
Write-InstallLog "Log completo de esta instalacion: $LogFile"
Write-InstallLog "Para quitar todo despues: infra/deploy/uninstall-worker.ps1"

if ($isResume) {
    # Esta ventana la abrio la Scheduled Task de resume sin que nadie la
    # lanzara a mano -- sin esto se cerraria sola en cuanto termina el
    # script, y el voluntario nunca alcanzaria a leer si funciono o no.
    Write-Host ""
    Read-Host "Presiona Enter para cerrar esta ventana"
}
