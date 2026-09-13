#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Quita todo lo que install-worker.ps1 dejo corriendo/programado en esta
    PC: el contenedor del worker y las dos Scheduled Tasks (watchdog y
    resume). No desinstala Docker Desktop ni WSL2 -- son software de
    proposito general, no algo que "quitar el worker" deba tocar.

.PARAMETER RemoveDockerAutostart
    Ademas, quita la entrada de auto-inicio de Docker Desktop del
    registro (la que install-worker.ps1 agrego). Sin este flag, Docker
    Desktop se sigue abriendo solo al iniciar sesion -- razonable si
    la persona lo sigue usando para otra cosa.

.EXAMPLE
    .\uninstall-worker.ps1
    .\uninstall-worker.ps1 -RemoveDockerAutostart
#>
[CmdletBinding()]
param(
    [switch]$RemoveDockerAutostart
)

$ErrorActionPreference = "Continue"
$LogDir = Join-Path $env:ProgramData "Geant4Worker"
$LogFile = Join-Path $LogDir "install-worker.log"
$ResumeTaskName = "Geant4WorkerInstallResume"
$WatchdogTaskName = "Geant4WorkerWatchdog"

function Write-InstallLog {
    param([string]$Message)
    $line = "[{0}] [UNINSTALL] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    if (Test-Path $LogDir) { Add-Content -Path $LogFile -Value $line }
}

Write-InstallLog "=== Quitando el worker de computo distribuido de esta PC ==="

foreach ($taskName in @($WatchdogTaskName, $ResumeTaskName)) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-InstallLog "Tarea programada '$taskName' eliminada."
    } else {
        Write-InstallLog "Tarea programada '$taskName' no existia (nada que quitar)."
    }
}

$existing = docker ps -a --filter "name=^geant4-worker$" --format "{{.Names}}" 2>$null
if ($existing -eq "geant4-worker") {
    Write-InstallLog "Deteniendo y eliminando el contenedor 'geant4-worker'..."
    Write-InstallLog "(Si tenia una run asignada, el Coordinator la reencola sola tras el timeout de heartbeat -- no se pierde nada, ver infra/README.md.)"
    docker rm -f geant4-worker *> $null
    Write-InstallLog "Contenedor eliminado."
} else {
    Write-InstallLog "No habia contenedor 'geant4-worker' corriendo (nada que quitar)."
}

if ($RemoveDockerAutostart) {
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    if (Get-ItemProperty -Path $runKey -Name "Docker Desktop" -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $runKey -Name "Docker Desktop" -ErrorAction SilentlyContinue
        Write-InstallLog "Auto-inicio de Docker Desktop desactivado (Docker Desktop sigue instalado, solo ya no se abre solo)."
    }
} else {
    Write-InstallLog "Docker Desktop sigue configurado para abrirse solo al iniciar sesion -- usa -RemoveDockerAutostart si tambien quieres desactivar eso."
}

Write-InstallLog "Docker Desktop y WSL2 NO se desinstalaron -- este script solo quita el worker."
Write-InstallLog "=== Listo. Esta PC ya no participa en el barrido. ==="
