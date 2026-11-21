# Improvement plans (audit of 21 Nov)

Every improvement found in one pass over the whole app, each written as a plan to execute later
([TEMPLATE.md](TEMPLATE.md): type, impact, effort, confidence, where, problem, plan, check). 173 entries.

| File | Area | Entries |
|---|---|---|
| [00-live-findings.md](00-live-findings.md) | Seen on the running app and the real state (headless Chrome, `outputs/`) | LIVE-01 to 10 |
| [01-server-app.md](01-server-app.md) | The local server and the app's backend | SRV-01 to 32 |
| [02-hosting-sync-export.md](02-hosting-sync-export.md) | Hosting, sync, backup, films, copies | HOST-01 to 28 |
| [03-pipeline.md](03-pipeline.md) | The analysis pipeline and its benchmarks | PIPE-01 to 23 |
| [04-match-page.md](04-match-page.md) | The public match page | PAGE-01 to 25 |
| [05-review-app-ui.md](05-review-app-ui.md) | The review's and the app's screens | REV-01 to 27 |
| [06-tooling-tests-docs.md](06-tooling-tests-docs.md) | Tests, CI, docs, install, licences, repo hygiene | TOOL-01 to 28 |
| [07-known-backlog.md](07-known-backlog.md) | What the code and docs already list as left | – |

Confidence: `confirmed` was run or reproduced, `read` traced in the code, `suspected` says what is left to check. A
"Verified" line under an entry is a second, independent reproduction. Each file ends with "Looked at, fine".

## Order

### 1. Now (each under an hour)

| ID | What |
|---|---|
| SRV-01 | Any file of the computer readable through `/matches//…`: keep "Réseau local" off until fixed |
| HOST-01 | One crafted viewer report stops every review (the public `/feedback` is live) |
| LIVE-01 | The review's stylesheet loses to the page's since a594cda: names clipped, grids, paddings |
| PAGE-02 | The coach's fault playlists name the player at fault (the owner's rule) |
| REV-01 | A refused save wipes the Match tab's unsaved corrections |
| TOOL-03 | The 6.9 GB backup zip at the root is one `git add -A` from a public commit: ignore it |

### 2. Lost work and the two machines

REV-02, REV-03 (corrections lost by a run's reload, by undo after a restart), SRV-04 ("Tout récupérer" under an open
review), LIVE-02 = HOST-11 (a pulled match reads as changed), LIVE-03 (opening a review marks it changed), HOST-02 (a
clock behind sends old files as the new version), HOST-05 (`--delete` before the new files land), PIPE-01 (a failed
rerun orphans the checked rallies), PIPE-02 = TOOL-01 with SRV-03 (the update's `--autostash` leaves conflict markers:
move the retrained weights to `outputs/learned/`, refuse the update on a conflict), SRV-15 (answers not flushed),
LIVE-04 (the other machine's key path), HOST-10, HOST-16.

### 3. Wrong results

PAGE-01 (a let serve gets no rating), PIPE-03 (the near-touch identity never reaches the page: 29 touches), PIPE-04
(a failed ffmpeg stamps a short `play.npz` as done), SRV-02 (several videos picked never scan), HOST-03 (reports
filed on the wrong rally), HOST-06, HOST-07, HOST-08, PIPE-08, PIPE-09, SRV-05, SRV-07, SRV-08.

### 4. Guards, so the above stays fixed

LIVE-06 (run the app on a copy: `VOLLEYBALL_HOME`), LIVE-05 (refuse a second server), TOOL-04 (CI), SRV-27 = TOOL-12
(no test reaches an HTTP route), TOOL-07 (three tests never run), TOOL-05, TOOL-06, REV-24, TOOL-13.

### 5. The owner's review time

REV-04 (every edit saved at once, state.md item 14), REV-06 to REV-09 (shortcuts), REV-15 (the video remade per
question), REV-13, REV-14.

### 6. The page for its viewers

PAGE-03 and PAGE-07 with LIVE-09 (800 tab stops, 8,000 listeners, an 850 ms task on a phone), PAGE-04, PAGE-05
(no keyboard shortcut in the player), PAGE-06 (links to a moment), LIVE-07 (axe: labels, contrast, landmarks),
PAGE-11, PAGE-12, PAGE-16, PAGE-17, REV-20 and PAGE-18 (native tooltips).

### 7. Local network

SRV-06 (routes for the machine only), SRV-18, SRV-19, LIVE-08 (gzip).

### 8. Long runs

PIPE-05 (tracking kept in memory: any stop loses hours), PIPE-06 (nothing keeps the machine awake), PIPE-13,
PIPE-14, SRV-13, SRV-16, the pull-forward rows of 07.

### 9. The rest

Cross-platform (HOST-12 = TOOL-14 fonts, HOST-13, TOOL-11), licences and privacy of the repository (TOOL-17,
TOOL-18, TOOL-19, TOOL-08, TOOL-02 rated low once checked), docs (TOOL-20 to 22, PIPE-23, SRV-31), maintainability
(SRV-28 to 30, HOST-28, REV-25, TOOL-09, TOOL-23 to 27).

## Not done

Four further audits were started and cut short before writing anything; their scope, for whoever resumes:

- **Statistics' correctness**: every number of the page recomputed from `data.js` on the four matches against
  `docs/review.md` "The statistics' reading" (`web.py`, `Stats/helpers`, `Story`, `Coach`, `Season`), conservation
  checks (points = rallies won, aces ≤ serves), and standard stats the data already holds (sideout %, attack efficiency).
- **The review as a process**: from `identity_answers.json`'s logs, which question kinds are answered as proposed, the
  time per answer (no timestamp may exist: then add one), what another order or a bulk confirm would save.
- **The review end to end in a browser with writes**: REV-02, REV-03, REV-10 and the `read` SRV entries reproduced
  through the server; needs LIVE-06 first.
- **3D, TV mode and the replay in a browser**: sync against the video, frame rate on a phone, disposal on view
  switches, WebGL lost, `scene3d/hall.ts` (unread past line 80).

Also not checked: anything under Windows / WSL2, the owner's nginx (only its public headers: HSTS, nosniff, noindex
present; no Content-Security-Policy nor frame-ancestors), a pipeline or GPU run.

## Looked at, fine (by the audit's lead)

- The local server refuses another site's requests (Origin, `Sec-Fetch-Site`), other host names (DNS rebinding), and
  `..` in paths; scripts are not includable cross-site. The one hole is SRV-01.
- The hosted pages' scripts are versioned (`data.js?v=…`): no stale data under a new page; the video without its key
  redirects; the origin answers nobody but its proxy.
- English: no French left on the page, the review or the list. No horizontal scroll at 390 px, light and dark; no
  console error through play, 3D, TV, commentary, highlights; the sticky bar's links land on their heading; no layout
  shift; nothing runs while the page idles.
