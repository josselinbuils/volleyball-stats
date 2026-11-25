"""The machine kept from sleeping on its own while long work runs (the screen still free to), and whether it runs on
battery: a sleep would stop a job for good. Nothing to set: each system's own way, without admin rights.

- Windows: `SetThreadExecutionState`, held by this process's thread; under WSL2 the sleep is Windows', so a hidden
  `powershell.exe` holds it, telling whether Windows runs on battery, until this process stops reading it.
- macOS: `caffeinate -i`, bound to this process. Linux: `systemd-inhibit` when present.
"""

import ctypes
import functools
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from volleyball_stats.network import in_wsl

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
CHECK_S = 30
WHO, WHY = "Volleyball Stats", "Analyse en cours"
# GetSystemPowerStatus's flag for no battery; under WSL2, Windows asked once whether it has one.
NO_BATTERY = 128
HAS_BATTERY = "@(Get-CimInstance Win32_Battery).Count -gt 0"

# Holds Windows awake while a byte comes in at least every BEAT_S (a stopped job's own stop the beats too), its input
# open; after each, writes 1 on battery, else 0.
BEAT_S = 2.5 * CHECK_S
POWERSHELL = (
    "$ErrorActionPreference = 'Stop'; "
    "Add-Type -Namespace VolleyballStats -Name Power -MemberDefinition '"
    "[DllImport(\"kernel32.dll\")] public static extern uint SetThreadExecutionState(uint flags); "
    "[StructLayout(LayoutKind.Sequential)] public struct Status { public byte AC, Flag, Life, Reserved; public int Left, Full; } "
    "[DllImport(\"kernel32.dll\")] public static extern bool GetSystemPowerStatus(out Status status);'; "
    f"[VolleyballStats.Power]::SetThreadExecutionState([uint32]{ES_CONTINUOUS | ES_SYSTEM_REQUIRED}) | Out-Null; "
    "$s = New-Object VolleyballStats.Power+Status; $in = [Console]::OpenStandardInput(); $b = New-Object byte[] 1; "
    "do { [VolleyballStats.Power]::GetSystemPowerStatus([ref]$s) | Out-Null; "
    "[Console]::Out.WriteLine([int]($s.AC -eq 0)); [Console]::Out.Flush(); $read = $in.BeginRead($b, 0, 1, $null, $null) } "
    f"while ($read.AsyncWaitHandle.WaitOne({int(BEAT_S * 1000)}) -and $in.EndRead($read) -eq 1)"
)


def on_battery() -> bool | None:
    """Whether this machine runs on battery now; None when it cannot be told (under WSL2: Windows' tells)."""
    try:
        if sys.platform == "win32":
            return windows_battery()
        if sys.platform == "darwin":
            return "'Battery Power'" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=10).stdout
        supplies = list(Path("/sys/class/power_supply").glob("*"))
        if not supplies:
            return None
        return any((s / "type").read_text().strip() == "Battery" and (s / "status").read_text().strip() == "Discharging" for s in supplies if (s / "status").exists())
    except (OSError, subprocess.SubprocessError):
        return None


@functools.cache
def laptop() -> bool | None:
    """Whether this machine has a battery (a laptop, whose lid closing still sleeps it); None when it cannot be told."""
    try:
        if sys.platform == "win32":
            return windows_status().flag & NO_BATTERY == 0
        if in_wsl():
            if not shutil.which("powershell.exe"):
                return None
            said = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", HAS_BATTERY], capture_output=True, text=True, timeout=30).stdout.strip()
            return {"True": True, "False": False}.get(said)
        if sys.platform == "darwin":
            return "InternalBattery" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=10).stdout
        return any((s / "type").read_text().strip() == "Battery" for s in Path("/sys/class/power_supply").glob("*"))
    except (OSError, subprocess.SubprocessError):
        return None


class Status(ctypes.Structure):
    _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("life", ctypes.c_ubyte), ("reserved", ctypes.c_ubyte), ("left", ctypes.c_ulong), ("full", ctypes.c_ulong)]


def windows_status() -> Status:
    status = Status()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        raise OSError("GetSystemPowerStatus")
    return status


def windows_battery() -> bool:
    return windows_status().ac == 0


def holder() -> list[str] | None:
    """The command keeping the machine awake for as long as it runs, beside this process; None when this process holds
    it itself (Windows) or nothing can."""
    if sys.platform == "win32":
        return None
    if in_wsl():
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", POWERSHELL] if shutil.which("powershell.exe") else None
    if sys.platform == "darwin":
        return ["caffeinate", "-i", "-w", str(os.getpid())]
    if shutil.which("systemd-inhibit"):
        # `cat` ends when this process closes its input, or stops.
        return ["systemd-inhibit", "--what=idle:sleep", f"--who={WHO}", f"--why={WHY}", "--mode=block", "cat"]
    return None


@contextmanager
def held(battery: Callable[[bool], None] = lambda _: None, check_s: float = CHECK_S) -> Iterator[None]:
    """Keeps the machine from sleeping on its own inside the block; `battery` told whether it runs on battery, then each
    change. A system refusing leaves the work running as before."""
    stop, last = threading.Event(), [None]

    def tell(now: bool | None) -> None:
        if now is not None and now != last[0]:
            last[0] = now
            battery(now)

    def check() -> None:
        while True:
            tell(on_battery())
            if stop.wait(check_s):
                return

    command, process, watcher = holder(), None, None
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    if command:
        try:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE if in_wsl() else subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        except OSError:
            process = None
    if process and in_wsl():
        def beat() -> None:
            # A beat every check_s; the battery comes back after each.
            try:
                while not stop.wait(check_s):
                    process.stdin.write("\n")
                    process.stdin.flush()
            except (OSError, ValueError):
                pass

        threading.Thread(target=beat, daemon=True).start()
        watcher = threading.Thread(target=lambda: [tell(line.strip() == "1") for line in process.stdout if line.strip() in ("0", "1")], daemon=True)
    elif not in_wsl():
        watcher = threading.Thread(target=check, daemon=True)
    if watcher:
        watcher.start()
    try:
        yield
    finally:
        stop.set()
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        if process:
            # Its input closed, the holder ends by itself (under WSL2 only so: killed, its Windows side would stay).
            try:
                process.stdin.close()
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait()
