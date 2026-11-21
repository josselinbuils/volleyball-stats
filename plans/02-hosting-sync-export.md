# Hosting, sync and export — improvements

One entry per finding, most valuable first. IDs are `HOST-NN`.

Read in full: `web.py`, `film.py`, `matches.py`, `sync.py`, `sync_remote.py`, `backup.py`, `backup_remote.py`,
`feedback.py`, `server.py`, `video_copies.py`, `timeline.py`, `framing.py`, `speech.py`, `voice.py`, `blur.py`,
`presence.py`, `docs/nginx.conf`, `docs/hosting.md`. "confirmed" entries were reproduced in the session's scratch
folder (`scratchpad/hosting/`: scripts on the real modules, the test harness of `tests/test_backup_flow.py`, a local
rsync). Nothing was sent to the server; the owner's live nginx configuration was not read.

## HOST-01 One crafted viewer report stops the review of every match

- **Type**: security
- **Impact**: high — anyone who knows the site's address can make the review refuse to open on both machines, for all
  matches, until a log is edited by hand.
- **Effort**: S
- **Confidence**: confirmed
- **Verified** (21 Nov, by the audit's lead): the code path holds (`feedback.py:47`: `report.get("id") in by_id` sits outside the `try`); the public `/feedback` endpoint is live, so this is reachable by anyone today.
- **Where**: `src/volleyball_stats/feedback.py:34-54` (`read`), `:145-156` (`main`),
  `src/volleyball_stats/review.py:807-818` (`reports`), `:176` (`Questions.load`), `:1074` (`report_question`),
  `tests/test_feedback.py`
- **Problem**: `/feedback` is public (nginx only caps 2 KB and 5 a minute per address) and its body is trusted once it
  parses as a JSON object. Run on the real functions (`scratchpad/hosting/fb.py`):
  - `{"id": []}`: `if report.get("id") in by_id` raises `TypeError: unhashable type: 'list'` in `feedback.read`. No
    `match` is needed: `review.reports` reads every `outputs/feedback/*.log` for every match, and
    `Questions(match, fps, court)` (`review.py:2574`) calls it when the review starts. `feedback.fetch_all` hits it too
    (its `finally` reads the log), and the log is synced to the other machine (`backup.SHARED`).
  - `{"match": "<a real folder name>", "time": "abc"}` beside a normal report: `sorted(..., key=lambda r:
    r.get("time") or 0)` raises `'<' not supported between 'str' and 'float'`. The folder name is public (`data.js`).
  - `"clip": "x"` (AttributeError), `"time": [1]` (TypeError) in `report_question`; `"time": 1e400` passes as `inf`
    and `json.dumps` then writes `Infinity`, which the browser's `JSON.parse` refuses.
- **Plan**:
  1. In `feedback.py`, add `clean(report: dict) -> dict | None` and call it in `read` before the `id` test: keep only
     the known keys with their types (`id` str up to 64, `match`/`page`/`kind`/`shown`/`comment` str, cut to a length,
     `time` an int or float with `math.isfinite`, `rally` int or None, `clip` a dict whose `time` is finite and whose
     `type`/`name` are str or None, `team`/`player` int or None); a wrong `id` or `clip` is dropped from the report, a
     report without a str `match` or a finite `time` is skipped. Nothing else to change: every reader goes through `read`.
  2. Tests in `tests/test_feedback.py` (class of `read`): one log holding the five lines above plus a good report
     gives the good report alone; `review.reports` on it does not raise.
- **Check**: `uv run pytest -q tests/test_feedback.py tests/test_review.py`; append `{"received":"x","report":"{\"id\":[]}"}`
  to a copy of a log in a temp `outputs/feedback/` and call `review.reports`.

## HOST-02 A machine whose clock is behind saves into an older copy: the other machine pulls the old files as the new version

- **Type**: data-loss
- **Impact**: high — two-machine owners: work sent from one machine is silently replaced on the other by the copy
  before it, then overwritten on the server by the next push; rare (needs a clock or hour-boundary mismatch), silent.
- **Effort**: M
- **Confidence**: confirmed (clock an hour behind); read (two pushes straddling an hour)
- **Where**: `src/volleyball_stats/backup.py:66` (`copy_id`), `:235-266` (`upload`),
  `src/volleyball_stats/sync_remote.py:47-54` (`newest`), `src/volleyball_stats/sync.py:484-503` (`pull`),
  `tests/test_backup_flow.py`
- **Problem**: the copy a push writes into is named by the sending machine's local hour (`day = copy_id()`), while a
  pull takes each match from the lexicographically last copy holding it (`sync_remote.newest`) with the claim's
  version. Reproduced with the harness of `tests/test_backup_flow.py` (`scratchpad/hosting/test_skew.py`): the Mac
  pushes at `T11`, the PC pulls, changes `answers.json`, pushes with `copy_id` = `T10`:
  ```
  claim {'version': 2, 'pushedBy': 'pc', ...}   copies ['2026-01-01T10', '2026-01-01T11']
  list  {'m': {'version': 2, ..., 'day': '2026-01-01T11'}}
  mac has: first | changed: False            # after sync.pull: version 2 remembered over version 1's files
  ```
  The PC's work is only in `T10`, which `backup.stale` may remove (the match's "newest" is `T11`). A WSL2 clock lags
  after the PC sleeps; a few seconds of difference are enough around the hour. Same result without any skew when a long
  push computed `T10` and another process makes `T11` from `T10` (`snapshot` hard-links every match, outside the claims'
  lock) before the first rsync ends: `T11` holds the match as it was. `sync.verify` would tell, weekly at best.
