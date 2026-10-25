# volleyball-stats

Automatic per-player volleyball statistics from a match video.

The only manual step is naming players: the pipeline groups every touch into identities, and you
name each identity once. A roster kept across matches suggests the names of the players it has
already seen.

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
  NVIDIA driver covers WSL2: do not install a Linux driver. The locked PyTorch is the CUDA 13
  build, which supports the RTX 50 series and needs a recent driver (R580 or later).
- Older repositories pinning older PyTorch or TensorFlow versions are ported to this environment
  rather than run as-is.
- Code can be written on any machine and run on the GPU machine over SSH (e.g. VS Code
  Remote-SSH).

On the Windows PC:

```bash
wsl --install -d Ubuntu-24.04                     # in PowerShell, then reboot
# in Ubuntu:
sudo apt update && sudo apt install -y ffmpeg git
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/josselinbuils/volleyball-stats.git && cd volleyball-stats
uv sync
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name())"
uv run python benchmarks/speed.py VIDEO          # projected processing time of a match
```

Keep the videos in the Ubuntu file system (`~/`), not under `/mnt/c`: reading Windows files from
WSL2 is several times slower.

The ball and the players are tracked from one reading of the video by `ffmpeg`, on the graphics card
(NVDEC) when it can, the frames shrunk to 1280 px before the models: `speed.py` compares it with the
old two readings and projects both over a 2-hour match. On the M4 Pro the models set the pace (7.8 h
instead of 8.4 h for 2 hours of 4K 50 fps); the RTX 5080 should run them several times faster, so
the saved reading matters more there. `sudo apt install ffmpeg` in WSL2 is enough for NVDEC.

A 2-hour match at 50 fps needs about 8 GB of RAM at its peak, the identity step holding the
players' rows (`benchmarks/scale.py` measures each step on a synthetic long match). WSL2 gets half
of the PC's RAM by default: with 16 GB, raise it in `%UserProfile%\.wslconfig` (`[wsl2]`, then
`memory=12GB`) and restart WSL (`wsl --shutdown`).

## Run on a match

```bash
uv run python -m volleyball_stats.court click VIDEO          # once per court: rough clicks
uv run python -m volleyball_stats.court fit outputs/court/VIDEO_clicks.json VIDEO --court NAME [--lens outputs/lens.json]
uv run python -m volleyball_stats.court auto VIDEO           # next matches on a known court
uv run python -m volleyball_stats.match VIDEO --court outputs/court/VIDEO.json [--players [--teams "NAME_1[:COLOUR],NAME_2[:COLOUR]"] [--date YYYY-MM-DD] [--title TITLE] [--sets M:SS,...] [--scores 25-21,...] [--squad N[,N]]]
```

`--court` takes `outputs/court/VIDEO.json` from `auto`, or `outputs/courts/NAME.json` from `fit` on
the first match of a court. `match` writes the ball track, rallies, typed contacts, net crossings and a
report to `outputs/VIDEO/`; the actions CSV holds each contact with its type and side of the net.
`--players` adds the player tracks (from the same reading of the video as the ball) and the teams: each contact
gets the team on its side (actions CSV `team`), each rally the team on the left and its set
(rallies CSV `left`, `set`), and the report counts per team and per set instead of per side. It also
gives each player one identity for the whole match (`identities.csv`, actions CSV `identity`; see
the [identity benchmark](benchmarks/identity/README.md)), numbered 1, 2, ... per team, and each
rally's winner and the running score of its set (`points.csv`, see the
[points benchmark](benchmarks/points/README.md)). `--squad` gives the number of players of each
team when known (team 1 first): the identities to find.

