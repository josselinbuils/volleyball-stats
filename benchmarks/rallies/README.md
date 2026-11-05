# Rally segmentation benchmark

Three signals for finding the rallies (serve contact to dead ball) of a sideline video, scored
alone and combined against hand-labelled rallies of two tuning clips of a school match, then checked
on a held-out clip of the same match.

## Run

```bash
uv run --group bench python benchmarks/rallies/bench.py \
  data/benchmarks/side_club.mp4:outputs/benchmarks/ball/side_club_ball.csv:benchmarks/rallies/ground_truth/side_club.csv \
  data/benchmarks/side_long.mp4:outputs/benchmarks/ball/side_long_ball.csv:benchmarks/rallies/ground_truth/side_long.csv \
  data/benchmarks/side_holdout.mp4:outputs/benchmarks/ball/side_holdout_ball.csv:benchmarks/rallies/ground_truth/side_holdout.csv --show
uv run --group bench python -m volleyball_stats.rallies data/benchmarks/side_club.mp4 outputs/benchmarks/ball/side_club_ball.csv --out outputs/benchmarks
```

The ball tracks come from `ball.py` (default stride). The motion energy of each video is cached
under `outputs/benchmarks/bench/rallies/`. Append `:outputs/benchmarks/players/CLIP_players.csv:outputs/court/side_holdout.json`
to a triple to score `served` and `pipeline` (match.py's windows, `match.rally_windows`) too.

## Videos

| Clip | Source | Length | Content |
| --- | --- | --- | --- |
| `side_club.mp4` | same clip as [benchmarks/ball](../ball/README.md) | 180 s | 8 rallies, one already running when the clip starts |
| `side_long.mp4` | same match and camera, 600 s | 600 s | 9 rallies; 0–230 s is warm-up including serving practice, 544–582 s a break |
| `side_holdout.mp4` | same match and camera, 33:00–43:00 of the source video; held out | 600 s | 21 rallies; breaks at 230–270 s and 420–450 s |

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
flight, under the 300 px travel floor). All constants were set by looking at both clips; on a
held-out clip of the same match the F1 drops to 0.72 (see [Held-out check](#held-out-check)).

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

## Held-out check

`side_holdout.mp4` was not looked at while setting the constants. Its 21 rallies were labelled
blind, with the procedure above, before running `rallies.py` or the benchmark on it. Two rallies
end on a fault whistle. Two balls fly out of the frame high and land unseen; they are labelled at
the frame they leave, and the whistle follows 1.1 s and 4.3 s later. The dig into the net at
151–162 s drops out of sight, so its floor contact is estimated to ±0.3 s.

| ball + whistle | n | P ±1 s | R ±1 s | F1 ±1 s | MAE | F1 ±2 s |
| --- | --- | --- | --- | --- | --- | --- |
| side_club (tuning) | 7 | 1.00 | 0.88 | 0.93 [0.77–1.00] | 0.26 s | 0.93 [0.77–1.00] |
| side_long (tuning) | 9 | 1.00 | 1.00 | 1.00 [1.00–1.00] | 0.25 s | 1.00 [1.00–1.00] |
| **side_holdout** | 15 | 0.87 | 0.62 | **0.72** [0.56–0.88] | 0.27 s | 0.72 [0.56–0.88] |

Each signal alone on `side_holdout`, F1 ±1 s: ball 0.45 [0.27–0.62], whistle 0.42 [0.23–0.57],
motion 0.00.

The module overfits the whistles of the tuning clips. The ball runs carry over: every true rally
overlaps one, and the matched boundaries are off by 0.27 s on average. All 8 misses and both false
rallies come from closing the run with a whistle:

| Rally (s) | Result | Cause |
| --- | --- | --- |
| 151.1–162.5, 373.0–387.3, 473.0–476.9 | missed | soft end whistle: peak 17–19 and tonality 24–34, above `MIN_PEAK` 15 and `TONALITY` 30 together for under 80 ms |
| 280.9–286.0 | missed | a louder 3 kHz whistle from another court at the same moment, so the end whistle's peak is not the band maximum |
| 215.3–219.9 | missed | whistle found but rejected by the live-ball test: 2 s later, the dead ball is rolled back across the court at ≥15 px/frame |
| 405.6–408.9 | end 5 s late (miss + false) | same test: the shanked reception falls from above the frame and bounces high, so the next whistle, 4.4 s later, closes the rally |
| 553.1–555.3 | missed | same test: a fault whistle after the reception, then the ball falls untouched |
| 101.7–112.1 | missed | the dig flies out of the frame, and the whistle comes 4.3 s later, past the 2 s window |
| 482.7–488.6 | false | a ball thrown back to the server, closed by the authorization whistle of the next serve (0.9 s); `actions.served` drops it in the pipeline |

So `MIN_PEAK`, `TONALITY` and the live-ball test (`LIVE_SPEED`, `LIVE_WINDOW_S`) fit the loud
whistles and the dead balls of the two tuning clips. On this clip the end whistle is soft or masked
in 4 of 21 rallies, and the dead ball moves fast after 3 of 21 end whistles. Proposed fixes, not
applied:

- Set the whistle threshold per clip from the referee's authorization whistles (one per rally, long
  and loud) instead of absolute constants. Compare the peak to the 3.3–4.3 kHz band only, so that
  another whistle at 3 kHz cannot mask it. The four missed whistles stay above peak 8 and
  tonality 15 for 50–170 ms.
- Replace the speed test with a test that the ball is still played: a contact from `contacts.py`
  1–3 s after the whistle, or the court position of a dead ball.
- Never close a rally with a whistle of 0.6 s or more that a serve follows within 16 s (the next
  authorization). The window after the last ball motion can then grow for balls that leave the
  frame.

These fixes would be designed after seeing this clip, so checking them needs a clip from another
match. Limits of this check: same match, referee, gym and camera, and one annotator.

## Method (`rallies.py`)

1. Ball speed over a 3-frame lag; frames at 6–60 px/frame are "moving" (a rolling ball stays under
   6; above 60 the tracker jumped to another ball, which ends the run instead of joining two, the
   max-velocity gate of [beach-volley-vision](https://github.com/ddecks/beach-volley-vision)'s
   rally detector, MIT).
2. Runs of moving frames with gaps up to 1.5 s bridged (the longest gap inside a true rally is 1.3 s),
   at least 0.67 s long and 300 px wide. The run starts at the first frame from which the ball
   covers 200 px of width within a second: the serve, not the toss or the bounces before it.
3. Whistles: 16 kHz mono PCM from ffmpeg, 1024-point STFT every 10 ms, a frame is a whistle when
   its 2.7–4.3 kHz peak is 30× the median of 1.5–6 kHz and above 15; runs of 80 ms or more, dips
   under 0.2 s merged. Only the whistles within 500 Hz of the video's most common whistle pitch
   are the referee's: 3.3–4.3 kHz on the school match, 2.9–3.3 kHz on the first ASPOM match.
4. A run is a rally if a whistle starts between 0.5 s after its serve and 2 s after its last motion
   and the ball is not flying at 15 px/frame 1–3 s after that whistle (otherwise it was another
   court's whistle and the next one is tried). The rally ends at that whistle or at the run's last
   motion, whichever comes first.
5. With the players tracked (`served`): a serve is the end of a stand of 1.5 s or more by a player
   behind an end line, with the ball on the server's side then and, within 3 s, across the net or,
   starting a ball run, within 200 px (scaled) of it: a serve into the net. The rally runs to the end
   of the ball's motion (`motion_end`: moving frames, gaps up to 2 s bridged, play near the net that
   travels little included), at the latest as the next server's stand starts, or to the first
   whistle before that end or up to 2 s after it that no flying ball follows, as in step 4; the go
   (a whistle during the stand that ends in a serve) closes none. The pipeline adds these rallies
   where step 4 found none: one starting in a step 4 rally or up to 2 s before it is that rally; one
   that a step 4 rally (or another served one) follows less than 8 s after its end is the same rally,
   the ball out of sight between: one window from the serve.

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
- Pixel constants are for the school match's court, 1032 px from end line to end line; the pipeline
  scales them by the video's court length (2.16 on the first ASPOM match, 4K).
- `served` needs the servers in the frame: the camera at the net post of the school match misses
  most of them (F1 ±1 s 0.00–0.43 alone).

## First ASPOM match

4K at 50 fps from 6 m off the sideline, 67 minutes, 128 points (25-23, 25-12, 25-18). The referee
whistles at 2.9–3.3 kHz, under the old 3.3 kHz band, and mostly only the go, not the dead ball: most
rallies come from `served`. `ground_truth/first_match_26_36.csv` labels the 21 rallies of 26:00–36:00
(set 2), from 2 fps court strips of the 4K source and the ball track printed every 0.1 s, as above.

```bash
uv run --group bench python benchmarks/rallies/bench.py --no-motion \
  "data/matches/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4:outputs/matches/2026-10-29-aspom-1-vs-aspom-2/ball.csv:benchmarks/rallies/ground_truth/first_match_26_36.csv:outputs/matches/2026-10-29-aspom-1-vs-aspom-2/players.csv:outputs/courts/aspom_begles.json@1560-2160"
```

| pipeline | n | F1 ±1 s | F1 ±2 s | found P | found R |
| --- | --- | --- | --- | --- | --- |
| before | 20 | 0.73 [0.56–0.87] | 0.83 [0.67–0.93] | 1.00 | 0.95 |
| after | 21 | **0.86** [0.70–0.96] | **1.00** | 1.00 | **1.00** |

Held out: `ground_truth/first_match_50_60.csv` labels the 22 rallies of 50:00–60:00 (set 3) the
same way, after the fixes (`@3000-3600`):

| pipeline | n | F1 ±1 s | F1 ±2 s | found P | found R |
| --- | --- | --- | --- | --- | --- |
| before | 24 | 0.57 [0.39–0.73] | 0.70 [0.54–0.85] | 0.88 | 0.95 |
| after | 23 | 0.58 [0.40–0.75] | 0.76 [0.60–0.88] | 0.91 | 0.95 |
| + `whistled` | 24 | 0.57 | 0.74 | 0.92 | **1.00** |

So the fixes barely carry over. `rallies.whistled` then takes a ball run starting from behind an
end line 1.5–16 s after a whistle as a serve, whoever the players' tracks show there. Merged with
the other serves it opened windows too early (F1 ±1 s 0.48 here); kept only where no window lies
within 8 s and lasting 5 s, it finds the 30 s rally whose server stood out of view (its end 10 s
early: the ball goes out of sight), the tuning span is unchanged, `side_holdout` finds 2 more
rallies (found R 0.81 → 0.90, P 1.00, F1 ±1 s 0.74 → 0.75), and over the whole match it adds 41:33
and 58:55 (missed rallies) and 1:18 (warm-up). Left: two false windows (the next server
bouncing the ball, a ball rolled back), ends cut by another court's whistle (−4.1 s) or with the
ball out of sight (−3.0, −2.3 s), and a rally joined to its dead-ball tail by the 8 s rule (+10 s).

**No player touch.** `match.py` then drops the windows whose contacts are 2 floor contacts or more
and no player touch (`actions.no_play`, after `mark_dead` turns a player bouncing the ball into
floor contacts): the two false windows above. On the windows of the first match's outputs (before
the 31 Oct fixes), 50:00-60:00 goes from F1 ±1 s 0.57, found P 0.88 to 0.59, P 0.95 (24 → 22
windows, none missed more); 26:00-36:00 is unchanged; over the match it drops these 2 windows only,
both answered "no play" in the review (of 6 so answered, against 23 confirmed rallies). The other
4 have a serve or a player touch: a serve followed by 4 net contacts, a dig then 5 floors, a lone
floor, an empty window.

**Serves before the window.** At 4K 50 fps the windows open later than on the school match: 21
of the 43 labelled rallies of both spans open over `LEAD_S` = 0.33 s after their serve contact, 10
over 0.5 s, up to 1.0 s, so the serve fell outside its window and was never typed. `match.rally_windows`
then types each window's contacts from `actions.SERVE_BEFORE_S` = 1 s before it (after the previous
window's end) and, when they open on a serve before its lead, starts the window `LEAD_S` after that
serve (`actions.serve_starts`), unless the next contact is the serving side's within `BOUNCE_PX`
of the server: the server bouncing the ball before serving (`side_holdout` 17170, whose real serve
was then typed "net"; 7-334 px at 4K, against 570 px and more for a false contact in the serve's
flight).

| Windows of the current code | Serves typed | Labelled serves found ±0.1 s | Typed serves off a label | F1 ±1 s 26-36 / 50-60 | MAE 26-36 / 50-60 |
| --- | --- | --- | --- | --- | --- |
| before | 81 of 137 | 19 of 43 | 7 | 0.86 / 0.57 | 0.29 / 0.49 s |
| **`serve_starts`** | **108 of 137** | **35 of 43** | **5** | **0.90 / 0.57** | **0.25 / 0.42 s** |

The school clips' pipeline and the actions benchmark do not move (F1 ±1 s 0.93, 0.95, 0.75;
71/81 and 33/48 contacts). Starting the window at the serve itself instead of `LEAD_S` after it
loses 2 school rallies at ±1 s (two "serves" found over 1 s early); a 1.0-1.25 s look-back finds the
most serves.

