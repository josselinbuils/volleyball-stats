# Defence placement

`defense.gaps` against the perimeter defence the owner's team plays. No labels say where a player should have stood:
the check is whether the other team scores more when the floor defenders stand further from their spots.

```bash
uv run python benchmarks/defense/bench.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 outputs/matches/2026-11-02-avia-1-vs-aspom-2
```

## Results (7 Nov)

- 367 attacks, all with floor defenders, 4.4 each.
- Both teams of both matches stand short of the perimeter's spots, the same in each: corners 1.3-1.4 m too near the net
  and 0.9-1.1 m off their sideline, zone 6 1.3-2.1 m too near, the front player not blocking 0.3-1.1 m too near and
  0.9-1.0 m off the sideline. Some players repeat on both matches (two in zone 6: 2.4 and 2.5 m, 2.4 and 2.3 m).
- Attacks not missed 303, 31% scored. By the defenders' mean way to their spots, nearest quarter first: 26%, 35%,
  29%, 34%. A hint at most: the textbook spots are not shown to cost fewer points at this level.
- Cues for the whole match: 19 players on the first, 17 on the second.
