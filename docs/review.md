# The review

How it runs, what it asks, its Match tab. Hosting: [hosting.md](hosting.md).

- A match's review: `uv run python -m volleyball_stats.review outputs/matches/MATCH` (http://127.0.0.1:8765, `/review#questions`, `/review#match`). Each apply
  rebuilds the pages, its "Mettre en ligne" uploads the hosted ones when the owner wants, the first time asking with the video and a password, or without it (`outputs/matches/MATCH/publish.json`); "Mettre à jour tous les matchs en ligne" (the "..." menu) rebuilds every match online and uploads them at once; "Apprendre de mes réponses"
  retrains the learned attribution and reruns the pipeline (`learn --rerun`: 3 min on the M4 with the poses cached, 40 without), moving the answers onto
  the new windows itself (`learn.rerun`, `rekey`). Before stopping the review (a restart is needed for a server or page change), check that
  `curl -s 127.0.0.1:8765/progress` gives `{}`: otherwise an apply is running. `outputs/feedback/feedback-conflicts.log` is no viewer's: Claude's note on two
  answers that disagreed (merged). The review's progress names each step and the pipeline's stage, with the time left from each one's last duration
  (`outputs/matches/MATCH/review_timings.json`). A run that fails opens an alert with its step and error, even after a reload, until closed (`/failure`); the traceback is in the server's log. `uv run python -m volleyball_stats.learn outputs/matches/MATCH --video VIDEO --court COURT` scores every step on the
  answers and the checked rallies, against its last run (`learn.json`).
  Stats: a serve, an attack or a block the other team's next touch, the rally's last, loses is a point for it, that
  touch staying the other team's fault (both count; a serve's is an ace); an attack
  blocked for a point is a fault (`web.credited`). That is the statistics' reading only: the labels stay what happened, the attack in play (the owner's rule, `label` on the page's touch, `web.labelled`), so a label's point or fault before another touch warns. The viewers' "Signaler" reports ([hosting.md](hosting.md)) are the main source of
  corrections: fetch them, record the clear ones (a named player on a replayed touch, "pas une phase de jeu") as pending review answers, leave
  the rest (no comment, unsure) to the review's Match tab, which lists each rally reported; then score and fix
  the steps they point at. Kili labels (`docs/kili_labelling.md`) only where reports are not enough.
  The review also asks every touch its page credits to no named player (a player on court under
  `web.BRIEF_S` of a set is a tracking slip) and who missed every ace its page counts as a missed reception
  (`review.aces`, read from the page): the page should show no unidentified player.