**Serves the ball track misses.** `match.py` then adds, in each window still with no serve, the
serve `rallies.served` saw within `match.UNSEEN_SERVE_S` = 1 s of its start, as a contact at the top
of the box of the player standing deepest behind that end line, before the window's first contact
and crossing (`match.unseen_serves`); attribution then gives it that player. On the first match it
adds 23 serves: 131 of 137 windows open on one, the 43 labelled serves are all found within ±1 s
(35 within ±0.1 s, the added ones landing 0.1-0.5 s off the contact), one typed serve lies off a
label, and the 6 that the owner had added by hand in the review go to the same player as the
owner's. On `side_holdout` it adds 2, both labelled serves (8420, 9616; one from outside the frame).

Before, the one miss was a serve into the net (no net crossing, no whistle after it). The ends were
the errors: served rallies ran to the next whistle, often the next rally's go (+11.4 s, +12.8 s), or
stopped with the serve's ball run while play went on near the net (−8.2 s, −1.6 s). The fixes of
step 5 were made on this span, so these numbers are not held out. The school clips' pipeline is
unchanged by them (F1 ±1 s 0.93, 0.95, 0.74). Over the whole match (held out), the windows per set go from
49, 39, 48 to 50, 39, 45 for 48, 37, 43 points: two missed rallies found (4:53, 28:26), five
duplicates joined to their rally, the 7 rallies the review confirmed all kept. Three of 21 ends are
still more than 1 s off: a ball out of sight 1.6 s after a block, a dig sending the ball away, a
rally the ball's motion overruns into the dead ball.

