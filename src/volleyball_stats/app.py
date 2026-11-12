"""The app: the one command to start, everything else in the browser.

    uv run stats [MATCH] [--port PORT]           the app in a window of its own (the shortcut's), stopped with it
    uv run stats browser [MATCH] [--port PORT]   the app in a browser tab
    uv run stats server [MATCH] [--port PORT]    the app, opening nothing (a restart: the page is open)
    uv run stats stop [--port PORT]              stops it

Opens the list of the matches (the review server, review.py), or MATCH's review, and serves under /app/ what used to
need a command: checking the machine (doctor.py), importing a match from the camera's card, mapping the court,
running the pipeline, the videos between two machines and updating the code. The long work runs in jobs (jobs.py),
which outlive the server.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs

from volleyball_stats import backup, club_settings, doctor, files, git_check, jobs, presence, server, shortcut, sync

DATA = Path("data/matches")
OUTPUTS = Path("outputs")
MATCHES = OUTPUTS / "matches"
COURTS = OUTPUTS / "courts"
COURT, BACKGROUND = "court.json", "background.png"
IMAGES = {"start": ("start.jpg", "image/jpeg"), "court": ("court.jpg", "image/jpeg"), "background": (BACKGROUND, "image/png")}
# Where a camera's card or a video folder may be.
MOUNTS = {"mac": ["/Volumes"], "linux": ["/media/{user}", "/run/media/{user}"]}
NAME = re.compile(r"[^,:]+")
# The length of the video review.TOOK's durations were measured on.
TOOK_VIDEO_S = 4013.0
VIDEOS = "videos"
MODELS = "models"
# The "Serveur" tab's jobs: every match online rebuilt and uploaded, every match changed copied to the server, the copies
# checked against this machine's.
HOSTING = "hosting"
BACKUP = "backup"
VERIFY = "verify"


# The words after `stats`, and how the page opens for each: a window of its own, a browser tab, nothing.
OPENING = {None: "window", "browser": "tab", "server": None}
COMMANDS = ("browser", "server", "stop")
opening: str | None = "window"

# Browsers that open a page as an app (its own window, without tabs or address bar), the first found taken.
APP_BROWSERS = {
    "wsl": [
        "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    ],
    "mac": [f"{root}/{name}.app" for name in ("Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium") for root in ("/Applications", str(Path.home() / "Applications"))],
    "linux": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"],
}


def app_window(url: str, system: str) -> list[str] | None:
    """The command opening `url` in a window of its own, None without such a browser. Under WSL2, Windows' browser
    (it reaches the server through localhost), started by `start` for it not to hang on to this server's console."""
    for found in APP_BROWSERS[system]:
        if system == "linux":
            if shutil.which(found):
                return [found, f"--app={url}"]
        elif Path(found).exists():
            if system == "mac":
                return ["open", "-na", found, "--args", f"--app={url}"]
            windows = subprocess.run(["wslpath", "-w", found], capture_output=True, text=True).stdout.strip()
            # start's first quoted word is a title: one with a space, quoted as is by WSL (an empty one would not be).
            return ["cmd.exe", "/c", "start", "Volleyball Stats", windows, f"--app={url}"] if windows else None
    return None


# Windows' curl, to know when Windows reaches this server.
WINDOWS_CURL = "/mnt/c/Windows/System32/curl.exe"
# How long a just started server may take to be reached from Windows before the page opens anyway.
REACHED_WITHIN_S = 10.0


def reached_from_windows(url: str) -> bool:
    """Whether Windows reaches `url`: WSL2 forwards a port just opened to Windows' localhost after a moment, a page
    opened sooner shows the browser's error until it reloads."""
    try:
        done = subprocess.run([WINDOWS_CURL, "-s", "-o", "NUL", "--max-time", "1", url], capture_output=True, timeout=5, stdin=subprocess.DEVNULL, cwd="/mnt/c")
    except (OSError, subprocess.SubprocessError):
        return True
    return done.returncode == 0


