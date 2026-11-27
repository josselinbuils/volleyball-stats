; setup.exe: install.ps1 run with no admin rights, in its own window (its steps and uv's bars), the app opening at the end.
; Its uninstaller runs the installed install.ps1 to remove the app, asking whether the matches go too.
;
;   ISCC.exe /DVersion=1.2 packaging\windows\setup.iss    (Inno Setup 6.5 or later: GitHub's Windows runners have it)
;
; Its version is the release's tag, which the Installers workflow passes; "dev" built by hand without one.
;
; It changes rarely (SmartScreen's reputation is per file): the code comes from GitHub at install, then updates itself.

#define Name "Volleyball Stats"
#ifndef Version
  #define Version "dev"
#endif

[Setup]
AppId={{AA8FB1F0-2846-4A9B-BD8D-774F9FCE21B0}
AppName={#Name}
AppVersion={#Version}
AppPublisher=volleyball-stats
AppPublisherURL=https://github.com/josselinbuils/volleyball-stats
DefaultDirName={%USERPROFILE}\volleyball-stats
PrivilegesRequired=lowest
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
SetupIconFile=volleyball-stats.ico
UninstallDisplayIcon={app}\packaging\windows\volleyball-stats.ico
UninstallDisplayName={#Name}
WizardStyle=modern
OutputDir=dist
OutputBaseFilename=volleyball-stats-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
#if Ver >= EncodeVer(6, 7, 0)
; Inherited by install.ps1 when Setup is not elevated (never here): uv's links to its Python would be refused.
RedirectionGuard=no
#endif

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
fr.Installing=Installation de {#Name} : suivez son avancée dans la fenêtre qui s'ouvre.
en.Installing=Installing {#Name}: follow it in the window that opens.
fr.Failed=L'installation n'a pas abouti : la fenêtre en dit la raison. Relancez cette installation une fois réglé.
en.Failed=The installation did not finish: its window says why. Run this installation again once fixed.
fr.Matches=Supprimer aussi vos matchs (vidéos et statistiques) ?
en.Matches=Also delete your matches (videos and statistics)?

[Files]
Source: "..\..\install.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Code]
function Quoted(Text: String): String;
begin
  Result := Text;
  StringChangeEx(Result, '''', '''''', True);
  Result := '''' + Result + '''';
end;

{ install.ps1 in a PowerShell window, after Settings (its environment variables); its exit code. The 64-bit PowerShell
  (Setup is 32-bit: its own would make uv take a 32-bit Python, which has no torch). }
function RunScript(Script: String; Settings: String): Integer;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe'), '-NoProfile -ExecutionPolicy Bypass -Command "' + Settings + '$env:VOLLEYBALL_STATS_DIR = '
    + Quoted(ExpandConstant('{app}')) + '; iex (Get-Content -Raw -Encoding UTF8 -LiteralPath ' + Quoted(Script)
    + '); if ($VolleyballStatsFailed) { exit 1 }"', '', SW_SHOW, ewWaitUntilTerminated, Code);
  Result := Code;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := CustomMessage('Installing');
    if RunScript(ExpandConstant('{tmp}\install.ps1'), '$env:VOLLEYBALL_STATS_PAUSE = 1; ') <> 0 then
      SuppressibleMsgBox(CustomMessage('Failed'), mbError, MB_OK, IDOK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  What: String;
begin
  if (CurUninstallStep = usUninstall) and FileExists(ExpandConstant('{app}\install.ps1')) then
  begin
    What := '1';
    if not UninstallSilent and (MsgBox(CustomMessage('Matches'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      What := 'matches';
    RunScript(ExpandConstant('{app}\install.ps1'), '$env:VOLLEYBALL_STATS_UNINSTALL = ' + Quoted(What) + '; ');
  end;
end;
