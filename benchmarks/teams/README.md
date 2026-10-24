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
```

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
  detected one, named as in `teams.json`); changes of ends found against labelled.
- **Colour vs side**: player frames inside the rallies whose colour group plays on the side its
  group holds in that rally. Players never cross the net, so a disagreement is a colour error:
  this scores the colour alone on every track, not only the labelled sequences.
- **Tracks**: labelled tracks whose team wears their label's colour, by colour group alone and with
  the side correction of the module.
- **Attribution**: typed contacts attributed right (the attribution benchmark's `truth` and
  `detected` scores), the toucher searched among the tracks of the contact's side by
  `players.py`'s median side (today's rule), by colour group, or by team.
- **Sets**: set starts found.

## Method

1. **Jersey colour per track.** On 8 boxes spread over each track, the torso (x 30-70 %, y 20-45 % of
   the box: chest, clear of the head, arms and shorts), median pixel in Lab; the track's colour is
   the median of its 8. Frames are read in order, seeking over gaps of more than 150 frames:
   6-7 s for a 10-minute 720p clip (about 1,400 frames decoded) on the M4 Pro.
2. **Two colour groups.** 2-means in Lab weighted by track length, started from the darker and the
   lighter half by weight. Liberos and other outliers (a referee kept by the tracker, a crop
   mixing two players) join the nearer group.
3. **Side map per rally.** In each rally window, the group holding the left half (feet court x < 0)
   is the one with the most player frames on its side, counting both groups. A rally without
   players keeps the previous rally's sides.
4. **Team per track: the side corrects the colour.** A track's team is the team on its median side
   of the net in the rally it plays most frames of (else the nearest rally). Colour decides which
   team is on which side; the side decides each track. This is the deliberately simple rule for
   liberos: they wear another colour but stay on their team's side.
5. **Names.** Team 1 is the team on the left at the first rally. Each team's colour snaps to one of
   about a dozen named colours: gym footage greys and blues a white jersey (L\* 55-60, chroma
   10-15) and darkens navy nearly to black, so low chroma reads as white, grey or black, except a
   dark one with a blue cast (navy).
6. **Sets.** A new set starts when the teams change ends after at least 90 s without a rally (a set
   break lasts 3 minutes or more); a change of ends after a shorter break is the deciding set's
   swap at 8 points, in the same set. The set start is the middle of the break.

## Results

Tuning (`side_club` + `side_long`):

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

- One match, one camera, white against navy: two jerseys as far apart as they get in lightness.
  Two close colours (navy against black, red against dark red) are untested; the side map only
  needs the majority of each team's frames right, which leaves a wide margin, but nothing here
  measures it.
- One real change of ends (`side_setend`), no deciding set. The 90 s rule for a deciding set's swap
  is tested on synthetic windows only.
- The sides of a rally come from its window: a window starting during the warm-up or spanning a
  set break would be voted by the players on court then. Rallies the segmenter misses are not
  needed here, but a whole set without a detected rally would hide its change of ends.
- A side map wrong on one rally after a long break starts a set; two in a row would also flip the
  names for those rallies. Not seen on these clips.
- Tracks between rallies (set breaks, warm-ups) take the sides of the nearest rally: players
  walking to the other end during a set break can carry the wrong team on the page's replay.
- Jersey colours snap to about twelve names; the swatch is the named colour, not the measured one.
  `--teams NAME:COLOUR` sets any colour.

## Next steps

- A match with a deciding set, and one with close jersey colours, to measure the rule and the
  colour margin.
- The identity step (jersey numbers) can reuse the per-track colour to tell liberos apart.
