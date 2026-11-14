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
  over). During a timeout, "Temps mort" and its team over the video and beside the court; in TV mode its card, the
  rally before it held 3 s for it.
- The video player skips 10 s back or forward. Its "Zoom auto", on from the start where the match has views, frames the players as the review's
  (`framing.py`'s views), moving only to keep the ball in, the view easing there by a spring; a jump
  in the video cuts to its view. Playlists and the loop fade through black (0.3 s, picture and sound)
  around each jump; one hidden copy of the video, kept for the whole playlist, loads the next 3 clips' starts one after another, once its first clip has started, each until the browser can play it; not on a page served from this machine (the review, or opened from the disk). A spinner shows over the picture while the video waits for its data over 0.3 s; the seek bar
  shows in a lighter line what the browser loads from where the video stands, and in a playlist only what it holds of
  the clips to play: on a fast network it loads up to 70 s past each one, which the player jumps over (what it loaded
  once elsewhere may be gone). Read every 0.5 s and at each jump (`video.buffered`). Chromium reports
  each loaded byte at its share of the file, off by up to 65 s on the copies, read back through each file's own index
  (a point every 10 s, `web.frames_index`), beside the exact seconds where each copy stood: the playing copy's range
  around it ends at the lesser reading; the hidden copy's own downloads are told by growing while it stands there and
  starting, read back, at its keyframe (`seekBar.isDownload`). Against the bytes the network delivered (headless Chrome,
  on the host and locally, 720p and AV1 copies, early and late in the match, plain play and jumps, playlists of rallies
  and of touches): each part within 1 s of what is loaded; loaded parts drawn late or short in 3-13% of samples, up to 5 s.
- Beside it, the court seen from above follows the play: the players, the ball with a trail as long
  as it is fast, and a ring around the player touching it.
- Each player keeps one mark for the whole match: their number, then once named their jersey number, or without one
  their initials (two letters when two teammates without a jersey share one).
- **3D view:** a switch turns the court into a 3D scene to turn around with the pointer (three.js, in
  its own `scene3d.js` loaded only then):
  - the players as figures jumping to attack and block;
  - the ball's height reconstructed, each flight rising as high as gravity requires for its duration,
    and over the net when it crosses it, each touch at a typical height for its action.

## Mon match and L'histoire du match

"Mon match": a viewer picks their name (remembered on that device) and sees what they did, their touches
to replay, their best points, their run on serve, who sets whom and their card to save. Their measures: the fastest
serve and the usual speed, the hitting height and the "Détente" (their median jump, from 5 measured jumps). "L'histoire du
match": the score gap rally by rally, a few plain sentences per set and the key moments (runs of 5 points,
deficits of 4 caught up, set points saved, the longest rally, a timeout after 3 points in a row against its team that
wins it 4 of the next 6), each replaying; the timeouts (`timeouts.py`, the review's) as dashed lines on the curve, each
replaying the 6 points after it. Both follow the set filter.

## Les trophées

Awards for what players did well, never for faults, from a minimum so that none goes to next to nothing;
a tie shares one. Each replays its moments. Most touches, winning attacks, winning blocks, aces, digs, sets
and perfect receptions, the longest run on serve, the fastest serve, the highest median jump ("Le Ressort", from 5
measured jumps), the setter and attacker with the most winning attacks, and the longest rally.

## Mode TV

The view's "TV" switch films the match like a broadcast, in a 3D model of the first match's gym, with no footage, so the
whole match can be public without anyone's consent. "Regarder le match" plays every rally of the set shown, one after another.

- **Ball:** each flight is an arc under gravity between two touches, each touch placed in 3D where the path best matches
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
  else by the player's name, spoken on request by a voice generated on this machine: Kokoro,
  the SIWIS voice at 1.2 times its speed. `uv run --group voice python -m volleyball_stats.voice outputs/matches/MATCH` makes the audio missing
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
- **Phones** (under 640 px): "Mon match" comes right after the header. Something played while the replay is out of sight
  opens the video and court in a sheet from the bottom (`Watch/PlayerSheet.tsx`); "Fermer" stops it, the page where it was.
- **Theme:** a switch next to the language picks the light, dark or automatic theme (the system's,
  by default), remembered by the browser.
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
