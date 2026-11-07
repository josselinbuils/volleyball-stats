# Defence systems

`defense.layout` and `defense.learn` scored on where the other team's attacks went (`defense.balls`: the defenders'
first touch but a block, a dug ball 1 m further along its flight, or where it landed untouched). No labels say where a
player should have stood: the check is the share of those balls with a spot within 1.5 m, each match held out from the
learning in turn.

```bash
uv run python benchmarks/defense/bench.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 outputs/matches/2026-11-02-avia-1-vs-aspom-2
```

## Results (7 Nov)

Balls within 1.5 m of a spot, first match (90 balls) / second (139):

| System | First | Second |
|---|---|---|
| Textbook perimeter (corners 1 m inside, 6.5 m off the net; 6 at 8 m) | 58% | 47% |
| Perimeter (corners 2 m inside, 6 m off; 6 at 7 m) | 74% | 71% |
| Middle up | 31% | 22% |
| Rotation | 57% | 51% |
| Learned on the other match | 70% | 69% |
| The players' own places at the hit | 64% | 76% |

- The perimeter's corners were moved after looking at both matches: its numbers are not held out.
- Learning by the balls within 1.5 m alone held out 66% and 55%; by the mean distance, 63% and 68%; a bell 1 m wide, kept, 70% and 69%; 1.5 m, 62% and 68%.
- The players' own places lean on the balls they dug, where they stood.
- Even under a double block, 40 of the 93 balls past the 3 m line went through the middle 3 m: the block does not take
  the middle away at this level.
