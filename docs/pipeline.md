# Pipeline

How a video becomes statistics, step by step. Each step is scored against hand labels in
[`benchmarks/`](../benchmarks); to label a new setup's match, see [kili_labelling.md](kili_labelling.md).

- [Steps](#steps)
- [Status](#status)
- [Prior art](#prior-art)

## Steps

| Step | What it does | Starting point |
| --- | --- | --- |
| 1. Rallies | Find when the ball is in play, drop dead time | Ball-track runs closed by the referee's whistle ([benchmark](../benchmarks/rallies/README.md)) |
| 2. Court | Map pixels to court coordinates | Lens undistortion + homography: rough clicks once per court, snapped to the painted lines; known courts recognised automatically when the stand moves a little ([benchmark](../benchmarks/court/README.md)) |
| 3. Ball | Track the ball, detect contacts and net crossings | WASB, pretrained ([benchmark](../benchmarks/ball/README.md)); contacts from velocity changes with gravity removed ([benchmark](../benchmarks/contacts/README.md)) |
| 4. Actions | Classify each contact: serve, reception, set, attack, block, dig | Rules: contact order per side of the net + floor position ([benchmark](../benchmarks/actions/README.md)) |
| 5. Players | Detect and track players, tell the teams apart, attribute each contact | YOLO11m + BoT-SORT + an offline pass joining and filtering tracks ([benchmark](../benchmarks/players/README.md)); teams from the side of the net, followed from rally to rally by the tracks crossing each break and, after a long break, by the players' looks (by the rules when both teams wear the same kit), so kits may differ within a team; sets from the changes of ends ([benchmark](../benchmarks/teams/README.md)); toucher = nearest box on the contact's side, an arm above for serves, attacks and blocks ([benchmark](../benchmarks/attribution/README.md)) |
| 6. Identity | Merge tracklets into one identity per player for the match | Tracks cut at crowd episodes, OSNet re-ID embeddings whitened per team, a time-ordered assignment under cannot-links (seen together, too far to run), one number per track inside a rally; jersey numbers read on 4K footage as constraints; dimensions weighted by how well they tell apart the players the review confirms ([benchmark](../benchmarks/identity/README.md)) |
| 7. Naming | Name each identity once, suggest names across matches | The review page's "Noms" tab; a roster of re-ID embeddings per named player |
| 8. Stats | Per-player counts and outcomes, reception ratings, balls dropped between two players, strengths and things to work on | The page's "Statistiques" table: each touch's outcome from the next contact (the ball landing in, out or in the net); an ace counts against the receiver nearest to where it lands; a reception's rating from where the next touch is played; the players' positions where an untouched ball lands; a player's rates compared with the rest of their team's |

## Status

Two real matches filmed in 4K at 50 fps and processed (October and November 2026). On the first one,
against the 129 rallies checked by hand:

| Measure | Result |
| --- | --- |
| Touches found | 872 of 945 (92%) |
| Touches found that are real | 863 of 909 (95%) |
| Touch types right | 778 of 872 (89%) |
| Touches given to the right named player | 679 of 761 (89%) |
| Rally winners right | 117 of 128 (91%) |

The weak spots are rally ends and how a rally ends (in, out, fault), and the ball when it leaves the
frame or stays unseen near the floor. Everything is tuned on the first match: the second one, held out,
will tell how it carries over. For reference, a fixed-camera semi-automatic system reached 77% agreement
with human scouting ([UFP thesis, 2026](https://bdigital.ufp.pt/bitstreams/9e2cbd9e-89d4-4191-a1bc-7a0533e97f9f/download)).

What is next, with the numbers: [state.md](state.md), [next_steps.md](next_steps.md) and [plan.md](plan.md).
Ideas for later: attack efficiency, and a second camera on the opposite sideline if the far side proves
unreliable.

## Prior art

- [shukkkur/VolleyVision](https://github.com/shukkkur/VolleyVision) (AGPL-3.0): ball tracking,
  court detection, action recognition.
- [Shaamallow/VolleyVision](https://github.com/Shaamallow/VolleyVision): ball tracking, YOLOv8
  action model.
- [masouduut94/volleyball_analytics](https://github.com/masouduut94/volleyball_analytics)
  (GPL-2.0): ball and action detection.
- [haotianxia/VolleyStats](https://github.com/haotianxia/VolleyStats) (Apache 2.0): stats on top of
  [tprlab/vball](https://github.com/tprlab/vball).
- [SFU Volleyball dataset](https://github.com/mostafa-saad/deep-activity-rec): annotated frames
  with player actions.
- [DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis) (MIT):
  the same goal, with per-stage numbers.
- Commercial: Balltime / Hudl Assist.

Scientific literature per pipeline step, with recommendations: [literature.md](literature.md).
