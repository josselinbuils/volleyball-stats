# Review and app screens — improvements

One entry per finding, most valuable first. IDs are `REV-NN`.

Baseline (21 Nov, `main` at a594cda): `npx tsc --noEmit -p .` clean, `npm test` 61 files / 430 tests pass.
No browser was available (the Chrome DevTools server did not connect) and no POST was sent to the running
server: every entry is `read` unless it says otherwise. Paths are relative to the repository; `R/` stands
for `web/src/components/Review/`.

## REV-01 A failed save resets the Match tab's editor

- **Type**: data-loss
- **Impact**: high — one refused or dropped "Valider" throws away every correction not saved yet, in all rallies, and moves the video on.
- **Effort**: S (under an hour)
- **Confidence**: read (traced in the code, callers included)
- **Verified** (21 Nov, headless Chrome on a scratch copy of the first match): confirmed. `/answer` answered 503: the touch changed from `pass` to `serve` is back to `pass`, the video jumps to the next rally (7.1 s -> 48.0 s), only "Échec : réessayez." shows.
- **Where**: `R/Review.tsx:241-360` (`handled`, `saveUnchecked`, `saveEdits`), `R/MatchTab.tsx:252-267`, `R/ReportEditor.tsx:689-702,757-766`
- **Problem**: the save functions catch their failure and resolve:
  ```ts
  const saveEdits = async (changes, rally) => {
    try { onSaved(await post('answer', {...})); ... } catch { setError(true); }
  };
  ```
  and `MatchTab` goes on as if saved: `onSave(changes, rally).then(() => { setRound((r) => r + 1); ... go(spans[k + 1].start ...) })`.
  `setRound` remounts `<ReportEditor key={round}>`, which starts again from the last saved `corrections`. A refusal is
  common, not exotic: 503 `busy` during any run (apply, films, hosting), 409 `updating` during the app's update, a
  Wi-Fi drop on a "Réseau local" device. Same for "Supprimer" (`onSaveUnchecked`) and "Traité" (`onHandled`).
- **Plan**:
  1. `saveEdits`, `saveUnchecked`, `handled`, `uncheck` in `Review.tsx` return `true`/`false` (as `saveComment` already does).
  2. `MatchTab.tsx:252-267`: `setRound` and `go(...)` only when the save returned `true`; types `Promise<boolean>` in `MatchTab` and `ReportEditor` props.
  3. Test: the three `.then` bodies move to a small helper in `R/helpers/` (`afterSave(saved, ...)`) with a vitest case "a failed save keeps the round".
- **Check**: `npm test`; by hand: start "Refaire les vidéos", correct a touch in the Match tab, press V: the error shows and the correction is still in the list.

## REV-02 Corrections made while a run goes are thrown away by the reload at its end

