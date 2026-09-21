<#
.SYNOPSIS
    Script de désinstallation propre de System Orion (EF-11).

.DESCRIPTION
    Arrête et supprime le service Windows « SystemOrion ».
    Nettoie les clés de registre HKLM\SOFTWARE\SystemOrion et les fichiers binaires locaux.
    CONFORMITÉ EF-11 : Les données et historiques sauvegardés sur le partage réseau
    ne sont JAMAIS supprimés lors de la désinstallation.
#>

[CmdletBinding()]
param(
    [switch]$KeepLogs = $true,
    [switch]$KeepConfig = $false
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host "  System Orion — Désinstallation de l'agent (EF-11)        " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Yellow

# 1. Vérification des privilèges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Ce script doit être exécuté avec des privilèges Administrateur élevés."
    exit 1
}

$serviceName = "SystemOrion"

# 2. Arrêt du service
$svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -ne "Stopped") {
        Write-Host "[*] Arrêt du service $serviceName..." -ForegroundColor Gray
        Stop-Service -Name $serviceName -Force
        Start-Sleep -Seconds 2
    }
    # 3. Suppression du service
    & sc.exe delete $serviceName
    Write-Host "[OK] Service Windows $serviceName supprimé." -ForegroundColor Green
} else {
    Write-Host "[*] Service Windows $serviceName non présent." -ForegroundColor Gray
}

# 4. Suppression de la configuration en registre
if (-not $KeepConfig) {
    $regPath = "HKLM:\SOFTWARE\SystemOrion"
    if (Test-Path $regPath) {
        Remove-Item -Path $regPath -Recurse -Force
        Write-Host "[OK] Clé de registre $regPath supprimée." -ForegroundColor Green
    }
}

# 5. Gestion des journaux et état
$dataDir = "C:\ProgramData\SystemOrion"
if (Test-Path $dataDir) {
    if ($KeepLogs) {
        Write-Host "[INFO] Les journaux locaux dans '$dataDir\logs' sont conservés." -ForegroundColor Cyan
    } else {
        Remove-Item -Path $dataDir -Recurse -Force
        Write-Host "[OK] Données locales supprimées : $dataDir" -ForegroundColor Green
    }
}

Write-Host "==========================================================" -ForegroundColor Yellow
Write-Host "  Désinstallation terminée. Sauvegardes réseau préservées. " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Yellow
