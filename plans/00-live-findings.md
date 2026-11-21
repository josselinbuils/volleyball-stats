# Live findings — seen on the running app (21 Nov)

Found by driving the app in a headless Chrome (`playwright-core` + the installed Chrome, scripts in the session's
scratch folder) and by reading the real `outputs/` state. Every entry here was reproduced, not only read.

## LIVE-01 The review's and the list's stylesheet loses to the page's one since a594cda

- **Type**: bug (regression of the last commit on `main`, a594cda, 21 Nov 12:46)
- **Impact**: high — every review and the app's list: player names hidden under their picture in the Match tab, the
  list's cards two a row instead of three, table paddings, a keyboard button shown on phones that should be hidden.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `web/src/lib/sheet.ts:6-13` (`addSheet`), the theme's `<style>` written by `applyTheme`
- **Problem**: `addSheet` now does `document.head.prepend(style)`: the app's full sheet (`#app-sheet`, 1,610 rules)
  comes *before* the page's own `assets/style-*.css` (1,187 rules). Both declare the same Tailwind layers, so at equal
  specificity the later sheet wins: a utility that exists in both (`px-1.5`, `p-2`, `px-2`, `sm:grid-cols-2`) now beats
  one that exists only in the app's sheet (`pl-8`, `pl-4`, `pr-4`, `xl:grid-cols-3`, `mx-auto`, `max-sm:hidden`).
  Measured by moving `#app-sheet` right after the `<link>` and diffing every element's computed style:
  - `/review#match` (1440 px): 21 elements change; the 20 `PlayerSelect` inputs have `padding-left: 6px` instead of
    `32px` (`cn(FIELD, picture && 'pl-8')`, `Review/PlayerSelect.tsx:152`): the name's first letters sit under the
    24 px picture (a seven-letter name loses its first two).
  - `/` (the list): 42 elements; the matches' grids `repeat(2, …)` instead of `repeat(3, …)` (`xl:grid-cols-3`), the
    Progress tables' `pl-4` / `pr-4` back to 8 px.
  - `/review#match` on a phone: a button meant hidden shows (`display: flex` instead of `none`), a margin differs.
  - The club's colours stay right in both orders (`--primary: #e30613`): the theme's `<style>` is after both.
