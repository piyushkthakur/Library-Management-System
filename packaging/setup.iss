; Library Management System — Windows installer (Inno Setup 6/7)
;
; Flow:
;   welcome -> [XAMPP page, only if XAMPP is missing] -> destination ->
;   desktop-shortcut task -> install files -> post-install config -> done
;
; The XAMPP page offers to run the bundled XAMPP installer; when it returns,
; setup re-checks and only then lets the LMS installation continue.
; The app itself creates the database and runs migrations on first launch.

#define MyAppName "Library Management System"
#define MyAppVersion "1.0"
#define MyAppExeName "LibraryManagementSystem.exe"

[Setup]
AppId={{A8F3D2B1-5C7E-4A96-8D21-3F6B9E4C7A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={autopf}\LibraryManagementSystem
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=output
OutputBaseFilename=LibraryManagementSystem-Setup-{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; The application bundle built by packaging\build.bat
Source: "..\dist\LibraryManagementSystem\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; Clean environment template (no credentials) — copied to the data dir on first install
Source: "env.template"; DestDir: "{app}"; Flags: ignoreversion
; Bundled XAMPP installer — extracted to {tmp} only when actually needed
Source: "vendor\xampp-installer.exe"; DestDir: "{tmp}"; Flags: dontcopy
; Microsoft VC++ runtime — pre-installed before XAMPP (see XamppInstallClick)
Source: "vendor\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  XamppDir: String;
  XamppPage: TWizardPage;
  XamppStatus: TNewStaticText;
  XamppButton: TButton;

{ A directory counts as XAMPP if it has the control panel or a MySQL server. }
function IsXamppAt(const Dir: String): Boolean;
var
  Base: String;
begin
  Base := AddBackslash(Dir);
  Result := FileExists(Base + 'xampp-control.exe') or
            FileExists(Base + 'xampp_control.exe') or
            FileExists(Base + 'mysql\bin\mysqld.exe');
end;

{ Same locations the LMS app itself scans (database.py): drives C:..G: plus
  the usual registry uninstall entries. }
function ProbeXamppDir(): String;
var
  i: Integer;
  Candidate, Uni: String;
begin
  Result := '';
  for i := 1 to 5 do
  begin
    Candidate := Copy('CDEFG', i, 1) + ':\xampp';
    if IsXamppAt(Candidate) then
    begin
      Result := Candidate;
      Exit;
    end;
  end;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\XAMPP', 'InstallLocation', Candidate) then
    if IsXamppAt(Candidate) then begin Result := Candidate; Exit; end;
  if RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\XAMPP', 'InstallLocation', Candidate) then
    if IsXamppAt(Candidate) then begin Result := Candidate; Exit; end;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\XAMPP', 'UninstallString', Uni) then
  begin
    Candidate := ExtractFilePath(Uni);
    if IsXamppAt(Candidate) then begin Result := Candidate; Exit; end;
  end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Apache Friends\XAMPP', 'InstallPath', Candidate) then
    if IsXamppAt(Candidate) then begin Result := Candidate; Exit; end;
end;

function InitializeSetup(): Boolean;
begin
  XamppDir := ProbeXamppDir();
  Result := True;
end;

procedure XamppInstallClick(Sender: TObject);
var
  Rc, Rc2, Capped: Integer;
begin
  Capped := Length(XamppDir);
  XamppButton.Enabled := False;
  { XAMPP's installer runs its bundled vcredist quietly WITHOUT /norestart,
    which reboots the PC before its Start Menu shortcuts are created.
    Pre-installing the same runtime (quiet, never reboot) makes that a no-op. }
  XamppStatus.Caption := 'Installing the Visual C++ runtime first - this does not restart the computer...';
  ExtractTemporaryFile('vc_redist.x64.exe');
  Exec(ExpandConstant('{tmp}\vc_redist.x64.exe'), '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, Rc2);
  XamppStatus.Caption := 'Starting the XAMPP installer - follow its prompts. This setup continues automatically when it finishes.';
  ExtractTemporaryFile('xampp-installer.exe');
  if Exec(ExpandConstant('{tmp}\xampp-installer.exe'), '', '', SW_SHOW, ewWaitUntilTerminated, Rc) then
    XamppDir := ProbeXamppDir()
  else
    MsgBox('Could not start the XAMPP installer.'#13#10 +
      'Check that vendor\xampp-installer.exe was bundled correctly.', mbError, MB_OK);
  { Insurance: cancel a reboot XAMPP's vcredist may have scheduled anyway. }
  Exec('shutdown.exe', '/a', '', SW_HIDE, ewNoWait, Rc2);
  if XamppDir <> '' then
    XamppStatus.Caption := 'XAMPP detected at ' + XamppDir + '. Click Next to continue installing the LMS.'
  else if Rc <> 0 then
    XamppStatus.Caption := 'The XAMPP installer was closed without finishing (code ' + IntToStr(Rc) + '). Click the button to try again.'
  else
    XamppStatus.Caption := 'XAMPP not detected yet. Click the button to run its installer again.';
  XamppButton.Enabled := True;
end;

procedure InitializeWizard();
begin
  XamppPage := CreateCustomPage(wpWelcome, 'XAMPP is required',
    'The LMS stores its data in MySQL, which is provided by XAMPP.');

  XamppStatus := TNewStaticText.Create(XamppPage);
  XamppStatus.Parent := XamppPage.Surface;
  XamppStatus.Left := 0;
  XamppStatus.Top := 0;
  XamppStatus.Width := XamppPage.SurfaceWidth;
  XamppStatus.WordWrap := True;
  XamppStatus.AutoSize := True;
  if XamppDir <> '' then
    XamppStatus.Caption := 'XAMPP was detected at ' + XamppDir + '.'
  else
    XamppStatus.Caption :=
      'XAMPP was not found on this PC.'#13#10#13#10 +
      'Click "Install XAMPP now" below - the official XAMPP setup will open (it is included with this installer, no internet needed). ' +
      'Once the XAMPP setup finishes, you return here and the LMS installation continues.'#13#10#13#10 +
      'If XAMPP is already installed in a non-standard location, you may click Next and configure the database later.';

  XamppButton := TButton.Create(XamppPage);
  XamppButton.Parent := XamppPage.Surface;
  XamppButton.Left := 0;
  XamppButton.Top := XamppStatus.Top + XamppStatus.Height + ScaleY(16);
  XamppButton.Width := ScaleX(170);
  XamppButton.Height := ScaleY(29);
  XamppButton.Caption := 'Install XAMPP now';
  XamppButton.OnClick := @XamppInstallClick;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = XamppPage.ID) and (XamppDir <> '');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = XamppPage.ID then
  begin
    XamppDir := ProbeXamppDir(); // user may have installed XAMPP meanwhile
    if XamppDir = '' then
      if MsgBox('XAMPP could not be detected.'#13#10#13#10 +
        'The LMS needs XAMPP''s MySQL to store data. Without it the app will show a database error on first launch.'#13#10#13#10 +
        'Install XAMPP anyway?', mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
  end;
end;

{ Runs after files are copied: prepare XAMPP auto-start + first-run .env.
  Never overwrites an existing .env (reinstall keeps settings). }
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir, BatPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    XamppDir := ProbeXamppDir(); // covers XAMPP installed during this run
    if XamppDir <> '' then
    begin
      { The app starts MySQL via <xampp>\mysql_start.bat (database.py);
        some XAMPP versions ship without it. }
      BatPath := AddBackslash(XamppDir) + 'mysql_start.bat';
      if not FileExists(BatPath) then
        SaveStringToFile(BatPath,
          '@echo off'#13#10 +
          'rem Created by the LMS installer - starts XAMPP MySQL for the LMS.'#13#10 +
          '"%~dp0mysql\bin\mysqld.exe" "--defaults-file=%~dp0mysql\bin\my.ini"'#13#10,
          False);
    end;
    DataDir := ExpandConstant('{localappdata}\LibraryManagementSystem');
    ForceDirectories(DataDir);
    if not FileExists(DataDir + '\.env') then
      FileCopy(ExpandConstant('{app}\env.template'), DataDir + '\.env', False);
  end;
end;