def open_browser(url: str) -> None:
    """`url` in a window of its own (`opening`), else in the browser; under WSL2, Windows', once it reaches the server
    (meanwhile the server starts serving)."""
    if doctor.system() == "wsl" and Path(WINDOWS_CURL).exists():
        threading.Thread(target=open_once_reached, args=(url,)).start()
    else:
        show(url)


def open_once_reached(url: str) -> None:
    deadline = time.monotonic() + REACHED_WITHIN_S
    while not reached_from_windows(url) and time.monotonic() < deadline:
        time.sleep(0.1)
    show(url)


def show(url: str) -> None:
    system = doctor.system()
    command = app_window(url, system) if opening == "window" else None
    windows = "/mnt/c" if Path("/mnt/c").exists() else None
    if command:
        subprocess.Popen(command, cwd=windows if system == "wsl" else None, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    elif system == "wsl" and shutil.which("explorer.exe"):
        subprocess.run(["explorer.exe", url], cwd=windows, capture_output=True)
    else:
        webbrowser.open(url)


def uv() -> str | None:
    """uv's path: `uv run` says it, else the PATH or where its installer puts it."""
    for found in (os.environ.get("UV"), shutil.which("uv"), str(Path.home() / ".local/bin/uv"), str(Path.home() / ".cargo/bin/uv")):
        if found and Path(found).exists():
            return found
    return None


def restart_command() -> list[str]:
    """This server started again with the code and dependencies as they now are, the page already open."""
    args = [a for a in sys.argv[1:] if a != "--no-browser"] + ["--no-browser"]
    tool = uv()
    if tool:
        return [tool, "run", "--project", str(git_check.ROOT), "python", "-m", "volleyball_stats.review", *args]
    return [sys.executable, "-m", "volleyball_stats.review", *args]


def windows_drives() -> list[str]:
    """Under WSL2, Windows' drive letters but C (a card plugged in after WSL started has no /mnt/ folder yet)."""
    try:
        roots = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "(Get-PSDrive -PSProvider FileSystem).Name"], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL, cwd="/mnt/c" if Path("/mnt/c").exists() else None
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({d.strip().upper() for d in roots.split() if re.fullmatch(r"[A-Za-z]", d.strip()) and d.strip().upper() != "C"})