- **Plan**:
  1. In `addSheet`, insert the sheet right after the page's own stylesheet instead of first in the head:
     `const link = document.querySelector('link[rel=stylesheet]'); link ? link.after(style) : document.head.prepend(style);`
     (after the page's sheet so the app's full sheet settles every conflict as one Tailwind build would; before the
     club's `<style>`, which `applyTheme` appends later or which already sits after the link).
  2. Checked: `applyTheme` (`web/src/helpers/theme.ts:38`) appends its `<style>` at the end of the head from
     `main.tsx` / `matches.tsx`, before the review or the app mounts, and the head holds one stylesheet link: step 1
     gives page sheet, app sheet, club colours.
  3. Add a test beside `sheet.ts` (jsdom is not installed: test the order with a tiny fake `document.head` or move the
     ordering into a pure helper `placeSheet(head)`), asserting the order link → `#app-sheet` → theme.
  4. `npm run build`, commit the build.
- **Check**: open a review's Match tab: the player fields show whole names beside the picture; the list shows three
  cards a row at 1440 px; the header stays the club's red. Or rerun the scratch `cascade.mjs` diff: 0 elements changed.

## LIVE-02 A pulled match looks "changed here" at once: `pull` remembers its state before rewriting publish.json

- **Type**: bug (sync)
- **Impact**: high — on the machine that pulls (the Mac today): every pulled match counts as changed, so the next
  "Tout récupérer" asks to replace it, a review opening it once the PC pushed again asks "which copy to keep", and with
  automatic copies on the match is sent straight back (a version bump per pull, the two machines ping-ponging).
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/sync.py:484-507` (`pull`), `sync.py:510-523` (`relative_copies`)
- **Problem**: `remember(match, version, backup.signature([match]))` runs inside `with alone(match)`, then
  `relative_copies(match)` rewrites `publish.json` (the other machine's `/home/.../data/matches/...` paths made
  relative), moving the folder's latest mtime past the remembered signature. On the Mac, right after today's
  "Tout récupérer" (12:34-12:44): `.sync.json` and `publish.json` share the same second in the three matches pulled, and
  `sync.changed(match)` is `True` for all four matches (`uv run python -c "…sync.changed(m)…"`), with nothing edited.
- **Plan**:
  1. In `pull`, call `relative_copies(match)` before `remember(...)`, inside the `alone` block.
  2. Test in `tests/test_sync.py`: a pull of a match whose publish.json holds another machine's absolute video paths
     leaves `sync.changed(match)` false (the existing pull tests show how the server is faked).
- **Check**: pull a match pushed by the other machine; `sync.changed` is false; "Tout récupérer" a second time says
  "Déjà à jour." and asks nothing.

## LIVE-03 Opening a review marks the match "changed here": derived files count in the sync signature

- **Type**: bug (sync)
- **Impact**: medium — a review merely opened (no answer given) rewrites `photo_scores.json`, `photo_vectors.npz`,
  `photo_candidates.json`, `photo_shown.json`, `likeness_seen.json`, `jersey_pictures.json`, `source.json`; none is in
  `backup.SKIP`, so the match's signature moves: false conflicts between the two machines, needless copies sent.
- **Effort**: M
- **Confidence**: confirmed (the second match, opened at 12:35-12:41 on 21 Nov after its pull: those seven files and
  nothing else are newer than its state; same on the first match after a server start)
- **Where**: `src/volleyball_stats/backup.py:38` (`SKIP`), `backup.py:80-91` (`signature`), the writers in
  `review.py` / `web.py` / `likeness.py` / `jerseys.py`
- **Problem**: `signature` is (file count, latest mtime) over everything not skipped. The files above are made again
  at each review start; some are byte-identical (`source.json` was), some differ per machine (the photo caches).
- **Plan**:
  1. Sort the seven files: a cache the other machine can rebuild (photo scores, vectors, candidates, likeness seen,
     jersey pictures) goes in `backup.SKIP` *only if* rebuilding is cheap and deterministic enough; check each one's
     cost first (`likeness_seen.json` saves a 5 s model load, `photo_vectors.npz` a pass over the pictures): for those
     worth sharing, keep them synced but write them only when their content changes.
  2. Add a helper in `files.py`, `write_if_changed(path, text_or_bytes)` (read, compare, skip the write), and use it
     for `source.json`, `photo_shown.json`, `jersey_pictures.json`, `photo_candidates.json`, `photo_scores.json`.
     `np.savez` output is not byte-stable (zip timestamps): for `photo_vectors.npz` compare the arrays before saving.
  3. Test: start a review twice on a fixture match (the tests of `review.py` build one); `backup.signature` is the
     same before and after the second start.
- **Check**: open and close a review without answering; `sync.changed(match)` stays false.

## LIVE-04 A pulled match's publish.json carries the other machine's ssh key path

- **Type**: bug (two machines)
- **Impact**: medium — on the Mac the viewers' reports fetch fails every 10 minutes with the PC's key
  (`reports fetch failed: … scp -i /home/<user>/.ssh/… exit 255`, 6 times in `outputs/app.log`), and anything reading
  the hosting from a match's own publish.json (`backup.rename_copies`, `backup.connection`) would fail the same way.
- **Effort**: S
- **Confidence**: confirmed for the reports fetch; read for the other readers
- **Where**: `src/volleyball_stats/feedback.py:100-113` (hostings gathered from every publish.json),
  `sync.py:510` (`relative_copies` fixes the videos' paths, not `key`), `backup.py:284`, `sync.py:53-63` (`server`)
- **Problem**: `outputs/server.json` holds `key: ~/.ssh/…` (portable), but each pulled `publish.json` holds the
  absolute path of the machine that pushed. `feedback` collects `(upload, key)` pairs from every publish.json: the
  server is fetched once with the right key and once with a path that does not exist here.
- **Plan**:
  1. Smallest: in `feedback`'s hostings loop and in `backup.rename_copies`, take the hosting through `sync.server(outputs)`
     (server.json wins) instead of the match's raw publish.json; fall back to the match's only without a server.json.
  2. Stop the cause: where publish.json is written (`matches.ensure_publish`, the Site tab's save), store `key` with
     `~` when it is under the home folder (`"~/" + str(Path(key).relative_to(Path.home()))`), and have
     `relative_copies` do the same repair for a `key` that does not exist here but whose file name exists in `~/.ssh/`.
  3. Test: `feedback` with a publish.json whose key path is missing and a server.json whose key exists fetches once.
- **Check**: `grep -c "reports fetch failed" outputs/app.log` stops growing on the Mac.

## LIVE-05 Nothing stops a second server on the same outputs

- **Type**: bug / robustness
- **Impact**: medium — `uv run stats server NAME --port 8766` while the app runs on 8765 starts a second review on the
  same `outputs/`: both rebuild the same match's review page, pictures and caches; two applies could interleave.
  (Seen during this audit: a second server meant for a scratch copy ran on the real folder, because `app.main` does
  `os.chdir(git_check.ROOT)`, `app.py:1102`.)
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/app.py:1095-1123` (`main`), `review.py` (the server's start)
- **Plan**:
  1. At start, before binding: read `outputs/app.pid.json` (`{pid, port, boot}`); if that process still runs
     (`jobs.process_key` already tells a live process from a reused pid) and its port differs, print "already running
     on port N" and open that page instead (what a second start on the same port does today). Write the file once
     listening, remove it on stop.
  2. Test in `tests/test_app.py`: a live record for another port refuses; a dead record is replaced.
- **Check**: with the app open, `uv run stats server --port 8766` opens nothing new and says where the app runs.

## LIVE-06 No way to run the app on a copy of the outputs

- **Type**: tests / maintainability
- **Impact**: medium — the app cannot be driven end to end (a browser test, an audit, a risky fix tried) without
  touching the real matches: `os.chdir(git_check.ROOT)` pins `outputs/` and `data/` to the repository.
- **Effort**: S
- **Confidence**: confirmed
- **Where**: `src/volleyball_stats/app.py:1102`
- **Plan**:
  1. `os.chdir(os.environ.get("VOLLEYBALL_HOME") or git_check.ROOT)`: a developer's variable, not a user's command
     (the rule "every action in the app" stands: nobody needs it to use the app). Document it in `docs/running.md`
     beside `VOLLEYBALL_MACHINE`.
  2. Check what else reads the repository root for data rather than code: `learn.ROOT`, `play_training.ROOT`,
     `gesture_training.ROOT` (benchmarks' code: fine), `matches.py:600` (`cwd=` for `uv run --group voice`: code, fine).
  3. Then a browser smoke test becomes possible (see TOOL plan: CI): start the app on a fixture folder, load `/`,
     `/review`, `/page`, fail on any console error.
- **Check**: `VOLLEYBALL_HOME=/tmp/copy uv run stats server` lists only the copy's matches.

## LIVE-07 Accessibility, measured with axe on the rendered pages

- **Type**: accessibility
- **Impact**: low to medium — keyboard and screen-reader users; the list's dimmed cards for anyone in bright light.
- **Effort**: S each
- **Confidence**: confirmed (axe-core 4 on `/`, `/review`, `/page`, 1440 px and iPhone 13, light and dark)
- **Where / Problem**:
  1. `label-content-name-mismatch` (serious), 19 nodes on `/page`, 2-3 on the review: an `aria-label` that does not
     contain the control's visible text (WCAG 2.5.3: voice control says the visible words and nothing answers). The
     match title's menu button is labelled "Changer de match" while showing "Match A vs B"
     (`Review/ReviewHeader.tsx`); the Story's set rows on the page; the language menu. Fix: start the label with the
     visible text ("Match A vs B, changer de match") or drop the `aria-label` and give the extra words in a
     `sr-only` span.
  2. `color-contrast` (serious), 4 nodes on the list: the `<time>` and text of a card without its video, dimmed with
     `opacity-60` (`components/Matches.tsx`). Fix: dim with `text-muted-foreground` on the texts instead of the
     card's opacity, or keep the date at full opacity.
  3. `region` (moderate), 2 nodes on every page: the club band's controls sit outside any landmark. Fix: the band is
     a `<header>` (or `role="banner"`), the page's content in `<main>` everywhere (`/page` and the review have it;
     check the band's component).
  4. Controls under 24 px (WCAG 2.5.8): the `Hint` button is 14×14 px on every page (`components/Hint.tsx`; state.md
     says unseen 44 px tap areas were added on the page: check `Hint` has one, the measure here is its box), the
     Match tab's two checkboxes 13×13 px.
- **Plan**: fix in the order above; add `@axe-core/playwright` to the browser smoke test of LIVE-06 and fail on
  `serious` or worse.
- **Check**: axe reports no serious violation on the four pages.

## LIVE-08 The local server sends its scripts uncompressed

- **Type**: performance
- **Impact**: low on the machine itself; medium over "Réseau local" (a phone on Wi-Fi loads 2.0 MB for a review:
  `review-app.js` 970 KB, `index-*.js` 741 KB, `data.js` 239 KB, `style` 85 KB; the list 1.5 MB: `app.js` 936 KB,
  `matches-*.js` 476 KB).
- **Effort**: S
- **Confidence**: confirmed (no `content-encoding` on any response of 127.0.0.1)
- **Where**: the static file answer in `src/volleyball_stats/review.py` (the handler serving `site/` and the match's
  `review/` folder)
- **Plan**:
  1. For `.js`, `.css`, `.html`, `.json`, `.svg` answers when the request has `Accept-Encoding: gzip`: send
     `gzip.compress(body, 6)` with `Content-Encoding: gzip` and `Vary: Accept-Encoding`, cached in memory by
     (path, mtime, size) since the files are static between builds. Never for ranges or videos.
  2. Test: a GET with the header gets a gzip body that decompresses to the file; without it, the raw file.
- **Check**: the review's first load over the local network transfers about 0.5 MB instead of 2.0 MB.

## LIVE-09 The match page's first render: one 850 ms task on a phone, 8,000 listeners

- **Type**: performance
- **Impact**: medium — a mid-range phone freezes close to a second while the page mounts; everything after is smooth.
- **Effort**: M
- **Confidence**: confirmed (Chrome, CPU throttled 4x as an iPhone 13 viewport, the first match's page served locally)
- **Where**: the sections mounted at once in `web/src/App.tsx`; the rally cards, the curve and the timeline
  (`components/RallyCharts/`, `components/Story/Curve.tsx`)
- **Problem**: measured after load:

  | view | FCP | long tasks | longest | script | DOM nodes | event listeners | heap |
  |---|---|---|---|---|---|---|---|
  | phone, CPU 4x | 1.05 s | 5, 1.33 s in all | 850 ms | 1.15 s | 4,094 | 5,883 | 48 MB |
  | desktop 1440 px | 0.36 s | 2, 0.37 s | 302 ms | 0.37 s | 9,662 | 8,242 | 64 MB |
  | review, Match tab | 0.73 s | 1, 77 ms | 77 ms | 0.16 s | 3,333 | 660 | 12 MB |
  | the app's list | 0.15 s | none | – | 0.10 s | 1,057 | 430 | 8 MB |

  No layout shift (CLS 0), nothing runs while idle (15 ms of script in 5 s). The cost is the mount itself: about 800
  buttons (PAGE-03), each with its handlers and, in the rally cards, its tooltip (PAGE-07).
- **Plan**:
  1. Do PAGE-07 and PAGE-03 first (one tooltip and one roving tab stop per group instead of one per rally): they
     remove most of the listeners.
  2. Then mount the sections below the fold when they come near the screen: a small `Deferred` wrapper
     (`IntersectionObserver`, `rootMargin: '600px'`, a placeholder of the section's usual height so the sticky
     bar's links land right; the bar's click mounts its target first). Start with "Échanges" (the rally cards), the
     heaviest and the last on the page.
  3. Measure again with the scratch `perf.mjs` (CDP `Emulation.setCPUThrottlingRate` 4, `longtask` observer).
- **Check**: the longest task on the throttled phone under 300 ms; the sticky bar's links still land on their heading.

## LIVE-10 Without a server set, the list asks for the backups and logs an error

- **Type**: bug (cosmetic)
- **Impact**: low — a console error at every load of the list for anyone who hosts nothing (every new user).
- **Effort**: S
- **Confidence**: confirmed (`GET /app/server/copies` -> 400 on a copy of the outputs without `server.json`)
- **Where**: the Site tab's first fetch in `web/src/components/SiteTab.tsx`; the route in `src/volleyball_stats/app.py`
- **Plan**: answer `200 {"copies": []}` when no server is set (the tab already shows the "set a server" state), or
  skip the request while `state.server` is null. Keep 400 for a malformed request only.
- **Check**: the list loads with an empty console on a fresh `outputs/`.

## What this audit touched (told for the record)

A second server started for a scratch copy (port 8766, 12:52-12:57 on 21 Nov) ran on the real `outputs/` instead
(`os.chdir`, LIVE-06). It only received GET requests and the pages' presence pings: no answer, name or setting changed.
Like any review start, it rebuilt the first match's review page and picture caches
(`outputs/matches/2026-10-29-aspom-1-vs-aspom-2/review/`, `photo_*.json|npz`, `jersey_pictures.json`,
`likeness_seen.json`, `source.json`), wrote `outputs/feedback/new.json` and lines in `outputs/app.log`, and tried one
reports fetch from the hosting server, which failed (LIVE-04). That match already counted as changed here before
(LIVE-02). It was stopped with `uv run stats stop --port 8766`; the app on 8765 was not touched.
