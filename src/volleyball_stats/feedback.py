"""Viewers' reports of what is wrong in a match page's moments (web.py --feedback), from the hosting's
log: one JSON object a line, the body the page sent in its "report". Listed by match, then time.

    scp -i ~/.ssh/id_ed25519_ovh root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/feedback/feedback.log outputs/feedback.log
    uv run python -m volleyball_stats.feedback outputs/feedback.log
"""

import argparse
import json
from pathlib import Path


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
