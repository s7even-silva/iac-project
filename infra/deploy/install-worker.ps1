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

.PARAMETER WorkerToken
    Token compartido del Coordinator (X-Worker-Token), si esta
    configurado con WORKER_TOKEN -- pidelo a quien administre el
    Coordinator. Vacio por defecto (sin token, coordinator sin
    autenticacion todavia).

.PARAMETER Cpus
    Limite duro de nucleos para el contenedor (docker run --cpus). Sin
    limite por defecto -- usa todo lo que Docker tenga disponible. Pasa
    un numero (puede ser fraccionario, ej. 2.5) si prefieres dejar
    margen para seguir usando tu PC mientras corre una simulacion.

.PARAMETER MemoryLimit
    Limite duro de RAM para el contenedor (docker run --memory), ej.
    "4g". Sin limite por defecto.

.EXAMPLE
    .\install-worker.ps1
    .\install-worker.ps1 -WorkerLabel "laptop-dante" -WorkerThreads 4
    .\install-worker.ps1 -Cpus 2 -MemoryLimit 4g
#>
[CmdletBinding()]
param(
    [string]$CoordinatorUrl = "http://34.134.100.224:8000",
    [string]$WorkerLabel = $env:COMPUTERNAME,
    [int]$WorkerThreads = 0,
    [string]$WorkerToken = "",
    [string]$Cpus = "",
    [string]$MemoryLimit = "",
    [string]$WorkerImage = "ghcr.io/s7even-silva/iac-project/geant4-worker:latest"
)

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $env:ProgramData "Geant4Worker"
$LogFile = Join-Path $LogDir "install-worker.log"
$ResumeTaskName = "Geant4WorkerInstallResume"
$WatchdogTaskName = "Geant4WorkerWatchdog"
$SelfCopyPath = Join-Path $LogDir "install-worker.ps1"
# Fijado a un commit concreto (no a la rama, que es mutable) -- asi el
# codigo que corre despues de un reinicio es exactamente el mismo que
# arranco la instalacion, no una version distinta si alguien pusheo
# cambios entre medio. Actualizar este hash cuando el script cambie de
# verdad y se quiera que los voluntarios reciban la version nueva.
$InstallScriptCommit = "5abd0fc"
$InstallScriptUrl = "https://raw.githubusercontent.com/s7even-silva/iac-project/$InstallScriptCommit/infra/deploy/install-worker.ps1"
$MaxResumeAttempts = 3

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
    # Requisitos ACTUALES de Docker Desktop (no solo el minimo historico
    # de WSL2, que es mas laxo): Windows 10 22H2 build 19045+, o Windows
    # 11 23H2 build 22631+. Una PC puede tener WSL2 "compatible" segun el
    # build viejo y aun asi Docker Desktop rechazarla o fallar al abrir.
    $build = [System.Environment]::OSVersion.Version.Build
    $isWin11 = $build -ge 22000
    Write-InstallLog "Build de Windows detectado: $build ($(if ($isWin11) { 'Windows 11' } else { 'Windows 10' }))"
    if ($isWin11) {
        if ($build -lt 22631) {
            Write-InstallLog "Windows 11 build $build es mas viejo que 23H2 (22631) -- Docker Desktop actual puede no ser compatible. Actualiza Windows primero via Windows Update." "ERROR"
            return $false
        }
    } else {
        if ($build -lt 19045) {
            Write-InstallLog "Windows 10 build $build es mas viejo que 22H2 (19045) -- Docker Desktop actual puede no ser compatible. Actualiza Windows primero via Windows Update." "ERROR"
            return $false
        }
    }
    return $true
}

