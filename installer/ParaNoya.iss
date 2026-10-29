#ifndef AppVersion
  #define AppVersion "1.2.5.5"
#endif
[Setup]
AppId={{22874636-8296-42A7-8E61-56C5242C838F}
AppName=ParaNoya
AppVersion={#AppVersion}
AppPublisher=mburakharput
DefaultDirName={localappdata}\Programs\ParaNoya
DefaultGroupName=ParaNoya
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer-output
OutputBaseFilename=ParaNoya-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\paranoya.ico
UninstallDisplayIcon={app}\ParaNoya.exe
CloseApplications=yes
[Files]
Source: "..\dist\ParaNoya\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: desktopicon; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked
[Icons]
Name: "{group}\ParaNoya"; Filename: "{app}\ParaNoya.exe"
Name: "{autodesktop}\ParaNoya"; Filename: "{app}\ParaNoya.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\ParaNoya.exe"; Description: "ParaNoya uygulamasını aç"; Flags: nowait postinstall skipifsilent
