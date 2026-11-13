# The review

How it runs, what it asks, its Match tab. Hosting: [hosting.md](hosting.md).

- [Running it](#running-it)
- [Applying and learning](#applying-and-learning)
- [The statistics' reading](#the-statistics-reading)
- [What it asks](#what-it-asks)
- [The match list, renames, timeouts](#the-match-list-renames-timeouts)
- [The Match tab](#the-match-tab)

## Running it

- A match's review: `uv run stats server MATCH` ([running.md](running.md)): http://127.0.0.1:8765/review, `#questions`,
  `#match`; http://127.0.0.1:8765 is always the list.
- `uv run stats stop` refuses while an apply runs (`curl -s 127.0.0.1:8765/progress` gives `{}` once none does).
- The progress names each step and the pipeline's stage, with the time left from each one's last duration
  (`outputs/matches/MATCH/review_timings.json`).
- A run that fails opens an alert with its step and error, even after a reload, until closed (`/failure`); the traceback
  is in the app's log.
- The app's log: what the server prints, kept in `outputs/app.log` too (`applog.py`, trimmed past 2 MB), shown by
  "Journal de l'app" in Diagnostic and by "Voir le détail" beside a failure (`/app/log`): the shortcut starts the app
  with no terminal.
- `outputs/feedback/feedback-conflicts.log` is no viewer's: Claude's note on two answers that disagreed (merged).

## Applying and learning

- Each apply rebuilds the pages.
- "Mettre en ligne" uploads the hosted ones when the owner wants, the first time asking with the video and a password, or
  without it (`outputs/matches/MATCH/publish.json`). "Mettre à jour tous les matchs en ligne" (the "..." menu) rebuilds
  every match online and uploads them at once.
- "Apprendre de mes réponses" (the Progrès tab; checked while its last run saw the answers as they stand: `review.learned`,
  `learn.json`'s `answers`) retrains the learned attribution and reruns the pipeline (`learn --rerun`: 3 min on the M4 with
  the poses cached, 40 without). It moves the answers onto the new windows itself (`learn.rerun`, `rekey`; a rally the
  review added that the pipeline now finds moves onto its window).
- On a match whose every rally is checked it only retrains and measures (`learn.retrain`, shown in "Progrès"), then trains
  the play model again when such matches' checked rallies changed since its last training (`learn.train_play`,
  `play_training`: a quarter of an hour on an NVIDIA card, hours without). The match stays as reviewed (`review.reviewed`),
  and the review asks only what teaches the next matches: who made a touch, a piece or two players whose answer may mend
  a touch the training reads (`review.untaught`).
- `uv run python -m volleyball_stats.learn outputs/matches/MATCH --video VIDEO --court COURT` scores every step on the
  answers and the checked rallies, against its last run (`learn.json`).

## The statistics' reading

- A serve, an attack or a block the other team's next touch, the rally's last, loses is a point for it, that touch staying
  the other team's fault (both count; a serve's is an ace). An attack blocked for a point is a fault (`web.credited`).
- That is the statistics' reading only: the labels stay what happened, the attack in play (the owner's rule, `label` on
  the page's touch, `web.labelled`), so a label's point or fault before another touch warns.
- A fault may be put on a teammate's earlier touch of the rally, a bad set or reception (the Match tab, under the fault's
  player: "Sa faute" or "À cause de"; `cause` in the `action` answer, `web.blamed`): the statistics count it for that
  touch's player, graded 0, and no longer for the one who made it, whose touch is left ungraded (the owner's rule, 13 Nov).

## What it asks

- Who a piece of track is (pieces and merges, most at stake first) comes before the other questions: one answer names
  every touch on it, and a rally checked in the Match tab answers the rest. Answer them and apply before the Match tab.
- The viewers' "Signaler" reports ([hosting.md](hosting.md)) are the main source of corrections. "Charger les
  signalements" fetches them; record the clear ones (a named player on a replayed touch, "pas une phase de jeu") as
  pending review answers, leave the rest (no comment, unsure) to the Match tab, which lists each rally reported; then score
  and fix the steps they point at.
- Every touch its page credits to no named player (a player on court under `web.BRIEF_S` of a set is a tracking slip), and
  who missed every ace its page counts as a missed reception (`review.aces`, read from the page): the page should show no
  unidentified player.

## The match list, renames, timeouts

- The review opens without a match on the list of the matches (`review.match_list`, those with a `source.json`); opening
  one replaces the server's process (`review.switch`).
- The list's "La saison" tab reads each match's `review/data.js` (`/matches/NAME/data.js`); hosted, each match's `data.js`
  ([history.md](history.md)).
- A match is named by its date and teams (`rename.target_name`): changing a team's name in the review renames its folders,
  video and backups, and restarts the server (`rename.py`); the old name stays an alias (`source.json`) for reports and
  viewers' choices. The hosted page follows on its next upload, with a redirect from its old address
  (`matches.write_redirects`).
- Timeouts (`timeouts.py`): found from the empty court or a long gap in a set (`timeouts.csv`), shown as dashed bands on
  the Match tab's bar and in its list between the rallies. Pick the team, move its start or end to the video's moment,
  remove one, add one (the whole gap of `rallies.csv` the video is in, the rallies added in the review not counted).
  Kept in `timeouts.json`, in frames: a rerun keeps them; a change waits for the apply. The page shows them
  ([match-page.md](match-page.md)).

## The Match tab

`#match` holds the reports and opens on the first rally not checked.

### The video

- It plays the match freely, with its sound (a button cuts it), the arrow keys moving it by 1 s.
- Zoom: buttons, ⌘ or Ctrl + wheel or a pinch, a drag moves the view. "Zoom auto" frames all the players: a view for the
  serve, from the rally before's end and showing the server by the ball (often too far back to be tracked), and one for
  the exchange, each kept while it fits (`framing.py`; on the two matches 1.1 changes a rally at 1.4× median). Zooming by
  hand overrides it until the next rally, its button resuming it sooner.
- Under it, a zoomable bar of every rally, touch, report (red flag) and warning (orange flag: on its touch, else the
  rally's start; an automatic report only where the editor finds no warning on its rally). It colours each rally (orange
  warning, green checked, grey to check) and its arrows go to the next one to check.

### Correcting

- Beside the video, the touches around it: correct, add (a serve before a rally starts it, and the touches added after it
  are that rally's), remove, end a rally (`end` answers), join two rallies (`join` answers), start a rally at a moment
  (`split` answers: one missed, or the second of two taken for one; `web.rally_table`).
- Rallies are named by their `rallies.csv` start (`key` on the page), which an added serve moves. A line between rallies
  shows the score after each one; a rally header turns orange with a warning.
- A rally's winner follows its last touch (`web.followed`).
- "Faute de jeu" (`fault`): a fault without the ball (net, centre line, rotation), only added in the review: always a
  fault, no touch of the ball in the checks, counted in its player's faults.
- "À rejouer" (`redo`, beside the winners): the rally stays, its touches in play, nobody scores; picking a winner takes it
  back.
- "Erreur d'arbitrage" (`referee` answers, `wrongCall` on the page): the winner stays the team that got the point, the
  score follows it, the last touch keeps what really happened: the true winner is the other team. Nothing trains on how
  rallies end yet: such training reads these answers.
- "Commentaire": the owner's note on a rally, in the review only (`rally_comments.json`, moved by a rerun; on no page, so
  never hosted), saved on leaving the field.
- The star on a touch puts it in the films, the match's and its player's (`film.PICKS`, by frame, saved at once; a rerun's
  touch within 0.3 s takes it).
- "Fin du match à …" (the video's moment) and taking it back are in the "..." menu.
- So are "Nouveau set à …" and "Retirer le début du set N" (the set the video is in; `review.set_start`, teams.json's
  `sets`): a set starts at the rally playing or the next one, its start the middle of the break before it, a start
  already in that break giving way. The pipeline runs again then (no training; on a reviewed match too): the sides of
  teams in one kit change at each set start.

### Checking a rally

- "Valider" in a rally's header saves and checks it: green, its reports handled, until a new report. The button then
  becomes "Invalider", which unchecks it, or "Valider" again while the rally has unsaved corrections.
- A rally checked is locked as it showed: its winner (`pinned`), touches (`locked`: a rerun loses or adds none), their
  players and actions (`touch`, `action`); no question its check answers is asked. Unchecking unlocks it.
- Joined (`liveReports`), rallies are checked as one, at once: their automatic reports wait for the next apply, a player's
  jersey apart.
- Any rally not joined can be deleted (the bin in its header; on one with no touch and no end said, "Supprimer" takes the
  place of "Valider"): saved at once, no play (`play`), or its split undone if the review started it. "Rétablir" takes it
  back until the apply.
- Corrections not validated are lost by a reload, an action that reloads or leaving the tab: the review asks first. Saved
  corrections not yet in the review's page show in the editor (the last report answer carries them all,
  `review.superseded`).

### Automatic reports and flags

Automatic reports (`review.unusual`) flag:

- no serve first, two serves, a reception not right after a serve, a serve not followed by a reception, four touches in a
  row, the wrong server, no touch, no winner, over 2.5 s between two touches, a server out of rotation order;
- a set ending off the score given (`scoreOff`, asked again once the score moves; the list shows the running score);
- the score board gaining more points than rallies played between two readings, the next one keeping that lead, a rally to
  replay allowed to explain one (`missedPoint`, `review.missed_points`: none on the first match, 26 of its 129 rallies
  found hidden in turn, for lack of readings);
- the running score parting from the score board's for two readings in a row (`boardOff`, `scoreboard.py`: the board read
  before each serve, a misread one dropped, its sides fitted set by set);
- one jersey on two players of a team (allowed, the owner's: both may wear no team jersey; handled once).

A rally between two equal board readings (`boardStill`, to replay or false) and a last touch scoring with no net crossing
after it, a block apart (`notOver`, `review.crossings`: `net.csv` stops with the windows) are reported too, but never on a
rally checked: a new check reopens none. No winner, a set's score, the board and a missed point sit at the rally's end,
after its touches; the others at its start or their touch.

The editor also flags what may be right after all, on its touch and gone once the rally is checked (`checks.ts`,
`doubtful`): a touch seen twice, a team playing on after its attack or relance, a set going to the other team, a set as
first touch, a dig or reception after the team's own touch, two sets in a row, a rally ending on a set, a point on a
reception or dig (not a relance: it happens), an ace. Scored on the pipeline's rallies against the corrections: a flag
sits on a correction 82-100% of the time on both matches, 40% by chance. Rejected: over 2 s between touches (61% on the
first match), a floor contact on a player (47%), a team change without a net crossing (37 left on checked rallies:
crossings go unseen).
