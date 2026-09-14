# Pruebas sin Windows/Docker: extraer funciones del AST, nunca ejecutar instalador.
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot)
$installer = Join-Path $repo 'deploy/install-worker.ps1'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($installer,[ref]$tokens,[ref]$errors)
if ($errors) { throw ($errors | Out-String) }
foreach ($name in @('Uninstall-Worker','Test-WorkerVolumeMounted','Test-DockerSockMounted','Test-DockerEngineRunning','Invoke-NativeCommand','Save-LegacyWorkerData','Get-ExistingWorkerEnvValue','Save-SelfCopy')) {
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
# Reemplaza la funcion real completa, NO solo el cmdlet Unregister-
# ScheduledTask -- la real usa Start-Job, que arranca un runspace/proceso
# nuevo sin visibilidad del mock de arriba (confirmado: un mock ahi nunca
# se invocaba de verdad, ver el comentario en install-worker.ps1). Esta
# version sincronica prueba que Uninstall-Worker sigue pidiendo la
# eliminacion de las tareas correctas, sin poder ejercitar el mecanismo
# de timeout en si (eso exige Windows/Task Scheduler real).
function Unregister-ScheduledTaskSafe { param($TaskName,[int]$TimeoutSeconds) Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
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
    # Verifica que Uninstall-Worker realmente pide desregistrar AMBAS
    # tareas via Unregister-ScheduledTaskSafe -- no solo que el escenario
    # completo no truena (ver el mock sincronico de esa funcion mas
    # arriba, y por que Start-Job real no es mockeable aqui).
    Assert ($events -contains 'task:watchdog') 'No desregistro la tarea del watchdog'
    Assert ($events -contains 'task:resume') 'No desregistro la tarea de resume'
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
    # 2>$null aqui, no dentro del mock: a diferencia de un comando nativo
    # real (donde "*> $null" DENTRO de Invoke-NativeCommand ya silencia el
    # stderr real del proceso, verificado por separado), $PSCmdlet.WriteError()
    # emite al stream de error de PowerShell, que via un scriptblock anidado
    # (Invoke-NativeCommand llamando a esta funcion mock con "&") se muestra
    # igual en consola pese a "Continue" -- ruido cosmetico del mock, no del
    # codigo real que prueba (confirmado: con un comando nativo real que
    # falla, sin este mock, no hay ruido alguno).
    $result = Test-DockerEngineRunning 2>$null
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

    # Bloque real de tolerancia a tarea huerfana (2026-09-14, fix
    # permanente): -ResumeAfterWsl ya no consulta Task Scheduler para
    # decidir $isResume -- exige ADEMAS que $ResumePendingFile exista.
    # El nodo IfStatementAst solo cubre el "if {...}" en si -- se extrae
    # tambien la asignacion de $isResume y su limpieza del marcador
    # (las 2 lineas que le siguen en el flujo real) buscando el texto
    # completo entre el inicio del if y el cierre del segundo bloque,
    # para probar el mecanismo completo, no solo la mitad del if.
    $global:resumeIfNode = $ast.Find({param($node)
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.StartsWith('if ($ResumeAfterWsl -and -not (Test-Path $ResumePendingFile)) {')
    }, $true)
    $global:resumeAssignNode = $ast.Find({param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Extent.Text -eq '$isResume = [bool]$ResumeAfterWsl'
    }, $true)
    $global:resumeCleanupNode = $ast.Find({param($node)
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text -eq 'if ($isResume) { Remove-Item $ResumePendingFile -ErrorAction SilentlyContinue }'
    }, $true)
    $global:resumeBlock = $resumeIfNode.Extent.Text + "`n" + $resumeAssignNode.Extent.Text + "`n" + $resumeCleanupNode.Extent.Text
    function Resolve-ResumeFixture {
        [CmdletBinding()]param([switch]$ResumeAfterWsl, [switch]$MarkerExists)
        $ResumePendingFile = Join-Path $temp 'resume.pending'
        Remove-Item $ResumePendingFile -ErrorAction SilentlyContinue
        if ($MarkerExists) { Set-Content -Path $ResumePendingFile -Value 'x' }
        Remove-Variable -Name isResume -ErrorAction SilentlyContinue
        # Nota real de PowerShell, confirmada aparte antes de escribir
        # esto: un 'return' dentro de un Invoke-Expression NO sale de la
        # funcion que lo invoca -- solo termina la evaluacion de esa
        # cadena, y el resto del CUERPO DE LA FUNCION (aqui, nada mas)
        # sigue normal. Por eso la forma correcta de verificar el caso
        # huerfano no es "la funcion corto camino", es "el codigo despues
        # del return (fijar $isResume) nunca se ejecuto" -- que es
        # exactamente lo que SI iguala al comportamiento real de nivel
        # superior (ahi 'return' termina el script completo antes de
        # llegar a $isResume = ...).
        Invoke-Expression $global:resumeBlock
        return @{
            IsResumeWasSet = (Test-Path variable:isResume)
            IsResume = $isResume
            MarkerStillExists = Test-Path $ResumePendingFile
        }
    }
    $orphan = Resolve-ResumeFixture -ResumeAfterWsl -MarkerExists:$false
    Assert (-not $orphan.IsResumeWasSet) 'Tarea huerfana (-ResumeAfterWsl sin marcador) no debio llegar a fijar $isResume'
    $real = Resolve-ResumeFixture -ResumeAfterWsl -MarkerExists
    Assert ($real.IsResume -eq $true) 'Reanudacion real (-ResumeAfterWsl con marcador) no fijo $isResume=true'
    Assert (-not $real.MarkerStillExists) 'Reanudacion real no borro el marcador tras consumirlo'
    $fresh = Resolve-ResumeFixture -MarkerExists:$false
    Assert ($fresh.IsResume -eq $false) 'Instalacion/actualizacion normal (sin -ResumeAfterWsl) no debio marcarse como reanudacion'

    Write-Host 'PASS: 20 escenarios de ciclo de vida (mocks; no certifican Windows).'
} finally { Remove-Item $temp -Recurse -Force }
