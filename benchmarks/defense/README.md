# Defence placement

`defense.assign` against the perimeter defence the owner's team plays. No labels say where a player should have stood:
the check is whether the other team scores more when the defenders stand further from their spots.

```bash
uv run python benchmarks/defense/bench.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 outputs/matches/2026-11-02-avia-1-vs-aspom-2
```

## Results (7 Nov)

- 367 attacks, all with defenders, 5.9 each.
- Blockers stand near their spot: within 0.4 m of depth and 0.7 m to the side, but for one team's 4 (1.3 m). Off the net, both teams of both matches
  stand short of the perimeter's spots: 5 and 1 1.2-1.7 m too near the net and 0.5-1.7 m inside, 6 1.3-2.1 m too near,
  4 and 2 not blocking 0.5-1.7 m too near and up to 1.6 m inside, 3 behind the block 0.6-1.4 m too near.
- Player places from 5 attacks: 70 on the first match, 57 of them 1 m or more off; 81 on the second, 55.
- Attacks not missed 303, 31% scored. By the defenders' mean way to their spots, nearest quarter first: 28%, 33%,
  26%, 37%. A hint at most: the textbook spots are not shown to cost fewer points at this level.