function Test-Wsl2Ready {
    # Docker recomienda mantener WSL2 actualizado (>=2.1.5) -- una
    # version vieja es causa conocida de problemas de arranque de Docker
    # Desktop, aunque wsl --status ya reporte "listo". Se comprueba y
    # actualiza aqui mismo, en vez de solo instalar si falta del todo.
    try {
        wsl --status 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { return $false }
    } catch {
        return $false
    }

    try {
        $versionOutput = wsl --version 2>&1
        $versionLine = $versionOutput | Where-Object { $_ -match "WSL version:\s*([\d.]+)" }
        if ($versionLine -and $Matches[1]) {
            $current = [version]$Matches[1]
            $minimum = [version]"2.1.5"
            if ($current -lt $minimum) {
                Write-InstallLog "WSL $current esta desactualizado (Docker recomienda >= $minimum) -- actualizando con 'wsl --update'..."
                wsl --update 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
            }
        } else {
            Write-InstallLog "No se pudo leer la version de WSL desde 'wsl --version' -- se continua igual." "WARN"
        }
    } catch {
        Write-InstallLog "No se pudo verificar/actualizar la version de WSL ($_) -- se continua igual." "WARN"
    }
    return $true
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
    Write-InstallLog " Windows necesita reiniciar para terminar de activar WSL2"
    Write-InstallLog " (requisito de Docker Desktop), que se acaba de instalar."
    Write-InstallLog ""
    Write-InstallLog " Al volver a iniciar sesion, se abrira SOLA una ventana negra"
    Write-InstallLog " (PowerShell) mostrando el resto de la instalacion -- instalar"
    Write-InstallLog " Docker Desktop, activarlo, y conectar el worker. Puede tardar"
    Write-InstallLog " varios minutos. No la cierres hasta que diga '=== Listo. ==='."
    Write-InstallLog ""
    Write-InstallLog " IMPORTANTE: guarda tu trabajo abierto (documentos, navegador,"
    Write-InstallLog " etc.) antes de continuar -- el reinicio los cierra."
    Write-InstallLog "=================================================================="
    Write-InstallLog ""
    $answer = Read-Host "Escribe 'si' para reiniciar ahora, o cualquier otra cosa para cancelar (la tarea queda programada, reinicia tu mismo cuando quieras)"
    Save-SelfCopy

    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$SelfCopyPath`" " +
               "-CoordinatorUrl `"$CoordinatorUrl`" -WorkerLabel `"$WorkerLabel`" " +
               "-WorkerThreads $WorkerThreads -WorkerToken `"$WorkerToken`" " +
               "-Cpus `"$Cpus`" -MemoryLimit `"$MemoryLimit`" -WorkerImage `"$WorkerImage`""
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argList
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Unregister-ScheduledTask -TaskName $ResumeTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $ResumeTaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null

    if ($answer -eq "si") {
        Write-InstallLog "Reiniciando..."
        Restart-Computer
    } else {
        Write-InstallLog "Reinicio pospuesto -- la tarea ya quedo programada, reinicia tu mismo cuando quieras y la instalacion continua sola."
    }
}

function Install-Wsl2 {
    if (Test-Wsl2Ready) {
        Write-InstallLog "WSL2 ya esta instalado y operativo."
        return
    }

    # Limite de reintentos: sin esto, un fallo real (sin red, Windows
    # Update bloqueado, permisos) se confundiria siempre con "pide
    # reinicio" y reiniciaria la PC indefinidamente en cada login.
    $attemptFile = Join-Path $LogDir "wsl-install-attempts.txt"
    $attempts = 0
    if (Test-Path $attemptFile) { $attempts = [int](Get-Content $attemptFile -ErrorAction SilentlyContinue) }
    if ($attempts -ge $MaxResumeAttempts) {
        throw "WSL2 no quedo operativo tras $MaxResumeAttempts intentos. Revisa manualmente ('wsl --install' en una consola de administrador) -- puede ser un problema de red, Windows Update, o permisos que este script no puede resolver solo."
    }
    Set-Content -Path $attemptFile -Value ($attempts + 1)

    Write-InstallLog "Instalando WSL2 (wsl --install)..."
    wsl --install --no-distribution 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
    $installExitCode = $LASTEXITCODE
    Start-Sleep -Seconds 3

    if (Test-Wsl2Ready) {
        Write-InstallLog "WSL2 quedo operativo sin necesitar reinicio."
        Remove-Item $attemptFile -ErrorAction SilentlyContinue
        return
    }

    # Exit codes de wsl.exe documentados: 0 = ok, 3010 = reinicio
    # requerido (ERROR_SUCCESS_REBOOT_REQUIRED). Cualquier otro codigo
    # distinto de exito es un fallo real, no "falta reiniciar" -- antes
    # esto no se distinguia y cualquier fallo se interpretaba como
    # reinicio pendiente.
    if ($installExitCode -ne 0 -and $installExitCode -ne 3010) {
        throw "wsl --install fallo con codigo $installExitCode (no es el codigo de 'reinicio requerido'). Revisa tu conexion a internet o si Windows Update esta bloqueado por politica, y corre 'wsl --install' manualmente para ver el error completo."
    }

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

    # No confiar solo en HTTPS/DNS para saber que el .exe descargado es
    # legitimo -- verificar que este firmado digitalmente y que la firma
    # sea valida (cadena de confianza intacta) antes de ejecutarlo con
    # privilegios de administrador.
    $signature = Get-AuthenticodeSignature -FilePath $installerPath
    if ($signature.Status -ne "Valid") {
        Remove-Item $installerPath -ErrorAction SilentlyContinue
        throw "El instalador de Docker Desktop descargado no tiene una firma digital valida (status: $($signature.Status)). No se ejecuta por seguridad -- puede ser una descarga corrupta o interceptada. Descargalo manualmente desde https://www.docker.com/products/docker-desktop/ y verifica tu antivirus/red."
    }
    $signerName = $signature.SignerCertificate.Subject
    if ($signerName -notmatch "Docker") {
        Remove-Item $installerPath -ErrorAction SilentlyContinue
        throw "El instalador esta firmado, pero no por Docker (firmante: $signerName). No se ejecuta por seguridad."
    }
    Write-InstallLog "Firma digital verificada (firmante: $signerName)."

    Write-InstallLog "Instalando Docker Desktop (modo silencioso, puede tardar varios minutos)..."
    # --accept-license evita el dialogo interactivo de terminos; el
    # backend queda en WSL2 (default en instalaciones nuevas).
    $proc = Start-Process -FilePath $installerPath -ArgumentList "install", "--quiet", "--accept-license" -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "El instalador de Docker Desktop termino con codigo $($proc.ExitCode)."
    }
    Remove-Item $installerPath -ErrorAction SilentlyContinue
    Write-InstallLog "Docker Desktop instalado."
    Sync-PathWithDockerCli
}

function Sync-PathWithDockerCli {
    # El instalador de Docker Desktop agrega su carpeta de binarios al
    # PATH de MAQUINA, pero un PowerShell ya abierto ANTES de esa
    # instalacion no recarga esa variable solo -- 'docker' pareceria
    # "no encontrado" aunque la instalacion haya sido exitosa. Refrescar
    # el PATH de este proceso desde el registro, sin depender de que el
    # usuario abra una consola nueva.
    $cliDir = "$env:ProgramFiles\Docker\Docker\resources\bin"
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
    if ((Test-Path $cliDir) -and ($env:Path -notlike "*$cliDir*")) {
        $env:Path = "$env:Path;$cliDir"
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-InstallLog "El comando 'docker' no aparece en el PATH todavia tras instalar -- puede necesitar cerrar y reabrir esta ventana manualmente si el resto del script falla por esto." "WARN"
    }
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

function Invoke-DockerPullWithRetry {
    param([int]$MaxAttempts = 3)
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Write-InstallLog "Descargando la imagen del worker ($WorkerImage), intento $attempt de $MaxAttempts..."
        $output = docker pull $WorkerImage 2>&1
        $output | ForEach-Object { Write-InstallLog "  $_" }
        if ($LASTEXITCODE -eq 0) { return }

        $outputText = $output -join "`n"
        # "failed to fetch oauth token" / timeout / "net/http" son fallos
        # de red transitorios (ej. contra ghcr.io/token) -- vale la pena
        # reintentar. "unauthorized"/"denied" es un problema real de
        # permisos del paquete, no de red -- reintentar no lo arregla.
        $isAuthError = $outputText -match "unauthorized|denied:"
        if ($isAuthError) {
            throw "docker pull fallo por permisos (no es un problema de red): $outputText`nEsto pasa si la imagen del worker esta marcada como privada en GHCR -- avisa a quien administra el proyecto, no es algo que puedas arreglar desde tu PC."
        }
        if ($attempt -eq $MaxAttempts) {
            throw "docker pull fallo tras $MaxAttempts intentos, parece un problema de red/conexion:`n$outputText`nRevisa tu conexion a internet (o si un firewall/antivirus bloquea Docker) e intenta de nuevo mas tarde."
        }
        Write-InstallLog "Fallo transitorio, reintentando en 10s..." "WARN"
        Start-Sleep -Seconds 10
    }
}

