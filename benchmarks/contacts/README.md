# Contact detection benchmark

Contact and net crossing detectors on the WASB ball tracks of `side_club` and `side_long`, scored
against hand-labelled rallies.

## Run

```bash
uv run --group bench python benchmarks/contacts/bench.py score \
  outputs/ball/side_club_ball.csv:benchmarks/contacts/ground_truth/side_club.csv \
  outputs/ball/side_long_ball.csv:benchmarks/contacts/ground_truth/side_long.csv --verbose
uv run --group bench python benchmarks/contacts/bench.py sweep <the same pairs>
```

`score` runs `contacts.detect` with its defaults, `sweep` searches the parameters of the three
candidates. The tracks come from `python -m volleyball_stats.ball VIDEO --stride 1 --out
outputs/ball`. Both clips are 29.97 fps with the net at x=612: on this side camera the net plane
projects to x≈598 at the near post and x≈625 at the far post (measured on frame 0 of
`side_club`); the court calibration module will provide that x later.

## Ground truth

`ground_truth/<clip>.csv`: `rally,frame,event,type`, with `start`/`end` rows bounding each rally
window, `contact` rows typed when obvious (`serve`, `pass`, `set`, `attack`, `dig`, `block`,
`floor`, `net` for a ball into the net, empty when unclear) and `net` rows for the crossings.
Only detections inside the windows are scored.

Labelled by reviewing crop sheets around the tracked ball at full frame rate, a contact being the
frame where the ball reverses or breaks its path at a player or the floor, cross-checked on the
track numbers: ±1 frame when the ball is visible. 8 contacts fall in a track gap (ball hidden by
the player) and are placed from the incoming and outgoing flights, ±2 frames. Net crossings are
the frame where the ball's x passes 612, interpolated when the ball is hidden. Left out: a serve
hit outside the frame (rally 1 of `side_club`), catches and balls rolling after the point.

| Clip | Rallies | Contacts | Net crossings |
| --- | --- | --- | --- |
| `side_club` | 7 (frames 400–5056) | 37 | 10 |
| `side_long` | 5 (frames 7140–14290) | 48 | 16 |

Types: 11 serves, 10 passes, 19 sets, 16 attacks, 13 digs, 1 block, 10 floor bounces, 1 ball into
the net, 4 unclear touches.

## Method

A free flight is a parabola in the image, so the velocity between contacts only changes by
gravity. `contacts.py` fits one straight line to the 0.17 s of track before each frame and one
to the 0.17 s after (the frame itself belongs to both flights), removes gravity (the median
vertical acceleration of the moving ball, 0.56–0.60 px/frame² here) and reports the velocity
change in px/s. Contacts are the peaks above 360 px/s, at least 0.2 s apart. Gaps are handled by
fitting whatever is visible on each side, so a contact hidden for up to 6 frames is still found
and placed on the interpolated track; a gap longer than the window on either side gives no value,
so an apex lost against the windows never fires.

A net crossing is a sign change of x − 612 between consecutive visible frames under 1 s apart,
counted once the ball gets 30 px past the net, so a ball played at the net does not cross back
and forth.

## Results

Contacts: a detection within ±2 frames of a labelled contact is a hit, one-to-one. ±4 changes
nothing for `delta_v` and `angle`: their detections are either within 2 frames or wrong. 95%
intervals bootstrap the rallies.

### Candidates

Best F1 at ±2 of each candidate over its window, minimum gap and threshold, pooled over the 12
rallies (`sweep`).

| Candidate | Signal | Window | Gap | Threshold | P | R | F1 ±2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `delta_v` | velocity change, gravity removed | 0.17 s | 0.20 s | 360 px/s | **0.988** | **0.941** | **0.964** |
| `angle` | angle between incoming and outgoing velocities ([beach-volley-vision](https://github.com/ddecks/beach-volley-vision)'s rule, MIT) | 0.10 s | 0.10 s | 80° | 0.987 | 0.882 | 0.932 |
| `residual` | RMS residual of one parabola over the window | 0.10 s | 0.20 s | 3.5 px | 0.986 | 0.859 | 0.918 |

`delta_v` wins because it reads a speed change along the same direction (a hit on a slow ball,
a serve from a toss) and does not amplify the direction noise of slow balls; the angle's best
threshold sits at 75–85° because anything lower fires on the toss and on balls played at the
net, and it misses 10 contacts that `delta_v` finds. `delta_v`'s F1 is 0.958–0.964 for any
threshold from 260 to 420 px/s at a 0.2 s gap; 360 is the middle of the plateau. A 0.15 s gap
at 320–340 px/s ties on F1 (P 0.976, R 0.953).

### Chosen detector (`contacts.detect`)

| What | Tol | P | R | F1 | 95% interval |
| --- | --- | --- | --- | --- | --- |
| contacts | ±2 | 0.988 | 0.941 | 0.964 | [0.92–0.99] |
| contacts | ±4 | 0.988 | 0.941 | 0.964 | [0.92–0.99] |
| net crossings | ±2 | 0.963 | 1.000 | 0.981 | [0.93–1.00] |
| net crossings | ±4 | 0.963 | 1.000 | 0.981 | [0.93–1.00] |

Recall per type: serves 11/11, passes 10/10, sets 18/19, attacks 16/16, digs 13/13, floor
bounces 10/10, block 0/1, ball into the net 0/1, unclear touches 2/4.

The 5 misses: 3 contacts within 3 frames of another one, merged by the 0.2 s minimum gap
(a block 3 frames after the attack, two touches 2–3 frames from a floor bounce); the serve
into the net, where the tracker loses the ball at the net and nothing follows to fit; one set
played from a gap in the track (the ±2 label). The 1 false contact is the ball leaving the frame
through the top edge. The 1 false crossing is a ball passing under the net along the floor.

### Ball tracker stride

On tracks made with `ball.py --stride 3` (each frame seen by one window instead of up to 3), the
default detector scores F1 0.919 at ±2 (P 0.974, R 0.871, interval 0.86–0.95): 6 more contacts
missed (2 serves, 2 floor bounces, a set, an unclear touch), the net crossings unchanged.
Re-sweeping on those tracks gets at best 0.931 (`delta_v`, 0.10 s window, 0.10 s gap, 300–340
px/s, R 0.871). The lighter track costs about 7% of the contacts.

## Limits

- Two contacts under 0.2 s apart merge into one: an attack and its block, a touch and the floor.
  A learned spotter on the trajectory (sliding-window CNN/TCN over x, y, visibility and velocity,
  trained on these labels) is the known fix in the literature, worth it once a few hundred
  contacts are labelled; 85 is not enough to train one.
- A contact needs 2 visible frames on each side within 0.17 s: a ball lost right after the hit
  (into the net, out of frame) is missed, and a ball leaving the frame fires.
- The net plane is a vertical line at one x: a ball passing under the net or outside the
  antennas counts as a crossing. The court calibration will give the net's extent.
- Thresholds are in image pixels per second: the 4K 50 fps target camera needs the sweep rerun
  (or thresholds in m/s once calibrated), and the perspective makes x velocities drift slowly
  along a flight, which the window length absorbs here.
- The detector runs on the whole track: dead time (ball held, rolling, warm-up balls on other
  courts) produces contacts too, so the rally module should bound it.
- 12 rallies from one match, labelled by one person from the track crops.
