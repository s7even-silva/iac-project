<#
.SYNOPSIS
    Reanuda el worker pausado con pause-worker.ps1.

.DESCRIPTION
    Wrapper trivial sobre pause-worker.ps1 resume -- existe como archivo
    separado para que el voluntario tenga dos nombres de comando claros
    (pause-worker / resume-worker) en vez de tener que acordarse de un
    parametro posicional. Ambos scripts se distribuyen juntos (ver
    Save-SelfCopy/Register-WatchdogTask en install-worker.ps1).

.EXAMPLE
    .\resume-worker.ps1
#>
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $here "pause-worker.ps1") resume
