# Pruebas sin Windows/Docker: extraer funciones del AST, nunca ejecutar instalador.
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot)
$installer = Join-Path $repo 'deploy/install-worker.ps1'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($installer,[ref]$tokens,[ref]$errors)
if ($errors) { throw ($errors | Out-String) }
foreach ($name in @('Uninstall-Worker','Test-WorkerVolumeMounted','Save-LegacyWorkerData','Get-ExistingWorkerEnvValue','Save-SelfCopy')) {
    $fn=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
    Invoke-Expression $fn.Extent.Text
}
$temp=Join-Path ([IO.Path]::GetTempPath()) ('worker-tests-'+[guid]::NewGuid())
New-Item -ItemType Directory $temp | Out-Null
$env:ProgramFiles=$temp; $env:LOCALAPPDATA=$temp; $env:COMPUTERNAME='test'
$LogDir=$temp; $PauseFile=Join-Path $temp 'worker.paused'
$WatchdogTaskName='watchdog'; $ResumeTaskName='resume'
function Write-InstallLog { param($Message,$Level) }
function Get-ScheduledTask { param($TaskName) return $TaskName }
function Unregister-ScheduledTask { param($TaskName,[switch]$Confirm) $global:events.Add("task:$TaskName") }
function Save-PauseResumeScripts {}
function docker {
    $global:events.Add(($args -join ' '))
    $global:LASTEXITCODE=0
    switch ($args[0]) {
        start { if ($global:failStart) { $global:LASTEXITCODE=1 } }
        info { if ($global:failInfo) { $global:LASTEXITCODE=1 } }
        ps { 'geant4-worker' }
        inspect { '[{"Name":"geant4-worker-data","Destination":"/var/lib/geant4-worker"}]' }
        volume { if ($args[1] -eq 'ls') { 'geant4-worker-data' } }
        cp { if ($global:failCopy) { $global:LASTEXITCODE=1 } else { Set-Content (Join-Path $args[2] 'pending-result.json') 'pending' } }
    }
}
function Invoke-UninstallTest {
    [CmdletBinding(SupportsShouldProcess)]param()
    Uninstall-Worker
}
function Assert($Condition,$Message) { if (-not $Condition) { throw $Message } }
function Reset {
    $global:events=[Collections.Generic.List[string]]::new()
    $global:failInfo=$false; $global:failCopy=$false; $global:failStart=$false
    $global:RemoveWorkerData=$false; $global:RemoveDocker=$false
    $global:RemoveDockerAutostart=$false; $global:RemoveWSL=$false
}
try {
    Reset
    Invoke-UninstallTest -WhatIf
    Assert ($events.Count -eq 0) 'WhatIf ejecuto comandos'
    Reset
    $RemoveDocker=$true
    try { Invoke-UninstallTest -Confirm:$false; throw 'No rechazo flags' } catch { Assert ($_.Exception.Message -like '*requiere -RemoveWorkerData*') 'Validacion incorrecta' }
    Assert ($events.Count -eq 0) 'Flags invalidos causaron cambios'
    Reset
    $failInfo=$true
    try { Invoke-UninstallTest -Confirm:$false; throw 'No fallo daemon' } catch { Assert ($_.Exception.Message -like '*Docker no responde*') 'Error incorrecto' }
    Assert (-not ($events -match '^task:|^rm ')) 'Daemon caido produjo eliminaciones'
    Reset
    New-Item -ItemType File $PauseFile | Out-Null
    Invoke-UninstallTest -Confirm:$false
    Assert ($events -contains 'rm geant4-worker') 'No elimino worker'
    Assert (-not ($events -match '^volume rm')) 'Borro datos por defecto'
    Assert (-not (Test-Path $PauseFile)) 'Quedo pausa obsoleta'
    Reset
    $RemoveWorkerData=$true
    Invoke-UninstallTest -Confirm:$false
    Assert ($events -contains 'volume rm geant4-worker-data') 'No retiro datos solicitados'
    Reset
    $failCopy=$true
    try { Save-LegacyWorkerData; throw 'No fallo copia' } catch { Assert ($_.Exception.Message -like '*NO se elimina*') 'Copia fallida no aborta' }
    Assert (-not ($events -match '^rm ')) 'Copia fallida borro contenedor'
    Reset
    $backup=Save-LegacyWorkerData
    Assert (Test-Path (Join-Path $backup 'pending-result.json')) 'No respaldo resultados'
    Assert ($events[0] -eq 'stop geant4-worker') 'Copia no detuvo escrituras'
    Reset
    $SourceScriptPath=Join-Path $temp 'install-worker.ps1'; $SelfCopyPath=$SourceScriptPath
    Set-Content $SourceScriptPath 'test'
    Save-SelfCopy
    Assert ((Get-Content $SourceScriptPath) -eq 'test') 'Autocopia altero fuente'
    Reset
    $pauseScript=Join-Path $repo 'deploy/pause-worker.ps1'
    & $pauseScript
    $userPause=Join-Path $temp 'Geant4Worker/worker.paused'
    Assert (Test-Path $userPause) 'Pausa sin argumentos no creo marca'
    $failStart=$true
    try { & $pauseScript resume; throw 'Reanudar fallo sin error' } catch { Assert ($_.Exception.Message -like '*se conserva la pausa*') 'Error de reanudacion incorrecto' }
    Assert (Test-Path $userPause) 'Reanudacion fallida borro pausa'
    function docker { $global:LASTEXITCODE=0; '[{"Name":"geant4-worker-data","Destination":"/wrong"}]' }
    Assert (-not (Test-WorkerVolumeMounted)) 'Acepto destino incorrecto'
    function Get-Command { param($Name) return $null }
    Assert ($null -eq (Get-ExistingWorkerEnvValue 'WORKER_LABEL')) 'Docker ausente no soportado'
    Write-Host 'PASS: 12 escenarios de ciclo de vida (mocks; no certifican Windows).'
} finally { Remove-Item $temp -Recurse -Force }
