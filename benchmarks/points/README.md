# Points benchmark

`volleyball_stats.points` tells who won each rally and keeps the running score of each set, from how
the rally ends and from who serves next. Scored against hand-labelled winners: tuned on `side_club`
and `side_long`, then run once on the held-out `side_holdout` and `side_setend`.

## Run

```bash
uv run --group bench python benchmarks/points/bench.py side_club side_long [--verbose]
uv run --group bench python benchmarks/points/bench.py side_holdout side_setend
uv run python -m volleyball_stats.points outputs/VIDEO --fps FPS --court COURT_JSON
```

The bench reads each clip's ball track, the jersey colour on each side of the
[teams benchmark](../teams/README.md) and, where they exist, the labelled contacts of the
[contacts benchmark](../contacts/README.md); it runs `rallies.py`, `contacts.py` and `actions.py`
itself (relances left out: they do not change a winner), at 29.97 fps with the net at x=612, on the
court of [benchmarks/court/ground_truth/side_club.json](../court/ground_truth/side_club.json) (same
camera for the four clips). The CLI reads a match's outputs (`match.py`) and writes `points.csv`:
each rally's server, winner, reason and the score after it.

## Ground truth

`ground_truth/<clip>.csv`: `start_frame,end_frame,set,server,winner,end,note`, server and winner by
jersey colour (`white`, `navy`; white is Team 1, on the left at the first rally, in all four clips),
`end` how the rally ended: `in` (the ball lands in the loser's court), `out` (the last touch sends
it out), `net` (into the net), `fault` (a whistled fault the ball's path does not show), empty when
not checked.

| Clip | Rally windows | Rallies | in / out / net / fault |
| --- | --- | --- | --- |
| `side_club` | [rallies](../rallies/README.md) ground truth | 8 | 4 / 2 / 1 / 1 |
| `side_long` | same | 9 | 5 / 2 / 2 / 0 |
| `side_holdout` (held out) | same | 21 | 7 / 6 / 5 / 3 |
| `side_setend` (held out) | the pipeline's 8 plus 2 it missed | 10 (4 in set 1, 6 in set 2) | 4 / 1 / 0 / 1, 4 unchecked |

Labelled from the video. The winner of a rally is the team serving the next one (the sideout
rule), read from the server's end on the frames of the next serve; each rally's end was checked
against it on the rallies benchmark's notes and the ball track, and on crops of the video where they
disagreed. The last rally of each clip and of set 1 of `side_setend` are labelled from their end
alone. Found on the way:

- 5 whistled faults the ball's path does not show, or contradicts: `side_holdout` 2551, a low
  serve landing just past the net, yet the receivers serve next; `side_setend` 16518, a fault
  whistled on navy's attack while white digs, the second referee pointing to white.
- 5 balls the rallies notes describe as hitting the floor land out, at the far ends, the far
  sideline or past the right end line: the next serve says so (`side_club` 0, `side_long` 13514,
  `side_holdout` 9007, 9616, 15349; 9616 could also be a fault, the next serve only gives the
  winner).
- `side_long` 15809: the serve hits the net and falls on the server's side at 529.9 s; the rallies
  ground truth ends the rally at the whistle, 6 s later, after the ball was rolled under the net.
- `side_setend`: 2 rallies `rallies.py` misses (35.2 s, a white ace; 593.3 s, a reception shanked
  out as the clip ends, before any whistle). The other gaps between rallies hold substitutions, a
  timeout and the set break, checked on 1.5 s contact sheets.

Limits: one annotator; the sideout rule as the main evidence (a replayed rally would break it, none
seen); scores start at 0-0 at each clip's first rally, the clips starting mid-set.

## Method (`points.py`)

1. **End of rally** (`side_lost`), on the rally's typed contacts and net crossings. The last touch
   is the last contact that is neither `floor` nor `net`. If a floor contact follows it, its floor
   projection decides: within 1 m of the net the side that sent the ball there loses, in the court
   (lines in, 0.3 m margin) the side it lands on, out the side of the last touch. Without one: a
   trailing touch within 1 m of the net (the ball in the net, or a block; the camera stands in the
   net plane, so a ball at the net projects there whatever its height) loses for the side that sent
   the ball; a ball that crossed after the last touch was not returned (the other side loses); one
   that did not cross loses for the side of the last touch.
2. **Next serve**: the side of the next rally's contact typed `serve`, in the same set.
3. **Combined** (`combine`): agreeing rules decide. When they differ and the next serve comes within
   25 s of the rally's end, the next server wins: no rally fits in so short a gap (the shortest
   between two rallies is 12 s on the tuning clips, the longest 51 s across a timeout). After a longer
   gap a rally was likely missed: the end rule keeps this rally, and the missed one counts for the
   next server. Without an end-of-rally winner, the next server.
