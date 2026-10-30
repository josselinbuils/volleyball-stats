# Identity benchmark

`volleyball_stats.identity` links the player tracks of `players.py` into one identity per real
player for the whole match, numbered 1, 2, ... per team, so a player keeps the same number on the
page from the first serve to the last ball. Scored against hand-labelled identities: tuned on
`side_holdout`, held out `side_setend` (a set end, the break, the change of ends and set 2).

## Use

`match.py --players` runs it after the teams; alone, on a match folder run with `--players`:

```bash
uv run python -m volleyball_stats.identity outputs/VIDEO --video VIDEO [--squad N[,N]]
```

writes `identities.csv` (`track,start_frame,end_frame,team,identity,runner_up,confidence`: one row
per piece of track, identity 0 for none), `identity_candidates.json` (the least sure pieces and
pairs of identities, ranked by seconds of play and contacts at stake) and the embedding cache
`embeddings.npz`, and refreshes the `identity` column of `actions.csv`. A rerun without new tracks
takes seconds and keeps the previous numbers. `identity_answers.json`, the user's answers, overrides
the model:

```json
{
  "same": [[{"track": 12}, {"track": 40, "frame": 5210}]],
  "different": [[{"team": 1, "identity": 3}, {"track": 77}]],
  "not_player": [{"track": 5}]
}
```

A reference is a whole track, the piece of a track holding a frame, or an identity of the previous
run. `--squad` (team 1 first) caps the identities per team. The names given on the review page
(`player_names.json`, a reference per name) are constraints too: one name one player, two names
two.

## Run

```bash
uv run --group bench python benchmarks/identity/bench.py side_holdout side_setend [--squad N[,N]] [--baseline tracks|colour]
GRID="NEW=0.8,0.9 CONTINUITY=0.2,0.3" uv run --group bench python benchmarks/identity/bench.py side_holdout --sweep
```

Each clip reads `data/CLIP.mp4` and `outputs/CLIP/` from `match.py --players` (players.csv,
rallies.csv). The embedding cache is keyed by piece of track only: delete `embeddings.npz` before
sweeping `CROPS`, `CLEAR`, `HALF` or the crowd constants. About 1 minute per clip on the M4 Pro
(MPS) without the cache, seconds with it.

## Answers held out

`answers.py` scores the step on a match's own review answers: each half of
`identity_answers.json` held out in turn, the step run with the other half (names and cuts always
kept), the held-out "same" groups and "different" pairs checked (37 s on the first ASPOM match).

```bash
uv run python benchmarks/identity/answers.py outputs/first_match --video data/first_match.mp4
```

First ASPOM match, 143 answers and 37 names (one club, one kit for both teams): 181/329 held-out
constraints kept (55%) before `sharpen`, 201/329 (61%) with it at `SHARPEN` 0.5 (199, 60%, at 1).
The questions were asked where the step doubted, so about half is the floor. Counting the pictures
left unmarked in a card as one player adds nothing (61%). The school clips, without answers, keep
their IDF1 (0.895 and 0.806).

## Ground truth

`ground_truth/<clip>.csv`: `frame,player,x1,y1,x2,y2,track`, every tracked on-court player on
frames 2 s apart. `player` is the team's jersey colour (`W` white, `N` navy) and the jersey number
when it was readable on a zoomed crop, `L` for the libero, a letter for a player whose number never
was; `?` unsure (left out), `X` not a player (counts against precision). Identities were followed
with jersey numbers, hair, shoes, height and position continuity on 3× crops.

| Clip | Stretch | Frames | Labelled boxes | Players |
| --- | --- | --- | --- | --- |
| `side_holdout` (tuning) | 0:00-5:00, 15 rallies and the breaks | 151 | 1,373 | 15 |
| `side_setend` (held out) | 0:00-1:04 (set 1 end) and 7:08-9:12 (set 2, teams on the other ends) | 96 | 908 | 16 |

## Metric

- **IDF1** (IDP, IDR): labelled boxes whose identity is the one paired with their player, players
  and identities paired one to one by shared boxes. **IDR** is the share of player dots showing
  their player's number on the page.
