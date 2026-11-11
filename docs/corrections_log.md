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
   - windows: the touches outside every rally window (26 / 53 to add);
   - false touches: those seen twice or mistimed (23 / 34 of those to remove), then the rest;
   - types: the 91 / 130 types to fix;
   - ball: a training set to fine-tune the ball model on the two matches (the ball is about 4 px wide at the model's 512x288;
     the same model size, so no slower on either machine), labels from the reviewed touches' flights.

## Kept

Nothing yet.

## Tried and dropped

Nothing yet.

## Next

Players (84 / 103): split the wrong picks from the wrong identities, once contacts and types settle.
