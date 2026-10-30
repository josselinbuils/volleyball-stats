# Labelling a match in Kili

A labelled match is the reference the benchmarks score the pipeline against. Label one per new
setup (gym, camera, framing), not every match. This guide uses the first ASPOM match
(`data/first_match.mp4`); change the names for another.

## Video

Upload a 1080p copy: it keeps the 4K file's frames, so a Kili frame number is the pipeline's.

```bash
ffmpeg -hwaccel videotoolbox -i data/first_match.mp4 -vf scale=1920:-2 -fps_mode passthrough \
  -c:v h264_videotoolbox -b:v 12M -c:a aac -b:a 128k -movflags +faststart data/first_match_1080p.mp4
```

- A video project at the native 50 fps: Kili samples 30 fps by default (`processingParameters`
  in the SDK). Check once that Kili's frame N shows the frame at N / 50 s, and whether it counts
  from 0 or 1: the converter needs it.
- Upload one part per set (the whole match at 1080p is about 6 GB), cut at exact frames between
  sets and named by its first frame, which the converter adds back. For the set from 24:10 (frame
  72500) to 46:00: `ffmpeg -ss 1450 -i data/first_match_1080p.mp4 -t 1310 -fps_mode passthrough
  -c:v h264_videotoolbox -b:v 12M -c:a aac data/first_match_1080p_from_72500.mp4`. A cut can land
  a frame off: check each part's first frame against the whole file and name the part by the frame
  it really starts on. The first match's parts start at frames 0, 72500 and 137999.
- Keep the project private: the footage shows real players (see Privacy in the README).
- No names in the labels: players are known by team and jersey number. The review page names them.

## Interface

A starting point for the project's JSON interface; adjust it in Kili's editor.

```json
{
  "jobs": {
    "EVENT": {
      "mlTask": "CLASSIFICATION", "instruction": "Rally event", "isChild": false, "required": 0,
      "content": { "input": "radio", "categories": {
        "SERVE": { "name": "Serve", "children": ["SERVER"] },
        "DEAD": { "name": "Dead ball", "children": ["WINNER", "END"] },
        "NET_TOUCH": { "name": "Ball touches the net, still in play" } } }
    },
    "SERVER": {
      "mlTask": "CLASSIFICATION", "instruction": "Serving team", "isChild": true, "required": 1,
      "content": { "input": "radio", "categories": { "TEAM_1": { "name": "ASPOM 01" }, "TEAM_2": { "name": "ASPOM 02" } } }
    },
    "WINNER": {
      "mlTask": "CLASSIFICATION", "instruction": "Point won by", "isChild": true, "required": 1,
      "content": { "input": "radio", "categories": { "TEAM_1": { "name": "ASPOM 01" }, "TEAM_2": { "name": "ASPOM 02" } } }
    },
    "END": {
      "mlTask": "CLASSIFICATION", "instruction": "How it ended", "isChild": true, "required": 1,
      "content": { "input": "radio", "categories": {
        "IN": { "name": "In" }, "OUT": { "name": "Out" }, "NET": { "name": "Net" }, "FAULT": { "name": "Fault" } } }
    },
    "TOUCH": {
      "mlTask": "OBJECT_DETECTION", "instruction": "Player touching the ball", "isChild": false, "required": 0,
      "tools": ["rectangle"],
      "content": { "input": "radio", "categories": { "TOUCHER": { "name": "Toucher", "children": ["TYPE", "OCCLUDED"] } } }
    },
    "TYPE": {
      "mlTask": "CLASSIFICATION", "instruction": "Touch", "isChild": true, "required": 1,
      "content": { "input": "radio", "categories": {
        "SERVE": { "name": "Serve" }, "PASS": { "name": "Reception" }, "DIG": { "name": "Dig" },
        "SET": { "name": "Set" }, "ATTACK": { "name": "Attack" }, "BLOCK": { "name": "Block" },
        "FREE_BALL": { "name": "Free ball" } } }
    },
    "OCCLUDED": {
      "mlTask": "CLASSIFICATION", "instruction": "Overlaps another player", "isChild": true, "required": 0,
      "content": { "input": "checkbox", "categories": { "YES": { "name": "Yes" } } }
    },
    "PLAYER": {
      "mlTask": "OBJECT_DETECTION", "instruction": "Player on court", "isChild": false, "required": 0,
      "tools": ["rectangle"],
      "content": { "input": "radio", "categories": {
        "TEAM_1": { "name": "ASPOM 01", "children": ["JERSEY"] }, "TEAM_2": { "name": "ASPOM 02", "children": ["JERSEY"] } } }
    },
    "JERSEY": {
      "mlTask": "TRANSCRIPTION", "instruction": "Jersey number, empty if unreadable", "isChild": true, "required": 0,
      "content": { "input": "textField" }
    }
  }
}
```

Events are one-frame classifications. If Kili carries one over the next frames, that is fine: the
converter keeps each run's first frame.

## Pass 1: rallies (first)

About 2 events per point (128 on the first match), 1-2 h.

- **SERVE** on the frame the server's hand hits the ball; the serving team.
- **DEAD** on the first of: the ball's first contact with the floor or an object, a serve hitting
  the net, the ball leaving the frame at floor height, or the referee's fault whistle when it comes
  before any of those. The winning team, and how it ended: `In` (lands in the loser's court),
  `Out` (the last touch sends it out), `Net` (into the net), `Fault` (whistled, the ball's path does
  not show it).
- Not rallies: warm-up and practice serves, a point replayed. A rally already running when the
  video starts gets a DEAD without a SERVE.

Check per set: the winners add up to the set's score.

## Pass 2: contacts (later)

About 5 touches per rally, 4-6 h. On each touch's frame (the ball meets the arms or hands), a
**TOUCH** box around the whole player, with:

- the type: `Serve`, `Reception` (first touch of a serve), `Dig` (first touch of any other ball
  from the other side), `Set`, `Attack` (sent over to score: spike, tip, also a second-touch dump),
  `Block` (at the net against an attack), `Free ball` (sent over without attacking);
- `Overlaps another player` when the toucher's box overlaps someone else's.

Also a **NET_TOUCH** event when the ball touches the net and play goes on.

## Pass 3: players (optional, a sample)

For the identity benchmark: every 2 s (100 frames) in about 10 rallies per set, a **PLAYER** box on
each player on court, with their team and jersey number. Kili's tracking keeps one object per
player: keep it on the same player through the rally.

## Export

Export the labels as Kili's JSON into `data/kili/first_match.json` (`data/` stays off git), and
note in which frame Kili counts from. A converter (written with the first export) turns it into
the benchmarks' ground truth, scaling boxes to the 4K frame:

| Labels | Ground truth |
| --- | --- |
| SERVE, DEAD | `benchmarks/rallies/ground_truth/first_match.csv`, `benchmarks/points/ground_truth/first_match.csv` |
| SERVE, DEAD + set starts in `outputs/first_match/teams.json` | `benchmarks/teams/ground_truth/first_match.csv` |
| TOUCH, NET_TOUCH | `benchmarks/contacts/ground_truth/first_match.csv`, `benchmarks/attribution/ground_truth/first_match.csv` |
| PLAYER | `benchmarks/identity/ground_truth/first_match.csv` (players as `ASPOM 01 #22`) |