4. **Score**: per set from 0-0, sets from `teams.py`'s set starts. The final scores the user gives
   (`scores` in `teams.json`, team 1 first, e.g. `["25-21", "18-25"]`, asked at the naming step or
   passed to `teams.settle`) give the drift per set (`points.set_drift`): estimated minus given.

Constants, each the middle of a plateau on the tuning clips: net margin 0.75-1.5 m, in-margin
0-0.6 m.

## Results

Winners right out of every labelled rally. `labelled`: labelled windows, contacts and types (the
rallies the contacts benchmark labelled); `detected`: `contacts.py` and `actions.py` in the labelled
windows; `pipeline`: `match.py`'s windows, contacts and crossings (`match.rally_windows`, with the
players of `outputs/players/CLIP_players.csv`, else `outputs/CLIP/players.csv`), a labelled rally
without a window counting as wrong. In brackets, rallies with an answer.

| Contacts and windows | Rule | Tuning (17 rallies) | Held out (31 rallies) |
| --- | --- | --- | --- |
| labelled | end of rally | 12/12 | 6/7 |
| detected | end of rally | 16/17 | 18/31 (30) |
| detected | next serve | 15/17 (15) | 24/31 (24) |
| detected | **combined** | **17/17** | **28/31** |
| pipeline | end of rally | 16/17 (16) | 13/31 (20) |
| pipeline | next serve | 14/17 (14) | 14/31 (16) |
| pipeline | **combined** | **16/17** (16) | **16/31** (21) |

- The next serve is right whenever there is one (15/15, 24/24 on the labelled windows); it has no
  answer for a clip's or a set's last rally. The combined rule gets the rest from the end of the
  rally.
- End of the rally, held out, 13 errors: 4 whistled faults; 3 in/out calls at the far ends or
  the frame edges (two landings in by the video and 0.7-1.1 m out by the calibration, one out by
  the video and in by the calibration); 2 landings out that are no floor contact, one not
  detected, one typed as a touch (`actions.py` only types floors on the near part of the court
  or, for the rally's last contact, up to the far sideline); 2 blocked attacks dropping at the net,
  blamed on the wrong side; 1 serve into the net with no contact detected; 1 rally of tangled
  contacts at the net.
- Pipeline: `rallies.py` misses 10 of the 48 rallies (7 of 21 on `side_holdout`, see its held-out
  check), and one window has no contact. Of the 21 held-out rallies with an answer, 16 are right.
  `actions.served` drops its one false window, a ball thrown back to the server: one point less
  for team 1 on `side_holdout`, where it made up for a missed rally.

### Running score

Pipeline, per set, labelled against estimated final score (team 1 - team 2) and worst drift over the
set (points off, both teams summed, after each labelled rally):

| Clip, set | Labelled | Combined | Worst drift | Without the missed-rally credit | Worst drift |
| --- | --- | --- | --- | --- | --- |
| `side_club` 1 | 2-6 | 1-6 | 1 | 1-6 | 1 |
| `side_long` 1 | 3-6 | 3-6 | 0 | 3-6 | 0 |
| `side_holdout` 1 | 11-10 | 9-7 | 6 | 9-4 | 8 |
| `side_setend` 1 | 2-2 | 1-2 | 1 | 1-2 | 1 |
| `side_setend` 2 | 4-2 | 2-3 | 3 | 2-3 | 3 |

Labelled windows and detected contacts with a third of the rallies dropped at random (200 draws, the
rate `rallies.py` misses on `side_holdout`), mean final drift per set:

| Score from | Tuning | Held out |
| --- | --- | --- |
| end of rally only | 2.78 | 3.73 |
| combined, without the missed-rally credit | 2.70 | 3.36 |
| **combined** | **2.09** | **2.46** |

Each missed rally costs about a point; the credit gets back about a quarter of them (only those
the other team won, after a gap of more than 25 s). A full set needs `rallies.py`'s recall more than better rules: at its held-out
recall a 25-point set would end several points short, which the user's final score shows as the
drift.

## Proposed fixes, not applied

Designed after seeing the held-out clips; another match should check them.

- Find the landing from the ball track (the bounce: the track's vertical velocity flipping at floor
  level) instead of `actions.py`'s floor type, so out landings past the far lines count.
- A lens model ([court benchmark](../court/README.md)) for the in/out calls near the ends and the
  frame edges, where the plain homography is off by up to 1.4 m.
- A rally ending on a block: the side the ball falls on loses, from the landing, rather than the
  attacker.
- `rallies.py`'s recall (its own proposed fixes) is the first lever for the score.

## Limits

- One match, one camera, one annotator, 48 rallies; the tuning clips set the constants.
- Faults the referee whistles without the ball showing them (net touch, foot fault, rotation, double
  contact) are only found by the next serve.
- The score starts at 0-0 at each set's first rally found: a recording started mid-set, or a set
  whose first rallies are missed, shifts it; the given final scores show the drift but do not
  correct the running score.
