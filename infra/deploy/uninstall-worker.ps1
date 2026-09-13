#Requires -RunAsAdministrator
# Compatibilidad: toda la implementacion vive en install-worker.ps1.
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [switch]$RemoveDockerAutostart,
    [switch]$RemoveWorkerData,
    [switch]$RemoveDocker,
    [switch]$RemoveWSL
)
& (Join-Path $PSScriptRoot 'install-worker.ps1') -Action Uninstall @PSBoundParameters
