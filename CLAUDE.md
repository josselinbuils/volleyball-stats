# CLAUDE.md

Automatic per-player volleyball stats from one fixed sideline camera (see README.md): Python
pipeline in `src/volleyball_stats/`, match page in `web/` (React + shadcn/ui), one benchmark per
step in `benchmarks/`. The owner plays at ASPOM Bègles (adult leisure). Their camera: DJI Osmo
Action 3, 4K 50 fps; their processing PC: RTX 5080 under WSL2.

## Rules

- Speak English with the owner; the page and the review page open in French (fr first, then en, in
  `web/src/locales/`). UX first: understandable by anyone, never traded for performance.
- Never publish, host or share anything without the owner. The hosted page has no password: it
  never carries real footage or player pictures (nor anything cut from them) without every
  player's consent; the names given in the review stay on it (the owner's choice). Footage may go
  online without that consent only behind a password, unreachable by direct link without it. Never
  republish the YouTube clips in `data/`.
- Commit with the personal identity (`Josselin BUILS <josselin.buils@gmail.com>`), never a work email.
- A fix or feature done: commit it and restart the review (idle first, see below) without asking.
- No new Python dependency without asking (no scipy: numpy and what is installed).
- The review server binds 127.0.0.1 only. `outputs/` (gitignored) holds names of real people
  (`player_names.json`, `roster.json`): never commit it.
- Benchmark-driven: change a step, run its benchmark, report the numbers before and after.
- A review question about who touched the ball always offers every player of both teams: the
  touch's team is often wrong. The answer takes the picked player's team.

## Conventions

- Format web files with `npx prettier --single-quote --print-width 200` (no config file: the
  defaults restyle everything). Some files already differ; only format the ones you touch.
- The page's build is committed in `src/volleyball_stats/site/`: after any `web/` change run
  `npm run build` in `web/` and commit the build with it. It makes the page, `scene3d.js` (three.js)
  that the page loads only when the 3D view is shown, and in `matches_site/` the list of the hosted
  matches (`matches.html`, `src/matches.tsx`).
- Python style: short docstrings, comments only where needed, `ponytail:` comments for deliberate
  limits with their upgrade path. Tests in `tests/`, web tests beside their helpers.

## Check a change

```bash
uv run pytest -q
cd web && npx tsc --noEmit -p . && npm test && npm run build
uv run python -m volleyball_stats.web outputs/side_setend --video data/side_setend.mp4 --court outputs/court/side_holdout.json
```

The page holds no video by default; `--footage full --club 1 --pictures` (saved in
`outputs/VIDEO/page.json`) brings back the video and the club's pictures for features that need them.

Then open `outputs/side_setend/site/index.html` (two sets) or `outputs/side_holdout/site/` (one
set). In browser checks mute the videos and check a phone width (no horizontal page scroll). The
"Analyse" columns stay empty on these short clips: lower `MIN_TRIES` in
`web/src/components/Stats/helpers/insights.ts` temporarily to see them, and restore it before the
build you commit. `benchmarks/scale.py` measures memory on a 2-hour match, `benchmarks/speed.py`
the trackers' speed (`outputs/speed/side_holdout_4k.mp4` is a 4K test copy).

## State and next steps

