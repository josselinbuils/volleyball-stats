# Timeouts benchmark

`volleyball_stats.timeouts`: a gap inside a set under 180 s, with 6 players or fewer on the court for 30 s or more, or of 70 s or more.

```bash
uv run python benchmarks/timeouts/bench.py outputs/matches/MATCH
```

It scores on the review's answers (`timeouts.json`), once given. No truth yet: on two matches, of 268 gaps, 6 found, from one frame each 3 look like
timeouts, 1 probably, 1 is unclear and 1 (30:50 on the second match) likely the set break running on. The 308 s after the second match's last point stays out.
Gaps of 39-60 s with a full court stay out too: 8 of 8 showed players in play, so mostly a rally missed.
