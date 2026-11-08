# Processing a match

Every command and option, from the camera's card to the hosted page. The short path is in the
[README's getting started](../README.md#getting-started).

1. [Import a match](#import-a-match)
2. [Map the court](#1-map-the-court)
3. [Run the pipeline](#2-run-the-pipeline)
4. [Review and name the players](#3-review-and-name-the-players)
5. [Build the match page](#4-build-the-match-page)
6. [Host the matches](#5-host-the-matches)

## Import a match

```bash
uv run python -m volleyball_stats.import_match /Volumes/SD_CARD --teams "NAME_1[:COLOUR],NAME_2[:COLOUR]" [--from TIME] [--to TIME] [--date DATE]
```

It joins the camera's chapters without re-encoding, cut at the times given in the joined video, into
`data/matches/MATCH/MATCH.mp4`, where `MATCH` is the name of the match's hosted page (date and teams), and starts
`outputs/matches/MATCH/` with `teams.json`. The first team is the one on the left at the first rally: check
`outputs/matches/MATCH/start.jpg`. The card is only read.

Change a team's name in the review and the match follows: its folders, video and backups take the new name, and the next upload moves
its hosted page, with a redirect from the old address. `uv run python -m volleyball_stats.rename outputs/matches/MATCH [NEW_NAME]` does the same without the review.

## 1. Map the court

```bash
uv run python -m volleyball_stats.court click VIDEO          # once per court: rough clicks
uv run python -m volleyball_stats.court fit outputs/court/VIDEO_clicks.json VIDEO --court NAME [--lens docs/lens_osmo_action3_standard_4k.json]
uv run python -m volleyball_stats.court auto VIDEO           # next matches on a known court
```

- **First match on a court:** `click`, then `fit`. It writes `outputs/courts/NAME.json`.
- **Next matches on that court:** `auto` recognises it, even when the stand moved a little. It
  writes `outputs/court/VIDEO.json`.

Either file is the `--court` of the next steps.

## 2. Run the pipeline

```bash
uv run python -m volleyball_stats.match VIDEO --court outputs/court/VIDEO.json [--players [--teams "NAME_1[:COLOUR],NAME_2[:COLOUR]"] [--date YYYY-MM-DD] [--title TITLE] [--sets M:SS,...] [--scores 25-21,...] [--squad N[,N]]]
```

`match` writes to `outputs/matches/VIDEO/`:

- the ball track, rallies, typed contacts, net crossings and a report;
- the actions CSV: each contact with its type and side of the net.

`--players` adds the players, from the same reading of the video as the ball:

- **Teams:** each contact gets the team on its side (actions CSV `team`), each rally the team on the
  left and its set (rallies CSV `left`, `set`). The report counts per team and per set instead of
  per side.
- **Identities:** each player gets one identity for the whole match, numbered 1, 2, ... per team
  (`identities.csv`, actions CSV `identity`; see the
  [identity benchmark](../benchmarks/identity/README.md)).
- **Score:** each rally's winner and the running score of its set (`points.csv`; see the
  [points benchmark](../benchmarks/points/README.md)).
- **Attack jumps:** the attackers' poses around each attack (`jumps.json`), from which the page's build measures each
  jump ([jumps benchmark](../benchmarks/jumps/README.md)); its build poses only the touches the review moves.
- `--squad` gives the number of players of each team when known (team 1 first): the identities to
  find.

### Teams, date, title, sets and scores

Team 1 is the team on the left of the camera at the first rally. Teams keep their names when they
change ends, at a set break or a timeout. Kits may differ within a team: a player's team is their
side of the net. Two teams in the same kit (two teams of one club) are taken to change ends at every
set break, as the rules say, and only then.

`outputs/matches/VIDEO/teams.json` holds:

| Field | Value | Default (`null`) |
| --- | --- | --- |
| Names | Team names | "Team 1" / "Équipe 1" |
| `colour` | Team colours | The detected `jersey` colour |
| Date | `"yyyy-mm-dd"` | The video's recording date |
| Title | The match's title | "Match NAME_1 vs NAME_2", translated on the page |
| Set starts | `"m:ss"`, the first set 1's: the rallies before it (the warm-up) are left out | The detected set starts, the first `"0:00"` |
| Final scores | `"25-21"`, team 1 first | Unknown |
| `end` | `"m:ss"`, the end of the match ("Fin du match" in the review's Match tab): what follows is left out | The end of the video |

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
[teams benchmark](../benchmarks/teams/README.md)). Teams that keep their ends between sets get no new
set: give the set starts with `--sets` or at the prompt. The final scores show on the page once a set is
over, and the report gives the estimated score's drift from them.

## 3. Review and name the players

```bash
uv run python -m volleyball_stats.review                 # opens on the list of the matches
uv run python -m volleyball_stats.review outputs/matches/VIDEO   # opens on this match
```

The list shows the matches `match --players` has run on (`outputs/matches/VIDEO/source.json` holds their video and court), one still
being processed greyed out; "Changer de match" goes back to it from a review. Choosing another match restarts the server on it,
which waits for an apply in progress to end. `--video`, `--court`, `--squad` and `--roster` override what is saved.

`review` opens, on this machine only, on the **"Noms" tab** (below), then asks about the players the
identity step is least sure of, most at stake first. Each question shows the player outlined on a
looping video, zoomed on them ("Voir toute l'image" for the whole frame), and pictures of the
players they could be, with the names already given.

| Key | Answer |
| --- | --- |
| 1, 2 | That number |
| 3 | Someone else |
| X | Not a player |
| S | Don't know |

For two numbers never on court together: 1 for the same person, 2 for two people.

- **Answers** are saved at once to `identity_answers.json` and hold as hard constraints. Undoing one
  not applied yet is instant.
- **"Ou choisissez qui c'est"** answers a question with any player of either team: type part of a
  name, Enter picks the one left. **"La personne change ici"** (C), the clip paused when the outlined
  person changes, cuts the piece of track there into two players.
- Only doubts with 10 s or more at stake are asked (a touch counting as 10 s): the questions end.
- **A warning** shows the players holding two names after an apply, with the answers joining them:
  a filmstrip of each piece (two people: cut between them; one: forget the answer whose name does not
  match), and every answer pinned on those names, each correctable. An answer that would join two
  named players asks first.
- **"Plus d'images de …"** on a card shows the 24 pieces looking most like the player (same team,
  never on court at the same time as their card's pictures): click those showing someone else and
  confirm, the rest are them.
- **The keyboard** in "Noms": ↑ ↓ between cards, ← → between pictures, Space marks a picture (type the
  name, Enter), N names the player.
- **Jersey numbers** (footage of 1440p or more) join the pieces read with one number and part two
  numbers: a step of `match`, about an hour on 4K, writes `jerseys.csv`, kept for the next runs and
  read by every apply. "Noms" fills the number read and suggests first the roster's player wearing
  it; a card without one takes what its pictures read (`jersey_pictures.json`).
  Each team's numbers are its own. RapidOCR reads the torsos; a piece keeps a number read
  twice and never contradicted, and a number seen on two pieces at once (two people wear it) joins
  nobody.
  A piece your answers give another number's player follows the answer alone.
- **The score board** the scorer flips near the camera is read before each serve (RapidOCR, a step of
  `match`, `scoreboard.csv`, kept for the next runs): the review reports the rally after which the
  running score parts from it ("Score après l'échange différent du tableau", `review.board_off`).
- **Apply** shows its steps on a progress bar; pictures are cut ahead and kept in
  `outputs/matches/VIDEO/crops/`.
- **Apply** comes back without waiting for the players' pictures and the jersey numbers they read:
  they follow in the background, each kept (`photo_moments/`, `jersey_pictures.json`) under a stamp of
  the video, the code and the locked dependencies, so a change of any of them makes them again.
- **A picture showing someone else**, in a question or in "Noms": click it, then say who it is if you
  know, or that it is not a player. On "Apply", that piece of track becomes that player (or someone
  else, or no one) and leaves the other pictures' player. A player whose pictures are all marked is
  no longer offered, and players with the same name are offered once. A name or a choice pinned on
  a picture marked as someone else moves to the player's first picture left.
- **"Apply"** (or "undo") reruns the identity step and rebuilds the match page in seconds, keeping
  the other numbers.
- **The identity step also reruns alone:**
  `uv run python -m volleyball_stats.identity outputs/matches/VIDEO --video VIDEO [--squad N[,N]]`.

The **"Noms" tab** names the players: pictures of each one, a name and an optional jersey number,
which the page then shows instead of the match number.

- Names are saved at once to `player_names.json` and apply like answers: one name is one player, two
  names two, so naming two numbers alike joins them.
- Applying also updates the roster (`--roster`, `outputs/roster.json` by default, outside the
  repository since it names people): each named player's appearance over their last 5 matches. Its players follow a team's name
  however it changes.
- "Noms" offers both teams' names: one of the other team moves the card there on "Apply".
- The next matches suggest names from it, to confirm with a click. On two clips of the same club,
  the right name came first for 7 of 12 players, and among the 3 shown for 9.
- Answers and names refer to pieces of player tracks: tracking the players again (`--force`) drops
  them.

## 4. Build the match page

```bash
uv run python -m volleyball_stats.web outputs/matches/VIDEO --video VIDEO --court CALIBRATION_JSON [--club N] [--footage none|full|blur-opponents|blur-all] [--pictures] [--copy-video] [--theme NAME]
```

`web` builds the page in `outputs/matches/VIDEO/site/`: open `index.html` (French by default). What it shows
is described in [The match page](match-page.md).

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
  for the neutral one; see [`branding/brand.example.json`](../branding/brand.example.json)): logo and
  club name in a band at the top linking to `url`, accent colours, page and card styles per colour scheme.
- **Choices are saved** in `outputs/matches/VIDEO/page.json`: rebuild with only the flag to change
  (`--no-pictures`, `--footage none`...). A build with `--out` (to host) neither reads nor saves
  them: no video nor pictures unless its own flags ask.
- **The review page** builds its own copy with the video in `outputs/matches/VIDEO/review/`, and rebuilds the
  published page on "apply".

## 5. Host the matches

The same files open from disk and host well (Lighthouse mobile performance 82 on a whole match without
footage, desktop 99).

The hosted page has no password, so it never carries real footage or player pictures (nor anything
cut from them) without every player's consent. To host the matches:

1. Build each one with `--footage none --no-pictures --out SITE/NAME`, any NAME.
2. List them, newest first, on `SITE/index.html`: `uv run python -m volleyball_stats.matches SITE`
   (again after each new match). It renames each folder after the match's date and teams' names,
   its address: `SITE/2026-10-25-aspom-begles-vs-talence/`. A new build of a match replaces its
   folder.
3. Copy `SITE` to a server that supports gzip (nginx does).
4. Set long cache headers on `assets/`.

With every player's consent, `--footage ... --copy-video` adds the video: the server then needs HTTP
range requests too.