- Weak spots: rally ends. On two labelled 10 minutes of the first match (`benchmarks/rallies`),
  pipeline F1 ±1 s 0.86 on the span the 31 Oct `served` fixes were tuned on, 0.58 on the other
  (0.57 before the fixes; a 30 s rally missed whose server stood out of view); a third of the
  school match's held-out rallies missed. How a rally
  ends (in, out, fault) is the least reliable measure, attribution is right 76-87% of the time
  on the labelled clips (pose on the wrists since 1 Nov; 108 of the 139 hard touches answered on the first match)
  (its doubts, a player twice in a row and spot checks are asked in the review as "Qui a touché le
  ballon ?"; `benchmarks/attribution/answers.py` scores the picks on those answers),
  identity IDF1 0.81-0.89. Free balls rest on one labelled example. The ball often leaves the frame
  (high serves and sets, the owner noticed): on the first match 47 of the ~950 track gaps in rallies
  go through the top; the false touches they made are dropped (`attribution.FAR`) and no net crossing
  is lost (5, all under `contacts.MAX_GAP`), so carrying the flight across them waits for a match
  where it shows.
- The first match (`data/first_match.mp4`, 4K, court `outputs/courts/aspom_begles.json`): its review
  runs with `uv run python -m volleyball_stats.review outputs/first_match --video data/first_match.mp4
  --court outputs/courts/aspom_begles.json` (http://127.0.0.1:8765, `/review#questions`,
  `/review#match`); each apply rebuilds the pages, its "Mettre en ligne" uploads the hosted ones when the owner
  wants (`outputs/first_match/publish.json`); "Apprendre de mes réponses" retrains the learned attribution and reruns the pipeline (`learn --rerun`).
  Before stopping the review (a restart is needed for a server or page change), check that
  `curl -s 127.0.0.1:8765/progress` gives `{}`: otherwise an apply is running. On 1 Nov: 129 rallies
  on the page for 128 points (25-23, 25-12, 25-18 given), 46 questions open (touches found by the
  applies since).
  Rerun on 1 Nov with the owner's go (the 31 Oct and 1 Nov fixes; 40 min on the M4: relances 11.5,
  wrists 12, teams 15.5; backup in `outputs/first_match/backup-before-rerun-1nov/`), the answers moved
  onto the new windows by `volleyball_stats.rekey`. A rerun moves the windows the answers point at:
  rekey after each one. Not in its outputs yet: the 1 Nov server's bounce fix (rally 43678, 14:33,
  comes back with the next rerun).
  `uv run python -m volleyball_stats.learn outputs/first_match --video data/first_match.mp4 --court
  outputs/courts/aspom_begles.json` scores every step on the answers and the checked rallies, against
  its last run (`learn.json`).
  Stats: a serve or an attack the other team touches and loses is no point by itself, that touch's
  fault wins the rally (the owner's rule, 1 Nov; an ace or a kill lands untouched); an attack blocked
  for a point is a fault (`web.credited`). The viewers' "Signaler" reports (see Hosting) are the main source of
  corrections: fetch them, record the clear
  ones (a named player on a replayed touch, "pas une phase de jeu") as pending review answers, leave
  the rest (no comment, unsure) to the review's Match tab, which lists each rally reported; then score and fix
  the steps they point at. Kili labels (`docs/kili_labelling.md`) only where reports are not enough.
  The review also asks every touch its page credits to no named player (a player on court under
  `web.BRIEF_S` of a set is a tracking slip): the page should show no unidentified player.
- `docs/next_steps.md`: what the 1 Nov answers changed in the pipeline and what is left, with the
  numbers; the plan for learning from the review (`learn`).
- Open, most useful first:
  1. In use by the owner since 1 Nov: the review's Match tab (`#match`) holds the reports, no longer
     questions. The video plays the match freely, over a zoomable bar of every rally, touch and report.
     Beside it, the touches around the video: correct, add (a serve before a rally starts it, and the
     touches added after it are that rally's), remove, join two rallies (`join` answers), start a rally
     at a moment (`split` answers: one missed, or the second of two taken for one; `web.rally_table`).
     A rally checked keeps the winner it showed (`pinned` answers, the review's winner answers still win). "Valider
     l'échange" saves and checks the rally: green, its reports handled, until a new report; "Retirer la
     validation" unchecks it. Saved corrections not yet in the review's page show in the editor (the
     last report answer carries them all, `review.superseded`). Automatic reports (`review.unusual`)
     flag no serve first, two serves, a reception not right after a serve, a serve not followed by a
     reception, four touches in a row, the wrong server, no touch, no winner, a set ending off the
     score given (`scoreOff`, asked again once the score moves; the list shows the running score). Rallies are named by
     their `rallies.csv` start (`key` on the page), which an added serve moves.
  2. Reports to handle in the Match tab: 76 on 1 Nov (22 from the viewers fetched on 31 Oct 23:10,
     `outputs/feedback-20261031-231035.log`, the online log emptied after; the rest automatic), 3
     rallies checked. `outputs/feedback-conflicts.log` is no viewer's: Claude's note on two answers
     that disagreed at 14:00 (merged, Anthony kept).
  3. The first match: 1 answer waiting for the owner's apply, which also brings the 1 Nov stats rules
     and the rerun to the hosted pages. Backups of the answers from the
     1 Nov repairs (`outputs/first_match/identity_answers.before-*.json`) can go once the owner is happy.
  4. Videos: the hosted 1080p copies have a keyframe every 2 s and a 720p copy plays in small players
     (all three live since 1 Nov; their sources in `~/Downloads`, named in `publish.json`).
  5. Rally ends and winners: `rallies.whistled` as a fallback is in (held out found R 1.00, F1 ±1 s 0.57).
     Left on 50:00-60:00: two false windows (server bouncing the ball, a ball rolled back), ends cut by
     another court's whistle (-4.1 s) or the ball out of sight (-3.0, -2.3, and -10 s for 58:55), a rally
     joined to its dead-ball tail by the 8 s rule (+10 s); then how rallies end (in, out, fault).
  6. The review's rally answers (`identity_answers.json` "rally") as labels to drop false windows
     automatically (asked, not started).
  7. Node.js and library updates on the owner's services (offered by the owner, not done).
  8. Names: a player without a jersey shows their tracking number (Sylvain: 10), which can clash with
     real jerseys: show initials instead? (Théo and Maeva sharing 10 is right.)
  9. Deferred: the pose check on passes, sets and digs (hands near the ball, +1-2 of 42 touches on
     the benchmark for a pose pass over every touch); the serve rotation check (unverified, ~9
     players a team rotate in).
  10. On the owner's RTX 5080 PC: measure `speed.py`, tune jersey numbers on that footage.
  11. Later: a 3D view that looks like the ASPOM gymnasium of the first match.

## Hosting

https://josselinbuils.dev/volleyball/ lists the matches, each at `/volleyball/DATE-TEAM-vs-TEAM/`
(the first match at `/volleyball/2026-10-29-aspom-01-vs-aspom-02/`), from the OVH server (`ssh root@<OVH IP> -i ~/.ssh/id_ed25519_ovh`): a
`volleyballstats` nginx service in `/home/ubuntu/docker` (the owner's `docker` repo: changes go through a PR
there, assigned to the owner), the site in `volleyball-stats/site`, the `/volleyball` route in
`reverse-proxy/Caddyfile` (Caddy since 31 Oct; the Node proxy pegged the CPU gzipping `players.js`: PR
josselinbuils/docker#2, rollback `/root/rollback-proxy.sh`). `/usr/local/bin/vbs-monitor.sh` logs the CPU every
minute to `/var/log/vbs-monitor/` with a snapshot when busy; `matches.build` writes `.gz` copies nginx sends as
they are (`gzip_static`). SSH is key-only, but for root with a password from the Docker networks: the
build manager (`josselinbuils/build-manager`, on a push to master of blog or portfolio) logs in so and
rebuilds that service with `docker compose`. Every service restarts with the server. The docker repo
takes commits on master directly. Cloudflare and browsers keep the hashed and `?v=` files for good (the
unhashed ones load with the build's hash, card pictures with their own), images a day, pages are
checked each time; the video copy's files only in the viewer's browser (`private`). `outputs/hosted/` holds the hosted
site: build each match into it without footage or pictures, list them (which names their folders),
copy it over; nothing restarts. With `outputs/MATCH/publish.json` (`site`, `url`, `light`, `av1`, `small`,
`club`, `upload` as `root@<OVH IP>:…/site/`, `key`), the review's "Mettre en ligne" does all of it
(`matches.host`, refusing to upload a video copy that opens without the password) and says when:

```bash
uv run python -m volleyball_stats.web outputs/first_match --video data/first_match.mp4 --court outputs/courts/aspom_begles.json --footage none --club 1 --no-pictures --video-page video/ --feedback /volleyball/feedback --out outputs/hosted/MATCH
uv run python -m volleyball_stats.matches outputs/hosted
rsync -rt --delete -e "ssh -i ~/.ssh/id_ed25519_ovh" outputs/hosted/ root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/site/
```

A match's video goes in its `video/` folder (`--out outputs/hosted/MATCH/video --footage full
--copy-video --club both --pictures`, `--light-video` for a lighter H.264 copy on the same timeline
(`ffmpeg -i VIDEO -vf scale=1920:1080:flags=lanczos,fps=25 -c:v libx264 -preset slow -crf 28
-maxrate 5M -bufsize 10M -g 50 -c:a aac -b:a 96k -movflags +faststart`), `--av1-video` for an AV1
one the browsers that can play first (same with `-c:v libsvtav1 -preset 6 -crf 40 -g 50`; VMAF 90.7
at 541 kb/s against the H.264 copy's 89.0 at 1254 kb/s with `-g 250`); the public build links to it
with `--video-page video/`, whose dialog asks the password), `--small-video` for a 720p H.264 one
(same with `scale=1280:720`, -56% against 1080p) the page plays while its player is small: the
1080p copy in full screen, zoomed on the ball or over 1600 screen pixels wide, the video carrying on
where it stood. A keyframe every 2 s (`-g 50`) keeps the jumps between clips from freezing: 21
frames to decode a jump instead of 131 with `-g 250`, for +30% size in H.264, +60% in AV1. The
service's nginx serves every `/volleyball/*/video/` file only with the cookie `video_key`, the
SHA-256 of `volleyball:` and the password, listed in `volleyball-stats/video_key.conf` as
`"<sha256>" 1;` (mounted in the container, `nginx -s reload` after a change); otherwise it redirects
to the page with `?video=denied`, wrong keys limited to 10 a minute, `Cache-Control: private,
no-store` so Cloudflare keeps nothing. Check that a `curl` without it gets 302 before uploading a
video. The copies keep their source's date, so an upload skips an unchanged video.

Hosted pages are built with `--feedback /volleyball/feedback`: one tap on "Signaler" reports the
moment, "Préciser" then adds what is wrong and a comment to the same report (its `id`); the
service's nginx logs each POST (2 KB, 5 a minute per visitor) to
`volleyball-stats/feedback/feedback.log`. Fetch them keeping a dated copy (the review reads every
`outputs/feedback*.log`), then empty the log online:

```bash
scp -i ~/.ssh/id_ed25519_ovh root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/feedback/feedback.log outputs/feedback.log
cp -p outputs/feedback.log outputs/feedback-$(date +%Y%m%d-%H%M%S).log
uv run python -m volleyball_stats.feedback outputs/feedback.log
ssh -i ~/.ssh/id_ed25519_ovh root@<OVH IP> ': > /home/ubuntu/docker/volleyball-stats/feedback/feedback.log'
```

Test the report endpoint without writing to that log (it holds viewers' reports).

Sponsors live in `branding/aspom/sponsors/`, git-ignored: brands stay off GitHub, the
hosted page's build reads them from this machine.
