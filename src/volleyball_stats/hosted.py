"""Where a match's hosted page stands: what its last upload sent (HOSTED, HOSTED_PAGE), whether the review's page or the
site's code changed since, and what."""

import hashlib
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from volleyball_stats import files, git_check, matches, speech
from volleyball_stats.review import page_data

# Beside a match's outputs: when its hosted page was last uploaded, and what it then showed (`page_stamp`).
HOSTED = "hosted.json"
# The page data and code the last upload sent (`page_content`): what changed since, when the online page is late.
HOSTED_PAGE = "hosted_page.json"
# The code the hosted pages run, by the name the late page's tip gives each (`matches.CODE_FILES`).
CODE_PAGES = matches.CODE_FILES
# The code page_stamp takes, in its order: since the site runs one code for all its pages (`matches.share_code`, 24 Nov), none,
# the code late on its own (`site_code`); uploads recorded without their `pages` took the first two only, then all three.
STAMPED, OLD_STAMPED = (), ("list", "page")


def page_stamp(match: Path, pages: tuple[str, ...] = STAMPED) -> str:
    """What the hosted page would show: the review's page data, as content (its keys in any order), and the code of `pages`.
    Not the data's `v`, its address for the browser's cache, which each patch of the pictures moves (`web.patch_people`): a
    restart rebuilding the same page then patching it gave another, and the online page looked late."""
    return data_stamp(page_content(match)["data"], pages)


def data_stamp(data: dict, pages: tuple[str, ...] = STAMPED) -> str:
    """`page_stamp` of the page data `data`."""
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode())
    for name in pages:
        digest.update(CODE_PAGES[name].read_bytes())
    return digest.hexdigest()[:16]


# The parts of the page data whose changes the tip names one by one: the club's fields, the players and films by name.
NAMED_KEYS = ("club", "people", "films")


def page_content(match: Path) -> dict:
    """The review's page data without its `v` (`page_stamp`), and its code's stamp for each of CODE_PAGES."""
    data = page_data(match / "review") or {}
    data.pop("v", None)
    return {"data": data, "code": {name: hashlib.sha256(path.read_bytes()).hexdigest()[:16] for name, path in CODE_PAGES.items()}}


def page_changes(sent: dict, now: dict) -> list[dict]:
    """What changed from the page content `sent` to `now` (`page_content`): each part of the data that differs, with how many of
    its items changed, added or went (a list's, a mapping's) and, for NAMED_KEYS, which (`keys`: the players by name)."""
    out = []
    # Data built before its format was written is format 1 (`matches.page_format`): no change of the page.
    old, new = {"format": 1, **sent["data"]}, {"format": 1, **now["data"]}
    for part in sorted(set(old) | set(new)):
        a, b = old.get(part), new.get(part)
        if a == b:
            continue
        keys = None
        if isinstance(a, list) and isinstance(b, list):
            texts = lambda items: Counter(json.dumps(x, sort_keys=True) for x in items)  # noqa: E731
            gone, came = texts(a) - texts(b), texts(b) - texts(a)
            count = max(sum(gone.values()), sum(came.values()))
        elif isinstance(a, dict) and isinstance(b, dict):
            changed = sorted((k for k in set(a) | set(b) if a.get(k) != b.get(k)), key=lambda k: (len(k), k))
            count = len(changed)
            if part == "people":
                # The tracks without a name only colour the court's dots by team, renumbered by each run: positions.
                keys = [name for k in changed if (name := (b.get(k) or {}).get("name") or (a.get(k) or {}).get("name"))]
                if not keys:
                    out.append({"part": "positions", "count": None})
                    continue
                count = len(keys)
            elif part in NAMED_KEYS:
                keys = changed
        else:
            count = None
        out.append({"part": part, "count": count, **({"keys": keys} if keys else {})})
    # Once each: the positions may come with the players' and on their own. The code an older upload recorded is the site's
    # now (`site_code`).
    return list({c["part"]: c for c in out}.values())


# The commits the late page's tip names under the code, at most.
CODE_COMMITS = 5


def code_commits(sent: dict[str, str], now: dict[str, str]) -> list[str] | None:
    """The commits that changed the code of the pages of `sent` (their stamps at the upload) since, newest first, each once,
    CODE_COMMITS at most: then "+N" last. None when git cannot tell for one of them."""
    found = {}
    for name, stamp in sent.items():
        commits = git_check.commits_since(CODE_PAGES[name].resolve(), stamp, now.get(name, ""))
        if commits is None:
            return None
        found.update(dict.fromkeys(commits))
    subjects = [subject for _, subject in sorted(found, reverse=True)]
    return subjects if len(subjects) <= CODE_COMMITS else [*subjects[: CODE_COMMITS - 1], f"+{len(subjects) - CODE_COMMITS + 1}"]


