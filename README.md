# volleyball-stats

Automatic per-player volleyball statistics from a match video.

The only manual step is naming players: the pipeline groups every touch into identities, and you
name each identity once. Jersey numbers map to names through a roster kept across matches.

## Recording

- One fixed camera, centered behind a baseline, 3–6 m back, 3.5–5 m high, framing the whole court.
  No auto-tracking or panning camera.
- 4K (2.7K minimum) at 50 fps, linear mode, exposure/focus/white balance locked, shutter 1/250 or
  faster, audio on.
- Mounted on wall bars or a railing, or on a light stand (e.g. Manfrotto 1004BAC) with sandbags or
  strapped to something fixed.

## Development setup

- Training and match processing run on an NVIDIA GPU (RTX 5080), in WSL2 with Ubuntu. The Windows
  NVIDIA driver covers WSL2: do not install a Linux driver.
- RTX 50 series requires PyTorch 2.7+ built for CUDA 12.8+. Older repositories pinning older
  PyTorch or TensorFlow versions are ported to this environment rather than run as-is.
- Code can be written on any machine and run on the GPU machine over SSH (e.g. VS Code
  Remote-SSH).

## Pipeline

| Step | What it does | Starting point |
| --- | --- | --- |
| 1. Rallies | Find when the ball is in play, drop dead time | Motion + whistle detection |
| 2. Court | Detect court lines, map pixels to court coordinates | Line detection + homography |
| 3. Ball | Track the ball, detect contacts and net crossings | TrackNet |
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
8. Later: quality grades (reception 0–3, attack efficiency), second camera if the far side is
   unreliable.

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
- Commercial: Balltime / Hudl Assist.

## License

[AGPL-3.0](LICENSE), so AGPL dependencies such as Ultralytics YOLO and VolleyVision can be reused.
GPL-2.0-only code, such as volleyball_analytics, is incompatible: reference only.

## Privacy

Published footage or datasets require the consent of every filmed player (parents for minors),
opponents included.