## Whole match, on the review's checked rallies

`checked.py` scores the windows `match.py` writes on every rally a match's review checked: the touches with a
contact inside a window, the contacts in windows that are no touch, the windows on no rally, the rallies
with no window (`match.rally_windows` alone before 5 Nov, the tables below).

```bash
uv run --group bench python benchmarks/rallies/checked.py outputs/matches/2026-10-29-aspom-1-vs-aspom-2 --video data/matches/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4 --court outputs/courts/aspom_begles.json
```

On the first match's 129 rallies and 944 touches (1 Nov), the ball speed saying a rally is still live
(`LIVE_SPEED`) in px/s rather than px/frame, 600 instead of 15 at 50 fps:

| | Touches in windows | Contacts no touch | False windows | Rallies missed | `side_holdout` F1 ±1 s |
| --- | --- | --- | --- | --- | --- |
| before | 812 | 146 | 8 | 2 | 0.75 |
| after | 829 | 153 | 8 | 2 | 0.86 |

`side_club` 0.93, `side_long` 0.95, 26:00-36:00 0.90 and 50:00-60:00 0.57 do not move. Tried and dropped: a whistle
closing nothing while the ball run goes on 3 s after it (+7 touches on the match, but `side_club` 0.80, `side_long`
0.89, `side_holdout` 0.67); `MIN_SPEED` and `MAX_SPEED` per second (`MIN_SPEED` 3.6 at 50 fps: 814 touches, 217 no touch,
12 false windows).