def hosted_state(saved: dict | None, stamp: str, today: date) -> dict:
    """Where the hosted page stands from `saved`, the last upload's HOSTED: behind unless it carried this `stamp`; `day` when
    it was not `today`."""
    if not saved:
        return {"at": None, "day": None, "error": None, "behind": True}
    at = datetime.fromisoformat(saved["at"])
    return {"at": at.strftime("%H:%M"), "day": None if at.date() == today else at.date().isoformat(), "error": None, "behind": saved["stamp"] != stamp}


def read_hosted(match: Path, code: bool = True) -> dict:
    """`hosted_state`, with what changed since the last upload when the page is late and it kept what it sent (`changes`),
    and whether the video's copies were made from other rallies than the review's now (`copiesStale`). With `code`, the site's
    code late (`site_code`) makes it late too, as its last cause: its upload puts the code in."""
    path, sent = match / HOSTED, match / HOSTED_PAGE
    saved = files.read_json(path)
    state = hosted_state(saved, page_stamp(match, tuple(saved.get("pages", OLD_STAMPED)) if saved else STAMPED), date.today())
    state["changes"] = page_changes(json.loads(sent.read_text()), page_content(match)) if state["behind"] and sent.exists() else None
    # An upload before the shared code stamped its pages' code too: late only for its data now.
    if state["behind"] and saved and saved.get("pages", OLD_STAMPED) and state["changes"] == []:
        state["behind"], state["changes"] = False, None
    config = match / matches.PUBLISH
    given = files.read_json(config)
    state["copiesStale"] = bool(given) and matches.copies_stale(match, given)
    late = site_code(Path(given["site"]).expanduser()) if code and saved and given and given.get("site") else None
    if late and late["behind"]:
        state["behind"] = True
        state["changes"] = [*(state["changes"] or []), {**late["change"], "part": "siteCode"}]
    return state


def site_code(site: Path) -> dict:
    """Whether the pages' code online in `site` (as last uploaded or mirrored, `matches.CODE`) is older than this app's, and
    what changed (`change`: the pages whose code did, the commits when git tells them). Before CODE, every site was."""
    sent, now = matches.online_code(site), matches.code_stamps()
    if sent and sent.get("code") == now:
        return {"behind": False, "change": None}
    pages = [name for name in CODE_PAGES if not sent or (sent.get("code") or {}).get(name) != now[name]]
    commits = code_commits({name: sent["code"][name] for name in pages if name in sent["code"]}, now) if sent and sent.get("code") else None
    return {"behind": True, "change": {"part": "code", "count": None, "keys": pages, **({"commits": commits} if commits else {})}}


def code_version() -> str:
    """The code this process runs, as it was on disk when asked: its Python files and the pages' templates."""
    digest = hashlib.sha256()
    for path in [*sorted(Path(__file__).parent.glob("*.py")), *CODE_PAGES.values()]:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


# Taken at start: the code this process runs, whatever is on disk later.
CODE = code_version()


def page_taken(match: Path) -> tuple[dict, str]:
    """The review's page of `match` as an upload starting now takes it: its content and stamp, for `record_hosted`."""
    return page_content(match), page_stamp(match)


def record_hosted(match: Path, taken: tuple[dict, str] | None = None) -> None:
    """The upload of `match`'s page just made: its time, stamp and the code that built it, on disk now (HOSTED), and what it
    sent (HOSTED_PAGE): the page as the upload began (`taken`, `page_taken`), a change made while it ran left late. The stamp
    is the review's page as last built, by older code maybe: `restamp` then takes the next build."""
    content, stamp = taken or page_taken(match)
    # The upload made the commentary's missing audio (`matches.make_voice`) after it took the page, and its build took it:
    # the review's page takes it at its next build, and the online page was shown late for it ("Commentaire").
    data = {k: v for k, v in content["data"].items() if k != "voice"}
    if speech.voice_index(match, data):
        data["voice"] = True
    if data != content["data"]:
        content, stamp = {**content, "data": data}, data_stamp(data)
    # Without the code: the site's, late on its own (`site_code`).
    files.write_text(match / HOSTED_PAGE, json.dumps({"data": content["data"]}, ensure_ascii=False) + "\n")
    files.write_text(match / HOSTED, json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "stamp": stamp, "pages": list(STAMPED), "code": code_version()}) + "\n")


def restamp(match: Path, before: str | None) -> None:
    """The review's page of `match` rebuilt from the same answers, `before` its stamp: when the last upload carried that stamp and
    was built by this code, the online page is the rebuilt one, recorded so. Else the review's newer code showed it late."""
    path = match / HOSTED
    saved = files.read_json(path)
    if not saved or before is None or saved["stamp"] != before or saved.get("code") != CODE or page_stamp(match) == before:
        return
    files.write_text(match / HOSTED_PAGE, json.dumps({"data": page_content(match)["data"]}, ensure_ascii=False) + "\n")
    files.write_text(path, json.dumps({**saved, "stamp": page_stamp(match, tuple(saved.get("pages", OLD_STAMPED)))}) + "\n")

