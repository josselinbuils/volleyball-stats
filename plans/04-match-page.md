# Match page — improvements

One entry per finding, most valuable first. IDs are `PAGE-NN`.

Numbers come from the two matches in `outputs/matches/*/review/data.js` (called A: 129 rallies, 947 contacts; B: 150
rallies, 1201 contacts). `npx tsc --noEmit -p .` is clean and `npm test` passes (61 files, 430 tests) as of this audit.
Not checked: nothing was opened in a browser (the DevTools connection failed), so no real tab order, no phone at 390 px,
no contrast of the club themes `applyTheme` builds, no frame cost, no tooltip behaviour: the entries marked `read` rest
on the code alone. The bundle's composition is unknown too (`npm run build` is forbidden here, so no visualiser), as are
`scene3d/hall.ts` past its first 80 lines and the `ui/` primitives beyond `button` (stock shadcn).

## PAGE-01 A let serve gets no rating, a touch followed by a net or floor contact a wrong one

- **Type**: bug
- **Impact**: medium — every server's "Service" grade, the tough/fair/easy split, the "Service gênant" strength and the season's serve measure skip 9 of 99 serves in play on match A (2 of 123 on B).
- **Effort**: S
- **Confidence**: confirmed (counted on both matches with a scratch script; the code path read)
- **Where**: `web/src/components/Stats/helpers/stats.ts:250`, `:266`, `:290` (and the set's `contacts[k + 1]` for `setsAttacked` / `setAssists`), `web/src/components/Stats/helpers/stats.test.ts`
- **Problem**: `stats()` reads the raw next contact, which may be a `net` or `floor` contact and not a touch:
  `const grade = graded(serveRating(c, contacts[k + 1], contacts[k + 2]));` and `serveRating` returns null when
  `next.type !== 'pass'`. A serve brushing the net (serve, `net`, pass) is therefore unrated, although `web.result`
  already treats it as in play ("a serve brushing the net on its way over"). Same raw read for
  `rating(c, contacts[k + 1])` on receptions and digs: a `floor` contact 0.2 s after the touch gives null (`FLIGHT_S`), a
  later one is graded from the floor contact's place. `attackRating` does it right: `after.filter(... isTouch(n))`.
  Counted: serve then `net` then pass 9 (A) and 2 (B); reception or dig then a non-touch then a touch 2 (A); set then a
  non-touch then an attack 2 (A) and 2 (B).
- **Plan**:
  1. In `stats()`, compute once the next touches of each contact in its rally (`isTouch`, same `rally`), and pass them:
     the serve its next two touches, the reception and the dig their next touch, the set its next touch.
  2. Tests in `stats.test.ts`: serve + `net` + pass + set is rated as serve + pass + set; a pass followed by a `floor`
     then a set is graded from the set; a set + `net` + attack counts in `setsAttacked`.
  3. Report the serve grades before and after on both matches (`lines()` on their `data.js`).
- **Check**: `cd web && npm test -- stats`; on match A the rated serves go up by 9.

## PAGE-02 The coach's fault playlists name the player at fault under the video

- **Type**: bug
- **Impact**: medium — "Le coin du coach" must never name a player for a fault (the owner's rule); playing "ce qui coûte des points" shows the name of each player who made the fault.
- **Effort**: S
- **Confidence**: read (both files traced; not seen in a browser)
- **Verified** (21 Nov, headless Chrome on a scratch copy of the first match): confirmed. Playing "Les attaques fautées ou contrées", the third clip's bar reads "Attaque fautée · ASPOM 1, <the player's name> · 11:04".
- **Where**: `web/src/components/Coach/Coach.tsx:106`, `web/src/components/Watch/PlaylistBar.tsx:36-37` and `:73-78`, `web/src/lib/playlist.ts` (`Clip`)
- **Problem**: `ThingRow` strips the names on purpose: `contactClips(thing.contacts, match.duration).map(({ player: _, name: __, ...clip }) => clip)`.
  The clip keeps `contact`, and the playlist bar reads the player from it:
  `const shown = useVideoTime((time) => clip?.contact ?? ...)`, `const action = contacts[shown]`, then
  `[groupName(t, action.g), playerLabel(t, action.person)]` beside `actions.<type>.error`. `clipLabel` and
  `entryDetail` (the rally cards) do respect the stripped names.
- **Plan**:
  1. Add `unnamed?: true` to `Clip`; `ThingRow` sets it in place of the destructuring.
  2. `PlaylistBar` leaves `playerLabel` out of the action line when `clip?.unnamed`; `contactClips` callers unchanged.
  3. Owner's call to ask: the spoken and written commentary (`helpers/commentary.ts:77`, `...FaultNamed`) names the
     player during these clips too; `unnamed` could pick the unnamed line there.
  4. Test: a `PlaylistBar` helper (or `clipLabel` sibling) returning the action line without a name for an unnamed clip.
- **Check**: play a row of "Ce qui coûte des points" for the owner's team: no player name anywhere around the video.

## PAGE-03 About 400 tab stops before the end of the page

- **Type**: accessibility
- **Impact**: medium — a keyboard user tabs through every rally three times (387 stops on match A, 450 on B) to cross the page.
- **Effort**: M
- **Confidence**: read (the counts are the rallies of the two matches; tab order not walked in a browser)
- **Verified** (21 Nov, headless Chrome on a scratch copy of the first match): confirmed and larger: 800 focusable controls on the first match's page at 1440 px.
- **Where**: `web/src/components/Story/Curve.tsx:167-181`, `web/src/components/RallyCharts/Timeline.tsx:60-75`, `web/src/components/Watch/RallyCards.tsx:60-61`, `web/src/components/CourtChart/Arrows.tsx:21`
- **Problem**: one focusable `<button>` per rally in the score curve, in the timeline and in the rally cards, none with
  `tabIndex`. The court's dots already follow the opposite policy (`ContactDots.tsx`: "Hundreds of them stay out of the
  tab order", `tabIndex={-1}`), but the "Directions" view keeps one stop per arrow (`SvgButton` default `tabIndex={0}`):
  292 serves and attacks on A, 372 on B.
- **Plan**:
  1. A small `useRoving` hook in `web/src/hooks/` (three consumers): one stop per chart (the current rally, else the
     first), ArrowLeft/ArrowRight/Home/End move the focus among the container's buttons.
  2. Use it in `Curve`, `Timeline` and `RallyCards`; `Arrows` takes `tabIndex={-1}` as `ContactDots` does, the zones
     view staying the keyboard's way.
  3. Test the hook's key handling (next, previous, ends) beside it.
- **Check**: Tab from the header reaches "Les échanges" in a handful of presses; arrows walk the rallies in each chart.

## PAGE-04 A grade's breakdown and a chip's comparison cannot be read on a touch screen

- **Type**: UX
- **Impact**: medium — on a phone a player sees "3,2" or "Service gênant" and never what it is made of; a tap plays the touches.
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/CountButton.tsx:27-38`, `web/src/components/Stats/StatsTable.tsx:114-136` and `:255-283`
- **Problem**: the breakdown ("2 parfaites, 5 bonnes...") is `CountButton`'s `tip`, shown by `<Tip label={hint}>` on a
  button whose click plays; the chip's "12 sur 15 (80 %), le reste de l'équipe..." is a `Tooltip` on a button whose
  click plays too. Hover only: `Tip tap` is reserved for triggers "whose click does nothing else". The season page shows
  the same chip detail on tap (`Season.tsx:100`), the match page cannot.
- **Plan**:
  1. Carry the detail in the playlist's title, which the bar and the phone sheet already show: `InsightChip` plays with
     `${label(tr)}, ${who(tr)} · ${detail}`; `StatsTable`'s `tip(r, stat)` takes the `t` given to the title and is
     appended the same way for the four rating columns.
  2. Keep the hover tips as they are. If the owner finds the title too long, the alternative is a muted second line in
     `PlaylistBar` fed by an optional `about` on the playlist.
- **Check**: at 390 px, tap a serve grade: the sheet's title line tells its aces, tough, fair, easy and faults.

## PAGE-05 The hosted player has no keyboard shortcut

- **Type**: feature
- **Impact**: medium — on a computer every pause, 5 s back or full screen is a mouse trip to a small button; the seek bar's arrows move 0.1 s.
- **Effort**: M
- **Confidence**: read (`grep keydown` in the page's graph: only `useAutoHide`, `PlayerSheet` Escape, `VideoChoice`, `SvgButton`)
- **Verified** (21 Nov, headless Chrome on a scratch copy of the first match): confirmed. With the video playing and the focus on the page, Space, →, K and F change nothing.
- **Where**: `web/src/components/Watch/Watch.tsx` (the player's box), `web/src/components/Watch/VideoControls.tsx` (the seek `<input type="range" step={0.1}>`), `web/src/lib/player.tsx` (`togglePlay`, `seekTo`)
- **Problem**: no key plays, pauses, seeks, mutes or opens full screen. With the focus on the seek bar an arrow key is
  the range's native step, a tenth of a second.
- **Plan**:
  1. A pure `keyAction(event)` helper in `Watch/helpers/` returning `toggle | back | forward | mute | fullscreen | null`
     (Space and K, ArrowLeft/ArrowRight 5 s, M, F), null when the target is a button, a link, a select or a text field.
  2. `onKeyDown` on the player's box in `Watch.tsx` (focus inside it only: Space keeps scrolling the page elsewhere);
     the seek bar's own `onKeyDown` maps the arrows to 5 s.
  3. Test `keyAction` beside it. No new interface text.
- **Check**: click the video, press K, the arrows, F and M.

## PAGE-06 No link to a point of the match

- **Type**: feature
- **Impact**: medium — a player cannot send a teammate "look at this rally": the address never changes, the page always opens at its top.
- **Effort**: M
- **Confidence**: read (`location.hash` is only read for `#key=` and the list's tabs)
- **Where**: `web/src/lib/player.tsx` (`PlayerProvider`), `web/src/components/Watch/PlaylistBar.tsx`, `web/src/components/VideoChoice.tsx:67` (`location.replace(page)` drops the hash), `web/src/lib/clipboard.ts`
- **Problem**: nothing writes or reads a moment in the address. A time would not do: the hosted video's copy is shorter
  than the match (`timeline.py`), so the page without the video and the one with it disagree on seconds; the rally
  number is the same on both.
- **Plan**:
  1. On load, `#echange=42` prepares the rallies' playlist at that rally, waiting at its start (`play(title, rallyClips(...), k)`,
     the existing "tap to play" state) and scrolls to `#watch`.
  2. A "copy the link" icon button in `PlaylistBar` beside previous/next (`lib/clipboard`, a `Tip`, a check mark once copied).
  3. `VideoChoice` forwards the hash to the video page; `linkedKey` keeps the other hash parameters.
  4. Test the hash parsing helper. The link holds a number only: no footage, no name.
- **Check**: copy the link on rally 42, open it in a private window with and without the password: both wait on rally 42.

## PAGE-07 The rally cards mount about a thousand tooltips

- **Type**: performance
- **Impact**: medium — 904 (A) to 1029 (B) Radix tooltips for one list, each with a `fullscreenchange` listener, all re-rendered when the list re-renders; the letters' tips are also against the tooltip rule.
- **Effort**: S
- **Confidence**: confirmed for the counts (scratch script: 129 + 775 and 150 + 879); read for the rest
- **Where**: `web/src/components/Watch/RallyCards.tsx:60` and `:89-97`, `web/src/components/Tip.tsx:23-27`
- **Problem**: each card is a `Tip`, and inside it each letter is another `Tip` on an `aria-hidden` plain `<span>`:
  `<Tip key={c.i} label={t(`types.${c.type}`)}><span aria-hidden ...>`. CLAUDE.md: an explanation never goes "on plain
  text nor around other tips". A touch screen and a keyboard cannot open them, and the legend under the list already
  names every letter (`RallyCards.tsx:117-125`). Every `Tip` subscribes to `fullscreenchange` (`useSyncExternalStore`).
- **Plan**:
  1. Remove the per-letter `Tip` (the legend and the card's `sr-only` list of touches stay).
  2. Keep the card's own `Tip`; the `onTheLeft` one becomes plain text (it repeats its own label).
- **Check**: React DevTools' component count of `Tooltip` under `#watch` drops to the number of rallies; `npm test` (`Tip.test.ts`).

## PAGE-08 The 3D view loads and draws while it is out of sight

- **Type**: performance
- **Impact**: medium — a viewer who once chose "3D" or "TV" downloads `scene3d.js` (612 KB, 153 KB gzip) and `ball3d.js` at every page load, before scrolling to the replay, and the scene renders (2048 px shadow map) every video frame while they read the stats below.
- **Effort**: S
- **Confidence**: read (cost on a phone not measured)
- **Where**: `web/src/components/Watch/Replay.tsx:53-60`, `web/src/components/Watch/Scene3D.tsx:94-116`, `web/src/scene3d/scene.ts:542-673`
- **Problem**: the stored view mounts `Scene3D` at once (`stored === '3d' || stored === 'tv'`), whose effect calls
  `loadBall3d(); loadScene()` on mount; the replay is the page's fourth section. While the video plays, `Replay`
  re-renders every frame (`useVideoTime((now) => now)`), the effect `[state, status, theme]` calls
  `scene.current.update(...)`, and `update` always ends with `request()`: no check that the canvas is on screen.
- **Plan**:
  1. In `Scene3D`, an `IntersectionObserver` on `box` (a `rootMargin` of a screen): load on the first intersection, the
     "loading" placeholder shown until then; skip `update` while not intersecting and run it once on coming back.
  2. Optional, same observer: `Replay` holds its time while out of sight in the 2D view.
- **Check**: with `court-view` = `3d` in localStorage, reload: the network panel shows `scene3d.js` only once the replay nears the screen; the performance panel shows no WebGL frame while scrolled to "Les échanges" with the video playing.

## PAGE-09 A viewer who holds the password renders the page without the video before the one with it

- **Type**: performance
- **Impact**: medium — every returning player (the usual case once the password is in) waits for the whole page twice and sees the page without the video flash first.
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/VideoChoice.tsx:58-68`, `web/src/main.tsx:28-34`
- **Problem**: the redirect sits in an effect of a component of the rendered app: `else if (hasVideoKey()) { location.replace(page); }`.
  It runs after the first commit of `<App />` (every section computed and painted), and the page stays shown until the
  video page answers. `hasVideoKey()` only reads `document.cookie`: it can be asked before anything renders.
- **Plan**:
  1. Export from `VideoChoice.tsx` a `goToVideo(): boolean` doing `arrive()` then, with `match.videoPage`, a key and no
     `?video=denied`, `location.replace(page)`.
  2. `main.tsx` calls it before `createRoot(...).render(...)` and renders nothing when it returns true (a loader in
     `#root` if the owner wants one); the effect keeps only the `denied` branch and the `ASK` listener.
- **Check**: with the cookie set, open the match's address: the performance panel shows no React render before the navigation.

## PAGE-10 The timeline re-renders its 150 buttons four times a second

- **Type**: performance
- **Impact**: low — while the video plays, every rally's button and tooltip of "Les échanges" is rebuilt 4 times a second to move a one-pixel line; the scoreboard re-renders every frame.
- **Effort**: S
- **Confidence**: read (cost not measured)
- **Where**: `web/src/components/RallyCharts/Timeline.tsx:24` and `:79`, `web/src/components/Watch/Scoreboard.tsx:14-18`
- **Problem**: `const head = useVideoTime((time) => Math.round(time * 4) / 4);` lives in `Timeline`, whose render maps
  `rallies` to a `Fragment` with a `Tooltip` and a `<button>` each. `Scoreboard` selects the raw time
  (`useVideoTime((time) => time)`) to show a score that changes once a rally; `Overlay`'s tower selects a key.
- **Plan**:
  1. Move the playhead to a `Playhead({ from, to })` child of `Timeline` holding the `head` subscription.
  2. `Scoreboard` selects `scoreAt(...)` reduced to a string key (set and both scores), then reads the score from it.
- **Check**: React Profiler while playing: `Timeline` commits only when the current rally changes.

## PAGE-11 Two dialogs are modal in name only

- **Type**: accessibility
- **Impact**: low — with a keyboard or a screen reader, Tab leaves the password choice and the phone's video sheet for the page behind them.
- **Effort**: S for the password choice, M for the sheet
- **Confidence**: read
- **Where**: `web/src/components/VideoChoice.tsx:111-140`, `web/src/components/Watch/PlayerSheet.tsx:29-53`
- **Problem**: both set `role="dialog" aria-modal="true"` on a plain `<div>`: no focus trap, the page behind neither
  inert nor scroll-locked (the sheet sets `overscroll-contain` only). `ui/dialog` (Radix, already in the page's bundle
  through `ErrorNote`) does all three.
- **Plan**:
  1. `VideoChoice`: `Dialog open onOpenChange={(o) => !o && stay()}` with `DialogContent`, `DialogTitle`; drop the
     hand-made Escape listener.
  2. `PlayerSheet`: while `sheet`, set `inert` on `<main>`'s other sections (the sheet moves the player, so the
     attribute goes on its siblings), removed on close.
- **Check**: open each, press Tab ten times: the focus stays inside; VoiceOver's rotor lists only the dialog.

## PAGE-12 The video's buttons are 32 px tap targets on a phone

- **Type**: accessibility
- **Impact**: low — play, previous, next, speed, full screen sit 4 px apart at 32 px on a phone, under the 44 px the page gives its other controls.
- **Effort**: S
- **Confidence**: read (not tried on a phone)
- **Where**: `web/src/components/VideoButton.tsx:21`
- **Problem**: `'inline-flex h-9 min-w-9 ... max-sm:h-8 max-sm:min-w-8'` with no `tap`: the utility (`index.css:6`,
  an unseen 44 px `::after` on coarse pointers) is on `CountButton`, the 3D toggle and the curve's marks, not here.
  `docs/state.md` item 18 lists the 44 px areas as done but for the curve's and the timeline's rallies.
- **Plan**:
  1. Add `tap relative` to `VideoButton`'s classes; check in the bar that neighbouring areas split the gap evenly.
- **Check**: at 390 px with touch emulation, each button's hit box measures 44 px (DevTools, `::after`).

## PAGE-13 A film starts over the match's sound and says nothing when its file is gone

- **Type**: UX
- **Impact**: low — opening "Voir mon film" while the match plays gives two soundtracks; a missing film is a black box.
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/MyMatch/Film.tsx:19-26`
- **Problem**: `<video src={src} controls autoPlay playsInline ...>` opens without touching the match's player
  (`usePlayer().video` keeps playing) and without `VideoError`, which the match's video has for a file that cannot load.
- **Plan**:
  1. On open, `usePlayer().video?.pause()`.
  2. Wrap the film's `<video>` in a `relative` box with `<VideoError video={ref} />`.
- **Check**: play the match, open a film: the match pauses; rename the film's file: "error.video" shows over it.

## PAGE-14 The 3D view reads seven pixels back for its colours at every frame

- **Type**: performance
- **Impact**: low — seven 2D-canvas fills and `getImageData` calls plus a `getComputedStyle` per video frame while the 3D view plays.
- **Effort**: S
- **Confidence**: read (cost not measured)
- **Where**: `web/src/components/Watch/Scene3D.tsx:44-67` and `:111-116`
- **Problem**: the effect `[state, status, theme]` runs `sceneColors(...)` on every `state`, which calls `rgb()` seven
  times (`fillRect` then `getImageData(0, 0, 1, 1)`), though the colours change only with `theme`.
- **Plan**:
  1. Memoise `rgb()` by its colour string (a `Map`), or keep `sceneColors`' result in a ref refreshed when `theme` changes.
- **Check**: the performance panel shows no `getImageData` while the 3D view plays.

## PAGE-15 A let serve's arrow ends on the net

- **Type**: bug
- **Impact**: low — in the court's "Directions" view the 9 let serves of match A are drawn as balls landing on the net though they were received.
- **Effort**: S
- **Confidence**: read (same 9 and 2 serves as PAGE-01)
- **Where**: `web/src/components/CourtChart/helpers/arrows.ts:36-40`, `arrows.test.ts`
- **Problem**: `const n = all[c.i + 1];` then `const landing = !isTouch(n);`: a serve in play followed by a `net`
  contact then a pass gets `landing` true and stops at the net.
- **Plan**:
  1. When `c.result === 'play'`, take the next touch of the rally (`isTouch`) in place of a non-touch.
  2. Test: serve, `net`, pass gives an arrow to the pass, `landing` false.
- **Check**: `npm test -- arrows`.

## PAGE-16 The sticky bar's links scroll without moving the focus

- **Type**: accessibility
- **Impact**: low — a keyboard or screen-reader user who follows "Stats" stays in the bar: the next Tab goes to the next link, not into the section.
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/Header/StickyBar.tsx:103-110`
- **Problem**: `go()` does `e.preventDefault(); scrollTo({ top: ... })` only.
- **Plan**:
  1. After the scroll, `section.focus({ preventScroll: true })` with `tabIndex={-1}` set on the section (each `Card`
     has the `id` already).
- **Check**: Tab to "Stats", Enter, Tab: the focus is on the stats table's first control.

## PAGE-17 The list's tabs announce themselves as tabs but do not behave as such

- **Type**: accessibility
- **Impact**: low — a screen reader says "tab, 1 of 2" where arrows do nothing and no panel is tied to the tab.
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/Tabs.tsx:7-14` (used by the hosted list and by the app)
- **Problem**: `role="tablist"` with `role="tab"` buttons, all in the tab order, no ArrowLeft/ArrowRight, no
  `aria-controls`, no `role="tabpanel"` on what they switch.
- **Plan**:
  1. Arrow keys move and select; only the selected tab has `tabIndex={0}`; callers wrap the content in a `role="tabpanel"`
     labelled by the tab (or, simpler, drop the tab roles for `aria-current` buttons). Reuse PAGE-03's hook.
- **Check**: VoiceOver on the list: arrows switch between "Matchs" and "Saison".

## PAGE-18 The court's marks use the browser's own tooltip

- **Type**: maintainability
- **Impact**: low — the dots, zones and arrows of "Le terrain" show a native tooltip (another look, late, none on touch) where the rule is `Tip` only.
- **Effort**: M
- **Confidence**: read
- **Where**: `web/src/components/CourtChart/SvgButton.tsx:20`, `web/src/components/CourtChart/Arrows.tsx:56`, `web/src/components/Header/TeamLegend.tsx:17`, `web/src/components/Tip.test.ts:24`
- **Problem**: `<title>{label}</title>` inside the SVG gives the native tooltip the convention forbids; `Tip.test.ts`
  only looks for a `title` attribute (`node.name.getText() === 'title'`), so an SVG `<title>` element passes.
- **Plan**:
  1. `SvgButton` names itself with `aria-label` and drops `<title>`; one shared tooltip for the court (a single `Tip`
     anchored on the hovered or focused mark) so hundreds of dots do not each mount one (see PAGE-07).
  2. `Tip.test.ts` also refuses a `<title>` JSX element outside `<svg aria-hidden>` icons.
- **Check**: `npm test -- Tip`; hover a dot: the app's tooltip.

## PAGE-19 Copying a player's card answers nothing, done or failed

- **Type**: UX
- **Impact**: low — "Copier" in the card's menu closes with no sign; a refused clipboard fails silently, against "an action never fails silently".
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/MyMatch/PlayerCard.tsx:75-83`
- **Problem**: `const copy = () => void navigator.clipboard.write([...]).catch(() => {});` and
  `toBlob((blob) => blob && then(blob))`: no success state, no `ErrorNote`.
- **Plan**:
  1. A `copied | failed | null` state: the download button's row shows a check for two seconds, or an `ErrorNote`
     (`explain`) under the card.
- **Check**: copy with the clipboard permission denied: the note shows.

## PAGE-20 The report flag has no loader while it sends

- **Type**: maintainability
- **Impact**: low — the one-tap "Signaler" swaps its text for "Envoi…" with no spinner, unlike every other async button.
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/Watch/Feedback.tsx:108-110`
- **Problem**: a plain `<button disabled={state === 'sending'}>` with a text state; the form's own submit below uses
  `Button busy`.
- **Plan**:
  1. Show `LoaderCircle` in place of the flag icon while `state === 'sending'` (the button's look stays its own).
- **Check**: throttle the network, tap the flag: a spinner turns in it.

## PAGE-21 The TV score card bounces in whatever the reduced-motion setting

- **Type**: accessibility
- **Impact**: low — one overshooting slide per rally in TV mode for a viewer who asked for less motion.
- **Effort**: S
- **Confidence**: read
- **Where**: `web/src/components/Watch/Overlay.tsx:314`
- **Problem**: `animate-in ... duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] fade-in slide-in-from-bottom-8`
  without `motion-reduce:animate-none`, which the phone sheet has (`PlayerSheet.tsx:57`).
- **Plan**:
  1. Add `motion-reduce:animate-none` there.
- **Check**: emulate `prefers-reduced-motion: reduce`: the card appears in place.

## PAGE-22 A set to 15 gets no set point and no "moments chauds"

- **Type**: bug
- **Impact**: low — only where a deciding set is played to 15 in a match of fewer than five sets: the commentary announces no set point at 14, "Dans les moments chauds" and the "égalité tardive" highlight never fire.
- **Effort**: S
- **Confidence**: read (the owner's two matches are three sets to 25: not hit today)
- **Where**: `web/src/components/Watch/helpers/commentary.ts:27-28` and `:87`, `web/src/components/Stats/helpers/strengths.ts:22`, `web/src/components/MyMatch/helpers/myMatch.ts:10`
- **Problem**: `SET_AT = 25`, `LAST_SET_AT = 15` only when `r.set === sets && sets >= 5`; `LATE_SCORE = 20` and
  `LATE = 20` are fixed. The story already adapts: `setPoints(all, Math.min(SET_POINTS, Math.max(...final)))`.
- **Plan**:
  1. A shared `setTarget(final)` in `web/src/helpers/plays.ts` (`Math.min(25, Math.max(...final))`), used by the three:
     set point at `target - 1`, late from `target - 5`.
  2. Tests on a 15-12 set in each helper's test file.
- **Check**: `npm test -- commentary strengths myMatch`.

## PAGE-23 The data's shaping is untested and written twice

- **Type**: tests
- **Impact**: low — every statistic starts from `lib/match.ts` (13.5 KB, no test); the season rebuilds its contacts with its own copy of the rule.
- **Effort**: M
- **Confidence**: read
- **Where**: `web/src/lib/match.ts:259-276`, `web/src/components/Season/helpers/season.ts:141`
- **Problem**: the page: `g: (hasTeams && c.team) || (c.side === 'left' ? 1 : 2)`; the season:
  `g: c.team ?? (c.side === 'left' ? 1 : 2), player: null, name: null`. The module reads `window.MATCH` at import, so
  nothing of it is tested; among the hosted pages' helpers the others without a test are small
  (`Stats/helpers/best.ts`, `Season/helpers/loadMatch.ts`, `helpers/theme.ts`).
- **Plan**:
  1. Extract a pure `shape(data)` (rallies, contacts, sets) in `lib/match.ts`, exported; the module's constants call it,
     `buildSeason` too.
  2. `lib/match.test.ts`: a contact's team from `team` then from its side, `left` and `flipped`, contacts filed in their rally.
- **Check**: `npm test -- match season`.

## PAGE-24 The player's loop runs at every frame while the video is paused

- **Type**: performance
- **Impact**: low — 60 callbacks a second for as long as the page is open, each reading `currentTime` and writing the video's style and volume; battery on a phone left on the page.
- **Effort**: M
- **Confidence**: suspected (the loop is read; its cost while paused is not measured, and it may be negligible)
- **Verified** (21 Nov, headless Chrome): measured and negligible. With the video paused, 5 s of idle cost 15 ms of script on a phone throttled 4x (8 ms on a desktop). Not worth doing; kept so nobody measures it twice.
- **Where**: `web/src/lib/player.tsx:214-256`
- **Problem**: `tick` ends with `frame = requestAnimationFrame(tick)` unconditionally; it starts when a media is set
  and stops only on unmount.
- **Plan**:
  1. Measure first (performance panel, paused, 30 s). If it shows: run the loop between `play` and `pause`/`ended`,
     plus one `tick` on `seeked` and `timeupdate` so a paused seek still publishes the time and the fade.
- **Check**: paused, the performance panel shows no animation frame from `player.tsx`.

## PAGE-25 The season tab downloads every match's whole data, one after the other

- **Type**: performance
- **Impact**: low — 53 to 64 KB gzip a match today, in sequence (each script writes the same `window.MATCH`): fine for a few matches, seconds on a phone past twenty.
- **Effort**: M
- **Confidence**: read (sizes measured on the two matches; no timing on a phone)
- **Where**: `web/src/components/Season/helpers/loadMatch.ts:24-33`, `web/src/components/Season/Season.tsx:149-173`
- **Problem**: `const data = queue.then(() => read(m));`: a chain of script loads, each a full `data.js`, to compute a
  few numbers a player.
- **Plan**:
  1. Not before the list is long: then have `matches.build` write each match's season lines into `matches.js` (the same
     `lines`/`strengths` maths, so written by a Node step of the web build or kept in the browser and cached in
     `sessionStorage` by `v`). The cheap first step is the cache: `sessionStorage` keyed by `path` and `v` holding the
     `buildSeason` inputs.
- **Check**: the season tab's second opening in a session makes no request.

## Looked at, fine

- `cn` 0.5.0: the shadcn-ui package, imported once (`lib/utils.ts`); every dependency of `package.json` is imported; `@base-ui/react` only by the review's combobox, outside both hosted graphs.
- No unreached module: every non-test file under `web/src` is in the graph of one of the five entries (`sourceGraph`).
- `online.ts` and `online.test.ts`: the hosted graphs (132 and 36 modules) reach no `LOCAL` module; `Progress/` and `VideoPassword.tsx` are app-only.
- Bundles as committed: page 741 KB (230 KB gzip), its sheet 85 KB (16 KB), `scene3d.js` 612 KB (153 KB) loaded on the first 3D view only, list 476 KB (150 KB); both locales cost about 6 KB gzip each in the page, not worth a split.
- System fonts only, no web font; the poster and the card pictures load lazily; `?v=` on every unhashed script (`web.version`), `.gz` copies and the caching described in `docs/hosting.md`.
- Link previews: `matches.share` writes the `og:*` tags and a drawn `preview.png` (teams, score, date: no footage); pages carry `noindex`.
- Locales: same keys in `fr` and `en` (`locales.test.ts`), every plural has `_one` and `_other` but four `myMatch` texts only called from 3 or 5 up; the texts with `{{count}}` and no plural are all called with counts of 2 or more; `ofName`/`ofTeam` differ by design.
- Numbers and dates go through `formatters(lang)` (`Intl`); playlist titles are functions of `t`, so a language switch renames a playing list; the theme and the language survive a blocked `localStorage`.
- Text contrast of the theme tokens, computed: `muted-foreground`, `link`, `destructive` and `primary-foreground` on their backgrounds are 4.9:1 or more in light, dark and Haikyu.
- `meanServeRating`, `meanRating`, `meanAttackRating`, `meanDigRating`: denominators are the rated touches, null when none; `attackRating` already skips non-touches; `mvp` cannot divide by zero after its time filter.
- `insights`, `strengths`, `toWorkOn`: gaps against the rest of the team with minimum samples; `f.pct(n / of)` only with `of > 0`.
- `setScores`, `setsWon`, `pointSplit`; the season's `setScores` agrees with the header's on given and estimated scores.
- Story: `runs`, `comebacks`, `setPoints` (adapts to the final score), `breaks`, the curve's placement; trophies' ties and minimums.
- Coach: `lostOn`, `things`, `setters`, `jumpers`, `defenders`, `receivers`, the placement and reception cards (one named player by choice, as the rule allows).
- "Mon match": `measures` (medians from 3 or 5 tries), `highlights`, `tops`, `duos`, `serveRun`; an unknown remembered player falls back to the picker.
- Season: `seasonTeams`, `matchesOf`, `values` (no division by zero under `MIN_SAMPLE`), `risesOf`, the failed load's retry and its loading text.
- Court chart: zones' shares (`n / shown.length` with `n > 0`), the dots kept out of the tab order, empty states; histogram and timeline scales (`Math.max(1, ...)`).
- Empty data: `hasTeams` and `known.length` guards, `rallies[0]` fallbacks in `write_site`, spans and ticks with no rally.
- Player: playlists, loop, fades, the phone sheet's opening rule, `useVideoTime` selectors returning primitives, `Clock` on the page without footage, `useUnstuck`, `Preload`.
- Listeners and loops cleaned up: `useAutoHide`, `useHandZoom`, `useFullscreen` (iPhone's `webkitEnterFullscreen` too), `VideoError`, `useListTab`, `Scene3D`'s dispose (`forceContextLoss`) and observers, `canDraw3d`'s single probe.
- Video helpers: `cameraAt`, `zoomOn`, `throughCut`, the seek bar's helpers, `sceneAt`, `flight`, `director`, `lineCall`, `score`.
- Conventions: no `title` attribute (`Tip.test.ts`), failures through `ErrorNote`, no `window.confirm`, `Button busy` on the password form, `Hint` behind info icons, the season's chips on `Tip tap`.
- Reduced motion: smooth scrolls, `.flight-flow`, `.progress-slide`, `.sparkle` and the phone sheet all honour it.
- `VideoChoice`'s password flow: fingerprint only, cookie on the site's folder, a refused key cleared, "no answer is no wrong password".
