<div align="center">

# volleyball-stats

**Per-player volleyball statistics from one camera on the sideline.**

Film a match, let the pipeline find every touch, name the players once:<br>
you get a match page where every number replays its moments.

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![Platform: Linux, WSL2, macOS](https://img.shields.io/badge/platform-Linux%20%7C%20WSL2%20%7C%20macOS-lightgrey)](docs/setup.md)

<br>

<img src="docs/images/match-page.webp" alt="A match page: the score, the match in numbers and the story of the match, set by set">

</div>

## What you get

From the video of a whole match, with no tagging by hand:

- **Every player's statistics:** serves, receptions, sets, attacks, blocks and digs, with their
  outcomes, ratings and faults, team by team and set by set.
- **Every moment replayable:** click a number, a dot or a trophy to watch those touches, in the video
  or on an animated court in 2D, 3D or a TV-style broadcast with commentary.
- **The story of the match:** the score gap rally by rally, runs, comebacks and set points saved.
- **Advice for the team:** what cost the most points (naming no one for a fault), who sets whom, the
  attack jump and the placement in reception and defence, and trophies for what players did well.
- **My match:** each player picks their name and sees their own touches, best points and card.
- **A page to share:** static files that open from disk or host anywhere, in French and English, light
  or dark. With no footage by default, so no player shows on video without their consent.

The only manual step is naming the players: the pipeline groups every touch into identities, a review
page asks about the ones it is unsure of, and you name each player once. A roster suggests the names
of players already seen in earlier matches.

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/images/tv-mode.webp" alt="TV mode: a rally rebuilt in 3D in a model of the gym, filmed like a broadcast"><br><b>TV mode:</b> each rally rebuilt in 3D, filmed like a broadcast</td>
    <td width="50%"><img src="docs/images/statistics.webp" alt="The statistics table: touches, serves, receptions and sets per player"><br><b>Statistics:</b> each player's touches and their outcomes</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/court-map.webp" alt="Every touch of the match drawn where it was played on the court"><br><b>On the court:</b> every touch where it was played</td>
    <td width="50%"><img src="docs/images/coach.webp" alt="The coach's corner: what cost the most points, and who sets whom"><br><b>The coach's corner:</b> what to work on, who sets whom</td>
  </tr>
</table>

Screenshots of a real match, with the players' names hidden.

## How it works

```mermaid
flowchart LR
    A[Film the match] --> B[Map the court<br>once per gym]
    B --> C[Run the pipeline]
    C --> D[Review and<br>name the players]
    D --> E[Match page]
```

The pipeline reads the video once and finds the rallies, tracks the ball and its contacts, types each
touch (serve, reception, set, attack, block, dig), tracks the players, splits them into teams, follows
each one through the whole match and keeps the score. Each step is scored against hand labels in
[`benchmarks/`](benchmarks). See [the pipeline](docs/pipeline.md) for the methods and their accuracy.

## Getting started

### 1. Install

You need a computer with a graphics card: an NVIDIA one, or a Mac with an Apple chip (slower). In a terminal (on a
Mac: the Terminal app), paste this line and press Enter:

```bash
curl -LsSf https://raw.githubusercontent.com/josselinbuils/volleyball-stats/main/install.sh | sh
```

It installs what is missing, puts a "Volleyball Stats" shortcut on the desktop and opens the app in the browser.
Next time, open that shortcut, or run the same line again.

On Windows, the app runs in Ubuntu (WSL2): in PowerShell as administrator, run `wsl --install -d Ubuntu-24.04`,
restart, open "Ubuntu" from the Start menu, choose a user name and password, then paste the line above there. See
[Setup](docs/setup.md) for the NVIDIA driver.

The app's "Installation" button checks the graphics card, the memory, the disk space and the tools, and says what to
fix.

### 2. Film a match

One fixed camera on a sideline, in line with the net, about 6 m away and 3.6 m high, framing both end
lines. Film in 4K (2.7K minimum) at 50 fps with the exposure locked. See [Recording](docs/recording.md)
for the stand, the camera settings and the lens calibration.

### 3. Everything else, in the app

1. **Import a match:** pick the camera's card, name the team on the left at the first rally and the other one.
2. **Check:** the app finds the court in a gym it knows; the first time in a gym, click its corners and lines once.
   Check the sides and the court's lines on two pictures, then start the analysis: hours for a 2-hour match.
3. **Review:** once analysed, the match opens in the review. Name each player from their pictures, answer the
   questions about the players it is unsure of, then apply: the match page is rebuilt in seconds.

The match page is in `outputs/matches/MATCH/site/index.html`; the review's "Mettre en ligne" hosts it. When a new
version of the code is out, the app offers to update.

Developers start it with `uv run volleyball-stats`. Each step also has its command, with every option:
[Processing a match](docs/processing.md).

## Documentation

| Guide | What it covers |
| --- | --- |
| [Setup](docs/setup.md) | Requirements, install on WSL2 or macOS, processing time and memory |
| [Recording](docs/recording.md) | Camera placement, hardware, settings, lens calibration |
| [Processing a match](docs/processing.md) | Import, court, pipeline, review, page build and hosting, with every option |
| [The match page](docs/match-page.md) | Each section of the page, how each statistic is counted, changing the page |
| [Pipeline](docs/pipeline.md) | Each step's method and benchmark, accuracy, prior art |
| [Literature](docs/literature.md) | Scientific work per pipeline step, with recommendations |

## Development

```bash
uv run pytest -q                                  # Python tests
cd web && npm install && npm test && npm run build   # the page (Node 22), its build committed
```

Each pipeline step has a benchmark in [`benchmarks/`](benchmarks): change a step, run its benchmark,
compare the numbers before and after.

## Privacy

Published footage, player pictures or datasets require the consent of every filmed player (parents for
minors), opponents included. The page shows no video and no player picture unless asked to.

## License

[AGPL-3.0](LICENSE), so AGPL dependencies such as Ultralytics YOLO and VolleyVision can be reused.
GPL-2.0-only code, such as volleyball_analytics, is incompatible: reference only.
