"""The app: the one command to start, everything else in the browser.

    uv run volleyball-stats [MATCH] [--no-browser] [--port PORT]

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
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs

from volleyball_stats import branding, doctor, files, git_check, jobs

DATA = Path("data/matches")
OUTPUTS = Path("outputs")
MATCHES = OUTPUTS / "matches"
COURTS = OUTPUTS / "courts"
COURT, BACKGROUND = "court.json", "background.png"
IMAGES = {"start": ("start.jpg", "image/jpeg"), "court": ("court.jpg", "image/jpeg"), "background": (BACKGROUND, "image/png")}
# Where a camera's card or a video folder may be.
MOUNTS = {"mac": ["/Volumes"], "linux": ["/media/{user}", "/run/media/{user}"], "wsl": ["/mnt"]}
NAME = re.compile(r"[^,:]+")
# The length of the video review.TOOK's durations were measured on.
TOOK_VIDEO_S = 4013.0
VIDEOS = "videos"
MODELS = "models"


def open_browser(url: str) -> None:
    """`url` in the browser; under WSL2, Windows' (it reaches the server through localhost)."""
    if doctor.system() == "wsl" and shutil.which("explorer.exe"):
        subprocess.run(["explorer.exe", url], cwd="/mnt/c" if Path("/mnt/c").exists() else None, capture_output=True)
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


def sources() -> list[dict]:
    """The folders where a match's video may be: the cards and drives mounted, those with a camera's DCIM first."""
    user = os.environ.get("USER", "")
    found = []
    for mount in MOUNTS[doctor.system()]:
        base = Path(mount.format(user=user))
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if path.name.startswith(".") or path.name in ("Macintosh HD", "c", "wsl", "wslg") or not path.is_dir():
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


def scan(source: str) -> dict:
    """The recordings of a card or folder, each with its start, length and the match day it gives."""
    from volleyball_stats import import_match

    path = Path(source).expanduser()
    if not path.exists():
        raise LookupError("missing")
    found = import_match.videos(path)
    if not found:
        raise LookupError("empty")
    groups = import_match.recordings([import_match.probe(p) for p in found])
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
    groups = import_match.recordings([import_match.probe(p) for p in import_match.videos(Path(body["source"]).expanduser())])
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
    """The matches not ready for the review, with what they wait for: `importing`, `court` (to map by hand), `check`
    (to look at, then start), `running`, `failed`, or `elsewhere` (run by a command, or on the other machine)."""
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
            item["searching"] = job.get("step") == "court"
            item["left"] = time_left(job, time.time())
        elif job and job.get("failed") == "court" and job.get("error") not in ("stopped", "interrupted") and not (folder / COURT).exists():
            item["state"] = "court"
        elif job and job.get("failed"):
            item["state"] = "failed"
        elif (folder / files.SOURCE).exists() and not job:
            item["state"] = "elsewhere"
        elif (folder / COURT).exists():
            item["state"] = "check"
        elif folder.exists():
            item["state"] = "court"
        else:
            continue
        found.append(item)
    return found


def time_left(job: dict, now: float) -> float | None:
    """Seconds left of a job's step: from its progress while it tells one (the copy, the tracking), then for the
    pipeline each later stage's duration on the first ASPOM match (review.TOOK), in proportion to the video's length."""
    from volleyball_stats import review

    spent, done = now - job.get("stepStarted", job["started"]), job.get("progress")
    here = spent * (1 - done) / done if done and done > 0.01 else None
    if job.get("step") != "pipeline":
        return here
    stage = job.get("stage") or "tracking"
    later = review.STAGES[review.STAGES.index(stage) + 1 :] if stage in review.STAGES else []
    scale = job.get("duration", TOOK_VIDEO_S) / TOOK_VIDEO_S
    rest = scale * sum(review.TOOK.get(f"pipeline:{s}", 0.0) for s in later)
    if stage == "tracking":
        return None if here is None else here + rest
    return scale * review.TOOK.get(f"pipeline:{stage}", 0.0) / 2 + rest


