# The review

How it runs, what it asks, its Match tab. Hosting: [hosting.md](hosting.md).

- A match's review: `uv run python -m volleyball_stats.review outputs/MATCH` (http://127.0.0.1:8765, `/review#questions`, `/review#match`). Each apply
  rebuilds the pages, its "Mettre en ligne" uploads the hosted ones when the owner wants (`outputs/MATCH/publish.json`); "Apprendre de mes réponses"
  retrains the learned attribution and reruns the pipeline (`learn --rerun`: 3 min on the M4 with the poses cached, 40 without), moving the answers onto
  the new windows itself (`learn.rerun`, `rekey`). Before stopping the review (a restart is needed for a server or page change), check that
  `curl -s 127.0.0.1:8765/progress` gives `{}`: otherwise an apply is running. `outputs/feedback-conflicts.log` is no viewer's: Claude's note on two
  answers that disagreed (merged). The review's progress names each step and the pipeline's stage, with the time left from each one's last duration
  (`outputs/MATCH/review_timings.json`). `uv run python -m volleyball_stats.learn outputs/MATCH --video VIDEO --court COURT` scores every step on the
  answers and the checked rallies, against its last run (`learn.json`).
  Stats: a serve, an attack or a block the other team's next touch, the rally's last, loses is a point for it, that
  touch staying the other team's fault (the owner's rule: labelled so, both count; a serve's is an ace); an attack
  blocked for a point is a fault (`web.credited`). The viewers' "Signaler" reports ([hosting.md](hosting.md)) are the main source of
  corrections: fetch them, record the clear ones (a named player on a replayed touch, "pas une phase de jeu") as pending review answers, leave
  the rest (no comment, unsure) to the review's Match tab, which lists each rally reported; then score and fix
  the steps they point at. Kili labels (`docs/kili_labelling.md`) only where reports are not enough.
  The review also asks every touch its page credits to no named player (a player on court under
  `web.BRIEF_S` of a set is a tracking slip): the page should show no unidentified player.
- The review opens without a match on the list of the matches (`review.match_list`, those with a `source.json`); opening one replaces the server's process (`review.switch`).
- A match is named by its date and teams (`rename.target_name`): changing a team's name in the review renames its folders, video and backups, and restarts the server (`rename.py`); the old name stays an alias (`source.json`) for reports and viewers' choices. The hosted page follows on its next upload, with a redirect from its old address (`matches.write_redirects`).
- Timeouts (`timeouts.py`): found from the empty court or a long gap in a set (`timeouts.csv`), shown as dashed bands on the Match tab's bar and in its list between the rallies: pick the team, remove one, add one at the video's moment (`timeouts.json`, in frames: a rerun keeps them). In the review only, on no page yet.
- The review's Match tab (`#match`) holds the reports. The video plays the match freely, with its sound (a button cuts it) and zoom (buttons, ⌘ or Ctrl + wheel or a pinch, a drag moves the view), over a zoomable bar of every rally, touch and report.
  Beside it, the touches around the video: correct, add (a serve before a rally starts it, and the
  touches added after it are that rally's), remove, end a rally (`end` answers), join two rallies (`join` answers), start a rally
  at a moment (`split` answers: one missed, or the second of two taken for one; `web.rally_table`).
  A rally checked is locked as it showed: its winner (`pinned`), touches (`locked`: a rerun loses or adds
  none), their players and actions (`touch`, `action`); no question its check answers is asked; unchecking
  unlocks it. A rally's winner follows its last touch (`web.followed`). "Valider"
  in a rally's header saves and checks it: green, its reports handled, until a new report; the button then
  becomes "Invalider", which unchecks it, or "Valider" again while the rally has unsaved corrections. Saved corrections not yet in the review's page show in the editor (the
  last report answer carries them all, `review.superseded`). Automatic reports (`review.unusual`)
  flag no serve first, two serves, a reception not right after a serve, a serve not followed by a
  reception, four touches in a row, the wrong server, no touch, no winner, a set ending off the
  score given (`scoreOff`, asked again once the score moves; the list shows the running score), then the moments the ball seems in play outside that set's rallies (`missedPoint`, `review.missed_points`: of 129 rallies hidden in turn, its 5 per set hold 86), over 2.5 s between two touches, a server out of rotation order, one jersey on two players of a team (allowed, the owner's: both may wear no team jersey; handled once), the running score parting from the score board's for two readings in a row (`boardOff`, `scoreboard.py`: the board read before each serve, a misread one dropped, its sides fitted set by set). Rallies are named by
  their `rallies.csv` start (`key` on the page), which an added serve moves. A line between rallies
  shows the score after each one; a rally header turns orange with a warning; the match bar colours
  each rally (orange warning, green checked, grey to check) and its arrows go to the next one to
  check. "Faute de jeu" (`fault`): a fault without the ball (net, centre line, rotation), only added in
  the review: always a fault, no touch of the ball in the checks, counted in its player's faults.
  "À rejouer" (`redo`, beside the winners): the rally stays, its touches in play, nobody scores; picking
  a winner takes it back. "Erreur d'arbitrage" (`referee` answers, `wrongCall` on the page): the winner stays the
  team that got the point, the score follows it, the last touch keeps what really happened: the true
  winner is the other team. Nothing trains on how rallies end yet: such training reads these answers. The rally's "Commentaire": the owner's note, in the review only
  (`rally_comments.json`, moved by a rerun; on no page, so never hosted), saved on leaving the field.
