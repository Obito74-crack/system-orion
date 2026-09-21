; Inno Setup Script pour System Orion (CDC ET-01 / EF-01 / EF-02 / EF-11)
; Génère l'installateur Windows autonome avec support du mode silencieux /VERYSILENT

#define MyAppName "System Orion"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "System Orion Enterprise"
#define MyAppExeName "SystemOrionService.exe"
#define MyAppAdminExeName "SystemOrionAdmin.exe"
#define MyAppDistDir "dist\SystemOrion"

[Setup]
AppId={{D97F66B1-39E6-4A0D-B4E6-76497B1A832A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SystemOrion
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=SystemOrion_Setup_{#MyAppVersion}
OutputDir=output
Compression=lzma2/ultra
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
UninstallDisplayName={#MyAppName}
CloseApplications=yes
RestartApplications=no

; Chemins et répertoires de données locales (ProgramData)
[Dirs]
Name: "{commonappdata}\SystemOrion"; Permissions: system-full admins-full
Name: "{commonappdata}\SystemOrion\logs"; Permissions: system-full admins-full

[Files]
; Binaires issus de la compilation PyInstaller (one-dir)
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\Configuration {#MyAppName}"; Filename: "{app}\{#MyAppAdminExeName}"; Comment: "Panneau de configuration administrateur System Orion"
Name: "{autoprograms}\{#MyAppName}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Magasin unique HKLM\SOFTWARE\SystemOrion (CDC D7)
Root: HKLM; Subkey: "SOFTWARE\SystemOrion"; Flags: uninsdeletekeyifempty
Root: HKLM; Subkey: "SOFTWARE\SystemOrion"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: createvalueifdoesntexist uninsdeletevalue
Root: HKLM; Subkey: "SOFTWARE\SystemOrion"; ValueType: string; ValueName: "LogDir"; ValueData: "{commonappdata}\SystemOrion\logs"; Flags: createvalueifdoesntexist
Root: HKLM; Subkey: "SOFTWARE\SystemOrion"; ValueType: string; ValueName: "StateDbPath"; ValueData: "{commonappdata}\SystemOrion\state.db"; Flags: createvalueifdoesntexist

[Run]
; Enregistrement et démarrage automatique du service Windows SYSTEM (CDC D1, ET-03)
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install"; StatusMsg: "Enregistrement du service Windows SystemOrion..."; Flags: runhidden
Filename: "sc.exe"; Parameters: "config SystemOrion start= auto"; StatusMsg: "Configuration du démarrage automatique..."; Flags: runhidden
Filename: "sc.exe"; Parameters: "start SystemOrion"; StatusMsg: "Démarrage du service SystemOrion..."; Flags: runhidden
; Lancement optionnel de l'assistant de configuration en fin d'installation manuelle (EF-01a)
Filename: "{app}\{#MyAppAdminExeName}"; Description: "Lancer le panneau de configuration System Orion"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Arrêt propre et suppression du service lors de la désinstallation (CDC EF-11)
Filename: "sc.exe"; Parameters: "stop SystemOrion"; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Parameters: "--remove"; Flags: runhidden

[UninstallDelete]
; Nettoyage des dossiers locaux d'application (les données réseau distantes ne sont JAMAIS supprimées)
Type: files; Name: "{commonappdata}\SystemOrion\state.db*"
Type: filesandordirs; Name: "{commonappdata}\SystemOrion\logs"
Type: dirifempty; Name: "{commonappdata}\SystemOrion"

[Code]
// Vérification préalable des prérequis Windows 10/11 64 bits (CDC section 3)
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  if (Version.Major < 10) then
  begin
    MsgBox('System Orion requiert Windows 10 ou Windows 11 (64 bits).', mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;
  Result := True;
end;
