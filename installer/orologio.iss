; Εγκατάσταση «Ωρολόγιο Δημοτικού» (Inno Setup 6). Χτίζεται στο GitHub Actions:
;   iscc /DAppVersion=0.5.0 /DSourceDir=..\dist\Orologio_Dimotikou installer\orologio.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Orologio_Dimotikou"
#endif

[Setup]
AppId={{6C1E0B5A-3F7D-4C49-9E2B-0B7A8D2E5F41}
AppName=Ωρολόγιο Δημοτικού
AppVersion={#AppVersion}
AppVerName=Ωρολόγιο Δημοτικού {#AppVersion}
AppPublisher=Ωρολόγιο Δημοτικού
AppPublisherURL=https://github.com/stam1966/orologio-dimotikou
AppSupportURL=https://github.com/stam1966/orologio-dimotikou/issues
AppUpdatesURL=https://github.com/stam1966/orologio-dimotikou/releases
DefaultDirName={localappdata}\Programs\OrologioDimotikou
DefaultGroupName=Ωρολόγιο Δημοτικού
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Orologio_Dimotikou_Setup_{#AppVersion}
SetupIconFile=..\src\app.ico
UninstallDisplayIcon={app}\src\app.ico
UninstallDisplayName=Ωρολόγιο Δημοτικού
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=force
RestartApplications=no

[Languages]
#ifexist AddBackslash(SourcePath) + "Greek.isl"
Name: "el"; MessagesFile: "{#SourcePath}\Greek.isl"
#else
Name: "el"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Εικονίδιο στην επιφάνεια εργασίας"; GroupDescription: "Εικονίδια:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "data\*,ΕΓΚΑΤΑΣΤΑΣΗ.cmd,ΑΠΕΓΚΑΤΑΣΤΑΣΗ.cmd,SYNTOMEFSI.cmd"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Τα δεδομένα του σχολείου: δεν διαγράφονται ποτέ από την απεγκατάσταση
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\Ωρολόγιο Δημοτικού"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-X utf8 ""{app}\src\server.py"""; WorkingDir: "{app}"; IconFilename: "{app}\src\app.ico"
Name: "{group}\Ωρολόγιο Δημοτικού (διάγνωση προβλημάτων)"; Filename: "{app}\START_KONSOLA.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\src\app.ico"
Name: "{autodesktop}\Ωρολόγιο Δημοτικού"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-X utf8 ""{app}\src\server.py"""; WorkingDir: "{app}"; IconFilename: "{app}\src\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-X utf8 ""{app}\src\server.py"""; WorkingDir: "{app}"; Description: "Άνοιγμα της εφαρμογής"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\src\__pycache__"
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\src"
Type: filesandordirs; Name: "{app}\tests"

[Messages]
el.FinishedLabel=Η εγκατάσταση ολοκληρώθηκε. Η εφαρμογή ανοίγει από το εικονίδιο «Ωρολόγιο Δημοτικού». Τα δεδομένα σας φυλάσσονται στον φάκελο «data» και διατηρούνται σε ενημερώσεις και απεγκατάσταση.
