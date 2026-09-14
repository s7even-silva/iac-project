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

      1. Verifica arquitectura (x86-64), version de Windows, RAM total, y
         que la CPU soporte virtualizacion y este habilitada en firmware
         (VT-x/AMD-V) -- sin esto ni WSL2 ni Docker pueden funcionar, y el
         error que dan por separado no es claro.
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

.PARAMETER Action
    Install (default) instala/actualiza; Uninstall retira worker y tareas,
    conservando el volumen. Admite -WhatIf y solicita confirmacion al retirar.
.PARAMETER RemoveWorkerData
    Con Uninstall: borra el volumen del worker y resultados pendientes.
.PARAMETER RemoveDocker
    Con Uninstall y RemoveWorkerData: desinstala Docker Desktop y TODOS sus datos.
.PARAMETER RemoveWSL
    Con Uninstall: retira WSL del usuario y desactiva sus caracteristicas Windows.
    No borra distribuciones ni reinicia automaticamente.
.PARAMETER RemoveDockerAutostart
    Con Uninstall: quita el autoinicio Docker del usuario actual.

.PARAMETER CoordinatorUrl
    URL del coordinator. Default: el desplegado en produccion.

.PARAMETER WorkerLabel
    Nombre para identificar esta PC en el coordinator (ver
    GET /api/v1/workers). Si no se especifica: si ya existe un worker
    corriendo en esta PC (instalado con este script o con el docker run
    manual de GUIA_VOLUNTARIOS.md), se reusa su label actual sin
    preguntar nada. Si no existe ninguno, se pregunta de forma
    interactiva -- dejar vacio usa $env:USERNAME (tu usuario de Windows,
    mas legible que el nombre de maquina que se usaba antes por
    defecto).

.PARAMETER WorkerThreads
    Nucleos logicos que el worker le pide a Geant4 por run. Default (sin
    pasar este parametro): todos los nucleos que Docker le asigna al
    contenedor, detectados por el propio worker desde adentro
    (os.cpu_count() en worker.py) -- no un numero fijado por este script.

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
    # Primera instalacion en esta PC -- pregunta el nombre a usar.
    .\install-worker.ps1
    .\install-worker.ps1 -WorkerLabel "laptop-dante" -WorkerThreads 4
    .\install-worker.ps1 -Cpus 2 -MemoryLimit 4g

    # Actualizar un worker que YA existe (instalado con este script o
    # con el docker run manual de GUIA_VOLUNTARIOS.md): mismo comando,
    # sin parametros -- detecta el contenedor existente, reusa su label
    # actual sin preguntar, salta las verificaciones de WSL2/Docker
    # Desktop (ya funcionan), y solo descarga la imagen nueva si cambio.
    .\install-worker.ps1
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = "High")]
param(
    [ValidateSet("Install", "Uninstall")]
    [string]$Action = "Install",
    [switch]$RemoveDockerAutostart,
    [switch]$RemoveWorkerData,
    [switch]$RemoveDocker,
    [switch]$RemoveWSL,
    [string]$CoordinatorUrl = "https://coordinator.vlaboratory.org",
    [string]$WorkerLabel,
    [int]$WorkerThreads = 0,
    [ValidateSet("0", "1")]
    [string]$WorkerAutoUpdate = "1",
    [string]$WorkerToken = "",
    [string]$Cpus = "",
    [string]$MemoryLimit = "",
    # Digest fijo, no :latest -- reproducibilidad cientifica: se puede
    # saber exactamente que version del worker produjo cada resultado.
    # Actualizar este hash cuando se publique una imagen nueva de
    # verdad (docker buildx imagetools inspect ... para obtenerlo).
    [string]$WorkerImage = "ghcr.io/s7even-silva/iac-project/geant4-worker@sha256:78cce5255237fe3296bcd985fc04c8675ed98d46d07dd20cef7f0ea70f1ac461"
)

$ErrorActionPreference = "Stop"
$SourceScriptPath = $PSCommandPath
if ($Action -eq "Install" -and ($RemoveDockerAutostart -or $RemoveWorkerData -or $RemoveDocker -or $RemoveWSL -or $WhatIfPreference)) {
    throw "Las opciones de retirada y -WhatIf requieren -Action Uninstall."
}
$LogDir = Join-Path $env:ProgramData "Geant4Worker"
$LogFile = Join-Path $LogDir "install-worker.log"
$ResumeTaskName = "Geant4WorkerInstallResume"
$WatchdogTaskName = "Geant4WorkerWatchdog"
$SelfCopyPath = Join-Path $LogDir "install-worker.ps1"
$PauseScriptPath = Join-Path $LogDir "pause-worker.ps1"
$ResumeScriptPath = Join-Path $LogDir "resume-worker.ps1"
# El voluntario debe poder pausar/reanudar SIN elevacion (pause-
# worker.ps1/resume-worker.ps1 corren como su usuario normal, no como
# administrador) -- C:\ProgramData es escribible por administradores por
# defecto, pero no hay garantia de que un usuario estandar tenga permiso
# de escritura ahi (depende de las ACL resultantes de esa maquina en
# particular). El estado de pausa en si vive en el perfil del propio
# usuario (%LOCALAPPDATA%, siempre escribible sin elevacion) en vez de
# en $LogDir -- separado del resto (logs, self-copy, Scheduled Tasks),
# que si necesitan privilegios de administrador y se quedan en ProgramData.
$UserStateDir = Join-Path $env:LOCALAPPDATA "Geant4Worker"
$PauseFile = Join-Path $UserStateDir "worker.paused"
# Fijado a un commit concreto (no a la rama, que es mutable) -- asi el
# codigo que corre despues de un reinicio es exactamente el mismo que
# arranco la instalacion, no una version distinta si alguien pusheo
# cambios entre medio. Actualizar este hash cuando el script cambie de
# verdad y se quiera que los voluntarios reciban la version nueva.
$InstallScriptCommit = "38e5ee60bdbf26c89c01b96adf712f04ffae066e"
$InstallScriptUrl = "https://raw.githubusercontent.com/s7even-silva/iac-project/$InstallScriptCommit/infra/deploy/install-worker.ps1"
$MaxResumeAttempts = 3