- The review opens without a match on the list of the matches (`review.match_list`, those with a `source.json`); opening one replaces the server's process (`review.switch`).
- The list's "La saison" tab reads each match's `review/data.js` (`/matches/NAME/data.js`); hosted, each match's `data.js` ([plan.md](plan.md)).
- A match is named by its date and teams (`rename.target_name`): changing a team's name in the review renames its folders, video and backups, and restarts the server (`rename.py`); the old name stays an alias (`source.json`) for reports and viewers' choices. The hosted page follows on its next upload, with a redirect from its old address (`matches.write_redirects`).
- Timeouts (`timeouts.py`): found from the empty court or a long gap in a set (`timeouts.csv`), shown as dashed bands on the Match tab's bar and in its list between the rallies: pick the team, move its start or end to the video's moment, remove one, add one (the whole gap of `rallies.csv` the video is in, the rallies added in the review not counted; `timeouts.json`, in frames: a rerun keeps them). In the review only, on no page yet.
- The review's Match tab (`#match`) holds the reports and opens on the first rally not checked. The video plays the match freely, with its sound (a button cuts it), the arrow keys moving it by 1 s, and zoom (buttons, ⌘ or Ctrl + wheel or a pinch, a drag moves the view; "Zoom auto" frames all the players, a view for the serve, from the rally before's end and showing the server by the ball (often too far back to be tracked), and one for the exchange, each kept while it fits: `framing.py`, on the two matches 1.1 changes a rally at 1.4× median; zooming by hand overrides it until the next rally, its button resuming it sooner), over a zoomable bar of every rally, touch, report (red flag) and warning (orange flag: on its touch, else the rally's start; an automatic report only where the editor finds no warning on its rally).
  Beside it, the touches around the video: correct, add (a serve before a rally starts it, and the
  touches added after it are that rally's), remove, end a rally (`end` answers), join two rallies (`join` answers), start a rally
  at a moment (`split` answers: one missed, or the second of two taken for one; `web.rally_table`).
  A rally checked is locked as it showed: its winner (`pinned`), touches (`locked`: a rerun loses or adds
  none), their players and actions (`touch`, `action`); no question its check answers is asked; unchecking
  unlocks it. A rally's winner follows its last touch (`web.followed`). "Valider"
  in a rally's header saves and checks it: green, its reports handled, until a new report; the button then
  becomes "Invalider", which unchecks it, or "Valider" again while the rally has unsaved corrections. On a rally with no touch and no end said, "Supprimer" takes its place: saved at once, no play (`play`), or its split undone if the review started it; "Rétablir" takes it back until the apply. Saved corrections not yet in the review's page show in the editor (the
  last report answer carries them all, `review.superseded`). Automatic reports (`review.unusual`)
  flag no serve first, two serves, a reception not right after a serve, a serve not followed by a
  reception, four touches in a row, the wrong server, no touch, no winner, a set ending off the
  score given (`scoreOff`, asked again once the score moves; the list shows the running score), the score board gaining more points than rallies played between two readings, the next one keeping that lead, a rally to replay allowed to explain one (`missedPoint`, `review.missed_points`: none on the first match, 26 of its 129 rallies found hidden in turn, for lack of readings), over 2.5 s between two touches, a server out of rotation order, one jersey on two players of a team (allowed, the owner's: both may wear no team jersey; handled once), the running score parting from the score board's for two readings in a row (`boardOff`, `scoreboard.py`: the board read before each serve, a misread one dropped, its sides fitted set by set). A rally between two equal board readings (`boardStill`, to replay or false) and a last touch scoring with no net crossing after it, a block apart (`notOver`, `review.crossings`: `net.csv` stops with the windows) are reported too, but never on a rally checked: a new check reopens none. The editor also flags what may be right after all, on its touch and gone once the rally is checked (`checks.ts`, `doubtful`): a touch seen twice, a team playing on after its attack or relance, a set going to the other team, a set as first touch, a dig or reception after the team's own touch, two sets in a row, a rally ending on a set, a point on a reception or dig (not a relance: it happens), an ace. Scored on the pipeline's rallies against the corrections: a flag sits on a correction 82-100% of the time on both matches, 40% by chance. Rejected: over 2 s between touches (61% on the first match), a floor contact on a player (47%), a team change without a net crossing (37 left on checked rallies: crossings go unseen). No winner, a set's score, the board and a missed point sit at the rally's end, after its touches; the others at its start or their touch. Rallies are named by
  their `rallies.csv` start (`key` on the page), which an added serve moves. Joined (`liveReports`), rallies are checked as one, at once: their automatic reports wait for the next apply, a player's jersey apart. A line between rallies
  shows the score after each one; a rally header turns orange with a warning; the match bar colours
  each rally (orange warning, green checked, grey to check) and its arrows go to the next one to
  check. "Faute de jeu" (`fault`): a fault without the ball (net, centre line, rotation), only added in
  the review: always a fault, no touch of the ball in the checks, counted in its player's faults.
  "À rejouer" (`redo`, beside the winners): the rally stays, its touches in play, nobody scores; picking
  a winner takes it back. "Erreur d'arbitrage" (`referee` answers, `wrongCall` on the page): the winner stays the
  team that got the point, the score follows it, the last touch keeps what really happened: the true
  winner is the other team. Nothing trains on how rallies end yet: such training reads these answers. The rally's "Commentaire": the owner's note, in the review only
  (`rally_comments.json`, moved by a rerun; on no page, so never hosted), saved on leaving the field. The star on a touch puts it in the films, the match's and its player's (`film.PICKS`, by frame, saved at once; a rerun's touch within 0.3 s takes it).