function Install-WorkerContainer {
    Invoke-DockerPullWithRetry

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
    if ($WorkerToken) {
        $envArgs += @("-e", "WORKER_TOKEN=$WorkerToken")
    }
    $limitArgs = @()
    if ($Cpus) { $limitArgs += @("--cpus", $Cpus) }
    if ($MemoryLimit) { $limitArgs += @("--memory", $MemoryLimit) }

    Write-InstallLog "Creando el contenedor del worker..."
    docker run -d --name geant4-worker --restart unless-stopped @envArgs @limitArgs $WorkerImage 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
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

    # Verificar por worker_id real (persistido dentro del contenedor por
    # worker.py), no solo por label -- un registro VIEJO con el mismo
    # label (de una instalacion anterior, ya muerto) haria que esta
    # comprobacion pareciera exitosa aunque el worker nuevo nunca se
    # haya conectado de verdad.
    $workerId = $null
    $idElapsed = 0
    while ($idElapsed -lt 30) {
        $workerId = docker exec geant4-worker cat /var/lib/geant4-worker/worker_id 2>$null
        if ($LASTEXITCODE -eq 0 -and $workerId) { break }
        Start-Sleep -Seconds 3
        $idElapsed += 3
    }
    if (-not $workerId) {
        Write-InstallLog "No se pudo leer el worker_id desde dentro del contenedor -- revisa 'docker logs geant4-worker'." "ERROR"
        return $false
    }

    $headers = @{}
    if ($WorkerToken) { $headers["X-Worker-Token"] = $WorkerToken }

    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $workers = Invoke-RestMethod -Uri "$CoordinatorUrl/api/v1/workers" -Headers $headers -TimeoutSec 10
            $match = $workers | Where-Object { $_.worker_id -eq $workerId }
            if ($match -and $match.last_heartbeat) {
                Write-InstallLog "Worker '$WorkerLabel' (id $workerId) confirmado en el Coordinator, con heartbeat reciente."
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
    Write-InstallLog "El worker (id $workerId) no aparecio en $CoordinatorUrl/api/v1/workers tras $TimeoutSeconds s -- revisa 'docker logs geant4-worker' para ver el error real." "ERROR"
    return $false
}

function Register-WatchdogTask {
    # Recurrente (a diferencia de Register-ResumeTask): corre al inicio
    # de sesion Y despues cada 30 minutos mientras la sesion siga activa
    # -- solo AtLogOn dejaba un hueco real (si Docker Desktop se cae
    # horas despues del login, nadie lo nota hasta el proximo inicio de
    # sesion). No reemplaza --restart unless-stopped (esa sigue siendo
    # la primera linea de defensa para el CONTENEDOR) -- esto cubre que
    # el propio Docker Desktop (el motor) siga arriba.
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
    $logonTrigger = New-ScheduledTaskTrigger -AtLogOn
    # Repeticion cada 30 min durante 10 anios (limite arbitrario alto,
    # equivalente a "indefinidamente") -- cubre el caso de Docker
    # cayendose horas despues del login, no solo al iniciar sesion.
    $recurringTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Unregister-ScheduledTask -TaskName $WatchdogTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $WatchdogTaskName -Action $action -Trigger @($logonTrigger, $recurringTrigger) `
        -Principal $principal -Settings $settings -Force | Out-Null
    Write-InstallLog "Watchdog registrado (tarea '$WatchdogTaskName', corre al iniciar sesion y cada 30 min mientras siga activa)."
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
    Write-InstallLog " Esto SI instala/configura software en tu PC (WSL2, Docker Desktop,"
    Write-InstallLog " tareas programadas) -- pero no accede ni modifica tus documentos"
    Write-InstallLog " personales: el worker corre aislado dentro de un contenedor Docker,"
    Write-InstallLog " sin ver el resto de tu sistema de archivos. Log completo en: $LogFile"
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
if (-not (Test-WorkerRegistered)) {
    throw "El worker se creo pero no se confirmo conectado al Coordinator -- no se reporta exito. Revisa 'docker logs geant4-worker' y vuelve a correr este script."
}

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
