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
- `docs/history.md`: what was tried, kept and left from 1 to 11 Nov, with the numbers, and what was done until 22 Nov ("Done,
  5-22 Nov", the numbered items other notes cite); `corrections_log.md`: fewer corrections since 11 Nov.

## Open

1. Waiting on the owner: the camera's shutter. Three warm-up minutes at the next match, from the match position, WB 4000K:
   1/240 ISO 3200 (the 2 Nov settings), 1/500 ISO 6400, 1/1000 ISO 12800 (the Osmo Action 3 offers no 1/480 or 1/960). Compare
   the ball's detection, a spiking arm's sharpness, the grain and flicker, then set [recording.md](recording.md). On 2 Nov the
   camera stood behind the end line, not on the sideline as the guide says: the attacker about 115 px tall at the far net.
2. Fewer corrections: the players are now the largest share (440 of 1,412 on the four matches, history item 31);
   [corrections_log.md](corrections_log.md) "Next" is the hand-over. The ball unseen around touches and how rallies end are
   not pursued (22 Nov): every lead measured failed; only a new idea with a credible gain brings them back.
3. VR (history item 20): standalone in the Quest Browser on the hosted page (HTTPS), once uploaded with the owner; the
   comfort of the teleport and snap turn (`ARC_SPEED`, `FADE_S`, `SNAP` in `scene3d/scene.ts`), the video panel on the left
   hand (`PANEL_AT`, `PANEL_TILT`), the name tags' size, the frame rate standalone (the 2048 shadow map).
4. The play model on someone else's footage: its windows are worse on the one other match (`benchmarks/rallies/README.md`);
   a threshold or uses set per footage, or training on more views, before it runs on anything but the camera's own 4K.
5. Ideas, not planned: the blockers' jumps on the page (measured, `benchmarks/jumps/ground_truth/blocks.csv`); in the 3D
   looks, the shoes' colour, leggings, long sleeves, glasses (the parsing model's unused classes); the limits of the 3D ball
   and TV mode (history, "The page").

Dropped by the owner (22 Nov), not to be proposed again: a job queue the machines pull from, logins and the review on the
VPS, other people's matches (a club sends a video, the owner processes it); a fine-tuned ball model in any variant; the
phone checks left and the hosted video copies' leftovers.

`data/benchmarks/` holds the benchmark clips, `outputs/benchmarks/` their outputs.
