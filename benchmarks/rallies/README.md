# Rally segmentation benchmark

Three signals for finding the rallies (serve contact to dead ball) of a sideline video, scored
alone and combined against hand-labelled rallies of two clips of the same school match.

## Run

```bash
uv run --group bench python benchmarks/rallies/bench.py \
  data/side_club.mp4:outputs/ball/side_club_ball.csv:benchmarks/rallies/ground_truth/side_club.csv \
  data/side_long.mp4:outputs/ball/side_long_ball.csv:benchmarks/rallies/ground_truth/side_long.csv --show
uv run --group bench python -m volleyball_stats.rallies data/side_club.mp4 outputs/ball/side_club_ball.csv
```

The ball tracks come from `ball.py` (default stride). The motion energy of each video is cached
under `outputs/bench/rallies/`.

## Videos

| Clip | Source | Length | Content |
| --- | --- | --- | --- |
| `side_club.mp4` | same clip as [benchmarks/ball](../ball/README.md) | 180 s | 8 rallies, one already running when the clip starts |
| `side_long.mp4` | same match and camera, 600 s | 600 s | 9 rallies; 0–230 s is warm-up including serving practice, 544–582 s a break |

Wide-angle camera raised next to the net post, 1280×720 at 29.97 fps, other courts in view and
within earshot.

## Ground truth

`ground_truth/<clip>.csv`: `start_frame` (serve contact), `end_frame` (ball dead) and a note.
Labelled from 1 fps contact sheets of the whole clip, then 6 fps sheets and full-resolution crops
around every boundary, with the ball track printed frame by frame to pin the contact and the floor
bounce. The end is the first of: floor or object contact (a bounce in the track, confirmed on the
crops), the serve hitting the net, the ball leaving the frame at floor height, or the referee's
whistle when it comes before any of those (a fault, or a ball flying out). Every end is 0.1–1.1 s
before a whistle, which cross-checks the label.

Limits: one annotator, no second pass; a few floor contacts happen at the far left edge of the
frame where the court is 20 px per metre, so ±0.3 s is the realistic precision there; the partial
rally at the start of `side_club` has `start_frame=0` and cannot be matched by any method within
±1 s unless it predicts the clip start. Warm-up serves are not rallies.

## Results

A predicted rally matches a true one when both boundaries are within the tolerance; one match per
true rally, in time order. MAE is the mean absolute boundary error over the matches. The interval
is a 95% bootstrap of F1 over rallies (matched pairs, misses and false alarms resampled together).
`motion` is shown at its best threshold (1.2× the median energy).

### side_club (8 rallies, 39 s in play)

| Signal | n | P ±1 s | R ±1 s | F1 ±1 s | MAE | F1 ±2 s |
| --- | --- | --- | --- | --- | --- | --- |
| ball | 9 | 0.33 | 0.38 | 0.35 [0.00–0.60] | 0.26 s | 0.71 [0.43–0.90] |
| whistle | 8 | 0.62 | 0.62 | 0.62 [0.31–0.84] | 0.42 s | 0.88 [0.62–1.00] |
| motion | 9 | 0.00 | 0.00 | 0.00 | – | 0.12 [0.00–0.32] |
| **ball + whistle** | 7 | **1.00** | **0.88** | **0.93** [0.77–1.00] | 0.26 s | 0.93 [0.77–1.00] |

### side_long (9 rallies, 72 s in play)

| Signal | n | P ±1 s | R ±1 s | F1 ±1 s | MAE | F1 ±2 s |
| --- | --- | --- | --- | --- | --- | --- |
| ball | 13 | 0.38 | 0.56 | 0.45 [0.21–0.69] | 0.25 s | 0.55 [0.22–0.77] |
| whistle | 13 | 0.15 | 0.22 | 0.18 [0.00–0.40] | 0.41 s | 0.64 [0.33–0.85] |
| motion | 25 | 0.00 | 0.00 | 0.00 | – | 0.12 [0.00–0.27] |
| **ball + whistle** | 9 | **1.00** | **1.00** | **1.00** [1.00–1.00] | 0.25 s | 1.00 [1.00–1.00] |