### 2 Nov: late windows and windows that are no rally

All 129 rallies being checked, every window can be scored by its start. Three rules, tuned there:

- `actions.late_serves`: a window opening up to 10 s after its serve starts at it, the serve being the
  contact deep behind the first crossing since the previous window and the referee's go (2 s back without
  a go). A window already opening on a serve stays: an earlier one is a ball thrown over the net.
- `actions.no_play` with the windows: one with no serve, or over 3 s with no crossing (a real serve into
  the net lasts at most 1.6 s), is none. Of the 5 windows it takes, the owner had answered "no play" on 4;
  the fifth is the tail of a real rally, which keeps its window.
- `attribution.unreached`: a serve whose ball crosses the net within 1.2 s stays with no player at the ball
  (a server out of view: the match's first rally).

| | Rally starts ±1 s of 129 | Windows | Touches in windows | 26:00-36:00 F1 ±1 s | 50:00-60:00 |
| --- | --- | --- | --- | --- | --- |
| before | 123 | 135 | 844 | 0.90 | 0.57 |
| after | 126 | 130 | 872 | 0.90 | 0.57 |

A rerun on a copy of the match kept all 129 checked rallies, their winners and running scores, every named
player on the touches they share, the sets' scores and no warning; 3 rallies change, by a floor or net
contact only (the lock holds the players' touches).

Settings searched one at a time (30 constants of `rallies`, `actions`, `attribution` and `contacts`, sets
1-2 apart from set 3): none gains on both but `MOTION_BRIDGE_S` 3 (+0.003, +0.004 of touches F1, one rally
start fewer): left at 2. The constants sit on a plateau, so what is left on 50:00-60:00 needs another signal
(ends with no whistle). Tried and dropped: carrying a rally through the next contacts after its window
(7 real touches for 16-29 false).


### 5 Nov: both matches checked

`checked.py` now scores the windows `match.py` writes (`match.typed_windows`, then `actions.no_play`). With the second
match's 150 checked rallies:

- `no_play` drops a window with no player touch rather than one with no serve: the second match's camera misses
  servers, and 7 of its real rallies had no serve typed (dropped), against 3 false windows that have touches.
- `rallies.alone` takes a whistled serve however short: the aces and serve faults the server's stand misses
  (5 on the two matches) last 1-3 s, under the 5 s it asked.
- `no_play` drops a window of 20 floor contacts or more (`BOUNCED_FLOORS`): a ball bounced 31 times after a whistle,
  where a real rally has at most 13.

| | Touches in windows M1 / M2 | Contacts no touch | False windows | Rallies missed | `side_holdout` F1 ±1 s |
| --- | --- | --- | --- | --- | --- |
| before | 878 / 1073 | 63 / 89 | 2 / 3 | 2 / 9 | 0.77 |
| after | 880 / **1103** | 66 / 94 | 3 / 3 | **0 / 2** | **0.86** |

Of 945 and 1199 touches, 129 and 150 rallies. 26:00-36:00 0.90, 50:00-60:00 0.58, `side_club` 0.93 and `side_long` 0.89
(`match.py`'s windows) do not move. The 2 rallies left on the second match: a serve fault whose ball is lost at once
(39:10), and a serve inside a window opened 6 s early by a ball thrown over, typed "net" (69:22).

The 6 false windows left were all answered "no play" in the review but one, and nothing tells them from rallies: their
contacts run serve, pass, set like a rally's, and a referee's go comes before them as often (107 of 130 real windows
have one 1.5-16 s before). They stay review questions.

Ends, tried on the labelled spans and dropped:

| | 26:00-36:00 F1 ±1 s | 50:00-60:00 |
| --- | --- | --- |
| now | 0.90 | 0.58 |
| end at the first floor contact after the last touch | 0.81 | 0.62 |
| the same with 2 or 3 floors after it | 0.90 | 0.58 |
| the same after a serve only (aces) | 0.90 | 0.62, but it cuts real rallies whose pass was typed floor (a set after it) |
| `carried_on` through a whistle contacts follow 1-3 s later | 0.86 | 0.58 (`side_long` 0.78, `side_holdout` 0.67) |

What is left on 50:00-60:00 is the ball out of sight (-3.0, -2.3, -9.9 s), another court's whistle (-4.1 s) and a rally
joined to its dead-ball tail (+10 s, a tail with a net crossing, closed by the next serve's go): ends need a signal other
than the ball's, the players' moves, say.
