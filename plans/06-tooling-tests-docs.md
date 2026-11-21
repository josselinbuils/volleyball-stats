# Tooling, tests, docs and project health — improvements

One entry per finding, most valuable first. IDs are `TOOL-NN`.

Measured on 21 Nov 2026, macOS (M4 Pro), `main` at `a594cda`, working tree clean:

| Check | Result |
|---|---|
| `uv run pytest -q --durations=15` | 1101 passed, 1 skipped (`tests/test_jobs.py:68`, "no /proc here"), 47.0 s wall (56 s with `-W default`), 26 warnings (all `ResourceWarning`, TOOL-26) |
| Slowest tests | `test_web.py::TestPhotos::test_saves_a_picture…` 4.84 s, `test_video_copies.py` 3.92 + 3.29 + 2.54 s, `test_court.py::TestSnapping` 1.99 s, `test_backup_flow.py` 1.92 s; everything else under 1.7 s |
| Same suite from a clean `git archive` export, empty `HOME`, no `models/`, `data/`, `outputs/` | 1101 passed, 52 s, but it downloaded two models (TOOL-05) |
| Random order (`uv run --with pytest-randomly pytest -p randomly`) | 1 failed, 1100 passed: order-dependent (TOOL-06) |
| Coverage (`uv run --with pytest-cov pytest --cov=volleyball_stats`) | 69 % of 16,841 statements (TOOL-12, TOOL-13) |
| `npx tsc --noEmit -p .` | clean, 5.9 s |
| `npm test` (vitest 5.0.5) | 61 files, 430 tests, 1.05 s |
| `npm audit` | 6 moderate, all under the `shadcn` CLI (TOOL-09) |
| `uvx ruff check src tests benchmarks` (0.17.6, default rules) | 422 findings, 213 auto-fixable; `--select F`: 16 (TOOL-07) |
| `uvx ruff format --check` | 169 of 195 files would change (the project's long lines): not worth adopting |
| `uvx pyright src/volleyball_stats` | 362 errors in 15 s, see "Looked at, fine" |
| Page built into a scratch folder (`vite build --outDir …`, 5 builds, about 3 s) | byte-identical to the committed `site/` and `matches_site/` |
| Fresh clone | 51 MB (`--depth 1`: 3.3 MB); the local `.git` is 165 MB only because 120 MB is loose objects |

## TOOL-01 The app's update leaves conflict markers in the learned attribution weights

- **Type**: bug
- **Impact**: high — any installation that retrained ("Mettre à jour" / "Réanalyser") and then takes a code update whose commits also retrained: attribution crashes on every match and every later update is refused, with a git message.
- **Effort**: M
- **Confidence**: confirmed for git's behaviour (reproduced in a scratch repo); read for the app's path around it.
- **Duplicate** (21 Nov, by the audit's lead): same defect as PIPE-02 (`plans/03-pipeline.md`), found independently; SRV-03 (`plans/01-server-app.md`) is the same `--autostash` exit code for code files. One fix covers the three: see the index.
- **Where**: `src/volleyball_stats/learn.py:223`, `benchmarks/attribution/ranker.py:127,152-153`, `src/volleyball_stats/ranker.py:15,72-73`, `src/volleyball_stats/analysis.py:60`, `src/volleyball_stats/app.py:738-748`, `src/volleyball_stats/backup.py:42`, `docs/setup.md:19`, `tests/test_app.py`
- **Problem**: `learn.train` runs `benchmarks/attribution/ranker.py … --write --if-better`, which rewrites the **tracked** file `src/volleyball_stats/attribution_ranker.json` in the user's clone. Upstream rewrites it too (14 commits, the last ones titled "retrained … by the app's update"). `app.update` then runs `git pull --ff-only --autostash` and only looks at the exit code. Reproduced with two scratch repos changing one JSON file on both sides:
  ```
  Applying autostash resulted in conflicts.
  Your changes are safe in the stash.
  rc=0
  <<<<<<< Updated upstream
  {"w": [4, 5, 6], "touches": 200}
  =======
  {"w": [7, 8, 9], "touches": 150}
  >>>>>>> Stashed changes
  ```
  Exit code 0, so `update()` goes on to `uv sync` and the restart. `ranker.load` is `json.loads(path.read_text())`: `JSONDecodeError` at the next attribution. The file stays `UU`, so the next "Mettre à jour" fails with "Pulling is not possible because you have unmerged files". `docs/setup.md:19` already tells the owner to resolve this by hand between their two machines; a user without git knowledge cannot.
- **Plan**:
  1. Learned weights leave the tracked tree: `ranker.py` gets `LEARNED = Path("outputs/learned/attribution_ranker.json")` and `load()` reads it when it exists, else the packaged `WEIGHTS` (the shipped default). `backup.SHARED` already carries `learned`, so both machines share it like the play and gesture models.
  2. `benchmarks/attribution/ranker.py --write` writes to `ranker.LEARNED` (lines 152-154); `analysis.fingerprint` (line 60) stamps the file `load()` would read, so a retrain still reruns the matches.
  3. `app.update` stops trusting the exit code alone: after the pull, `git -C ROOT diff --name-only --diff-filter=U`; if a file is listed (any other tracked file changed by hand), `git checkout HEAD -- <those files>` (the pulled version; the local one stays in `git stash list`) and raise `RuntimeError` with an `explain` key naming them, not git's words.
  4. Suspected, to check with an older uv on the PC: `uv run stats` may rewrite the tracked `uv.lock` (no `--frozen` in `install.sh:72`'s launcher nor in `app.restart_command`, `app.py:147-153`), dirtying the tree the same way; if it does, add `--frozen` to both and to `uv sync` at `app.py:746`.
  5. `docs/setup.md:19`: drop `attribution_ranker.json` from the files that conflict.
  6. Tests in `tests/test_app.py`: two temporary repos (as the reproduction above); `update()` on a clone with a conflicting local change raises and leaves `git status --porcelain` without `UU`; on a clean clone it fast-forwards. A test in `tests/test_ranker.py` that `load()` prefers `LEARNED`.
  7. Run `benchmarks/attribution` (`answers.py`) before and after: same numbers (only the file's place changes).
- **Check**: `uv run pytest -q tests/test_app.py tests/test_ranker.py`; by hand, retrain in the app, then `git status --short` shows no change under `src/`.

## TOOL-02 The public history gives the server's address, and the server's limits trust a header

- **Type**: security
- **Impact**: high — the repository is public: anyone reading two old commits of `CLAUDE.md` gets the hosting server's real address behind Cloudflare, its root login name and a webhook endpoint's port; reached directly, the video password's 10-a-minute limit may be bypassed, and that password guards footage of real people.
- **Effort**: M (server side, with the owner) + S (optional history rewrite)
- **Confidence**: confirmed for the history; suspected for the bypass (left to check on the server: whether ports 80/443 already refuse everything but Cloudflare's ranges; no ssh was allowed).
- **Verified** (21 Nov, by the audit's lead): the bypass does not apply today: from an outside address the origin's ports 80, 443 and 8090 give no answer (8 s timeouts), so only Cloudflare reaches nginx and the header is its own. What stays true: the address is in the public history (low while the firewall holds), and `docs/hosting.md` should tell other hosts to do the same (plan step 2). Impact: low, not high.
- **Where**: commits `a1729b0` and `19eeabf` (both 16 Nov, `CLAUDE.md`, added then removed); `docs/hosting.md:57`; `docs/nginx.conf:5,27`; the owner's server.
- **Problem**: `git log --all -S'<the address>' --name-only` returns those two commits: the new and the old VPS's IPv4 addresses, `root@` in front, an `http://…:8090/webhook` endpoint and a note on a temporary ssh key. Nothing else sensitive was found in 974 commits (see "Looked at, fine"). `docs/hosting.md:57` says the owner's own nginx keys its limits on `$http_cf_connecting_ip`: that is a request header, which only Cloudflare sets honestly. A client talking to the origin directly chooses its value per request, so `limit_req_zone … zone=video … rate=10r/m` no longer limits password guesses (6 characters at least, `docs/state.md:156`).
- **Plan**:
  1. On the server (owner): accept 80/443 only from Cloudflare's published ranges (firewall, or nginx `allow`/`deny all`), and replace the header by `set_real_ip_from <Cloudflare ranges>; real_ip_header CF-Connecting-IP;` with the limits keyed on `$binary_remote_addr` as `docs/nginx.conf` does. Check the webhook on 8090 is closed to the outside or checks its secret; root ssh by key only.
  2. `docs/hosting.md` "Your own server": one paragraph for anyone behind a proxy: the two `real_ip` lines, never a raw `$http_…` header as a limit's key.
  3. Optional, the owner's call: rewrite the two commits (`git filter-repo --replace-text`) and force-push; forks and GitHub's caches keep the old ones, so step 1 is what protects. If rewritten, both machines re-clone.
- **Check**: from a machine outside Cloudflare, `curl -m 5 -H 'Host: <site>' http://<origin>/` times out or is refused; 20 wrong-key requests in a minute through the public address get 429 after the burst whatever `CF-Connecting-IP` header is sent.

## TOOL-03 A 6.9 GB backup of `outputs/` at the root is one `git add -A` from being committed

- **Type**: security
- **Impact**: high — `backup outputs 08-11-2026.zip` holds the names files and results of real matches; the project's rule is to commit and push after every change, and nothing ignores the file.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `.gitignore`
- **Problem**: `git add -A --dry-run` prints `add 'backup outputs 08-11-2026.zip'`; `git check-ignore` matches nothing for it. `unzip -l` lists 159 entries among names files, pictures and videos. GitHub would refuse this one at push (over 100 MB), after a commit of 6.9 GB to undo; a smaller archive (results without videos) would go through to the public repository. `.idea/` is ignored only by the owner's global `~/.gitignore` (absent on the PC or for a contributor); `.coverage` and `htmlcov/` are not ignored either.
- **Plan**:
  1. `.gitignore`: add `*.zip`, `/backup*`, `.idea/`, `.coverage`, `htmlcov/`.
  2. Tell the owner the archive would be safer outside the repository's folder (their call).
- **Check**: `git add -A --dry-run` prints nothing; `git status --short` is empty.

## TOOL-04 No CI: a workflow that runs what `CLAUDE.md` asks to run by hand

- **Type**: tests
- **Impact**: high — every commit goes straight to `main` (972 in 30 days of work), the checks rely on whoever commits remembering them, and only one OS is ever exercised per commit.
- **Effort**: M
- **Confidence**: read (the commands were all run locally; the workflow itself was not run)
- **Where**: new `.github/workflows/checks.yml`; `tests/test_web.py:828-880` (TOOL-05 first)
- **Problem**: there is no `.github/`. Facts the design rests on: the suite passes from a clean export in 52 s; the page builds reproducibly in about 3 s; 12 of the 573 commits touching `web/src` changed sources without the build; native Windows is not a target of the code (`os.nice`, `os.getloadavg`, `os.killpg`, `ps`, `/proc`: `app.py:1078`, `doctor.py:98`, `jobs.py:371,245`), "Windows" being Ubuntu under WSL2 (`README.md:95`), so `ubuntu-24.04` is the Windows run and `windows-latest` would only fail.
- **Plan**:
  1. `.github/workflows/checks.yml`, on `push` to `main` and `pull_request`, `concurrency: {group: checks-${{ github.ref }}, cancel-in-progress: true}`, actions pinned by commit SHA, no secret:
     ```yaml
     jobs:
       python:
         strategy: {fail-fast: false, matrix: {os: [ubuntu-24.04, macos-15]}}
         runs-on: ${{ matrix.os }}
         steps:
           - uses: actions/checkout@<sha>
           - uses: astral-sh/setup-uv@<sha>
             with: {enable-cache: true, cache-dependency-glob: uv.lock}
           - run: sudo apt-get update && sudo apt-get install -y ffmpeg
             if: runner.os == 'Linux'
           - run: brew install ffmpeg
             if: runner.os == 'macOS'
           - run: uv sync --frozen
           - run: uv run pytest -q
             env: {YOLO_OFFLINE: "1", HF_HUB_OFFLINE: "1"}
           - run: uvx ruff@0.17.6 check src tests benchmarks --select F,B006,B008
           - run: uvx vermin --target=3.8- --violations src/volleyball_stats/sync_remote.py src/volleyball_stats/backup_remote.py
       web:
         runs-on: ubuntu-24.04
         defaults: {run: {working-directory: web}}
         steps:
           - uses: actions/checkout@<sha>
           - uses: actions/setup-node@<sha>
             with: {node-version-file: web/.nvmrc, cache: npm, cache-dependency-path: web/package-lock.json}
           - run: npm ci
           - run: npx tsc --noEmit -p .
           - run: npm test
           - run: npm run build
           - run: git diff --exit-code -- ../src/volleyball_stats/site ../src/volleyball_stats/matches_site
     ```
  2. What to know about the heavy dependencies: on Linux `uv sync` brings the CUDA build of torch with its NVIDIA libraries and `onnxruntime-gpu` (several GB; they cannot be left out, `import torch` loads them); the macOS environment is 1.2 GB. `setup-uv`'s cache keyed on `uv.lock` makes it a restore; a repository's caches are capped at 10 GB, so do not add a third OS. `ffmpeg` is needed by `test_decode`, `test_jobs`, `test_import_match`, `test_video_copies`, `test_teams`.
  3. What cannot run there: anything with a GPU or real footage (`stats match`, every `benchmarks/*/bench.py`: their clips are the YouTube clips never to republish and the club's matches), the Windows shortcut (`powershell.exe`), the review in a browser.
  4. Left to learn from the first run: whether the Linux build's hashed file names equal the Mac's (they are content hashes; the owner already commits builds from both machines). If not, run the `web` job on `macos-15`.
  5. `README.md` "Development": a line on the checks; `CLAUDE.md` "Check a change" keeps the local commands.
- **Check**: push a branch with a deliberate failing assert, then a source change in `web/src` without its build: both jobs go red; `main` goes green.

## TOOL-05 Two tests run the real pose and re-identification models, downloading them when absent

- **Type**: tests
- **Impact**: medium — on a fresh clone or in CI the suite needs the network and a third party's Google Drive, writes 59 MB into `./models/`, and fails offline; they are also the slowest tests.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `tests/test_web.py:828-880` (`TestPhotos`), `src/volleyball_stats/web.py:1600-1604,1737-1740`
- **Problem**: run from a clean export (`git archive HEAD | tar -x`, empty `HOME`), `pytest tests/test_web.py` leaves `models/yolo11m-pose.pt` (42 MB, Ultralytics' GitHub release) and `models/osnet_ain_x1_0_msmt17.pth` (17 MB, gdown from Google Drive) plus `~/.cache/gdown/cookies.txt`. The two tests stub `web.upscaler` (`monkeypatch.setattr(web, "upscaler", lambda: None)`) but not the pose model nor `identity.load_reid`. `YOLO_OFFLINE=1` did not stop it.
- **Plan**:
  1. In both tests, stub the two loaders as the upscaler is: `monkeypatch.setattr("ultralytics.YOLO", fake)` returning no keypoints for the grey frames (what the real model finds there: the expected crop `(17, 13)` comes from the box alone), and `monkeypatch.setattr(identity, "load_reid", …)` with `describe` returning unit vectors.
  2. Keep one line asserting no file appears under `models/` (`monkeypatch.chdir(tmp_path)` first).
- **Check**: from a clean export with the network off, `uv run pytest -q tests/test_web.py` passes and `ls models` fails; `--durations=5` no longer lists `TestPhotos` first.

## TOOL-06 After Ultralytics is imported, a logo Pillow cannot read tries a `pip install` and crashes

- **Type**: bug
- **Impact**: medium — a club whose logo file is not a readable picture loses the page build after an apply (the same process has imported Ultralytics by then); the suite hides it by test order.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/icon.py:53-58,74`, `src/volleyball_stats/__init__.py`, `tests/test_icon.py:30-32`
- **Problem**: `uv run pytest -q tests/test_identity.py tests/test_icon.py` fails every time (`1 failed, 45 passed`), as does the whole suite in random order:
  ```
  requirements: Ultralytics requirement ['pi-heif'] not found, attempting AutoUpdate...
  …/python: No module named pip
  FAILED tests/test_icon.py::TestIcon::test_does_without_an_unreadable_logo - ModuleNotFoundError: No module named 'pi_heif'
  ```
  `ultralytics/utils/patches.py` replaces `PIL.Image.open` for the whole process: on `UnidentifiedImageError` it calls `check_requirements("pi-heif")`, which runs `python -m pip install` twice (network waits; with pip present it would install a package into the user's environment unasked) and then raises `ModuleNotFoundError`. `icon.colours` catches `(OSError, ValueError)` only. In the app: `identity.py:375` imports `ultralytics.utils.ops` during an apply, then `web.club_page` (`web.py:512`) calls `icon.colours` for the favicon. The club dialog filters by MIME type only (`ClubDialog.tsx:29`, `club_settings.DATA_URL`), not by content.
- **Plan**:
  1. `src/volleyball_stats/__init__.py`: `os.environ.setdefault("YOLO_AUTOINSTALL", "false")` before anything imports Ultralytics (`ultralytics/utils/__init__.py:73` reads it): the app never installs packages at run time. `players.make_tracker` already stands in for `lap`.
  2. `icon.logo_colours` reads the picture without the patched opener: `cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)`, `None` giving `[]`; or keep Pillow and catch `ImportError` too in `colours`.
  3. `tests/test_icon.py`: the existing test first does `import ultralytics.utils.patches  # the patch in place`, so it no longer depends on order.
- **Check**: `uv run pytest -q tests/test_identity.py tests/test_icon.py` and `uv run --with pytest-randomly pytest -q -p randomly` both pass, with no "AutoUpdate" line in the output.

## TOOL-07 Three tests never run; one lint rule set would have said so

- **Type**: tests
- **Impact**: medium — two test classes are silently replaced by later classes of the same name; the project has no lint at all.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `tests/test_attribution.py:145,205`, `tests/test_sync.py:270,310`, `pyproject.toml`, and the files listed below
- **Problem**: `uvx ruff check src tests benchmarks --select F`:
  ```
  tests/test_attribution.py:205:7: F811 Redefinition of unused `TestReadPlayers` from line 145
  tests/test_sync.py:310:7: F811 Redefinition of unused `TestAuto` from line 270
  ```
  The first `TestReadPlayers` (1 test) and the first `TestAuto` (2 tests) are never collected. Run from a scratch copy with the classes renamed: `3 passed`, so nothing is broken today; the suite would be 1104. The other `F` findings are dead weight, not bugs: 10 unused imports (`identity.py:34`, `review.py:43` `backup`, `web.py:31`, `tests/test_decode.py:6`, `tests/test_film.py:9`, `tests/test_matches.py:2,10`, `tests/test_video_copies.py:6`, `benchmarks/pose/run.py:23`, `benchmarks/pose/score.py:15`), 2 unused variables (`benchmarks/actions/learned/evaluate.py:56` `rows`, `benchmarks/corrections/breakdown.py:60` `kept`), `match.py:340` an f-string without a placeholder, `tests/test_web.py:1069` a loop variable shadowing the imported `contacts`. `B006`/`B008` find 3 mutable or computed defaults (`court.py:489`, `web.py:1651`, `framing.py:76`), none mutated today.
- **Plan**:
  1. Rename the shadowed classes (`TestReadPlayersRoundTrip`, `TestAutoChoice`).
  2. `pyproject.toml`, no dependency added (ruff runs through `uvx`):
     ```toml
     [tool.ruff.lint]
     select = ["F", "B006", "B008"]
     ```
  3. `uvx ruff check --fix src tests benchmarks` for the 11 auto-fixable ones, the 5 others by hand; the three defaults become `None` with the value set inside.
  4. The CI step of TOOL-04; one line in `CLAUDE.md` "Check a change".
- **Check**: `uvx ruff check src tests benchmarks` prints "All checks passed!"; `uv run pytest -q` reports 1104 passed.

## TOOL-08 Ultralytics' usage analytics is on in every run

- **Type**: security
- **Impact**: medium — each analysis tells Google Analytics, through Ultralytics, the machine's CPU model, system, Python and torch versions, the model's name and an install id; nothing in the app or the docs says so, in a project whose line is that nothing leaves the machine unasked.
- **Effort**: S
- **Confidence**: read (`events.enabled` is `True` here; the request itself was not captured)
- **Where**: `src/volleyball_stats/players.py:73-77` and the five other `from ultralytics import YOLO` (`actions.py:372`, `attribution.py:225`, `jumps.py:115`, `film.py:1261`, `web.py:1600`)
- **Problem**: `.venv/bin/python -c "from ultralytics.utils.events import events; print(events.enabled, events.metadata)"` prints `True` and `{'install': 'git', 'python': '3.12', 'torch': '2.14.1', 'CPU': 'Apple M4 Pro', 'version': '8.4.184', 'env': 'Darwin', …}`. `ultralytics/utils/events.py:224` queues an event at each predictor's start and posts it to `https://www.google-analytics.com/mp/collect` (at most one flush per 30 s) while `SETTINGS["sync"]` is true, its default. No player data is in it.
- **Plan**:
  1. One loader for the six call sites, in `players.py`: `def yolo(path)`, which imports `YOLO`, sets `ultralytics.utils.events.events.enabled = False` and returns `YOLO(str(path))`. In-process only: it does not rewrite the user's global `Ultralytics/settings.json`, which other projects share.
  2. The same place sets `HF_HUB_DISABLE_TELEMETRY=1` (`os.environ.setdefault`, beside TOOL-06's line) for the Hugging Face downloads.
  3. A test: after `players.yolo` on a stubbed `YOLO`, `events.enabled is False`.
- **Check**: `uv run python -c "from volleyball_stats import players; from ultralytics.utils.events import events; players.yolo('models/yolo11m.pt'); print(events.enabled)"` prints `False`.

## TOOL-09 292 of the 493 locked npm packages are there for one CSS file

- **Type**: maintainability
- **Impact**: medium — the `shadcn` command-line tool is a devDependency only for `@import 'shadcn/tailwind.css'`; it brings an HTTP server framework, an MCP SDK and `ts-morph`, and every `npm audit` advisory.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `web/package.json:31`, `web/src/index.css:3`, `web/package-lock.json`, `docs/match-page.md` ("Changing the page")
- **Problem**: walking `package-lock.json` from the root's dependencies: 493 packages reachable, 201 without `shadcn`. `grep -rn shadcn web/src web/package.json` finds one use, `src/index.css:3`. The imported file is `node_modules/shadcn/dist/tailwind.css`, 637 lines of keyframes and `@custom-variant` rules. `npm audit`: 6 moderate (hono, and minimatch through `@ts-morph/common` → `ts-morph` → `shadcn`), `npm audit fix --force` proposing `shadcn@1.0.0`.
- **Plan**:
  1. Copy `node_modules/shadcn/dist/tailwind.css` to `web/src/shadcn.css` (MIT: keep its notice in a first-line comment with the version, 4.22.1); `index.css:3` becomes `@import './shadcn.css';`.
  2. Remove `shadcn` from `devDependencies`, `npm install`; add a component later with `npx shadcn@<version> add …`, written in `docs/match-page.md`.
  3. `npm run build`: the two style sheets must come out byte-identical (same hashed names); if `web/online.ts`'s Tailwind `@source` handling needs the new file, it is in `src/` already.
- **Check**: `npm audit` reports 0 vulnerabilities; `npm ls --all | wc -l` drops by about 290; `git status` after the build shows no change under `src/volleyball_stats/site*/assets/`.

## TOOL-10 The models come from other people's Google Drives, unchecked, with a raw error when that fails

- **Type**: bug
- **Impact**: medium — a new installation cannot analyse anything the day a Drive file hits its download quota or is removed; the user sees a Python traceback.
- **Effort**: M
- **Confidence**: read (the failure itself was not provoked)
- **Where**: `src/volleyball_stats/ball.py:74-79`, `src/volleyball_stats/identity.py:206-213`, `src/volleyball_stats/web.py:124,1529-1545`, `src/volleyball_stats/doctor.py:113-135`, `pyproject.toml:8`
- **Problem**: the ball model (`wasb_volleyball.pth.tar`, 6 MB) and the re-identification model (`osnet_ain_x1_0_msmt17.pth`, 17 MB) are fetched with `gdown.download(id=…, quiet=True)` from their authors' personal Drives: no mirror, no size or hash check, and gdown's quota error ("Too many users have viewed or downloaded this file recently") reaches the job's log as it is; when gdown returns without a file, the next line is `torch.load(path)` and a `FileNotFoundError`. `web.upscaler` calls `urllib.request.urlopen(UPSCALER_URL)` with no timeout (a stalled connection holds the page build for good, against "nothing waits for good") and reads 29 MB in one go. `weights_only=True` on both `torch.load` calls and safetensors for the upscaler mean a tampered file cannot run code: the gap is availability and a clear message, not code execution. The Hugging Face models (`likeness.MODEL`, `gesture.BASE`) are pinned to no revision.
- **Plan**:
  1. One helper in `files.py`, `fetch(url, path, sha256, timeout=30)`: `urllib` stream to a temporary file beside `path`, hash checked, `os.replace`; `RuntimeError("model")` with the file's name on failure, mapped in `web/src/lib/errors.ts` (`explain`) to a short text ("Modèle introuvable : réessayez plus tard"), fr and en.
  2. With the owner (publishing is theirs): the two weights as assets of a GitHub release of this repository (both MIT, `vendor/LICENSE-WASB.md`, `vendor/LICENSE-OSNET.md`); `ball.load_model` and `identity.load_reid` call `fetch` on that URL, the Drive id kept as second source. `gdown` then leaves `pyproject.toml` (and beautifulsoup4, soupsieve, PySocks from the lock) — a dependency removed, none added.
  3. `web.upscaler` uses the same helper (timeout, hash).
  4. `revision="<commit>"` on the three `from_pretrained` calls that download (`likeness.py:71`, `gesture.py:221`, `play_training.py:204`).
  5. Tests: `fetch` on a local `http.server` in a thread: a good file lands, a wrong hash leaves nothing and raises, a server that never answers raises within the timeout.
- **Check**: `rm models/wasb_volleyball.pth.tar`, then the app's "Diagnostics" → download: the file is back with the expected hash; with the network off the app shows the short text, not a traceback.

## TOOL-11 `install.sh` on a machine it cannot serve ends in an error a beginner cannot read

- **Type**: cross-platform
- **Impact**: medium — an Intel Mac, a Linux without `apt`, or Windows' Git Bash each fail minutes in, with another tool's message.
- **Effort**: S
- **Confidence**: read (walked through, not run on those machines)
- **Where**: `install.sh:22,45-59,62-65`, `README.md:85-97`, `docs/setup.md:9-14`
- **Problem**:
  - Intel Mac: `uv.lock` has no `macosx_*_x86_64` wheel for torch 2.14.1 (only `macosx_14_0_arm64`). The script installs Homebrew (10 minutes, a password) and three tools, clones, then `uv run stats` stops on uv's "no wheel for the current platform". `README.md:85` says "a Mac with an Apple chip"; the script does not check `uname -m`.
  - macOS older than 14: same wheel floor, same ending.
  - Linux without `apt-get` (Fedora, Arch): `sudo apt-get update` → "command not found", `set -e` ends the script.
  - Git Bash / MSYS on Windows: `uname -s` is `MINGW64_NT…`, the `else` branch runs `sudo apt-get`.
  - `$DIR` existing without `.git` (a folder made by hand, an unpacked zip): `git clone` → "destination path already exists and is not an empty directory".
  - Disk: the first start downloads about 1.2 GB on a Mac and several GB on Linux (CUDA) with no word on the room needed; `doctor.disk` only speaks once the app is open.
- **Plan**:
  1. Before installing anything, a `stop()` helper printing one plain sentence and exiting 1, for: Darwin with `uname -m` not `arm64`; Darwin with `sw_vers -productVersion` under 14; `uname -s` neither Darwin nor Linux ("On Windows, run this line inside Ubuntu (WSL2): see the README"); Linux without `apt-get` (name the three tools to install by hand, then run again); `$DIR` existing, non-empty, without `.git`.
  2. `df -Pk "$HOME"`: under 10 GB free, the same `stop` with the number.
  3. `README.md` step 1: "about 10 GB of free disk for the app, 150 GB to process matches" (the numbers of `doctor.DISK_GB`, `WARN_DISK_GB`).
- **Check**: `sh install.sh` with `uname` stubbed on the `PATH` (a scratch `uname` script printing `x86_64` / `MINGW64_NT`) prints the sentence and exits 1 before any install; on the Mac and the PC it still starts the app.

## TOOL-12 The review server's HTTP layer has no test

- **Type**: tests
- **Impact**: medium — every answer, apply, upload and file request goes through `review.serve`'s handler; it is the largest untested block of the project.
- **Effort**: L
- **Confidence**: confirmed (coverage numbers); the seam proposed is read, not tried
- **Where**: `src/volleyball_stats/review.py:2554-3438` (`serve`), `:2457-2552` (`serve_list`), `:2107-2133` (`send_file`), `tests/test_review.py`
- **Problem**: coverage by function: `serve` 676 of 699 statements never run, of which `Handler.post` 292 of 292 and `Handler.get` 72 of 72; `serve_list` 78 of 80; `send_file` 23 of 24. `serve` is one 880-line function: the handler, its locks and 20 inner functions close over its locals, and it opens the video, builds the page and starts five threads before listening, so no test can reach a route. What the routes guard is tested only one level down (`network.same_site`, `range_of`).
- **Plan**:
  1. Smallest seam, no behaviour change: split `serve` at `review.py:3417` into `server_for(match, video, court, squad, theme, port, roster) -> Server` (everything up to `Server((bind, port), Handler)`, threads not started) and the rest (threads, `presence.watch`, `serve_forever`). Same for `serve_list`.
  2. `tests/test_review.py`, a fixture match as `TestPhotos` builds (a 20-frame grey video, four CSV files), `server_for(…, port=0)`, `serve_forever` in a thread, then with `urllib`:
     - `GET /current` → the match's name;
     - `GET /%2e%2e/%2e%2e/pyproject.toml` and `GET //etc/hosts` → 404;
     - `GET /assets/<file>` with `Range: bytes=0-9` → 206, 10 bytes, `Content-Range`; `Range: bytes=999999999-` → what `range_of` decides;
     - any `POST` with `Origin: http://evil.example.com` → 403; without the `Origin` a browser sends → as `ours()` decides;
     - `POST` of one answer → `identity_answers.json` holds it, the reply's `answered` is 1.
  3. Only then, route by route, the rest of `Handler.post`.
- **Check**: `uv run --with pytest-cov pytest --cov=volleyball_stats.review -q tests/test_review.py`: `review.py` above 70 % (55 % today).

## TOOL-13 Risky functions with no test, by name

- **Type**: tests
- **Impact**: medium — each one below decides something a wrong answer makes costly (a worse model kept, a server copy moved, a match not rebuilt) and is never executed by the suite.
- **Effort**: M
- **Confidence**: confirmed (never executed, from `coverage json` mapped to functions); what each test should assert is read from the code
- **Where**: as listed
- **Problem**: per-module coverage, lowest of the modules with logic: `gesture_training.py` 30 %, `doctor.py` 37 %, `voice.py` 39 %, `match.py` 40 %, `film.py` 41 %, `lens.py` 48 %, `jerseys.py` 51 %, `review.py` 55 %, `play_training.py` 56 %, `learn.py` 59 %, `app.py` 63 %, `court.py` 65 %, `gesture.py` 65 %, `scoreboard.py` 67 %, `shortcut.py` 69 %, `network.py` 70 %, `identity.py` 71 %, `sync.py` 77 %. Modules without a test file: `backup_remote` (80 % through `test_backup.py`), `sync_remote` (93 % through `test_backup_flow.py`), `gesture_training`, `voice`. Much of the rest is model inference, rightly left to the benchmarks. Worth a test, no GPU needed:
  - `app.update` (`app.py:738`, 9 of 10): see TOOL-01.
  - `app.stop` (`app.py:1044`, 14 of 18): a fake server answering 409 to `/app/quit` → exit status 1 and the "being applied" line; one that keeps listening → "Still running.", 1.
  - `app.import_steps` (`app.py:425`, 24 of 25) and `app.run_pipeline` (`app.py:556`, 11 of 12): the command lines they build for a job, given a card with two chapters and a court already known.
  - `doctor.disk`, `memory`, `gpu`, `checks` (`doctor.py:44-108`): `shutil.disk_usage` stubbed at 59, 149 and 151 GB → error, warn, ok; a `/mnt/c/...` path with `system() == "wsl"` → `slow`; a check that raises → an `error` row carrying its id, the others still returned.
  - `play_training.check` (`play_training.py:147`, 11 of 12): the gate that lets retrained weights replace the old ones; with `train`, `clips_p` and `no_model` stubbed, a model placing fewer sure clips than no model must not be reported as better.
  - `learn.rerun` (`learn.py:260`, 35 of 36): with `train` and the pipeline stubbed, the order train → pipeline → answers moved, and that a failing step leaves `learn.json` as it was.
  - `web.renew_code` (`web.py:1474`, 7 of 8): a hosted page given the new build keeps its `data.js` content, loses `review-app.js`, and its old hashed assets are gone.
  - `web.build` (`web.py:1932`, 48 of 51): the page's top-level builder; one run on the fixture match asserting the files of `site/`.
  - `backup.rename_copies` (`backup.py:277`, 6 of 7): `rename_command` is tested as a string; run it with `sh -c` on a temporary tree: a copy under the old name moves, one where the new name exists is left alone, a match name with a space or a quote survives.
  - `jobs.stop` (`jobs.py:365`, 7 of 8): a job running `sleep 30` with a child: after `stop`, both are gone and the record says `stopped`; a record whose pid now belongs to another process is not signalled.
  - `network.configure_windows` (`network.py:141`, 11 of 12): the PowerShell text it would run elevated, with `subprocess.run` stubbed; a port that is not a number is refused before anything runs.
  - `shortcut.make`, `make_linux`, `refresh` (`shortcut.py:124-176`): with `HOME` in `tmp_path`, the `.desktop` entry's `Exec` and `Icon`, and that a second `refresh` with the same colours makes nothing.
  - `sync.main` (`sync.py:567`, 42 of 42): `pull --all` wiring, the one "Tout récupérer" starts as a job.
  - `review.Questions.build` (`review.py:575`, 68 of 69) and `Questions.conflicts` (`review.py:444`, 29 of 30): the questions asked for a fixture with two look-alike pieces.
  - `presence.watch` (`presence.py:63`, 12 of 13): with a fake clock, the stop callback fires once after the last page leaves, never while `busy()` is true.
- **Plan**:
  1. Add them in the order above, each in its module's test file, inside a class, fixtures from `tmp_path` and `monkeypatch` as the suite does.
  2. In CI (TOOL-04) print the total with `uv run --with pytest-cov pytest --cov=volleyball_stats --cov-report=term:skip-covered -q` in a non-blocking step; no threshold.
- **Check**: the coverage of `doctor.py`, `app.py`, `learn.py` and `play_training.py` rises; `uv run pytest -q` stays under a minute.

## TOOL-14 The shared link's picture and the films use fonts only a Mac has

- **Type**: cross-platform
- **Impact**: medium — on the PC that processes the matches (WSL2), the preview picture and every film fall back to OpenCV's font, whose zero is slashed: a score's "0" reads "Ø".
- **Effort**: S
- **Confidence**: read (the Mac path and the fallback are in the code; the PC's output was not looked at)
- **Where**: `src/volleyball_stats/matches.py:77-78,146`, `src/volleyball_stats/film.py:48,1217-1219,1267`
- **Problem**: `CARD_FONT = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")` with `cv2.FontFace(str(CARD_FONT) if CARD_FONT.exists() else "sans")`, the comment beside it saying what the fallback does ("a score's "0" then reads "Ø""). `film.FONTS` is the same folder for Arial Bold Italic, DIN Alternate Bold and DIN Condensed Bold. Against the rule that nothing relies on one system; the same match gives different pictures on the two machines.
- **Plan**:
  1. One helper in `files.py`, `font(*names) -> str`: the first existing path among the Mac's folder and what Ubuntu has after `apt install ffmpeg` (fontconfig brings DejaVu: `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`, `DejaVuSansCondensed-Bold.ttf`, `DejaVuSans-BoldOblique.ttf`), else `fc-match -f '%{file}' 'sans:bold'` when `fc-match` exists, else `"sans"`. No font is added to the repository.
  2. `matches.py:146` and `film.font` call it.
  3. Tests: with the candidates in `tmp_path`, the first existing wins; none → `"sans"`.
- **Check**: on the PC, rebuild one match's preview (`outputs/hosted/<match>/preview.png`) and one film: the score's zeros are plain.

## TOOL-15 The two scripts sent to the server must run on its Python; nothing checks it

- **Type**: tests
- **Impact**: low — `sync_remote.py` and `backup_remote.py` are piped to the server's `python3`; a newer syntax would pass every local test (Python 3.12) and fail every backup.
- **Effort**: S
- **Confidence**: confirmed (today both need 3.5 only: `uvx vermin` → "Minimum required versions: 3.5")
- **Where**: `src/volleyball_stats/sync_remote.py:2`, `src/volleyball_stats/backup_remote.py:2`, `.github/workflows/checks.yml`
- **Problem**: both docstrings say "the server's python3 (3.8)"; `docs/state.md:47` says the server is Ubuntu 26.04 since 16 Nov. Either floor is fine; none is enforced.
- **Plan**:
  1. The `vermin --target=3.8- --violations` step of TOOL-04.
  2. Correct the two docstrings to the floor kept ("3.8 or later").
- **Check**: on a branch, a line using `str.removesuffix` (3.9) in `sync_remote.py` turns the step red.

## TOOL-16 Every machine picks its own Python

- **Type**: maintainability
- **Impact**: low — the Mac's environment sits on Anaconda's 3.12.7 (`.venv/pyvenv.cfg`: `home = /opt/anaconda3/bin`); another machine takes whatever 3.12+ it finds (3.14 on a recent Ubuntu), so a failure can belong to one machine's interpreter.
- **Effort**: S
- **Confidence**: confirmed for the fact; suspected for any harm (the lock has wheels for 3.12, 3.13 and 3.14)
- **Where**: new `.python-version`, `docs/setup.md:14`
- **Problem**: no `.python-version`; `requires-python = ">=3.12"`. uv prefers a system interpreter over its managed ones.
- **Plan**:
  1. `.python-version` with `3.12`: uv downloads and uses its own 3.12 everywhere, CI included.
  2. On each machine the next `uv run` rebuilds `.venv` once (minutes): tell the owner before.
- **Check**: `uv run python -V` prints 3.12.x on both machines and in CI.

## TOOL-17 No inventory of the models' licences, and one of them is non-commercial

- **Type**: docs
- **Impact**: medium — the README states the code's licence only; someone hosting matches for a fee, or the owner's later plan for other clubs, would not know which weights restrict that.
- **Effort**: M
- **Confidence**: read for the list; suspected for two licences quoted from memory (VideoMAE's and MSMT17's terms: check the model card and the dataset page before writing them down)
- **Where**: `docs/pipeline.md` (new short table), `README.md:152-155`, `web/vite.config.ts` and the three other vite configs
- **Problem**: what the project downloads or builds on, and where its licence is written today:
  | Weights | Used in | Licence | Written down? |
  |---|---|---|---|
  | YOLO11 m, m-pose, s-seg, m-seg | `players.py`, `actions.py`, `film.py` | AGPL-3.0 (the reason for the project's licence) | `README.md:154` |
  | WASB volleyball HRNet | `ball.py` | MIT (repository) | `vendor/LICENSE-WASB.md` (the code) |
  | OSNet-AIN x1.0, trained on MSMT17 | `identity.py` | MIT (torchreid); MSMT17 itself is released for research | `vendor/LICENSE-OSNET.md` (the code) |
  | 4xNomosWebPhoto RealPLKSR | `web.py:119-124` | CC-BY-4.0 | a code comment |
  | SegFormer B2 clothes | `likeness.py:20` | MIT | `docs/match-page.md:102` |
  | VideoMAE base, Kinetics | `gesture.py:29`, `play_training.py:29`; the learned play and gesture models derive from it | CC-BY-NC-4.0 on its model card | nowhere |
  | Kokoro-82M, SIWIS voice | `voice.py:57` | Apache-2.0, corpus CC-BY-4.0 | on the page itself |
  Code dependencies are all compatible with AGPL-3.0 (Python: MIT, BSD, Apache-2.0, MPL-2.0, PSF, and Ultralytics' AGPL; web: 90 MIT, 2 Apache-2.0, 1 ISC, 1 0BSD). Second gap: the committed and hosted bundles carry no third-party notice (`grep -c '@license'` is 0 in `index-*.js`, `scene3d.js`, `review-app.js`, `app.js`), while MIT and Apache-2.0 ask for the notice to travel with copies. The source offer AGPL asks for is there (`ClubBar.tsx:39` links the repository on every page).
- **Plan**:
  1. `docs/pipeline.md`: the table above, checked against each model card, with one sentence: the play and gesture models, built on VideoMAE, are for non-commercial use.
  2. `README.md` "License": one line pointing to it.
  3. The bundles' notices: one generated `THIRD_PARTY_LICENSES.txt` beside `index.html` and `matches.html`, written by a 20-line plugin in `web/online.ts` (`generateBundle`: for each bundled module under `node_modules`, its package's name, version and `LICENSE` text, deduplicated) and added to the four vite configs; no dependency added.
- **Check**: `ls src/volleyball_stats/site/THIRD_PARTY_LICENSES.txt` after a build, React, three and lucide named in it; the table's licences match the cards.

## TOOL-18 Real players' first names in tracked files

- **Type**: security
- **Impact**: low — first names only, and the hosted pages show names by the owner's choice; but the rule is that names of real people stay in `outputs/`, and three places tie a name to a tracking fault or a spelling.
- **Effort**: S
- **Confidence**: confirmed (the roster's names searched in the tree and in the history, counts only)
- **Where**: `benchmarks/identity/README.md:84,87`; `docs/corrections_log.md:403`; `docs/history.md:349`; `src/volleyball_stats/speech.py:161`; fixtures in `tests/test_review.py`, `tests/test_speech.py`, `tests/test_likeness.py`, `tests/test_matches.py`, `tests/test_identity.py`, `tests/test_feedback.py`, `web/src/helpers/players.test.ts`, `web/src/components/Review/helpers/players.test.ts`, `web/src/components/Watch/helpers/commentary.test.ts`, `web/src/components/Watch/helpers/replay.test.ts`, `web/src/lib/format.test.ts`
- **Problem**: 16 of the roster's 22 first names appear in tracked files (the others nowhere, in the tree or in 974 commits). In the docs they name a real player's card or spelling; in the tests they are fixtures that happen to be the club's players. No surname, picture, or names file was ever committed (`git log --all --name-only` shows no path under `outputs/`).
- **Plan**:
  1. The four doc and docstring lines: "a player", "one player's second card", a made-up name for the elision example.
  2. The owner's call for the fixtures: keep (common first names) or replace by invented ones in one pass; the tests' expectations on elision ("d'A…") need a name starting with a vowel.
- **Check**: the scan used here (names read from `outputs/roster.json` at run time, `git grep -n -i -w -F`) returns nothing for the doc files.

## TOOL-19 A real club's logo is tracked where the code says brands stay out

- **Type**: docs
- **Impact**: low — a public AGPL repository redistributes a club's logo and colours; the code's own comment says brands stay off the repository.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `branding/aspom/Logo_ASPOM.png`, `branding/aspom/brand.json`, `.gitignore:10`, `src/volleyball_stats/web.py:500-502`, `docs/processing.md:240-244`, `web/src/index.css:139`, `web/src/locales/*.json:228`
- **Problem**: `git ls-files branding` lists the logo (152 KB) and `brand.json`; only `branding/*/sponsors/` is ignored. `web.py:501`: "(git-ignored under branding/: brands stay off the repository)". The README's screenshots show the same logo. The licence (AGPL) does not cover a club's mark. Smaller, same family: the theme named "Haikyu!!" is a colour scheme only (no artwork or font), the name being a publisher's mark.
- **Plan**:
  1. The owner's call, one of: a line in the README ("the ASPOM Bègles Volley name and logo belong to the club, shown with its agreement, not under this licence"), or `git rm --cached branding/aspom` with `branding/*/` ignored but the example (the app's club lives in `outputs/club/` already).
  2. Make the comment at `web.py:501` say what is true after 1.
- **Check**: `git ls-files branding` and the comment agree.

## TOOL-20 `docs/state.md` lists 31 "open" items, most of them done

- **Type**: docs
- **Impact**: medium — the file `CLAUDE.md` names as "start here when asked what to do" needs a full read of 184 dense lines to find the handful of things actually left.
- **Effort**: M
- **Confidence**: confirmed
- **Where**: `docs/state.md:18-184`, `docs/history.md:1`, `CLAUDE.md` (the "Read when needed" table), `docs/README.md:19`
- **Problem**: under "## Open", 15 items start with "Done" and about 10 more are dated accounts of finished work (17, 18, 21-31). What is open is spread inside them: item 3 (the 3D ball and TV mode's limits), 4 "Left:", 7 "Left:", 9 (the job queue, on hold), 14 (saving every edit at once), 18 "Not looked at", 19 "Not looked at", 20 (VR, an idea), 24 "Left:", 30-31 "Next:". `docs/history.md` is titled "History (1-11 Nov)" and stops there; the days since live in `state.md`.
- **Plan**:
  1. `state.md` keeps three short sections: the weak spots (lines 3-16 as they are), "Open" (only what is left: the ten items above, each cut to its open part with a link to its account), "Ideas and on hold" (9, 14, 20).
  2. Every finished account moves, text unchanged, to `docs/history.md` under a new "## 12-21 Nov" with one `###` per former item; its title becomes "History".
  3. Before renumbering, `grep -rn "state.md\|item [0-9]" docs CLAUDE.md benchmarks src` and fix the references to item numbers (`history.md` "Left" item 8 and 14 are cited from `state.md`).
  4. `CLAUDE.md`'s table: `history.md` row loses "1-11 Nov".
- **Check**: `docs/state.md` under 60 lines; `git diff --stat` shows the moved lines as moves (`git diff -M --stat`), and the link check of "Looked at, fine" still passes.

## TOOL-21 `docs/corrections_log.md` is a 619-line log read as a reference

- **Type**: docs
- **Impact**: low — its conclusions ("Kept", "State", "Next") sit at lines 81, 500 and 581, between 400 lines of experiment accounts in date order.
- **Effort**: M
- **Confidence**: confirmed
- **Where**: `docs/corrections_log.md`, `CLAUDE.md` (table row), `docs/state.md` (links by section title)
- **Problem**: section order today: how the work is run, baseline, steps, Kept (81), Tried and dropped (114-410, ten accounts), the owner's answers (411), the third match (444), the fourth match (482), State: hand-over, dated 13 Nov (500), re-identification compared (539), Next (581). The hand-over is a week older than the sections around it. The file also names about 25 scratch scripts that are in no repository (`holes.py`, `sides2.py`, `hits3.py`, `grammar.py`, `e2e.py`…).
- **Plan**:
  1. Reorder, text unchanged: a first screen with "State" (re-dated, its stale lines dropped), "Kept" and "Next"; then "How the work is run" and the harness; then "Tried and dropped" with the re-identification comparison inside it; the two held-out matches last.
  2. Keep every section title (other docs link to them by name: `state.md` cites "Kept", "Next", "The third match", "The fourth match", "Types (11 Nov)", "A renamed player in the truth", "The ball's sound where it is unseen").
  3. One sentence at the top of "Tried and dropped": the scripts named there were scratch files, not kept.
- **Check**: the first 60 lines answer "what is next and what was kept"; the link check still passes.

## TOOL-22 Small mismatches between the docs and the code

- **Type**: docs
- **Impact**: low — each is a wrong number or a claim one step out of date.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: as listed
- **Problem**: found while checking the docs' 157 relative links, 229 backticked `module.name` and 63 paths, every `--option` and 12 constants against the code (the rest matched):
  - `src/volleyball_stats/doctor.py:19`: "about 8 GB of RAM at its peak (docs/setup.md)"; `docs/setup.md:80` says 6.3 GB.
  - `CLAUDE.md` says the project runs on "at least Windows and macOS"; `README.md:12` badges "Linux | WSL2 | macOS" and the code has no native Windows path but `sync.py:203` (`msvcrt`, never reached: `os.nice` and `os.getloadavg` fail first). Say "Windows through WSL2" in `CLAUDE.md`, and drop the `os.name == "nt"` branch or keep it with a comment that it is unreachable today.
  - `README.md:141`: `npm install` where a contributor wants the locked versions: `npm ci`.
  - `sync_remote.py:2`, `backup_remote.py:2`: "python3 (3.8)" (TOOL-15).
  - `web.py:501`: "brands stay off the repository" (TOOL-19).
  - `docs/setup.md:19`: the ranker conflict (goes with TOOL-01).
  - `docs/README.md` and the README's table list six guides; `review.md`, `hosting.md` and `running.md` are reachable only from "Project notes", though `README.md:120` links `hosting.md` as the guide to one's own server. Move `hosting.md` to the guides' table.
- **Plan**:
  1. Fix each line as said.
  2. Keep the two scratch scripts' logic as one test, `tests/test_docs.py`: every relative markdown link of `README.md`, `CLAUDE.md` and `docs/*.md` resolves to a file and, with a `#fragment`, to a heading of it; every backticked `module.NAME` whose module is in `src/volleyball_stats/` appears in that module. It runs in a second and caught the mismatches above.
- **Check**: `uv run pytest -q tests/test_docs.py`.

## TOOL-23 The committed build is 84 % of the history's weight

- **Type**: maintainability
- **Impact**: low — nothing is slow today (a clone is 51 MB); at the present pace the history grows by about 50 MB a month, nearly all of it bundles.
- **Effort**: S for the measure kept, L for the alternative
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/site/`, `src/volleyball_stats/matches_site/`, `install.sh:64`
- **Problem**: over all 974 commits, blobs under `site/` are 488 MB raw and 82.6 MB packed, under `matches_site/` 245 MB and 33.5 MB: 116 of the 138 MB of packed blobs, from 553 commits. Each web commit adds four files of 0.5 to 1 MB that compress poorly against their previous version (minified, renamed symbols). The build exists in git so that users need no Node: that reason holds.
- **Plan**:
  1. Keep the build committed. Do not rewrite history for size.
  2. `install.sh:64`: `git clone --depth 1` (3.3 MB instead of 51). `git pull --ff-only` works on a shallow clone; `git_check.commits_since` already returns `None` "when git cannot tell (no history…)", so a late page's tip of commits is simply absent on such an install: check that the page shows nothing rather than an error.
  3. Only if the repository passes about 500 MB: CI builds and pushes the two folders to a `release` branch that `install.sh` clones and the app's update pulls, `main` ignoring them; the owner's machines keep building locally. Not worth its moving parts today.
- **Check**: `sh install.sh` into a scratch `VOLLEYBALL_STATS_DIR` leaves a `.git` of a few MB; "Mettre à jour" in that copy still updates.

## TOOL-24 Dependencies imported but not declared, and a launcher name kept for a migration that is over

- **Type**: maintainability
- **Impact**: low — the app's start depends on a package it never asks for; a script entry and its comment outlive their reason.
- **Effort**: S
- **Confidence**: confirmed for the imports; suspected for the legacy entry (left to check: `cat ~/.local/bin/volleyball-stats` on the PC ends with `run stats`, as it does on the Mac)
- **Where**: `pyproject.toml:7-18,22-24`, `src/volleyball_stats/icon.py:10`, `src/volleyball_stats/gesture.py:299`, `src/volleyball_stats/gesture_training.py:243`, `src/volleyball_stats/shortcut.py:133-140`, `src/volleyball_stats/app.py:1085-1089,1104`
- **Problem**: `icon.py` imports `PIL` at module level and `shortcut.py` imports `icon`, so every start needs Pillow, present only because Ultralytics depends on it (`pyproject.toml` lists it in the `bench` group alone). `safetensors` is imported directly and comes through `transformers`. Asked-for dependencies are all used (`gdown` 3 imports, `spandrel` 1, `rapidocr-onnxruntime` 1, `transformers` 4). `volleyball-stats = "volleyball_stats.app:main"` is commented "launchers installed until 2026-11 start; the app rewrites them to `stats`" (`shortcut.update_launcher`), and `app.parse` still maps `--stop` and `--no-browser`.
- **Plan**:
  1. `pyproject.toml` dependencies: add `pillow` and `safetensors` (already locked: `uv lock` changes no version; not new dependencies, so within the rule, but say it to the owner).
  2. Once both machines' launchers end with `run stats`: remove the `volleyball-stats` entry, `shortcut.update_launcher` and its call at `app.py:1104`, and the two legacy flags in `app.parse` with their tests.
- **Check**: `uv lock --check` passes; `uv run stats --help` works; `grep -rn "run volleyball-stats" src` is empty.

## TOOL-25 The pins: what an upgrade looks like

- **Type**: maintainability
- **Impact**: low — nothing is broken or vulnerable (but TOOL-09); two packages are a major behind and one is superseded.
- **Effort**: M
- **Confidence**: confirmed for the versions (`npm outdated`, `uv tree --outdated`); suspected for `rapidocr-onnxruntime` being superseded by the `rapidocr` package (check on PyPI)
- **Where**: `web/package.json`, `web/package-lock.json`, `pyproject.toml`, `uv.lock`
- **Problem**: web, all pins real and installed as written; behind: `typescript` 6.0.3 → 7.0.2, `i18next` 26.5.10 → 27.2.2, `react-i18next` 17.1.8 → 18.0.3 (majors); `vite` 8.3.5 → 8.3.8, `vitest` 5.0.5 → 5.1.1, `tailwindcss` 4.3.3 → 4.3.5, `three` 0.186.1 → 0.187.0, `lucide-react` 1.61 → 1.77, `@vitejs/plugin-react` 6.1.2 → 6.3.0 (minors). `@base-ui/react` is the only range (`^1.9.0`) among exact pins. `@types/node` is 24.x while `web/.nvmrc` is 22: types of a newer Node than the one that runs. Python, 149 packages locked: `ultralytics` 8.4.184 → 8.4.216, `torch` 2.14.1 → 2.15.0, `transformers` 5.22.1 → 5.23.0, `opencv-python` 5.0.0.93 → 5.1.0.95, `numpy` 2.5.4 → 2.5.5, `gdown` 6.4.2 → 6.5.2, `pytest` 9.1.1 → 9.2.0; `rapidocr-onnxruntime` 1.4.4 has no newer version. `pyproject.toml` leaves most unpinned on purpose, `uv.lock` deciding; `onnxruntime-gpu==1.31.0` is exact because it shares torch's CUDA 13 libraries.
- **Plan**:
  1. Web, one commit per step, each followed by `npx tsc --noEmit -p . && npm test && npm run build` and a look at the page: first the minors together; then `@base-ui/react` pinned exactly and `@types/node` set to `22.x`; then `i18next` with `react-i18next`; `typescript` 7 last and alone.
  2. Python, one package per commit with `uv lock --upgrade-package NAME`: `pytest`, `numpy`, `gdown` freely; `ultralytics` only with `benchmarks/players` and `benchmarks/identity` before and after (a tracker change moves tracks); `torch` together with `onnxruntime-gpu` (same CUDA) and `benchmarks/speed.py` on the PC; `opencv-python` with `benchmarks/court` and the film tests; `transformers` with `benchmarks/likeness` and `benchmarks/rallies`.
  3. `rapidocr-onnxruntime`: leave until its successor is checked with the jerseys and scoreboard numbers (`docs/state.md:41`: 301 of 303 pieces the same number).
- **Check**: after each step, the commands named with it; `uv tree --outdated --depth 1` and `npm outdated` shrink.

## TOOL-26 The suite's 26 warnings: two pipes never closed, and progress lines printed over the results

- **Type**: maintainability
- **Impact**: low — no leak in practice (CPython closes them when the function returns), but the warnings would hide a real one, and the summary is followed by stray `::progress` lines.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/jobs.py:171-186`, `src/volleyball_stats/matches.py:629-644`, `src/volleyball_stats/video_copies.py:262-267`, `tests/test_jobs.py`, `tests/test_matches.py`
- **Problem**: `uv run pytest -q -W default` ends with 26 `ResourceWarning`: "unclosed file <_io.TextIOWrapper name=14>" from `jobs.ffmpeg` and `matches.counted` (a `subprocess.Popen` with two pipes, waited but never closed), "unclosed file <_io.BufferedReader>" under `video_copies.py:262,267`, two "subprocess … is still running" in `test_jobs.py`, two log files left open by `applog` tests. After the summary line the terminal shows `::progress 0.8955 part= left=60`, written by a child process that outlives its test.
- **Plan**:
  1. `with subprocess.Popen(…) as process:` in `jobs.ffmpeg` and `matches.counted` (closes both pipes, waits); the same for the reader in `video_copies`.
  2. The two tests that leave a child running wait for it (`process.wait(timeout=5)`) before returning.
  3. `pyproject.toml`: `[tool.pytest.ini_options] filterwarnings = ["error::ResourceWarning"]` once the count is zero.
- **Check**: `uv run pytest -q -W default` ends with "1104 passed, 1 skipped" and no warning block or stray line.

## TOOL-27 Vite warns that its config will stop loading in a later major

- **Type**: maintainability
- **Impact**: low — every `npm test` and build prints it; the day the default changes, the build fails.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `web/vite.config.ts:5`
- **Problem**: "Your Vite config uses features that are unsupported by `configLoader: 'native'` … import "./online" without a file extension (vite.config.ts:5:24). Add the file extension".
- **Plan**:
  1. `import { online } from './online.ts';` (`tsconfig.json` already has `allowImportingTsExtensions`).
- **Check**: `npm test` prints no "(!)" block; `npx tsc --noEmit -p .` stays clean.

## TOOL-28 The new-reports notification keeps the language the page opened in

- **Type**: i18n
- **Impact**: low — after switching French ↔ English, the system notification of new viewers' reports is still written in the first language until a reload.
- **Effort**: S
- **Confidence**: read (found by the react-hooks rule, the effect read; not reproduced in a browser)
- **Where**: `web/src/components/NewReports.tsx:40-59`
- **Problem**: the polling effect is created once (`}, []);`) and its `read` closes over `t` and `title` as they were then: `new Notification(t('newReports.count', …), { body: more.map(title).join(' · ') })`.
- **Plan**:
  1. Keep the single interval; read the texts through a ref updated at each render (`const texts = useRef({ t, title }); texts.current = { t, title };`) and use `texts.current` inside `read`.
- **Check**: with notifications allowed, switch the language, wait for a new report (or lower `EVERY_MS` locally): the notification is in the new language.

## Looked at, fine

- **Python tests' isolation**: no `conftest.py` needed; no test binds port 8765, reads the real `outputs/`, or writes under the real `HOME` but through TOOL-05's two tests (run with an empty `HOME`: only Ultralytics' settings and gdown's cookie file appeared).
- **Flakiness**: two runs in file order identical (1101 passed); the one order-dependent test is TOOL-06. Four tests sleep (0.01 to 0.3 s), none on a race I could trigger.
- **Web tests**: 61 files, 430 tests in 1 s; fr and en hold the same 1,532 keys (`locales.test.ts` checks it); the 44 placeholder differences are French's `ofName` / `ofTeam` elision, on purpose. Helpers without a sibling test are thin or rendering code (`scene3d/scene.ts` 696 lines, `scene3d/hall.ts` 344, `lib/match.ts` 333 of types, `Stats/helpers/cardPicture.ts` 183 of canvas drawing).
- **ESLint with the react-hooks plugin** (run from a scratch folder, nothing installed in `web/`): 0 `rules-of-hooks` errors, 22 `exhaustive-deps` warnings, 21 of them deliberate "run only when X changes" effects with their comment. One real finding (TOOL-28). Not worth adopting: `tsc` strict with `noUnusedLocals` already covers the rest.
- **Pyright**: 362 errors, 0 real bug in the 40 read: OpenCV and numpy stubs returning `None`-able values (`reportOptionalSubscript`/`MemberAccess` 107), argument types (145), three "possibly unbound" in loops that always run (`court.py:338`, `film.py:749`, `play_training.py:232`), one star-unpacked call miscounted (`gesture_training.py:294`). Not worth adopting.
- **Ruff beyond `F`**: `S` (subprocess without shell, asserts), `PTH`, `ARG005`, `B905`, `PLW1510`, `RUF012` total about 3,000 findings of style; `BLE001` once, already marked on purpose (`doctor.py:106`); `S105` is a file name (`matches.PASSWORD`), `S104` the opt-in LAN bind.
- **Docs against the code**: the 157 relative links and their fragments all resolve; every `--option` named in the docs exists in an `argparse` call (but options of other tools: certbot, docker); 12 constants quoted with a value match (`shortcut.VERSION` 3, `backup.MARGIN_GB` 1.0, `review.MIN_IMPACT` 20, `web.BRIEF_S` 30, `presence`'s 30 s / 2 min / 30 min…); `CLAUDE.md`'s named files and helpers exist (`Tip.test.ts`, `ask.tsx`, `lib/errors.ts` `explain`, `ErrorNote`, `Hint`, `useRunning`, `web/.nvmrc` = 22, `LOCAL` in `web/online.ts`, port 8765, `stats stop` / `server` / `--with-window`). The scratch scripts `corrections_log.md` names are scratch on purpose.
- **Secrets in the history** (all 974 commits, patches scanned without the builds and locks): no private key, token, password or key file; the only passwords are test literals; the only emails are the author's public one and two paper authors'; ssh targets are placeholders (`root@host`, `root@1.2.3.4`). The exception is TOOL-02.
- **`outputs/`, `data/`, `models/` never committed**: no path under them in `git log --all --name-only`.
- **README screenshots**: 10 of the 22 image versions in the history looked at (the first and the latest of those that list players: statistics, trophies, court map, coach's corner, match page, placement, TV mode, the app): "Player N" everywhere, no face, the app's matches staged, as the README says. The 12 others were not opened.
- **Committed build in sync and reproducible**: built into a scratch folder at `a594cda`, byte-identical to the committed files.
- **`lap`**: Ultralytics' trackers want it, the lock does not have it; `players.make_tracker` stands in with Ultralytics' own solver on purpose (a `ponytail:` comment says so), and TOOL-06's `YOLO_AUTOINSTALL=false` keeps it from being fetched at run time.
- **Model files' safety**: `torch.load(..., weights_only=True)` for the two downloaded checkpoints, safetensors for the upscaler and the learned models.
- **`uv.lock`**: universal (Linux, macOS, Windows markers), 149 packages, one `onnxruntime` per machine as `pyproject.toml` explains; torch's Linux wheel is the CUDA 13 one `docs/setup.md` names.
- **Vendored code**: `vendor/osnet_ain.py` and `vendor/wasb_hrnet.py` each with its MIT licence file beside it.
- **Runtime reaching outside the package** (`benchmarks/attribution/ranker.py` from `learn.py:223`, `web/src/locales/fr.json` from `film.py:37`): the project is only ever run from its clone, so a wheel is not a target; fine as long as that holds.
- **Shortcuts** (`shortcut.py`): quoting of the PowerShell text, the Mac bundle's `Info.plist`, the Linux entry and the "made once per version and colours" record read sound; covered at 69 % (TOOL-13 names the rest).
- **`benchmarks/` layout**: one folder per step with its `README.md`, plus `scale.py` and `speed.py`; 109 tracked files, 3.2 MB of history.

## Not checked

- Anything on the owner's server (TOOL-02's second half), on the PC under WSL2 (TOOL-14's actual pictures, the Windows shortcut), or on GitHub (branch protection, whether Actions is enabled).
- Whether the Linux build equals the Mac's byte for byte (TOOL-04, step 4).
- The licences of VideoMAE and MSMT17 against their pages (TOOL-17), and `rapidocr-onnxruntime`'s successor (TOOL-25): no network lookups were made for them.
