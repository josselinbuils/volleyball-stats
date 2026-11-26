"""Whether a change moved the matches' online state, as the app shows it (Site tab, a match's review): nothing may
turn late or changed by itself.

    uv run python benchmarks/online.py before   # before the change: outputs/online_before.json
    uv run python benchmarks/online.py          # after it: the differences, exit 1 when any
"""

import json
import sys
from pathlib import Path

from volleyball_stats import hosted, server

OUT = Path("outputs")
BEFORE = OUT / "online_before.json"


def state() -> dict:
    """The Site tab's rows and code row, then each match's state in its review and its page's stamp."""
    found = {"listed": server.listed(OUT), "code": server.code_state(OUT), "matches": {}}
    for match in sorted((OUT / "matches").iterdir()):
        if (match / "review" / "data.js").exists():
            found["matches"][match.name] = {"hosted": hosted.read_hosted(match), "stamp": hosted.page_stamp(match)}
    return json.loads(json.dumps(found, sort_keys=True, default=str))


def differences(before, after, at: str = "") -> list[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        return [d for k in sorted(before.keys() | after.keys()) for d in differences(before.get(k), after.get(k), f"{at}.{k}")]
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [d for i, (b, a) in enumerate(zip(before, after)) for d in differences(b, a, f"{at}[{i}]")]
    return [] if before == after else [f"{at}: {before!r} -> {after!r}"]


if __name__ == "__main__":
    now = state()
    if sys.argv[1:] == ["before"]:
        BEFORE.write_text(json.dumps(now, indent=1) + "\n", encoding="utf-8")
        print(f"{len(now['matches'])} matches, {len(now['listed'])} in the Site tab: {BEFORE}")
        sys.exit()
    found = differences(json.loads(BEFORE.read_text(encoding="utf-8")), now)
    print("\n".join(found) or f"same online state ({len(now['matches'])} matches)")
    sys.exit(1 if found else 0)