Teams are Team 1 and Team 2, Team 1 being the team on the left of the camera at the first rally;
they keep their names when they change ends. `outputs/VIDEO/teams.json` holds their names (`null`
for the default "Team 1" / "Équipe 1"), colours (`colour`, `null` for the detected `jersey`), the
match's date (`"yyyy-mm-dd"`) and title (`null` for the default "Match NAME_1 vs NAME_2",
translated on the page), the set starts (`"m:ss"`, the first `"0:00"`) and the sets' final scores
(`"25-21"`, team 1 first, `null` when unknown). It is written on the first run: names and colours
come from `--teams` (the first name is the team on the left at the first rally; a colour is
`#rrggbb` or a name such as `white`, `navy`, `rouge`, `marine`), the date from `--date`, the title
from `--title`, the set starts from `--sets` and the scores from `--scores`; else, on a terminal,
the pipeline opens an image of a few players of each team and asks for them, then for the date
(dd/mm/yyyy or yyyy-mm-dd), the title, each set's start and its final score (Enter keeps the
default name, the detected colour, the video's recording date, the default title, the detected set
start and an unknown score); else the defaults. Later runs reuse the file: edit it to fix a name, a
colour, the date, the title, a set start (a new set starts when the teams change ends after a set
break, see the [teams benchmark](benchmarks/teams/README.md)) or a score, or pass the flags again
(`--title ""` goes back to the default title). The final scores show on the page once a set is
over and the report gives the estimated score's drift from them.

```bash
uv run python -m volleyball_stats.review outputs/VIDEO --video VIDEO --court CALIBRATION_JSON [--squad N[,N]] [--roster PATH]
```

`review` opens, on this machine only, the players the identity step is least sure of, most at stake
first: the player outlined on the looping video, pictures of the numbers they could be, an answer
per key (1, 2: that number, 3: someone else, X: not a player, S: don't know; for two numbers never
on court together, 1: same person, 2: two people). Answers are saved at once to
`identity_answers.json` and hold as hard constraints; "apply" (or "undo") reruns the identity step
and rebuilds the match page in seconds, keeping the other numbers. The identity step also reruns
alone: `uv run python -m volleyball_stats.identity outputs/VIDEO --video VIDEO [--squad N[,N]]`.
Its "Noms" tab names the players: pictures of each one, a name and an optional jersey number, which
the page then shows instead of the match number. Names are saved at once to `player_names.json` and
apply like answers: one name is one player, two names two, so naming two numbers alike joins them.
Applying also updates the roster (`--roster`, `outputs/roster.json` by default, outside the
repository since it names people): each named player's appearance over their last 5 matches, from
which the next matches suggest names, to confirm with a click (on two clips of the same club, the
right name came first for 7 of 12 players, among the 3 shown for 9). Answers and names refer to
pieces of player tracks: tracking the players again (`--force`) drops them.

```bash
uv run python -m volleyball_stats.web outputs/VIDEO --video VIDEO --court CALIBRATION_JSON [--copy-video] [--theme NAME]
```

`web` builds the match page in `outputs/VIDEO/site/` (open `index.html`; French by default): every
number and chart element plays its moments in the video, with a top view of the court following
the play, each player keeping one number for the whole match (their jersey number and name once
named), and the set and its score (estimated, or the final score you gave once the set is over)
above the video. The match's title and date head the page. The video player skips 10 s back or
forward; beside it, the court seen from above shows the players, the ball with a trail as long as it
is fast, and a ring around the player touching it.

The "Statistiques" table gives, team by team, each player's and the whole team's touches, serves
(aces, faults), receptions and digs (faults, an ace counting against the receiver nearest to where
it landed; and those after which the team did not attack), sets, attacks (winning, faults), free
balls (faults), blocks and "Bilan" (points, faults). Its "Analyse" group lists each player's
strengths and things to work on: the rates at least 20 points apart from the rest of their team's,
with 5 attempts or more on each side. A switch shows the same as one card per player instead, with
their picture from the video (`site/players/`, the clearest moment of their longest stretch on
court). Without player tracks it counts each side of the net.

