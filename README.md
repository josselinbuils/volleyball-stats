# volleyball-stats

Automatic per-player volleyball statistics from a match video.

The only manual step is naming players: the pipeline groups every touch into identities, and you
name each identity once. Jersey numbers map to names through a roster kept across matches.

## Recording

- One fixed camera on a sideline, aligned with the net, a few meters from the court, 3.6 m high,
  framing both end lines. No auto-tracking or panning camera.
- 4K (2.7K minimum) at 50 fps, widest field of view (lens distortion is corrected in software),
  exposure/focus/white balance locked, shutter 1/250 or faster, audio on.
- Mounted on a light stand (Manfrotto 1004BAC): stand base on the floor behind a handball goal
  post, column strapped to the post (80 × 80 mm) with two straps, low and at ~1.8 m. Only on an
  anchored goal. Without a goal: sandbags on the stand legs.

### Hardware

- [x] DJI Osmo Action 3 Standard Combo
- [x] microSD SanDisk Extreme 256 GB
- [x] 5 m USB-C charging cable
- [x] Manfrotto 1004BAC light stand
- [x] Three-prong to 1/4" adapter: Insta360 1/4" to 3 Pin Adapter
- [x] 2 straps, 25 mm, ~2 m, no hooks (gentle on the stand column)
- [ ] Cord loop (any, e.g. paracord), camera frame to stand column, with a little slack
- [x] Power bank, ~10,000 mAh
- Only if needed: sandbags (free-standing stand), ball head (if the camera hinge slips), bike
  handlebar mount.

### Before the first match

- [ ] Check the SD card with [F3](https://github.com/AltraMayor/f3) or H2testw.
- [ ] Record 2 hours at home, 4K 50 fps, on the power bank through the 5 m cable: no cut, no
      overheating.
- [ ] Lock the settings: 50 fps, widest field of view, shutter 1/250 or faster, exposure and white
      balance locked, audio on.
- [ ] Calibrate the lens once at those settings: without it the court mapping is off by 0.3–1.4 m
      (see the court benchmark). Print the board (`python -m volleyball_stats.lens pattern`), tape
      it flat on cardboard, film it for a minute at 1–3 m while tilting it and sweeping it into the
      corners and edges of the frame, then `python -m volleyball_stats.lens calibrate VIDEO` writes
      `outputs/lens.json`, to pass as `--lens` to the court commands.
- [ ] At the gym: get approval for the handball goals, check they are anchored, check the framing
      from the stand shows both end lines and the near corners.

### After the first match

- [ ] Label rallies and the contacts of a few rallies, rerun the ball, rally and contact
      benchmarks on it.
- [ ] Rallies: apply and test the fixes of the [held-out check](benchmarks/rallies/README.md#held-out-check)
      (whistle threshold per video, "ball still in play" from contacts, authorization whistles never
      closing a rally).
- [ ] Contact pixel thresholds: rerun the sweep for 4K 50 fps.

## Development setup

- Training and match processing run on an NVIDIA GPU (RTX 5080), in WSL2 with Ubuntu. The Windows
  NVIDIA driver covers WSL2: do not install a Linux driver.
- RTX 50 series requires PyTorch 2.7+ built for CUDA 12.8+. Older repositories pinning older
  PyTorch or TensorFlow versions are ported to this environment rather than run as-is.
- Code can be written on any machine and run on the GPU machine over SSH (e.g. VS Code
  Remote-SSH).

## Run on a match

```bash
uv run python -m volleyball_stats.court click VIDEO          # once per court: rough clicks
uv run python -m volleyball_stats.court fit outputs/court/VIDEO_clicks.json VIDEO --court NAME [--lens outputs/lens.json]
uv run python -m volleyball_stats.court auto VIDEO           # next matches on a known court
uv run python -m volleyball_stats.match VIDEO --court outputs/court/VIDEO.json
```

`--court` takes `outputs/court/VIDEO.json` from `auto`, or `outputs/courts/NAME.json` from `fit` on
the first match of a court. `match` writes the ball track, rallies, contacts, net crossings and a
report to `outputs/VIDEO/`.

## Pipeline

| Step | What it does | Starting point |
| --- | --- | --- |
| 1. Rallies | Find when the ball is in play, drop dead time | Ball-track runs closed by the referee's whistle ([benchmark](benchmarks/rallies/README.md)) |
| 2. Court | Map pixels to court coordinates | Lens undistortion + homography: rough clicks once per court, snapped to the painted lines; known courts recognised automatically when the stand moves a little ([benchmark](benchmarks/court/README.md)) |
| 3. Ball | Track the ball, detect contacts and net crossings | WASB, pretrained ([benchmark](benchmarks/ball/README.md)); contacts from velocity changes with gravity removed ([benchmark](benchmarks/contacts/README.md)) |
| 4. Actions | Classify each contact: serve, reception, set, attack, block, dig | Contact order per side + position |
| 5. Players | Detect and track players, attribute each contact | YOLO + ByteTrack + pose (wrists) |
| 6. Identity | Merge tracklets into one identity per player for the match | Jersey number OCR + re-ID + team color |
| 7. Naming | Show one thumbnail gallery per identity, store number → name | Simple local UI |
| 8. Stats | Per-player counts and outcomes (kill, error, ace) | Ball landing spot + next action |

## Roadmap

1. Film a first match.
2. Rally segmentation and court detection.
3. Ball tracking and contact detection.
4. Action classification.
5. Player tracking and contact attribution.
6. Identity clustering and naming.
7. Stats report.
8. Later: quality grades (reception 0–3, attack efficiency), second camera on the opposite
   sideline if the far side is unreliable.

Each step is validated on real footage against a manual scout of the same rallies before the next
one starts. Reference: a fixed-camera semi-automatic system reached 77% agreement with human
scouting ([UFP thesis, 2026](https://bdigital.ufp.pt/bitstreams/9e2cbd9e-89d4-4191-a1bc-7a0533e97f9f/download)).

## Prior art

- [shukkkur/VolleyVision](https://github.com/shukkkur/VolleyVision) (AGPL-3.0): ball tracking,
  court detection, action recognition.
- [Shaamallow/VolleyVision](https://github.com/Shaamallow/VolleyVision): ball tracking, YOLOv8
  action model.
- [masouduut94/volleyball_analytics](https://github.com/masouduut94/volleyball_analytics)
  (GPL-2.0): ball and action detection.
- [haotianxia/VolleyStats](https://github.com/haotianxia/VolleyStats) (Apache 2.0): stats on top of
  [tprlab/vball](https://github.com/tprlab/vball).
- [SFU Volleyball dataset](https://github.com/mostafa-saad/deep-activity-rec): annotated frames
  with player actions.
- [DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis) (MIT):
  the same goal, with per-stage numbers.
- Commercial: Balltime / Hudl Assist.

Scientific literature per pipeline step, with recommendations: [docs/literature.md](docs/literature.md).

## License

[AGPL-3.0](LICENSE), so AGPL dependencies such as Ultralytics YOLO and VolleyVision can be reused.
GPL-2.0-only code, such as volleyball_analytics, is incompatible: reference only.

## Privacy

Published footage or datasets require the consent of every filmed player (parents for minors),
opponents included.
