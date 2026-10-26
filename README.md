# volleyball-stats

Automatic per-player volleyball statistics from a match video.

- **Input:** one fixed camera on the sideline, filming a whole match.
- **Output:** a match page with each player's stats, every moment replayable in the video or on an
  animated court.
- **Only manual step:** naming the players. The pipeline groups every touch into identities, and you
  name each one once. A roster kept across matches suggests the names of players it has already
  seen.

## Contents

- [How it works](#how-it-works)
- [Recording](#recording)
- [Setup](#setup)
- [Process a match](#process-a-match)
- [The match page](#the-match-page)
- [Pipeline](#pipeline)
- [Roadmap](#roadmap)
- [Prior art](#prior-art), [License](#license), [Privacy](#privacy)

## How it works

1. **Film** the match with one fixed camera ([Recording](#recording)).
2. **Map the court** once per gym: a few rough clicks on the court lines.
3. **Run the pipeline:** ball, rallies, contacts, actions, players, teams, identities, score.
4. **Review** the players it is least sure of, and name them.
5. **Open the match page:** stats per player and team, each one playing its moments.

## Recording

### Camera placement

- One fixed camera on a sideline, aligned with the net, a few meters from the court, 3.6 m high.
- It frames both end lines. No auto-tracking or panning camera.
- It sits on a light stand (Manfrotto 1004BAC):
  - the stand's base on the floor behind a handball goal post;
  - the column strapped to the post (80 × 80 mm) with two straps, one low and one at ~1.8 m;
  - only on an anchored goal. Without a goal: sandbags on the stand legs.

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

### Camera settings (Osmo Action 3)

In short: 4K (2.7K minimum) at 50 fps, widest field of view, everything locked, shutter 1/250 or
faster. Lens distortion is corrected in software.

| Setting | Réglage | Where | Value | Why |
| --- | --- | --- | --- | --- |
| Resolution | Résolution | Swipe up | 4K (16:9) | Ball and jersey numbers; the ball model reads 16:9 |
| Frame rate | Fréquence d'images | Swipe up | 50 fps | No flicker under 50 Hz lighting |
| Loop recording | Enregistrement en boucle | Swipe up, top left | Off | Would overwrite the start of the match |
| Stabilisation | Stabilisation | Swipe up, top right | Off (no RockSteady, no HorizonBalancing) | Fixed camera; stabilisation warps each frame |
| Mode | Mode | Parameters icon | PRO | Locked exposure |
| Field of view | Champ de vision | PRO | Ultra Wide, else Wide; never Standard (Dewarp) | Distortion is corrected in software; Dewarp crops |
| Shutter speed | Vitesse d'obturation | PRO, Exposure: Manual | 1/250, 1/500 if the gym is bright | Sharp ball |
| ISO | ISO | PRO, Exposure: Manual | Lowest correct one, set at the gym (often 800–3200) | Locked exposure |
| White balance | Balance des blancs | PRO | Manual, set at the gym (often 4500–5500 K under LEDs) | Stable jersey colours for the teams |
| Colour | Couleur | PRO | Normal, not D-Cinelike | Natural colours for the teams |
| Enhanced image quality | Qualité d'image améliorée | PRO | Off, On only facing sunlit windows | Made for strong light contrast; more power and heat |
| Video compression | Compression vidéo | Swipe down, Settings | Compatibility (H.264) or Efficiency (HEVC, smaller files) | Both decode on the GPU |
| Anti-flicker | Anti-scintillement | Swipe down, Settings | 50 Hz | French power grid |
| Screen off when recording | Écran éteint pendant l'enregistrement | Swipe down, Settings | Shortest delay | Less heat |
| Auto power off | Arrêt automatique | Swipe down, Settings | 30 min (the longest) | No stop before the first serve; the 2-hour test checks it never stops a recording |

- Resolution, frame rate, field of view and stabilisation stay the same for the lens calibration and
  every match. ISO and white balance change with the gym only.
- There is no bitrate setting: the camera records at up to 130 Mbps, about 120 GB for 2 hours.
- The French names are approximate: the menus may word them slightly differently.

### Before the first match

- [x] Check the SD card with [F3](https://github.com/AltraMayor/f3) or H2testw.
- [x] Set the [camera settings](#camera-settings-osmo-action-3), ISO and white balance aside.
- [ ] Record 2 hours at home, 4K 50 fps, on the power bank through the 5 m cable: no cut, no
      overheating.
- [ ] Calibrate the lens once at those settings (see [below](#lens-calibration)).
- [ ] At the gym: get approval for the handball goals and check they are anchored. Check the framing
      from the stand shows both end lines and the near corners.

#### Lens calibration

Without it, the court mapping is off by 0.3–1.4 m (see the
[court benchmark](benchmarks/court/README.md)).

1. Print the board: `uv run python -m volleyball_stats.lens pattern`.
2. Tape it flat on cardboard.
3. Film it for a minute at 1–3 m, tilting it and sweeping it into the corners and edges of the frame.
4. Run `uv run python -m volleyball_stats.lens calibrate VIDEO`. It writes `outputs/lens.json`, to
   pass as `--lens` to the court commands.

### After the first match

- [ ] Label rallies and the contacts of a few rallies, then rerun the ball, rally and contact
      benchmarks on them.
- [ ] Rallies: apply and test the fixes of the
      [held-out check](benchmarks/rallies/README.md#held-out-check):
  - a whistle threshold per video;
  - "ball still in play" from contacts;
  - authorization whistles never closing a rally.
- [ ] Contact pixel thresholds: rerun the sweep for 4K 50 fps.

## Setup

### Requirements

- Training and match processing run on an NVIDIA GPU (RTX 5080), in WSL2 with Ubuntu.
- The Windows NVIDIA driver covers WSL2: do not install a Linux driver.
- The locked PyTorch is the CUDA 13 build. It supports the RTX 50 series and needs a recent driver
  (R580 or later).
- Code can be written on any machine and run on the GPU machine over SSH (e.g. VS Code Remote-SSH).
- Older repositories pinning older PyTorch or TensorFlow versions are ported to this environment
  rather than run as-is.

### Install

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

### Performance

- **Keep the videos in the Ubuntu file system** (`~/`), not under `/mnt/c`: reading Windows files
  from WSL2 is several times slower.
- **One reading of the video:** `ffmpeg` decodes it once for both the ball and the players, on the
  graphics card (NVDEC) when it can, shrinking the frames to 1280 px before the models.
  `sudo apt install ffmpeg` in WSL2 is enough for NVDEC.
- **Processing time:** `speed.py` compares that reading with the old two readings and projects both
  over a 2-hour match. On the M4 Pro the models set the pace (7.8 h instead of 8.4 h for 2 hours of
  4K 50 fps). The RTX 5080 should run them several times faster, so the saved reading matters more
  there.
- **Memory:** a 2-hour match at 50 fps needs about 8 GB of RAM at its peak, the identity step
  holding the players' rows (`benchmarks/scale.py` measures each step on a synthetic long match).
- **WSL2 memory:** WSL2 gets half of the PC's RAM by default. With 16 GB, raise it in
  `%UserProfile%\.wslconfig` (`[wsl2]`, then `memory=12GB`) and restart WSL (`wsl --shutdown`).

## Process a match

### 1. Map the court

```bash
uv run python -m volleyball_stats.court click VIDEO          # once per court: rough clicks
uv run python -m volleyball_stats.court fit outputs/court/VIDEO_clicks.json VIDEO --court NAME [--lens outputs/lens.json]
uv run python -m volleyball_stats.court auto VIDEO           # next matches on a known court
```

- **First match on a court:** `click`, then `fit`. It writes `outputs/courts/NAME.json`.
- **Next matches on that court:** `auto` recognises it, even when the stand moved a little. It
  writes `outputs/court/VIDEO.json`.

Either file is the `--court` of the next steps.

### 2. Run the pipeline

```bash
uv run python -m volleyball_stats.match VIDEO --court outputs/court/VIDEO.json [--players [--teams "NAME_1[:COLOUR],NAME_2[:COLOUR]"] [--date YYYY-MM-DD] [--title TITLE] [--sets M:SS,...] [--scores 25-21,...] [--squad N[,N]]]
```

`match` writes to `outputs/VIDEO/`:

- the ball track, rallies, typed contacts, net crossings and a report;
- the actions CSV: each contact with its type and side of the net.

`--players` adds the players, from the same reading of the video as the ball:

- **Teams:** each contact gets the team on its side (actions CSV `team`), each rally the team on the
  left and its set (rallies CSV `left`, `set`). The report counts per team and per set instead of
  per side.
- **Identities:** each player gets one identity for the whole match, numbered 1, 2, ... per team
  (`identities.csv`, actions CSV `identity`; see the
  [identity benchmark](benchmarks/identity/README.md)).
- **Score:** each rally's winner and the running score of its set (`points.csv`; see the
  [points benchmark](benchmarks/points/README.md)).
- `--squad` gives the number of players of each team when known (team 1 first): the identities to
  find.

#### Teams, date, title, sets and scores

Team 1 is the team on the left of the camera at the first rally. Teams keep their names when they
change ends, at a set break or a timeout. Kits may differ within a team: a player's team is their
side of the net.

`outputs/VIDEO/teams.json` holds:

| Field | Value | Default (`null`) |
| --- | --- | --- |
| Names | Team names | "Team 1" / "Équipe 1" |
| `colour` | Team colours | The detected `jersey` colour |
| Date | `"yyyy-mm-dd"` | The video's recording date |
| Title | The match's title | "Match NAME_1 vs NAME_2", translated on the page |
| Set starts | `"m:ss"`, the first `"0:00"` | The detected set starts |
| Final scores | `"25-21"`, team 1 first | Unknown |

The first run writes it, from the first source available:

1. **The flags:**
   - `--teams` for the names and colours: the first name is the team on the left at the first rally;
     a colour is `#rrggbb` or a name such as `white`, `navy`, `rouge`, `marine`;
   - `--date`, `--title`, `--sets` and `--scores`.
2. **Questions on a terminal:** it opens an image of a few players of each team and asks for their
   names and colours, then the date (dd/mm/yyyy or yyyy-mm-dd), the title, each set's start and its
   final score. Enter keeps the default.
3. **The defaults.**

Later runs reuse the file. To fix something, either:

- edit the file: a name, a colour, the date, the title, a set start or a score;
- or pass the flags again (`--title ""` goes back to the default title).

A new set starts when the teams change ends after a set break (see the
[teams benchmark](benchmarks/teams/README.md)). Teams that keep their ends between sets get no new
set: give the set starts with `--sets` or at the prompt. The final scores show on the page once a set is
over, and the report gives the estimated score's drift from them.

### 3. Review and name the players

```bash
uv run python -m volleyball_stats.review outputs/VIDEO --video VIDEO --court CALIBRATION_JSON [--squad N[,N]] [--roster PATH]
```

`review` opens, on this machine only, the players the identity step is least sure of, most at stake
first. Each question shows the player outlined on a looping video and pictures of the numbers they
could be.

| Key | Answer |
| --- | --- |
| 1, 2 | That number |
| 3 | Someone else |
| X | Not a player |
| S | Don't know |

For two numbers never on court together: 1 for the same person, 2 for two people.

- **Answers** are saved at once to `identity_answers.json` and hold as hard constraints.
- **"Apply"** (or "undo") reruns the identity step and rebuilds the match page in seconds, keeping
  the other numbers.
- **The identity step also reruns alone:**
  `uv run python -m volleyball_stats.identity outputs/VIDEO --video VIDEO [--squad N[,N]]`.

The **"Noms" tab** names the players: pictures of each one, a name and an optional jersey number,
which the page then shows instead of the match number.

- Names are saved at once to `player_names.json` and apply like answers: one name is one player, two
  names two, so naming two numbers alike joins them.
- Applying also updates the roster (`--roster`, `outputs/roster.json` by default, outside the
  repository since it names people): each named player's appearance over their last 5 matches.
- The next matches suggest names from it, to confirm with a click. On two clips of the same club,
  the right name came first for 7 of 12 players, and among the 3 shown for 9.
- Answers and names refer to pieces of player tracks: tracking the players again (`--force`) drops
  them.

### 4. Build the match page

```bash
uv run python -m volleyball_stats.web outputs/VIDEO --video VIDEO --court CALIBRATION_JSON [--club N] [--footage none|full|blur-opponents|blur-all] [--pictures] [--copy-video] [--theme NAME]
```

`web` builds the page in `outputs/VIDEO/site/`: open `index.html` (French by default).

| `--footage` | The page shows |
| --- | --- |
| `none` (default) | No video: every moment replays on an animated top view of the court |
| `full` | The video |
| `blur-opponents` | The video, with the team other than `--club` (your team, 1 or 2) pixelated |
| `blur-all` | The video, with both teams pixelated |

- **Blurring** (`volleyball_stats.blur`) pixelates the tracked players' boxes, carried across
  tracking gaps. People never tracked, such as the bench or the public, stay visible. The blurred
  copy is kept beside the outputs.
- **`--pictures`** puts your team's players' pictures on their cards. Without it, the cards show a
  silhouette.
- **`--theme`** picks a club theme, `branding/NAME/brand.json` with its logo (default `aspom`, `none`
  for the neutral one; see `branding/brand.example.json`): logo and club name in a band at the top
  linking to `url`, accent colours, page and card styles per colour scheme.
- **Choices are saved** in `outputs/VIDEO/page.json`: rebuild with only the flag to change
  (`--no-pictures`, `--footage none`...).
- **The review page** builds its own copy with the video in `outputs/VIDEO/review/`, and rebuilds the
  published page on "apply".

## The match page

### Replay

- The match's title and date head the page.
- Every number and chart element plays its moments in the video or on the animated court.
- Above the video: the set and its score (estimated, or the final score you gave once the set is
  over).
- The video player skips 10 s back or forward.
- Beside it, the court seen from above follows the play: the players, the ball with a trail as long
  as it is fast, and a ring around the player touching it.
- Each player keeps one number for the whole match: their jersey number and name once named.
- **3D view:** a switch turns the court into a 3D scene to turn around with the pointer (three.js, in
  its own `scene3d.js` loaded only then):
  - the players as figures jumping to attack and block;
  - the ball's height reconstructed, each flight rising as high as gravity requires for its duration,
    each touch at a typical height for its action.

### Statistics

The "Statistiques" table gives, team by team, each player's and the whole team's:

- touches;
- serves: aces, faults;
- receptions and digs: faults (an ace counts against the receiver nearest to where it landed), and
  those after which the team did not attack;
- sets;
- attacks: winning, faults;
- free balls: faults;
- blocks;
- "Bilan": points, faults.

Its "Analyse" group lists each player's strengths and things to work on: the rates at least 20
points apart from the rest of their team's, with 5 attempts or more on each side.

A switch shows the table as one FIFA-style card per player instead, with their picture from the
video (`site/players/`: the clearest moment of their longest stretch on court, 3 wide for 4 tall).

Without player tracks, everything counts each side of the net instead of each team.

### Display

- **Team colours:** everything is split by team, in each team's jersey colour. A colour too close to
  the background is outlined in grey; Team 2's changes when the two look alike.
- **Set filter:** with several sets, one filter at the top of the screen shows a single set. Every
  section follows it, and the video's timeline then covers that set only.
- **Theme:** a switch next to the language picks the light, dark or automatic theme (the system's,
  by default), remembered by the browser.
- **Loading:** the players' positions over the whole video come in `players.js`, loaded right after
  the first paint (0.9 MB, 0.23 MB gzipped, for 10 minutes).

### Hosting

The same files open from disk and host well (Lighthouse mobile performance 98 with gzip).

The hosted page has no password, so it never carries real footage or player pictures (nor anything
cut from them) without every player's consent. To host it:

1. Build it with `--footage none --no-pictures`.
2. Copy the folder to a server that supports gzip (nginx does).
3. Set long cache headers on `assets/`.

With every player's consent, `--footage ... --copy-video` adds the video: the server then needs HTTP
range requests too.

### Change the page

The page is a React + shadcn/ui app in `web/`. Its build is committed in
`src/volleyball_stats/site/`, so processing a match needs no Node.

```bash
cd web
npm install
npm run dev      # reads web/public/data.js, copied from a built match
npm test
npm run build    # updates src/volleyball_stats/site/
```

## Pipeline

| Step | What it does | Starting point |
| --- | --- | --- |
| 1. Rallies | Find when the ball is in play, drop dead time | Ball-track runs closed by the referee's whistle ([benchmark](benchmarks/rallies/README.md)) |
| 2. Court | Map pixels to court coordinates | Lens undistortion + homography: rough clicks once per court, snapped to the painted lines; known courts recognised automatically when the stand moves a little ([benchmark](benchmarks/court/README.md)) |
| 3. Ball | Track the ball, detect contacts and net crossings | WASB, pretrained ([benchmark](benchmarks/ball/README.md)); contacts from velocity changes with gravity removed ([benchmark](benchmarks/contacts/README.md)) |
| 4. Actions | Classify each contact: serve, reception, set, attack, block, dig | Rules: contact order per side of the net + floor position ([benchmark](benchmarks/actions/README.md)) |
| 5. Players | Detect and track players, tell the teams apart, attribute each contact | YOLO11m + BoT-SORT + an offline pass joining and filtering tracks ([benchmark](benchmarks/players/README.md)); teams from the side of the net, followed from rally to rally by the tracks crossing each break and, after a long break, by the players' looks, so kits may differ within a team; sets from the changes of ends ([benchmark](benchmarks/teams/README.md)); toucher = nearest box on the contact's side, an arm above for serves, attacks and blocks ([benchmark](benchmarks/attribution/README.md)) |
| 6. Identity | Merge tracklets into one identity per player for the match | Tracks cut at crowd episodes, OSNet re-ID embeddings whitened per team, a time-ordered assignment under cannot-links (seen together, too far to run); jersey numbers (4K) as constraints later ([benchmark](benchmarks/identity/README.md)) |
| 7. Naming | Name each identity once, suggest names across matches | The review page's "Noms" tab; a roster of re-ID embeddings per named player |
| 8. Stats | Per-player counts and outcomes, strengths and things to work on | The page's "Statistiques" table: each touch's outcome from the next contact (the ball landing in, out or in the net); an ace counts against the receiver nearest to where it lands; a player's rates compared with the rest of their team's |

## Roadmap

Every step of the pipeline runs, benchmarked on YouTube clips of another club (720p, 30 fps). Next:

1. Film a first match (with the players' consent) and work through the checklists above.
2. Measure `benchmarks/speed.py` on the RTX 5080.
3. Tune on that 4K footage:
   - rally detection: it misses about a third of the held-out clip's rallies;
   - how rallies end;
   - contacts at 50 fps;
   - jersey numbers as identity clues.
4. Later: stats over several matches per named player, attack efficiency, a second camera on the
   opposite sideline if the far side is unreliable.

Each step is checked on real footage against a manual scout of the same rallies. For reference, a
fixed-camera semi-automatic system reached 77% agreement with human scouting
([UFP thesis, 2026](https://bdigital.ufp.pt/bitstreams/9e2cbd9e-89d4-4191-a1bc-7a0533e97f9f/download)).

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
