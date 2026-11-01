#ifndef AppVersion
  #define AppVersion "1.2.5.3"
#endif
[Setup]
ShowLanguageDialog=yes
UsePreviousLanguage=yes
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
[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
turkish.DesktopShortcut=Masaüstü kısayolu oluştur
english.DesktopShortcut=Create a desktop shortcut

[Files]
Source: "..\dist\ParaNoya\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
[Icons]
Name: "{group}\ParaNoya"; Filename: "{app}\ParaNoya.exe"
Name: "{autodesktop}\ParaNoya"; Filename: "{app}\ParaNoya.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\ParaNoya.exe"; Description: "ParaNoya uygulamasını aç"; Flags: nowait postinstall skipifsilent
