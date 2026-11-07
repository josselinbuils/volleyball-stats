# Where the project stands

The pipeline's weak spots and what is left to do, most useful first.

- Weak spots: touches and rally ends. On the first match: touches found 872 of 945, 863 of 909 real, types 778 of 872, named players 679 of 761,
  checked winners 117 of 128. Rallies on its two labelled 10 minutes (`benchmarks/rallies`): pipeline F1 ±1 s 0.90 on the span the `served` fixes were
  tuned on, 0.58 on the other; the school match's held-out clip 0.86. How a rally ends (in, out, fault) is the least reliable measure.
  Attribution is right 76-87% of the time on the labelled clips (held out on the first match's answers, the learned order 628 of 702, the rule 615): its
  doubts, a player twice in a row and spot checks are asked in the review as "Qui a touché le ballon ?"; `benchmarks/attribution/answers.py` scores the
  picks. Identity IDF1 0.81-0.89. Free balls rest on one labelled example. The ball often leaves the frame (high serves and sets): the false touches
  that makes are dropped (`attribution.FAR`) and no net crossing is lost (`contacts.MAX_GAP`); carrying the flight across waits for a match where it shows.
- Rally ends now carry on through contacts (`rallies.carried_on`); most touches still added by hand have no contact: the ball is unseen near the floor.
- Attack jumps (`jumps.py`, 7 Nov): takeoff, landing, the hit and the run-up from the attacker's pose; on 40 labelled attacks
  takeoff within 2 frames for 22 of 24 jumps measured, landing 21, timing within 60 ms 22 (`benchmarks/jumps`). About two thirds
  of attacks get one (a foot hidden loses the rest). It feeds "Le saut d'attaque" in the coach's corner and the 3D figures' jumps.
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
   point dropped too), then how rallies end (in, out, fault). Next step for ends: labels from the second match.
5. Done (5 Nov): the checked rallies as labels (`checked.py` scores `match.py`'s windows). The 6 false windows left have
   no feature apart from real rallies: review questions.
6. Done (5 Nov, `docs/next_steps.md`): the pose on every touch type and the serve rotation, both dropped.
7. On the owner's RTX 5080 PC: measure `speed.py`.
8. `data/benchmarks/` holds the benchmark clips, `outputs/benchmarks/` their outputs.
9. The owner's plan, nothing started, not before the second match is reviewed and its quality known: a helper they trust,
   then maybe other people's matches. First a job queue the Mac and the 5080 pull from (they only reach out; a busy one takes no job),
   useful alone; then the VPS's system upgraded (2 vCPU, 3.7 GB, 18 GB free, Ubuntu 20.04), a login per person and the review on it, with
   the slow steps on the workers, a process per open match (`review.switch` restarts the only server) and crops prepared from the 4K.
   About 1-2 weeks, about EUR 0-1 a month. Other people adding matches is decided later: uploads, court setup in the browser, clubs kept
   apart, workers sandboxed, consent and GDPR (advice first; the hosting rules in `CLAUDE.md` would change on purpose). In between, a club sends a video
   and the owner processes it. Rejected for now: rented GPUs for everything (EUR 25-45 a month, rough, from third-party prices).
10. Done (5 Nov): the star on a touch (Match tab) puts it in the match's film and its player's.
