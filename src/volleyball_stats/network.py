"""The review on the local network: off by default, the app's "Réseau local" switches it for as long as the review runs
(SESSION, which the server's restarts inherit), at every start only when asked (`always`, outputs/network.json, this
machine's own: the owner's call, 16 Nov). On, the server listens on every address and takes requests named by an IP address, a `.local` name or
this machine's name, besides 127.0.0.1 and localhost; no code (the owner's call, 16 Nov: a home network). Under WSL the
network reaches it only once WSL shares the computer's address (`networkingMode=mirrored`) and WSL's firewall lets the
port in: `configure_windows` sets both, an administrator's approval asked once.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import subprocess
from pathlib import Path

from volleyball_stats import files

FILE = "network.json"
# Set by the switch in the server's environment: its own restarts (another match opened, the app updated) keep it, a new
# start of the app does not.
SESSION = "VOLLEYBALL_STATS_LAN"
# WSL's own firewall (Hyper-V's) knows its virtual machine by this id.
WSL_VM = "{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}"
RULE = "volleyball-stats-review"


def always(outputs: Path) -> bool:
    """Whether the review listens on the local network from every start."""
    path = outputs / FILE
    try:
        return bool(json.loads(path.read_text()).get("always")) if path.exists() else False
    except (OSError, ValueError):
        return False


def shared(outputs: Path) -> bool:
    """Whether the review listens on the local network: switched so while it runs, else from every start."""
    said = os.environ.get(SESSION)
    return said == "1" if said in ("0", "1") else always(outputs)


def share(outputs: Path, on: bool) -> None:
    """The review on the local network until it closes (the server, starting again, takes it), or no longer; off, not at
    the next starts either."""
    os.environ[SESSION] = "1" if on else "0"
    if not on:
        keep(outputs, False)


def keep(outputs: Path, on: bool) -> None:
    """The review on the local network from every start, or only when switched."""
    files.write_text(outputs / FILE, json.dumps({"always": bool(on)}) + "\n")


def bind(outputs: Path) -> str:
    """The address the server listens on."""
    return "0.0.0.0" if shared(outputs) else "127.0.0.1"


def named_here(host: str, port: int, lan: bool) -> bool:
    """Whether a request's Host names this server: 127.0.0.1 or localhost, and with `lan` an IP address, a `.local` name or
    this machine's name. Not any name: a site rebinding its own domain to this machine would name it."""
    name, _, given = host.rpartition(":")
    if given != str(port) or not name:
        return False
    if name in ("127.0.0.1", "localhost"):
        return True
    if not lan:
        return False
    try:
        ipaddress.ip_address(name.strip("[]"))
        return True
    except ValueError:
        return name.lower().endswith(".local") or name.lower() == socket.gethostname().lower()


def address() -> str | None:
    """This machine's address on the local network (the one its traffic leaves by), None without a network. No packet is
    sent: a UDP socket only picks its route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.254.254.254", 1))
            found = probe.getsockname()[0]
    except OSError:
        return None
    return None if found.startswith("127.") else found


def in_wsl() -> bool:
    return "microsoft" in os.uname().release.lower() if hasattr(os, "uname") else False


def wsl_mode() -> str | None:
    """WSL's networking mode ("nat", "mirrored"...), None outside WSL or when it cannot be told."""
    if not in_wsl():
        return None
    try:
        return subprocess.run(["wslinfo", "--networking-mode"], capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def wsl_config() -> Path | None:
    """The Windows user's .wslconfig, through WSL's view of the C: drive; None when it cannot be found."""
    try:
        profile = subprocess.run(["cmd.exe", "/c", "echo %USERPROFILE%"], capture_output=True, text=True, timeout=10, cwd="/mnt/c").stdout.strip()
        found = subprocess.run(["wslpath", "-u", profile], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(found) / ".wslconfig" if found else None


def mirrored_config(text: str) -> str:
    """`text`, a .wslconfig, with `networkingMode=mirrored` under [wsl2] (Windows line ends kept)."""
    end = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    out, section, done = [], None, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if section == "wsl2" and not done:
                # At the section's end, before the blank lines parting it from the next.
                out.insert(len(out) - next((k for k, kept in enumerate(reversed(out)) if kept.strip()), 0), "networkingMode=mirrored")
                done = True
            section = stripped[1:-1].strip().lower()
        elif section == "wsl2" and stripped.split("=")[0].strip().lower() == "networkingmode":
            if not done:
                out.append("networkingMode=mirrored")
                done = True
            continue
        out.append(line)
    if not done:
        if section != "wsl2":
            out += (["", "[wsl2]"] if out else ["[wsl2]"])
        out.append("networkingMode=mirrored")
    return end.join(out) + end


def configure_windows(port: int) -> None:
    """WSL set to share the computer's address (.wslconfig, its old copy kept beside it as .wslconfig.bak) and WSL's
    firewall letting `port` in, through a PowerShell Windows asks an administrator's approval for. WSL takes the first
    at its next start. OSError when it cannot be done."""
    path = wsl_config()
    if path is None:
        raise OSError("no .wslconfig found")
    text = path.read_text() if path.exists() else ""
    if text:
        files.write_text(path.with_name(".wslconfig.bak"), text)
    files.write_text(path, mirrored_config(text))
    rule = (
        f"Remove-NetFirewallHyperVRule -Name {RULE} -ErrorAction SilentlyContinue; "
        f"New-NetFirewallHyperVRule -Name {RULE} -DisplayName 'Volleyball stats review' -Direction Inbound "
        f"-VMCreatorId '{WSL_VM}' -Protocol TCP -LocalPorts {int(port)} -Action Allow"
    )
    run = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile','-Command',\"{rule}\""],
        capture_output=True, text=True, timeout=300,
    )
    if run.returncode:
        raise OSError(run.stderr.strip() or "the firewall rule was not added")


def state(outputs: Path, port: int) -> dict:
    """What the app's "Réseau local" shows: whether it is on, the address to type elsewhere, and under WSL whether
    Windows still has to be set up (`windows`: "mirrored" when done, else the mode WSL is in)."""
    found = address()
    mode = wsl_mode()
    return {
        "lan": shared(outputs),
        "always": always(outputs),
        "url": f"http://{found}:{port}/" if found and (mode in (None, "mirrored")) else None,
        "wsl": mode,
    }
