; Build with: powershell -ExecutionPolicy Bypass -File scripts\build_worker.ps1 -Clean -Installer
#define AppName "DrunkenBot GPU Farm Worker"
#define AppVersion "0.1.0"
#define AppExe "GPUFarmWorker.exe"

[Setup]
AppId={{4BCA0A5D-4911-4A3F-AF0A-6E4CA4D519EA}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\DrunkenBot GPU Farm Worker
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=GPUFarmWorker-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExe}

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