Everything is split by team, in each team's jersey colour (outlined in grey where it is too close
to the background, and changed for Team 2 when the two look alike); without player tracks it falls
back to the sides of the net. With several sets, one filter, which stays at the top of the screen,
shows a single set: every section follows it and the video's timeline then covers that set only. A switch
next to the language picks the light, dark or automatic theme (the system's, by default),
remembered by the browser. The players' positions over the whole video come in `players.js`,
loaded right after the first paint (0.9 MB, 0.23 MB gzipped, for 10 minutes). `--theme` picks a club
theme, `branding/NAME/brand.json` with its logo (default `aspom`, `none` for the neutral one; see
`branding/brand.example.json`): logo and club name in a band at the top linking to `url`, accent
colours, page and card styles per colour scheme. The same files open from disk and host well
(Lighthouse mobile performance 98 with gzip). To host it, copy the folder with `--copy-video` to a
server that supports HTTP range requests and gzip (nginx does), with long cache headers on
`assets/`, behind a password: the footage shows minors.

The page is a React + shadcn/ui app in `web/`; its build is committed in
`src/volleyball_stats/site/`, so processing a match needs no Node. To change it: `cd web && npm
install`, `npm run dev` (reads `web/public/data.js`, copied from a built match), `npm test`, then
`npm run build` to update `src/volleyball_stats/site/`.

## Pipeline

| Step | What it does | Starting point |
| --- | --- | --- |
| 1. Rallies | Find when the ball is in play, drop dead time | Ball-track runs closed by the referee's whistle ([benchmark](benchmarks/rallies/README.md)) |
| 2. Court | Map pixels to court coordinates | Lens undistortion + homography: rough clicks once per court, snapped to the painted lines; known courts recognised automatically when the stand moves a little ([benchmark](benchmarks/court/README.md)) |
| 3. Ball | Track the ball, detect contacts and net crossings | WASB, pretrained ([benchmark](benchmarks/ball/README.md)); contacts from velocity changes with gravity removed ([benchmark](benchmarks/contacts/README.md)) |
| 4. Actions | Classify each contact: serve, reception, set, attack, block, dig | Rules: contact order per side of the net + floor position ([benchmark](benchmarks/actions/README.md)) |
| 5. Players | Detect and track players, tell the teams apart, attribute each contact | YOLO11m + BoT-SORT + an offline pass joining and filtering tracks ([benchmark](benchmarks/players/README.md)); teams from the torso colour of the tracks, the side of the net each team holds rally by rally, and sets from the changes of ends ([benchmark](benchmarks/teams/README.md)); toucher = nearest box on the contact's side, an arm above for serves, attacks and blocks ([benchmark](benchmarks/attribution/README.md)) |
| 6. Identity | Merge tracklets into one identity per player for the match | Tracks cut at crowd episodes, OSNet re-ID embeddings whitened per team, a time-ordered assignment under cannot-links (seen together, too far to run); jersey numbers (4K) as constraints later ([benchmark](benchmarks/identity/README.md)) |
| 7. Naming | Name each identity once, suggest names across matches | The review page's "Noms" tab; a roster of re-ID embeddings per named player |
| 8. Stats | Per-player counts and outcomes, strengths and things to work on | The page's "Statistiques" table: each touch's outcome from the next contact (the ball landing in, out or in the net); an ace counts against the receiver nearest to where it lands; a player's rates compared with the rest of their team's |

## Roadmap

Every step of the pipeline runs, benchmarked on YouTube clips of another club (720p, 30 fps). Next:

1. Film a first match (with the players' consent) and work through the checklists above.
2. Measure `benchmarks/speed.py` on the RTX 5080.
3. Tune on that 4K footage: rally detection (it misses about a third of the held-out clip's rallies),
   how rallies end, contacts at 50 fps, jersey numbers as identity clues.
4. Host the match page behind a password.
5. Later: stats over several matches per named player, attack efficiency, a second camera on the
   opposite sideline if the far side is unreliable.

Each step is checked on real footage against a manual scout of the same rallies. Reference: a fixed-camera semi-automatic system reached 77% agreement with human
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
