"""Processes, the same on every system: whether one runs and is the one started then, its priority, the machine's load,
a process started apart from this one (outliving it) and stopped with what it started, the command lines running.
POSIX through `os` and `ps`; Windows through its API (`ctypes`) and PowerShell, where `os.kill(pid, 0)` would send
Ctrl+C to the whole console and `os.nice`, `os.getloadavg` and `ps` do not exist."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

WINDOWS = sys.platform == "win32"
# OpenProcess's right to ask a process's state; GetExitCodeProcess's code of one still running.
QUERY_LIMITED, STILL_ACTIVE = 0x1000, 259
ACCESS_DENIED = 5
# Windows' priority classes as the nice value they stand for.
PRIORITY_NICE = {0x40: 19, 0x4000: 10, 0x20: 0, 0x8000: -5, 0x80: -10, 0x100: -20}
# CreateProcess's flags: a group of its own (no Ctrl+C from this console), a console of its own never shown (the
# commands it starts share it, none opening a window), out of this process's job (uv's, which ends its processes with it).
NEW_PROCESS_GROUP, NO_WINDOW, BREAKAWAY_FROM_JOB = 0x200, 0x08000000, 0x01000000
# How long the machine's load is measured on Windows, which keeps no load average.
LOAD_SAMPLE_S = 0.5


def kernel32():
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.GetProcessTimes.argtypes = [wintypes.HANDLE, *[ctypes.POINTER(ctypes.c_ulonglong)] * 4]
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.GetPriorityClass.argtypes = [wintypes.HANDLE]
    k.GetSystemTimes.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)] * 3
    return k


def windows_state(pid: int) -> tuple[bool, int | None]:
    """Whether the process `pid` runs, and its creation time (Windows' ticks) when it can be asked."""
    import ctypes
    from ctypes import wintypes

    k = kernel32()
    handle = k.OpenProcess(QUERY_LIMITED, False, pid)
    if not handle:
        # Another user's process, denied: it runs.
        return ctypes.get_last_error() == ACCESS_DENIED, None
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False, None
        times = [ctypes.c_ulonglong() for _ in range(4)]
        created = times[0].value if k.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]) else None
        return code.value == STILL_ACTIVE, created
    finally:
        k.CloseHandle(handle)


def exists(pid: int) -> bool:
    """Whether a process `pid` runs (or is a zombie not waited for yet, on POSIX)."""
    if pid <= 0:
        return False
    if WINDOWS:
        return windows_state(pid)[0]
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def ended_child(pid: int) -> bool:
    """Whether `pid` is a child of this process that ended, a zombie until waited for (POSIX only)."""
    if WINDOWS:
        return False
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
        return bool(done)
    except ChildProcessError:
        return False


def key(pid: int) -> str | None:
    """Where the system tells it, the process `pid` exactly, which no clock change moves: on Linux the boot's id and
    its start in ticks since the boot, on Windows its creation time; None elsewhere (macOS)."""
    if WINDOWS:
        running, created = windows_state(pid)
        return f"windows:{created}" if running and created else None
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
        ticks = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None
    return f"{boot}:{ticks}"


def started(pid: int) -> str | None:
    """When the process `pid` started, as `ps` tells it (POSIX); None on Windows, whose `key` is exact."""
    if WINDOWS:
        return None
    try:
        found = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace").stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return found or None


def priority() -> int:
    """This process's priority as a nice value: above 0, below the normal one (zsh's background jobs, Windows' "below
    normal"), which the processes it starts inherit."""
    if WINDOWS:
        k = kernel32()
        return PRIORITY_NICE.get(k.GetPriorityClass(k.GetCurrentProcess()), 0)
    return os.nice(0)


def total_memory() -> int | None:
    """The machine's memory in bytes, None when it cannot be told."""
    if WINDOWS:
        import ctypes
        from ctypes import wintypes

        class Status(ctypes.Structure):
            _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD), *[(name, ctypes.c_ulonglong) for name in ("total", "free", "page", "page_free", "virtual", "virtual_free", "extended")]]

        status = Status(length=ctypes.sizeof(Status))
        return status.total if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def system_times() -> tuple[int, int]:
    """Windows' idle and total CPU time since its start, in ticks summed over the cores."""
    import ctypes

    idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
    kernel32().GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    # The kernel's time counts the idle time.
    return idle.value, kernel.value + user.value


def load() -> float:
    """The machine's load, as the number of cores kept busy: the last minute's average on POSIX, the busy share of
    every core over LOAD_SAMPLE_S on Windows."""
    if not WINDOWS:
        return os.getloadavg()[0]
    idle, total = system_times()
    time.sleep(LOAD_SAMPLE_S)
    idle2, total2 = system_times()
    spent = total2 - total
    return (1 - (idle2 - idle) / spent) * (os.cpu_count() or 1) if spent > 0 else 0.0


def apart() -> dict:
    """Popen's options for a process that outlives this one, out of its console's Ctrl+C and of its group's end."""
    if WINDOWS:
        return {"creationflags": NEW_PROCESS_GROUP | NO_WINDOW | BREAKAWAY_FROM_JOB}
    return {"start_new_session": True}


def start_apart(command: list[str], **options) -> subprocess.Popen:
    """`command` started `apart`; on Windows, inside this process's job when that job lets none out."""
    try:
        return subprocess.Popen(command, **options, **apart())
    except PermissionError:
        if not WINDOWS:
            raise
        return subprocess.Popen(command, **options, creationflags=NEW_PROCESS_GROUP | NO_WINDOW)


def stop_tree(pid: int) -> None:
    """Stops the process `pid` started `apart` and every process it started."""
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def powershell(script: str, timeout: float = 30) -> str:
    """What `script` prints, from Windows' PowerShell (its output as UTF-8)."""
    done = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script],
        capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    return done.stdout.decode("utf-8", "replace").replace("\r", "")


def command_lines() -> list[str]:
    """The command lines of the processes running on this machine."""
    try:
        if WINDOWS:
            return [line for line in powershell("Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }").splitlines() if line.strip()]
        return subprocess.run(["ps", "-Ao", "command="], capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace").stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


def busiest(count: int = 5) -> list[str]:
    """The processes using the most CPU now, as "12.3% name"."""
    try:
        if WINDOWS:
            # Per core, as `ps` tells it; the idle and the total left out.
            script = (
                "Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object { $_.Name -notin '_Total', 'Idle' } | "
                "ForEach-Object { \"$($_.PercentProcessorTime) $($_.Name)\" }"
            )
            lines = powershell(script).splitlines()
        else:
            lines = subprocess.run(["ps", "-Ao", "pcpu=,comm="], capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace").stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []
    rows = [line.split(None, 1) for line in lines if len(line.split(None, 1)) == 2]
    rows = [(float(cpu.replace(",", ".")), name.strip()) for cpu, name in rows if cpu.replace(",", ".").replace(".", "", 1).isdigit()]
    return [f"{cpu:g}% {Path(name).name}" for cpu, name in sorted(rows, key=lambda r: -r[0])[:count]]
