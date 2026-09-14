# Pruebas sin Windows/Docker: extraer funciones del AST, nunca ejecutar instalador.
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot)
$installer = Join-Path $repo 'deploy/install-worker.ps1'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($installer,[ref]$tokens,[ref]$errors)
if ($errors) { throw ($errors | Out-String) }
foreach ($name in @('Uninstall-Worker','Test-WorkerVolumeMounted','Test-DockerSockMounted','Test-DockerEngineRunning','Save-LegacyWorkerData','Get-ExistingWorkerEnvValue','Save-SelfCopy')) {
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
    Reset
    function docker { $global:LASTEXITCODE=0; '[{"Source":"/var/run/docker.sock","Destination":"/var/run/docker.sock"}]' }
    Assert (Test-DockerSockMounted) 'No detecto el socket de Docker montado'
    function docker { $global:LASTEXITCODE=0; '[{"Name":"geant4-worker-data","Destination":"/var/lib/geant4-worker"}]' }
    Assert (-not (Test-DockerSockMounted)) 'Acepto un contenedor sin el socket de Docker montado'
    Reset
    # Bug real reportado en produccion (2026-09-13, log completo de un
    # voluntario): con $ErrorActionPreference='Stop' (global del
    # instalador) y Windows PowerShell 5.1 (lo que de hecho usan las
    # Scheduled Tasks), un comando nativo que escribe a stderr y se
    # redirige con "*>"/"2>&1" se convertia en un NativeCommandError que
    # abortaba el instalador entero -- exactamente cuando "docker info"
    # fallaba porque el motor todavia no habia arrancado, el propio
    # chequeo que debia DETECTAR eso terminaba el script antes de llegar
    # a Start-Process "Docker Desktop.exe". No se puede reproducir el
    # NativeCommandError exacto de PS 5.1 aqui (pwsh 7.x ya no lo tiene,
    # cambio de comportamiento documentado por Microsoft) -- se simula el
    # mismo tipo de error (un comando nativo que escribe a stderr y
    # devuelve LASTEXITCODE!=0) via un ErrorRecord real, no un throw
    # generico. Esta funcion aisla 'Continue' alrededor de "docker info"
    # precisamente para neutralizar esto bajo 'Stop'.
    $ErrorActionPreference = 'Stop'
    function docker {
        $err = [System.Management.Automation.ErrorRecord]::new(
            [System.Exception]::new('simulated stderr from native command'),
            'NativeCommandError', [System.Management.Automation.ErrorCategory]::NotSpecified, $null)
        $global:LASTEXITCODE = 1
        $PSCmdlet.WriteError($err)
    }
    $result = Test-DockerEngineRunning
    Assert ($result -eq $false) 'Test-DockerEngineRunning no debio propagar el NativeCommandError bajo Stop'
    Assert ($ErrorActionPreference -eq 'Stop') 'Test-DockerEngineRunning no restauro ErrorActionPreference tras NativeCommandError'
    Reset
    # Barrera adicional: una excepcion real de PowerShell (no solo un
    # comando nativo con exit code) tampoco debe propagarse -- por eso la
    # funcion real tiene 'catch' ademas de 'finally'. Sin ese catch, este
    # caso especifico fallaria (la excepcion se propagaria pese al finally).
    $ErrorActionPreference = 'Stop'
    function docker { throw [System.Management.Automation.RuntimeException]::new('simulated non-native exception') }
    $result = Test-DockerEngineRunning
    Assert ($result -eq $false) 'Test-DockerEngineRunning no debio propagar una excepcion real bajo Stop'
    Assert ($ErrorActionPreference -eq 'Stop') 'Test-DockerEngineRunning no restauro ErrorActionPreference tras excepcion real'
    Reset
    # Ejecutar el bloque REAL que conserva configuracion al actualizar.
    $global:updateBlock = $ast.Find({param($node)
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.StartsWith('if ($isUpdate) {')
    }, $true).Extent.Text
    function Get-ExistingWorkerEnvValue {
        param($VarName)
        if ($VarName -eq 'WORKER_AUTO_UPDATE') { return '0' }
        return $null
    }
    function docker {
        $global:LASTEXITCODE=0
        if ($args -contains '{{.Config.Image}}') { return 'repo@sha256:updated' }
        return '{"NanoCpus":1000000000,"Memory":2147483648}'
    }
    function Resolve-UpdateFixture {
        [CmdletBinding()]param($WorkerImage='old-installer-pin', $WorkerAutoUpdate='1')
        $isUpdate=$true
        Invoke-Expression $global:updateBlock
        return @{ Image=$WorkerImage; AutoUpdate=$WorkerAutoUpdate }
    }
    $resolved=Resolve-UpdateFixture
    Assert ($resolved.Image -eq 'repo@sha256:updated') 'Instalador revierte imagen actualizada'
    Assert ($resolved.AutoUpdate -eq '0') 'Instalador reactiva auto-update deshabilitado'
    $resolved=Resolve-UpdateFixture -WorkerImage 'explicit-pin' -WorkerAutoUpdate '1'
    Assert ($resolved.Image -eq 'explicit-pin' -and $resolved.AutoUpdate -eq '1') 'Ignora opciones explicitas'
    Write-Host 'PASS: 17 escenarios de ciclo de vida (mocks; no certifican Windows).'
} finally { Remove-Item $temp -Recurse -Force }
