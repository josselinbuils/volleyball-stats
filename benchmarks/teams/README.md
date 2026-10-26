# Teams benchmark

`volleyball_stats.teams` names the two teams Team 1 and Team 2 and follows which side of the net
each one plays on, rally by rally, so a team keeps its name when the teams change ends (between
sets, and at 8 points in a deciding set). It also numbers the sets. Scored against hand-labelled
jersey colours per rally: tuned on `side_club` and `side_long`, held out `side_holdout` and
`side_setend`, a clip cut around a real set end.

## Use

`match.py --players` runs it after the player tracks; alone:

```bash
uv run python -m volleyball_stats.teams data/match.mp4 outputs/match/players.csv outputs/match/rallies.csv [--out DIR]
```

writes `<video>_tracks.csv` (`track,team`). From Python, `teams.assign(video, rows, windows)` returns
the team of each track, the team on the left of each rally, each team's jersey colour and a few
player crops per team. `match.py` writes the team on the left and the set of each rally into
`rallies.csv` (`left`, `set`), each contact's team into `actions.csv` (`team`), the tracks' teams into
`tracks.csv` and the names, colours and set starts into `teams.json` (see the main README).

## Run

```bash
uv run --group bench python benchmarks/teams/bench.py side_club side_long [--sweep]
uv run --group bench python benchmarks/teams/bench.py side_holdout side_setend
uv run --group bench python benchmarks/teams/bench.py side_holdout side_setend --mixed
```

`--mixed` dresses each player of the clip's `outputs/CLIP/identities.csv` in a random shirt (9
common colours) and shorts (white, black or grey), over 5 seeds, and scores the side map again: kits
that differ within a team, as in adult leisure matches.

Each clip reads `data/CLIP.mp4`, its player tracks (`outputs/players/CLIP_players.csv`, else
`outputs/CLIP/players.csv`), this folder's ground truth, and where they exist the identity labels of
[benchmarks/players](../players/README.md) and the touchers of
[benchmarks/attribution](../attribution/README.md).

`side_setend.mp4` is 43:00-53:00 of the same match (`side_holdout` ends at 43:00), run through the
whole pipeline with the court of `side_holdout`:

```bash
uvx yt-dlp -f '136+140' --download-sections '*2580-3180' -o data/side_setend.mp4 -- bFLVvZ09YJo
uv run --group bench python -m volleyball_stats.match data/side_setend.mp4 --court outputs/courts/test.json --players
```

## Ground truth

`ground_truth/<clip>.csv`: `start_frame,end_frame,left,right,note`, the jersey colour (`white`,
`navy`) on each side of the net in each rally, read on a frame from the middle of every rally.

| Clip | Rally windows | Rallies | Changes of ends |
| --- | --- | --- | --- |
| `side_club` | [benchmarks/rallies](../rallies/README.md) ground truth | 8 | 0 |
| `side_long` | same | 9 | 0 (the 544-582 s break is a timeout: both teams huddle by their own bench and come back to the same ends) |
| `side_holdout` (held out) | same | 21 | 0 (the 230-270 s and 420-450 s breaks are timeouts too) |
| `side_setend` (held out) | the pipeline's 8 detected rallies, each checked on a frame | 8 | 1: set 1 ends at 1:05, empty court until 6:00, warm-up until 7:00, set 2 from 7:12 with the teams on the other ends |

None of the three first clips has a change of ends: at 0:00-43:00 of the source video the match is
in its first set (the teams line up at 17:30, set 1 ends at 44:05), hence `side_setend`. Its
windows are the segmenter's, so the set-2 rallies it missed are not labelled (it finds about 2 in
3 rallies on `side_holdout`); every labelled window is a real rally.

Track identities: the sequences of the players benchmark (`W*` white, `N*` navy, liberos included:
the navy libero wears white in `side_club`, black in `side_holdout`; the white team's libero wears
black), matched to the tracks by feet within 20 px, each track taking its majority label.

