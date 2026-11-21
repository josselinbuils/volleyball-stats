# Server and app backend — improvements

One entry per finding, most valuable first. IDs are `SRV-NN`.

Scope: the local HTTP server (`review.py`: `serve_list` for the list, `serve` for a match), the `/app/*` routes
(`app.handle`), the jobs, "Réseau local", the self-update, the import, and their tests. `server.py` is the *hosting*
server's settings (the Site tab), not the HTTP server. Line numbers are those of `main` at a594cda. Experiments ran in a
scratch folder, on scratch copies; the running server only received GETs.

## SRV-01 Any file of the computer can be read through `/matches//…`

- **Type**: security
- **Impact**: high — with "Réseau local" on, any device of the network reads any file the user can (the ssh key of the
  hosting server, `outputs/video_password.json`, `outputs/server.json`); on 127.0.0.1, any local program.
- **Effort**: S
- **Confidence**: confirmed
- **Verified** (21 Nov, by the audit's lead): reproduced on a scratch server: `/matches//etc/passwd` answers 200 with the file, and so does a file under `~/.ssh/`. Cross-site pages and other host names are refused (403), so the reach is the local network while "Réseau local" is on, and any program of the machine. Fix this first; keep "Réseau local" off until then.
- **Where**: `src/volleyball_stats/review.py:2356-2362` (`list_page`), reached from `serve_list.do_GET` (2492) and from
  the match's server (`get`, 2995-2997); `tests/test_review.py:77-92`
- **Problem**: the path after `/matches/` is joined to the site folder, and only `..` is refused:
  ```python
  parts = Path(unquote(path).removeprefix("/matches/")).parts
  file = site.joinpath(*parts)
  ...
  if ".." in parts or not file.is_file():
      return None
  ```
  An absolute path makes `joinpath` drop `site`. On the running server (a GET):
  `curl -s --path-as-is -o /dev/null -w '%{http_code} %{size_download}\n' "http://127.0.0.1:8765/matches//etc/hosts"`
  → `200 285`, the hosts file; `/matches/%2Fetc%2Fhosts` → 200 too. The second branch has the same hole with a match
  name: `parts[0]` is only checked by `(out / parts[0] / files.SOURCE).exists()`, which an absolute `parts[0]` passes for
  any folder holding a `source.json`.
- **Plan**:
  1. In `list_page`, right after `parts = …`: `if not parts or any(p == ".." or Path(p).is_absolute() for p in parts): return None`.
     After `file` is settled (both branches), a second belt against links:
     `if not any(file.resolve().is_relative_to(root.resolve()) for root in (site, out)): return None`.
  2. Add to `tests/test_review.py` (the `list_page` tests, line 77): `/matches//etc/hosts`, `/matches/%2Fetc%2Fhosts`
     and `/matches/<absolute folder with a source.json>/data.js` all give `None`.
- **Check**: the `curl` above answers 404; `uv run pytest -q tests/test_review.py`.

## SRV-02 Several videos picked together never scan: the import dialog stops at "missing"

- **Type**: bug
- **Impact**: high — picking a match's chapters as files (the camera cuts a match into several) cannot be imported:
  only a folder or a single file works.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/app.py:883-884`; `tests/test_app.py:262`
- **Problem**: `if route == "scan": return reply(scan(str(body["source"])))`. The page sends an array when several
  files are picked (`web/src/components/Setup/ImportDialog.tsx:107`:
  `scan(r.source.length === 1 ? r.source[0] : r.source, …)`), and `scan` takes `str | list[str]` (387). `str()` of a
  list is `"['/a.mp4', '/b.mp4']"`, one path that does not exist. Ran in scratch with two real files:
  `app.handle("POST", "/app/scan", "", {"source": [a, b]}, list)` → `{"error": "missing"}`, 400, while
  `app.scan([a, b])` reaches the probe. The only test goes through `handle` with a string (`test_app.py:262`).
- **Plan**:
  1. `app.py:884`: `source = body["source"]`; `scan([str(s) for s in source] if isinstance(source, list) else str(source))`.
  2. In `tests/test_app.py`, beside line 262: the same call with a list of two files of `tmp_path` (the probe mocked
     as the neighbouring test does) answers 200 with `source` a list.
- **Check**: `uv run pytest -q tests/test_app.py`; in the app, "Importer" → pick two videos: the recordings show.

## SRV-03 The update leaves conflict markers in the code, then restarts on it

- **Type**: bug
- **Impact**: high — a machine with a local change that the update also touches (the owner's own, any time) ends with
  Python files holding `<<<<<<<`: the server restarts on them and no longer starts; nothing in the app repairs it.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/app.py:738-748` (`update`), route `update` (997-1002); `tests/test_app.py`
- **Problem**: `git pull --ff-only --autostash` exits 0 when the stash it puts back conflicts. Scratch repository, one
  local change on a line the remote also changed: `exit=0`, the file holds `<<<<<<< Updated upstream`, `git status`
  says `UU`, the stash is kept. `update()` only reads the exit code (`if pull.returncode:`), runs `uv sync`, answers
  200, and the handler calls `restart_after`.
- **Plan**:
  1. In `update()`, after the pull: `git -C ROOT diff --name-only --diff-filter=U`; when it lists files,
     `git -C ROOT reset --hard` (the local changes stay whole in the stash git kept: nothing is lost) and
     `print("update: local changes set aside, git stash pop brings them back", flush=True)` (the app's log).
  2. Test in `tests/test_app.py`: two scratch repositories in `tmp_path` (origin and clone, `git_check.ROOT`
     monkeypatched to the clone, `uv` monkeypatched to `None`), a conflicting local change; after `app.update()` no file
     of the clone holds `<<<<<<<`, `git stash list` has one entry, `HEAD` is origin's.
- **Check**: the test; by hand in a scratch clone, the same steps then `git status` is clean.

## SRV-04 "Tout récupérer" replaces the files of the match whose review is open

- **Type**: data-loss
- **Impact**: high — two machines: a pull under an open review leaves the server with the old answers in memory; the
  next answer writes them over the copy just brought.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/app.py:662-673` (`start_pull`), route `server/pull` (968); the same for the match
  server's own `/pull` (`review.py:3105-3106`, `pulled`); `tests/test_app.py`
- **Problem**: `server.restore` refuses the open match (`server.py:216-217`: `if what == open_match: raise
  PermissionError(what)`), `/sync/take` restarts the server after it (`review.py:3107-3119`: "Everything read from the
  match's files again"). `start_pull` and `pulled` do neither: `sync.pull_all` (`sync.py:454`) rewrites the open match's
  folder from a job. The review keeps `log` in memory and saves it whole on every answer (`save(answers, log)`,
  3395); `follow()` only re-reads when `review/data.js` changes, and `review/` is not synced (`backup.SKIP`). A pull can
  also start in the middle of an apply: only `learn`, `quit` and `update` ask `busy()` (951, 994, 999).
- **Plan**:
  1. `start_pull(apply, open_match=None, busy=False)`: `if busy: 409 {"error": "busy"}` (as `learn`); after
     `found = sync.due(OUTPUTS)`, `if open_match in {name for name, _ in found}: raise PermissionError(open_match)`, the
     refusal `server/restore` already gives (the page shows it the same way). Pass `open_match` and `busy()` at line 968.
  2. `review.py:3105`: in the match's server, `/pull` of `match.name` answers the same refusal.
  3. Tests in `tests/test_app.py`: `sync.due` monkeypatched to `[("m", False)]`, `handle(..., open_match="m")` on
     `/app/server/pull` is refused and `jobs.start` is not called; with `open_match="other"` it starts.
- **Check**: the tests; by hand with two machines, or with `sync.due` patched: the Site tab of an open match says why.

## SRV-05 A review that fails to start closes the app without a word

- **Type**: bug
- **Impact**: high — opening one broken match (a file missing or cut short) from the list ends the server: the page
  hangs, and from the shortcut there is no terminal to read why.
- **Effort**: M
- **Confidence**: read
- **Where**: `src/volleyball_stats/review.py:2386-2394` (`switch`), 3439-3465 (`main`), 2554 onwards (`serve`, all it
  reads before `Server(...)` at 3421); `serve_list` (2457); the list's page for the message
- **Problem**: `/open` answers `{}` then `switch` replaces the process by `python -m volleyball_stats.review NAME`
  (`os.execv`). Everything `serve` loads before it listens (`Questions`, `load_log`, the page's build, the tables) runs
  in the new process: any exception there ends it with a traceback in `outputs/app.log` and nothing on the port.
  `reopening` (2367-2371) only checks that the folder and its `source.json` exist. SRV-08 shows such a folder is easy
  to get (a hand-edited or half-synced `source.json`).
- **Plan**:
  1. In `main`, wrap the `serve(...)` call: `except Exception: traceback.print_exc()`, then
     `serve_list(args.outputs, args.theme, args.port, False, args.roster, failed=args.match.name)`.
  2. `serve_list` puts `failed` in the list's data (`matches.js`: `"failed": name`, once: cleared after the first
     `/matches/`), and the list shows an `ErrorNote` on that match's card (text through `explain`, "Voir le détail"
     to the log, as every failure). fr then en in `web/src/locales/`.
  3. Test: `review.main` with `serve` monkeypatched to raise and `serve_list` to record its arguments.
- **Check**: rename a scratch match's `tracks.parquet`, open it from the list: the list comes back with the note.

## SRV-06 On the local network, every device can do what only the computer should

- **Type**: security
- **Impact**: high — with "Réseau local" on (a gym's Wi-Fi with "À chaque démarrage"), any device reads the videos'
  password and the hosting server's settings, stops or updates the app, deletes a match, opens file windows on the
  computer.
- **Effort**: M
- **Confidence**: read (the routes); the owner decides the list (his call of 16 Nov was "no code" for the review)
- **Where**: `src/volleyball_stats/review.py:2477-2522`, 2982 and 3067 (the three entry points), `app.py:798-1002`
  (`handle`), `network.py:62-76` (`named_here`)
- **Problem**: once shared, `same_site(headers, port, lan)` accepts the machine's network address as `Host`, and no
  route looks at who asks. Among those open to a phone: `POST /app/server/password/get` (936-938, the password in
  clear), `/app/server` (the settings), `/app/update`, `/app/quit`, `/app/delete`, `/app/pick` (opens the file window
  on the computer; the request waits for it), `/app/video` and `/app/preview` (a video by its path), `/app/network`
  itself, `/app/log`. The share exists for the review's questions and the match page.
- **Plan**:
  1. In `app.py`, a set `MACHINE_ONLY` of routes (proposed: `server` and every `server/*`, `update`, `quit`, `delete`,
     `pick`, `scan`, `import`, `mount`, `video`, `preview`, `log`, `models`, `learn`, `run`; the owner trims it) and a
     `local: bool = True` argument of `handle`: a `MACHINE_ONLY` route with `local` false answers
     `403 {"error": "machine"}`. `/app/network` likewise in `network_route`.
  2. The three callers pass `local=ipaddress.ip_address(self.client_address[0]).is_loopback` (the socket's address:
     a `Host` header can be forged by a program, not this). To check under WSL2 (not done): the Windows browser reaching
     the server through `localhost` must come as loopback in both NAT and mirrored modes; if not, add the WSL host's
     address.
  3. The page: these entries hidden or disabled on a remote device (add `local` to `/app/network`'s state, which the
     page already asks: `network.state` gives `lan`, `always`, `url`, `wsl` today), `explain('machine')` fr/en for a
     request that still arrives.
  4. Tests: `handle("POST", "/app/quit", …, local=False)` → 403; a review route unaffected.
- **Check**: from a second device, `curl -X POST -H 'Content-Type: application/json' -d '{}' http://<address>:8765/app/server/password/get`
  → 403; the review's questions still answer there.

## SRV-07 One broken match folder takes the whole list down

- **Type**: bug
- **Impact**: medium — a `source.json` or `teams.json` cut short or missing a key (a sync stopped midway, a hand edit)
  and the app shows nothing at all: every load of the list fails with no answer.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/review.py:2305-2326` (`match_list`), its callers (`list_page` 2350, 2354;
  `app.handle`'s `listed`); `tests/test_review.py`
- **Problem**: `match_list` reads each folder with no guard: `json.loads(source.read_text())`, `given["video"]`,
  `given["court"]`, `matches.listed(...)`, `due(folder)`. In scratch, a match whose `source.json` has no `court`:
  `KeyError: 'court'`. `serve_list.do_GET` has no wrapper (SRV-09): the connection closes, the page stays blank.
- **Plan**:
  1. In `match_list`, the loop's body in `try: ... except (OSError, ValueError, LookupError, TypeError) as error:`:
     print the traceback (the app's log) and list the match as
     `{"name": folder.name, "path": folder.name, "date": None, "title": None, "teams": None, "scores": [], "sets": 0, "rallies": 0, "ready": False, "broken": True}`.
  2. The list's card shows `ErrorNote` for `broken` (one short text, fr/en) with "Supprimer" still offered.
  3. Test: two matches in `tmp_path`, one with `{}` as `source.json`: both listed, the broken one flagged.
- **Check**: the test; `uv run pytest -q tests/test_review.py`.

## SRV-08 Two loads of the list at once break each other

- **Type**: bug
- **Impact**: medium — two tabs, a tab and a phone, or the page reloaded as the app's window opens: a blank or
  unstyled list, or a traceback, until the next reload.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/review.py:2343-2352` (`list_page`), 2356-2364 (the files' reads)
- **Problem**: every GET of `/matches/` deletes and copies the site again:
  `shutil.rmtree(site, ignore_errors=True); shutil.copytree(matches.TEMPLATE, site)`, while other threads serve its
  files. Scratch stress, 10 s, one thread loading the page, one loading a script: `page ok: 20`,
  `page Error: 670`, `page FileExistsError: 512`, `page FileNotFoundError: 3`, `file 404: 1314589`, `file ok: 4812`.
- **Plan**:
  1. A module `threading.Lock` held by `list_page` for the rebuild and for the read of a file under `site`.
  2. Copy the template only when `site` is missing or older than `matches.TEMPLATE / "matches.html"` (mtime); each
     `/matches/` then only rewrites `matches.js`, through `files.write_text` (in place at once).
  3. Test: 8 threads calling `list_page("/matches/", …)` and `list_page("/matches/app.js", …)` 50 times: no exception,
     no `None`.
- **Check**: the test.

## SRV-09 Requests that end without an answer, or with Python's `repr`

- **Type**: bug
- **Impact**: medium — a failure the code did not list closes the connection: the page shows its generic failure, or
  waits; the reason is only in the log.
- **Effort**: S
- **Confidence**: read (`range_of` and `match_list` cases ran)
- **Where**: `src/volleyball_stats/review.py:2972-2980` (`Handler.answer`), 2477-2522 (`serve_list`'s `do_GET`,
  `do_POST`), 2397-2403 (`pulled`), 3070 and 2499 (`int(self.headers.get("Content-Length", 0))`)
- **Problem**:
  - `answer` catches `Busy`, then `(LookupError, TypeError, ValueError, AttributeError, StopIteration)`. A
    `RuntimeError` or `OSError` (`matches.set_password` in `/host` 3343, a full disk in `/comment` or `/feedback`,
    ssh's failure outside the steps) leaves through `Server.handle_error`: no response.
  - What it does answer is `json.dumps({"error": repr(error)})`: the page gets `KeyError('name')`.
  - `serve_list`'s handlers have no wrapper at all: `Content-Length: abc` raises in `do_POST` (2499), `match_list`
    in `do_GET` (SRV-07); `pulled` does not catch `ValueError`.
- **Plan**:
  1. `answer`: add `except Exception as error:` → `traceback.print_exc()`, then
     `self.send(json.dumps({"error": str(error) or type(error).__name__}).encode(), "application/json", 500)`, inside a
     `try/except OSError` (the headers may have left). In the 400 branch, `str(error) or type(error).__name__` in place
     of `repr(error)` (what `app.handle` does, 1003-1015).
  2. Move `answer` out of the closure (a small mixin class at module level, `send` with it) and use it for
     `serve_list`'s `do_GET`/`do_POST` too.
  3. Read the length with a helper returning 400 on a non-number.
  4. Tests with SRV-27's harness: a POST with `Content-Length: abc` → 400; a route patched to raise `RuntimeError`
     → 500 with a JSON body.
- **Check**: the tests; `curl -s -H 'Content-Type: application/json' -H 'Content-Length: abc' -X POST …` on a scratch
  server answers 400.

## SRV-10 Site tab jobs start in the middle of an apply

- **Type**: bug
- **Impact**: medium — a match put online, exported or backed up while its review rewrites its files: a page built
  from two states goes to the server, or a backup holds half an apply.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/app.py:914-932` (`server/host`), 946-948 (`export`), 965-974 (`server/verify`,
  `server/pull`, `server/backup`), 975-980 (`swap`, `run`); `busy` only at 951, 994, 999; `review.py:2664-2703`
- **Problem**: `busy` (true while the open review's run goes: `lambda: bool(progress)`, `review.py:3084`) is asked by
  `learn` ("Not under an apply: the open match's review would write as its pipeline runs again"), `quit` and `update`
  only. The others start a job that reads `outputs/matches/*` at once. The review's own uploads take its lock
  (`run_steps`); the Site tab's do not.
- **Plan**:
  1. In `handle`, one line before the POST routes:
     `if route in ("server/host", "export", "server/backup", "server/pull", "run", "swap", "delete") and busy(): return reply({"error": "busy"}, 409)`
     (the page already has the text for `busy`; `server/verify` only reads, left as is).
  2. The open review's own copies have the same hole: `backing` (2681, every 600 s) and `/backup` call `back_up`,
     which takes `backup_lock` only, never `lock` (`/sync/take` takes both: `with free(), backup_lock`). In `backing`,
     skip the round while `progress` is not empty; `/backup` answers `busy` then.
  3. Test in `tests/test_app.py`: each route with `busy=lambda: True` → 409 and `jobs.start` not called.
- **Check**: the tests.

## SRV-11 A job that died reads as running when another user's process took its number

- **Type**: bug
- **Impact**: medium — after a restart of the machine, a job (import, pipeline, upload) can show "running" for good:
  its match cannot be run, the update and the stop of the app with a window are refused, "Arrêter" fails.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/jobs.py:272-293` (`alive`), 365-374 (`stop`); `tests/test_jobs.py`
- **Problem**: `except PermissionError: return True` (281-282) answers before the start time or the key are compared:
  a number reused by a system process is "alive". Ran: `jobs.alive(1, 'Thu Jan  1 00:00:00 1970')` → `True` (the
  process 1 started in 2026), and `os.killpg(1, signal.SIGTERM)` raises `PermissionError`, which `stop` does not catch
  (`except ProcessLookupError: pass`): the route answers an error and the record is never marked ended.
- **Plan**:
  1. `alive`: on `PermissionError`, do not return: go on to the key / start comparison (`process_key` and
     `started_at` read `/proc` and `ps`, which work for another user's process); skip the `waitpid` block.
  2. `stop`: `except (ProcessLookupError, PermissionError): pass`.
  3. Tests: `alive(1, "Thu Jan  1 00:00:00 1970")` is `False` (skip when the test runs as root); `stop` on a record
     whose pid is 1 marks it `stopped` without raising.
- **Check**: `uv run pytest -q tests/test_jobs.py`.

## SRV-12 Each job fetches git first, and the "behind" warning can become its error

- **Type**: bug
- **Impact**: medium — every job started from the app waits for a `git fetch` (1.4 s here, up to 5 s offline at its
  end too), and a job that fails while the code is late shows "Warning: main is 3 commits behind…" as its reason.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/git_check.py:61-66` (`check`), `src/volleyball_stats/__init__.py`,
  `jobs.py:219-222` (`start`), 338-341 (`error_of`); `app.py:1093` (`main`), `review.py:3439` (`main`)
- **Problem**: `check()` runs once per `python -m volleyball_stats.X` unless `VOLLEYBALL_STATS_GIT_CHECKED` is set. The
  server started by `stats` is not a `-m` command: the variable is absent from its environment (`ps eww` on the
  running one: 0 match), so each runner (`python -m volleyball_stats.jobs`) checks. A runner with no step:
  `real 1.46` s, `0.03` with the variable set. The warning goes to stderr, which is the job's log
  (`stderr=subprocess.STDOUT`), from a thread that can write after the step's own error:
  `jobs.error_of("…error: unrecognized arguments: --x\nWarning: main is 3 commits behind origin/main: run git pull --rebase.\n")`
  returns the warning. The app has its own notice of a late code (`/git`).
- **Plan**:
  1. `jobs.start`: `env={**os.environ, "PYTHONUNBUFFERED": "1", git_check.CHECKED_ENV: "1"}`.
  2. Test: `jobs.start` with `subprocess.Popen` monkeypatched: the environment holds the variable.
- **Check**: the test; `time uv run python -m volleyball_stats.jobs <a record with no step>` under that variable.

## SRV-13 An upload hangs for hours on a dropped connection, the review locked meanwhile

- **Type**: bug
- **Impact**: medium — the Wi-Fi drops or the laptop sleeps during "Mettre en ligne" or a backup: ssh/rsync wait on a
  dead connection; the review's run never ends (no cancel), the app refuses to stop or update.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/matches.py:565-568` (`ssh_options`), used by `backup.connection`, `sync.rsync`,
  `server.ssh`; `tests/test_matches.py`
- **Problem**: the options are `BatchMode=yes`, `StrictHostKeyChecking=accept-new`, `ConnectTimeout=10`: the last only
  covers the connection's start. Without `ServerAliveInterval`, an established session whose peer vanished waits for
  the system's TCP timeout (hours with no data to send). The review's uploads run under `lock` (`run_steps`).
- **Plan**:
  1. `ssh_options`: add `"-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"` (a dead connection ends in a
     minute, with ssh's exit 255 that the callers already turn into an error).
  2. Update the test of `ssh_options` in `tests/test_matches.py`.
  3. Seen beside it, same change: `sync.rsync` (`sync.py:479`) passes `-e " ".join(ssh)`: a key path with a space
     breaks it; use `shlex.join(ssh)` (what `matches.ssh_shell` does).
- **Check**: the tests; by hand (the owner, his server): start an upload, turn the Wi-Fi off: the failure shows within
  about a minute.

## SRV-14 After an update, the restart depends on the page still being there

- **Type**: bug
- **Impact**: medium — the page reloaded or closed during a long `uv sync` (up to 30 min allowed): the code on disk is
  new, the server still runs the old one, and nothing offers the restart again ("up to date").
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/review.py:2508-2513`, 3084-3089; `app.py:1018-1041` (`restart_after`, `stop_after`);
  `review.py:2386-2394` (`switch`)
- **Problem**: both servers do `self.send(*answer)` then `if self.path == "/app/update" and answer[2] == 200:
  app.restart_after(...)`. `send` raises `BrokenPipeError` when the client left: the restart line is never reached
  (`handle_error` hides that exception). Same for `/app/quit` and `/app/network`. Second hole: `replace()` takes the
  review's `lock` and then `os.execv`; if the exec fails (`OSError`: the venv being rewritten), the daemon thread dies
  holding the lock: every later request waits for good, and `stats stop` never ends.
- **Plan**:
  1. In both handlers: `try: self.send(*answer) finally:` the three follow-ups (update, quit, network).
  2. `restart_after` and `switch`: `try: os.execv(...) except OSError: traceback.print_exc(); os._exit(1)` (a server
     that cannot restart on new code should not stay half alive; the shortcut starts it again).
  3. Test: a fake handler whose `send` raises `BrokenPipeError`: `restart_after` still called (monkeypatched).
- **Check**: the test.

## SRV-15 The review's answers are not flushed to the disk

- **Type**: data-loss
- **Impact**: medium — a power cut or a WSL shutdown just after an answer can leave `identity_answers.json` empty or
  cut: the review then fails to open (SRV-05) and hours of answers are gone (the last backup apart).
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/files.py:28-39` (`replacing`), its header note (line 4); `review.py:1466-1469`
  (`save`), `write_names`
- **Problem**: `replacing` writes a temporary file and `os.replace`s it, without `fsync`: the module says so itself
  ("no fsync, a power cut may still lose the last write; fsync the file and its folder if…"). On ext4 (WSL2) a rename
  over an unflushed file is the classic way to an empty file after a crash. The answers file is the one a user cannot
  make again; it is 1.1-1.3 MB on a real match, written at each answer.
- **Plan**:
  1. `replacing(path, mode="w", durable=False, **kwargs)`: when `durable`, `f.flush(); os.fsync(f.fileno())` before
     the `os.replace` (the folder's fsync is not needed for the old-or-new guarantee). `write_text(path, text, durable=False)`.
  2. `durable=True` for `review.save` and `write_names` only (the page's data is rebuilt, not these).
  3. Measure an answer's time before and after on a real-size file (`/answer` in scratch: `save` alone, 20 runs); on
     an SSD expect a few ms. Report both numbers.
  4. Test: `os.fsync` monkeypatched to count: called once for `durable`, never otherwise.
- **Check**: the test and the two timings.

## SRV-16 A stopped import leaves its half video on the disk

- **Type**: bug
- **Impact**: medium — "Arrêter" during an import leaves `NAME.part.mp4` (tens of GB for a 4K match) and
  `NAME.part.txt` in `data/`, never removed nor shown; a stopped export leaves its temporary folder.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/import_match.py:136-161` (`join`), `jobs.py:365-374` (`stop`), 383-392 (`run`);
  `matches.py:892` (the export's `tempfile`)
- **Problem**: `join` cleans in a `finally` (`part.unlink(missing_ok=True)`), but `jobs.stop` ends the group with
  `SIGTERM`, whose default action ends Python without running `finally`.
- **Plan**:
  1. In `jobs.py`'s `__main__` entry and at the top of `import_match.main` and `matches.main`:
     `signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))` (`SystemExit` unwinds the `finally` blocks and the
     `with tempfile.TemporaryDirectory()`); one helper `jobs.stoppable()` called by the three.
  2. Test in `tests/test_jobs.py`: start a job whose step is a small script writing a file in a `try/finally` after
     calling `jobs.stoppable()`, `jobs.stop` it: the file is gone.
- **Check**: the test; import a short clip in the app, stop it midway: `ls data/<name>/` holds no `.part.*`.

## SRV-17 WSL: `.wslconfig` is changed before Windows approves, and a refusal reads as done

- **Type**: bug
- **Impact**: medium — a Windows user who declines the administrator prompt keeps a changed `.wslconfig` (mirrored
  networking at WSL's next start) with no firewall rule; the page then hides the button that would add it.
- **Effort**: S
- **Confidence**: suspected — read on macOS; to check on Windows: what `Start-Process -Verb RunAs` returns when the
  prompt is declined, and whether the inner command's failure is seen
- **Where**: `src/volleyball_stats/network.py:141-162` (`configure_windows`), 165 (`state`);
  `web/src/components/Setup/NetworkDialog.tsx:89` (`needsWindows`)
- **Problem**: `files.write_text(path, mirrored_config(text))` (151) comes before the elevated PowerShell (157). The
  outer `powershell.exe` exit code is the only thing read; `Start-Process … -Wait` does not carry the inner command's
  failure. `state` judges "set up" from the file alone.
- **Plan**:
  1. Run the firewall rule first; write `.wslconfig` only once it succeeded.
  2. Make the result readable: the elevated command ends with `exit $LASTEXITCODE`-style status and the outer one uses
     `-PassThru` and `exit $p.ExitCode`; after it, verify with a non-elevated
     `Get-NetFirewallHyperVRule -Name RULE` and raise `OSError` when absent.
  3. `state`: `needsWindows` also when the rule is absent (that same read, cached for the process).
  4. Tests in `tests/test_network.py` with `subprocess.run` monkeypatched: a failing rule leaves `.wslconfig` untouched.
- **Check**: the tests; on the owner's PC: decline the prompt, `.wslconfig` is unchanged and the button stays.

## SRV-18 "À chaque démarrage" opens the app on whatever network the laptop joins

- **Type**: security
- **Impact**: medium — ticked once at home, the review (footage of real people, names) is offered with no code on
  the gym's or a café's Wi-Fi at every start.
- **Effort**: M
- **Confidence**: read
- **Where**: `src/volleyball_stats/network.py` (`keep`, `shared`, `bind`, `state`),
  `web/src/components/Setup/NetworkDialog.tsx`
- **Problem**: `network.json`'s `always` is a boolean: `shared()` is true wherever the machine starts. The owner's
  rule keeps footage off any place without a password; the local network without a code was his call for a network he
  chose.
- **Plan** (the owner's call first: it narrows a choice he made on 16 Nov):
  1. `keep(outputs, True)` also stores the network it was ticked on: the first three bytes of the machine's address
     (`network.address()`), as `"net": "192.168.1"`.
  2. `shared()` at start: true only when the current address has that prefix; otherwise the app starts on 127.0.0.1
     and the dialog says the share is off on this network, one tap to turn it on here (the existing switch).
  3. Limit to name in the code: two networks with the same prefix are taken as one (the gateway's MAC would tell them
     apart, `arp` differs per system).
  4. Tests in `tests/test_network.py`: `always` with another prefix → `bind()` is `127.0.0.1`.
- **Check**: the tests.

## SRV-19 On the local network, another site can read the matches' data

- **Type**: security
- **Impact**: low — a device of the network that visits a hostile *http* page (an https one cannot load an http
  script) while the share is on leaks the players' names and the match data to it.
- **Effort**: M
- **Confidence**: suspected — the server side ran; the browsers' side was not tested (Chrome asks before a public page
  reaches a local address; Safari and Firefox to check)
- **Where**: `src/volleyball_stats/review.py:2420-2428` (`same_site`)
- **Problem**: GETs are judged by `Host`, `Origin in (None, …)`, `Sec-Fetch-Site in (None, …)`. Browsers send
  `Sec-Fetch-*` only to trustworthy origins: https and loopback, not `http://192.168.x.x`; a `<script src>` carries no
  `Origin`. Ran: `same_site({"Host": "192.168.1.20:8765"}, 8765, True)` → `True`. `data.js`, `review.js`,
  `/matches/matches.js` are scripts setting globals (`window.MATCHES = …`): readable by the page that includes them.
  On 127.0.0.1 the header is sent and the check holds.
- **Plan**:
  1. When `Host` is not loopback, a GET of anything but an HTML page needs a cookie: the pages (`/matches/`,
     `/review`, the match page) answer with `Set-Cookie: vs=<token>; SameSite=Strict; HttpOnly; Path=/`; `same_site`
     gets the cookie and compares (`hmac.compare_digest`). `SameSite=Strict` is not sent with a script included from
     another site.
  2. The token: `secrets.token_urlsafe(16)` kept in `os.environ` so that it survives the `os.execv` restarts.
  3. Tests of `same_site`: a LAN host without the cookie → False for `/data.js`, True for `/review`; loopback
     unchanged.
- **Check**: the tests; from a phone, the review still loads its videos and data (the cookie follows same-site
  requests).

## SRV-20 The late-code check fetches on every page load

- **Type**: performance
- **Impact**: low — each load of the list or a review costs a `git fetch` (1.6 s measured on `/git`, 1.8 s on
  `/app/doctor`), up to 5 s offline, each holding a thread; nothing on screen waits for it.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/git_check.py:23-40` (`behind`), `review.py:2485-2486` and the same route in `get`;
  `doctor.py` (its call)
- **Problem**: `behind` fetches at each call; no cache. Measured on the running server: `/git` 1.60 s, `/app/doctor`
  1.77 s, against 0.04 s for `/app/state`.
- **Plan**:
  1. `git_check.behind_cached(root, every_s=600)`: a module dict `{at, value}` under a lock; `/git` and `doctor` use
     it. `app.update` clears it after a pull.
  2. Test: two calls, `_git` monkeypatched to count: one fetch.
- **Check**: `curl -s -o /dev/null -w '%{time_total}\n' 127.0.0.1:8765/git` twice: the second under 0.05 s.

## SRV-21 `Range` headers: a malformed one fails the request, an impossible one gets a wrong answer

- **Type**: bug
- **Impact**: low — a video request with an odd range ends with no response; no browser seen sending one.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/review.py:2136-2142` (`range_of`), 2107-2133 (`send_file`); `tests/test_review.py`
- **Problem**: ran: `range_of("bytes=abc-", 100)` and `range_of("bytes=-", 100)` raise `ValueError`;
  `range_of("bytes=5-2", 100)` gives `(5, 2)`, then `Content-Length: -2`; a first byte past the end gives `None`, so a
  200 with the whole file where 416 is expected.
- **Plan**:
  1. `range_of`: `try: … except ValueError: return None`; `return None` when `last < first`.
  2. `send_file`: when a `Range` was given and `first >= size`, answer 416 with `Content-Range: bytes */size`.
  3. Tests for the four inputs.
- **Check**: `uv run pytest -q tests/test_review.py`.

## SRV-22 Import: three inputs the form accepts and the job refuses

- **Type**: bug
- **Impact**: low — the import starts then fails as "interrupted" or with argparse's message, for an input the dialog
  let through.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/app.py:425-451` (`import_steps`), `import_match.py:52-59` (`videos`), 164 (`named`)
- **Problem**:
  - `command = [..., "--teams", flag, "--date", day, ...]`: a team name starting with `-` (no space) is read by
    argparse as an option.
  - `day` comes from `import_match.named(chapters, …, body.get("date"))`: for a `date` that `teams.parse_date` cannot
    read (anything but dd/mm/yyyy or yyyy-mm-dd) it is `None`, which goes into the command as is: the runner cannot
    start its step and the job reads "interrupted".
  - A folder of `.mov` files is "empty" (`p.suffix.lower() == ".mp4"`), while a single `.mov` picked as a file is
    taken (`if source.is_file(): return [source]`).
- **Plan**:
  1. `"--teams=" + flag`, `"--date=" + day` (argparse takes the value whatever its first character).
  2. `if not day: raise ValueError("date")` in `import_steps` (the page's `explain` has the form's texts).
  3. `videos`: `p.suffix.lower() in (".mp4", ".mov")`, what the file window offers (`app.py:266`:
     `'MP4, MOV|*.mp4;*.mov|…'`); check first that `join`'s `-c copy` into `.mp4` takes the camera's `.mov` (one short
     clip in scratch), else refuse a `.mov` in `scan` with a reason instead.
  4. Tests in `tests/test_app.py` and `tests/test_import_match.py` for the three.
- **Check**: the tests.

## SRV-23 "Oublier" on a running job removes its record under it

- **Type**: bug
- **Impact**: low — a request for a running job's id (a stale page, a second tab) deletes the record: the job
  disappears from the app while it still works, and its runner fails at its next step.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/jobs.py:377-380` (`forget`), `app.py:983-985`
- **Problem**: `forget` unlinks the record and the log without asking `running(job)`; the runner's `update(record, …)`
  then raises `FileNotFoundError`.
- **Plan**:
  1. `forget`: `if record.exists() and running(json.loads(record.read_text())): raise Running(job_id)` (the route
     already answers 409 for it).
  2. Test in `tests/test_jobs.py`.
- **Check**: the test.

## SRV-24 An unknown POST to a match's server answers 200 and rewrites the answers

- **Type**: bug
- **Impact**: low — a typo in a route or a page older than the server gets a success and a full rewrite of
  `identity_answers.json` instead of an error.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/review.py:3067-3415` (`post`): the chain of `if/elif self.path == …` ends at 3382
  (`elif self.path == "/undo" and (history or log)`), then `save(answers, log)` (3395) and the 200 (3415) for any path
- **Plan**:
  1. A module tuple of the routes this last block serves (`CHANGES` plus `/apply`, `/undo`, `/name`, … as the chain
     lists them); before taking the lock: `if self.path not in ROUTES: return self.send(b"Not found", "text/plain", 404)`.
  2. Test with SRV-27's harness: `POST /nope` → 404, the answers file's mtime unchanged.
- **Check**: the test.

## SRV-25 A link to the app from another site opens a blank page

- **Type**: UX
- **Impact**: low — the app's address clicked in a mail, a chat or a document (a cross-site navigation) gets an empty
  403.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/review.py:2420-2428` (`same_site`), 2479-2480, the same test in `get`
- **Problem**: `Sec-Fetch-Site: cross-site` is refused for every GET, top-level navigations included
  (`return self.send(b"", "text/plain", 403)`). A navigation cannot be read by the site it comes from.
- **Plan**:
  1. In both `do_GET`s: when the refusal comes only from `Sec-Fetch-Site` and the request is a navigation
     (`Sec-Fetch-Mode: navigate`, `Sec-Fetch-Dest: document`) with a good `Host`, answer `302` to the same path (the
     browser's second request is `none`/same-origin).
  2. Test of the helper with these headers.
- **Check**: `curl -s -o /dev/null -w '%{http_code}\n' -H 'Sec-Fetch-Site: cross-site' -H 'Sec-Fetch-Mode: navigate' -H 'Sec-Fetch-Dest: document' 127.0.0.1:8765/matches/`
  → 302.

## SRV-26 Small races in the jobs

- **Type**: bug
- **Impact**: low — rare: a job started twice by two requests at once; one poll of the state failing.
- **Effort**: S
- **Confidence**: read (300 scratch jobs started in a row: 0 record lost)
- **Where**: `src/volleyball_stats/jobs.py:209-227` (`start`), 230 (`update`), 310-326 (`told`)
- **Problem**:
  - `start` checks `is_running` then writes the record, with no lock: two requests of the same job (a double click
    through two tabs) both pass.
  - After `Popen`, the server's `update(record, pid=…)` (226) and the runner's first `update` both read-modify-write
    the record: the later one can drop the other's fields (`pid` lost → the job reads "interrupted").
  - `told`: `float(share)` on a `::progress ` line read while it is being written (the tail cut mid-line) raises
    `ValueError` in `/app/state`.
- **Plan**:
  1. A module `threading.Lock` around `start`'s check-and-write.
  2. Give the runner its own pid: the runner writes `pid`, `pidStarted`, `pidKey` itself at its start
     (`os.getpid()`), `start` no longer updates the record after `Popen` (it returns the same values for its caller).
  3. `told`: skip a line whose number does not parse.
  4. Tests: `told("::progress 0.\n::progress")` returns the last whole value; two threads calling `start` on one id:
     one `Running`.
- **Check**: `uv run pytest -q tests/test_jobs.py`.

## SRV-27 No test reaches an HTTP route

- **Type**: tests
- **Impact**: medium — SRV-01, 02, 07, 08, 09 and 24 are all at the seam between the handlers and the functions the
  tests call directly; 291 tests pass over them.
- **Effort**: M
- **Confidence**: read (`grep -n "HTTPConnection\|urlopen\|serve_list(" tests/` finds no request to a handler)
- **Where**: `src/volleyball_stats/review.py:2457-2551` (`serve_list`); a new `tests/test_http.py`
- **Problem**: `serve_list` builds the handler class, the server, the threads and calls `serve_forever` in one
  function: nothing can start it on a free port and stop it.
- **Plan**:
  1. Split `serve_list` in two: `list_server(out, theme, port, roster) -> Server` (the handler and
     `Server((host, port), Handler)`, no thread, no browser) and `serve_list`, which calls it then starts the threads
     and `serve_forever`.
  2. `tests/test_http.py`, inside one `describe`-like class: a fixture starting `list_server(tmp_path, …, port=0)` in
     a thread (`server.server_address[1]` for the port; `same_site`'s port from it), closed after. Cases: `/matches/`
     200; the traversal of SRV-01 → 404; `Host: evil.example` → 403; a POST without the JSON type → 403; `/app/scan`
     with a list (SRV-02); `Content-Length: abc` (SRV-09); 8 parallel `/matches/` (SRV-08).
  3. Then the same seam for a match (`serve`), once SRV-28 gives it one.
- **Check**: `uv run pytest -q tests/test_http.py`.

## SRV-28 `serve` is one 880-line function; `server.py` is not the server

- **Type**: maintainability
- **Impact**: medium — the match's server (state, threads and 40 routes) is a closure over some thirty variables:
  nothing in it can be tested or read alone; the file names mislead (the first place one looks for the HTTP server is
  `server.py`).
- **Effort**: L
- **Confidence**: read
- **Where**: `src/volleyball_stats/review.py:2554-3436` (`serve`), `server.py`, their imports and tests
- **Plan** (in steps that each leave the tests green; no behaviour change):
  1. Rename `server.py` → `hosting.py` (it holds the hosting server's settings, backups and restore) with its test
     file and imports (`app.py`, `review.py`, docs). `git mv` to keep the history.
  2. Move the HTTP part of `review.py` to `http_server.py`: `send_file`, `range_of`, `same_site`, `Server`,
     `switch`, `network_route`, `network_restart`, the shared handler base (SRV-09), `list_page`, `serve_list`.
  3. In `serve`, group the closure's state in one object (`Review`: `log`, `history`, `lock`, `progress`,
     `failure`, `questions`, …) with the helpers as methods (`run_steps`, `taken`, `free`, `follow`, `pages`); the
     handler keeps a reference to it. Then `post`'s chain becomes a table `{path: method}` (which also gives SRV-24
     its list).
  4. Each step: `uv run pytest -q`, and a review opened by hand.
- **Check**: `uv run pytest -q`; `wc -l src/volleyball_stats/review.py` under 2,600.

## SRV-29 The same lines written several times

- **Type**: maintainability
- **Impact**: low — a fix made in one copy and not the others (the two POST preludes already differ: a body that is not JSON
  gets `not json` from the list, a `repr` from a match).
- **Effort**: M
- **Confidence**: read
- **Where** and **Plan**, one small change each:
  1. `review.py:2495-2504` and `3067-3081`: the POST prelude (same-site, JSON type, size, body) → one function
     returning the body or the refusal. The match's `json.loads(raw or b"{}")` (3081) then answers "not json" as the
     list does.
  2. `Handler.send` defined in both servers → the shared base of SRV-09.
  3. `hosted.update({k: v for k, v in read_hosted(match).items() if k in ("behind", "changes", "copiesStale"…)})` at
     `review.py:2768, 2786, 2819, 3160, 3165` → one `refresh_hosted()`.
  4. The answer `{"answered": len(log), **waiting(match, log, shown), "rebuilt": …, "undone": …}` written six times
     in `post` (3338, 3355, 3360, 3366, 3381, 3415) → one `answered(rebuilt=False, undone=None, **more)`.
  5. Four readers of `data.js` (`matches.py:97` `page_of`, `matches.py:495`, `review.py:788`, `rekey.py:154`
     `read_page`) → one in `files.py`.
  6. `app.windows_home` (175) and `network.wsl_config` (105): the same `cmd.exe /c echo %USERPROFILE%` + `wslpath` →
     `network.wsl_config` calls `app.windows_home` (or both a helper in `doctor.py`).
  7. `rename.PORT = 8765` (`rename.py:21`) → `review.PORT`.
  8. `files.write_secret` (47) repeats `replacing`'s temporary-file logic → `replacing(path, opener=…)` with the 0600
     opener.
- **Check**: `uv run pytest -q` after each.

## SRV-30 Code only the tests use

- **Type**: maintainability
- **Impact**: low — two functions kept alive by their tests.
- **Effort**: S
- **Confidence**: read (`grep -rn "chain(\|jobs\.progress(" src tests`)
- **Where**: `src/volleyball_stats/review.py:1424` (`chain`, only `tests/test_review.py:1048-1049`; `film.py:692`
  calls its own `chain`), `jobs.py:332` (`progress`, only `tests/test_jobs.py:31-33`; the app uses `told`)
- **Plan**:
  1. Delete both functions and their tests; move the three `jobs.progress` cases onto `jobs.told` (same inputs,
     `told(...)["progress"]`, `["stage"]`).
- **Check**: `uv run pytest -q tests/test_jobs.py tests/test_review.py`.

## SRV-31 Comments and docs that no longer say what the code does

- **Type**: docs
- **Impact**: low — a reader is told the server is reachable from this machine only, where the code shares it.
- **Effort**: S
- **Confidence**: read
- **Where** and **Plan**:
  1. `review.py:1-12` (module docstring: "serves it on this machine only") and `3420` ("The footage shows real people:
     this machine only.", right above `Server((network.bind(app.OUTPUTS), port), Handler)`): say "this machine, or the
     local network when the app shares it (`network.py`)".
  2. `app.py:833`: "`here`: from this machine, which alone sees the videos' password" names a parameter that no longer
     exists, on a route that returns no password: delete the comment (or make it true with SRV-06).
  3. `doctor.py:18`: "about 8 GB of RAM at its peak (docs/setup.md)" against `docs/setup.md:80` "about 6.3 GB": one
     number in both.
  4. `review.py:106-111`: `with_review` sits in the middle of the constants, no blank lines after it: move it below
     them.
  5. `install.sh:6` and `:51-53`: "Linux" means `apt-get`; on another distribution the script fails at
     `sudo apt-get update`. Test `command -v apt-get` first and otherwise print what to install (git, ffmpeg, uv) and
     go on when they are there; say "Debian or Ubuntu" in `docs/setup.md`.
- **Check**: `grep -n "this machine only" src/volleyball_stats/review.py` finds nothing; `bash -n install.sh`.

## SRV-32 The app's log: tracebacks without a time, and it only shrinks at a start

- **Type**: maintainability
- **Impact**: low — "Voir le détail" shows errors nobody can place in time; a server left running for weeks grows
  its log past the 2 MB limit.
- **Effort**: S
- **Confidence**: read
- **Where**: `src/volleyball_stats/applog.py` (`Tee.write`, `start`), `Server.handle_error` (`review.py:2381`), the
  `traceback.print_exc()` calls of `review.py` and `app.py`
- **Problem**: only `start` writes a time (`--- 2026-… ---`) and trims (`if path.exists() and path.stat().st_size >
  MAX_BYTES`). Tracebacks follow each other bare.
- **Plan**:
  1. `Tee.write`: when a write starts a line (the previous one ended with `\n`) and more than a minute passed since
     the last stamp, first write `f"[{time.strftime('%Y-%m-%d %H:%M')}]\n"` to the file only.
  2. `Tee.write`: count the bytes written; past `MAX_BYTES`, trim as `start` does (under the lock, reopening the file).
  3. Tests in `tests/test_applog.py`: a stamp appears once per minute (time monkeypatched); the file stays under the
     limit after 3 MB of writes.
- **Check**: `uv run pytest -q tests/test_applog.py`.

## Looked at, fine

- POSTs from another site on 127.0.0.1: refused three ways (`Content-Type: application/json` needs a preflight the
  server never grants, `Origin`, `Sec-Fetch-Site`); form and plain-text posts get 403.
- DNS rebinding: `network.named_here` takes `127.0.0.1`/`localhost` (and the machine's own address when shared) with
  the right port only; a rebound name is refused.
- `/app/image` and the club's pictures: names checked against a pattern, `data:` URLs of png/jpeg/webp only, sizes
  bounded (`CLUB_BODY`, `MAX_BODY`).
- `app.delete`: the name goes through the job id's pattern, and the folder's `resolve().parent` is checked before
  `rmtree`.
- `/app/mount`: the drive is checked before it reaches the `mount` command.
- `/crop` and the pictures' routes: paths built from integers.
- `server.save`: the address must match `[\w.-]+@[\w.-]+`; `test`, `delete`, `keep` quote with `shlex.quote`; a copy's
  name is checked against `backup.COPY` before any ssh.
- `server.restore`: the copy and the match are checked against the server's own listing; the open match is refused.
- `sync.pull`: the name is checked against the server's list before it reaches a path or rsync.
- The export's folder name: a fixed pattern, no path from the request.
- `files.replacing`: one temporary file per process and thread, `os.replace` in place; no reader sees half a file
  (the fsync apart, SRV-15).
- Job identity for a number reused by the same user, and across a WSL restart (`pidKey` from `/proc`, else `ps`'s
  start time compared with tolerance); `ps lstart` in another locale falls back to equality.
- `jobs.stop` ends the whole group (`start_new_session=True`, `os.killpg`): ffmpeg and the steps go with the runner.
- The review's lock: `taken()` gives up while a run holds it (503 `busy`) instead of queueing; `free()` releases in a
  `finally`.
- Undo (`undo`, `history`): bounded (`UNDOS`), the names restored with the answers.
- After a rerun the players' and ball's tables are not stale: tracking only runs with `--force` or missing files.
- `presence.watch`: the app stops only with no window, no run, no job, after its delay; an apply is never cut.
- Speed: `/app/state` 0.04 s for four matches, `/matches/` 0.07 s, `/app/server` 0.11 s; a real review's data loads
  in about 1 s (`Questions()` 0.99 s for 1,151 answers); `import volleyball_stats.review` 0.7 s.
- `/matches/remote.json` (1.2 s over ssh) is asked apart from the page, which does not wait for it.
- `icon.py`, `shortcut.py`, `club_settings.py`, `rekey.py`, `rename.py` (the duplicate port apart): nothing found.
- Native Windows: out of scope by design (`doctor.system()` knows mac, wsl, linux; the code uses `os.nice`,
  `os.killpg`, `ps`): Windows means WSL2, as `docs/setup.md` says.
- The area's tests: `291 passed, 1 skipped in 10.89s`.

## Not checked

- Anything under Windows/WSL2 (SRV-17, the loopback question of SRV-06).
- What browsers do on a local-network address (SRV-19): no browser was available.
- POST routes and a match's routes on the running server (POSTs were forbidden, and it showed the list); those were
  read, or run in scratch through `app.handle`.
- The time a review takes to open (`web.review_page` and the pictures): not measured.
