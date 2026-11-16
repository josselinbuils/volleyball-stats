# Framing benchmark

The automatic zoom: `framing.camera` follows `framing.py`'s views (made with the page), which the video's copies are cut
by and the page draws with (video.js's `camera`); before 16 Nov the page zoomed the picture itself, as `--no-spring` replays. `bench.py` replays them on the analysed matches' review pages, every 0.2 s of the rallies: the zoom shown (median),
the share of moments showing every player on the court whole, and the share showing the ball where it is seen. No
labels: the players' boxes and the ball's track are the pipeline's.

```bash
uv run python benchmarks/framing/bench.py [--slide | --no-spring] [MATCH ...]
```

| 15 Nov, 3 matches | zoom | all players whole | ball |
|---|---|---|---|
| Before: one view per exchange (all its players), kept unless 1.3× too wide, at least half the picture; the view slid to the ball | ×1.40 | 98.6% | 99.2% |
| A view every second (players from 1 s before to 1.5 s after), kept unless 1.15× too wide, at least 40%; still sliding (`--slide`) | ×1.64 | 97.8% | 98.6% |
| The same, the view widened to the ball instead (kept) | ×1.62 | 99.3% | 98.5% |
| 16 Nov, the camera the copies are cut by: the same, followed by the spring (`framing.camera`) | ×1.62 | 99.5% | 98.4% |
| The same, zoomed 2.5x on the close calls' bounces (4, 0 and 5 calls; `framing.bounces`), as the page did on top | ×1.62 | 99.3% | 98.5% |

The owner's call (15 Nov): closer, as long as every player and the ball stay in, parts of the court out. The ball's
0.7 points lost are its fastest moments: the view follows its place averaged over 0.5 s.