The combination misses only the rally already running when `side_club` starts (1 s of ball
flight, under the 300 px travel floor). All constants were set by looking at both clips: there is
no held-out match, so expect the F1 to drop on another gym, referee or whistle.

### Why each signal fails alone

- **Ball track**: the serve and the play are found fine (every true rally overlaps a ball run, MAE
  0.25 s on the matched ones), but the ball keeps moving after it is dead: it bounces, rolls, and
  gets thrown back to the server, for 1.6–7.5 s. Nothing in the 2D track separates a rolling or
  thrown dead ball from a slow live one (a lob also moves 5–10 px/frame). The warm-up serving
  practice of `side_long` adds 4 false rallies, the server bouncing the ball before serving adds
  short ones.
- **Whistle**: the referee whistles twice per rally: a long one (0.6–1.5 s) authorizing the serve,
  1.5–16 s before it, and a short one (0.1–1 s) 0.1–1.1 s after the ball is dead. Pairing them
  gives the end to ±1 s but not the serve, and whistles from the other courts (3 inside the rallies
  of `side_long`) and re-whistles when the server waits break the pairing.
- **Motion energy**: players warm up, celebrate and walk between rallies; the frame-difference
  energy is as high then as during play. Useless here.

## Method (`rallies.py`)

1. Ball speed over a 3-frame lag; frames at 6–60 px/frame are "moving" (a rolling ball stays under
   6; above 60 the tracker jumped to another ball, which ends the run instead of joining two, the
   max-velocity gate of [beach-volley-vision](https://github.com/ddecks/beach-volley-vision)'s
   rally detector, MIT).
2. Runs of moving frames with gaps up to 1.5 s bridged (the longest gap inside a true rally is 1.3 s),
   at least 0.67 s long and 300 px wide. The run starts at the first frame from which the ball
   covers 200 px of width within a second: the serve, not the toss or the bounces before it.
3. Whistles: 16 kHz mono PCM from ffmpeg, 1024-point STFT every 10 ms, a frame is a whistle when
   its 3.3–4.3 kHz peak is 30× the median of 1.5–6 kHz and above 15; runs of 80 ms or more, dips
   under 0.2 s merged.
4. A run is a rally if a whistle starts between 0.5 s after its serve and 2 s after its last motion
   and the ball is not flying at 15 px/frame 1–3 s after that whistle (otherwise it was another
   court's whistle and the next one is tried). The rally ends at that whistle or at the run's last
   motion, whichever comes first.

Prior art checked: no volleyball rally-segmentation paper with code. See et al. 2025 end a
badminton rally when the shuttle stops moving, which fails here because the dead ball keeps
moving; Pidaparthy et al. (CVPRW 2021) combine visual cues and the whistle in an HMM for hockey,
the same idea as step 4 with a rule instead of a model; arXiv 2609.28049 (2026, 66 amateur
volleyball matches from one fixed camera) segments play with a prompted vision-language model but
reports no segmentation metric in its abstract. The VideoMAE SERVICE/PLAY/NO-PLAY classifier of
[volleyball_analytics](https://github.com/masouduut94/volleyball_analytics) is GPL-2.0 and needs a
GPU: the option if a learned model is wanted later. AudioSet whistle classifiers (YAMNet, PANNs)
need TensorFlow or a new dependency, so the FFT band detector stays.

## Limits

- Needs the referee's whistle in the audio: no whistle, no rally. A rally whose end whistle is
  missed is dropped rather than ended late.
- A whistle from another court within 2 s of a dead ball, or followed by 2 s of slow play, ends
  the rally early; a rally with a slow ball for the 2 s after a stray whistle would be cut there.
- Dead-ball motion that lasts longer than 2 s past the whistle is harmless, but a serve-like throw
  closed by a stray whistle would be a false rally. The court module's floor position is the right
  cue to retire a dead ball; add it when a clip shows this.
- Constants are in pixels of a 1280-wide frame; scale them for other resolutions.
