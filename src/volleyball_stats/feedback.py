"""Viewers' reports of what is wrong in a match page's moments (web.py --feedback), from the hosting's
log: one JSON object a line, the body the page sent in its "report". Listed by match, then time.

    scp -i ~/.ssh/id_ed25519_ovh root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/feedback/feedback.log outputs/feedback/feedback.log
    uv run python -m volleyball_stats.feedback outputs/feedback/feedback.log
"""

import argparse
import json
import subprocess
import threading
import time
from pathlib import Path

from volleyball_stats import files
from volleyball_stats.matches import PUBLISH, ssh_options

# The hostings' reports are fetched this often, in seconds, while the app runs.
EVERY_S = 10 * 60
# In outputs/feedback: the reports fetched and not yet seen in their match's review, by match ("matches", ids), and the last
# fetch's time ("at").
NEW = "new.json"
# One fetch at a time (the timer's and the user's), and one change of NEW: marking a match seen waits for no fetch.
fetching = threading.Lock()
writing = threading.Lock()


def merge(report: dict, later: dict) -> dict:
    """`report` completed by `later`, the same report (`id`) sent again with details: what it says
    replaces the flag's empty kind and comment."""
    return {**report, **{k: v for k, v in later.items() if k != "received" and v not in (None, "") and not (k == "kind" and v == "flag")}}


def read(path: Path) -> list[dict]:
    """The reports of the log at `path`, each with its "received" time, a report's details sent after
    its one-tap flag (same `id`) merged into it; lines that are no report (sent by hand, cut) skipped."""
    out: list[dict] = []
    by_id: dict[str, int] = {}
    for line in path.read_text().splitlines():
        try:
            entry = json.loads(line)
            report = json.loads(entry["report"])
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(report, dict):
            continue
        report = {**report, "received": entry.get("received")}
        if report.get("id") in by_id:
            out[by_id[report["id"]]] = merge(out[by_id[report["id"]]], report)
        else:
            if report.get("id"):
                by_id[report["id"]] = len(out)
            out.append(report)
    return out


def fetch(folder: Path, upload: str, key: str) -> Path | None:
    """The hosting's report log (beside the site of `upload`, publish.json's "root@HOST:.../site/")
    copied to `folder`/feedback-DATE.log, which the review reads, then emptied online; None when it
    holds nothing. The copy is kept before the log is emptied."""
    host, site = upload.split(":", 1)
    online = str(Path(site.rstrip("/")).parent / "feedback" / "feedback.log")
    ssh = ssh_options(key)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"feedback-{time.strftime('%Y%m%d-%H%M%S')}.log"
    subprocess.run(["scp", *ssh, f"{host}:{online}", str(target)], check=True, capture_output=True)
    if not target.stat().st_size:
        target.unlink()
        return None
    subprocess.run(["ssh", *ssh, host, f": > {online}"], check=True, capture_output=True)
    return target


def news(outputs: Path) -> dict:
    """NEW's content: {"at": time of the last fetch, "matches": {match: [report ids]}}."""
    try:
        found = json.loads((outputs / "feedback" / NEW).read_text())
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def seen(outputs: Path, name: str) -> None:
    """The new reports of the match `name` seen: its review shows them."""
    with writing:
        found = news(outputs)
        if name in found.get("matches", {}):
            del found["matches"][name]
            files.write_text(outputs / "feedback" / NEW, json.dumps(found) + "\n")


def fetch_all(outputs: Path) -> dict[str, int]:
    """Every hosting's reports (the publish.json of the matches in `outputs`) fetched (`fetch`), those of a match there added
    to its new ones (NEW, by the name it has now: a report may carry a former one); how many each match got. Those fetched
    before a hosting fails are counted: `fetch` empties the log online."""
    with fetching:
        hostings, names = set(), {}
        for match in sorted((outputs / "matches").glob("*/")):
            names.update({alias: match.name for alias in files.aliases(match)})
            names[match.name] = match.name
            try:
                config = json.loads((match / PUBLISH).read_text())
            except (OSError, ValueError):
                continue
            if isinstance(config, dict) and config.get("upload") and config.get("key"):
                hostings.add((config["upload"], config["key"]))
        if not hostings:
            return {}
        logs: list[Path] = []
        got: dict[str, int] = {}
        try:
            for upload, key in sorted(hostings):
                log = fetch(outputs / "feedback", upload, key)
                if log:
                    logs.append(log)
        finally:
            with writing:
                found = news(outputs)
                known = found.get("matches") if isinstance(found.get("matches"), dict) else {}
                for report in (r for log in logs for r in read(log)):
                    name = names.get(str(report.get("match")))
                    said = str(report.get("id") or f"{report.get('received')}:{report.get('time')}")
                    if name and said not in known.setdefault(name, []):
                        known[name].append(said)
                        got[name] = got.get(name, 0) + 1
                (outputs / "feedback").mkdir(parents=True, exist_ok=True)
                files.write_text(outputs / "feedback" / NEW, json.dumps({"at": time.time(), "matches": {k: v for k, v in known.items() if v}}) + "\n")
        return got


def watch(outputs: Path, got=lambda found: None) -> None:
    """Fetches every EVERY_S (`fetch_all`), the first once EVERY_S passed since the last (a server started again on
    another match fetches none at once), telling `got` what came; a failure (offline) waits for the next."""
    time.sleep(max(0.0, (news(outputs).get("at") or 0) + EVERY_S - time.time()))
    while True:
        try:
            found = fetch_all(outputs)
            if found:
                got(found)
        except Exception as error:  # noqa: BLE001
            print(f"reports fetch failed: {error}", flush=True)
        time.sleep(EVERY_S)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path, help="The hosting's feedback.log")
    args = parser.parse_args()
    reports = read(args.log)
    for match in sorted({str(r.get("match")) for r in reports}):
        print(f"== {match}")
        for r in sorted((r for r in reports if str(r.get("match")) == match), key=lambda r: r.get("time") or 0):
            t = float(r.get("time") or 0)
            rally = "" if r.get("rally") is None else f"rally {r['rally'] + 1}"
            comment = f" — {r['comment']}" if r.get("comment") else ""
            print(f"{int(t // 60)}:{t % 60:04.1f}  {rally:9}  {r.get('kind', '?'):7}  {r.get('shown', '')}{comment}")
    print(f"{len(reports)} reports")


if __name__ == "__main__":
    main()
