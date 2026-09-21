<#
.SYNOPSIS
    Script de déploiement et configuration automatisé de System Orion (D7, EF-02, ET-01).

.DESCRIPTION
    Ce script automatise :
    - La vérification des prérequis (Windows 10/11 x64, droits Administrateur, NTFS).
    - La création de l'arborescence C:\ProgramData\SystemOrion\logs.
    - Le dimensionnement initial du journal USN à 256 Mo (EF-04).
    - L'enregistrement des modèles de stratégie de groupe GPO (ADMX/ADML).
    - L'initialisation de la clé de registre HKLM\SOFTWARE\SystemOrion.
    - L'installation et le démarrage du service Windows « SystemOrion » sous compte SYSTEM (D1).

.PARAMETER BinaryPath
    Chemin du binaire compilé de l'agent (SystemOrionService.exe).

.PARAMETER TargetUncPath
    Chemin UNC de partage optionnel pour surcharger la détection AD (EF-03).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$BinaryPath = "C:\Program Files\SystemOrion\SystemOrionService.exe",

    [Parameter(Mandatory=$false)]
    [string]$TargetUncPath = ""
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  System Orion — Déploiement et enregistrement du service  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Vérification des privilèges Administrateur
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Ce script doit être exécuté avec des privilèges Administrateur élevés."
    exit 1
}

# 2. Vérification du système de fichiers NTFS sur C:
$volume = Get-Volume -DriveLetter C -ErrorAction SilentlyContinue
if ($volume.FileSystemType -ne "NTFS") {
    Write-Error "Le volume C: doit être formaté en NTFS pour supporter le journal USN (requis CDC section 3)."
    exit 1
}
Write-Host "[OK] Volume C: NTFS vérifié." -ForegroundColor Green

# 3. Création des répertoires locaux
$logDir = "C:\ProgramData\SystemOrion\logs"
if (-not (Test-Path $logDir)) {
    New-Item -Path $logDir -ItemType Directory -Force | Out-Null
    Write-Host "[OK] Répertoire de journaux créé : $logDir" -ForegroundColor Green
}

# 4. Dimensionnement initial du journal USN (256 Mo, allocation delta 32 Mo - EF-04)
Write-Host "[*] Configuration du dimensionnement du journal USN sur C:..." -ForegroundColor Yellow
try {
    # 268435456 octets = 256 Mo, 33554432 octets = 32 Mo
    & fsutil usn createjournal m=268435456 a=33554432 C:
    Write-Host "[OK] Journal USN dimensionné à 256 Mo." -ForegroundColor Green
} catch {
    Write-Warning "Impossible de redimensionner le journal USN automatiquement : $_"
}

# 5. Configuration de la base de registre HKLM\SOFTWARE\SystemOrion
$regPath = "HKLM:\SOFTWARE\SystemOrion"
if (-not (Test-Path $regPath)) {
    New-Item -Path $regPath -Force | Out-Null
}

Set-ItemProperty -Path $regPath -Name "BackupSubfolder" -Value "SystemOrion" -Force
Set-ItemProperty -Path $regPath -Name "CycleIntervalSeconds" -Value 60 -Type DWord -Force
Set-ItemProperty -Path $regPath -Name "UsnJournalSizeMb" -Value 256 -Type DWord -Force
Set-ItemProperty -Path $regPath -Name "RetentionMaxVersions" -Value 10 -Type DWord -Force
Set-ItemProperty -Path $regPath -Name "RetentionMaxDays" -Value 90 -Type DWord -Force

if ($TargetUncPath -ne "") {
    Set-ItemProperty -Path $regPath -Name "UncOverride" -Value $TargetUncPath -Force
}
Write-Host "[OK] Clé de registre $regPath initialisée." -ForegroundColor Green

# 6. Copie des modèles GPO (ADMX/ADML) vers le magasin local PolicyDefinitions si présents
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$admxSource = Join-Path $scriptDir "..\gpo\SystemOrion.admx"
$admlSource = Join-Path $scriptDir "..\gpo\fr-FR\SystemOrion.adml"
$policyDefPath = "C:\Windows\PolicyDefinitions"

if (Test-Path $admxSource) {
    Copy-Item -Path $admxSource -Destination $policyDefPath -Force -ErrorAction SilentlyContinue
    $admlDest = Join-Path $policyDefPath "fr-FR"
    if (-not (Test-Path $admlDest)) { New-Item -Path $admlDest -ItemType Directory -Force | Out-Null }
    Copy-Item -Path $admlSource -Destination $admlDest -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Modèles GPO ADMX/ADML installés dans C:\Windows\PolicyDefinitions." -ForegroundColor Green
}

# 7. Enregistrement et configuration du service Windows SystemOrion
$serviceName = "SystemOrion"
$serviceDisplayName = "System Orion"
$serviceDesc = "Agent silencieux de sauvegarde automatique des postes vers le partage réseau de l'entreprise (CDC v1.3)."

if (Test-Path $BinaryPath) {
    # Si le service existe déjà, on l'arrête avant mise à jour
    $existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existing) {
        if ($existing.Status -eq "Running") {
            Stop-Service -Name $serviceName -Force
        }
    } else {
        # Création du service sous compte LocalSystem (D1)
        & sc.exe create $serviceName binPath= "`"$BinaryPath`"" start= auto DisplayName= "$serviceDisplayName" obj= "LocalSystem"
        & sc.exe description $serviceName "$serviceDesc"
        # Configuration du redémarrage automatique en cas de défaillance (EF-12)
        & sc.exe failure $serviceName reset= 86400 actions= restart/60000/restart/60000/restart/60000
        Write-Host "[OK] Service Windows '$serviceName' créé et configuré." -ForegroundColor Green
    }

    Start-Service -Name $serviceName
    Write-Host "[OK] Service Windows '$serviceName' démarré avec succès." -ForegroundColor Green
} else {
    Write-Warning "Le binaire '$BinaryPath' est introuvable. Le service n'a pas été créé, mais la configuration et les prérequis sont prêts."
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Déploiement de System Orion terminé avec succès.        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
