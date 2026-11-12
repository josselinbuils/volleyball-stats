# Where the project stands

The pipeline's weak spots and what is left to do, most useful first.

- Weak spots: touches and rally ends. On the first match: touches found 890 of 955, 881 of 926 real, types 799 of 890, named players 678 of 769,
  checked winners 117 of 128; the second, 1073 of 1199, 1065 of 1136, 956 of 1073, 832 of 932, 127 of 145 (7 Nov, `pipeline.md`). Rallies on its two labelled 10 minutes (`benchmarks/rallies`): pipeline F1 ±1 s 0.90 on the span the `served` fixes were
  tuned on, 0.58 on the other; the school match's held-out clip 0.86. How a rally ends (in, out, fault) is the least reliable measure.
  Attribution is right 76-87% of the time on the labelled clips (held out on the first match's answers, the learned order 622 of 691, the rule 603): its
  doubts, a player twice in a row and spot checks are asked in the review as "Qui a touché le ballon ?"; `benchmarks/attribution/answers.py` scores the
  picks. Identity IDF1 0.81-0.89. Free balls rest on one labelled example. The ball often leaves the frame (high serves and sets): the false touches
  that makes are dropped (`attribution.FAR`) and no net crossing is lost (`contacts.MAX_GAP`); carrying the flight across waits for a match where it shows.
- Rally ends now carry on through contacts (`rallies.carried_on`); most touches still added by hand have no contact: the ball is unseen near the floor.
- Attack jumps (`jumps.py`, 7 Nov): takeoff, landing, the hit and the run-up from the attacker's pose; on 40 labelled attacks
  takeoff within 2 frames for 22 of 24 jumps measured, landing 21, timing within 60 ms 22 (`benchmarks/jumps`). About two thirds
  of attacks get one (a foot hidden loses the rest). It feeds "Le saut d'attaque" in the coach's corner, the "Détente" of "Mon match", the trophy "Le Ressort" and the 3D figures' jumps.
- `docs/next_steps.md`: what is left in the pipeline, with the numbers; the plan for learning from the review (`learn`).

## Open

1. Done (5 Nov): the second match (`2026-11-02-avia-1-vs-aspom-2`) reviewed and hosted.
2. Done (5 Nov): the learned attribution trains on every reviewed match (held out 623 -> 625 of 691, 859 -> 868 of 957);
   `identity.SHARPEN` 0.9 kept on both matches' answers. Jersey numbers now only keep players apart, and one read mostly on the
   other team links nobody (`identity.jersey_links`): held-out answers 206 -> 230 of 333 (224 without numbers), 419 -> 420 of 543.
3. `docs/plan.md`: the touches left, the 3D ball and TV mode's limits.
4. Rally ends and winners. Done (5 Nov, `benchmarks/rallies/README.md`): `no_play` keeps rallies with touches and no serve seen,
   short whistled serves count, a ball bounced 20 times is no rally; rallies missed 2 -> 0 of 129 and 9 -> 2 of 150, false windows
   2 -> 3 and 3 -> 3, `side_holdout` F1 ±1 s 0.77 -> 0.86; in the matches' outputs at the next "Apprendre de mes réponses".
   12 of the second match's 18 wrong winners are rallies with no window. Left: ends with the ball out of sight or another court's
   whistle (50:00-60:00 F1 ±1 s 0.58; four end rules tried, none gains; 7 Nov, the players' speed and the cheer after a
   point dropped too), then how rallies end (in, out, fault). A learned play / no-play clip model (`playing.py`, `next_steps.md`
   item 14) is in the pipeline since 12 Nov where its weights are (`outputs/learned/play/`, shared by the backup): 50:00-60:00 F1 ±1 s 0.58 -> 0.67,
   the touches outside every window 26 -> 8 and 53 -> 2; trained again by "Apprendre de mes réponses" on a fully checked match; not run on the Mac yet, and kept to the camera's own 4K footage (worse windows on the one other match there is).
5. Done (5 Nov): the checked rallies as labels (`checked.py` scores `match.py`'s windows). The 6 false windows left have
   no feature apart from real rallies: review questions.
6. Done (5 Nov, `docs/next_steps.md`): the pose on every touch type and the serve rotation, both dropped.
7. Done (8 Nov, `benchmarks/speed.py`): tracking on the RTX 5080 runs at 26 fps, 3.9 h for a 2-hour 4K match (7.8 h on the M4 Pro);
   one Python thread runs the ball's and players' models in turn (a core at 100%, the card 51% busy). Two threads (`match.side_by_side`, 8 Nov):
   29 -> 37 fps, tracks identical; CUDA only (Metal aborts on two threads); the players' YOLO in batches of 8 or half precision faster still, outputs changed (`speed.py`). Left: the pose's cost per touch there (`next_steps.md` item 8).
   The steps after tracking (8 Nov, first match): 2 h 56 -> 1 h 44, outputs identical (`speed.py`): the relance
   check and the wrists decode in one pass, and ffmpeg drops the frames nobody wants (`decode.frames_at`). RapidOCR
   on the GPU (`onnxruntime-gpu` on Linux, the Mac keeps `onnxruntime`): jerseys 45 -> 23.5 min (301 of 303 pieces
   the same number), scoreboard 6.6 -> 3.1 min (same scores).
8. `data/benchmarks/` holds the benchmark clips, `outputs/benchmarks/` their outputs.
9. The owner's plan, nothing started: a helper they trust,
   then maybe other people's matches. First a job queue the Mac and the 5080 pull from (they only reach out; a busy one takes no job),
   useful alone; then the VPS's system upgraded (2 vCPU, 3.7 GB, 18 GB free, Ubuntu 20.04), a login per person and the review on it, with
   the slow steps on the workers, a process per open match (`review.switch` restarts the only server) and crops prepared from the 4K.
   About 1-2 weeks, about EUR 0-1 a month. Other people adding matches is decided later: uploads, court setup in the browser, clubs kept
   apart, workers sandboxed, consent and GDPR (advice first; the hosting rules in `CLAUDE.md` would change on purpose). In between, a club sends a video
   and the owner processes it. Rejected for now: rented GPUs for everything (EUR 25-45 a month, rough, from third-party prices).
10. Done (5 Nov): the star on a touch (Match tab) puts it in the match's film and its player's.
11. Done (7 Nov): attack jumps measured (`jumps.py`, `benchmarks/jumps`), "Le saut d'attaque" in the coach's corner, the 3D
    figures' jumps, a pipeline stage posing the attackers, the review's screens their own script (the page 34 KB lighter).
    Measured, not on the page: blockers' jumps (`benchmarks/jumps/ground_truth/blocks.csv`), topping about when the ball
    crosses the net (0.18 s after the attack's contact). The jump height per player went on the page the same day ("Détente", "Le Ressort"). Tried and dropped the same day, numbers in
    `next_steps.md`: jumps as a touch-type cue, a learned retyping, the hitting height from the pose, a lower contact
    threshold near players, rules for made-up contacts and for floors that are touches.
12. Done (8 Nov): "Placement en réception" and "Placement en défense" in the coach's corner ([match-page.md](match-page.md)),
    a picked player's usual places against the system's spots.
13. Done (8 Nov): two machines. Any machine works on any match: the review opens on the server's newer copy, asks which to keep
    when both changed, and refuses a copy or an upload over a newer one (`sync.py`), the list downloads the matches only on the server, uploads keep the other machine's pages
    (`matches.mirror`, a dry run's guard), the videos go straight between the machines (`data_sync.py`). [hosting.md](hosting.md).
14. For later (the owner's, 9 Nov): the review's Match tab saves in four ways: touches, winner, join, end, wrong call and replay
    wait for "Valider"; stars, timeouts and "Supprimer" at once; comments on leaving the field; the match's end with an apply.
    Saving every edit at once, "Valider" only checking, would end the corrections not saved (a guard asks before losing them now).
15. Done (9 Nov): one command, everything in the app (`app.py`, `install.sh`, [running.md](running.md)): the machine's
    checks, import, court (clicked in the browser the first time in a gym), pipeline with its progress, the videos with the
    other machine, the update. `match.side_by_side` runs on CUDA only: on the Mac (MPS) two threads abort Metal.
16. Fewer corrections in the review (11-12 Nov, [corrections_log.md](corrections_log.md): the harness `benchmarks/corrections`, what
    was kept and dropped, what is next): the corrections left to the owner on the two reviewed matches 294 -> 281 and 410 -> 351
    (2.2 and 2.3 a rally). Kept: a set sent over the net typed by its flight, a touch on a nameless piece of track given its
    track's nearest name, the play / no-play model. Dropped with their numbers: a fine-tuned ball model, two stronger
    re-identification models, a learned touch type, eight pose models, rules for windows, false touches and types.
    Its "State" is the hand-over: what waits on the owner (a third match filmed on 12 Nov, a session on the Mac) and what is next.
