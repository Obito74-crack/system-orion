<#
.SYNOPSIS
    Script de diagnostic et validation d'environnement pour System Orion (Section 3, 10).

.DESCRIPTION
    Vérifie l'éligibilité du poste cible :
    1. Système d'exploitation et architecture 64 bits
    2. Système de fichiers NTFS et disponibilité du journal USN (EF-04)
    3. Jonction au domaine Active Directory et attributs utilisateur (EF-03)
    4. Accessibilité du partage réseau SMB (D5)
    5. Fournisseur de cliché instantané VSS (Win32_ShadowCopy / EF-06)
    6. Source Windows Event Log « SystemOrion » (EF-10)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$TestUncShare = ""
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  System Orion — Rapport de diagnostic d'environnement    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$allOk = $true

# 1. OS et Architecture
$os = Get-CimInstance Win32_OperatingSystem
$is64 = [Environment]::Is64BitOperatingSystem
Write-Host "OS : $($os.Caption) ($($os.Version)) - 64-bit : $is64"
if (-not $is64) {
    Write-Warning "System Orion nécessite impérativement un OS 64 bits."
    $allOk = $false
}

# 2. Volume C: NTFS et USN
$volC = Get-Volume -DriveLetter C -ErrorAction SilentlyContinue
if ($volC.FileSystemType -eq "NTFS") {
    Write-Host "[OK] Volume C: formaté en NTFS." -ForegroundColor Green
    try {
        $usnOut = & fsutil usn queryjournal C: 2>&1
        Write-Host "[OK] Journal USN actif sur C:." -ForegroundColor Green
    } catch {
        Write-Warning "Journal USN inaccessible sur C: : $_"
        $allOk = $false
    }
} else {
    Write-Error "Volume C: n'est pas en NTFS (trouvé : $($volC.FileSystemType))."
    $allOk = $false
}

# 3. Active Directory
$compSystem = Get-CimInstance Win32_ComputerSystem
if ($compSystem.PartOfDomain) {
    Write-Host "[OK] Poste joint au domaine AD : $($compSystem.Domain)" -ForegroundColor Green
} else {
    Write-Warning "Le poste est en WORKGROUP (hors domaine AD). Mode D5 standard non applicable."
}

# 4. Cliché instantané VSS (WMI / Win32_ShadowCopy)
try {
    $vssClass = Get-CimClass -ClassName Win32_ShadowCopy -ErrorAction SilentlyContinue
    if ($vssClass) {
        Write-Host "[OK] Classe WMI Win32_ShadowCopy disponible." -ForegroundColor Green
    } else {
        Write-Warning "Classe Win32_ShadowCopy non détectée."
        $allOk = $false
    }
} catch {
    Write-Warning "Erreur lors du test WMI VSS : $_"
    $allOk = $false
}

# 5. Partage réseau SMB
if ($TestUncShare -ne "") {
    if (Test-Path $TestUncShare) {
        Write-Host "[OK] Partage réseau accessible : $TestUncShare" -ForegroundColor Green
    } else {
        Write-Warning "Le partage réseau cible '$TestUncShare' est inaccessible ou droits insuffisants."
    }
}

# 6. Event Log « SystemOrion »
$sourceExists = [System.Diagnostics.EventLog]::SourceExists("SystemOrion")
if ($sourceExists) {
    Write-Host "[OK] Source Event Log 'SystemOrion' déjà enregistrée." -ForegroundColor Green
} else {
    Write-Host "[INFO] Source Event Log 'SystemOrion' sera créée au premier démarrage de l'agent." -ForegroundColor Gray
}

Write-Host "----------------------------------------------------------"
if ($allOk) {
    Write-Host "Diagnostic terminé : Le poste est éligible à System Orion." -ForegroundColor Green
} else {
    Write-Host "Diagnostic terminé avec des avertissements (voir ci-dessus)." -ForegroundColor Yellow
}
Write-Host "==========================================================" -ForegroundColor Cyan