## Metrics

- **Side map**: rallies whose team on the left wears the labelled colour (the team's colour is the
  detected one, named as in `teams.json`); changes of ends found against labelled. With `--mixed`,
  rallies whose team on the left is the first rally's exactly when the labels say so.
- **Colour vs side**: player frames inside the rallies whose torso colour group (2-means, in the
  benchmark only) plays on the side its group holds in that rally. Players never cross the net, so
  a disagreement is a colour error: it measures how much a team's kits agree.
- **Tracks**: labelled tracks whose team wears their label's colour, by colour group alone and with
  the team the module gives.
- **Attribution**: typed contacts attributed right (the attribution benchmark's `truth` and
  `detected` scores), the toucher searched among the tracks of the contact's side by
  `players.py`'s median side (today's rule), by colour group, or by team.
- **Sets**: set starts found.

## Method

Kits may differ within a team, so a team is never a colour.

1. **Look per track.** On 8 boxes spread over each track, the median Lab colour of the torso (x
   30-70 %, y 20-45 % of the box: chest, clear of the head, arms and shorts) and of the shorts (x
   30-70 %, y 50-65 %); the track's look is the median of its 8 (6 values). Frames are read in order,
   seeking over gaps of more than 150 frames: 6-7 s for a 10-minute 720p clip on the M4 Pro.
2. **Followed tracks across ordinary breaks.** From one rally to the next, when the tracks of the
   previous rally hold 25 % or more of the rally's player frames, the rallies join a stretch, and
   those tracks tell whether the teams changed ends: most of their frames on the other side. On the
   four clips, ordinary breaks keep 35-89 % of the next rally's frames on followed tracks; the long
   ones (61 s and 64 s timeouts, the set break) 0-18 %: the players left the court.
3. **Looks across long breaks.** From one stretch to the next, each track after the break finds the
   track of the previous stretch with the nearest look. The teams changed ends when 60 % or more of
   the frames after the break matched a player of the other side: breaks without a change are the
   more common case, so a change needs a clear majority.
4. **Team per track.** A track's team is the team on its median side of the net in the rally it
   plays most frames of (else the nearest rally). Liberos and players in other kits need nothing
   more.
5. **Names.** Team 1 is the team on the left at the first rally. Each team's colour is the median
   torso colour of its tracks, snapped to one of about a dozen named colours: gym footage greys and
   blues a white jersey (L\* 55-60, chroma 10-15) and darkens navy nearly to black, so low chroma
   reads as white, grey or black, except a dark one with a blue cast (navy). With mixed kits it means
   little: `--teams NAME:COLOUR` sets it.
6. **Sets.** A new set starts when the teams change ends after at least 90 s without a rally (a set
   break lasts 3 minutes or more); a change of ends after a shorter break stays in the same set (a
   deciding set's swap at 8 points, or a team's habit at a timeout). The set start is the middle of
   the break. Teams that keep their ends between sets get no set start: `--sets` or the prompt gives
   them.

## Results

