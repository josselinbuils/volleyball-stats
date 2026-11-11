# Fewer corrections in the review: work log

Started 11 Nov 2026. Goal (the owner's): less work correcting the automatic labels of a match.
This file is the hand-over: what was measured, tried, kept and dropped, and what to do next.
Read `state.md` and `next_steps.md` first for what was tried before 11 Nov.

## How the work is run

- Claude Fable 5.2 plans and reviews; Sonnet agents execute (cheaper). One agent at a time touches `src/`.
- The two reviewed matches in `outputs/matches/` are never written to: every rerun happens on a scratch copy.
- A change is kept only if the corrections it saves show on both matches (see "Harness").

## Where the corrections are (7 Nov, `learn.json`, before this work)

| Corrections left to the owner | First match (129 rallies) | Second match (150 rallies) |
| --- | --- | --- |
| Touches to add | 65 | 126 |
| Touches to remove | 45 | 71 |
| Types to fix | 91 | 117 |
| Players to fix (named ones) | 91 | 100 |
| Winners to fix | 11 | 18 |

## Harness (`benchmarks/corrections/`, 11 Nov)

    uv run python benchmarks/corrections/bench.py freeze            # once: the checked rallies' truth, frozen
    uv run python benchmarks/corrections/bench.py run NAME          # scratch copy + `learn.rerun` with today's code (3 min a match)
    uv run python benchmarks/corrections/bench.py score NAME --compare baseline
    uv run python benchmarks/corrections/breakdown.py NAME          # the errors by cause, `outputs/benchmarks/corrections/breakdown.md`

Everything lands in `outputs/benchmarks/corrections/MATCH/` (`truth.json`, `runs/NAME/`); the real match folders are only read.
A pipeline run writes nothing outside its `--out` (checked by a file snapshot before and after).
`score real` gives the real folders as they are: it matches `learn.json`'s 7 Nov numbers on the second match; on the first, 10 touches
left the reviewed page since and the names moved (880/945 found, 686/770 players).

## Baseline: today's code, run `baseline` (11 Nov, commit ed91e85)

| | First match | Second match |
| --- | --- | --- |
| Touches found | 880/945 | 1102/1199 |
| Pipeline touches kept | 871/917 | 1094/1167 |
| Types | 789/880 | 972/1102 |
| Named players | 686/770 | 850/953 |
| Winners | 120/128 | 138/145 |
| To add | 65 | 97 |
| To remove | 46 | 73 |
| Types to fix | 91 | 130 |
| Players to fix | 84 | 103 |
| Winners to fix | 8 | 7 |
| **Corrections** | **294** (2.28 a rally) | **410** (2.73 a rally) |
| Rallies needing none | 34 of 129 | 38 of 150 |

The second match's real folder (429 corrections) predates the 5 Nov rally fixes: a rerun alone brings 410.

### Where they come from (first / second match)

- To add (65 / 97): outside every rally window 26 / 53; ball seen under half of ±0.4 s 19 / 25; ball seen, no contact 15 / 12;
  contact found, no player at the ball 5 / 6. By type: attacks 19 / 29, sets 13 / 18, digs 7 / 18, serves 7 / 11.
  The second match: one rally whose window holds its last 1.3 s of 31 s (18 to add), two checked rallies with no window.
- To remove (46 / 73): relance 11 / 13, attack 10 / 11, dig 5 / 17, block 3 / 12, serve 8 / 3. 23 / 34 are 0.2-0.5 s from a real
  touch (seen twice, or a timing slip that also costs a touch to add: 18 / 6 of those to add are under 0.5 s from a pipeline touch).
- Types (91 / 130), truth -> pipeline: attack -> set 10 / 15, attack -> relance 10 / 8, relance -> attack 8 / 15, block -> attack 8 / 8,
  relance -> set 8 / 6; second match dig -> floor 14, dig -> relance 11; first match pass -> floor 7.
- Players (84 / 103): another named player 73 / 83, unknown 11 / 17; same team 68 / 92; the type wrong too on 25 / 20.
- Winners (8 / 7): last touch right, result wrong 6 / 4; another last touch 2 / 0; no window 0 / 3.
- 10 worst rallies: 85 of 294 and 149 of 410 corrections (one 79 s rally of the second match: 33).

## Steps

1. Done: the harness, the baseline and the breakdown above (a Sonnet agent, 14 min).
2. In progress, four Sonnet agents, the pipeline ones each in its own git worktree (`outputs`, `data`, `models` linked, main's `.venv`
   with `PYTHONPATH=src`), reruns one at a time (`flock`, 15 GB of RAM):
   - windows: done, nothing kept ("Tried and dropped");
   - false touches: done, nothing kept ("Tried and dropped");
   - types: done, one rule kept ("Kept"), the rest in "Tried and dropped";
   - ball: a training set to fine-tune the ball model on the two matches (the ball is about 4 px wide at the model's 512x288;
     the same model size, so no slower on either machine), labels from the reviewed touches' flights.

## Kept

| Change | First match | Second match |
| --- | --- | --- |
| A set crossing the net within 1.3 s of its touch is an attack, or a relance by its flight (`actions.SET_OVER_S`, `by_flight`; runs `types-setover`) | 294 -> 288 (types 91 -> 85) | 410 -> 400 (types 130 -> 119, players 103 -> 104) |

The slower sets over the net (1.4 s or more) stay sets, as the owner calls them. The threshold comes from 65 sets over the net on
the two matches (none between 1.3 and 1.4 s): to check on the third match. The school clips' actions benchmark does not run
`by_flight` (no camera model), so it is unchanged by construction; its ball tracks are not on this machine.

## Tried and dropped

### Types (11 Nov, `next_steps.md` "Types to fix (11 Nov)")

Of the 221 wrong types, 20 are a block the pipeline never saw (one touch serving an attack and a block 0.2 s apart: a touch to
add, counted as a type), 24 follow a wrong team, 26 a false touch just before: 151 are the typing's own.

| Idea | Result |
| --- | --- |
| Attack or relance from the height, the rise, the ball above the head, its rise in the picture, in grids | the rule in place (2.1 m, 6 m/s) is at the best on both matches (±3); trees of depth 1-3 lose 3-10 held out |
| The last touch typed floor made a pass or dig by the ball's height over the nearest player's feet | AUC 0.75 but overlapping: at 0.9 box heights 3 touches for 3 floors (first), 8 for 4 (second) |
| A first touch after the other team's attack, typed relance, made a dig | the owner calls the same flights relance 7 of 9 (first) and dig 8 of 14 (second) |
| A learned model | not built: no other cell has a signal to learn |

Out of reach: the missed blocks (detection: a second contact within 0.2 s), floor or touch (the hand on the ball), dig or
relance (the owner's rule to settle: see "Questions for the owner").

### Rally windows (11 Nov, `next_steps.md` "Tried and dropped (11 Nov)", runs `win-whole`, `win-whole2`, second match only)

The 79 touches outside every window (first 26 / second 53): the rally's last 1-3 touches after the window's end 26 / 29 (the
ball seen under 30% of the time in 4 of 5 of those tails; 5 / 6 of them after a whistle that closed the window mid-rally); the
window starting late 0 / 23 (three rallies of 18, 5 and 3 touches whose server stays behind the end line after serving, so
`served` sees no serve); no window 0 / 2 (serve faults with the ball unseen).

| Idea | Result |
| --- | --- |
| A whistled serve holding windows that start over 8 s after it becomes one window | second match 410 -> 412 (the 31 s rally then dropped by `no_play` / `mark_dead`: its low touches near the camera type "floor") |
| A "floor" the ball crosses the net within 2 s after is a low touch | second match 410 -> 429 (to add 97 -> 126, winners 7 -> 15: 8 windows lost) |

Not run: the first match on either idea (the second already lost), the school clips' rally benchmark (their ball tracks are not
in `outputs/`). Out of a rule's reach: the unseen tails (about 40 touches: the ball model), the mid-rally whistles (11: a chain
of 3+ contacts follows 100+ real whistles a match too), the server staying behind the line (23: a serve found from the ball
leaving the server, and `mark_dead` not killing a long rally; a larger change, not tried).