if ($Action -eq "Install") { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
# $env:LOCALAPPDATA bajo una sesion elevada (RunLevel Highest, no un
# token de SYSTEM distinto -- ver Register-ResumeTask/Register-
# WatchdogTask, ambas usan -UserId $env:USERNAME) sigue resolviendo al
# perfil del usuario actual, asi que esto crea la carpeta en el lugar
# correcto sin tener que calcular la ruta del perfil aparte.
if ($Action -eq "Install") { New-Item -ItemType Directory -Force -Path $UserStateDir | Out-Null }

# $MyInvocation.MyCommand.Path es $null cuando el script corre via
# "irm ... | iex" (sin archivo en disco, el metodo de instalacion de un
# solo comando que se documenta en la guia) -- en ese caso no hay nada
# que copiar con Copy-Item, hay que volver a descargarlo de GitHub para
# poder registrarlo en las Scheduled Tasks (que si necesitan un .ps1 real
# en disco, no pueden apuntar a un bloque de codigo en memoria).
function Save-SelfCopy {
    $invokedPath = $SourceScriptPath
    if ($invokedPath -and (Test-Path $invokedPath)) {
        if ([IO.Path]::GetFullPath($invokedPath) -ne [IO.Path]::GetFullPath($SelfCopyPath)) {
            Copy-Item -Path $invokedPath -Destination $SelfCopyPath -Force
        }
    } else {
        Invoke-WebRequest -Uri $InstallScriptUrl -OutFile $SelfCopyPath -UseBasicParsing
    }
    Save-PauseResumeScripts
}

function Save-PauseResumeScripts {
    # C:\ProgramData\Geant4Worker (=$LogDir) es escribible sin elevacion
    # adicional una vez que este instalador (que si corre elevado) creo
    # el directorio -- se dejan pause-worker.ps1/resume-worker.ps1 ahi
    # mismo para que el voluntario tenga un control real y accesible
    # sobre su propio worker, sin depender de que recuerde donde esta
    # worker.paused ni de volver a descargar nada de GitHub. Se traen
    # del mismo commit fijo que el resto de este instalador (ver
    # $InstallScriptCommit), no de la rama mutable.
    $baseUrl = "https://raw.githubusercontent.com/s7even-silva/iac-project/$InstallScriptCommit/infra/deploy"
    try {
        foreach ($name in @('pause-worker.ps1', 'resume-worker.ps1')) {
            $destination = Join-Path $LogDir $name
            $source = if ($SourceScriptPath) { Join-Path (Split-Path $SourceScriptPath) $name } else { $null }
            if ($source -and (Test-Path $source)) {
                if ([IO.Path]::GetFullPath($source) -ne [IO.Path]::GetFullPath($destination)) {
                    Copy-Item $source $destination -Force
                }
            } else {
                Invoke-WebRequest -Uri "$baseUrl/$name" -OutFile $destination -UseBasicParsing
            }
        }
        Write-InstallLog "pause-worker.ps1 / resume-worker.ps1 disponibles en $LogDir"
    } catch {
        Write-InstallLog "No se pudieron descargar pause-worker.ps1/resume-worker.ps1 ($_) -- se puede pausar/reanudar igual descargandolos a mano del repo (infra/deploy/)." "WARN"
    }
}

function Write-InstallLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    if (Test-Path $LogDir) { Add-Content -Path $LogFile -Value $line }
}