The colour groups of the previous method (2-means on the torso colour, the group holding most of a
rally's left half on the left) and the method above score the same on these white-against-navy
clips. With mixed kits, the previous method fails:

| Mixed kits, 5 seeds | Colour groups | Followed tracks and looks |
| --- | --- | --- |
| `side_holdout` side map | 57/105 | **105/105** |
| `side_holdout` changes of ends found (0 labelled) | 35 | **0** |
| `side_setend` side map | 22/40 | **35/40** |
| `side_setend` changes of ends found (5 labelled) | 12 | 4 |

Every ordinary break is decided by followed tracks (39 of 39 on the four clips), whatever the kits.
The miss is the `side_setend` set break: no track survives its 6 minutes, and one seed's random kits
leave fewer than 60 % of the frames matched to the other side. On the real kits the long breaks
score 0 % and 3 % (the two timeouts) and 78 % (the change of ends).

Real kits, tuning (`side_club` + `side_long`):

| | `side_club` | `side_long` | both |
| --- | --- | --- | --- |
| side map | 8/8 | 9/9 | **17/17** |
| changes of ends | 0 found / 0 | 0 / 0 | |
| colour vs side | 0.812 | 0.849 | 0.836 |
| tracks, colour alone | 12/15 | | 12/15 |
| tracks, with the side | 15/15 | | **15/15** |
| attribution, `players.py` sides (truth / detected) | 22/28, 20/28 | 36/42, 36/42 | 58/70, 56/70 |
| attribution, colour groups | 18/28, 17/28 | 30/42, 30/42 | 48/70, 47/70 |
| attribution, teams | 22/28, 20/28 | 36/42, 36/42 | **58/70, 56/70** |

Held out:

| | `side_holdout` | `side_setend` | both |
| --- | --- | --- | --- |
| side map | 21/21 | 8/8 | **29/29** |
| changes of ends | 0 found / 0 | **1 found / 1** | |
| colour vs side | 0.937 | 0.887 | 0.916 |
| tracks, colour alone | 15/15 | | 15/15 |
| tracks, with the side | 15/15 | | **15/15** |
| attribution, `players.py` sides | 33/42, 30/42 | | |
| attribution, colour groups | 31/42, 29/42 | | |
| attribution, teams | **33/42, 30/42** | | |
| set starts | 0:00 | **0:00, 4:06** (break 1:05-7:12) | |

- The side map is right for every rally of the four clips, on the labelled windows and on the
  pipeline's own (7, 9, 15 and 8 detected rallies, false ones included). On `side_setend` the
  white team is Team 1 on the left for the 3 rallies of set 1, then on the right for the 5 of set
  2, and set 2 starts in the break.
- Colour alone is wrong for 3 of the 15 `side_club` tracks: both liberos (W3 in black, N4 in
  white) and N6, a navy player whose long white arm sleeve covers the chest crop. On
  `side_holdout` the navy libero wears black and joins the navy group: 15/15. Across all player frames the colour agrees with
  the side 84 % (tuning) and 92 % (held out) of the time; the rest is mostly liberos.
- With the side correction every labelled track has its team, and attribution searching the
  toucher by team gives exactly today's scores: within a set a track's team is its side. Searching
  by colour group instead loses 10 tuning contacts and 2 held-out ones, the liberos' touches.
- Sweep (`--sweep`, tuning clips, colour vs side): 2, 4, 8 or 16 boxes per track and four torso
  boxes from x 35-65 % y 25-40 % to x 20-80 % y 10-60 % all score 0.817-0.868 with no trend, and none
  changes the side map or the tracks with the side. The defaults (8 boxes, x 30-70 % y 20-45 %)
  stayed.

## Limits

- One match, one camera, white against navy. Mixed kits are simulated: random colours per player of
  the pipeline's identities, whose errors give one player two kits now and then.
- A long break where no track survives rests on the looks alone: torso and shorts colours, close to
  a coin flip when kits are mixed and alike (one miss in 5 seeds). The identity step's re-ID
  embeddings would tell players apart better.
- A wrong decision at a break flips the team names of every rally after it, until the next wrong one.
- One real change of ends (`side_setend`), no deciding set and no change at a timeout.
- The sides of a rally come from its window: a window starting during the warm-up or spanning a
  set break holds the players on court then. Rallies the segmenter misses are not needed here: their
  break is just longer.
- Tracks between rallies (set breaks, warm-ups) take the sides of the nearest rally: players
  walking to the other end during a set break can carry the wrong team on the page's replay.
- Jersey colours snap to about twelve names; the swatch is the named colour, not the measured one.
  `--teams NAME:COLOUR` sets any colour.

## Next steps

- The first ASPOM match: real mixed kits, and changes of ends at timeouts if the teams make them.
- If long breaks fail on it: compare the players' re-ID embeddings instead of their colours.
