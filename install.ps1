# Installs volleyball-stats on Windows, then starts it; run again, it only starts it.
#
#   irm https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.ps1 | iex
#
# No admin rights, no git: uv (its own installer), the code from GitHub's archive (updates.py), the libraries, ffmpeg
# and the models (Diagnostics' download), the launcher, then the app, which puts its shortcut on the desktop and in the
# Start menu. setup.exe (packaging/windows) runs it. VOLLEYBALL_STATS_DIR: the folder (else ~\volleyball-stats);
# VOLLEYBALL_STATS_UNINSTALL=1 removes the app, =matches the matches too; VOLLEYBALL_STATS_PAUSE=1 waits for Enter on a
# failure (setup.exe's window would close on it). A failure sets $VolleyballStatsFailed (`exit` would close the window
# of a PowerShell it was pasted in).
#
# Windows PowerShell 5.1 runs it: no `??`, no `&&`, native commands' failures checked by their exit code. Run in its own
# scope: `iex` would leave its settings in the caller's session.

$global:VolleyballStatsFailed = $false
& {
  $ErrorActionPreference = 'Stop'
  # Invoke-WebRequest's own bar makes it many times slower.
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  $raw = 'https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main'
  $fr = (Get-UICulture).TwoLetterISOLanguageName -eq 'fr'
  $name = 'Volleyball Stats'

  function Say($inFrench, $inEnglish) {
    Write-Host ''
    Write-Host $(if ($fr) { $inFrench } else { $inEnglish }) -ForegroundColor Cyan
  }

  function Check($what) {
    if ($LASTEXITCODE) { throw "$what (exit $LASTEXITCODE)" }
  }

  function Remove($path) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Continue }
  }

  # A launcher's path, under the user's folder through %USERPROFILE%: cmd reads a .cmd in the console's code page.
  function InCmd($path) {
    if ($path.StartsWith($HOME, [StringComparison]::OrdinalIgnoreCase)) { return '%USERPROFILE%' + $path.Substring($HOME.Length) }
    return $path
  }

  $dir = if ($env:VOLLEYBALL_STATS_DIR) { $env:VOLLEYBALL_STATS_DIR } else { Join-Path $HOME 'volleyball-stats' }
  $bin = Join-Path $HOME '.local\bin'
  $launcher = Join-Path $bin 'volleyball-stats.cmd'
  $found = Get-Command uv -ErrorAction SilentlyContinue
  $uv = if ($found) { $found.Source } else { Join-Path $bin 'uv.exe' }

  try {
    # uv takes a Python of the process's kind: a 32-bit one has no torch.
    if ([Environment]::Is64BitOperatingSystem -and -not [Environment]::Is64BitProcess) {
      throw $(if ($fr) { 'ouvrez Windows PowerShell, pas sa version (x86)' } else { 'open Windows PowerShell, not its (x86) version' })
    }
    if ($env:VOLLEYBALL_STATS_UNINSTALL) {
      Say "Désinstallation de $name…" "Uninstalling $name…"
      if ((Test-Path -LiteralPath $uv) -and (Test-Path -LiteralPath "$dir\pyproject.toml")) {
        Push-Location $dir
        # 5.1 throws on a native command's stderr redirected under 'Stop'.
        try { & $uv run --no-sync stats stop 2>$null | Out-Null } catch {}
        Pop-Location
      }
      foreach ($folder in 'Desktop', 'Programs', 'LocalApplicationData') {
        $at = [Environment]::GetFolderPath($folder)
        if ($at) { Remove (Join-Path $at $(if ($folder -eq 'LocalApplicationData') { $name } else { "$name.lnk" })) }
      }
      Remove $launcher
      Remove (Join-Path $HOME '.local\share\volleyball-stats')
      Remove "$dir\.venv"
      Remove "$dir\models"
      $installed = "$dir\.install.json"
      if (Test-Path -LiteralPath $installed) {
        foreach ($file in (Get-Content -Raw -Encoding UTF8 -LiteralPath $installed | ConvertFrom-Json).files) { Remove (Join-Path $dir $file) }
        Remove $installed
        Get-ChildItem -LiteralPath $dir -Directory -Recurse -Filter __pycache__ | ForEach-Object { Remove $_.FullName }
        Get-ChildItem -LiteralPath $dir -Directory -Recurse | Sort-Object { $_.FullName.Length } -Descending |
          Where-Object { -not (Get-ChildItem -LiteralPath $_.FullName -Force) } | ForEach-Object { Remove $_.FullName }
      }
      if ($env:VOLLEYBALL_STATS_UNINSTALL -eq 'matches') {
        Remove "$dir\outputs"
        Remove "$dir\data"
      }
      return
    }

    if (-not (Test-Path -LiteralPath $uv)) {
      Say 'Installation de uv…' 'Installing uv…'
      powershell.exe -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
      Check 'uv'
    }

    if (-not (Test-Path -LiteralPath "$dir\.git") -and -not (Test-Path -LiteralPath "$dir\.install.json")) {
      Say "Téléchargement de $name…" "Downloading $name…"
      $work = Join-Path ([IO.Path]::GetTempPath()) ('volleyball-stats-' + [guid]::NewGuid())
      New-Item -ItemType Directory $work | Out-Null
      Invoke-WebRequest "$raw/src/volleyball_stats/updates.py" -OutFile "$work\updates.py" -UseBasicParsing
      Push-Location $work
      & $uv run --no-project --with certifi --python 3.12 -- python -I "$work\updates.py" install $dir
      Check 'download'
      Pop-Location
      Remove $work
    }

    Set-Location -LiteralPath $dir
    Say 'Installation des bibliothèques : la première fois, de longues minutes…' 'Installing the libraries: the first time, many minutes…'
    & $uv sync
    Check 'uv sync'
    Say 'Téléchargement de ffmpeg et des modèles…' 'Downloading ffmpeg and the models…'
    & $uv run python -m volleyball_stats.doctor --models
    Check 'models'

    New-Item -ItemType Directory -Force $bin | Out-Null
    $text = "@echo off`r`ncd /d `"$(InCmd $dir)`"`r`n`"$(InCmd $uv)`" run stats %*`r`n"
    [IO.File]::WriteAllText($launcher, $text, (New-Object Text.UTF8Encoding $false))

    Say "Ouverture de $name : la prochaine fois, son raccourci sur le bureau." "Opening ${name}: next time, its shortcut on the desktop."
    # As its shortcut starts it: no window but the app's.
    Start-Process -FilePath "$env:SystemRoot\System32\conhost.exe" -ArgumentList "--headless cmd.exe /c `"$launcher`""
  } catch {
    Write-Host ''
    Write-Host $(if ($fr) { "L'installation a échoué : $_" } else { "The installation failed: $_" }) -ForegroundColor Red
    if ($env:VOLLEYBALL_STATS_PAUSE) { Read-Host $(if ($fr) { 'Entrée pour fermer' } else { 'Enter to close' }) | Out-Null }
    $global:VolleyballStatsFailed = $true
  }
}
