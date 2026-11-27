"""The app's shortcut, opening it with no terminal: Windows' (desktop and Start menu, the app on Windows or in WSL2), a Mac's app
(the .dmg's dragged to Applications, else one in the user's Applications), Linux's applications menu, its icon in the
club's colours (icon.py). Made again by the app's start and the club's changes when its VERSION or colours change, in place of the older ones (a .bat, a .command),
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
VERSION = 5
# install.sh's, or on Windows the installer's (`uv run stats` in the code's folder).
LAUNCHER = Path.home() / (".local/bin/volleyball-stats.cmd" if os.name == "nt" else ".local/bin/volleyball-stats")
MADE = Path.home() / ".local/share/volleyball-stats/shortcut"
BUNDLE_ID = "io.github.josselinbuils.volleyball-stats"
APPLICATIONS = Path("/Applications")
# The Mac app's program and description (packaging/macos/app.sh), and the key giving it the launcher.
MAC = Path(__file__).resolve().parents[2] / "packaging/macos"
LAUNCHER_KEY = "VSLauncher"
ONE_AT_A_TIME = threading.Lock()


def ps_quote(text: str) -> str:
    """`text` as a PowerShell literal."""
    return "'" + text.replace("'", "''") + "'"


def windows_command(distro: str | None, launcher: Path) -> tuple[str, str]:
    """The program and arguments a Windows shortcut starts: the launcher, in `distro` under WSL2, under a console that
    shows no window (the app is in the browser, Quitter stops it)."""
    if distro is None:
        return "conhost.exe", f'--headless cmd.exe /c "{launcher}"'
    return "conhost.exe", f'--headless wsl.exe -d {distro} -- "{launcher}"'


def native() -> bool:
    return doctor.system() == "windows"


def local_path(windows: str) -> Path:
    """A Windows path as this process reads it."""
    return Path(windows) if native() else wsl_path(windows)


def icon_name(pair: tuple[str, str], suffix: str) -> str:
    """Named after its colours: Windows and desktops keep a file's icon cached by its path."""
    return f"volleyball-stats-{pair[0][1:]}-{pair[1][1:]}{suffix}"


def make_windows(pair: tuple[str, str]) -> list[Path]:
    """The shortcut on Windows' desktop and in its Start menu, its icon copied beside Windows' apps' data."""
    distro = None if native() else os.environ.get("WSL_DISTRO_NAME")
    if not distro and not native():
        return []
    script = "foreach ($f in 'Desktop', 'Programs', 'LocalApplicationData') { [Environment]::GetFolderPath($f) }; $env:SystemRoot"
    found = run_powershell(script).splitlines()
    if len(found) != 4 or not all(found):
        return []
    desktop, programs, local, root = found
    icon_dir = local_path(local) / NAME
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
    old = local_path(desktop) / f"{NAME}.bat"
    old.unlink(missing_ok=True)
    return [local_path(link) for link in links if local_path(link).exists()]


def run_powershell(script: str) -> str:
    """What `script` prints, from Windows' PowerShell."""
    done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], cwd=None if native() else "/mnt/c", capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60, encoding="utf-8", errors="replace")
    return done.stdout.replace("\r", "").strip()


def wsl_path(windows: str) -> Path:
    return Path(subprocess.run(["wslpath", "-u", windows], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip())


def info_plist(before: dict | None = None) -> bytes:
    """The Mac app's description (packaging/macos's), with the launcher it starts and the version of the app it
    replaces (`before`'s: the .dmg's release)."""
    info = plistlib.loads((MAC / "Info.plist").read_bytes())
    kept = {key: (before or {})[key] for key in ("CFBundleShortVersionString", "CFBundleVersion") if key in (before or {})}
    return plistlib.dumps({**info, **kept, LAUNCHER_KEY: str(LAUNCHER)})


def ours(app: Path) -> bool:
    try:
        return plistlib.loads((app / "Contents/Info.plist").read_bytes()).get("CFBundleIdentifier", "").startswith(BUNDLE_ID)
    except (OSError, plistlib.InvalidFileException):
        return False


def unquarantined(app: Path) -> bool:
    """Whether `app` has no quarantine left, removed if needed: macOS would call a quarantined app changed damaged."""
    subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(app)], capture_output=True)
    return subprocess.run(["/usr/bin/xattr", "-p", "com.apple.quarantine", str(app)], capture_output=True).returncode != 0


