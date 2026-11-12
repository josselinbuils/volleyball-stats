# Pose models compared (11-12 Nov)

The pipeline poses players with YOLO11m-pose in three places: the wrists around each touch (who touched the ball,
`attribution.by_wrists`), the attacker over a jump (`jumps.py`) and the boxes that tell an attack from a relance
(`actions.mark_relances`). The owner's question (11 Nov): would a stronger pose model do better? Each candidate runs on the
same pixels, cut once from the two reviewed matches, and writes the pipeline's own cache files; the pipeline's code then
scores them. Verdict: none is clearly better, YOLO11m-pose stays.

## Run

```bash
uv run python benchmarks/pose/cache.py MATCH          # the crops, once: outputs/benchmarks/pose/MATCH/ (17-19 GB a match)
uv run python benchmarks/pose/run.py MODEL MATCH      # outputs/benchmarks/pose/runs/MODEL/MATCH/{wrists,jumps,relances,speed}.json
uv run python benchmarks/pose/score.py MODEL [--parts wrists jumps relances] [--conf 0.7] [--keypoint-conf 0.3]
```

`MODEL` is `yolo11m-pose` (the pipeline's, run again through the benchmark as a control) or a folder or file of
`models/pose_candidates/` (`models.py`; not in the repository). The top-down models (all but the YOLOs) are given the boxes
YOLO11m-pose found for the wrists and the tracks' boxes for the jumps; they make no boxes, so no relance score. A crop file
left empty by a stopped run makes `run.py` fail: delete the files of size 0 and run `cache.py` again.

## Results

Who touched: the right picks on the review's answered touches with a candidate (691 on the first match, 957 on the second),
by the wrists' rule and by the learned order with each match's sets held out (`benchmarks/attribution/ranker.py`). Jumps:
the 80 labelled attacks of `benchmarks/jumps` (59 with a jump to measure), found and within 2 frames or 60 ms of the label.
Attack or relance: right of the 170 and 210 pipeline attacks and relances of the checked rallies.

| Model | Licence | Who touched, rule (first / second) | Learned order | Jumps found of 59 | Of those, takeoff / landing / timing in tolerance | Attack or relance | ms a wrist call / a jump frame |
| --- | --- | --- | --- | --- | --- | --- | --- |
| YOLO11m-pose (today) | AGPL-3.0 | 610 / 843 | 625 / 868 | 46 | 39 / 40 / 42 | 143 / 168 | 41 / 27 |
| YOLO11x-pose | AGPL-3.0 | 615 / 853 | 628 / 866 | 47 | 39 / 40 / 39 | 135 / 162 | 55 / 80 |
| YOLO26m-pose | AGPL-3.0 | 607 / 836 | 628 / 865 | 50 | 41 / 42 / 42 | 141 / 173 | 31 / 9 |
| YOLO26x-pose | AGPL-3.0 | 609 / 835 | 627 / 867 | 48 | 38 / 40 / 37 | 132 / 166 | 52 / 43 |
| RTMPose-x (body7, 384x288, ONNX) | Apache-2.0 | 608 / 844 | 625 / 868 | 49 | 41 / 38 / 36 | | 34 / 10 |
| RTMW-x (whole body, 384x288, ONNX) | Apache-2.0 | 611 / 842 | 633 / 869 | 47 | 39 / 38 / 34 | | 38 / 11 |
| ViTPose-base (simple decoder) | Apache-2.0 | 611 / 845 | 628 / 871 | 48 | 36 / 39 / 40 | | 17 / 9 |
| ViTPose+ huge | Apache-2.0 | 617 / 843 | 628 / 869 | 45 | 40 / 39 / 39 | | 48 / 38 |
| Sapiens 0.6B (torchscript, 1024x768) | CC BY-NC 4.0 | 610 / 838 | 629 / 865 | 42 | 32 / 36 / 33 | | 471 / 80 |

The control gives the pipeline's own scores within 2 (611 / 844 and 626 / 866 from the match folders' caches). Times on the
RTX 5080, each model alone or beside one other job; the top-down ones exclude finding the boxes.

- Who touched, by the learned order the pipeline uses on this footage: +8 and +1 for RTMW-x, within 4 either way for every
  other model, as much as one retrained order changes. The rule alone gains most with YOLO11x-pose (+5 and +10), which
  the learned order does not keep (+3 and -2). The right player is among the candidates on 665 and 921
  touches whatever the model: the wrong picks are two players in line with the camera (`docs/corrections_log.md`
  "Players"), not wrists badly placed.
- Jumps: YOLO26m-pose finds 4 more of 59, with as many in tolerance as today (takeoff 41 against 39, timing 42 against 42);
  the thresholds (`jumps.KEYPOINT_CONF`, the wrists' `WRIST_CONF`) are those tuned for YOLO11m-pose and were not tuned again for any candidate.
- Attack or relance: 311 of 380 today, 314 for YOLO26m-pose, 298 for YOLO26x-pose, 297 for YOLO11x-pose.

Not run through `benchmarks/corrections`: no candidate gains offline. What a better pose could still give is the blockers'
hands at the net (the blocks made up or missed right after an attack), which no step reads today.