### False touches (11 Nov, offline on the `baseline` runs, no rerun: no rule came close)

What they are (first / second match): 0.2-0.5 s from a real touch 23 / 34, of which a second touch on one the pipeline also
has 14 / 31 and the real one mistimed 9 / 3; no real touch within 0.5 s 23 / 39.

- The main double: a "block" 11 frames (`contacts.GAP` + 1) after a rightly timed attack, across the net: 5 of 14 and about 12 of 31.
  Real blocks at that spacing outnumber them (about 11 real for 1-3 false, 17 for 9): the turn's strength, the ball's direction
  and track jumps do not tell them apart.
- 5 of the first match's 9 mistimed are serves the owner placed 15-36 frames after the ball's first sighting, the ball already
  flying: the truth's time, not a slip (1 on the second).
- Those far from any real touch: often 2-4 relance/dig/set touches between the real attack and the floor; the ball is seen less
  around them (median 0.6-0.7 of ±0.4 s against 1.0) and its track jumps more (p90 270-810 px against 46), but both hit real touches.

| Rule (false removed for real lost) | First match | Second match |
| --- | --- | --- |
| Ball seen under 30-80% of ±0.4 s | 0 for 12 up to 13 for 143 | 4 for 19 up to 48 for 151 |
| A track jump over 80 px near the contact | 7 for 12 | 11 for 14 |
| One track twice within 0.6 s, the second dropped (23 pairs, one false in 17) | 5 for 6 | about 5 for 3 |
| A touch under 1.6x the threshold | 8 for 18 | 28 for 30 |
| A block under 1.25x the threshold | 0 for 0 | 6 for 3 |

Out of a rule's reach: the block after an attack needs the blockers' hands at the net (pose) or a learned filter; the rest a
better ball track.

## Questions for the owner

- A first touch after the other team's attack that sends the ball straight back over: dig or relance? The two matches' labels
  disagree (relance 7 of 9, dig 8 of 14); one rule would save about 16 type fixes over the two matches.

## Next

Players (84 / 103): split the wrong picks from the wrong identities, once contacts and types settle.