def mac_app() -> Path | None:
    """The Mac app this module made, which opens the app in its window: None elsewhere or before it was made."""
    if doctor.system() != "mac":
        return None
    for app in (APPLICATIONS / f"{NAME}.app", Path.home() / "Applications" / f"{NAME}.app"):
        try:
            if LAUNCHER_KEY in plistlib.loads((app / "Contents/Info.plist").read_bytes()):
                return app
        except (OSError, plistlib.InvalidFileException):
            continue
    return None


def make_mac(pair: tuple[str, str]) -> list[Path]:
    """`Volleyball Stats.app` (app.swift): the .dmg's in Applications made the shortcut, else one in the user's
    Applications (Launchpad, Spotlight); those made before elsewhere (the desktop) removed."""
    home = Path.home()
    dragged = APPLICATIONS / f"{NAME}.app"
    app = dragged if dragged.is_dir() and os.access(dragged / "Contents", os.W_OK) else home / "Applications" / f"{NAME}.app"
    if app == dragged and not unquarantined(app):
        return []
    for old in (home / "Applications" / f"{NAME}.app", home / "Desktop" / f"{NAME}.app"):
        if old != app and ours(old):
            shutil.rmtree(old, ignore_errors=True)
    (home / "Desktop" / f"{NAME}.command").unlink(missing_ok=True)
    # Written in place, the app possibly running: the .dmg's signature and installer gone, its program replaced by a
    # new file when it changed (a running program's file rewritten would kill it).
    shutil.rmtree(app / "Contents/_CodeSignature", ignore_errors=True)
    (app / "Contents/Resources/install.sh").unlink(missing_ok=True)
    (app / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
    (app / "Contents/Resources").mkdir(exist_ok=True)
    try:
        before = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    except (OSError, plistlib.InvalidFileException):
        before = None
    (app / "Contents/Info.plist").write_bytes(info_plist(before))
    icon.write(pair, app / "Contents/Resources/volleyball-stats.icns")
    program, built = app / "Contents/MacOS/volleyball-stats", (MAC / "volleyball-stats").read_bytes()
    if not program.exists() or program.read_bytes() != built:
        fresh = program.with_name(".volleyball-stats")
        fresh.write_bytes(built)
        fresh.chmod(0o755)
        os.replace(fresh, program)
    # Finder and the Dock keep an app's icon until it changes.
    os.utime(app)
    return [app]


def desktop_entry(picture: Path) -> str:
    return f'[Desktop Entry]\nType=Application\nName={NAME}\nExec="{LAUNCHER}"\nIcon={picture}\nTerminal=false\nCategories=Sports;Video;\n'


def make_linux(pair: tuple[str, str]) -> list[Path]:
    """The entry in the applications menu, its icon beside the record of what was made."""
    for old in MADE.parent.glob("volleyball-stats*.png"):
        old.unlink()
    picture = icon.write(pair, MADE.parent / icon_name(pair, ".png"))
    entry = Path.home() / ".local/share/applications/volleyball-stats.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(desktop_entry(picture), encoding="utf-8")
    return [entry]


def update_launcher() -> None:
    """install.sh's launcher of before `stats`, made to start it."""
    try:
        text = LAUNCHER.read_text(encoding="utf-8")
    except OSError:
        return
    if " run volleyball-stats " in text:
        LAUNCHER.write_text(text.replace(" run volleyball-stats ", " run stats "), encoding="utf-8")


def key(pair: tuple[str, str]) -> str:
    return f"{VERSION} {pair[0]} {pair[1]}"


def make(pair: tuple[str, str] | None = None) -> list[Path]:
    """This machine's shortcut made again, in the club's colours unless `pair`; where it went, none without the
    launcher."""
    if not LAUNCHER.exists():
        return []
    pair = pair or icon.colours(club_settings.read())
    with ONE_AT_A_TIME:
        made = {"wsl": make_windows, "windows": make_windows, "mac": make_mac, "linux": make_linux}[doctor.system()](pair)
        if made:
            MADE.parent.mkdir(parents=True, exist_ok=True)
            MADE.write_text(key(pair), encoding="utf-8")
    return made


def made(pair: tuple[str, str]) -> bool:
    try:
        return MADE.read_text(encoding="utf-8").strip() == key(pair)
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
