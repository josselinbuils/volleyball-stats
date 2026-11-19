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
  `#match`; its page without the review at http://127.0.0.1:8765/page; http://127.0.0.1:8765 is always the list. Each
  page links back at its top (the app's window has no back button): the page to the review (at `/page`, whatever the
  address: "Réseau local" too), the review to the list.
- "Réseau local" (the list's app panel, `network.py`, off by default) opens the review to the other devices of the local
  network until it closes (the server's own restarts keep it, `network.SESSION`), at every start only when "À chaque
  démarrage" is ticked (`outputs/network.json`), no code (the owner's calls, 16 Nov): the server starts again listening on
  every address and takes requests named by an IP address, a `.local` name or the machine's name (any other name stays
  out: a site rebinding its domain to this machine), other sites' requests still refused. The dialog gives the address
  to type there. Under WSL, "Configurer Windows" first sets `networkingMode=mirrored` in `.wslconfig` (its old copy
  `.wslconfig.bak`) and adds WSL's firewall rule for the port (`New-NetFirewallHyperVRule`, an administrator's approval
  asked), then the computer restarts.
- `uv run stats stop` refuses while an apply runs (`curl -s 127.0.0.1:8765/progress` gives `{}` once none does).
- The progress names each step and the pipeline's stage. Only counted work moves the bar (the owner's rule, 15 Nov):
  each step tells its own share (`shared`, `eta`'s `own`: the apply's rows of `players.csv` and page parts, the films'
  frames searched and shots made, the copies' ffmpeg time), else it holds; steps and stages weigh their last duration
  (`outputs/matches/MATCH/review_timings.json`, kept as the run started). The time left: the counted pace, else the
  last duration.
- A run that fails opens an alert with its step and error, even after a reload, until closed (`/failure`); the traceback
  is in the app's log.
- The app's log: what the server prints, kept in `outputs/app.log` too (`applog.py`, trimmed past 2 MB), shown by
  "Journal de l'app" in Diagnostic and by "Voir le détail" beside a failure (`/app/log`): the shortcut starts the app
  with no terminal.
- `outputs/feedback/feedback-conflicts.log` is no viewer's: Claude's note on two answers that disagreed (merged).

## Applying and learning

- Each apply rebuilds the pages. Its button shows while something differs from the last apply (`review.waiting`); its tip
  lists what (`to_apply`: the answers not applied by what they are about, jersey numbers, time-outs, names). The rallies
  checked that a start locks (`locked`) say what the page shows already: they count as applied (`applied_too`).
- "Mettre en ligne" uploads the hosted ones when the owner wants, the first time asking with the video, behind the videos' one password
  ([hosting.md](hosting.md#the-video-and-its-password)), or without it (`outputs/matches/MATCH/publish.json`). Its video's copies come cut by the automatic zoom
  and shorter than the match ([hosting.md](hosting.md)): once their zoom or time map has changed since they were made (a
  correction moved a rally or a touch, or copies made before 16 Nov), it asks "Refaire les vidéos ?" first; "Plus tard" uploads with them as they are, and "Refaire
  les vidéos au nouveau zoom" (the "..." menu, while they wait) makes them again and uploads (the owner's call, 16 Nov:
  never on its own, hours of encoding). "Mettre à jour tous les matchs en ligne" (the "..." menu) rebuilds
  every match online and uploads them at once. "Exporter le site" (the same menu, a server set or not) zips the pages for
  any host ([hosting.md](hosting.md#without-a-server-the-export)).
- "Réanalyser" (the list of the matches, above its tabs) brings every match waiting up to date in one job of the
  app (`learn.update`, `app.LEARN`, it outlives the review switching matches). In a review, beside the reason it waits,
  it asks "Réanalyser ce match ?" and updates that match only (`/app/learn` with `here`: `learn --update MATCHES
  --only NAME`); the others keep their badge. A match waits (`review.due`, a dot and the reason on its card: the owner's
  naming, 15 Nov) for its answers given since its last learning (`review.learned`, `learn.json`'s `answers`:
  "Réponses à apprendre", no count: the learning keeps only their hash; a report marked "Traité" without a correction
  teaches nothing and does not count, `review.silent`) or for other code or models than those its
  analysis was made with ("Nouvelle version de l'analyse", "Nouvelle version" on the card:
  `analysis.py`'s fingerprint of the pipeline's modules, comments and docstrings left out, of the learned order of who
  touched and of the play model, kept in the match's `analysis.json` by each run; web.py is not part of it, an apply
  rebuilds the pages). The job trains the learned attribution once on every match's answers (each match's held-out
  scores in its `ranker.json`), then reruns the pipeline of each match waiting (the open one alone from a review),
  those the new learned order makes older included (`learn.rerun`: 3 min on the M4 with the poses cached, 40 without),
  rebuilds its pages and applies its answers (`review.rebuilt`). It moves the answers onto the new windows itself
  (`rekey`; a rally the review added that the pipeline now finds moves onto its window). While it runs a review
  refuses every change (409 `updating`) and waits; once it ends the review's server reads its match again (`follow`,
  by its page's time) and the page reloads.
- A match whose every rally is checked keeps its labels: only new answers make it wait, and the update only measures it
  (`learn.measured`), then trains the play model again when such matches' checked rallies changed since its last training
  (`learn.train_play`, `play_training`: a quarter of an hour on an NVIDIA card, hours without). The match stays as reviewed
  (`review.reviewed`), and the review asks only what teaches the next matches: who made a touch, a piece or two players
  whose answer may mend a touch the training reads (`review.untaught`).
- The list's "Progrès" tab (`Progress/Progress.tsx`, in `app.js`: never hosted) shows every run's scores on the answers of
  all the matches measured so far (`review.pooled_runs`) and what the last update changed, summed over its matches on the
  same answers (`review.last_comparison`, its runs' `update` in `learn.json`).
- `uv run python -m volleyball_stats.learn outputs/matches/MATCH --video VIDEO --court COURT` scores every step on the
  answers and the checked rallies, against its last run (`learn.json`).

## The statistics' reading

- Attack or relance by what is seen, never by intent (the owner's rule, 14 Nov): a ball sent over with one hand (a hit, a tip,
  a placed ball, jumped or not) is an attack, on any touch; one played with both hands (forearm or overhead pass) is a dig (or
  reception) on the first touch; on the second, a relance when the other team plays next, a set when its own plays on (by
  what follows: a set gone over by mistake counts as a relance); a relance on the third (`actions.relances_by_touch`,
  `relanceFirst`, `relanceSecond`, `setOver`).

- A serve, an attack or a block the other team's next touch, the rally's last, loses is a point for it, that touch staying
  the other team's fault (both count; a serve's is an ace). An attack blocked for a point is a fault (`web.credited`).
- That is the statistics' reading only: the labels stay what happened, the attack in play (the owner's rule, `label` on
  the page's touch, `web.labelled`), so a label's point or fault before another touch warns.
- A fault may be put on one of the team's two touches just before it, a bad set or reception (the Match tab, under the fault's
  player: "Sa faute" or "À cause de" that touch, an older one picked before still shown; `cause` in the `action` answer, `web.blamed`): the statistics count it for that
  touch's player, graded 0, and no longer for the one who made it, whose touch is left ungraded (the owner's rule, 13 Nov).
- "Faute partagée avec" (the person icon beside a fault's player, `partner` answers, `web.partnered`): a second player of the
  team shares the fault, a full one each in their statistics, once for the team (the owner's rule, 18 Nov).

## What it asks

- Who a piece of track is (pieces and merges, most at stake first) comes before the other questions: one answer names
  every touch on it, and a rally checked in the Match tab answers the rest. Answer them and apply before the Match tab.
  Only pieces worth more than about two touches are asked (`review.MIN_IMPACT`; the rest, a touch each, the Match tab
  answers faster), and the pieces answered leave the list (`identity.doubts`): one round, a few new after an apply.
- A question's video has full screen at its bar's right end, as the Match tab's: no card, the video as large as the
  screen allows, the question, name field, answers and outlined pictures in a column right beside it
  (`hooks/useFullscreen.ts`, shared; the status badge and an error follow it there). In both tabs the video's column
  takes its width (`--video-w`, set by `ClipVideo` on the full-screen block): the Match tab's timeline and rally bar
  are as wide as the video, the column beside starts where it ends, the whole centred.
  Out of full screen too, a question's outlined pictures sit beside the video under the answers (under the video on a
  phone, seen before answering).
- Nobody comes in or goes out during a rally, nor in a short break between two with the same six: once all six named
  players of a team are seen in one, a piece no named player holds takes the one off court while it is on
  (`identity.fill_in`, each apply), and is no longer asked. A card made of other players' pieces empties by itself (17 Nov).
- The viewers' "Signaler" reports ([hosting.md](hosting.md)) are the main source of corrections. "Charger les
  signalements" fetches them; record the clear ones (a named player on a replayed touch, "pas une phase de jeu") as
  pending review answers, leave the rest (no comment, unsure) to the Match tab, which lists each rally reported; then score
  and fix the steps they point at.
- Every touch its page credits to no named player (a player on court under `web.BRIEF_S` of a set is a tracking slip;
  an unnamed identity under a tenth of its team's median time, `identity.leftovers`, gets no card in the review and no
  number on the page, `web.unjoined`: one rule for both, so no touch names a player the review cannot offer), and
  who missed every ace its page counts as a missed reception (`review.aces`, read from the page): the page should show no
  unidentified player.
- A player's card has "Silhouette 3D", a man's or a woman's figure, and "Cheveux", the hair colour guessed from the
  card's picture (`likeness.py`) to correct, or bald (never guessed) (`/look`, saved at once in `likeness_choices.json`
  by name, else by card: the player's other matches take it too, their pages patched at once, their hosted copies then
  late; not a "Joueur N" name, another player in each match; no rebuild). The hairstyle and
  skin stay the guess's alone (the owner's call, 16 Nov).

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

