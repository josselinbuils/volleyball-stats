# The match page

What the generated page shows, section by section. Every number and chart element replays its
moments.

- [Replay](#replay)
- [Mon match and L'histoire du match](#mon-match-and-lhistoire-du-match)
- [Les trophées](#les-trophées)
- [Mode TV](#mode-tv)
- [Le coin du coach](#le-coin-du-coach)
- [Statistics](#statistics)
- [Display](#display)
- [Change the page](#change-the-page)

## Replay

- The match's title and date head the page.
- Every number and chart element plays its moments in the video or on the animated court.
- Above the video: the set and its score (estimated, or the final score you gave once the set is
  over; nothing said in a set whose rallies add up to its final score, `exactSet`). A set's final score is the one given,
  else its counted one once every rally of it is checked in the review (`web.settled_scores`): no "(estimé)" then. During a timeout, "Temps mort" and its team over the video and beside the court; in TV mode its card, the
  rally before it held 3 s for it.
- The video's bar: the timeline on its own row, as wide as the video; under it play, the time, 10 s back and forward, then
  the commentary, the sound, the options (⚙: "Vidéo augmentée", "Ralentir à chaque touche", "Rejouer
  l'échange en boucle", each named and ticked) and full screen. "Ralentir à chaque touche" (kept in the browser) slows it to 0.5× around each touch only (`helpers/slow.ts` `PAGE_SLOW_RATE`; the review's clips 0.25×, to answer). The video zooms by itself, always (no switch since 16 Nov: the owner's call), framing the
  players as the review's (`framing.py`'s views: during an exchange one a second, of the players around it), widening only
  to keep the ball in, the view easing there by a spring (`framing.camera`); between rallies the whole picture, the
  server's view 3 s before the serve (`SERVE_LEAD_S`, 15 Nov; [benchmark](../benchmarks/framing/README.md)). The hosted
  copies come cut by that camera from the 4K source (`match.zoomed`, [hosting.md](hosting.md)), the page drawing on them by
  it (ball.js's `camera`, `helpers/zoom.ts` `cameraAt`, `throughCut`); on this machine (the review) the page zooms the
  source by the same camera, and so copies made before 16 Nov. A close call's zoom springs over it. Playlists and the loop fade through black (0.3 s, picture and sound)
  around each jump. A wait for data 2.5 s without more loaded reloads the copy where it stood, its play and speed kept,
  each try twice as long after the last up to 20 s (`useUnstuck`; a request held by the server, 15 Nov: back in 3 s; asking
  again for the same moment waited on the stuck request). One hidden copy of the video, kept for the whole playlist, loads the next 3 clips' starts one after another, once its first clip has started, each until the browser can play it; not on a page served from this machine (the review, or opened from the disk). A spinner shows over the picture while the video waits for its data over 0.3 s; the seek bar
  shows in a lighter line what the browser loads from where the video stands (the rallies in yellow on it, as in the review's video, brighter where loaded), and in a playlist only what it holds of
  the clips to play: on a fast network it loads up to 70 s past each one, which the player jumps over (what it loaded
  once elsewhere may be gone). Read every 0.5 s and at each jump (`video.buffered`). Chromium reports
  each loaded byte at its share of the file, off by up to 65 s on the copies, read back through each file's own index
  (a point every 10 s, `web.frames_index`), beside the exact seconds where each copy stood: the playing copy's range
  around it ends at the lesser reading; the hidden copy's own downloads are told by growing while it stands there and
  starting, read back, at its keyframe (`seekBar.isDownload`). Against the bytes the network delivered (headless Chrome,
  on the host and locally, 720p and AV1 copies, early and late in the match, plain play and jumps, playlists of rallies
  and of touches): each part within 1 s of what is loaded; loaded parts drawn late or short in 3-13% of samples, up to 5 s.
- "Vidéo augmentée" (`Watch/Overlay.tsx`, `helpers/overlay.ts`; on unless turned off, kept in the browser) draws on the
  video what the pipeline knows, as the films show it: the ball's trail over its last 0.5 s, as long as the ball is
  fast, warm with a soft glow; the score in the upper left corner as the films' timing tower (`Tower`: teams, points,
  set; the point just won gold 1.5 s; on a narrow video the teams' colours alone; the playlist's title goes below it);
  and a card in the lower left corner ("Signaler" and the court's inset hold the others) for each measured serve's
  speed (with a gauge) and attack's speed (with a gauge, its height and "Détente" below when measured), else its
  height ("Détente" below when measured), from the serve's hit plus 0.15 s or the attack's hit, until the next card,
  2.4 s at most (`statCards`). The films' card (`film.telemetry`): slanted dark panel, red edge, the number slamming in
  (`outBack`) and counting up to gold over 0.55 s, sized by the picture's width (`cqw`) up to 80rem: in full screen on a
  1920 px screen two thirds of the whole width's size (the owner, 15 Nov: that too big, 56rem too small), placed on the picture, not its black
  bars. All on the video's clock: paused,
  it shows that moment. Names at each touch were tried and dropped (the owner, 15 Nov). A close call (`helpers/lineCall.ts`, 15 Nov):
  a rally ending on the ball landing within 0.4 m of a line on the other side from its last touch, or any such landing the
  review marks as a wrong call, zooms 2.5 times on the bounce (from 0.6 s before it to 2.2 s after, where `ball.js` sees the
  ball then) and shows "Dedans" or "Dehors" at the bottom's middle (its right corner on a narrow video) for 2.4 s, the
  measured mark against its line drawn from above, and "Erreur d'arbitrage" on a wrong call. In or out is told by who won
  the point (the other team on a wrong call), not by the measure: the mark is drawn only where it says the same, and a close
  landing where it does not is left out (13 of the 17 landings within 0.5 m on the three matches agreed). 4, 0 and 5 calls
  on the three matches, the Le Haillan wrong call (an attack called in, 0.92 m out) among them. The films show it too. A canvas in the video's box, drawn by the zoom's loop for the frame
  on screen (`requestVideoFrameCallback`), so it moves with the zoom. `ball.js` holds the ball's place by each frame's
  real seconds (`web.ball_track`, `film.frame_times`): the camera drops 5 to 10 frames a match, a frame's number then
  runs up to 45 ms off the video, one to two balls for a fast one, and the hosted copies play 25 frames a second on the
  source's timeline. A place every 0.08 s, and the frames between where a straight line would miss the ball by 0.004 of
  the picture's width, the corners at touches: on the Avia match a line between the 0.08 s places alone misses it by
  2.6 px in 4K at the median but 60 at the 99th percentile; the corners add 11% of places (`ball.js` 246 to 305 KB, 80
  to 93 compressed). Seen on paused frames of its 720p copy at 114 s, 2658 s and 4434 s: the trail ends behind the ball.
- What plays is listed under the player (`Watch/RallyCards.tsx`, `useWatchList.ts`): the set's rallies, or while other
  moments play (a number, a chart, a trophy...) one card per moment, its touch lit among its rally's letters, under the
  playlist's title and "3 sur 10". The one playing stands out, kept in view; a card plays from it. On a phone it stands
  under the player's controls, in the sheet too. In full screen, where the bar under the player is out of sight, the
  control bar adds previous and next, and "Liste" opens the same list over the picture (`Watch/WatchPanel.tsx`); on a
  phone held upright the bar's buttons take two rows, previous, play, next, the list and full screen on the first.
- Full screen's "Disposition" (`Watch/LayoutMenu.tsx`, kept in the browser) shows the video alone, the court's replay
  beside it (under it on a screen held upright) or in its bottom right corner. The page's own replay moves there, its
  2D/3D/TV choice and 3D view kept, dark as the video around it; only full screen has a layout (the `multi-view-layout`
  branch's resizable four views were too complex).
- Beside it, the court seen from above follows the play: the players, the ball with a trail as long
  as it is fast, and a ring around the player touching it.
- Each player keeps one mark for the whole match: their number, then once named their jersey number, or without one
  their initials (two letters when two teammates without a jersey share one).
- **3D view:** a switch turns the court into a 3D scene to turn around with the pointer (three.js, in
  its own `scene3d.js` loaded only then):
  - the players as figures jumping to attack and block, each with their hair (colour, and short, mid-length, a ponytail,
    long or bald) and skin guessed from their card's picture (`likeness.py`: a human-parsing model, SegFormer trained on
    ATR, MIT licence, downloaded on first use; [benchmark](../benchmarks/likeness/README.md)), a man's or a woman's figure
    as set in the review's Names tab (a woman's short hair drawn as a long bob, to mid-neck); only on a page with the video (the review, a local one, the hosted one behind its password), never for a blurred team:
    elsewhere made-up looks;
  - the ball's height reconstructed, each flight rising as high as gravity requires for its duration,
    and over the net when it crosses it, each touch at a typical height for its action.

## Mon match and L'histoire du match

"Mon match": a viewer picks their name (remembered on that device) and sees what they did, their touches
to replay, their best points, their run on serve, who sets whom and their card to save. Their measures: the fastest
serve and the median speed (from 3), the fastest attack and its median speed (from 5: spikes and tips mix), the median hitting height and the median "Détente" (from 5 measured jumps), each median named so on the page (the owner, 15 Nov: a plain number reads as a best). "L'histoire du
match": the score gap rally by rally, a few plain sentences per set and the key moments (runs of 5 points,
deficits of 4 caught up, set points saved, the longest rally, a timeout after 3 points in a row against its team that
wins it 4 of the next 6), each replaying; the timeouts (`timeouts.py`, the review's) as dashed lines on the curve, each
replaying the 6 points after it. Both follow the set filter.

## Les trophées

Awards for what players did well, never for faults, from a minimum so that none goes to next to nothing;
a tie shares one. Each replays its moments. Most touches, winning attacks, winning blocks, aces, digs, sets
and perfect receptions, the longest run on serve, the fastest serve, the fastest attack ("Le Canon", from 5 measured), the highest jump ("Le Ressort", from 5
measured jumps; each speed and jump trophy a record, the best single value: the owner, 15 Nov; the review asks to confirm each record;
a reading far from its player's others or from everyone's is left out of the whole page, trophies and cards included: `web.unlikely`), the setter and attacker with the most winning attacks, and the longest rally.

## Mode TV

The view's "TV" switch films the match like a broadcast, in a 3D model of the first match's gym, with no footage, so the
whole match can be public without anyone's consent. "Regarder le match" plays every rally of the set shown, one after another.

- **Ball:** after a rally's last touch in the air (half the rallies: no floor contact seen), it falls to the floor: a point
  into the other court (an attack 5 m past the net in 0.5 s, a block 1.5 m, a serve 6 m), an attack or serve fault past
  the end line, a ball in the net straight down, else on 1.5 m the way it came (`flight.fallAfter`). Each flight is an arc under gravity between two touches, each touch placed in 3D where the path best matches
  the ball in the video (`ball3d.py`, `ball3d.js` on the page, loaded with the 3D view). It needs the camera's lens: without
  it, typical heights per action stay. `benchmarks/ball3d/bench.py` scores it.
- **Director** (`Watch/helpers/director.ts`, a function of the time alone, so pausing and jumping just work): behind the
  server, then a wide shot following the ball, a cut to the net's side from each set to the attack.
- **Players** (`Watch/helpers/pose.ts`, in the plain 3D view too): they run as fast as the tracking says and make each
  action's gesture around its real contact: jumping to the ball's height (an attack with its jump measured, `air`, from its
  real takeoff to its real landing), lunging up to 1.2 m towards it when it is within 2.5 m. The gestures are
  illustrative, not the player's own technique. A serve starts in the server's hand.
- **Replays:** in the real pauses between rallies, slowed down, through the eyes of who scored: aces, winning blocks, attacks
  ending a long rally or a set, and one winning attack in four otherwise.
- **Commentary** (`Watch/helpers/commentary.ts`): generated from the touches, in French then English, shown as captions, naming who
  did something, who scored and who gave a point away.
- **Voice:** a script for speech (`speech.py`), in French, calling every named touch, in full when there is room before the next and
  else by the player's name, each a different way from the last of its kind (`Ways`), the score saying who took the lead,
  levelled or pulled away. Between rallies, once the end is said and before the next serve, a remark (`Story`): a set's
  summary, a comeback, a streak's end, a player's milestone (second ace, fifth attack point), the match's fastest serve or
  attack, a streak, the longest rally; a welcome, a goodbye, and each timeout. A joke now and then (at most every 8 rallies
  and once per timeout, never twice in a match, never naming a player): about 15 a match. A line is written as the page
  shows it ("ace", figures, "km/h") and spelled for the voice; the index keeps those words, which the TV view shows in French
  with the recorded voice (the page's own lines otherwise). Spoken by a voice generated on this machine: Kokoro,
  the SIWIS voice at 1.2 times its speed. Heard with the video and the court's replay in any view, by the microphone of the
  video's bar (`Commentary.tsx`): on at first where the match's recorded voice speaks the page's language, the choice kept in
  the browser; the match's sound drops to 30% under each line, back after 0.8 s of silence (the player's loop sets the volume,
  `setUnder`). Muting the video mutes it. `ponytail:` iPhones ignore a video's volume: no ducking there (Web Audio on the
  video would need it served with CORS). `uv run --group voice python -m volleyball_stats.voice outputs/matches/MATCH` makes the audio missing
  in `outputs/matches/MATCH/voice/` (`spoken.json` there spells names for it, never committed), from the review's page, else the built one;
  each upload runs it first. A build keeps the lines still true of the match. Without audio, or in English, the browser's voice.

## Le coin du coach

Team by team, following the set filter. Advice for the team: no player is named for a fault or a weak number, but in
the reception and defence placements and the attack jump (the owner's call).

- what cost the team the most points (each lost rally goes to one cause: its own last touch's fault, on the teammate's
  touch the review puts it on when it does, or the other team's last touch scoring), with the other team's count and a tip;
- who sets whom: each setter from 5 sets and who attacks right after, the winners in green;
- "Le saut d'attaque": each attacker with 5 jumps measured on a teammate's set (`jumps.py`, `benchmarks/jumps`) and a
  tip from their medians: jump later (the contact 120 ms or more past the flight's top) or earlier (as much before it),
  up rather than forward (carried over 0.8 m towards the net); the row replays those attacks. No run-up tip: a player's
  run-up changes too much from one match to the next (the owner's call, 7 Nov);
- "Placement en réception": a reception system with 3 receivers and, if picked, a player. One card, its court showing
  the system's receiving spots (green dots) and the zone at the net where the other three stand. At each serve with the
  six players seen (`web.received`, their places at the hit), the three nearest the net stay there and the others go to
  the spots by the least total distance (`reception.receivers`). With a player, each spot they took from 3 serves adds
  their usual place and an arrow, and their place at the net a dot alone; the card replays the serves they stood 1 m
  off a spot. The systems differ by the middle receiver's depth only, the side ones where the owner's team stood on 2
  Nov, centred (5.5 m off the net, 2.5 m aside): as deep as them in a line, 1 m deeper in an arc (theirs), 2 m in a V.
  Sources give shapes, not depths: those depend on the serve expected; the owner's team stood 0.3 m deeper against the
  fastest third of serves. A depth picker moves the receivers 1 m shorter or deeper, kept out of the 1.5 m by the net
  and the last metre before the end line, where few serves land (`reception.deeper`).
- "Placement en défense": a defence system, the setter's position (at 2, the team's, or at 3) and, if picked, a player
  (nobody at first). A card per side the other team attacks from (left, middle, right) and block (one blocker, then
  two), its court showing the attacker 1 m off the net, 3 m aside or in the middle (`defense.ATTACKERS`), and every
  position's spot in the system against them (green dots, numbered, `defense.table`). With a player, each position they
  defended there from 3 attacks adds their usual place at the hit (a dot in the team's colour, numbered too) and an
  arrow to its spot where the two dots part; the card replays the attacks they stood 1 m off. The systems: the perimeter
  the owner's team plays (its corners 2 m inside the sidelines 6 m off the net, 6 at 7 m: the owner's), Laëticia's
  version of it (a teammate's diagrams: the block inside the attacker, the off-blocker in the middle short, the line
  digger deep on the line, the cross digger forward, 6 deep toward the cross), the middle up and the rotation (AVCA's
  descriptions, distances approximate). At each attack, the players within 1.2 m of the net make a single block (by 3,
  the middle, the setter at 2; the page swaps it with the outside on the attack's side, who then blocks, the setter at 3
  covering behind) or a double one (3 and 2, or 4 and 3) in front of the attacker; the perimeter's spots go to the
  defenders by the least total distance: a position is the perimeter spot defended, not the rotation's, the same in
  every system, which moves its spot only. `benchmarks/defense/bench.py` scores the systems.

## Statistics

The "Statistiques" table gives, team by team, each player's and the whole team's:

- touches;
- serves: aces (nobody touches it, or the first receiver loses it with no touch after), faults, and a
  rating out of 5 from the other team's reception: 5 for an ace or a reception missed, 4 when the
  reception is poor or sent straight back, 3 when it is good, 2 when it is perfect, 0 for a fault;
- receptions and digs: faults (an ace counts against the receiver nearest to where it landed), and
  those after which the team did not attack;
- receptions: a rating out of 5 from where the next touch is played: 5 within 1.5 m of the setter's
  target (1 m off the net, between zones 2 and 3), 3.3 within 3 m, 1.7 further or sent straight over
  the net, 0 for a fault;
- sets: attacked right after, assists (a teammate's winning attack right after), faults;
- attacks: winning, faults, and from 5 attacks a rating out of 5: 5 winning, 4 in play with no counter-attack, 2 with one, 1 blocked,
  0 another fault;
- free balls: faults;
- a fault the review puts on a teammate's earlier touch (a bad set, a bad reception: [review.md](review.md), "Stats") counts in
  that touch's faults, graded 0, and not in its own touch's, left ungraded: an attack lost on a bad set is the setter's fault;
- blocks;
- digs: from 5 digs a rating out of 5, as for receptions;
- "Bilan": points, faults, and "Entre deux": the balls that landed in untouched within 2.5 m of two
  teammates about as close as each other, the pair on hover.

Its "Analyse" group lists each player's main thing to work on, its largest gap with the rest of the team, and, the rarest in their team first, two strengths at most, beside the MVP's badge:
the rates at least 20 points above the rest of their team's; how present they are for their time on the court (on every ball,
in defence); how reliable (serve, attack, few faults); tough serves; sets followed by an attack; assists, winning blocks, points when the score is
high and close, the most points in the team, and playing all around. Each is earned from a minimum, from 5 attempts on each side
for a rate, so a player can have none.

"Mon match" shows the picked player's FIFA-style card, with their picture from the
video (`site/players/`: the clearest moment of their longest stretch on court, 3 wide for 4 tall).

Without player tracks, everything counts each side of the net instead of each team.

## Display

- **Team colours:** everything is split by team, in each team's jersey colour. A colour too close to
  the background is outlined in grey; Team 2's changes when the two look alike.
- **Set filter:** with several sets, one filter at the top of the screen shows a single set. Every
  section follows it, and the video's timeline then covers that set only.
- **The bar at the top:** it stays on screen while the page scrolls, with the set filter and a link to each section, the
  one on screen marked (`Header/StickyBar.tsx`); on a phone the links take a row of their own, scrolling sideways.
- **Phones** (under 640 px): the sections in the same order as on a computer (the owner's, 15 Nov). Something played while the replay is out of sight
  opens the video and court in a sheet from the bottom (`Watch/PlayerSheet.tsx`); "Fermer" stops it, the page where it was.
  The statistics show one group of columns at a time, picked above the table ("Temps" with "Touches"); the score curve
  has a row per set, on one scale; "Sur le terrain" opens on "Par zone". The score bar above the replay puts the set and "Score estimé" on
  a line above the teams, the court's header leaves the last touch to the bar under the court, the trophies stand two a
  row.
- **Touch screens** (a coarse pointer): the texts say "Appuyez" where a mouse clicks or hovers (their `touch` versions in
  `locales/`); a tap on a player of the court replay shows their name, the next tap elsewhere hides it. Small controls get a
  tap area of at least 44 px, unseen (the `tap` utility in `index.css`); the curve's rallies and timeouts stay narrow,
  a rally every few pixels.
- **Theme and language:** two menus on the club's band (beside the title without one, `Settings.tsx`): the light, dark or
  automatic theme (the system's, by default) and French or English, remembered by the browser.
- **Loading:** the players' positions come in one file per 5 minutes (`positions/N.js`), loaded as the replay reaches them, the next one a little ahead; the balls dropped between two players read theirs from `data.js`.

## Change the page

The page is a React + shadcn/ui app in `web/`. Its build is committed in
`src/volleyball_stats/site/`, so processing a match needs no Node.

```bash
cd web
npm install
npm run dev      # reads web/public/data.js, copied from a built match
npm test
npm run build    # updates src/volleyball_stats/site/ and matches_site/
```
