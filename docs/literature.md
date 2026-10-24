# Literature survey

Scientific work relevant to each pipeline step, with a recommendation for this project. Surveyed
2026-10-23/24. Entries marked *(abstract only)* were read from the abstract or an index record.
Every link was resolve-checked (HTTP 200, or 202/403 bot challenges on IEEE, ACM, OpenCV and
Roboflow pages); the one exception is flagged.

Licence reading for an AGPL-3.0 project: MIT, BSD, Apache-2.0 and CC BY code or weights can be
reused; GPL-3.0 code can be combined (GPLv3 §13) but keep it in a separate module; GPL-2.0-only,
CC BY-NC-* and unlicensed code is reference only; CC BY-NC datasets are fine for evaluation and
research training, not for anything sold.

## Top recommendations

1. **Court: fit the painted lines, do not train a keypoint net.** The only volleyball keypoint
   model found reports 0.49 m median error on gym images against 0.10 m on broadcast; the same
   project switched to fitting the court model to the painted lines of an empty-court background
   frame for fixed cameras and got 0.02–0.06 m median on 5 of 6 clips
   ([DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis), MIT).
   Undistort first: calibrate the lens once per FOV mode with a checkerboard
   ([OpenCV fisheye](https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html), or
   [Gyroflow's calibrator](https://docs.gyroflow.xyz/app/getting-started/lens-calibration)); the
   fallback is the one-parameter division model estimated from line straightness
   ([Fitzgibbon 2001](https://doi.org/10.1109/CVPR.2001.990465)). Add the checkerboard clip to the
   "before the first match" checklist.
2. **Contacts: a learned classifier over trajectory windows, not parabola geometry.** Parabola
   intersection recovered only 48.9% of contacts
   ([Gomez et al. 2014](https://doi.org/10.1371/journal.pone.0111730)); trajectory-window
   classifiers reach 87% on table-tennis strokes
   ([Kulkarni et al. 2023](https://arxiv.org/abs/2302.09657)) and are what the badminton
   challenge entries converged on after y-reversal counting proved noise-prone
   ([Chou et al. 2023](https://arxiv.org/abs/2308.12645)). Inpaint tracking gaps first
   ([TrackNetV3](https://github.com/qaz812345/TrackNetV3), MIT). Bootstrap labels with the
   direction-change heuristic, correct by hand, train a TCN/GRU on (x, y, visibility, velocity,
   court coordinates).
3. **Rallies: an HMM over ball-track continuity and an off-the-shelf whistle score.**
   [Pidaparthy et al. 2021](https://openaccess.thecvf.com/content/CVPR2021W/CVSports/papers/Pidaparthy_Automatic_Play_Segmentation_of_Hockey_Videos_CVPRW_2021_paper.pdf)
   (hockey) hit 96% recall with an HMM over deep visual cues; audio helped only after unsupervised
   per-game adaptation. Rally end as "no ball motion for N frames" worked in badminton (95% on 187
   rallies, [See et al. 2025](https://research.monash.edu/en/publications/a-comparative-analysis-of-deep-learning-models-and-gradient-compu/)).
   AudioSet-trained [YAMNet](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv)
   (Apache-2.0, class 396 "Whistle") and [PANNs](https://github.com/qiuqiangkong/audioset_tagging_cnn)
   (MIT) give the whistle score without training. Reference bar: F1 0.76 on fixed-camera clips
   for the DL-Volleyball-Analysis rally classifier.
4. **Actions: classify from contact order, court position, ball trajectory and pose; no public
   dataset matches this camera.** Per-player labels exist only on broadcast-style footage
   ([SFU Volleyball](https://github.com/mostafa-saad/deep-activity-rec), 9 actions;
   [MultiSports](https://github.com/MCG-NJU/MultiSports), CC BY-NC) or on a 2011 Austrian league
   set ([Waltner et al. 2014](https://www.tugraz.at/index.php?id=17751), 7 actions). Trajectory-only
   classification of volleyball phases is established
   ([Chen et al. 2007](https://doi.org/10.1109/ICASSP.2007.366103),
   [Chen & Chu 2021](https://doi.org/10.1109/TCSII.2021.3067027),
   [PathFinder 2023](https://arxiv.org/abs/2309.14753)), and keypoint-only models match RGB on the
   SFU dataset ([COMPOSER](https://arxiv.org/abs/2112.05892)). Plan to label your own contacts:
   the one study on amateur single-camera volleyball labelled 46,648 contacts over 66 matches
   ([Kodathala et al. 2026](https://arxiv.org/abs/2609.28049)).
5. **Players: YOLO + ByteTrack/BoT-SORT, then constrained tracklet merging; expect identity to
   stay the hardest stage.** Volleyball is in [SportsMOT](https://github.com/MCG-NJU/SportsMOT)
   (CC BY-NC) for evaluation; [GTA](https://arxiv.org/abs/2411.08216) post-processing is a
   plug-in gain. Merge tracklets with hard constraints (same team, non-overlapping in time, jersey
   agreement, physically reachable gap) before appearance re-ID
   ([Golovkin et al. 2025](https://arxiv.org/abs/2504.06357)). Jersey OCR: legibility filter,
   pose-guided torso crop, scene-text model, tracklet vote
   ([Koshkina & Elder 2024](https://arxiv.org/abs/2405.13896); 85.6% tracklet accuracy with a
   single-stage digit model, [Grad 2025](https://cvpr.thecvf.com/virtual/2025/35507)). Team
   colour: [roboflow/sports](https://github.com/roboflow/sports) `TeamClassifier` (MIT). Kodathala
   et al. found identity unchanged by better temporal reasoning: unseen numbers cannot be
   recovered, so the rotation order is the lever this project has that they did not use.
6. **Contact attribution: a touch-probability model over pose and ball, not nearest box.**
   Skeleton + ball with a learned touch model gave 82.5% last-touch accuracy in soccer, >90% on
   aerial duels ([Wang et al. 2025](https://doi.org/10.1007/s12283-025-00518-3)); player keypoint
   sequences alone predict shuttle direction at 92% ([Chien & Yu 2023](https://arxiv.org/abs/2307.16000)).
7. **Ball: fine-tune WASB on own footage, semi-supervised.** A WASB fine-tuned on gym footage
   scored F1 0.942 on held-out gym matches against 0.859 for VballNet (DL-Volleyball-Analysis);
   teacher–student pseudo-labelling on unlabelled matches is the cheap way to get there
   ([Vandeghen et al. 2022](https://arxiv.org/abs/2204.06859)). 3D from one view is feasible with
   physics (82.5% success, [MVA 2021](https://www.mva-org.jp/Proceedings/2021/papers/P1-14.pdf);
   [Where Is The Ball 2025](https://arxiv.org/abs/2506.05763)) but stats v1 only needs the
   homography of the landing frame.
8. **Read DL-Volleyball-Analysis before building each stage.** Same goal, same single camera,
   MIT, active (Oct 2026), with per-stage numbers: court above, rallies F1 0.76, tracking IDF1
   0.69, actions macro-F1 0.68, digits mAP 0.82, 3D attack error 0.31 m. The UFP thesis's 77.4%
   agreement came with manual court calibration and failed on fast rallies, net/boundary
   ambiguity, other balls and busy backgrounds: exactly this project's gym.
9. **Licences to avoid in code:** PnLCalib (GPL-2.0), jersey-number-pipeline (CC BY-NC 3.0),
   deepsport (CC BY-NC-ND), COMPOSER and Sportlight calibration (no licence), VolleyStats (no
   licence), volleyball_analytics (GPL-2.0). sn-gamestate is GPL-3.0: combinable, keep separate.

## 1. Rally / point segmentation

- [Itazuri et al., CVPRW 2017](https://openaccess.thecvf.com/content_cvpr_2017_workshops/w2/papers/Itazuri_Court-Based_Volleyball_Video_CVPR_2017_paper.pdf),
  *Court-Based Volleyball Video Summarization Focusing on Rally Scene*. Detects rally scenes
  from court-transition cues caused by camera operation; broadcast volleyball; no numbers in the
  abstract; no code. *(abstract only)* **Skip**: relies on broadcast cuts.
- [Pidaparthy, Dowling & Elder, CVPRW 2021](https://openaccess.thecvf.com/content/CVPR2021W/CVSports/papers/Pidaparthy_Automatic_Play_Segmentation_of_Hockey_Videos_CVPRW_2021_paper.pdf),
  *Automatic Play Segmentation of Hockey Videos*. HMM of play state driven by deep visual cues
  and optional audio (whistle); visual cues generalise across cameras, audio only after
  unsupervised adaptation of emission distributions per game; 20–50% compression at 96% recall;
  whistle intervals averaged 0.73 s. No code. **Adapt**: the HMM + per-game audio adaptation is
  the design to copy.
- [See, Paramesran, Hassan & Krishnasamy 2025](https://research.monash.edu/en/publications/a-comparative-analysis-of-deep-learning-models-and-gradient-compu/),
  *A Comparative Analysis of Deep Learning Models and Gradient Computation for Rally Detection in
  Badminton Videos*. BiLSTM vs CNN on 12-frame windows of 26 trajectory features (distance,
  angle, gradient) for the serve start; rally end when ≥80% of consecutive frames show no
  shuttle motion; 95% on 187 rallies. *(abstract only)* **Adapt**: same features from the WASB
  track.
- [Deng et al. 2021, EventAnchor](https://arxiv.org/abs/2101.04954). Table tennis; rally
  segmentation from score changes, 98.5%; interactive annotation. **Idea only**: scoreboard
  reading is a fallback cue if a scoreboard is in frame.
- [Kodathala, Pollishetty & Cargill 2026](https://arxiv.org/abs/2609.28049), *Prompt, Probe,
  Train, or Annotate? Single-camera sports video understanding in amateur settings*. Amateur
  volleyball, single fixed camera, 66 matches, 46,648 labelled contacts; compares VLM prompting,
  small trained specialists, video world models and manual annotation across play segmentation,
  contact detection, rally outcome and identity. Findings: a prompted VLM segments play well, a
  much smaller trained model detects contacts better at a fraction of the cost, rules recover
  rally outcomes pixels cannot, identity is hardest for everything. No code or data; CC BY-NC-SA
  paper. *(abstract only)* **Use** as the design reference for the whole pipeline; the closest
  published setting to this project.
- [Nguyen et al., CVPRW 2025, VNL-STES](https://openaccess.thecvf.com/content/CVPR2025W/CVSPORTS/papers/Nguyen_VNL-STES_A_Benchmark_Dataset_and_Model_for_Spatiotemporal_Event_Spotting_CVPRW_2025_paper.pdf).
  Its `score` event marks rally ends; see §2.
- [DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis) (MIT).
  Rally classifier on court, player and ball cues trained on three fixed-camera matches labelled
  from the on-screen score (405 points): F1 0.742 on broadcast, 0.76 on six fixed-camera clips.
  **Use** as the baseline to beat.
- Whistle detection. No learned sports-whistle detector with code was found; classical band-pass
  energy detectors report ~80% ([Amrita, 2011](https://www.amrita.edu/publication/automated-referee-whistle-sound-detection-for-extraction-of-highlights-from-sports-video/),
  *(abstract only)*). AudioSet models carry the class:
  [YAMNet](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv)
  (Apache-2.0; ids 396 "Whistle", 35 "Whistling") and [PANNs CNN14](https://github.com/qiuqiangkong/audioset_tagging_cnn)
  (MIT, 527 classes). **Use** YAMNet or PANNs as the whistle scorer; threshold per match.
- [Xu et al. 2025](https://arxiv.org/abs/2505.03991), survey of sports video event detection.
  Separates temporal action localisation (rallies) from precise event spotting (contacts); notes
  benchmarks are broadcast-biased. *(abstract only)* **Idea only**: vocabulary and dataset list.

## 2. Contact / hit detection and net crossing

- [Gomez, Herrera López, Link & Eskofier, PLOS ONE 2014](https://doi.org/10.1371/journal.pone.0111730),
  *Tracking of Ball and Players in Beach Volleyball Videos*. Background subtraction, parabola
  growth (after Chen 2007) or Hough segments; contacts from intersections of vertical parabolas;
  camera behind the court. Ball tracking 54.2%, contacts 48.9% within 10 frames on 31 videos /
  190 contacts; the authors could not reproduce the >90% claimed earlier. Code in the supporting
  information, no licence. **Idea only**: the negative result that kills pure physics.
- [Chen, Chen & Lee, ICASSP 2007](https://doi.org/10.1109/ICASSP.2007.366103), *Physics-Based
  Ball Tracking in Volleyball Videos with its Applications to Set Type Recognition and Action
  Detection*, and [Chen, Tsai, Lee & Yu, MTAP 2012](https://doi.org/10.1007/s11042-011-0833-y),
  *Ball tracking and 3D trajectory approximation with applications to tactics analysis from
  single-camera volleyball sequences*. Candidate detection, trajectory linking, 3D path from the
  2D track with calibration and ball physics; set-type recognition from the trajectory;
  international broadcast games. *(abstract only)* **Idea only**: the 2D→3D-by-physics recipe,
  pre-deep-learning.
- [Chen & Chu, IEEE TCSII 2021](https://doi.org/10.1109/TCSII.2021.3067027), *How it flies and
  why it flies? Volleyball trajectory segmentation and classification*. Two cameras, 3D
  trajectory, BERT-style per-frame labelling into six classes (serve, attack, ...), long rallies
  segmented. No numbers in the abstract, no code. *(abstract only)* **Idea only**: sequence
  labelling of the trajectory is the right formulation; this project has one camera.
- [Chen & Wang, ACM MM Asia 2023, TrackNetV3](https://doi.org/10.1145/3595916.3626370),
  [code](https://github.com/qaz812345/TrackNetV3) (MIT, weights included). Prediction module
  with background estimation and mixup, then a rectification module that builds repair masks and
  inpaints occluded segments; shuttlecock accuracy 87.72% → 97.51%. No event detection in the
  repo. **Adapt**: the inpainting stage, before contact detection.
- [Raj, Wang & Gedeon 2024, TrackNetV4](https://arxiv.org/abs/2409.14543). Motion attention from
  frame differencing fused into TrackNet; research report. *(abstract only)* **Skip** for
  tracking (WASB already won the benchmark); VballNet is built on it.
- [Voeikov, Falaleev & Baikulov, CVPRW 2020, TTNet](https://arxiv.org/abs/2004.09927) and
  [OpenTTGames](https://lab.osai.ai/) (CC BY-NC-SA 4.0; 120 fps, 4,271 events: bounce, net hit,
  empty). Joint ball detection, segmentation and event spotting from short frame stacks, 97%
  event accuracy. Official code not found; an unofficial PyTorch port exists without licence.
  **Idea only**: event spotting from a frame stack around the ball.
- [Kulkarni, Jamadagni, Paul & Shenoy 2023](https://arxiv.org/abs/2302.09657), *Table Tennis
  Stroke Detection and Recognition Using Ball Trajectory Data*. Umpire-view camera, four
  players, six stroke classes; stroke boundaries found mathematically from the trajectory
  (2,023 strokes), then a temporal convolutional network reaches 87.2% on unseen data. No code.
  *(abstract only)* **Adapt**: TCN over trajectory windows is the shape of the contact model.
- [Chien & Yu 2023](https://arxiv.org/abs/2307.16000), *Automated Hit-frame Detection for
  Badminton Match Analysis*. Rally trimming (99% shot-angle accuracy), player and court
  keypoints, shuttle flight-direction prediction from player keypoint sequences (>92%), hit-frame
  detection; no code. *(abstract only)* **Idea only**: pose predicts hits, useful for attribution.
- [Chou et al. 2023](https://arxiv.org/abs/2308.12645), *An All Deep System for Badminton Game
  Analysis* ([code](https://github.com/jean50621/Badminton_Challenge), CC0). CoachAI 2023 track
  entry (score 0.78/1): modified TrackNet, then sliding-window clip classification "A hits / B
  hits / none" because y-reversal counting fails on noisy detections. *(abstract only)*
  **Adapt**: window classification with the hitter's side as the label.
- [Liu & Wang, CVPRW 2022, MonoTrack](https://arxiv.org/abs/2204.01899). Recurrent shot
  segmentation from per-frame shuttle position, court and pose, then 3D shuttle trajectory with
  physics and court priors; singles only; no code link on arXiv. *(abstract only)* **Idea only**.
- [Chen, Cai, Wang & Yan 2021](https://arxiv.org/abs/2107.09255), *Monocular Visual Analysis
  for Electronic Line Calling of Tennis Games*. Bounce as the point minimising trajectory fitting
  loss; 99.4% in/out on 394 samples. *(abstract only)* **Idea only** for landing-spot refinement.
- Precise event spotting from video: [E2E-Spot, ECCV 2022](https://arxiv.org/abs/2207.10213)
  ([code](https://github.com/jhong93/spot), BSD-3-Clause; RegNet-Y + GSM, trains on one GPU),
  [T-DEED, CVPRW 2024](https://arxiv.org/abs/2404.05392) ([code](https://github.com/arturxe2/T-DEED),
  GPL-3.0). **Adapt** E2E-Spot if trajectory-only contacts plateau: it is small and permissive.
- [Nguyen et al., CVPRW 2025, VNL-STES](https://openaccess.thecvf.com/content/CVPR2025W/CVSPORTS/papers/Nguyen_VNL-STES_A_Benchmark_Dataset_and_Model_for_Spatiotemporal_Event_Spotting_CVPRW_2025_paper.pdf),
  [project](https://hoangqnguyen.github.io/stes/). First volleyball precise-event benchmark:
  Volleyball Nations League broadcast, 8 games, 1,028 rallies, 251,110 frames, 6,137 events in
  six classes (serve, receive, set, spike, block, score) with frame and (x, y). STES (E2E-Spot
  backbone + spatial head) mTAP@0–4 frames 68.44 vs T-DEED 58.58; per class: serve 79.7, receive
  73.6, block 59.4, score 43.1. A 398×224 copy of the dataset (13 GB) is public; the code repo
  has no licence file. **Use** the dataset for pre-training or evaluation of a video-based
  contact spotter; broadcast view, so expect a domain gap.
- SoccerNet Ball Action Spotting ([2023 results](https://arxiv.org/abs/2309.06006)): 12 ball-touch
  classes spotted at frame level in broadcast soccer; E2E-Spot derivatives dominate. **Idea only**.
- [Dong et al., AAAI 2026, RacketVision](https://arxiv.org/abs/2511.17045)
  ([code](https://github.com/OrcustD/RacketVision), MIT). Ball + racket pose across three racket
  sports; trajectory forecasting with cross-attention over racket pose. *(abstract only)*
  **Skip**: no volleyball, no hit labels.
- Net crossing: no dedicated paper found. Gomez et al. used the net line; DL-Volleyball-Analysis
  uses the net tape to recover focal length for 3D. **Use** geometry: the net is a known vertical
  plane through the court homography, a crossing is the track passing the net's image line
  between two contacts.

## 3. Court registration and camera calibration

- [Farin, Krabbe, de With & Effelsberg 2004](https://doi.org/10.1117/12.526813), *Robust camera
  calibration for sport videos using court models*. Hough lines matched to a court model with
  RANSAC-like hypothesis testing; the classical baseline every later paper cites. **Use** as the
  starting point for line fitting on the background frame.
- [Citraro et al., MVA 2020](https://arxiv.org/abs/2003.14109), *Real-Time Camera Pose
  Estimation for Sports Fields*. FCN keypoint localisation plus field lines and player
  ground-plane positions; per-frame focal length and pose from a moving, uncalibrated camera;
  evaluated on soccer, basketball and a volleyball set. Code and data release not confirmed.
  *(abstract only)* **Idea only**: the only volleyball calibration paper; moving-camera
  machinery this project does not need.
- [Nie, Chen & Hamid, WACV 2021](https://www.amazon.science/publications/a-robust-and-efficient-framework-for-sports-field-registration).
  Dense grid of keypoints plus field features, multi-task; the template for keypoint methods.
  No code. *(abstract only)* **Idea only**.
- [Chu et al., CVPRW 2022, KpSFR](https://openaccess.thecvf.com/content/CVPR2022W/CVSports/papers/Chu_Sports_Field_Registration_via_Keypoints-Aware_Label_Condition_CVPRW_2022_paper.pdf)
  ([code](https://github.com/ericsujw/KpSFR), MIT). Keypoint heatmaps with label conditioning;
  TS-WorldCup dataset (3,812 soccer frames). **Adapt** only if a keypoint net is ever trained for
  moving footage.
- [Maglo, Orcesi & Pham, MMSports 2022, KaliCalib](https://arxiv.org/abs/2209.07795). Basketball;
  encoder-decoder keypoints with perspective-aware sampling, heavy augmentation; MSE ÷4.7 vs the
  challenge baseline; no code link. *(abstract only)* **Idea only**: augmentation for arena
  variety.
- [Theiner & Ewerth, WACV 2023, TVCalib](https://arxiv.org/abs/2207.11709)
  ([code](https://github.com/MM4SPA/tvcalib), MIT; segmentation weights). Camera parameters, not
  a homography, by minimising segment reprojection of line/point-cloud correspondences; soccer.
  **Adapt**: a permissive optimiser for lines once the line segmenter exists; a 3D camera matters
  if ball height is ever needed.
- [Gutiérrez-Pérez & Agudo, CVIU 2026, PnLCalib](https://arxiv.org/abs/2404.08401) (extended
  *No Bells, Just Whistles*, CVPRW 2024; [code](https://github.com/mguti97/PnLCalib), GPL-2.0).
  Keypoints and lines on a 3D field model, non-linear refinement; best single-view numbers on
  SoccerNet-Calibration, WC14, TS-WorldCup. **Skip** (GPL-2.0); read for the refinement step.
- [Falaleev & Chen, MMSports 2024](https://arxiv.org/abs/2410.07401)
  ([code](https://github.com/NikolasEnt/soccernet-calibration-sportlight), no licence file),
  winner of the [SoccerNet 2023](https://arxiv.org/abs/2309.06006) calibration challenge (score
  0.55 vs 0.08 baseline): keypoints + lines, extra points from line/conic intersections, a voter
  over reliable points. **Idea only**: the voting over derived points.
- [Agrawal, Sundararajan & Sagar 2024](https://arxiv.org/abs/2404.06977), *Accurate Tennis
  Court Line Detection on Amateur Recorded Matches*. Hough + homography with pretrained shadow
  removal and object detection to clean amateur, dirty courts; qualitative only; no code.
  *(abstract only)* **Idea only**: pre-clean the background frame (players, shadows) before
  line fitting.
- [DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis) (MIT).
  18×9 m model, 14-point keypoint model from Roboflow Universe sets (CC BY 4.0): 0.10 m median on
  held-out broadcast clips (96% < 0.3 m), 0.49 m on gym images; for fixed end-line cameras the
  court is fitted to the painted lines of an empty-court background image, 0.02–0.06 m median on
  5/6 clips, one clip off by 1.06 m; net tape gives the focal length. **Use**: the line-fitting
  path and its failure case (check every match once by hand).
- Roboflow Universe volleyball court keypoint sets:
  [primaryws](https://universe.roboflow.com/primaryws) (862 images, YOLO11n-pose variant),
  [protom](https://universe.roboflow.com/protom/volleyball-court-detection-tpvsi) (CC BY 4.0).
  Blog by the VballNet author on an 8,000-image court set (page blocked during verification, not
  read). **Idea only**, if a keypoint net is wanted for a second camera.
- Lens distortion. [Fitzgibbon 2001](https://doi.org/10.1109/CVPR.2001.990465): one-parameter
  division model estimated jointly with the homography. [Devernay & Faugeras 2001](https://doi.org/10.1007/PL00013269)
  and [Thormählen et al. 2003](https://www.informatik.uni-marburg.de/~thormae/paper/MIRA03-TTHBIW.pdf):
  distortion from line straightness, with outlier rejection of truly curved lines.
  [OpenCV fisheye](https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html) and
  [Gyroflow](https://docs.gyroflow.xyz/app/getting-started/lens-calibration) (checkerboard
  video; the Osmo Action 3 is not among its built-in profiles). **Use** a checkerboard once per
  locked setting; division model from the court lines as the no-checkerboard fallback.

## 4. Volleyball action recognition

Datasets:

- [SFU Volleyball dataset](https://github.com/mostafa-saad/deep-activity-rec) (Ibrahim et al.,
  CVPR 2016; code BSD-2-Clause, dataset licence not stated). 55 YouTube videos, 4,830 annotated
  frames (±20 frames of context), player boxes with 9 actions (waiting, setting, digging,
  falling, spiking, blocking, jumping, moving, standing) and 8 group activities (left/right set,
  spike, pass, winpoint). Broadcast-style side view; WASB's volleyball weights were trained on
  ball annotations added to it. Label errors documented by
  [DECOMPL](https://arxiv.org/abs/2303.06439) (ICIP 2024 re-annotation). **Use** for
  pre-training a pose/crop action model and for the ball; the group-activity task itself is not
  this project's.
- [Waltner, Mauthner & Bischof 2014](https://arxiv.org/abs/1404.6413),
  [Volleyball Activity Dataset](https://www.tugraz.at/index.php?id=17751). 6 HD games, Austrian
  Volley League 2011/12, 18,960 frames, 36,178 player annotations, 7 classes (serve, reception,
  setting, attack, block, stand, defense/move); player-centred classification 77.56%, +18 points
  on some classes with a temporal context descriptor. Licence not stated. **Use** for
  evaluation: the closest label set to this project's actions.
- [MultiSports, ICCV 2021](https://arxiv.org/abs/2105.07404) ([repo](https://github.com/MCG-NJU/MultiSports),
  code MIT, dataset CC BY-NC 4.0). 3,200 clips, 37,701 action tubes over four sports including
  volleyball with fine-grained classes (serve, block, pass, spike, dink...; class list not
  re-verified here); broadcast. **Use** for research evaluation only (NC).
- [SportsHHI, CVPR 2024](https://arxiv.org/abs/2404.04565). 34 human-human interaction classes
  in basketball and volleyball, 11,398 keyframes, 50,649 interactions. *(abstract only)*
  **Idea only**: interaction labels (set-to, block-against) are a model for attribution labels.
- [VNL-STES](https://hoangqnguyen.github.io/stes/) (§2): serve/receive/set/spike/block/score
  with location; the only volleyball set whose labels are contacts rather than clips.
- [VREN, ICKG 2022](https://arxiv.org/abs/2209.13846) (Xia et al.): rally notation for
  professional and NCAA games, tasks rally outcome, setting/hitting type prediction;
  [RallyGraph / Graph Encoding, KDD-W 2023](https://arxiv.org/abs/2308.11142): GNN over
  contact-by-contact graphs; [PathFinder, ICDMW 2023](https://arxiv.org/abs/2309.14753):
  setting-tactic classification from the set-ball trajectory, single camera, plus a front/back
  row test for the opposite hitter. The companion [VolleyStats](https://github.com/haotianxia/VolleyStats)
  repo has no licence; it builds on [tprlab/vball](https://github.com/tprlab/vball)
  (Apache-2.0). *(abstracts only)* **Adapt** the trajectory-based set classification; the
  notation language is a reasonable schema for the stats output.
- [VolleyVision](https://github.com/shukkkur/VolleyVision) (AGPL-3.0): ~14k-image action
  dataset, five frame-level classes (block, defense, serve, set, spike), YOLO classifiers.
  [DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis):
  YOLO26s-cls on player crops weighted by ball position, macro-F1 0.678 (block, receive, set,
  spike). **Use** as weak baselines; frame-level crops ignore the contact order this project has.

Methods:

- [Zhou et al., ECCV 2022, COMPOSER](https://arxiv.org/abs/2112.05892)
  ([code](https://github.com/hongluzhou/composer), no licence). Keypoint-only multiscale
  transformer; 94.5% group accuracy on SFU Volleyball with keypoints alone (96.3% on the
  re-annotated set). A 2025 Windsor thesis reports 79.0% person-level action accuracy
  keypoint-only. **Idea only**: evidence that pose tokens carry the action; implement
  independently.
- [Chang, CVPRW 2026, BST](https://arxiv.org/abs/2502.21085): badminton stroke types from
  skeleton + shuttle trajectory + court position, clipped around each swing; TemPose line
  ([TemPose-TF-ASF 2026](https://arxiv.org/abs/2605.02558)) adds neighbouring-stroke context.
  *(abstracts only)* **Adapt**: per-contact clip of (pose, ball track, court position, previous
  and next contact) is the input design for serve/reception/set/attack/block/dig.
- [Nako et al., ICPRAM 2025](https://doi.org/10.5220/0013238000003905), *Hierarchical
  Classification for Automatic Assessment of the Reception Quality*. TimeSformer on raw video,
  Data Volley labels, one camera behind the court, 11 university matches, 1,508 receptions;
  six-class 0.725, hierarchical steps 1.00 (front/back), 0.95 (A/B vs C), 0.77 (A vs B). No
  code. **Idea only** for the later 0–3 reception grade: labels from a scout file, hierarchical
  split, and a reminder that A vs B is the hard part.
- [Kodathala et al. 2026](https://arxiv.org/abs/2609.28049): single-frame CV is not competitive
  on motion tasks; a small trained model beats VLM prompting on contacts. **Use** (§1).

## 5. Player detection, tracking, re-identification, attribution

- Trackers: [ByteTrack, ECCV 2022](https://github.com/ifzhang/ByteTrack) (MIT),
  [BoT-SORT 2022](https://github.com/NirAharon/BoT-SORT) (MIT), both bundled in Ultralytics.
  **Use** (planned).
- [SportsMOT, ICCV 2023](https://arxiv.org/abs/2304.05170) ([repo](https://github.com/MCG-NJU/SportsMOT),
  CC BY-NC 4.0; [MixSort](https://github.com/MCG-NJU/MixSort), MIT). 240 sequences, basketball,
  volleyball (serve-zone views, ~12 tracks per clip), football, from official recordings on
  YouTube. **Use** for evaluating the tracker; MixSort's appearance association is a cheap
  upgrade.
- [Sun et al., ACCV-W 2024, GTA](https://arxiv.org/abs/2411.08216). Appearance-based global
  tracklet split-and-merge post-processing, new SportsMOT state of the art; code not located.
  *(abstract only)* **Adapt** as the offline pass (this project is offline).
- [Scott et al., CVPRW 2024, TeamTrack](https://arxiv.org/abs/2404.13868)
  ([repo](https://github.com/atomscott/TeamTrack), MIT). Full-pitch soccer, basketball, handball
  from fisheye side views and drones, 4.3M boxes. **Idea only**: the fisheye side view is the
  closest camera geometry to this project's; useful for pre-training the detector on wide views.
- [SoccerNet-GSR, CVPRW 2024](https://arxiv.org/abs/2404.11335) ([sn-gamestate](https://github.com/SoccerNet/sn-gamestate),
  GPL-3.0; [TrackLab](https://github.com/TrackingLaboratory/tracklab), MIT). Tracking + re-ID +
  team + jersey + pitch localisation on a minimap, 200 clips.
  [Golovkin et al. 2025](https://arxiv.org/abs/2504.06357): split tracklets by jersey and team,
  merge same-jersey tracklets only when non-overlapping, same team and physically reachable, then
  re-ID. [PRTreID 2024](https://arxiv.org/abs/2401.09942): one part-based embedding for re-ID,
  team and role. *(abstracts only)* **Adapt** the merge rules; TrackLab is a usable skeleton.
- Jersey numbers. [Koshkina & Elder, CVPRW 2024](https://arxiv.org/abs/2405.13896)
  ([code](https://github.com/mkoshkina/jersey-number-pipeline), CC BY-NC 3.0, weights): outlier
  removal by re-ID features, legibility classifier, pose-guided crop, PARSeq scene-text model,
  tracklet consolidation; hockey → soccer transfer. [Balaji et al., MMSports 2023](https://arxiv.org/abs/2309.06285):
  keyframe selection since numbers are visible in few frames. [Grad, CVPRW 2025](https://cvpr.thecvf.com/virtual/2025/35507):
  single-stage digit-compositional classifier with Dirichlet uncertainty, 85.62% tracklet
  accuracy on SoccerNet (2,853 tracklets, classes 1–99 and "none"). **Adapt** the Koshkina
  pipeline structure with permissive parts (ViTPose/RTMPose crop, PARSeq is Apache-2.0); the
  rotation order resolves the tracklets whose number is never legible.
- Team colour: [roboflow/sports](https://github.com/roboflow/sports) (MIT) `TeamClassifier`
  (SigLIP crop embeddings → UMAP → k-means); a 2025 GSR entry clusters jersey colours and
  assigns sides by mean x position. **Use**.
- [Holmberg 2026, Selective Mask Propagation](https://arxiv.org/abs/2606.13033). Training-free:
  hands hard windows to a video-object-segmentation model only when assignment uncertainty
  fires. *(abstract only)* **Idea only** for net-crowd occlusions.
- Pose: [RTMPose](https://arxiv.org/abs/2303.07399) (Apache-2.0, MMPose) or YOLO11-pose
  (AGPL-3.0). **Use** either; wrists and hands are the attribution signal.
- Contact attribution. [Wang, Mills, Billingham, Robertson & Hosoi, Sports Engineering 2025](https://doi.org/10.1007/s12283-025-00518-3):
  skeletal + ball tracking, a touch-probability model picks the touch frame, rules or a
  supervised model pick the player; 82.5% on World Cup duels, >90% aerial; data from FIFA, no
  code. [Chien & Yu 2023](https://arxiv.org/abs/2307.16000): pose sequences predict the hit.
  [Kodathala et al. 2026](https://arxiv.org/abs/2609.28049): identity is the hardest stage and
  motion cannot recover unseen numbers. **Adapt**: wrist/hand–ball distance at the contact
  frame, learned over pose + ball + court side, with the rotation order as a prior.

## 6. End-to-end systems and evaluations

- UFP thesis, 2026 ([PDF](https://bdigital.ufp.pt/bitstreams/9e2cbd9e-89d4-4191-a1bc-7a0533e97f9f/download);
  the repository sits behind a bot check, so title and author could not be read; figures from the
  indexed text). Semi-automatic pipeline: YOLO ball detection, temporal tracking, scoreboard
  reading, manual court calibration and marker ROI, rally management, event interpretation
  (attack, block, out, net, ace, error). Agreement with manual review 77.38% over 84 points
  (81.82% set 1, 72.50% set 2). Failures: fast rallies, trajectories near the net and lines,
  other balls, venue-dependent backgrounds. **Use** as the agreement baseline and the failure
  list to test against.
- [DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis) (MIT,
  NTOU, active Oct 2026). Single camera → point-by-point record: court (§3), VballNet V4c or
  fine-tuned WASB (§7), YOLO26s + BoT-SORT (IDF1 0.690, HOTA 0.636), crop action classifier
  (macro-F1 0.678), digit voting (mAP 0.824 on unseen teams), rally classifier (F1 0.76 fixed
  camera), 3D trajectory fit (attack error 0.76 → 0.31 m on synthetic rallies), review web app;
  3 min of fixed-camera video takes 19 min on a laptop CPU. **Use**: the closest open project;
  borrow stage by stage.
- [Kodathala et al. 2026](https://arxiv.org/abs/2609.28049) (§1): the only published study of
  this exact setting; no code.
- [Xia, Tracy et al.](https://arxiv.org/abs/2309.14753) line (VREN, RallyGraph, PathFinder) and
  [VolleyStats](https://github.com/haotianxia/VolleyStats) / [vball](https://github.com/tprlab/vball)
  (Apache-2.0): stats from a single camera, setting tactics; VolleyStats unlicensed. **Adapt**
  vball ideas only.
- [Gomez et al. 2014](https://doi.org/10.1371/journal.pone.0111730) (beach, §2) and
  [Chen et al. 2012](https://doi.org/10.1007/s11042-011-0833-y) (indoor broadcast, §2): the two
  older single-camera volleyball systems; both document how far pure vision falls short.
- [masouduut94/volleyball_analytics](https://github.com/masouduut94/volleyball_analytics)
  (GPL-2.0): YOLOv8 actions + ball + game-state classifier. **Reference only** (licence).
- Balltime ([Hudl](https://www.hudl.com/products/balltime)): uploads processed within an hour,
  touches and players tagged, downtime removed, ball trajectory, serve speed, jump height;
  acquired by Hudl in 2025. No publications or accuracy figures. **Skip** as a source; it fixes
  the feature bar.
- [Zhao et al. 2023](https://arxiv.org/abs/2307.03353), survey of deep learning in sports: notes
  volleyball datasets are few and small. **Idea only**.

## 7. Ball tracking improvements

- [Tarashima et al., BMVC 2023, WASB](https://arxiv.org/abs/2311.05237)
  ([code](https://github.com/nttcom/WASB-SBDT), MIT). HRNet heatmaps, position-aware training,
  temporally consistent inference; new ball annotations on the SFU Volleyball dataset. The
  project's chosen tracker. **Use**.
- Fine-tuning on own footage: [DL-Volleyball-Analysis](https://github.com/DL-Volleyball-Analysis/volleyball-analysis)
  fine-tuned WASB on broadcast + gym data, F1 0.942 on held-out gym matches vs 0.859 for VballNet.
  [Vandeghen, Cioppa & Van Droogenbroeck, CVPRW 2022](https://arxiv.org/abs/2204.06859):
  teacher–student semi-supervision with losses that let the student doubt the teacher, from a
  small labelled set plus unlabelled broadcast video. *(abstract only)* **Use**: label a few
  hundred frames per gym, pseudo-label the rest, fine-tune WASB.
- [Gossard et al., CVPRW 2026, BlurBall](https://arxiv.org/abs/2509.18387). Label the ball at
  the centre of the blur streak and predict blur attributes; improves detection across models.
  *(abstract only)* **Idea only**: adopt the centre-of-blur convention when labelling 50 fps
  spikes.
- [VballNet](https://github.com/asigatchov/vball-net-pytorch) (MIT) and
  [TrackNetV3 beach weights](https://huggingface.co/deadfast/beach-volley-vision-models):
  already benchmarked, behind WASB.
- 3D from one view. [Chen et al. 2012](https://doi.org/10.1007/s11042-011-0833-y): physics +
  calibration. [MVA 2021, monocular volleyball](https://www.mva-org.jp/Proceedings/2021/papers/P1-14.pdf):
  gravity, drag and Magnus model with drift correction from volleyball motion features, 82.5%
  success (server timed out during verification; from the index record).
  [Van Zandycke & De Vleeschouwer, CVPRW 2022](https://arxiv.org/abs/2204.00003) and
  [Caio et al., MMSports 2023](https://arxiv.org/abs/2309.03640): per-frame 3D from the ball's
  pixel diameter or its ground projection, calibrated camera, basketball
  ([deepsport](https://github.com/gabriel-vanzandycke/deepsport), CC BY-NC-ND).
  [Ponglertnapakorn & Suwajanakorn, CVPRW 2025, Where Is The Ball](https://arxiv.org/abs/2506.05763):
  LSTM from 2D track to 3D in a camera-independent canonical frame, trained on simulation,
  generalises to real multi-bounce sequences. [Vorobev et al. 2025](https://arxiv.org/abs/2506.07981):
  multi-mode state model, centimetre-level soccer 3D from one broadcast camera, proprietary
  data. [TT3D, CVPRW 2025](https://arxiv.org/abs/2504.10035): bounce state chosen by
  reprojection error, spin inferred. *(abstracts only)* **Idea only** until landing accuracy or
  quality grades need height; a 4K side view at 50 fps with a known 18×9 m court is a favourable
  case for the physics approaches.
- Trajectory smoothing: TrackNetV3 inpainting (§2) for gaps; for contacts, do not smooth across
  a suspected contact (piecewise fits per free flight, as in Gomez et al.).