- **Type**: data-loss
- **Impact**: high — an apply takes minutes, the owner keeps correcting meanwhile; everything typed then is lost without a word.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/Review.tsx:212-218` (`mayLeave`), `:446-466` (run going as the page opens), `:469-495` (`reload`), `:785-805` (`MatchTab` gets no `busy`, `Names` does at `:778`)
- **Problem**: `run` calls `mayLeave()`, which sets `leaving.current = true`, then `reload()` awaits the whole run and ends
  with `location.reload()`. During the run the Match tab stays editable, every save is refused (503) and, the guard being
  disarmed (`if (!leaving.current) { event.preventDefault(); }`), the reload asks nothing. A page opened while a run goes
  (`running`) reloads the same way; there only the browser's own prompt may show.
- **Plan**:
  1. `Review.tsx`: pass `busy={busy !== null}` to `MatchTab`; `MatchTab` sets `inert` on the editor column (list, caption editor, timeline edits) while busy, the video and the progress above staying usable.
  2. `reload()`: before `location.reload()`, `if (unsavedRef.current) { leaving.current = false; }` so that anything typed before the lock still asks.
  3. Gone for good with REV-04 (nothing stays unsaved longer than a second).
- **Check**: start an apply, try to change a touch: the list does not answer; the page reloads at the end with nothing lost.

## REV-03 "Annuler" after a server restart empties every waiting correction

- **Type**: data-loss
- **Impact**: high — one click on the undo arrow loses all the Match tab's corrections since the last apply, while their rallies stay ticked as checked.
- **Effort**: S (under an hour)
- **Confidence**: confirmed (on the pure functions; not through the server)
- **Where**: `src/volleyball_stats/review.py:1795-1806` (`superseded`, `corrections`), `:2092-2101` (`undo`), `:2596` (`history` in memory), `:3390-3392`; `R/ReviewHeader.tsx:315`
- **Problem**: each save empties the earlier waiting report answers of their `changes`, the last one carrying all. Undo
  normally pops `history`, but that list lives in memory: empty after every restart (each fix pushed restarts the review,
  each match switch too) and capped at `UNDOS = 100`. Then `undo` returns `log[:-1]`: the one entry holding everything.
  ```
  before undo: {'fixes': {'a': 1, 'b': 2, 'c': 3}}
  after undo with no history: {} undone edit:3 checked [1, 2]
  ```
  (three saves through `superseded`, then `undo(log, [])`). The button is enabled as soon as `answered` > 0.
- **Plan**:
  1. `review.undo`, branch without history: when `log[-1]` carries `changes`, do not drop it: return the log with that entry's `changes` kept and only its `checked` removed (the last rally unchecked), or the log unchanged with `undone = None`.
  2. Simpler variant to weigh: `superseded` leaves the previous carrier its `changes` (only older ones are emptied), so `log[:-1]` always falls back on the save before.
  3. Test in `tests/test_review.py` beside line 933: three report saves, `undo(log, [])`, `corrections(...)` still holds the first two.
- **Check**: `uv run pytest -q tests/test_review.py -k undo`.

## REV-04 Every Match tab edit saved at once (state.md item 14): the path

- **Type**: feature
- **Impact**: high — ends the four ways of saving and the corrections lost on a reload, a tab change, a crash or a refused save.
- **Effort**: M (half a day) for steps 1-5, after REV-01, REV-03 and REV-05
- **Confidence**: read (server contract traced; the cost of one `/answer` on a real match is not measured)
- **Where**: `R/ReportEditor.tsx:395-420,689-702,757-766`, `R/MatchTab.tsx:252-267`, `R/Review.tsx:209-230,343-360`, `R/RallyComment.tsx:26,49`, `src/volleyball_stats/review.py:1795-1800,3227-3252,3390-3392`, `docs/review.md`, `docs/state.md` item 14
- **Problem**: touches, winner, join, end, wrong call and replay wait for "Valider"; stars, timeouts and "Supprimer" go at
  once; comments on blur; the match's end with an apply. The server needs nothing new for the first group: `/answer` with
  `id: 'edit:…'`, `choice: 'report'`, `changes` and no `checked` is already accepted (`sent = choice == "report" and "changes" in body`),
  and `changes` is the whole edit state, small (largest saved body in `outputs/`: 4,935 bytes). Measured offline on the two
  largest matches: `waiting()` 47-81 ms (of which `film.status` 42-55 ms), answers file 1.1-1.2 MB rewritten per save,
  about 200 `edit:` entries of 1,000 in each log.
- **Plan**:
  1. Client, `R/hooks/useAutosave.ts` used by `ReportEditor`: when `JSON.stringify(changes)` differs from the last body sent, wait 800 ms without a change, then `onAutosave(changes, unchecked)` → `post('answer', { id: 'edit:<now>', choice: 'report', changes, auto: true, unchecked })`, `unchecked` being the checked rallies of the `unsaved` set (a checked rally edited goes back to "to check", as "Supprimer" does today through `saveUnchecked`). One request at a time; a change during it sends again after. The answer goes through `onSaved` only: no `setRound`, the editor is not remounted.
  2. "Valider" stays one request (`changes` + `checked`, as today) and cancels the pending timer: it only checks from the owner's view. Remount after it only when `changes` still equals what was sent (today edits typed during the request are dropped by the remount).
  3. Failure: the `unsaved` guard stays as it is (it now covers the 800 ms and failures only); an `ErrorNote` from `explain` above the list (REV-05) with the retry on the next change and every 5 s while unsaved. While `busy`, the editor is inert (REV-02).
  4. Tab closed inside the 800 ms: on `pagehide`, send the pending body with `fetch(..., { keepalive: true })` (bodies are far under its 64 KiB limit).
  5. Server, `/answer`: an `auto` edit whose predecessor `log[-1]` is itself an unapplied `auto` edit replaces it and pushes no `history` entry: "Annuler" takes back the edits since the last "Valider" or answer in one step, the log does not grow by one stub per touch, and `UNDOS` is not used up in three rallies. `superseded` drops emptied `edit:` entries that carry no `checked`/`unchecked`. Tests in `tests/test_review.py`.
  6. Comments: `RallyComment` saves 800 ms after the last key instead of on blur and unmount.
  7. The match's end and the sets stay with their apply (they change the pipeline's input); say so in `docs/review.md`, and rewrite item 14.
  8. Before choosing 800 ms: time one `/answer` in the browser's network panel on a real match (`questions.build` runs on each).
- **Check**: correct a touch, reload within two seconds: the correction is there; `npm test`, `uv run pytest -q`.

## REV-05 The review's requests lose the server's reason: one generic failure for everything

- **Type**: bug
- **Impact**: medium — "busy", "updating" and "no answer" all read as the same unexplained failure, so the owner retries blindly; against the `ErrorNote` + `explain` rule.
- **Effort**: M (half a day)
- **Confidence**: read
- **Where**: `web/src/lib/review.ts:362-378` (`post`), `R/Review.tsx:241-360,396-398,493,552,563,588,706`, `R/ReviewHeader.tsx:122`, `R/Elsewhere.tsx:19-27`, `web/src/components/SiteTab.tsx:441,486`
- **Problem**: `post` throws `new Error(`${path}: ${response.status}`)`: the body's `{"error": "busy"}` (503, `review.py:2977`) is
  dropped, a rejected `fetch` is not named `network`. Every 409 is read as a name merge:
  `const { merges, conflict } = await response.json()` then `merges.map(...)`: on `{"error":"updating"}` (`review.py:3143`)
  or `{"error":"busy"}` (`:3110,3123`) that is a `TypeError`. `Review` keeps `error` as a boolean and shows
  `<ErrorNote className=... />` with no text. `explain` already knows the three codes; `lib/app.ts` `call()` already reads them.
- **Plan**:
  1. `lib/review.ts`: `post` catches the fetch rejection (`network`), reads the JSON once, treats a 409 as a merge only when `merges` is an array (as a conflict when `conflict` is), and otherwise throws `new ReviewError(code)` carrying `error` from the body.
  2. `Review.tsx`: `error` becomes `Explained | null`; one `fail(e)` helper replaces the fifteen `setError(true)`; `onError` props of `Names`, `Pictures` and `onFailed` of `ReviewHeader` pass the error on. `Elsewhere`, `SiteTab` (restore: `r.error`; copies) use `explain` too.
  3. Tests in `lib/review.test.ts`: 503 busy, 409 updating, 409 merges, 409 conflict, rejected fetch.
- **Check**: `npm test`; by hand: answer a question during "Refaire les vidéos": the note says the app is busy.

## REV-06 Shortcuts fire behind dialogs and menus, and repeat when held

- **Type**: bug
- **Impact**: medium — a letter typed in the "..." menu or with a confirmation open answers the question behind it, or changes the named touch's action.
- **Effort**: S (under an hour)
- **Confidence**: read (Radix's menu source included: character keys are not prevented, `@radix-ui/react-menu/dist/index.mjs:343`)
- **Verified** (21 Nov, headless Chrome on a scratch copy of the first match): confirmed. With the header's "..." menu open, `S` changed the second touch's action (`pass` -> `serve`), `V` opened the "Valider quand même" dialog and `→` stepped the video (7.1 -> 7.4 s).
- **Where**: `R/Review.tsx:567-582`, `R/ReportEditor.tsx:793-818`, `R/ClipVideo.tsx:328-341`, `R/Names.tsx:87`
- **Problem**: four window `keydown` handlers, four different guards:
  - Questions (X, C, S, P, 1, 2): `typing` only, no dialog or menu check. With an `ask` open, `ClubDialog`, the match switch or the "..." menu focused, S skips the question, 1 answers it.
  - Match tab: checks `[role="dialog"]` but not `[role="menu"]`: R or P typed for the menu's typeahead sets the named touch to reception or set.
  - `ClipVideo` arrows: no dialog check (Space has one).
  - None checks `event.repeat`: N held adds a touch per repeat, S held skips several questions, V held re-validates as soon as `saving` clears.
- **Plan**:
  1. `web/src/lib/keys.ts`: `shortcutsOff(event)`: `defaultPrevented`, `repeat`, ctrl/meta/alt, target in `input, textarea, select, [contenteditable="true"]`, or `document.querySelector('[role="dialog"], [role="menu"], [role="listbox"], dialog[open]')`.
  2. The four handlers call it (the video's arrows keep repeating: frame stepping wants it).
  3. `lib/keys.test.ts` on a hand-made event object for each case.
- **Check**: `npm test`; by hand: open "...", type S: the question stays.

## REV-07 On piece and touch questions the name field holds the focus: the shown shortcuts do nothing

- **Type**: UX
- **Impact**: medium — the answering loop's keys (X, C, S, P, 1) are dead on its two most frequent questions until a click elsewhere.
- **Effort**: S (under an hour)
- **Confidence**: suspected — traced in the code; one keypress on a fresh piece question in a browser confirms it
- **Where**: `R/Review.tsx:591-606` (`PlayerSelect ... autoFocus`, `key={question.id}`), `:569-571`, `R/PlayerSelect.tsx:123-143`
- **Problem**: the field is remounted and focused for each question, and the handler returns on
  `event.target.closest('input, textarea, select')`: X goes into the field as text. Escape does not give the keys back
  (`onDone` is not passed here, so the field keeps the focus). The buttons still show their `kbd` hints.
- **Plan** (the owner's call between the two):
  1. Smallest: pass `onDone={() => (document.activeElement as HTMLElement | null)?.blur()}` as the Match tab does (`ReportEditor.tsx:1190-1203`): Escape hands the keys to the shortcuts; add the line to `Shortcuts`.
  2. Or no autofocus and a key (`/` or Enter) that focuses the field, so a wrong piece is skipped in one key and a name is two.
- **Check**: on a piece question, Escape then X answers "not a player".

## REV-08 Match tab: focus left in a list or a checkbox mutes every shortcut

- **Type**: UX
- **Impact**: medium — after choosing an action with the mouse, V, N, the letters and Space do nothing and the arrows change the action instead of stepping the video.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/ReportEditor.tsx:802,1125,1132,1230,1328,1333`, `R/MatchTab.tsx:153,167`, `R/ClipVideo.tsx:330`
- **Problem**: the native `<select>`s keep the focus after `onChange`; both handlers return on
  `closest('input, textarea, select')`, which also matches the two checkboxes (wrong call, join). `PlayerSelect` already
  blurs itself (`onDone`).
