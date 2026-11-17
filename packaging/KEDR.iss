#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef AppDist
  #define AppDist "..\.test-tmp\dist\KEDR"
#endif

[Setup]
AppId={{ADFDD7F5-B9B2-43D4-8C9A-A9F95F027907}
AppName=KEDR
AppVersion={#AppVersion}
AppPublisher=KEDR
AppPublisherURL=https://github.com/ivanitos-x/KEDR
DefaultDirName={localappdata}\Programs\KEDR
DefaultGroupName=KEDR
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\KEDR.exe
OutputDir=..\release
OutputBaseFilename=KEDR-Setup-{#AppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
Source: "{#AppDist}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\KEDR"; Filename: "{app}\KEDR.exe"

[Registry]
Root: HKCU; Subkey: "Software\Classes\KEDR.Model"; ValueType: string; ValueData: "KEDR model"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\KEDR.Model\DefaultIcon"; ValueType: string; ValueData: "{app}\KEDR.exe,0"
Root: HKCU; Subkey: "Software\Classes\KEDR.Model\shell\open\command"; ValueType: string; ValueData: """{app}\KEDR.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\KEDR.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "KEDR"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\KEDR.exe\shell\open\command"; ValueType: string; ValueData: """{app}\KEDR.exe"" ""%1"""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\KEDR\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "KEDR"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\KEDR\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "KEDR model viewer"
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "KEDR"; ValueData: "Software\KEDR\Capabilities"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.kvx\OpenWithProgids"; ValueType: string; ValueName: "KEDR.Model"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\KEDR\Capabilities\FileAssociations"; ValueType: string; ValueName: ".kvx"; ValueData: "KEDR.Model"
Root: HKCU; Subkey: "Software\Classes\Applications\KEDR.exe\SupportedTypes"; ValueType: string; ValueName: ".kvx"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.md2\OpenWithProgids"; ValueType: string; ValueName: "KEDR.Model"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\KEDR\Capabilities\FileAssociations"; ValueType: string; ValueName: ".md2"; ValueData: "KEDR.Model"
Root: HKCU; Subkey: "Software\Classes\Applications\KEDR.exe\SupportedTypes"; ValueType: string; ValueName: ".md2"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.md3\OpenWithProgids"; ValueType: string; ValueName: "KEDR.Model"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\KEDR\Capabilities\FileAssociations"; ValueType: string; ValueName: ".md3"; ValueData: "KEDR.Model"
Root: HKCU; Subkey: "Software\Classes\Applications\KEDR.exe\SupportedTypes"; ValueType: string; ValueName: ".md3"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.glb\OpenWithProgids"; ValueType: string; ValueName: "KEDR.Model"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\KEDR\Capabilities\FileAssociations"; ValueType: string; ValueName: ".glb"; ValueData: "KEDR.Model"
Root: HKCU; Subkey: "Software\Classes\Applications\KEDR.exe\SupportedTypes"; ValueType: string; ValueName: ".glb"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.blend\OpenWithProgids"; ValueType: string; ValueName: "KEDR.Model"; ValueData: ""; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\KEDR\Capabilities\FileAssociations"; ValueType: string; ValueName: ".blend"; ValueData: "KEDR.Model"
Root: HKCU; Subkey: "Software\Classes\Applications\KEDR.exe\SupportedTypes"; ValueType: string; ValueName: ".blend"; ValueData: ""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\KEDR.exe"; Description: "{cm:LaunchProgram,KEDR}"; Flags: nowait postinstall skipifsilent