- **Plan**:
  1. `backup.upload`: after `listed(...)`, `day = max([copy_id(), *days])`: never write behind the newest copy.
  2. Same function, after the match's rsync (`name` given): list again; while a copy newer than `day` exists, run the
     same `rsync_command` into the newest one (only the changed files go) and take it as `day`. The claim's commit
     (`sync.sending`) comes after `backup.backup`, so the version only moves once the newest copy holds the files.
  3. Tests in `tests/test_backup_flow.py`: the scenario above (`hour["id"]` set back before the second machine's push)
     ends with the first machine pulling the second's text; a `snapshot` monkeypatched to create the next hour's copy
     during the rsync ends with that copy holding the pushed file.
- **Check**: `uv run pytest -q tests/test_backup_flow.py tests/test_backup.py tests/test_sync.py`.

## HOST-03 A report sent from the video page is filed at the copy's time, on the wrong rally

- **Type**: bug
- **Impact**: medium — since the copies are shortened (16 Nov) a viewer's report made while watching the video opens
  another rally in the review: the feedback loop the page exists for points at the wrong moment.
- **Effort**: S
- **Confidence**: read (no report was received since 16 Nov to confirm on data: the logs of 17-18 Nov hold none)
- **Where**: `web/src/components/Watch/Feedback.tsx:73-83`, `src/volleyball_stats/review.py:1074` (`report_question`),
  `:1095` (the question's `time`), `web/src/lib/playlist.ts` (`rallyReported`), `tests/test_review.py`
- **Problem**: the page behind the password is built on the copy's timeline (`web.build`: `timeline.retimed(data,
  pieces)`), so `video.currentTime` and `clip.time` are the copy's seconds; the review's page stays on the source's.
  `report_question` does `at = float((report.get("clip") or {}).get("time") or report.get("time") or 0)` and looks for
  the rally with `r["start"] <= at <= r["end"]` in the review's rallies; nothing maps back (`timeline.to_source` is
  never called in `review.py` or `feedback.py`) and `report["rally"]` is ignored. On the two matches reviewed here the
  copies play 66.9 min in 39.5 and 84.5 in 46.0: a report at the copy's minute 30 lands around the source's minute 30,
  some twenty minutes before the rally it is about. The public page (no video) is on the source's time and is right.
- **Plan**:
  1. `Feedback.tsx`: when the rally (`rallyReported`) carries `real` (the retimed pages only, `timeline.retimed`),
     add `real` to the report: `rally.real[0] + (t - rally.start) * (rally.real[1] - rally.real[0]) / (rally.end -
     rally.start)` clamped to `rally.real`, `t` being the clip's time when a clip plays, else the video's.
  2. `report_question`: `at` is `report["real"]` when present (a finite number, see HOST-01), else as today; older
     reports are unchanged.
  3. Tests: a helper test beside `Feedback.tsx` (a rally with `real` gives the source's second); in
     `tests/test_review.py`, a report with `time` in another rally and `real` in rally k is filed under k.
- **Check**: `cd web && npx tsc --noEmit -p . && npm test`; `uv run pytest -q tests/test_review.py -k report`.

## HOST-04 An upload from the machine that still has the old password puts the old key back on the server

- **Type**: security
- **Impact**: medium — two-machine owners: after "change the password" on one machine, an upload from the other brings
  the former password back for every match's video and locks out the new one.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/matches.py:786-788`, `:853-854` (`upload_all`), `:436-459` (`set_password`),
  `src/volleyball_stats/sync.py:335-356` (`merge_shared`), `tests/test_matches.py`
- **Problem**: `upload_all` reads `key = video_key(files.root(hosted[0][0]))` from this machine's
  `outputs/video_password.json` and runs `if guarded: install_key(config, key)` on every upload with a video. That
  file reaches the other machine only through `merge_shared` (`backup.SHARED`, `--update`): at a push, a pull or the
  ten-minute timer, and only with sync on. A machine started after days and asked to "Mettre en ligne" at once
  rewrites `video_key.conf` with the old fingerprint; the final `opens(page, key)` check passes (it tests the key just
  installed). Its next sync then brings the newer file, and the app shows a password the server no longer takes.
- **Plan**:
  1. In `upload_all`, before `video_key(...)`: when `sync.server(outputs)` is set, bring the password file alone from
     the server's newest copy (`sync.rsync(config, f"{backup.ROOT}/{sync.newest_copy(config)}/{PASSWORD}",
     outputs / PASSWORD, "--update")`, a missing file ignored as `merge_shared` does). One ssh round trip more.
  2. Test in `tests/test_matches.py`: `sync.rsync` monkeypatched to write a newer password file; `install_key`
     receives the fingerprint of the newer one.
- **Check**: `uv run pytest -q tests/test_matches.py -k password`; by hand: change the password on machine A, upload
  from B without waiting, the new password still opens the video page.

## HOST-05 An upload removes the files the online pages use before their replacements land

- **Type**: bug
- **Impact**: medium — viewers during an upload (minutes, hours with new video copies): the old `index.html` asks
  for scripts, voice clips or films already deleted.
- **Effort**: S
- **Confidence**: confirmed locally (openrsync on both ends); the server's rsync not checked
- **Where**: `src/volleyball_stats/matches.py:659` (`upload_command`), `src/volleyball_stats/backup.py:152`
  (`rsync_command`), `tests/test_matches.py`
- **Problem**: `"rsync", "-rt", "--delete", "--delay-updates"`: `--delay-updates` renames the new files at the very
  end, but `--delete` alone deletes before or during the transfer. Local run (`scratchpad/hosting/rs`, a 300 MB file
  to make it last), looked at mid-transfer:
  ```
  dst/assets: .~tmp~            # index-OLD.js already gone, index-NEW.js not yet there
  dst/index.html: old           # still the page asking for index-OLD.js
  ```
  With `--delete-after` (and with `--delete-delay`) the same run keeps `index-OLD.js` until the end (exit 0, new
  files in place after), and its dry run still prints `*deleting assets/...`. The docstring of
  `backup.rsync_command` ("a copy cut off keeps its files as they were") is wrong for the same reason.
- **Plan**:
  1. `upload_command` and `rsync_command`: `--delete-after` in place of `--delete` (understood by openrsync's protocol
     29 and rsync 3; `--delete-delay` is the cheaper one where both ends are rsync 3).
  2. Check that the dry run's parsing still finds the deletions (`removed_pages`, `removed_films`, `files_to_send`,
     `backup.sent_bytes`): their tests in `tests/test_matches.py` and `tests/test_backup.py`, plus one asserting the flag.
- **Check**: the local run above with the new flag; `uv run pytest -q tests/test_matches.py tests/test_backup.py
  tests/test_backup_flow.py`; one real upload watched by the owner (the server's rsync).

## HOST-06 A close call whose bounce falls just after the rally's end is neither slowed nor held

- **Type**: bug
- **Impact**: medium — the hosted video: the slow motion and the held frame, made for the balls on the line, are
  missing for the calls that end a rally at their landing, and the Site tab says the copies wait to be made again.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/timeline.py:53-60` (`plan`'s `rally`), `:26-36` (`bounce_at`),
  `src/volleyball_stats/web.py:584` (`closed`), `tests/test_timeline.py`
- **Problem**: `for b in (b for b in held if start <= b <= end)`. `web.closed` ends a checked rally at its landing
  and `bounce_at` takes the ball's lowest place within `BOUNCE_S` (0.3 s) of it, so the bounce can come a few
  hundredths after `end`. `timeline.plan` run on one of the owner's reviewed matches: 4 line calls, bounces at 106.6
  (end 106.6), 756.963 (end 756.98), 996.443 (end 996.47) and 1019.023 (end 1018.95): 3 held frames for 4 calls. The
  fourth falls in the break, played fast or cut. `timeline.moved` compares the number of holds, so such a match
  can also read as "copies to make again".
- **Plan**:
  1. In `plan`, `rally(start, end, limit)` takes the bounces up to `min(end + BOUNCE_S, limit)` (`limit`: the next
     rally's start, the video's end for the last), plays to `max(end, b)` and returns that time; the break that
     follows starts from it.
  2. Test in `tests/test_timeline.py` beside `test_a_close_call_slows_down_to_its_bounce_and_holds_it`: a bounce 0.07 s
     after the rally's end is held, the map stays gapless and increasing.
- **Check**: `uv run pytest -q tests/test_timeline.py tests/test_video_copies.py tests/test_framing.py`; the scratch
  count again (4 holds for 4 calls). The copies of the matches concerned are then offered to be made again: expected.

## HOST-07 The copies' record travels with the match: on the other machine the video page is built for the source's timeline

- **Type**: bug
- **Impact**: medium — a machine holding its own copies of a match synced from the other one uploads a video page
  whose rallies, score and zoom are on the wrong times, with no error.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/video_copies.py:285-297` (`record`, `recorded`), `src/volleyball_stats/web.py:2007-2016`
  (`build`), `src/volleyball_stats/matches.py:796-806` (`upload_all`'s checks), `tests/test_video_copies.py`,
  `tests/test_matches.py`
- **Problem**: `copies_made.json` sits in the match folder, which is synced (not in `backup.SKIP`); the copies are in
  `data/matches/MATCH/reencoded/`, which is not. `recorded` returns None when `saved.get("size") !=
  light.stat().st_size`, and two machines never encode the same bytes. `web.build` then does `data["zoomed"] = made is
  not None` and keeps `pieces = None`: a page on the source's time, zooming itself, over copies that are cut and
  shortened. `upload_all` only refuses missing copies (`copies_gone`). `copies_stale` does return True for it, but
  that only shows "to make again" in the Site tab.
- **Plan**:
  1. `video_copies.record`/`recorded`: keep the record beside the copies (`light.parent / MADE`), reading the match
     folder's as a fallback for those already made.
  2. `upload_all`: with the video, `recorded(match, light) is None` raises `RuntimeError` ("video copies made
     otherwise: make them again") through `explain` (`web/src/lib/errors.ts`), before any build.
  3. Tests: `recorded` finds the record beside the copy; `upload_all` refuses a match whose record names another size.
- **Check**: `uv run pytest -q tests/test_video_copies.py tests/test_matches.py`.

## HOST-08 A copy whose source stops being read is finished with one frozen frame and accepted

- **Type**: bug
- **Impact**: medium — a decoder that dies mid-match (GPU session lost, a damaged file) gives hours of video stuck on
  one picture, with the right length, uploaded as good.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/video_copies.py:226-248` (`encode`), `:114` (`sound`), `tests/test_video_copies.py`
- **Problem**:
  ```python
  while current < wanted[n]:
      if reader.stdout.readinto(frame) != frame.nbytes:
          break
      current = next(delivered)
  ...
  writer.stdin.write(cut(frame, ...))
  ```
  When the reader ends, every later `n` writes the last `frame` again. The reader's exit code is then ignored as
  soon as one frame was sent (`process is writer or not sent`), and `reader.kill()` hides it anyway. The only check
  after, the copy's duration (`make`), passes: the count of frames is right. The fallback from a refused GPU decoder
  only covers a failure before the first frame.
- **Plan**:
  1. In `encode`: a short read while `current < wanted[n]` raises `RuntimeError` with the reader's last error line
     when it happens more than `FPS` frames before `wanted[-1]` (the last frames of a file may be missing), after
     closing the writer; `make`'s existing `except RuntimeError` then retries on the CPU.
  2. `sound`: check ffmpeg's return code where it reads the source (a failure pads silence today).
  3. Test in `tests/test_video_copies.py`: `reading` monkeypatched to a command giving 10 frames for a 100-frame
     copy raises and leaves no copy (as `test_a_copy_cut_short_does_not_appear`).
- **Check**: `uv run pytest -q tests/test_video_copies.py`.

## HOST-09 Remote commands and `rsync -e` built from unquoted settings

- **Type**: security
- **Impact**: medium with "Réseau local" on (anyone on the network can save the Site tab's fields), low otherwise — a
  folder or key path with a space breaks the reports' fetch, pulls and the weekly check; a crafted one runs commands.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/feedback.py:66-70` (`fetch`), `src/volleyball_stats/sync.py:399` (`verify`), `:479`
  (`rsync`), `src/volleyball_stats/server.py:18` (`ADDRESS`), `:31-34` (`save`), `tests/test_feedback.py`,
  `tests/test_sync.py`
- **Problem**:
  - `subprocess.run(["ssh", *ssh, host, f": > {online}"])`: `online` comes from the Site tab's folder, unquoted, run
    by the server's shell as the upload user (root in the docs). `/srv/my site/site` empties `/srv/my` and fails;
    `/srv/x;reboot/site` runs `reboot`. `backup.free_gb` and `matches.key_command` do quote (`shlex.quote`).
  - `"-e", " ".join(ssh)` in `sync.rsync` and `sync.verify`, while `backup.rsync_command` and `matches.ssh_shell` use
    `shlex.join`: a key at `~/My Keys/id` works for uploads and backups and breaks every pull, restore and verify; a
    key field `x -o ProxyCommand=...` becomes ssh options run on this machine.
  - `ADDRESS = re.compile(r"[\w.-]+@[\w.-]+")` lets a user or host start with `-`; `save` only checks the key is not
    empty.
- **Plan**:
  1. `feedback.fetch`: `f": > {shlex.quote(online)}"` (and `scp`'s `f"{host}:{shlex.quote(online)}"` stays as is on
     OpenSSH 9's sftp mode: test with a space before quoting it).
  2. `sync.rsync`, `sync.verify`: `shlex.join(ssh)`.
  3. `server.ADDRESS`: `[\w.][\w.-]*@[\w.][\w.-]*`; `save` refuses a key path that is not an existing file.
  4. Tests: `fetch` with a folder holding a space (`tests/test_feedback.py`, whose
     `test_keeps_a_dated_copy_then_empties_the_online_log` asserts the exact command: update it); `sync.rsync` with a
     key path holding a space (the harness of `tests/test_backup_flow.py`).
- **Check**: `uv run pytest -q tests/test_feedback.py tests/test_sync.py tests/test_backup_flow.py tests/test_server.py`.

## HOST-10 Fetching the reports can drop the ones that arrive meanwhile, and waits for ever on a stalled link

- **Type**: data-loss
- **Impact**: medium — a report posted between the copy and the emptying is lost; one hung ssh stops every later
  fetch (the timer's and "Charger les signalements") until the review restarts.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/feedback.py:57-71` (`fetch`), `:24` (`fetching`), `src/volleyball_stats/matches.py:565-568`
  (`ssh_options`), `tests/test_feedback.py`
- **Problem**: `scp` copies the log, then a second connection runs `: > log`: lines nginx appended in between are
  truncated unread. Neither `subprocess.run` has a `timeout=` and `ssh_options` sets `ConnectTimeout=10` only, so a
  connection that stalls after it opened never returns; `fetch_all` holds the `fetching` lock all along.
- **Plan**:
  1. `fetch`: after the copy, remove from the server only what was read, in one command:
     `n=<bytes copied>; f=<quoted log>; tail -c +$((n+1)) "$f" > "$f.new" && cat "$f.new" > "$f" && rm "$f.new"`
     (written in place: nginx keeps the file open in append mode, as the current `: >` relies on). The window shrinks
     from two connections to one `cat`.
  2. `timeout=120` on both calls (a `TimeoutExpired` reported as the other failures of `fetch_all`); add
     `-o ServerAliveInterval=15 -o ServerAliveCountMax=3` to `matches.ssh_options` (every ssh, scp and rsync gains it).
  3. Test in `tests/test_feedback.py`, with a real file and `sh -c` as the fake ssh: a line appended to the log
     between the copy and the cut is still in the online log after `fetch` (the existing test asserts `: > log`:
     update it).
- **Check**: `uv run pytest -q tests/test_feedback.py tests/test_matches.py`.

## HOST-11 A match just pulled reads as changed here and is sent back as a new version

- **Type**: bug
- **Impact**: low to medium — every pull of a match with video copies costs a push, a version and a server copy; a
  change made meanwhile on the other machine becomes a false "changed on both" question.
- **Effort**: S
- **Confidence**: confirmed
- **Duplicate** (21 Nov, by the audit's lead): seen on the real state, with a higher impact than rated here: LIVE-02 (`plans/00-live-findings.md`): all four matches read as changed on the Mac right after "Tout récupérer".
- **Where**: `src/volleyball_stats/sync.py:503-504` (`pull`), `:510-522` (`relative_copies`),
  `src/volleyball_stats/matches.py:545` (`add_copies`), `tests/test_sync.py`
- **Problem**: `pull` calls `remember(match, version, backup.signature([match]))`, then `relative_copies(match)`
  rewrites `publish.json` (the other machine's absolute `light`/`av1`/`small` paths), which moves the signature.
  Reproduced with the flow harness (`scratchpad/hosting/test_pull.py`), `publish.json` holding
  `"light": "/home/pc/.../data/matches/m/reencoded/m_1440p.mp4"`:
  ```
  light: data/matches/m/reencoded/m_1440p.mp4 | changed: True
  ```
  `add_copies` writes `str(path.resolve())`, so every match with copies carries one machine's absolute paths.
- **Plan**:
  1. `pull`: call `relative_copies(match)` inside the `with alone(match)` block, before `remember`.
  2. Test in `tests/test_sync.py` beside `test_the_other_machines_paths_become_the_projects`: after a pull of such a
     match, `sync.changed(match)` is False.
- **Check**: `uv run pytest -q tests/test_sync.py tests/test_backup_flow.py`.

## HOST-12 Films and link previews use fonts found on macOS only

- **Type**: cross-platform
- **Impact**: medium — on the PC (WSL2, the machine that encodes) the films and the shared links' cards are drawn
  with OpenCV's fallback font: another look than the Mac's, zeros slashed in the scores.
- **Effort**: M
- **Confidence**: read (not run on Linux here)
- **Where**: `src/volleyball_stats/film.py:48`, `:1217-1219` (`font`), `:1267`, `src/volleyball_stats/matches.py:78`,
  `:146` (`_write`), `tests/test_film.py`, `tests/test_matches.py`
- **Problem**: `FONTS = Path("/System/Library/Fonts/Supplemental")` with `font("Arial Bold Italic.ttf")`,
  `"DIN Alternate Bold.ttf"`, `"DIN Condensed Bold.ttf"`, and `CARD_FONT = Path("/System/Library/Fonts/Supplemental/Arial
  Bold.ttf")`; both fall back to `"sans"` when the file is missing, and `matches.py`'s own comment says what that
  costs: "OpenCV's own font slashes its zeros, a score's "0" then reads "Ø"". `preview.png` is rebuilt by whichever
  machine uploads, so the card changes with the machine. CLAUDE.md: nothing relies on one system.
- **Plan**:
  1. One helper (in `film.py`, used by `matches._write`): the first existing file among the macOS folder,
     `/mnt/c/Windows/Fonts` and `C:\Windows\Fonts` (`arialbd.ttf`, `arialbi.ttf`), `/usr/share/fonts/**` (Liberation
     Sans Bold / Bold Italic, DejaVu Sans Bold). DIN has no free twin on Windows or Linux.
  2. Owner's call, for the same look everywhere: ship three OFL fonts in the package (e.g. a condensed bold, a bold, a
     bold italic, some 300 KB) and drop the system lookups. No Python dependency either way.
  3. Test: the helper returns an existing file on the CI's Linux and on macOS; the card's text is not drawn with
     `"sans"` when a listed font exists.
- **Check**: `uv run pytest -q tests/test_film.py tests/test_matches.py`; one film and one `preview.png` made on the PC
  and on the Mac, compared.

## HOST-13 Films assume a 3840x2160 source at 50 fps and say nothing on another

- **Type**: cross-platform
- **Impact**: medium for any other camera (1080p, 4K 30/60): torn pictures or no film, with no message; none for the
  owner's camera.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/film.py:45-46`, `:926-929` (`read_picture`), `:633` (`status`), `:1975` (`build`),
  `tests/test_film.py`
- **Problem**: `SOURCE_W, SOURCE_H = 3840, 2160`, `FPS = 50.0`; `read_picture` reads `SOURCE_W * SOURCE_H * 3` bytes
  per frame and returns None on a short read, so a 1080p source yields no picture at all (each shot is skipped, see
  HOST-15) and a larger one yields sheared ones; frames are addressed with `round(moment * FPS)`. Neither `status`
  nor `build` looks at `decode.size(video)` or the page's `fps`. The rest of the pipeline reads both.
- **Plan**:
  1. Smallest: `film.build` raises `RuntimeError("films need a 3840x2160 video at 50 fps")` otherwise (through
     `explain`), and the review offers no film for such a match (`status` total 0 needs the video: pass it from its
     caller).
  2. Later, the generic version: the size and rate read once in `Maker.__init__` and passed down instead of the
     three constants.
  3. Test in `tests/test_film.py`: `build` on a 1920x1080 test clip raises.
- **Check**: `uv run pytest -q tests/test_film.py`.

## HOST-14 The server's limits count per address only, and nothing caps the reports' log

- **Type**: security
- **Impact**: low — a sender with an IPv6 range (a new address per request) can try video passwords without the
  10-a-minute limit and grow `feedback.log` at will on a server that also holds the owner's sites and the backups.
- **Effort**: S
- **Confidence**: read (`docs/nginx.conf`; the live configuration and any proxy in front were not read)
- **Where**: `docs/nginx.conf:5`, `:23-27`, `:69-77`, `docs/hosting.md` (your own server), `src/volleyball_stats/matches.py:54`
- **Problem**: `limit_req_zone $binary_remote_addr zone=feedback:1m rate=5r/m;` and `$video_bad` (the address too)
  are the only limits. The cookie is the bare SHA-256 of a password of 6 characters or more (`PASSWORD_MIN`), so the
  guess rate is the only defence of a short one. The log grows 2 KB a request until the next fetch.
- **Plan**:
  1. `docs/nginx.conf`: a second zone keyed on `$server_name` for `/feedback` (e.g. 60 a minute for the whole site)
     and one for wrong keys (e.g. 600 a minute), each as a second `limit_req` line in its location.
  2. Same file: `add_header X-Content-Type-Options nosniff always;` in the server block and its locations (nginx
     drops inherited `add_header` lines where a location has its own).
  3. `docs/hosting.md`: one line that the owner's server needs the new lines copied (the app does not write this file).
- **Check**: `nginx -t` on the server (the owner); `ab -n 100` on `/feedback` from one machine answers 503/429 past
  the site's rate.

## HOST-15 A film whose decoder fails is made with frozen or missing shots and recorded as done

- **Type**: bug
- **Impact**: low to medium — a film made while the GPU is busy can freeze or drop a shot, its sound running on; its
  hash is recorded, so it is never made again.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/film.py:906-914` (`decoder`), `:1586-1597` (the shot's loop), `:1359-1378`
  (`Maker.make`), `tests/test_film.py`
- **Problem**: `decoder` runs ffmpeg with `-v quiet` on the GPU when it can (`decode.hardware`), with no CPU
  fallback (`video_copies.make` has one: "The GPU busy with other work may refuse another decoder"), three films at
  once. In the loop, `if next_picture is None: break` then `if picture is None: continue`: a decoder that stops gives
  the last picture for the rest of the shot, one that never starts gives no frame at all, while `self.sound()` keeps
  the shot's full length. `encoder.wait()` is not checked either, and a failed mux leaves `draft-*.video.mp4` and
  `draft-*.pcm` behind.
- **Plan**:
  1. In the shot's loop: a None picture before the shot's last 2 frames raises `RuntimeError`; `Maker.shoot` catches
     the first one per shot and reads again with `decode.hardware` bypassed (a `flags` argument to `decoder`).
  2. `make`: `if encoder.wait(): raise RuntimeError(...)`; unlink `silent` and `sound` in a `finally`.
  3. Test in `tests/test_film.py`: `decoder` monkeypatched to end after 3 frames makes `make` raise.
- **Check**: `uv run pytest -q tests/test_film.py`.

## HOST-16 A push that fails leaves the match marked "sending" for an hour; a pull never looks at that mark

- **Type**: data-loss
- **Impact**: low — after a cut connection the other machine is told to "try again in a moment" for up to an hour;
  a pull during another machine's push takes a copy still being written.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/sync.py:239-259` (`sending`), `:484-503` (`pull`),
  `src/volleyball_stats/sync_remote.py:57-88` (`run`), `src/volleyball_stats/backup.py:38` (`SKIP`), `tests/test_sync.py`
- **Problem**: `begin` writes `pushing = {machine, at}`; when `backup.backup(match)` raises, nothing clears it and
  `busy` stays true for `COPY_S` (3600 s) for the other machine. The code's own note at `:255` covers the second
  half: `pull` reads `list` (which carries `pushing`) and never checks it. An interrupted rsync also leaves `.~tmp~`
  folders in the server's copy, which `SKIP` does not exclude from a pull or from `verify`.
- **Plan**:
  1. `sync_remote.run`: an `abort` op clearing `pushing` when it is this machine's; `sending` calls it in an
     `except` around `merge_shared`/`backup.backup` before re-raising.
  2. `pull`: when `found[name]["pushing"]` is another machine's and younger than `COPY_S`, raise the same "is sending
     it: try again in a moment" as `sending`.
  3. Add `".~tmp~"` to `backup.SKIP`.
  4. Tests in `tests/test_sync.py`: a failed push leaves `pushing` None; a pull while another machine sends raises.
- **Check**: `uv run pytest -q tests/test_sync.py tests/test_backup_flow.py`.

## HOST-17 The players' films are copied beside a page whose video is blurred

- **Type**: security
- **Impact**: low — only `stats web --footage blur-opponents|blur-all` (the app never builds such a page): the page
  hides a team in the video and offers films showing everyone.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/web.py:1443-1444` (`write_site`), `:2019` (`build`), `tests/test_web.py`
- **Problem**: `shown_films = copy_films(films if video else None, ...)` with the comment "Real footage: only beside a
  page that has the video". With a blurred footage `video` is the blurred copy, so the test passes and the films,
  cut from the unblurred source, land in `SITE/films/`.
- **Plan**:
  1. `build`: pass `match / "films"` to `write_site` only when `blurred == set()` (footage `full`), else None.
  2. Test in `tests/test_web.py`: a build with `blur-all` and a films folder writes no `films/` and no `data["films"]`.
- **Check**: `uv run pytest -q tests/test_web.py -k film`.

## HOST-18 The blurred copy is encoded straight into its final name

- **Type**: bug
- **Impact**: low — an interrupted or failed blur leaves a partial `*_blurred_N.mp4` that the next build takes as done.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/blur.py:94-107` (`write`), `src/volleyball_stats/web.py:1925-1928` (`footage_video`),
  `tests/test_blur.py`
- **Problem**: ffmpeg writes to `str(out)`; `footage_video` reuses the file when `out.exists()` and it is newer than
  the tracks. A stopped run (Ctrl-C, a full disk) leaves exactly that. `video_copies.make` already does it right
  (`.part.mp4`, then `replace`).
- **Plan**:
  1. `blur.write`: encode into `out.with_name(f"{out.stem}.part.mp4")`, `replace(out)` on success, unlink in a
     `finally`.
  2. Test in `tests/test_blur.py`: ffmpeg monkeypatched to fail leaves no `out`.
- **Check**: `uv run pytest -q tests/test_blur.py`.

## HOST-19 The videos' key is written before nginx's configuration is tested

- **Type**: bug
- **Impact**: low — on a server whose nginx test fails for another site, "change the password" reports a failure and
  keeps the old password in the app, while the new key waits in the file for the next reload by anyone.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/matches.py:548-556` (`key_command`), `:436-449` (`set_password`), `tests/test_matches.py`
- **Problem**: `printf '%s\n' LINE > video_key.conf && if ...; then ... 'nginx -t -q && nginx -s reload'`: the file
  is replaced first. `set_password`'s docstring says "RuntimeError when the server does not take it (nothing
  changes)": the file did change.
- **Plan**:
  1. `key_command`: keep the former content and put it back when the reload part fails:
     `old=$(cat KEYS 2>/dev/null); printf ... > KEYS && { RELOAD || { printf '%s\n' "$old" > KEYS; false; }; }`
     (written in place both times: the container mounts the file by its inode).
  2. Test in `tests/test_matches.py`: the command run with a fake `nginx` that fails leaves the file as it was.
- **Check**: `uv run pytest -q tests/test_matches.py -k key`.

## HOST-20 The copies set aside by "keep this machine's" are never listed, restorable or removed

- **Type**: maintainability
- **Impact**: low — each forced push leaves a full hard-linked copy in `aside/` that holds its room for ever once the
  dated copies it shares files with are gone, and that the Site tab cannot show or bring back.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/sync_remote.py:72-76`, `src/volleyball_stats/server.py:134` (`SIZES`), `:144` (`copies`),
  `src/volleyball_stats/backup.py:99-104` (`stale`), `docs/hosting.md:340`
- **Problem**: `aside = os.path.join(root, ASIDE, time.strftime(...) + "-v" + str(record["version"]))` then `cp -al`.
  `backup.listing`, `SIZES` (`[0-9][0-9][0-9][0-9]-...`) and `stale` only see the dated folders; `server.restore`
  only takes a `COPY`. The one copy made precisely because two versions disagreed is the one the app cannot reach.
- **Plan**:
  1. `backup.upload`'s last remote command: also remove the `aside/*` folders older than the oldest dated copy kept
     (`find ROOT/aside -mindepth 1 -maxdepth 1 ! -newer ROOT/<oldest kept copy> -exec rm -rf {} +`: the copies' folders
     carry their last save's time, `touch` in the same command).
  2. `docs/hosting.md`: say how long they stay. Listing them in the Site tab only if the owner wants it.
  3. Test in `tests/test_backup_flow.py`: an aside folder dated before the copies kept goes with them.
- **Check**: `uv run pytest -q tests/test_backup_flow.py tests/test_sync.py`.

## HOST-21 Nothing goes online when the commentary's audio cannot be made

- **Type**: UX
- **Impact**: low — a voice failure (the first download of the model offline, a `durations.json` cut mid-write) stops
  every upload and export, of every match, on a part of the page that is optional.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/matches.py:598-602` (`make_voice`), `:818`, `:899`,
  `src/volleyball_stats/voice.py:50-66`, `src/volleyball_stats/speech.py:509-511` (`voice_index`), `tests/test_speech.py`
- **Problem**: `make_voice(match)` runs for each match of each upload and export and raises `RuntimeError(f"voice:
  ...")`. In `voice.py`, `path.write_text(json.dumps(durations))` every 25 lines, in place: a stop mid-write leaves
  invalid JSON, and `json.loads(path.read_text())` then fails at every run, in `voice.py` and in `speech.voice_index`
  (every build of the match's pages, the review's included), until the file is deleted by hand.
- **Plan**:
  1. `voice.py`: write `durations.json` with `files.write_text` (atomic). One reader for both modules (in `speech.py`)
     returning `{}` for a file that does not parse: the clips are made again.
  2. Owner's call: in `upload_all` and `export`, a voice failure is told as a stage's warning and the build goes on
     with the audio there (`voice_index` works from `durations.json` alone), or it stays blocking as today.
  3. Test in `tests/test_speech.py`: `voice_index` on a match whose `durations.json` holds `{"a` returns None.
- **Check**: `uv run pytest -q tests/test_speech.py tests/test_matches.py`.

## HOST-22 In a player's film the commentary can talk over the replay's own line

- **Type**: bug
- **Impact**: low — two voice lines overlapping after a replay about the film's player.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/film.py:368-373` (`lines_of`), `tests/test_film.py`
- **Problem**:
  ```python
  elif shot["kind"] == "replay" and voice["replay"].get(name) and shot["start"] >= free:
      out.append({"at": shot["start"], "file": voice["replay"][name]})
  elif shot["kind"] == "replay" and voice["replay"].get(shot.get("who", {}).get("name")) and shot["start"] >= free:
      out.append({...})
      free = shot["start"] + shot["length"]
      free = shot["start"] + shot["length"]
  ```
  The line is doubled in the second branch and missing in the first: after the player's own replay line `free` does
  not move, so the next live shot's first line is placed without waiting.
- **Plan**:
  1. Move one of the two `free = ...` lines into the first branch.
  2. Test in `tests/test_film.py`: a replay of `name` followed by a live shot whose line starts inside it gives one
     line, not two.
- **Check**: `uv run pytest -q tests/test_film.py -k lines`.

## HOST-23 A name's pronunciation is replaced inside longer words

- **Type**: bug
- **Impact**: low — a short name with a pronunciation set changes every word that contains it (another player's
  longer name, a common word), in the voice only.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/speech.py:455-461` (`spelled`), `tests/test_speech.py`
- **Problem**: `for word, sound in spoken.items(): text = text.replace(word, sound)`: a substring replace, in the
  dictionary's order (a name that is the start of another one is replaced inside it first).
- **Plan**:
  1. One pass: `re.sub(r"(?<!\w)(" + "|".join(map(re.escape, sorted(spoken, key=len, reverse=True))) + r")(?!\w)",
     lambda m: spoken[m.group()], text)` when `spoken` is not empty.
  2. Test in `tests/test_speech.py`: `spelled("Ana et Anabel", {"Ana": "Anna"})` keeps "Anabel". The clips' names come
     from the spelled text (`clip_name`): the lines concerned are made again once, the others keep their audio.
- **Check**: `uv run pytest -q tests/test_speech.py`.

## HOST-24 Every failure of the shared files' merge is read as "not in that copy"

- **Type**: bug
- **Impact**: low — a network cut during a sync skips the courts, the club or the password without a word; the
  next step then uploads this machine's older view of them (`--update` saves the newer file, not a missing merge of
  the roster or the reports).
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/sync.py:347-355` (`merge_shared`), `:476-481` (`rsync`), `tests/test_sync.py`
- **Problem**: `except RuntimeError: # Not in that copy. pass` around `rsync(...)` and `join_lines(...)`, where
  `rsync` raises `RuntimeError(stderr)` for any exit code (timeouts, refused connections, a full disk here).
- **Plan**:
  1. `sync.rsync`: raise `LookupError` when rsync's exit code is 23 and its error names a missing file ("No such
     file or directory"), `RuntimeError` otherwise; `merge_shared` catches `LookupError` only. `pull` already raises
     `LookupError` for a missing match: check its callers treat the two alike.
  2. Test in `tests/test_backup_flow.py`: `rsync` monkeypatched to raise `RuntimeError("timeout")` makes
     `keep_shared` raise instead of passing.
- **Check**: `uv run pytest -q tests/test_sync.py tests/test_backup_flow.py`.

## HOST-25 The last guard before an upload only looks for `.mp4` outside `video/`

- **Type**: security
- **Impact**: low — defence in depth for the privacy rule: nothing writes them there today, but a player picture, a
  poster or a `.mov` left in the site folder outside `video/` would go online unnoticed.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/matches.py:367-369` (`unguarded_videos`), `:855-858`, `tests/test_matches.py`
- **Problem**: `[p for p in site.rglob("*.mp4") if "video" not in p.relative_to(site).parts[:-1]]`. The public build
  removes `players/`, the poster and the films by construction (checked, see "Looked at, fine"); this guard is the
  only check that does not depend on the build being right, and it knows one extension.
- **Plan**:
  1. Rename to `unguarded_footage` and also return, outside a `video` folder: `*.mov`, `*.m4v`, `*.webm`, any file
     under a `players/` or `films/` folder, `poster.webp`. `preview.png` (drawn, no footage) and `club/` stay allowed.
  2. Test in `tests/test_matches.py`: each of them placed in `SITE/MATCH/` is returned, the same under
     `SITE/MATCH/video/` is not.
- **Check**: `uv run pytest -q tests/test_matches.py -k unguarded`; `unguarded_footage` on the real
  `outputs/hosted` returns nothing.

## HOST-26 A space around the videos' password makes it wrong

- **Type**: UX
- **Impact**: low — a phone's keyboard adds a space after a suggested word: the viewer's right password is refused; a
  password saved with a pasted space cannot be typed from a message.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/matches.py:440-442` (`set_password`), `web/src/components/VideoChoice.tsx:92`
- **Problem**: `len(new.strip()) < PASSWORD_MIN` checks the stripped length, then `fingerprint(new)` and
  `{"password": new}` keep the spaces; the page hashes what was typed as is (`fingerprint(password)`).
- **Plan**:
  1. `set_password`: `new = new.strip()` before the checks.
  2. `VideoChoice.tsx`: try `password.trim()` when it differs and the typed one is refused (a password saved with
     spaces before this change keeps working).
  3. Tests: `tests/test_matches.py` (a password with spaces is stored stripped); the page's test beside
     `VideoChoice.tsx` if one exists, else `lib/videoPassword.test.ts`.
- **Check**: `uv run pytest -q tests/test_matches.py -k password`; `cd web && npm test`.

## HOST-27 A club or sponsor picture OpenCV cannot read stops every build with an AttributeError

- **Type**: bug
- **Impact**: low — a damaged logo, or a theme whose `brand.json` names a missing file, fails every page build and
  upload with `'NoneType' object has no attribute 'shape'`.
- **Effort**: S
- **Confidence**: read (the app only accepts `.png/.jpg/.jpeg/.webp` by suffix, `club_settings.PICTURES`: the
  content is not checked)
- **Where**: `src/volleyball_stats/web.py:515-516`, `:525-526` (`club_page`), `tests/test_web.py`
- **Problem**: `logo = cv2.imread(...)` then `if logo.shape[0] > LOGO_PX`; same for each sponsor's picture.
  `cv2.imread` returns None for a missing or unreadable file.
- **Plan**:
  1. `club_page`: a None logo drops `data["logo"]` (the page shows the club's name); a None sponsor picture drops the
     sponsor's `logo` (the code's own comment: "A sponsor without a logo shows as text").
  2. Test in `tests/test_web.py`: a `club.json` naming a text file as its logo builds.
- **Check**: `uv run pytest -q tests/test_web.py -k club`.

## HOST-28 The same small pieces are written several times across the export's modules

- **Type**: maintainability
- **Impact**: low — a fix made in one copy misses the others (the line calls' rule is the one that matters: the page
  and the films must agree on in and out).
- **Effort**: M
- **Confidence**: read
- **Where**: `src/volleyball_stats/film.py:127` (`read_page`), `:177-185` (`outside`, `line_call`), `:348`
  (`voice_index`), `:1381` (`long_date`), `src/volleyball_stats/web.py:1005-1014` (`outside`, `line_calls`),
  `src/volleyball_stats/matches.py:97` (`page_of`), `:132` (`french_date`), `:488-502` (`review_cut`),
  `src/volleyball_stats/voice.py:42`, `src/volleyball_stats/review.py` (`page_data`)
- **Problem**: `text[text.index("{") : text.rindex("}") + 1]` then `json.loads` is written in six places to read a
  `data.js`, `ball.js` or `voice/index.js`; `outside` exists in `film.py` and `web.py`; the French long date in
  `film.Maker.long_date` and `matches.french_date`.
- **Plan**:
  1. `files.py`: `read_js(path) -> dict` (the slice and the parse); the six places call it.
  2. `film.py` imports `outside` from `web.py` (it already imports `web` lazily elsewhere: check the import order)
     and `matches.french_date`, deleting its own.
  3. No new test: the existing ones of each caller cover the move.
- **Check**: `uv run pytest -q`.

## Looked at, fine

- No direct link to the footage: nginx's `video/` location tests the normalised `$uri`, serves from `/nonexistent`
  without the key, films included (`video/films/`); `Cache-Control: private` there, so a CDN keeps nothing.
- `upload_all` checks `protected()` on each video page and its first film before sending, `opens()` after, and
  refuses any `.mp4` outside `video/` (HOST-25 only widens it).
- The public page's build (`web.publish` with footage `none`): no video, poster, films, views, looks (`hide_looks`)
  nor player pictures (`pictured=set()`, `players/` removed); `preview.png` is drawn from colours and scores.
- `matches.export`: built in a temp folder with footage `none`, moved in place at the end.
- The cookie (`Secure; SameSite=Lax`), the key carried in the link's fragment and removed from the address
  (`linkedKey`), the password file written 0600 (`files.write_secret`): as designed and documented.
- `sync_remote.run`: claims read and written under the lock, `write` atomic; `begin`/`commit` refuse another
  machine's push; "keep this one" sets the server's copy aside first.
- `sync.settle`, `own`, `alone`, the `sending` mark: a push cut after the server's commit is recognised as this
  machine's (tested); the signature taken before the copy errs towards sending again.
- `sync.pull`: this machine's unpushed changes go to `backup-sync-<time>` (`--backup-dir`); `server.restore` is
  exercised end to end by `tests/test_backup_flow.py` (real rsync, snapshot and claims), a damaged copy is found by
  `sync.verify` there too.
- `backup_remote.snapshot`: built aside and renamed, safe when two machines make the same copy.
- `server.delete`/`keep`/`restore`: the copy's name checked against `backup.COPY` and quoted.
- `backup.stale` never removes a match's newest copy; `backup.room` refuses an upload that would fill the disk.
- `matches.mirror` before every build: pages and films put online by the other machine are kept
  (`removed_pages`, `removed_films` stop the upload otherwise).
- `video_copies.make`: `.part.mp4` then rename, length checked, CPU retry when the GPU refuses at start.
- Films: `draft-` file then rename, the manifest written after each film, a film kept when a later one fails.
- `timeline`: maps gapless and increasing on the two matches reviewed here (263 and 293 pieces); the times both
  ways and `moved` are tested (`tests/test_timeline.py`).
- `framing.py` and `presence.py`: nothing found.
- `speech.number`: French numerals right from 0 to 199 (70-99, "et un", "cent"); speeds are whole numbers before
  they reach it (`ball3d`).
- The commentary names players for their faults: the "never name a player" rule covers "Le coin du coach" only.
- `matches.online()` and `hosted_folder`: 0.02 s on the four hosted matches; no repeated-parse cost worth a change.
- `feedback.merge` by `id`: ids are random and never shown, a third party cannot rewrite someone's report.
