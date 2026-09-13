<#
.SYNOPSIS
    Pausa o retoma el worker de forma que el watchdog de
    install-worker.ps1 la respete -- a diferencia de un simple
    'docker stop geant4-worker', que el watchdog (registrado cada 30
    min) revertiria solo, deshaciendo la pausa sin que el usuario lo
    pidiera de nuevo.

.PARAMETER Action
    'pause' detiene el contenedor y dice al watchdog que no lo vuelva
    a levantar. 'resume' quita esa marca y vuelve a arrancarlo.

.EXAMPLE
    .\pause-worker.ps1 pause
    .\pause-worker.ps1 resume
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("pause", "resume")]
    [string]$Action = "pause"
)

$ErrorActionPreference = "Stop"

# %LOCALAPPDATA% (perfil del usuario actual), no %ProgramData% -- este
# script corre SIN elevacion (el voluntario no deberia necesitar "Run as
# administrator" solo para pausar/reanudar), y no hay garantia de que un
# usuario estandar tenga permiso de escritura en ProgramData en toda
# maquina. install-worker.ps1 usa la misma ruta para que el watchdog
# (que si corre elevado) encuentre el mismo archivo.
$UserStateDir = Join-Path $env:LOCALAPPDATA "Geant4Worker"
$PauseFile = Join-Path $UserStateDir "worker.paused"
New-Item -ItemType Directory -Force -Path $UserStateDir | Out-Null

if ($Action -eq "pause") {
    New-Item -ItemType File -Force -Path $PauseFile | Out-Null
    docker stop geant4-worker 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo detener Docker; la marca de pausa queda activa. Verifica el contenedor." }
    Write-Host "Worker pausado. El watchdog automatico ya NO lo va a volver a arrancar."
    Write-Host "Para retomar: .\pause-worker.ps1 resume"
} else {
    docker start geant4-worker 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No se pudo iniciar el worker; se conserva la pausa." }
    if (Test-Path $PauseFile) { Remove-Item $PauseFile }
    Write-Host "Worker retomado. El watchdog automatico volvio a quedar activo."
}