def run_pipeline(name: str, anyway: bool) -> dict | None:
    """Starts the pipeline on `name`; the machine's state instead when it is busy and not `anyway`."""
    busy = doctor.busy()
    if busy["status"] != "ok" and not anyway:
        return busy
    court = MATCHES / name / COURT
    if not court.exists():
        raise LookupError(name)
    from volleyball_stats import import_match

    video = video_of(name)
    command = ["volleyball_stats.match", str(video), "--court", str(court), "--players", "--anyway"]
    jobs.start(OUTPUTS, name, "pipeline", [("pipeline", command)], duration=import_match.probe(video).duration)
    return None


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
    (folder / COURT).unlink(missing_ok=True)
    jobs.start(OUTPUTS, name, "court", [("court", command)])


def videos_state() -> dict | None:
    """The exchange of the videos with the other machine: waiting with its address and code, copying, or how it ended."""
    job = next((j for j in jobs.state(OUTPUTS) if j["id"] == VIDEOS), None)
    if not job:
        return None
    text = jobs.tail(jobs.folder(OUTPUTS) / f"{VIDEOS}.log")
    found = re.search(r"data_sync (\S+):(\d+) (\w+)", text)
    return {**job, "address": found and found[1], "port": found and int(found[2]), "code": found and found[3]}


def models_state() -> dict | None:
    return next((j for j in jobs.state(OUTPUTS) if j["id"] == MODELS), None)


def update() -> None:
    """The code brought up to date (git pull), then the dependencies (uv sync); RuntimeError with git's or uv's reason."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    pull = subprocess.run(["git", "-C", str(git_check.ROOT), "pull", "--ff-only", "--autostash"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120)
    if pull.returncode:
        raise RuntimeError((pull.stderr.strip() or pull.stdout.strip()).splitlines()[-1])
    tool = uv()
    if tool:
        sync = subprocess.run([tool, "sync", "--inexact", "--project", str(git_check.ROOT)], capture_output=True, text=True, timeout=1800)
        if sync.returncode:
            raise RuntimeError(sync.stderr.strip().splitlines()[-1])


def state(listed: list[dict]) -> dict:
    return {"preparing": preparing(listed), "videos": videos_state(), "models": models_state(), "system": doctor.system()}


def handle(method: str, path: str, query: str, body: dict, listed, busy=lambda: False, rebranded=lambda: None) -> tuple[bytes, str, int] | None:
    """The response to an /app/ request; None when `path` is not one. `listed` gives the review's list of the matches,
    `busy` whether the server is applying answers (no update then), `rebranded` is told the branding changed."""
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
            if route == "sources":
                return reply(sources())
            if route == "brand":
                return reply({"brand": branding.read(), "presets": branding.presets()})
            if route == "brand/file":
                found = branding.file(parse_qs(query).get("path", [""])[0])
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
        if route in ("brand", "brand/preset"):
            if route == "brand":
                branding.save(body)
            else:
                branding.use(str(body["id"]))
            rebranded()
            return reply({"brand": branding.read()})
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
        if route == "update":
            running = [j["id"] for j in jobs.state(OUTPUTS) if j["running"]]
            if running or busy():
                return reply({"error": "busy", "running": running}, 409)
            update()
            return reply({})
    except FileExistsError as error:
        return reply({"error": "exists", "match": str(error)}, 409)
    except (RuntimeError, OSError) as error:
        return reply({"error": str(error) or type(error).__name__}, 409)
    except (LookupError, TypeError, ValueError, AttributeError) as error:
        return reply({"error": str(error) or type(error).__name__}, 400)
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


def already_open(port: int) -> bool:
    """Whether the app already answers on `port`: a second start only opens the page."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/current", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def main() -> None:
    from volleyball_stats import review

    os.chdir(git_check.ROOT)
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv[:-1] else review.PORT
    if already_open(port):
        print(f"Already open: http://127.0.0.1:{port}/", flush=True)
        if "--no-browser" not in sys.argv:
            open_browser(f"http://127.0.0.1:{port}/")
        return
    review.main()


if __name__ == "__main__":
    main()
