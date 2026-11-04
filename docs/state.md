# Where the project stands

The pipeline's weak spots and what is left to do, most useful first.

- Weak spots: touches and rally ends. On the first match: touches found 872 of 945, 863 of 909 real, types 778 of 872, named players 679 of 761,
  checked winners 117 of 128. Rallies on its two labelled 10 minutes (`benchmarks/rallies`): pipeline F1 ±1 s 0.90 on the span the `served` fixes were
  tuned on, 0.57 on the other; a third of the school match's held-out rallies missed. How a rally ends (in, out, fault) is the least reliable measure.
  Attribution is right 76-87% of the time on the labelled clips (held out on the first match's answers, the learned order 628 of 702, the rule 615): its
  doubts, a player twice in a row and spot checks are asked in the review as "Qui a touché le ballon ?"; `benchmarks/attribution/answers.py` scores the
  picks. Identity IDF1 0.81-0.89. Free balls rest on one labelled example. The ball often leaves the frame (high serves and sets): the false touches
  that makes are dropped (`attribution.FAR`) and no net crossing is lost (`contacts.MAX_GAP`); carrying the flight across waits for a match where it shows.
- `docs/next_steps.md`: what is left in the pipeline, with the numbers; the plan for learning from the review (`learn`).

## Open

1. The second match (`2026-11-02-avia-1-vs-aspom-2`): in review, 22 of about 144 rallies checked on 4 Nov, 7 score board reports, not hosted yet.
2. Once reviewed, that match held out whole: everything is tuned on the first. Retrain the ranker and
   re-sweep `identity.SHARPEN`.
3. `docs/plan.md`: the touches left, the 3D ball and TV mode's limits.
4. Rally ends and winners: `rallies.whistled` as a fallback is in (held
   out found R 1.00, F1 ±1 s 0.57). Left on 50:00-60:00: two false windows (server bouncing the ball,
   a ball rolled back), ends cut by another court's whistle (-4.1 s) or the ball out of sight (-3.0,
   -2.3, and -10 s for 58:55), a rally joined to its dead-ball tail by the 8 s rule (+10 s); then how
   rallies end (in, out, fault).
5. The review's rally answers and the 129 checked rallies as labels to drop false windows
   automatically (asked, not started).
6. Node.js and library updates on the owner's services (offered by the owner, not done).
7. Deferred: the pose check on passes, sets and digs (hands near the ball, +1-2 of 42 touches on
   the benchmark for a pose pass over every touch); the serve rotation check (unverified, ~9
   players a team rotate in).
8. On the owner's RTX 5080 PC: measure `speed.py`, tune jersey numbers on that footage.
9. `data/`'s and `outputs/`'s folders other than the two matches' are test clips and benchmarks.
10. The owner's plan, nothing started, not before the second match is reviewed and its quality known: a helper they trust,
   then maybe other people's matches. First a job queue the Mac and the 5080 pull from (they only reach out; a busy one takes no job),
   useful alone; then the VPS's system upgraded (2 vCPU, 3.7 GB, 18 GB free, Ubuntu 20.04), a login per person and the review on it, with
   the slow steps on the workers, a process per open match (`review.switch` restarts the only server) and crops prepared from the 4K.
   About 1-2 weeks, about EUR 0-1 a month. Other people adding matches is decided later: uploads, court setup in the browser, clubs kept
   apart, workers sandboxed, consent and GDPR (advice first; the hosting rules in `CLAUDE.md` would change on purpose). In between, a club sends a video
   and the owner processes it. Rejected for now: rented GPUs for everything (EUR 25-45 a month, rough, from third-party prices).
