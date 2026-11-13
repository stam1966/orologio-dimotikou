; Εγκατάσταση της σουίτας «Σχολικές Εφαρμογές» (Ωρολόγιο Σχολείου + Εφημερίες Εκπαιδευτικών), Inno Setup 6.
; Περιέχει τα δύο κανονικά Setup και τα εκτελεί σιωπηλά· μόνη της γράφει τη ρύθμιση του υπολογιστή
; %APPDATA%\SchoolApps\suite.json (κοινός φάκελος, ρόλος) που διαβάζουν και οι δύο εφαρμογές.
;   iscc /DAppVersion=0.35.0 /DOroSetup=..\dist\Orologio_Dimotikou_Setup_0.35.0.exe /DEfSetup=..\dist\Efimeries_Setup_x64.exe installer\suite.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef OroSetup
  #define OroSetup "..\dist\Orologio_Dimotikou_Setup.exe"
#endif
#ifndef EfSetup
  #define EfSetup "..\dist\Efimeries_Setup_x64.exe"
#endif

[Setup]
AppId={{2F8C6A41-7B3E-4D1A-9E55-6C0B2A9D7F13}
AppName=Σχολικές Εφαρμογές
AppVersion={#AppVersion}
AppVerName=Σχολικές Εφαρμογές {#AppVersion}
AppPublisher=Σχολικές Εφαρμογές
AppPublisherURL=https://github.com/stam1966/orologio-dimotikou
CreateAppDir=no
Uninstallable=no
DisableProgramGroupPage=yes
DisableReadyPage=no
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Sxolikes_Efarmoges_Setup_{#AppVersion}
SetupIconFile=..\src\app.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
#ifexist AddBackslash(SourcePath) + "Greek.isl"
Name: "el"; MessagesFile: "{#SourcePath}\Greek.isl"
#else
Name: "el"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Εικονίδια στην επιφάνεια εργασίας"; GroupDescription: "Εικονίδια:"

[Files]
Source: "{#OroSetup}"; DestDir: "{tmp}"; DestName: "orologio_setup.exe"; Flags: deleteafterinstall
Source: "{#EfSetup}"; DestDir: "{tmp}"; DestName: "efimeries_setup.exe"; Flags: deleteafterinstall

[Run]
Filename: "{tmp}\orologio_setup.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART {code:TasksArg}"; StatusMsg: "Εγκατάσταση: Ωρολόγιο Σχολείου…"; Check: WantOrologio
Filename: "{tmp}\efimeries_setup.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART {code:TasksArg}"; StatusMsg: "Εγκατάσταση: Εφημερίες Εκπαιδευτικών…"; Check: WantEfimeries
Filename: "{localappdata}\Programs\OrologioDimotikou\runtime\pythonw.exe"; Parameters: "-X utf8 ""{localappdata}\Programs\OrologioDimotikou\src\server.py"""; WorkingDir: "{localappdata}\Programs\OrologioDimotikou"; Description: "Άνοιγμα: Ωρολόγιο Σχολείου"; Flags: nowait postinstall skipifsilent; Check: WantOrologio
Filename: "{localappdata}\Programs\EfimeriesEkpaideftikon\EfimeriesPortable_x64.exe"; WorkingDir: "{localappdata}\Programs\EfimeriesEkpaideftikon"; Description: "Άνοιγμα: Εφημερίες Εκπαιδευτικών"; Flags: nowait postinstall skipifsilent unchecked; Check: WantEfimeries

[Messages]
el.FinishedLabel=Η εγκατάσταση ολοκληρώθηκε. Οι εφαρμογές ανοίγουν από τα εικονίδιά τους. Στην πρώτη εκκίνηση του υπολογιστή της Διεύθυνσης το Ωρολόγιο ζητά να ορίσετε (ή να πληκτρολογήσετε) το PIN της Διεύθυνσης.

[Code]
var
  AppsPage, UsePage, RolePage: TInputOptionWizardPage;
  DirPage: TInputDirWizardPage;

function Hex4(N: Integer): String;
var
  Digits: String;
begin
  Digits := '0123456789abcdef';
  Result := Digits[((N shr 12) and 15) + 1] + Digits[((N shr 8) and 15) + 1] +
            Digits[((N shr 4) and 15) + 1] + Digits[(N and 15) + 1];
end;

{ JSON μόνο με ASCII: οι ελληνικοί χαρακτήρες γράφονται ως \uXXXX }
function JsonEscape(const S: String): String;
var
  I: Integer;
  C: Char;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := S[I];
    if C = '\' then
      Result := Result + '\\'
    else if C = '"' then
      Result := Result + '\"'
    else if Ord(C) > 126 then
      Result := Result + '\u' + Hex4(Ord(C))
    else
      Result := Result + C;
  end;
end;

function WantOrologio(): Boolean;
begin
  Result := AppsPage.Values[0];
end;

function WantEfimeries(): Boolean;
begin
  Result := AppsPage.Values[1];
end;

function TasksArg(Param: String): String;
begin
  if WizardIsTaskSelected('desktopicon') then
    Result := '/TASKS="desktopicon"'
  else
    Result := '/TASKS=""';
end;

function Shared(): Boolean;
begin
  Result := not UsePage.Values[0];
end;

{ Ο φάκελος της σουίτας: νέος → <επιλογή>\Σχολικές Εφαρμογές· σύνδεση → ο φάκελος που έχει «Κοινά»
  (ή ο γονικός του, αν δείξατε τον φάκελο που τον περιέχει). }
function SuiteRoot(): String;
var
  D: String;
begin
  D := RemoveBackslash(DirPage.Values[0]);
  if DirExists(D + '\Κοινά') then
    Result := D
  else if DirExists(D + '\Σχολικές Εφαρμογές\Κοινά') then
    Result := D + '\Σχολικές Εφαρμογές'
  else if UsePage.Values[1] then
    Result := D + '\Σχολικές Εφαρμογές'
  else
    Result := '';
end;

procedure InitializeWizard;
begin
  AppsPage := CreateInputOptionPage(wpWelcome, 'Εφαρμογές', 'Ποιες εφαρμογές θα εγκατασταθούν;',
    'Μπορείτε να προσθέσετε την άλλη εφαρμογή αργότερα, ξανατρέχοντας αυτή την εγκατάσταση.', False, False);
  AppsPage.Add('Ωρολόγιο Σχολείου (ωρολόγιο πρόγραμμα, αναπληρώσεις, έντυπα Διεύθυνσης)');
  AppsPage.Add('Εφημερίες Εκπαιδευτικών');
  AppsPage.Values[0] := True;
  AppsPage.Values[1] := True;

  UsePage := CreateInputOptionPage(AppsPage.ID, 'Χρήση από άλλο υπολογιστή', 'Θα χρησιμοποιηθούν οι εφαρμογές και από άλλο υπολογιστή;',
    'Για δύο υπολογιστές (π.χ. Διευθυντής και Υποδιευθυντής) τα δεδομένα μπαίνουν σε κοινό φάκελο που βλέπουν και οι δύο ' +
    '(κοινόχρηστος φάκελος του σχολείου, NAS ή φάκελος του ενός υπολογιστή σε κοινή χρήση).', True, False);
  UsePage.Add('Όχι, μόνο αυτός ο υπολογιστής');
  UsePage.Add('Ναι — αυτός είναι ο ΠΡΩΤΟΣ υπολογιστής: δημιουργία κοινού φακέλου');
  UsePage.Add('Ναι — σύνδεση σε κοινό φάκελο που δημιουργήθηκε ήδη στον πρώτο υπολογιστή');
  UsePage.SelectedValueIndex := 0;

  DirPage := CreateInputDirPage(UsePage.ID, 'Κοινός φάκελος', 'Πού βρίσκεται ο κοινός φάκελος;',
    'Πρώτος υπολογιστής: διαλέξτε πού θα δημιουργηθεί ο φάκελος «Σχολικές Εφαρμογές». ' +
    'Δεύτερος υπολογιστής: δείξτε τον φάκελο «Σχολικές Εφαρμογές» του πρώτου (π.χ. \\ΥΠΟΛΟΓΙΣΤΗΣ\Κοινά\Σχολικές Εφαρμογές).',
    False, 'Νέος φάκελος');
  DirPage.Add('');
  DirPage.Values[0] := ExpandConstant('{userdocs}');

  RolePage := CreateInputOptionPage(DirPage.ID, 'Ρόλος του υπολογιστή', 'Ποιος χρησιμοποιεί αυτόν τον υπολογιστή;',
    'Ο ρόλος αλλάζει αργότερα από το Ωρολόγιο (Ρυθμίσεις εφαρμογής → Κοινή χρήση) μόνο με το PIN της Διεύθυνσης.', True, False);
  RolePage.Add('Διεύθυνση — αλλάζει το ωρολόγιο πρόγραμμα (στην πρώτη εκκίνηση ορίζετε ή δίνετε το PIN)');
  RolePage.Add('Υποδιευθυντής — βλέπει το πρόγραμμα, δηλώνει απουσίες και κάνει τις καλύψεις· εφημερίες πλήρως');
  RolePage.SelectedValueIndex := 0;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = DirPage.ID) or (PageID = RolePage.ID) then
    Result := not Shared();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = RolePage.ID then
  begin
    if UsePage.Values[1] then RolePage.SelectedValueIndex := 0 else RolePage.SelectedValueIndex := 1;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = AppsPage.ID) and (not AppsPage.Values[0]) and (not AppsPage.Values[1]) then
  begin
    MsgBox('Επιλέξτε τουλάχιστον μία εφαρμογή.', mbError, MB_OK);
    Result := False;
  end;
  if (CurPageID = DirPage.ID) and UsePage.Values[2] and (SuiteRoot() = '') then
  begin
    MsgBox('Στον φάκελο που δείξατε δεν υπάρχουν δεδομένα της σουίτας (λείπει ο υποφάκελος «Κοινά»).' + #13#10 +
           'Δείξτε τον φάκελο «Σχολικές Εφαρμογές» που δημιουργήθηκε στον πρώτο υπολογιστή.', mbError, MB_OK);
    Result := False;
  end;
  if (CurPageID = DirPage.ID) and UsePage.Values[1] and (not DirExists(RemoveBackslash(DirPage.Values[0]))) then
  begin
    MsgBox('Ο φάκελος δεν υπάρχει ή δεν είναι προσβάσιμος.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Cfg, Root, Role, Confirmed: String;
begin
  if CurStep = ssInstall then
  begin
    Root := '';
    Role := 'director';
    Confirmed := 'true';
    if Shared() then
    begin
      Root := SuiteRoot();
      ForceDirectories(Root + '\Ωρολόγιο');
      ForceDirectories(Root + '\Εφημερίες');
      ForceDirectories(Root + '\Κοινά');
      if RolePage.Values[0] then Role := 'director' else Role := 'deputy';
      Confirmed := 'false';
    end;
    Cfg := ExpandConstant('{userappdata}\SchoolApps');
    ForceDirectories(Cfg);
    SaveStringToFile(Cfg + '\suite.json', '{"root": "' + JsonEscape(Root) + '", "role": "' + Role + '", "confirmed": ' + Confirmed + '}', False);
  end;
end;
