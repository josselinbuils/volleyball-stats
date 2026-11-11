"""The app's shortcut, opening it with no terminal: under WSL2 Windows' (desktop and Start menu), a Mac's app
(Applications and desktop), Linux's applications menu, its icon in the club's colours (icon.py). Made again by the
app's start and the club's changes when its VERSION or colours change, in place of the older ones (a .bat, a .command),
when install.sh's launcher is there.

    uv run python -m volleyball_stats.shortcut
"""

import os
import plistlib
import shutil
import subprocess
import threading
from pathlib import Path

from volleyball_stats import club_settings, doctor, icon

NAME = "Volleyball Stats"
# Bumped when the shortcut changes: each machine's is made again once.
VERSION = 3
LAUNCHER = Path.home() / ".local/bin/volleyball-stats"
MADE = Path.home() / ".local/share/volleyball-stats/shortcut"
BUNDLE_ID = "io.github.josselinbuils.volleyball-stats"
ONE_AT_A_TIME = threading.Lock()


def ps_quote(text: str) -> str:
    """`text` as a PowerShell literal."""
    return "'" + text.replace("'", "''") + "'"


def windows_command(distro: str, launcher: Path) -> tuple[str, str]:
    """The program and arguments a Windows shortcut starts: the launcher in `distro`, under a console that shows no
    window (the app is in the browser, Quitter stops it)."""
    return "conhost.exe", f'--headless wsl.exe -d {distro} -- "{launcher}"'


def icon_name(pair: tuple[str, str], suffix: str) -> str:
    """Named after its colours: Windows and desktops keep a file's icon cached by its path."""
    return f"volleyball-stats-{pair[0][1:]}-{pair[1][1:]}{suffix}"


def make_windows(pair: tuple[str, str]) -> list[Path]:
    """The shortcut on Windows' desktop and in its Start menu, its icon copied beside Windows' apps' data."""
    distro = os.environ.get("WSL_DISTRO_NAME")
    if not distro:
        return []
    script = "foreach ($f in 'Desktop', 'Programs', 'LocalApplicationData') { [Environment]::GetFolderPath($f) }; $env:SystemRoot"
    found = run_powershell(script).splitlines()
    if len(found) != 4 or not all(found):
        return []
    desktop, programs, local, root = found
    icon_dir = wsl_path(local) / NAME
    for old in icon_dir.glob("volleyball-stats*.ico"):
        old.unlink()
    icon.write(pair, icon_dir / icon_name(pair, ".ico"))
    program, arguments = windows_command(distro, LAUNCHER)
    target, picture = f"{root}\\System32\\{program}", f"{local}\\{NAME}\\{icon_name(pair, '.ico')}"
    links = [f"{desktop}\\{NAME}.lnk", f"{programs}\\{NAME}.lnk"]
    run_powershell(
        "$shell = New-Object -ComObject WScript.Shell\n"
        + "".join(
            f"$s = $shell.CreateShortcut({ps_quote(link)}); $s.TargetPath = {ps_quote(target)}; $s.Arguments = {ps_quote(arguments)}; "
            f"$s.IconLocation = {ps_quote(picture)}; $s.Description = {ps_quote(NAME)}; $s.Save()\n"
            for link in links
        )
    )
    old = wsl_path(desktop) / f"{NAME}.bat"
    old.unlink(missing_ok=True)
    return [wsl_path(link) for link in links if wsl_path(link).exists()]


def run_powershell(script: str) -> str:
    """What `script` prints, from Windows' PowerShell."""
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], cwd="/mnt/c", capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    return done.stdout.replace("\r", "").strip()


def wsl_path(windows: str) -> Path:
    return Path(subprocess.run(["wslpath", "-u", windows], capture_output=True, text=True).stdout.strip())


def info_plist() -> bytes:
    """A Mac app's description: no Dock icon of its own, the page being in the browser."""
    return plistlib.dumps(
        {
            "CFBundleName": NAME,
            "CFBundleDisplayName": NAME,
            "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleExecutable": "volleyball-stats",
            "CFBundleIconFile": "volleyball-stats",
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": "1.0",
            "LSUIElement": True,
        }
    )


def make_mac(pair: tuple[str, str]) -> list[Path]:
    """`Volleyball Stats.app` in the user's Applications (Launchpad, Spotlight) and on the desktop."""
    home = Path.home()
    made = []
    for folder in (home / "Applications", home / "Desktop"):
        if folder.name == "Desktop" and not folder.is_dir():
            continue
        app = folder / f"{NAME}.app"
        shutil.rmtree(app, ignore_errors=True)
        (app / "Contents/MacOS").mkdir(parents=True)
        (app / "Contents/Resources").mkdir()
        (app / "Contents/Info.plist").write_bytes(info_plist())
        icon.write(pair, app / "Contents/Resources/volleyball-stats.icns")
        program = app / "Contents/MacOS/volleyball-stats"
        program.write_text(f'#!/bin/sh\nexec "{LAUNCHER}"\n')
        program.chmod(0o755)
        made.append(app)
    (home / "Desktop" / f"{NAME}.command").unlink(missing_ok=True)
    return made


def desktop_entry(picture: Path) -> str:
    return f'[Desktop Entry]\nType=Application\nName={NAME}\nExec="{LAUNCHER}"\nIcon={picture}\nTerminal=false\nCategories=Sports;Video;\n'


def make_linux(pair: tuple[str, str]) -> list[Path]:
    """The entry in the applications menu, its icon beside the record of what was made."""
    for old in MADE.parent.glob("volleyball-stats*.png"):
        old.unlink()
    picture = icon.write(pair, MADE.parent / icon_name(pair, ".png"))
    entry = Path.home() / ".local/share/applications/volleyball-stats.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(desktop_entry(picture))
    return [entry]


def key(pair: tuple[str, str]) -> str:
    return f"{VERSION} {pair[0]} {pair[1]}"


def make(pair: tuple[str, str] | None = None) -> list[Path]:
    """This machine's shortcut made again, in the club's colours unless `pair`; where it went, none without the
    launcher."""
    if not LAUNCHER.exists():
        return []
    pair = pair or icon.colours(club_settings.read())
    with ONE_AT_A_TIME:
        made = {"wsl": make_windows, "mac": make_mac, "linux": make_linux}[doctor.system()](pair)
        if made:
            MADE.parent.mkdir(parents=True, exist_ok=True)
            MADE.write_text(key(pair))
    return made


def made(pair: tuple[str, str]) -> bool:
    try:
        return MADE.read_text().strip() == key(pair)
    except OSError:
        return False


def refresh() -> None:
    """At the app's start and on the club's changes: the shortcut made again, aside, unless it is as it should be."""
    if not LAUNCHER.exists():
        return
    pair = icon.colours(club_settings.read())
    if not made(pair):
        threading.Thread(target=lambda: _quietly(lambda: make(pair)), daemon=True).start()


def _quietly(action) -> None:
    try:
        action()
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Shortcut not made: {error}", flush=True)


if __name__ == "__main__":
    for path in make():
        print(path)