def windows_home() -> Path | None:
    """Under WSL2, the Windows user's folder, where the downloads are."""
    try:
        profile = subprocess.run(["cmd.exe", "/c", "echo %USERPROFILE%"], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL, cwd="/mnt/c").stdout.strip()
        found = subprocess.run(["wslpath", profile], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(found) if found and Path(found).is_dir() else None


def mount(drive: str) -> Path:
    """Windows' drive `drive` (a letter) seen under /mnt/, as root through wsl.exe: no password to type."""
    if doctor.system() != "wsl" or not re.fullmatch(r"[A-Za-z]", drive) or drive.upper() == "C":
        raise ValueError(drive)
    target = Path("/mnt") / drive.lower()
    if not os.path.ismount(target):
        run = subprocess.run(
            ["wsl.exe", *(["-d", os.environ["WSL_DISTRO_NAME"]] if os.environ.get("WSL_DISTRO_NAME") else []), "-u", "root", "--", "sh", "-c", f"mkdir -p {target} && mount -t drvfs {drive.upper()}: {target}"],
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL, cwd="/mnt/c",
        )
        if run.returncode or not os.path.ismount(target):
            raise RuntimeError("mount")
    return target


def sources() -> list[dict]:
    """The folders where a match's video may be: the cards and drives mounted, those with a camera's DCIM first; under
    WSL2, each Windows drive (mounted when picked) and the Windows downloads."""
    user = os.environ.get("USER", "")
    found = []
    if doctor.system() == "wsl":
        for drive in windows_drives():
            path = Path("/mnt") / drive.lower()
            mounted = os.path.ismount(path)
            try:
                card = mounted and (path / "DCIM").is_dir()
            except OSError:
                card = False
            found.append({"path": str(path), "name": f"{drive}:", "card": card, **({} if mounted else {"drive": drive})})
        home = windows_home()
        for name in ("Downloads", "Videos", "Desktop"):
            if home and (home / name).is_dir():
                found.append({"path": str(home / name), "name": name, "card": False})
    for mount_point in MOUNTS[doctor.system()] if doctor.system() != "wsl" else []:
        base = Path(mount_point.format(user=user))
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if path.name.startswith(".") or path.name == "Macintosh HD" or not path.is_dir():
                continue
            try:
                card = (path / "DCIM").is_dir()
            except OSError:
                continue
            found.append({"path": str(path), "name": path.name, "card": card})
    for name in ("Downloads", "Movies", "Videos", "Desktop"):
        if (Path.home() / name).is_dir():
            found.append({"path": str(Path.home() / name), "name": name, "card": False})
    return sorted(found, key=lambda s: not s["card"])


def probed(videos: list[Path]) -> list:
    """Each video's length (import_match.probe); LookupError "unreadable:NAME" for one ffprobe cannot read (a chapter
    cut short by an empty battery)."""
    from volleyball_stats import import_match

    found = []
    for video in videos:
        try:
            found.append(import_match.probe(video))
        except (subprocess.CalledProcessError, KeyError, ValueError, IndexError) as error:
            raise LookupError(f"unreadable:{video.name}") from error
    return found


def scan(source: str) -> dict:
    """The recordings of a card or folder, each with its start, length and the match day it gives."""
    from volleyball_stats import import_match

    path = Path(source).expanduser()
    if not path.exists():
        raise LookupError("missing")
    found = import_match.videos(path)
    if not found:
        raise LookupError("empty")
    groups = import_match.recordings(probed(found))
    return {
        "source": str(path),
        "recordings": [
            {"start": g[0].stamp.isoformat() if g[0].stamp else None, "duration": sum(c.duration for c in g), "chapters": len(g), "date": import_match.named(g, ["", ""])[1]}
            for g in groups
        ],
    }


def team_flag(teams: list[dict]) -> str:
    """import_match's --teams from [{name, colour}], ValueError for a name it cannot carry."""
    from volleyball_stats.teams import parse_colour

    parts = []
    for team in teams:
        name, colour = str(team.get("name") or "").strip(), team.get("colour")
        if not NAME.fullmatch(name):
            raise ValueError("name")
        if colour and parse_colour(colour) is None:
            raise ValueError("colour")
        parts.append(f"{name}:{colour}" if colour else name)
    if len(parts) != 2:
        raise ValueError("teams")
    return ",".join(parts)


def import_steps(body: dict) -> tuple[str, str, list, float]:
    """The match's name and day, the steps importing it then looking for its court, and the length of the video they make."""
    from volleyball_stats import import_match, teams

    flag = team_flag(body["teams"])
    groups = import_match.recordings(probed(import_match.videos(Path(body["source"]).expanduser())))
    recording = int(body.get("recording") or 1)
    chapters = groups[recording - 1]
    start, end = [teams.seconds(body[k]) if body.get(k) else None for k in ("from", "to")]
    total = sum(c.duration for c in chapters)
    if (start or 0) >= min(end or total, total):
        raise ValueError("times")
    name, day = import_match.named(chapters, [t["name"].strip() for t in body["teams"]], body.get("date"))
    target = DATA / name / f"{name}.mp4"
    if target.exists() or (MATCHES / name).exists():
        raise FileExistsError(name)
    DATA.mkdir(parents=True, exist_ok=True)
    needed = 2 * sum(c.path.stat().st_size for c in chapters)
    if shutil.disk_usage(DATA).free < needed:
        raise OSError(f"disk:{round(needed / 1e9)}")
    command = ["volleyball_stats.import_match", str(Path(body["source"]).expanduser()), "--teams", flag, "--date", day, "--recording", str(recording)]
    command += [arg for k, flag_name in (("from", "--from"), ("to", "--to")) if body.get(k) for arg in (flag_name, str(body[k]))]
    return name, day, [("import", command), court_auto(name)], min(end or total, total) - (start or 0)


def court_auto(name: str) -> tuple[str, list[str]]:
    out = MATCHES / name
    return ("court", ["volleyball_stats.court", "auto", str(video_of(name)), "--out", str(out / COURT), "--background", str(out / BACKGROUND)])


def background(name: str) -> None:
    """The court's picture to click on, the players taken off (court.background), when the court's search made none."""
    import cv2

    from volleyball_stats import court

    cv2.imwrite(str(MATCHES / name / BACKGROUND), court.background(video_of(name)))


def video_of(name: str) -> Path:
    source = MATCHES / name / files.SOURCE
    if source.exists():
        return Path(json.loads(source.read_text())["video"])
    return DATA / name / f"{name}.mp4"


def preparing(listed: list[dict]) -> list[dict]:
    """The matches not ready for the review, with what they wait for: `importing`, `court` (to map by hand, `fitFailed`
    when the clicks did not fit), `check` (to look at, then start), `running`, `failed`, `elsewhere` (run by a command
    on this machine) or `stalled` (a run by a command that stopped, or one on the other machine)."""
    ready = {m["path"] for m in listed if m.get("ready") or m.get("missing")}
    by_match = {j["id"]: j for j in jobs.state(OUTPUTS) if j["kind"] in ("import", "court", "pipeline")}
    names = {p.parent.name for p in MATCHES.glob("*/teams.json") if not (p.parent / "report.md").exists()} | set(by_match)
    found = []
    for name in sorted(names - ready):
        job, folder = by_match.get(name), MATCHES / name
        saved = json.loads((folder / "teams.json").read_text()) if (folder / "teams.json").exists() else job or {}
        item = {"name": name, "date": saved.get("date"), "teams": saved.get("teams"), "job": job, "start": (folder / "start.jpg").exists(), "court": (folder / "court.jpg").exists()}
        if job and job["running"]:
            item["state"] = "importing" if job.get("step") == "import" else "running" if job.get("step") == "pipeline" else "court"
            item["searching"] = job.get("step") == "court" and not job.get("manual")
            item["placing"] = job.get("step") == "court" and bool(job.get("manual"))
            item["left"] = time_left(job, time.time())
        elif job and job.get("failed") == "court" and job.get("error") not in ("stopped", "interrupted") and not (folder / COURT).exists():
            item["state"] = "court"
            item["fitFailed"] = bool(job.get("manual"))
        elif job and job.get("failed"):
            item["state"] = "failed"
        elif (folder / files.SOURCE).exists() and not job:
            item["state"] = "elsewhere" if name in commands_running() else "stalled"
        elif (folder / COURT).exists():
            item["state"] = "check"
        elif folder.exists():
            item["state"] = "court"
        else:
            continue
        found.append(item)
    return found


def commands_running() -> str:
    """The pipelines running on this machine, their command lines: a match's name in it runs."""
    try:
        lines = subprocess.run(["ps", "-Ao", "command="], capture_output=True, text=True, timeout=5).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return ""
    return "\n".join(line for line in lines if "volleyball_stats.match " in line)


def court_of(name: str) -> Path:
    """The match's court: the app's, else the one its pipeline last ran with (source.json)."""
    court, source = MATCHES / name / COURT, MATCHES / name / files.SOURCE
    if not court.exists() and source.exists():
        return Path(json.loads(source.read_text())["court"])
    return court


def time_left(job: dict, now: float) -> float | None:
    """Seconds left of a job's step: from its progress while it tells one (the copy, the tracking), then for the
    pipeline each later stage's duration on the first ASPOM match (review.TOOK), in proportion to the video's length."""
    from volleyball_stats import playing, review

    spent, done = now - job.get("stepStarted", job["started"]), job.get("progress")
    here = spent * (1 - done) / done if done and done > 0.01 else None
    if job.get("step") != "pipeline":
        return here
    stage = job.get("stage") or "tracking"
    later = [s for s in review.STAGES[review.STAGES.index(stage) + 1 :] if s != "play" or playing.available()] if stage in review.STAGES else []
    scale = job.get("duration", TOOK_VIDEO_S) / TOOK_VIDEO_S
    rest = scale * sum(review.TOOK.get(f"pipeline:{s}", 0.0) for s in later)
    if stage == "tracking":
        return None if here is None else here + rest
    return scale * review.TOOK.get(f"pipeline:{stage}", 0.0) / 2 + rest


def told(job: dict, now: float) -> dict:
    """A running job's stage as its log tells it ("match 2/5": the second of five matches, `n` and `of`), the seconds
    spent and left."""
    stage, _, count = (job.get("stage") or "").partition(" ")
    n, _, of = count.partition("/")
    return {"stage": stage or None, "n": int(n) if n.isdigit() else None, "of": int(of) if of.isdigit() else None, "elapsed": now - job["started"], "left": time_left(job, now)}


def run_pipeline(name: str, anyway: bool) -> dict | None:
    """Starts the pipeline on `name`; the machine's state instead when it is busy and not `anyway`."""
    busy = doctor.busy()
    if busy["status"] != "ok" and not anyway:
        return busy
    court = court_of(name)
    if not court.exists():
        raise LookupError(name)
    from volleyball_stats import import_match

    video = video_of(name)
    command = ["volleyball_stats.match", str(video), "--court", str(court), "--players", "--anyway"]
    jobs.start(OUTPUTS, name, "pipeline", [("pipeline", command)], duration=import_match.probe(video).duration)
    return None


def played_teams() -> list[str]:
    """The teams' names of the matches, most matches first."""
    counts: dict[str, int] = {}
    for path in MATCHES.glob("*/teams.json"):
        for name in {t.get("name") for t in json.loads(path.read_text()).get("teams") or []}:
            if name:
                counts[name] = counts.get(name, 0) + 1
    return sorted(counts, key=lambda n: (-counts[n], n))


def swap(name: str) -> None:
    """The teams' sides swapped: the first is the one on the left at the first rally."""
    path = MATCHES / name / "teams.json"
    saved = json.loads(path.read_text())
    saved["teams"] = saved["teams"][::-1]
    files.write_text(path, json.dumps(saved, indent=2, ensure_ascii=False) + "\n")


def delete(name: str) -> None:
    """A match not reviewed yet taken away, its video too."""
    folder = MATCHES / name
    if (folder / "report.md").exists() or (folder / "identity_answers.json").exists() or any(j["id"] == name and j["running"] for j in jobs.state(OUTPUTS)):
        raise PermissionError(name)
    jobs.forget(OUTPUTS, name)
    for path in (folder, DATA / name):
        if path.is_dir() and path.resolve().parent in (MATCHES.resolve(), DATA.resolve()):
            shutil.rmtree(path)


def fit_court(name: str, clicks: dict, court_name: str) -> None:
    from volleyball_stats import court

    points = {k: [float(v[0]), float(v[1])] for k, v in clicks.items() if k in court.LANDMARKS}
    if len(points) < 4 or not NAME.fullmatch(court_name.strip()) or "/" in court_name:
        raise ValueError("clicks")
    folder = MATCHES / name
    files.write_text(folder / "court_clicks.json", json.dumps(points, indent=2))
    slug = re.sub(r"[^a-z0-9]+", "_", court_name.strip().lower()).strip("_") or name
    command = ["volleyball_stats.court", "fit", str(folder / "court_clicks.json"), str(video_of(name)), "--court", slug, "--courts", str(COURTS), "--out", str(folder / COURT)]
    if (folder / BACKGROUND).exists():
        command += ["--background", str(folder / BACKGROUND)]
    if jobs.is_running(OUTPUTS, name):
        raise jobs.Running(name)
    (folder / COURT).unlink(missing_ok=True)
    jobs.start(OUTPUTS, name, "court", [("court", command)], manual=True)


def videos_state() -> dict | None:
    """The exchange of the videos with the other machine: waiting with its address and code, copying, or how it ended."""
    job = next((j for j in jobs.state(OUTPUTS) if j["id"] == VIDEOS), None)
    if not job:
        return None
    text = jobs.tail(jobs.folder(OUTPUTS) / f"{VIDEOS}.log")
    found = re.search(r"data_sync (\S+):(\d+) (\w+)", text)
    return {**job, "address": found and found[1], "port": found and int(found[2]), "code": found and found[3], "copying": "::stage copying" in text}


def server_state() -> dict:
    """The "Serveur" tab: the server, whether this machine copies its matches by itself, how its last copies and check
    went, and the tab's jobs."""
    found = {j["id"]: j for j in jobs.state(OUTPUTS) if j["id"] in (HOSTING, BACKUP, VERIFY)}
    last = backup.state(OUTPUTS)
    found = {k: {**j, **told(j, time.time())} if j["running"] else j for k, j in found.items()}
    return {
        "server": server.read(OUTPUTS),
        "auto": sync.auto(OUTPUTS),
        "last": {k: last[k] for k in ("at", "error", "verified", "problems")},
        "online": server.online(OUTPUTS),
        "hosting": found.get(HOSTING),
        "backup": found.get(BACKUP),
        "verify": found.get(VERIFY),
    }


def models_state() -> dict | None:
    return next((j for j in jobs.state(OUTPUTS) if j["id"] == MODELS), None)


def update() -> None:
    """The code brought up to date (git pull), then the dependencies (uv sync); RuntimeError with git's or uv's reason."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    pull = subprocess.run(["git", "-C", str(git_check.ROOT), "pull", "--ff-only", "--autostash"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)
    if pull.returncode:
        raise RuntimeError(((pull.stderr.strip() or pull.stdout.strip()).splitlines() or [f"git pull: exit {pull.returncode}"])[-1])
    tool = uv()
    if tool:
        sync = subprocess.run([tool, "sync", "--inexact", "--project", str(git_check.ROOT)], capture_output=True, text=True, timeout=1800)
        if sync.returncode:
            raise RuntimeError((sync.stderr.strip().splitlines() or [f"uv sync: exit {sync.returncode}"])[-1])


def state(listed: list[dict]) -> dict:
    return {"preparing": preparing(listed), "videos": videos_state(), "models": models_state(), "system": doctor.system(), "backup": server.warning(OUTPUTS)}


def handle(method: str, path: str, query: str, body: dict, listed, busy=lambda: False, club_changed=lambda: None, open_match: str | None = None) -> tuple[bytes, str, int] | None:
    """The response to an /app/ request; None when `path` is not one. `listed` gives the review's list of the matches,
    `busy` whether the server is applying answers (no update then), `club_changed` is told the club changed, `open_match`
    the match whose review is open (it cannot be restored under it)."""
    if not path.startswith("/app/"):
        return None
    reply = lambda data, status=200: (json.dumps(data, ensure_ascii=False).encode(), "application/json", status)  # noqa: E731
    route = path.removeprefix("/app/")
    try:
        if method == "GET":
            if route == "state":
                return reply(state(listed()))
            if route == "doctor":
                return reply(doctor.checks(DATA.parent))
            if route == "server":
                return reply(server_state())
            if route == "server/copies":
                return reply(server.copies(OUTPUTS))
            if route == "sources":
                return reply(sources())
            if route == "club":
                return reply({"club": club_settings.read(), "themes": club_settings.themes(), "played": played_teams()})
            if route == "club/file":
                found = club_settings.file(parse_qs(query).get("path", [""])[0])
                if not found:
                    return reply({"error": "missing"}, 404)
                return found.read_bytes(), {".png": "image/png", ".webp": "image/webp"}.get(found.suffix.lower(), "image/jpeg"), 200
            if route == "image":
                q = parse_qs(query)
                file, kind = IMAGES[q["kind"][0]]
                name = q["match"][0]
                image = MATCHES / name / file
                if "/" in name or ".." in name:
                    return reply({"error": "missing"}, 404)
                if file == BACKGROUND and not image.exists() and video_of(name).exists():
                    background(name)
                if not image.is_file():
                    return reply({"error": "missing"}, 404)
                return image.read_bytes(), kind, 200
            return None
        name = str(body.get("match", ""))
        if name and ("/" in name or ".." in name):
            raise ValueError(name)
        if route in ("alive", "leaving"):
            (presence.PAGES.seen if route == "alive" else presence.PAGES.left)(str(body["id"]))
            return reply({})
        if route == "mount":
            return reply({"path": str(mount(str(body["drive"])))})
        if route == "scan":
            return reply(scan(str(body["source"])))
        if route == "import":
            name, day, steps, total = import_steps(body)
            jobs.start(OUTPUTS, name, "import", steps, total=total, teams=[{"name": t["name"].strip(), "colour": t.get("colour")} for t in body["teams"]], date=day)
            return reply({"match": name})
        if route == "court/auto":
            jobs.start(OUTPUTS, name, "court", [court_auto(name)])
            return reply({})
        if route == "court/fit":
            fit_court(name, body["clicks"], str(body["court"]))
            return reply({})
        if route in ("club", "club/theme"):
            if route == "club":
                club_settings.save(body)
            else:
                club_settings.use(str(body["id"]))
            club_changed()
            shortcut.refresh()
            return reply({"club": club_settings.read()})
        if route == "server":
            server.save(OUTPUTS, body)
            return reply(server_state())
        if route == "server/test":
            server.test(OUTPUTS)
            return reply({})
        if route == "server/auto":
            if not isinstance(body.get("on"), bool):
                raise ValueError("on")
            sync.set_auto(OUTPUTS, body["on"])
            return reply(server_state())
        if route == "server/host":
            jobs.start(OUTPUTS, HOSTING, HOSTING, [(HOSTING, ["volleyball_stats.matches", "--all", str(MATCHES)])])
            return reply(server_state())
        if route == "server/delete":
            server.delete(OUTPUTS, str(body["day"]))
            return reply({})
        if route == "server/keep":
            return reply({"removes": server.keep(OUTPUTS, body["keep"], bool(body.get("apply")))})
        if route == "server/restore":
            server.restore(OUTPUTS, str(body["copy"]), str(body["what"]), open_match)
            return reply({})
        if route == "server/verify":
            jobs.start(OUTPUTS, VERIFY, VERIFY, [(VERIFY, ["volleyball_stats.sync", "--outputs", str(OUTPUTS), "verify"])])
            return reply(server_state())
        if route == "server/backup":
            jobs.start(OUTPUTS, BACKUP, BACKUP, [(BACKUP, ["volleyball_stats.sync", "--outputs", str(OUTPUTS), "push", "--all"])])
            return reply(server_state())
        if route == "swap":
            swap(name)
            return reply({})
        if route == "run":
            refused = run_pipeline(name, bool(body.get("anyway")))
            return reply({"busy": refused} if refused else {}, 409 if refused else 200)
        if route == "stop":
            jobs.stop(OUTPUTS, str(body["id"]))
            return reply({})
        if route == "forget":
            jobs.forget(OUTPUTS, str(body["id"]))
            return reply({})
        if route == "delete":
            delete(name)
            return reply({})
        if route == "models":
            jobs.start(OUTPUTS, MODELS, "models", [("models", ["volleyball_stats.doctor", "--models"])])
            return reply({})
        if route == "videos/wait":
            jobs.start(OUTPUTS, VIDEOS, "videos", [("videos", ["volleyball_stats.data_sync"])])
            return reply({})
        if route == "videos/join":
            peer, code = str(body["address"]).strip(), str(body["code"]).strip()
            if not re.fullmatch(r"[\w.-]+:\d+", peer) or not re.fullmatch(r"\w+", code):
                raise ValueError("address")
            jobs.start(OUTPUTS, VIDEOS, "videos", [("videos", ["volleyball_stats.data_sync", peer, code])])
            return reply({})
        if route == "quit":
            if busy():
                return reply({"error": "busy"}, 409)
            return reply({})
        if route == "update":
            running = [j["id"] for j in jobs.state(OUTPUTS) if j["running"]]
            if running or busy():
                return reply({"error": "busy", "running": running}, 409)
            update()
            return reply({})
    except jobs.Running:
        return reply({"error": "running"}, 409)
    except FileExistsError as error:
        return reply({"error": "exists", "match": str(error)}, 409)
    except (RuntimeError, OSError) as error:
        return reply({"error": str(error) or type(error).__name__}, 409)
    except (LookupError, TypeError, ValueError, AttributeError) as error:
        return reply({"error": str(error) or type(error).__name__}, 400)
    except Exception as error:  # noqa: BLE001
        # A video ffprobe cannot read, a page build failing...: the page says it instead of waiting for good.
        traceback.print_exc()
        return reply({"error": str(error) or type(error).__name__}, 500)
    return None


def restart_after(lock=None) -> None:
    """Replaces this server by `restart_command`'s once the response on its way has left."""

    def replace() -> None:
        time.sleep(0.2)
        if lock:
            lock.acquire()
        command = restart_command()
        os.execv(command[0], command)

    threading.Thread(target=replace, daemon=True).start()


def stop_after(lock=None) -> None:
    """Ends this server once the response on its way has left; its jobs go on. Not by SIGINT: one started in the
    background ignores it."""

    def stop() -> None:
        time.sleep(0.2)
        if lock:
            lock.acquire()
        os._exit(0)

    threading.Thread(target=stop, daemon=True).start()


def stop(port: int) -> int:
    """Asks the server on `port` to stop, refused while it applies answers; the exit status."""
    if not already_open(port):
        print("Not running.", flush=True)
        return 0
    request = urllib.request.Request(f"http://127.0.0.1:{port}/app/quit", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(request, timeout=5).close()
    except urllib.error.HTTPError as error:
        if error.code == 409:
            print("Answers are being applied: try again once done.", flush=True)
            return 1
        raise
    for _ in range(50):
        if not already_open(port):
            print("Stopped.", flush=True)
            return 0
        time.sleep(0.1)
    print("Still running.", flush=True)
    return 1


def already_open(port: int) -> bool:
    """Whether the app already answers on `port`: a second start only opens the page."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/current", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def lowered() -> bool:
    """Whether this process runs below the normal priority: zsh lowers its background jobs' (bg_nice), and nothing
    without root brings it back, for the server nor its jobs."""
    return os.nice(0) > 0


def parse(args: list[str]) -> tuple[str | None, list[str]]:
    """The command after `stats` (None: the app in its own window) and the rest, for the review."""
    args = list(args)
    command = args.pop(0) if args[:1] and args[0] in COMMANDS else None
    # ponytail: the flags the commands replaced, for the habits of then; drop them once forgotten.
    for flag, instead in (("--stop", "stop"), ("--no-browser", "server")):
        if flag in args:
            args.remove(flag)
            command = command or instead
    return command, args


def main() -> None:
    from volleyball_stats import review

    global opening
    args = sys.argv[1:]
    if args[:1] in (["-h"], ["--help"], ["help"]):
        print(__doc__.split("\n\n")[1], flush=True)
        return
    command, args = parse(args)
    os.chdir(git_check.ROOT)
    club_settings.migrate()
    shortcut.update_launcher()
    port = int(args[args.index("--port") + 1]) if "--port" in args[:-1] else review.PORT
    if command == "stop":
        sys.exit(stop(port))
    opening = OPENING[command]
    if already_open(port):
        print(f"Already open: http://127.0.0.1:{port}/", flush=True)
        if opening:
            open_browser(f"http://127.0.0.1:{port}/")
        return
    if lowered():
        sys.exit(f"Started at a lowered priority (nice {os.nice(0)}), which the jobs it starts would inherit: start it from "
                 "its shortcut, or not as a background job of zsh (`setopt no_bg_nice` first).")
    shortcut.refresh()
    sys.argv = [sys.argv[0], *args, *([] if opening else ["--no-browser"]), *(["--with-window"] if opening == "window" else [])]
    review.main()


if __name__ == "__main__":
    main()