- It plays the match freely, with its sound (a button cuts it), the arrow keys moving it by a frame. Its controls sit in a
  black bar under it, as on the match page (`VideoButton`, shared), full screen at its right end.
- Its seek bar goes frame by frame on a small drag (a frame every 3 px, ±12, the count above the thumb; it pauses the
  video), the bar stretched around the press meanwhile so the thumb stays under the pointer; past that it moves at the
  bar's scale from there, skipping no frames, until released. A press on the thumb grabs it where it stands
  (`helpers/scrub.ts` `stretchedTime`).
- Zoom: buttons, ⌘ or Ctrl + wheel or a pinch, a drag moves the view; the wheel alone scrolls the page, zoomed or not. "Zoom auto" frames all the players: a view for the
  serve, from the rally before's end and showing the server by the ball (often too far back to be tracked), and one for
  the exchange, each kept while it fits (`framing.py`; on the two matches 1.1 changes a rally at 1.4× median). Zooming by
  hand overrides it until the next rally, its button resuming it sooner.
- The snail beside the speeds ("Ralentir à chaque touche", kept in the browser): the video plays at 0.5× from 0.3 s before each touch
  to 0.15 s after it, the touches as corrected (`helpers/slow.ts`, the match page's snail too); the caption over the video and the list's lit row
  change to that touch as it slows down (0.3 s before it, slowed or not), a space apart from the zoom's buttons; the sound's
  button at the right end, beside full screen.
- A click on the caption opens under it (the video paused) the touch's action and result, as in its card, and a player
  field: the touch named takes what is picked; a drag moves the caption.
- Keys, outside the fields (their tips say them): Space plays or pauses; the touch named over the video takes its action by
  its French name's letter (S service, R réception, P passe, A attaque, L relance, C contre, D défense, F faute de jeu, M balle manquée); V
  validates the rally on the video, N adds a touch at its moment. A player picked in a touch's field leaves it, for the
  keys to work again.
- A player field lists first the players with touches in the touch's set, its team's first, most touches first: those
  likely on court; then everyone, as before.
- Played past the end of a rally not checked, the video stops 1.5 s after it (the ball may still be up at the end found), once until moved back, to check it; "Valider" plays
  on from the next one.
- Under it, a zoomable bar of every rally, touch, report (red flag) and warning (orange flag: on its touch, else the
  rally's start; an automatic report only where the editor finds no warning on its rally, in orange too). It colours each rally (orange
  warning, green checked, grey to check) and its arrows go to the next one to check. Both bars show the rallies as
  corrected (an end moved, a rally started, joined or deleted) before they are saved.

### Correcting

- A report about one touch (a record, a point without crossing the net, a relance played high, a viewer's on the touch
  replayed) sits under that touch, its card edged in red (an automatic one's in orange, "Vérification automatique" said once
  in its header); a touch with a warning has an orange edge; an automatic report the editor's warnings find as well
  (`LIVE_PROBLEMS`, `unwarnedReports`: the rally's structure, serves, gap) shows only as that warning, gone once fixed,
  checking the rally handles it; "Ne commence pas par un service" offers "En faire le service"; the rally's warning
  sign says each warning's touch by its moment (the owner, 15 Nov: what a warning was about was hard to find).
- Beside the video, the touches around it: correct, add (a serve before a rally starts it, and the touches added after it
  are that rally's), remove, end a rally (`end` answers; its touches after that start a new rally at the first of them,
  `helpers/report.ts` `splitAfter`), join two rallies (`join` answers), start a rally at a moment
  (`split` answers: one missed, or the second of two taken for one; `web.rally_table`), with its serve (none within 1 s
  there yet) by the rally before's winner, its player field ready.
- A touch added guesses its action from the one before (`nextTouch`): after an attack, a block under 0.4 s later (on the
  three matches blocks came 0.02-0.54 s after it, median 0.2 s; digs 0.1-1.7 s, median 0.8 s), else a dig.
  After a point, the losing team's touch (the ball fell on their side): a reception after an ace, a block or a dig after
  an attack, else a dig.
- "Ajouter l'attaque" beside a set's doubt ("Une passe suivie par l'autre équipe", "L'échange finit sur une passe"; the
  owner's, 15 Nov) adds the attack the ball unseen hid, by the set's team, 1.42 s after the set and 0.2 s before the next
  touch at most (`missedAttackAt`), the video paused there and its player field ready; a rally ending on the set ends on
  the attack instead (the set's point or fault moves to it). On the three matches' pipeline runs (`add-15nov`), an attack
  was missing at 46 of the 116 sets doubted so, the rest sets really sent over or ending the rally, or relances and
  attacks typed as sets (a key fixes those); the time found within 0.2 s 33-84% of the time, 0.3 s 67-95% (on the 397
  attacks seen after a set: 1.42 s median, 70% within 0.2 s).
- Rallies are named by their `rallies.csv` start (`key` on the page). A rally starts at its first touch kept, its serve
  (`web.started`, never before the one before ends; the editor's `startOf` as the touches are removed or added): on the
  three matches, 55 of 444 started 0.5-11 s before their serve (touches removed in the review), most others 0.33 s after
  it. Its automatic reports keep the id of its window's start (`window` on the page), so none handled comes back.
- A touch added after a point or a fault in its rally puts that touch back in play (a playing fault stays one) and is
  the fault instead (the owner's, 19 Nov): after a point the losing team's, after a fault the ball touched on. A line between rallies
  shows the score after each one; a rally's whole surface turns orange with a warning, else light green once checked.
- A rally's winner follows its last touch (`web.followed`).
- "Faute de jeu" (`fault`): a fault without the ball (net, centre line, rotation), only added in the review: always a
  fault, no touch of the ball in the checks, counted in its player's faults, never put on a touch before it.
- "Balle manquée" (`missed`, `web.NO_BALL` with `fault`): a ball its player should have played, let fall untouched, only
  added in the review, at the moment it passes them. A fault as a playing fault is; the touch before keeps its result: the
  other team's serve or attack stays their point (`web.credited`), and it counts for its player as a missed reception after a
  serve, a missed dig after another touch of the other team (stats.ts), so the ace needs no receiver (`review.aces`). Shared
  ("Faute partagée avec"), it is in both players' "Entre deux" in place of the guess from where it landed (between.ts); "Le
  coin du coach" counts it as "Les ballons laissés" when shared or after the team's own touch, else as what beat it.
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

- "Valider" in a rally's header, or beside the video's caption on its rally's last touch, saves and checks it: green, its reports handled, until a new report. With a warning that
  checking leaves (not a doubt), it asks first ("Valider quand même"). A press in the list holds it still 3 s, as leaving a
  field does: scrolling to the video's touch moved the button from under the pointer, and the click was lost. The button then
  becomes "Invalider", which unchecks it, or "Valider" again while the rally has unsaved corrections.
- A rally checked ends with its last action: where its ball first lands after it (seen), at most 2.5 s after it, at once
  after a playing fault, never later than the end found (`web.closed`, `closedEnd` in the editor; it starts at its first
  action already, `web.started`). On the four matches (18 Nov) that landing came 1.1 s after the action at the median, 90%
  within 2.85 s; the ends found ran up to 17 s past it.
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

- no serve first, two serves, a reception not right after a serve (not as a rally's first touch: no serve says it), a serve not followed by a reception, four touches in a
  row, the wrong server, no touch, no winner, over 2.5 s between two touches, a server out of rotation order;
- a relance as a team's first touch (`relanceFirst`, after the other team's touch but a serve, or after a block) or as its
  second its team plays on (`relanceSecond`): a dig or a set by the owner's rule (14 Nov), on checked rallies too; on a checked
  rally, a set as a team's second touch the other team plays next (`setOver`): a relance (before, its 3rd touch is often
  missing: the editor's doubt "a set going to the other team" stands for it);
- a relance from 2.6 m on a 2nd touch or later (`highRelance`, `review.odd_heights`, from the touches' 3D places in ball3d.js, kept across a rerun in `before-rerun/review-ball3d.js`): a
  doubt, the touch flagged in the Match tab while its action stands; "Traité" keeps the action, validating handles it. An attack under 1.8 m was doubted too, dropped: the owner kept all 8
  answered;
- a set ending off the score given (`scoreOff`, asked again once the score moves; the list shows the running score);
- the score board gaining more points than rallies played between two readings, the next one keeping that lead, a rally to
  replay allowed to explain one (`missedPoint`, `review.missed_points`: none on the first match, 26 of its 129 rallies
  found hidden in turn, for lack of readings);
- the running score parting from the score board's for two readings in a row (`boardOff`, `scoreboard.py`: the board read
  before each serve, a misread one dropped, its sides fitted set by set);
- one jersey on two players of a team (allowed, the owner's: both may wear no team jersey; handled once).
- each trophy's record (`review.records`, `record.KEY`: the fastest serve and attack, the highest jump, from 5 measured; ties
  each), on its touch, its own question: the trophies take the best single reading (the owner, 15 Nov), which a wrong one
  wins, and the numbers alone do not tell a wrong one (on the three matches the outstanding ones were not all wrong).
  "Juste" (or checking its rally) keeps it; "Fausse" (a `wrong` answer: the key and frame; pending, it asks for the apply) takes that reading off the
  page at the apply (`web.wrong_measures`), and the next best one is asked then.

A rally between two equal board readings (`boardStill`, to replay or false) and a last touch scoring with no net crossing
after it, a block apart (`notOver`, `review.crossings`: `net.csv` stops with the windows) are reported too, but never on a
rally checked: a new check reopens none. No winner, a set's score, the board and a missed point sit at the rally's end,
after its touches; the others at its start or their touch.

The editor also flags what may be right after all, on its touch and gone once the rally is checked (`checks.ts`,
`doubtful`): a touch seen twice, a team playing on after its attack or relance, a set going to the other team, a set as
first touch, a dig or reception after the team's own touch, two sets in a row, a rally ending on a set, a point on a
reception or dig (not a relance: it happens). Scored on the pipeline's rallies against the corrections: a flag sits on a
correction 82-100% of the time on both matches, 40% by chance (4 Nov); on 14 Nov's pipeline against the answers with the
relance rule applied (`benchmarks/corrections/doubts.py`), 58% of 53 and 60% of 103, 20% and 22% by chance (a set going to
the other team 40% and 48%, a rally ending on a set 40% and 31%). Dropped: an ace (1 of 11 on the first match). Rejected: over 2 s between touches (61% on the first match), a floor contact on a player (47%), a team change without a net crossing (37 left on checked rallies:
crossings go unseen).
