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
    [Parameter(Mandatory, Position = 0)]
    [ValidateSet("pause", "resume")]
    [string]$Action
)

$LogDir = Join-Path $env:ProgramData "Geant4Worker"
$PauseFile = Join-Path $LogDir "worker.paused"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if ($Action -eq "pause") {
    New-Item -ItemType File -Force -Path $PauseFile | Out-Null
    docker stop geant4-worker 2>&1 | Out-Null
    Write-Host "Worker pausado. El watchdog automatico ya NO lo va a volver a arrancar."
    Write-Host "Para retomar: .\pause-worker.ps1 resume"
} else {
    Remove-Item -Path $PauseFile -ErrorAction SilentlyContinue
    docker start geant4-worker 2>&1 | Out-Null
    Write-Host "Worker retomado. El watchdog automatico volvio a quedar activo."
}