- **splits**: identities per player; **merges**: players per identity.
- **ceilings**: IDF1 when every track, then every piece of track, takes its majority player: what
  linking whole tracks or pieces can reach.
- **number changes**: a player's consecutive labelled boxes in one rally (2 s apart) showing two
  numbers, printed per clip.

## Method

Tracks swap players where two cross (at the net, in the huddles after a point): linking whole
tracks caps IDF1 at 0.82-0.88. Each track is cut in the middle of every crowd episode (its box
under another one by 30% or more), into pieces that hold one player 97-99% of the time. A piece is
described by an OSNet-AIN re-identification embedding (MSMT17 weights, MIT, vendored in
`src/volleyball_stats/vendor/`): the whole box plus its upper and lower halves, averaged over up to
12 of its clearest boxes, then whitened within its team, since teammates share the jersey and differ
in faint directions (hair, shorts, shoes, height). Per team, pieces are taken in time order and
handed to identities by an optimal assignment on the distance to each identity's prototype, under
hard constraints: two pieces seen at the same time, or too far apart for a run in the time between
them, are never one player; the next piece of the same track leans to its identity. Pieces of 5 s
or more build the identities (two passes, the second with the prototypes fixed), the shorter ones
join the nearest identity they can; identities never longer than 10 s get no number. Starters are
numbered by zone at the first serve (1 back right ... 6 back middle), the others by first
appearance. Inside a rally, no labelled track changed player at a cut (0 of 61) while the pieces'
numbers changed at 16% of the cuts: there each track then holds one number, the one of most of its
frames, unless a track seen at the same time holds it with more.

| Method | Tuning IDF1 | Held-out IDF1 | Identities / players (tuning, held out) |
| --- | --- | --- | --- |
| Tracks alone (`--baseline tracks`) | 0.339 | 0.436 | 92 / 15, 66 / 16 |
| Colour embedding instead of re-ID (`--baseline colour`) | 0.690 | 0.646 | 22 / 15, 19 / 16 |
| Average-linkage clustering of the pieces, re-ID (first version) | 0.71-0.72 | - | 36-45 / 15 |
| Time-ordered assignment, re-ID, whitened | 0.894 | 0.800 | 20 / 15, 21 / 16 |
| **Same, one number per track inside a rally (`identify`)** | **0.895** | **0.806** | 20 / 15, 21 / 16 |
| Same with the squad given (`--squad 8,7`, `--squad 9,7`) | 0.894 | 0.826 | 15 / 15, 16 / 16 |

Per team (white / navy): 0.924 / 0.888 tuning, 0.841 / 0.775 held out. Splits 1.33 and 1.40,
merges 1.07 and 1.14. Number changes in a rally: 0 of 33 tuning, 4 of 153 held out (1 and 16
before the rally hold). The page shows no number on 1.8% of the player dots of `side_setend`.

## Failures

- **Splits** make most of the loss: a player seen from the back, then from the front, or far then
  near, can become two identities. The held-out navy team (0.775) loses most across the change of
  ends, where every player moves to the other half and is seen at another scale.
- **Merges**: two teammates never on court together (a substitution, the libero and the player
  they replace) look alike in the same jersey and can share an identity: nothing forbids it.
- Short pieces (crowd episodes at the net) are assigned last, with little evidence.
- The 4 number changes left in a rally are hand-overs: the tracker loses a player at the net and a
  new track picks them up 1-9 frames later, 2-6 m away on the floor (half-hidden feet), too far to
  join them by position.

## Limits and next steps

- 720p footage: jersey numbers are unreadable. On 4K, numbers read on clear boxes enter
  `identify` as `jerseys` (same number one player, two numbers two), the strongest clue.
- The user's answers on the doubtful pieces (`identity_candidates.json`) fix the rest; the review
  page asks them on the video.
- Two clips of the same club and camera; the constants need a check on the user's footage.
- Long matches: the cannot-links are kept per piece, the pairs of a team close in time only. On a
  match of 43,000 pieces (the player rows of 2 hours at 50 fps, `benchmarks/scale.py`) the step
  takes 48 s and 6.3 GB at its peak, half of it the players' rows; a dense pieces x pieces matrix
  needed over 20 GB.