function Test-VirtualizationEnabled {
    # Get-ComputerInfo es lento (~5-10s) pero es la forma soportada de
    # leer HyperVRequirementVirtualizationFirmwareEnabled sin parsear
    # texto de systeminfo.exe, que cambia de idioma segun el Windows.
    Write-InstallLog "Verificando que la virtualizacion este habilitada en firmware (VT-x/AMD-V)..."
    try {
        $info = Get-ComputerInfo -Property "HyperV*"
        if ($info.HyperVisorPresent) { return $true }
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

function Test-ArchitectureSupported {
    # El instalador de Docker Desktop que se descarga mas abajo es
    # especificamente el build amd64 (ver Install-DockerDesktop, URL con
    # /win/main/amd64/) y la imagen del worker (geant4-worker) tambien se
    # publica solo para linux/amd64 -- ninguno de los dos corre en Windows
    # ARM64 (ej. Surface Pro X, laptops Snapdragon). Detectar esto ANTES de
    # descargar nada, con un mensaje claro, en vez de que el instalador de
    # Docker falle a medias con un error generico de arquitectura.
    $arch = $env:PROCESSOR_ARCHITECTURE
    Write-InstallLog "Arquitectura detectada: $arch"
    if ($arch -ne "AMD64") {
        Write-InstallLog "Esta PC es $arch, no AMD64/x86-64 -- el instalador de Docker Desktop y la imagen del worker que usa este script son solo para x86-64. No hay una via automatica para ARM64 todavia." "ERROR"
        return $false
    }
    return $true
}

function Test-EnoughRam {
    # Geant4 + el propio Docker Desktop (WSL2 de por medio) piden RAM real,
    # no solo disco -- una PC con muy poca RAM total podria "instalar bien"
    # y fallar recien horas despues, a mitad de una simulacion, con un
    # sintoma dificil de diagnosticar para un voluntario (el proceso se cae
    # o la PC se vuelve inusable). Verificar el total instalado ahora,
    # con un mensaje explicito, en vez de descubrirlo asi.
    param([double]$RequiredGb = 4.0)
    try {
        $totalGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    } catch {
        Write-InstallLog "No se pudo verificar la RAM total de esta PC ($_) -- se continua igual." "WARN"
        return $true
    }
    if ($totalGb -lt $RequiredGb) {
        Write-InstallLog "Esta PC tiene $totalGb GB de RAM (se recomiendan al menos $RequiredGb GB para correr Geant4 dentro de Docker/WSL2 sin quedarse sin memoria a mitad de una simulacion)." "ERROR"
        return $false
    }
    Write-InstallLog "RAM total OK ($totalGb GB)."
    return $true
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

    # 'wsl --update' es idempotente (no hace nada si ya esta al dia) y
    # se corre siempre, SIN parsear la salida de 'wsl --version' -- esa
    # salida es texto localizado (ej. "WSL version:" no aparece igual en
    # un Windows en espanol), asi que buscar esa cadena literal fallaba
    # silenciosamente sin avisar en cualquier idioma distinto al que se
    # probo. El exit code SI se revisa ahora (antes se ignoraba).
    try {
        Write-InstallLog "Verificando actualizaciones de WSL ('wsl --update')..."
        wsl --update 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
        if ($LASTEXITCODE -ne 0) {
            Write-InstallLog "'wsl --update' termino con codigo $LASTEXITCODE -- se continua igual, pero si Docker Desktop falla al abrir mas adelante, correr ese comando a mano (en una consola de administrador) puede ser la causa." "WARN"
        }
    } catch {
        Write-InstallLog "No se pudo correr 'wsl --update' ($_) -- se continua igual." "WARN"
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

    # RIESGO CONOCIDO, sin resolver a proposito: WorkerToken (si se usa)
    # queda visible en los argumentos de esta Scheduled Task -- cualquiera
    # con acceso a 'schtasks /query /tv' o al Task Scheduler en esta PC
    # puede leerlo en texto plano. Aceptable mientras WORKER_TOKEN no
    # este activado en produccion (ver AGENTS.md, "Computo distribuido");
    # si se activa, cifrar esto (DPAPI/Credential Manager) antes de
    # depender de el como control de acceso real, no solo un secreto
    # compartido entre companeros de confianza.
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$SelfCopyPath`" " +
               "-CoordinatorUrl `"$CoordinatorUrl`" -WorkerLabel `"$WorkerLabel`" " +
               "-WorkerAutoUpdate $WorkerAutoUpdate -WorkerThreads $WorkerThreads -WorkerToken `"$WorkerToken`" " +
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

    # Critico: el script NO debe seguir a Install-DockerDesktop/etc. en
    # este proceso -- WSL2 todavia no esta operativo (por eso se llego
    # aqui) sin importar si el reinicio fue ahora o se pospuso. Bug real
    # encontrado en revision: antes esta funcion simplemente retornaba y
    # el flujo principal continuaba de inmediato sobre un sistema a
    # medio configurar.
    exit 0
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

    # Se llama siempre aqui, no solo dentro de Install-DockerDesktop
    # (tras una instalacion nueva) -- si Docker Desktop ya existia desde
    # antes (el caso normal de companeros que ya tenian todo), este
    # proceso de PowerShell puede seguir sin 'docker' en su PATH igual,
    # por ejemplo si se abrio antes de que Docker se instalara en esa PC.
    # Es barata y segura de llamar de mas.
    Sync-PathWithDockerCli

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

function Test-EnoughDiskSpace {
    # La imagen pesa ~5GB comprimida, algo mas descomprimida en el
    # storage de Docker -- verificar ANTES de gastar minutos descargando
    # para fallar recien casi al final si el disco no alcanza.
    param([double]$RequiredGb = 10.0)
    $systemDrive = $env:SystemDrive
    $drive = Get-PSDrive -Name $systemDrive.TrimEnd(':') -ErrorAction SilentlyContinue
    if (-not $drive) {
        Write-InstallLog "No se pudo verificar espacio libre en disco -- se continua igual." "WARN"
        return $true
    }
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    if ($freeGb -lt $RequiredGb) {
        Write-InstallLog "Solo hay $freeGb GB libres en $systemDrive (se recomiendan al menos $RequiredGb GB para la imagen del worker, ~5GB, mas margen de Docker)." "ERROR"
        return $false
    }
    Write-InstallLog "Espacio en disco OK ($freeGb GB libres en $systemDrive)."
    return $true
}

function Invoke-DockerPullWithRetry {
    param([int]$MaxAttempts = 3)
    if (-not (Test-EnoughDiskSpace)) {
        throw "Espacio en disco insuficiente para descargar la imagen del worker. Libera espacio e intenta de nuevo."
    }
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

function Get-ExistingWorkerEnvValue {
    # Lee una variable de entorno real (WORKER_LABEL, WORKER_THREADS,
    # etc.) del contenedor 'geant4-worker' YA EXISTENTE, sin importar si
    # lo creo este script o el docker run manual de
    # GUIA_VOLUNTARIOS.md -- necesario para el modo "actualizar" (ver
    # Resolve-WorkerLabel y el flujo principal): un voluntario que ya
    # tiene un worker corriendo con Docker manual nunca corrio este
    # script, asi que no hay ningun rastro de su config en
    # C:\ProgramData\Geant4Worker -- la unica fuente de verdad es leer
    # el contenedor mismo. $null si el contenedor no existe o esa
    # variable no esta definida en el.
    param([string]$VarName)
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { return $null }
    $envList = docker inspect geant4-worker --format '{{json .Config.Env}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $envList) { return $null }
    try {
        $vars = $envList | ConvertFrom-Json
    } catch {
        return $null
    }
    $prefix = "$VarName="
    $match = $vars | Where-Object { $_ -like "$prefix*" } | Select-Object -First 1
    if (-not $match) { return $null }
    return $match.Substring($prefix.Length)
}

function Resolve-WorkerLabel {
    # -WasSpecified viene de $PSBoundParameters.ContainsKey('WorkerLabel')
    # DEL SCRIPT TOP-LEVEL (ver flujo principal) -- pasado explicito en
    # vez de leido aqui adentro porque $PSBoundParameters dentro de esta
    # funcion se referiria a los parametros de ESTA funcion (que no
    # tiene ninguno declarado con ese nombre), no a los del script que
    # la llama. Bug real encontrado probando esta funcion de forma
    # aislada: sin este parametro explicito, -WorkerLabel nunca ganaba,
    # ni siquiera pasandolo.
    param([Parameter(Mandatory)][bool]$WasSpecified, [string]$CurrentValue)
    if ($WasSpecified) {
        return $CurrentValue
    }
    # Ya existe un worker corriendo en esta PC (Docker manual o una
    # instalacion anterior de este script) -- reusar su label real tal
    # cual, sin preguntar. Bug real de UX que esto corrige: antes,
    # cualquiera que quisiera un label distinto del nombre de maquina
    # tenia que usar la sintaxis de [scriptblock]::Create(...) (dificil
    # de escribir bien, ver GUIA_VOLUNTARIOS.md) -- ahora, si ya eligieron
    # un label la primera vez (a mano, con docker run), simplemente se
    # conserva solo.
    $existingLabel = Get-ExistingWorkerEnvValue -VarName "WORKER_LABEL"
    if ($existingLabel) {
        Write-InstallLog "Worker existente encontrado con label '$existingLabel' -- se conserva (usa -WorkerLabel para cambiarlo)."
        return $existingLabel
    }
    # Primera instalacion en esta PC, sin label explicito -- preguntar en
    # vez de usar el nombre de maquina en silencio (poco legible, ej.
    # 'DESKTOP-A1B2C3'); dejar vacio usa el nombre de usuario de Windows,
    # normalmente mas reconocible para el resto del equipo.
    $answer = Read-Host "Nombre para identificarte en el Coordinator (Enter para usar '$env:USERNAME')"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $env:USERNAME }
    return $answer
}

function Get-DesiredWorkerConfigHash {
    # Huella de todo lo que --docker run recibiria, para comparar contra
    # un contenedor ya existente sin tener que enumerar campo por campo
    # en dos lugares distintos.
    $parts = @($WorkerImage, $CoordinatorUrl, $WorkerLabel, $WorkerThreads, $WorkerToken, $Cpus, $MemoryLimit, $WorkerAutoUpdate) -join "|"
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($parts)
    return [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes))
}

function Test-WorkerVolumeMounted {
    # Un worker creado por una version anterior de este script (antes de
    # que existiera el volumen nombrado geant4-worker-data) puede tener
    # el mismo config-hash deseado sin tener el volumen -- Get-
    # DesiredWorkerConfigHash nunca incluyo el volumen como parte del
    # hash, asi que ese caso pasaria la comparacion de hash como si no
    # hiciera falta ningun cambio, y el worker_id de ese voluntario se
    # seguiria perdiendo en cada recreacion futura. Se comprueba aparte,
    # explicitamente.
    param([string]$ContainerName = "geant4-worker")
    $mounts = docker inspect $ContainerName --format '{{json .Mounts}}' 2>$null
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron inspeccionar los montajes." }
    return [bool](($mounts | ConvertFrom-Json) | Where-Object {
        $_.Name -eq "geant4-worker-data" -and $_.Destination -eq "/var/lib/geant4-worker"
    })
}

function Test-DockerSockMounted {
    # Mismo patron que Test-WorkerVolumeMounted -- un worker creado antes
    # de que este instalador montara el socket de Docker (ver
    # auto_update() en worker.py) puede tener el mismo config-hash
    # deseado sin tener el socket, asi que la comparacion de hash sola no
    # basta para detectar que hace falta recrear el contenedor para
    # habilitar la auto-actualizacion.
    param([string]$ContainerName = "geant4-worker")
    $mounts = docker inspect $ContainerName --format '{{json .Mounts}}' 2>$null
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron inspeccionar los montajes." }
    return [bool](($mounts | ConvertFrom-Json) | Where-Object {
        $_.Source -eq "/var/run/docker.sock" -and $_.Destination -eq "/var/run/docker.sock"
    })
}

function Save-LegacyWorkerData {
    # Detener antes de copiar para no capturar un outbox a medio escribir.
    docker stop geant4-worker | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo detener el worker; se conserva el contenedor." }
    $backup = Join-Path $LogDir ("legacy-data-" + [guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    docker cp 'geant4-worker:/var/lib/geant4-worker/.' $backup
    if ($LASTEXITCODE -ne 0) { throw "No se pudo respaldar el estado completo; NO se elimina el contenedor." }
    Write-InstallLog "Estado completo (incluidos resultados pendientes) respaldado en $backup. Conservar para recuperacion."
    return $backup
}

function Test-WorkerPaused {
    # El watchdog ya respeta este archivo (ver Register-WatchdogTask) --
    # pero si el voluntario pauso el worker a proposito y despues vuelve
    # a correr install-worker.ps1 (ej. para una actualizacion, o solo
    # por probar), el instalador no debia deshacer esa pausa el mismo
    # arrancando o recreando el contenedor. Bug real encontrado en
    # revision: solo el watchdog conocia worker.paused, este script no.
    return Test-Path $PauseFile
}

function Install-WorkerContainer {
    if (Test-WorkerPaused) {
        Write-InstallLog "El worker esta pausado a proposito (existe $PauseFile) -- no se crea ni se arranca el contenedor. Corre '$ResumeScriptPath' primero si quieres reanudarlo." "WARN"
        return
    }

    Invoke-DockerPullWithRetry
    $desiredHash = Get-DesiredWorkerConfigHash

    $existing = docker ps -a --filter "name=^geant4-worker$" --format "{{.Names}}" 2>&1
    $legacyData = $null
    if ($existing -eq "geant4-worker") {
        # No matar un worker que puede llevar horas de simulacion solo
        # por volver a correr el instalador -- comparar la config
        # deseada contra la etiqueta que dejamos en el contenedor
        # anterior, y si coincide Y el volumen persistente ya esta
        # montado, no tocarlo. Bug real de la primera version: recreaba
        # el contenedor incondicionalmente en cada ejecucion. Bug real
        # de la segunda version (encontrado en revision externa): solo
        # comparaba el hash, asi que un worker de una version anterior a
        # la del volumen nombrado pasaba esta comprobacion como "ya
        # configurado" sin tener el volumen, y nunca se migraba.
        $existingHash = docker inspect geant4-worker --format '{{index .Config.Labels "geant4-worker-config-hash"}}' 2>$null
        $isRunning = docker ps --filter "name=^geant4-worker$" --format "{{.Names}}" 2>$null
        $hasVolume = Test-WorkerVolumeMounted
        $hasDockerSock = Test-DockerSockMounted
        if ($existingHash -eq $desiredHash -and $isRunning -eq "geant4-worker" -and $hasVolume -and $hasDockerSock) {
            Write-InstallLog "El contenedor 'geant4-worker' ya existe, esta corriendo, tiene el volumen persistente y el socket de Docker montado, y su configuracion no cambio -- no se toca (evita interrumpir una simulacion en curso)."
            return
        }
        if (-not $hasVolume) {
            Write-InstallLog "El contenedor 'geant4-worker' existente no tiene el volumen persistente (instalado por una version anterior de este script) -- se migra." "WARN"
            $legacyData = Save-LegacyWorkerData
        } elseif (-not $hasDockerSock) {
            Write-InstallLog "El contenedor 'geant4-worker' existente no tiene el socket de Docker montado (instalado antes de la auto-actualizacion) -- se recrea para habilitarla. Sin resultados que perder: el socket no contiene datos, solo el volumen (ya presente) los tiene." "WARN"
        } elseif ($isRunning -eq "geant4-worker") {
            Write-InstallLog "La configuracion cambio (imagen/label/threads/token/limites) -- se recrea el contenedor. Si tenia una run asignada, el Coordinator la reencola sola tras el timeout de heartbeat (ver infra/README.md), los resultados ya persistidos se conservan, pero el calculo en curso se reiniciara." "WARN"
        } else {
            Write-InstallLog "Existe un contenedor 'geant4-worker' detenido -- se elimina para recrearlo."
        }
        docker rm -f geant4-worker *> $null
        if ($LASTEXITCODE -ne 0) { throw "No se pudo eliminar el contenedor anterior." }
    }

    $envArgs = @(
        "-e", "COORDINATOR_URL=$CoordinatorUrl",
        "-e", "WORKER_LABEL=$WorkerLabel",
        "-e", "WORKER_AUTO_UPDATE=$WorkerAutoUpdate"
    )
    # Bug real encontrado en produccion (2026-09-13): si no se pasaba
    # -WorkerThreads, esta variable nunca se mandaba al contenedor --
    # worker.py caia a SU propio default hardcodeado (1 solo hilo), sin
    # importar cuantos nucleos tenga la maquina. Confirmado en vivo con
    # una PC de 16 nucleos corriendo al 100% en solo 1. NO se corrige
    # aqui detectando nucleos del lado de Windows ($env:
    # NUMBER_OF_PROCESSORS) -- esos son los del HOST, no
    # necesariamente los que Docker Desktop le asigna al contenedor
    # (depende de su configuracion de recursos, o de -Cpus si el
    # voluntario lo uso). El fix real esta en worker.py: cuando no se
    # pasa WORKER_THREADS, usa os.cpu_count() leido DESDE DENTRO del
    # contenedor -- la unica fuente que ve exactamente los CPUs
    # realmente disponibles ahi. Este bloque solo sigue pasando la
    # variable explicitamente cuando el voluntario SI pidio un limite
    # (-WorkerThreads > 0), para no perder esa opcion de "ceder menos
    # nucleos" que ya ofrece la guia.
    if ($WorkerThreads -gt 0) {
        $envArgs += @("-e", "WORKER_THREADS=$WorkerThreads")
    }
    if ($WorkerToken) {
        $envArgs += @("-e", "WORKER_TOKEN=$WorkerToken")
    }
    $limitArgs = @()
    if ($Cpus) { $limitArgs += @("--cpus", $Cpus) }
    if ($MemoryLimit) { $limitArgs += @("--memory", $MemoryLimit) }

    # Volumen NOMBRADO (no bind mount a una ruta del host) -- sobrevive
    # a docker rm -f del contenedor, asi que worker_id persiste entre
    # recreaciones (ej. al actualizar config/imagen). Bug real: sin
    # esto, cada docker rm -f borraba /var/lib/geant4-worker DENTRO del
    # contenedor y la misma PC volvia a aparecer como worker nuevo en
    # el Coordinator, perdiendo su identidad.
    docker volume create geant4-worker-data *> $null

    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el volumen persistente." }
    if ($legacyData) {
        $helper = "geant4-restore-" + [guid]::NewGuid().ToString('N')
        docker create --name $helper -v geant4-worker-data:/data --entrypoint sh $WorkerImage -c true | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el restaurador; respaldo: $legacyData" }
        try {
            docker cp "$legacyData/." "${helper}:/data"
            if ($LASTEXITCODE -ne 0) { throw "Restauracion fallida; respaldo conservado en $legacyData" }
        } finally { docker rm $helper | Out-Null }
    }

    # Socket de Docker montado DENTRO del contenedor -- permite que
    # worker.py se auto-actualice solo (docker_client.py, auto_update())
    # cuando el equipo publica una imagen nueva (ver
    # set_worker_image.py/AGENTS.md), sin pedirle a cada voluntario que
    # vuelva a correr este instalador a mano. Tradeoff de seguridad
    # aceptado a proposito (decision del usuario, 2026-09-13): el
    # contenedor gana la capacidad de crear/eliminar OTROS contenedores
    # en esta PC (no solo administrar el suyo propio) -- razonable para
    # maquinas de voluntarios de confianza conocidos, no para terceros
    # anonimos. Docker Desktop (WSL2 backend, el default en este
    # proyecto) traduce '/var/run/docker.sock' igual que en Linux nativo,
    # sin necesitar la named pipe de Windows (\\.\pipe\docker_engine)
    # aparte.
    $dockerSockArgs = @("-v", "/var/run/docker.sock:/var/run/docker.sock")

    Write-InstallLog "Creando el contenedor del worker..."
    docker run -d --name geant4-worker --restart unless-stopped `
        --label "geant4-worker-config-hash=$desiredHash" `
        -v geant4-worker-data:/var/lib/geant4-worker `
        @dockerSockArgs `
        @envArgs @limitArgs $WorkerImage 2>&1 | ForEach-Object { Write-InstallLog "  $_" }
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
            # 'online'/'seconds_since_heartbeat' vienen YA calculados por
            # el Coordinator (ver GET /api/v1/workers en app.py), con el
            # reloj del SERVIDOR -- bug real corregido aqui: la version
            # anterior parseaba last_heartbeat y lo comparaba contra
            # (Get-Date) de esta PC Windows, así que un reloj local
            # desfasado (adelantado, atrasado, zona horaria mal puesta)
            # podia hacer que un worker recien conectado pareciera viejo,
            # o uno realmente caido pareciera reciente. En un sistema
            # distribuido, la unica hora que importa para decidir "esta
            # vivo" es la del propio Coordinator.
            if ($match -and $match.online) {
                Write-InstallLog "Worker '$WorkerLabel' (id $workerId) confirmado en el Coordinator, heartbeat de hace $([math]::Round($match.seconds_since_heartbeat, 1))s."
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
`$PauseFile = '$PauseFile'
function Log(`$m) { Add-Content -Path `$LogFile -Value ("[{0}] [WATCHDOG] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), `$m) }

# Bug real corregido aqui: antes el watchdog volvia a arrancar el
# contenedor con 'docker start' sin importar POR QUE estaba detenido --
# un 'docker stop geant4-worker' voluntario (la forma documentada de
# pausar en la guia) quedaba deshecho en <=30 min por este mismo
# watchdog, sin que el usuario lo pidiera. Ahora respeta un archivo de
# pausa explicito: si existe, no toca el contenedor aunque este parado.
if (Test-Path `$PauseFile) {
    Log "Worker pausado a proposito (existe `$PauseFile) -- no se toca."
    exit 0
}

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

function Uninstall-Worker {
    if ($RemoveDocker -and -not $RemoveWorkerData) {
        throw "-RemoveDocker requiere -RemoveWorkerData: Docker elimina TODOS sus contenedores, imagenes y volumenes, incluidos resultados pendientes."
    }
    $installers = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop Installer.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop Installer.exe')
    ) | Where-Object { Test-Path $_ }
    if ($RemoveWSL -and $installers -and -not $RemoveDocker) {
        throw "Retira Docker primero (-RemoveDocker -RemoveWorkerData) antes de desactivar su backend WSL."
    }
    $description = "Eliminar worker, tareas y marca de pausa; conservar volumen y resultados pendientes"
    if ($RemoveWorkerData) { $description += "; BORRAR volumen del worker y sus resultados pendientes" }
    if ($RemoveDocker) { $description += "; DESINSTALAR Docker Desktop y TODOS sus datos, incluso de otros proyectos" }
    if ($RemoveWSL) { $description += "; retirar WSL del usuario y desactivar WSL/VirtualMachinePlatform (afecta otras aplicaciones; reinicio manual)" }
    if ($RemoveDockerAutostart) { $description += "; quitar autoinicio Docker del usuario" }
    if (-not $PSCmdlet.ShouldProcess($env:COMPUTERNAME, $description)) { return }
    # No afirmar exito si Docker existe pero el daemon no responde.
    $hasDocker = [bool](Get-Command docker -ErrorAction SilentlyContinue)
    if ($hasDocker) {
        docker info *> $null
        if ($LASTEXITCODE -ne 0) { throw "Docker no responde. Inicialo y reintenta; no se ha eliminado nada." }
    } elseif ($installers -or $RemoveWorkerData) {
        throw "No se puede verificar/eliminar el worker sin el CLI de Docker. Repara el PATH e inicia Docker."
    }
    foreach ($taskName in @($WatchdogTaskName, $ResumeTaskName)) {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
    }
    if ($hasDocker) {
        $existing = docker ps -a --filter 'name=^geant4-worker$' --format '{{.Names}}'
        if ($LASTEXITCODE -ne 0) { throw "No se pudo consultar el contenedor." }
        if ($existing -eq 'geant4-worker') {
            if (-not $RemoveWorkerData -and -not (Test-WorkerVolumeMounted)) { $null = Save-LegacyWorkerData }
            docker stop geant4-worker | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "No se pudo detener el worker." }
            docker rm geant4-worker | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "No se pudo eliminar el worker." }
        }
        if ($RemoveWorkerData) {
            $volumes = docker volume ls --format '{{.Name}}'
            if ($LASTEXITCODE -ne 0) { throw "No se pudieron consultar volumenes." }
            if ($volumes -contains 'geant4-worker-data') {
                docker volume rm geant4-worker-data | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "No se pudo eliminar el volumen del worker." }
            }
        }
    }
    if (Test-Path $PauseFile) { Remove-Item $PauseFile }
    if ($RemoveDockerAutostart -or $RemoveDocker) {
        $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
        if (Get-ItemProperty -Path $key -Name 'Docker Desktop' -ErrorAction SilentlyContinue) {
            Remove-ItemProperty -Path $key -Name 'Docker Desktop'
        }
    }
    if ($RemoveDocker) {
        foreach ($installer in $installers) {
            $process = Start-Process -FilePath $installer -ArgumentList 'uninstall' -Wait -PassThru
            if ($process.ExitCode -notin @(0, 3010)) { throw "Desinstalador Docker fallo: $($process.ExitCode)" }
        }
    }
    if ($RemoveWSL) {
        Get-AppxPackage -Name MicrosoftCorporationII.WindowsSubsystemForLinux | Remove-AppxPackage
        foreach ($feature in @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')) {
            Disable-WindowsOptionalFeature -Online -FeatureName $feature -NoRestart -Confirm:$false | Out-Null
        }
        Write-Host 'Reinicia Windows manualmente. No se han desregistrado ni borrado distribuciones Linux.'
    }
    Write-Host 'Retirada completada. Los logs y respaldos locales se conservan. Los resultados conservados necesitan un worker activo para reintentarse y pueden vencer en el coordinator.'
}

# --- Flujo principal ---

if ($Action -eq "Uninstall") { Uninstall-Worker; return }

$isResume = [bool](Get-ScheduledTask -TaskName $ResumeTaskName -ErrorAction SilentlyContinue)

# Deteccion automatica actualizar vs. instalar desde cero: si YA existe
# un contenedor 'geant4-worker' (sin importar si lo creo este script o
# el docker run manual de GUIA_VOLUNTARIOS.md -- Test-DockerAvailable
# corre 'docker' directo, funciona igual en ambos casos), Docker/WSL2 ya
# estan funcionando en esta PC por definicion: no tiene sentido repetir
# las verificaciones de arquitectura/Windows/virtualizacion/RAM ni la
# instalacion de WSL2/Docker Desktop, que solo hacen falta la primera
# vez. $isUpdate se decide ANTES de resolver el label (el propio label
# resuelto usa esta misma deteccion, ver Resolve-WorkerLabel) para poder
# mostrar un mensaje inicial distinto y mas corto en el caso de
# actualizacion.
$dockerCmdAvailable = [bool](Get-Command docker -ErrorAction SilentlyContinue)
$isUpdate = $false
if ($dockerCmdAvailable) {
    docker inspect geant4-worker *> $null
    $isUpdate = ($LASTEXITCODE -eq 0)
}

if ($isUpdate) {
    # Una imagen auto-actualizada no debe retroceder al pin de un instalador viejo.
    if (-not $PSBoundParameters.ContainsKey('WorkerImage')) {
        $WorkerImage = docker inspect geant4-worker --format '{{.Config.Image}}'
        if ($LASTEXITCODE -ne 0 -or -not $WorkerImage) { throw "No se pudo conservar la imagen actual." }
    }
    foreach ($entry in @{CoordinatorUrl='COORDINATOR_URL'; WorkerToken='WORKER_TOKEN'; WorkerThreads='WORKER_THREADS'; WorkerAutoUpdate='WORKER_AUTO_UPDATE'}.GetEnumerator()) {
        if (-not $PSBoundParameters.ContainsKey($entry.Key)) {
            $value = Get-ExistingWorkerEnvValue $entry.Value
            if ($null -ne $value) { Set-Variable -Name $entry.Key -Value $value }
        }
    }
    $hostConfig = docker inspect geant4-worker --format '{{json .HostConfig}}'
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron leer los limites actuales." }
    $hostConfig = $hostConfig | ConvertFrom-Json
    if (-not $PSBoundParameters.ContainsKey('Cpus') -and $hostConfig.NanoCpus) {
        $Cpus = ([double]$hostConfig.NanoCpus / 1e9).ToString([Globalization.CultureInfo]::InvariantCulture)
    }
    if (-not $PSBoundParameters.ContainsKey('MemoryLimit') -and $hostConfig.Memory) { $MemoryLimit = [string]$hostConfig.Memory }
}

$WorkerLabel = Resolve-WorkerLabel -WasSpecified $PSBoundParameters.ContainsKey('WorkerLabel') -CurrentValue $WorkerLabel

if ($isResume) {
    Write-InstallLog "=== Reanudando la instalacion despues del reinicio por WSL2 ==="
} elseif ($isUpdate) {
    Write-InstallLog "=================================================================="
    Write-InstallLog " Actualizando el worker de computo distribuido (ActiveShield_Sim)"
    Write-InstallLog ""
    Write-InstallLog " Ya existe un worker en esta PC -- Docker/WSL2 ya estan listos, asi"
    Write-InstallLog " que se salta directo a: descargar la imagen mas reciente (si cambio)"
    Write-InstallLog " y recrear el contenedor con ella, conservando tu label ('$WorkerLabel'),"
    Write-InstallLog " limites de CPU/RAM, y configuracion actuales."
    Write-InstallLog "=================================================================="
    Write-InstallLog ""
    Write-InstallLog "Coordinator: $CoordinatorUrl | Label: $WorkerLabel"
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

if (-not $isUpdate) {
    if (-not (Test-ArchitectureSupported)) { exit 1 }
    if (-not (Test-WindowsVersionSupported)) { exit 1 }
    if (-not (Test-VirtualizationEnabled)) { exit 1 }
    if (-not (Test-EnoughRam)) { exit 1 }

    Install-Wsl2
    # Si Install-Wsl2 registro un reinicio, Register-ResumeTask ya llamo
    # a Restart-Computer y el script no continua mas alla de este punto.

    Install-DockerDesktop
    Set-DockerAutoStart
    Start-DockerAndWait

    if (-not (Test-LinuxContainersMode)) { exit 1 }
} else {
    # Ya sabemos que Docker responde (es como se detecto $isUpdate) --
    # solo falta refrescar el PATH de esta sesion de PowerShell por si
    # se abrio antes de que Docker Desktop terminara de instalarse.
    Sync-PathWithDockerCli
}

if (-not (Test-CoordinatorReachable)) { exit 1 }

Install-WorkerContainer

if (Test-WorkerPaused) {
    # El worker esta pausado a proposito -- Install-WorkerContainer ya
    # no creo/arranco nada (ver arriba), asi que comprobar que este
    # registrado y corriendo ahora mismo no aplica ni tendria sentido.
    Write-InstallLog ""
    Write-InstallLog "=== Listo (worker pausado, sin cambios). ==="
    Write-InstallLog "Para reanudarlo: $ResumeScriptPath"
} else {
    if (-not (Test-WorkerRegistered)) {
        throw "El worker se creo pero no se confirmo conectado al Coordinator -- no se reporta exito. Revisa 'docker logs geant4-worker' y vuelve a correr este script."
    }

    Register-WatchdogTask

    Write-InstallLog "=== Listo. El worker esta corriendo y conectado. ==="
    Write-InstallLog "Ver progreso:  docker logs -f geant4-worker"
    Write-InstallLog "Ver en la web: $CoordinatorUrl/api/v1/workers"
    Write-InstallLog "Log completo de esta instalacion: $LogFile"
    Write-InstallLog "Para pausar/reanudar: $PauseScriptPath / $ResumeScriptPath"
    Write-InstallLog "Para quitar todo despues: infra/deploy/uninstall-worker.ps1"
}

if ($isResume) {
    # Esta ventana la abrio la Scheduled Task de resume sin que nadie la
    # lanzara a mano -- sin esto se cerraria sola en cuanto termina el
    # script, y el voluntario nunca alcanzaria a leer si funciono o no.
    Write-Host ""
    Read-Host "Presiona Enter para cerrar esta ventana"
}