- **Plan**:
  1. The five `<select>`s: `onChange={(e) => { ...; e.currentTarget.blur(); }}`.
  2. In the shared guard (REV-06) a checkbox or radio is not "typing": `input:not([type="checkbox"], [type="radio"])`.
- **Check**: pick "Attaque" in a row with the mouse, press V: the rally is validated.

## REV-09 Keys for the Match tab's most frequent corrections

- **Type**: feature
- **Impact**: medium — who touched, a touch too many and the result are the usual corrections, all mouse-only today.
- **Effort**: M (half a day)
- **Confidence**: read
- **Where**: `R/ReportEditor.tsx:51-54,793-818,1152-1203`, `R/MatchTab.tsx:140-175`, `R/Shortcuts.tsx:40-60`, `R/ClipVideo.tsx:324-341`
- **Problem**: the keys are the nine action letters, V and N; Space and the arrows in the Match tab only. Nothing for the
  named touch's player, its removal, its result, the next touch, the next rally to check; no Space or arrows on the Questions tab.
- **Plan** (each one line in the existing handler, all through REV-06's guard):
  1. J: focus the named touch's `PlayerSelect` (the caption editor's when shown, else the row's); Enter picks, Escape gives the keys back (already so).
  2. Backspace/Delete: `remove(named)`; again restores.
  3. 1 / 2 / 3: result in play / point / fault of the named touch.
  4. ↑ / ↓: previous / next touch, paused on it (`onPause(at)`); Shift+V or Enter on the last touch: validate and go on (already what V does when `k === here`).
  5. T: the next rally still to check (`openingTime` in `helpers/report.ts:186` gives it).
  6. Questions tab: `ClipVideo` listens to Space and the arrows out of `free` mode too.
  7. `Shortcuts.tsx` lists them; `keys.test.ts` checks no key is bound twice.
- **Check**: a rally corrected and validated without the mouse; `npm test`.

## REV-10 Two tabs or two devices: the last save silently replaces the other's corrections

- **Type**: data-loss
- **Impact**: medium — with "Réseau local" a phone and the PC may both have the Match tab open; whoever saves last wins for the whole match.
- **Effort**: M (half a day)
- **Confidence**: read
- **Where**: `src/volleyball_stats/review.py:3239-3244` (`log[:] = superseded(log, shown)`), `R/Review.tsx:343-360`, `R/ReportEditor.tsx:395-412`
- **Problem**: `changes` is the sender's whole edit state and the server empties every earlier waiting save. A tab opened
  before another tab's corrections sends a state without them: they are gone, no refusal, no notice. Nothing tells a
  tab that the log moved (`readElsewhere` is about the other machine's backup).
- **Plan**:
  1. Each response already gives `answered` (the log's length). The client sends it back as `seen` with an `edit:` answer; the server answers 409 `{"error":"stale"}` when `seen != len(log)` and `changes` is sent.
  2. `explain`: `stale` → a sentence with a "Recharger" button (`KNOWN` in `lib/errors.ts`, fr and en).
  3. Tests: `tests/test_review.py` (refused when the log moved), `lib/review.test.ts` (the code reaches the caller).
- **Check**: two tabs, a correction validated in each in turn: the second is told to reload.

## REV-11 A run whose request drops is shown as failed while it goes on

- **Type**: bug
- **Impact**: medium — on a long run (films, copies) the page says "failed", re-enables its buttons and never reloads at the end.
- **Effort**: S (under an hour)
- **Confidence**: suspected — the code path is traced; which browsers cut a request silent for minutes is not tested (Firefox's response timeout is 300 s by default; a sleeping laptop or a Wi-Fi drop does it anywhere)
- **Where**: `R/Review.tsx:469-495`
- **Problem**: `reload` awaits one `post(path)` held open for the whole run (`run_steps` answers at the end). On a
  rejection it clears the poll, `setBusy(null)`, and `setError(!failed)`: `readFailure()` is null since the run still goes.
- **Plan**:
  1. In the `catch`: `const p = await fetch('progress').then((r) => r.json()).catch(() => null)`; when `p?.steps`, keep `busy` and follow the run exactly as the `running` effect does (`:446-466`: poll, then `readFailure()` or reload). Extract that effect's body as `followRun()` and call it from both.
- **Check**: start "Refaire les vidéos", cut the network for the tab (DevTools offline) then restore: the progress goes on and the page reloads at the end.

## REV-12 The unsaved guard stays disarmed, and some reloads skip it

- **Type**: data-loss
- **Impact**: low — after a cancelled or failed action, corrections made next close without a question; a few in-app reloads only get the browser's prompt, the action already done.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/Review.tsx:212-218,530-565,680-686`, `R/Conflicts.tsx:73,184`, `web/src/components/ClubDialog.tsx:135`, `web/src/components/Behind.tsx:37`, `R/PhotoPicker.tsx:28`, `R/TeamEditor.tsx:28`
- **Problem**: `mayLeave()` sets `leaving.current = true` and only `reload`'s own paths and a tab change reset it. It stays
  set when `startOne`'s "Réanalyser ce match ?" is cancelled (`started === 'cancelled'`), when `post('separate')` or
  `post('end')` fails (`split`, `saveEnd`), when a `choose` opened from `run` is closed. Separately, the club dialog saved
  from the review, the update's restart, a cut or a "forget" reload the page without `mayLeave`.
- **Plan**:
  1. `mayLeave` stops setting the flag; a `leave()` helper sets it right before each `location.reload()` / navigation (`reload`, `followUpdate`, `MatchSwitch`).
  2. The in-app reloads above take `mayLeave` as `NewReports` does and ask before their request.
  3. Mostly moot once REV-04 is in: keep step 1, drop step 2 then.
- **Check**: edit a touch, "Réanalyser" then cancel, close the tab: the browser asks.

## REV-13 Names: two saves in flight, the second forgets the first

- **Type**: bug
- **Impact**: low — a name typed while the previous card's save is still going shows as not saved and is missing from the player lists until a reload.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/Names.tsx:117-143`
- **Problem**: `const next = new Map(saved).set(key, value); ... setSaved(next); onNamed(next);` builds on the `saved` of the
  render that started the save: the second answer writes a map without the first's entry.
- **Plan**:
  1. `setSaved((s) => new Map(s).set(key, value))`; `onNamed` from a `useEffect` on `saved` (skipping the first render).
- **Check**: with the network throttled, name two cards quickly: both keep their name and both are offered in the Match tab.

## REV-14 Names: Enter loses the place, and the jersey field posts twice

- **Type**: UX
- **Impact**: low — naming twelve players by keyboard: after Enter in a name field the next ↓ jumps back to the first card; each jersey typed costs two `/name` requests.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/NameField.tsx:65-71`, `R/Names.tsx:84-107,121-123,318-322,335,355`
- **Problem**: Enter in the name field is `preventDefault()` then `blur()`: no submit, the focus falls to `body`, and
  `focusCard(null, 1)` starts from the top. Enter in the jersey field submits (`void onSave(value); focusCard(...)`), the
  move blurs the field (`onBlur={() => void onSave(value)}`), and the "same as before" test passes for both since the
  first answer has not come back.
- **Plan**:
  1. `NameField`: an `onEnter` prop; `Names` passes `() => focusCard(form, 1)` so Enter saves (through the blur) and goes to the next card.
  2. `PlayerCard`: a ref of the last value sent; `onSave` returns when it is the same.
- **Check**: name a card, Enter: the next card's field has the focus; the network panel shows one `/name` per card.

## REV-15 The question's video element is made again for every question

- **Type**: performance
- **Impact**: medium — each answer waits for a new `<video>` on the 4K source to open and seek before the next clip shows; over 200 questions this is the loop's dead time.
- **Effort**: M (half a day)
- **Confidence**: suspected — the remount is read; the time it costs is to measure (performance panel, answer → first frame, ten questions)
- **Where**: `R/Review.tsx:821` (``key={`${question.id}${showOther}`}``), `R/ClipVideo.tsx` (the effect on `clip`)
- **Problem**: the key remounts `ClipVideo`, so the browser drops the element, its buffer and its decoder, then loads
  `match.video` again. The clips of one match come from one file.
- **Plan**:
  1. Measure first; stop there if the gap is under 150 ms.
  2. Else drop the `key`, reset `ClipVideo`'s per-clip state (`stretch`, `nudge`, boxes) in its `[clip.start, clip.end]` effect and seek the same element.
  3. Preload: once a question shows, `fetch` nothing, but set `currentTime` of a second hidden muted element to the next question's start (only if step 2 is not enough).
- **Check**: the measure before and after, same ten questions.

## REV-16 Following the app's update: waits for good when the server stops answering

- **Type**: UX
- **Impact**: low — the review stays locked on "update" with no word if the server died; against "nothing waits for good".
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/Review.tsx:500-523`
- **Problem**: `const found = await call<AppState>('state'); if (!found.ok) { return; }` every 3 s, for ever.
- **Plan**:
  1. Count the failures in a row; at 5, `window.clearInterval(timer); setBusy(null); setUpdateError(explain(t, found.error))`.
- **Check**: start the update, stop the server by hand: after 15 s the note says the app does not answer.

## REV-17 Pollers on `setInterval` with an async body

- **Type**: bug
- **Impact**: low — on a slow server (an apply on a busy disk, a phone on Wi-Fi) requests pile up and an older answer may land after a newer one: the bar steps back.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/Review.tsx:413-444` (`watchRun`, 400 ms), `web/src/components/SiteTab.tsx:206` (3 s), `web/src/components/Setup/Setup.tsx`, `web/src/components/ExportSite.tsx`
- **Problem**: `window.setInterval(async () => { ... await fetch('progress') ... }, 400)` starts a request whether or not
  the last one answered. `lib/tasks.ts` already does it right (a `setTimeout` chained after each answer).
- **Plan**:
  1. `web/src/lib/poll.ts`: `every(ms, work): () => void` (chained `setTimeout`, returns the stop); the four places use it.
  2. A vitest case with fake timers: a `work` slower than `ms` runs once at a time.
- **Check**: `npm test`.

## REV-18 Buttons that start a request without a loader

- **Type**: UX
- **Impact**: low — a second click sends the request twice ("Traité" appends two answers; a timeout bound moves twice), against the project's rule.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/ReportRow.tsx:46,52,60`, `R/TimeoutRow.tsx:52,65,73,76`, `R/ReportEditor.tsx:858,910`, `R/Conflicts.tsx:45`, `R/Conflicts.tsx` (`Pinned`)
- **Problem**: these `onClick`s call `onHandled`, `onTimeout`, `onSplit`, `repin` directly; `Review`'s `handled` and
  `saveTimeout` have no in-flight guard either (only `answer` has its `sending` ref).
- **Plan**:
  1. `ReportEditor` already has `const [saving, run] = useRunning()`: route `onHandled` and `onTimeout` through `run('report:<id>' | 'timeout:<start>', ...)`, pass `busy`/`disabled` down to `ReportRow` and `TimeoutRow`.
  2. `Conflicts`: `useRunning` for "Séparer" and `repin`.
- **Check**: with the network throttled, each button shows its loader and its neighbours wait.

## REV-19 Failures shown outside `ErrorNote`, or not at all

- **Type**: UX
- **Impact**: low — the server's raw words as the only message, no way to the log; two actions fail silently.
- **Effort**: M (half a day)
- **Confidence**: read
- **Where**: `R/RunFailure.tsx:15`, `web/src/components/Setup/PreparingCard.tsx:80`, `web/src/components/Setup/Setup.tsx:98`, `web/src/components/SiteTab.tsx:409-412,441,486`, `web/src/components/Setup/CourtDialog.tsx`, `web/src/components/ClubDialog.tsx:34`, `web/src/components/Setup/ImportDialog.tsx`
- **Problem**: `RunFailure` prints `repr(error)` in a mono `<p>`; `PreparingCard` and the backup line print `job.error` /
  `state.backup.error` raw; the restore's failure is `<Status ok={false}>{t('error.failed')}` with `r.error` dropped;
  `copiesError && <ErrorNote />` has no text. Silent: `void shrink(file, size).then(onChange)` (an unreadable image does
  nothing), `fetch('/app/sources')` failing gives an empty list.
- **Plan**:
  1. Each of the first five becomes `<ErrorNote {...explain(t, error, '<its sentence>')} />` (detail small, "Voir le détail").
  2. `ClubDialog`: `.catch(() => setError(explain(t, null, 'club.badImage')))` (fr, en); `ImportDialog`: an `ErrorNote` with retry in place of the empty list.
- **Check**: `npm test` (`locales.test.ts` for the new keys); a `.txt` renamed `.png` as the club's logo shows the note.

## REV-20 Native tooltips in the match timeline

- **Type**: UX
- **Impact**: low — four hover texts with the browser's look and delay, none on touch; the rule is `Tip` only, and its test does not see them.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `R/MatchTimeline.tsx:186,199,231,241`, `web/src/components/Tip.test.ts`
- **Problem**: SVG `<title>` children (timeout, rally, clip, comment). `Tip.test.ts` looks for `title=` attributes only.
- **Plan**:
  1. One `Tip` for the timeline, its label set by `onPointerMove` over the marks (as the bar's time bubble does), `<title>` removed; the marks keep an `aria-label`.
  2. `Tip.test.ts`: also fail on `<title>` in a `.tsx` under `components/`.
- **Check**: `npm test`.

## REV-21 `useRunning` clears another action's state; the Site tab's buttons do not all wait

- **Type**: bug
- **Impact**: low — in the Site tab a short action ending clears the loader of a longer one started beside it, which can then be started twice.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `web/src/hooks/useRunning.ts:8-12`, `web/src/components/SiteTab.tsx` (buttons not disabled on `doing !== null`)
- **Problem**: `finally { setRunning(null); }` whatever key is current.
- **Plan**:
  1. `setRunning((k) => (k === key ? null : k))`.
  2. `SiteTab`: every button that calls `run(...)` gets `disabled={doing !== null}`.
  3. A vitest case for the hook's reducer logic (extract `(current, ended) => next`).
- **Check**: `npm test`.

## REV-22 Dialogs that lose typed work on a click outside, and fields refused without a reason

- **Type**: UX
- **Impact**: low — up to twelve court clicks or a filled import form gone on one stray click; a save button stays grey with nothing saying why.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `web/src/components/Setup/CourtDialog.tsx:143`, `web/src/components/Setup/ImportDialog.tsx:121,263`
- **Problem**: neither dialog stops Radix's outside-click close once something is entered. `disabled={... || /[,:/]/.test(name)}`
  and `validName(team.name)` only set `aria-invalid`.
- **Plan**:
  1. `onInteractOutside={(e) => dirty && e.preventDefault()}` on both `DialogContent`s (Escape and the cross still close, after `ask` when dirty).
  2. One short line under the field when invalid (`setup.nameChars`, fr and en).
- **Check**: three court clicks, a click on the backdrop: the dialog stays.

## REV-23 Club dialog: picking the same image again does nothing

- **Type**: bug
- **Impact**: low — remove the logo, pick the same file: no `change` event, nothing happens.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `web/src/components/ClubDialog.tsx:27-37`
- **Problem**: the file input keeps its value after `shrink`.
- **Plan**:
  1. `event.currentTarget.value = ''` after reading `files[0]`.
- **Check**: by hand, the steps above.

## REV-24 Tests missing on what loses work

- **Type**: tests
- **Impact**: medium — the three data-loss paths above had no test to catch them.
- **Effort**: M (half a day)
- **Confidence**: confirmed (test lists read; `npm test` and the Python suite's `undo` cases checked)
- **Where**: `web/src/lib/review.test.ts` (covers `allMarked` and `serverBusy` only), `tests/test_review.py:922-934`, `R/helpers/report.test.ts`
- **Problem**: `post()` has no case (status codes, 409 shapes); `undo` without history is only tested on answers that
  carry nothing; the Match tab's "save failed" branch and the shortcut guards are untestable where they sit (inline in
  components); `pageSpans` (`helpers/report.ts:245`) has no case.
- **Plan**:
  1. The cases listed in REV-01, REV-03, REV-05, REV-06.
  2. `pageSpans`: one case with a joined and a deleted rally.
- **Check**: `npm test`, `uv run pytest -q`.

## REV-25 `ReportEditor.tsx` (1,357 lines) and `Review.tsx` (959): split where REV-04 needs it

- **Type**: maintainability
- **Impact**: low — every change to the Match tab reads one component holding the edit state, the checks, the keys and three levels of rows.
- **Effort**: M (half a day)
- **Confidence**: read
- **Where**: `R/ReportEditor.tsx`, `R/Review.tsx:241-360`, `web/src/lib/review.ts:208-209,223-225,282-286`
- **Problem**: the edit state (`fixes`, `added`, `splits`, `rallyFixes`, `changes`, `unsaved`: lines 233-244, 395-420) is what
  autosave hooks into; the touch row (1093-1210) and the rally's footer (1300-1352) are self-contained JSX. `Review.tsx`
  has seven save functions of the same shape. `lib/review.ts` carries doc comments orphaned from their functions.
- **Plan**:
  1. `R/hooks/useCorrections.ts`: the four states, their setters, `changes`, `unsaved` (moved as is, then REV-04's autosave beside it).
  2. `R/TouchRow.tsx` and `R/RallyFooter.tsx` cut out with their props; nothing else moves.
  3. `Review.tsx`: one `save(body, after?)` used by the seven.
  4. Remove the orphaned comments.
- **Check**: `npx tsc --noEmit -p . && npm test`; the Match tab by hand.

## REV-26 Match tab renders everything on each tick of the video

- **Type**: performance
- **Impact**: low — suspected jank while a clip plays on a long match (every rally's rows and checks, and the timeline's marks, recomputed about ten times a second).
- **Effort**: M (half a day)
- **Confidence**: suspected — the render path is read; a React profile on a full match is needed before touching it
- **Where**: `R/MatchTab.tsx` (`listNow` state passed as `now`), `R/ReportEditor.tsx` (rows and `problemsAt` for all rallies in the render body), `R/MatchTimeline.tsx:170-245`
- **Problem**: `now` is a prop of both; neither memoises what does not depend on it.
- **Plan**:
  1. Profile one minute of playback; stop if a commit stays under 8 ms.
  2. Else `useMemo` the rows and warnings on `[changes, saved, match]`, and split the timeline's static marks into a `memo` child, the cursor alone following `now`.
- **Check**: the profile before and after.

## REV-27 Small ones

- **Type**: accessibility
- **Impact**: low — each a detail for keyboard or screen-reader users.
- **Effort**: S (under an hour)
- **Confidence**: read
- **Where**: `web/src/components/VideoChoice.tsx:111`, `web/src/components/Tasks.tsx:205`, `web/src/components/Setup/RecordingPlayer.tsx:70,121`, `R/More.tsx:82`
- **Problem**: `VideoChoice` is a hand-made `role="dialog" aria-modal="true"` with no focus trap (Tab reaches the page behind);
  the tasks panel carries `role="dialog"` while not modal, which mutes the Match tab's shortcuts as long as it is open;
  `void v.play()` leaves an unhandled rejection when the browser refuses; "more pictures" loads behind a plain sentence, not the loader used elsewhere.
- **Plan**:
  1. `VideoChoice` on the shared `Dialog` (as `ask` is).
  2. Tasks panel: `role="region"` with its `aria-label`.
  3. `v.play().catch(() => {})`.
  4. `More`: the shared spinner beside the sentence.
- **Check**: `npm test`; Tab inside the video choice stays inside.

## Looked at, fine

- `R/Review.tsx` `answer`: the `sending` ref stops a double submit; a piece conflict or a merge refusal leaves the question in place.
- `savePick`, `saveComment`, `LookChoice`: optimistic change rolled back on failure.
- `R/Pictures.tsx`: saves queued one after the other, the last state winning.
- `web/src/hooks/usePhotos.ts`, `lib/tasks.ts`: timers cleared on unmount, one request at a time (`tasks`).
- `web/src/components/ask.tsx`, `Tip.tsx` (`Tip`, `Hint`), `ErrorNote.tsx` with its log dialog, `lib/sheet.ts`, `lib/errors.ts`.
- `lib/openMatch.ts`, `lib/appServer.ts`: every wait has an end (5 min) and says why it failed.
- `web/src/components/Setup/NetworkDialog.tsx`, `ExportSite.tsx`, `AppMatches.tsx`, `Update.tsx`, `NewReports.tsx`: loader, failure and retry present.
- `web/src/components/JobProgress.tsx`: the bar moves on the server's counted `fraction` only.
- `R/helpers/checks.ts`: every `Problem` kind has a test case; `helpers/report.ts`: all exports tested but `pageSpans`.
- `web/src/locales/fr.json` / `en.json`: 1,532 keys each, none missing; no hard-coded interface text found in the area's `.tsx`.
- No `title=` attribute and no `window.confirm` in the area (`Tip.test.ts`, grep).
- Request and response shapes against `review.py` for `/answer`, `/comment`, `/pick`, `/timeout`, `/name`, `/odd`, `/more`, `/photo`, `/look`, `/team`, `/nearest`, `/progress`, `/failure`, `/sync`: they agree (apart from REV-05).
- `R/Review.tsx` `beforeunload` guard and `mayLeave` on tab change, match switch, apply and undo: present (holes in REV-02 and REV-12).
- Grid widths in the review (`minmax(0, …)` everywhere, no fixed pixel width): nothing found by reading that forces a horizontal scroll; not checked in a browser.
