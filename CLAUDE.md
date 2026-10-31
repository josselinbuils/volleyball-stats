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
- No new Python dependency without asking (no scipy: numpy and what is installed).
- The review server binds 127.0.0.1 only. `outputs/` (gitignored) holds names of real people
  (`player_names.json`, `roster.json`): never commit it.
- Benchmark-driven: change a step, run its benchmark, report the numbers before and after.

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
  ends (in, out, fault) is the least reliable measure, attribution is right 71-83% of the time
  (its doubts, a player twice in a row and spot checks are asked in the review as "Qui a touché le
  ballon ?"; `benchmarks/attribution/answers.py` scores the picks on those answers),
  identity IDF1 0.81-0.89. Free balls rest on one labelled example. The ball often leaves the frame
  (high serves and sets, the owner noticed): on the first match 47 of the ~950 track gaps in rallies
  go through the top; the false touches they made are dropped (`attribution.FAR`) and no net crossing
  is lost (5, all under `contacts.MAX_GAP`), so carrying the flight across them waits for a match
  where it shows.
- The first match (`data/first_match.mp4`, 4K, court `outputs/courts/aspom_begles.json`): its review
  runs with `uv run python -m volleyball_stats.review outputs/first_match --video data/first_match.mp4
  --court outputs/courts/aspom_begles.json` (http://127.0.0.1:8765, `/review` for the questions);
  every touch and rally-window question is answered, and each apply rebuilds and uploads the hosted
  pages (`outputs/first_match/publish.json`). Rallies: 130 windows on the page for 128 points; the
  estimated finals 26-23, 26-14, 23-18 against 25-23, 25-12, 25-18 given (the rest: missed rallies).
  Its outputs predate the 31 Oct `served` fixes: rerun the pipeline only when the owner says so (it
  moves windows the review's answers point at; backup in `outputs/first_match/backup-before-rally-fix/`).
  Stats: each team's points plus the other's faults give 74-53 (75-53 played). The viewers'
"Signaler" reports (see Hosting) are the main source of corrections: fetch them, record the clear
  ones (a named player on a replayed touch, "pas une phase de jeu") as pending review answers, leave
  the rest (no comment, unsure) to the review, which asks each rally reported; then score and fix
  the steps they point at. Kili labels (`docs/kili_labelling.md`) only where reports are not enough.
  The review also asks every touch its page credits to no named player (a player on court under
  `web.BRIEF_S` of a set is a tracking slip): the page should show no unidentified player.
- Open, most useful first:
  1. In progress, uncommitted in the working tree: free play in the review's report questions (owner's
     ask: the question points at a moment, nothing holds you to its rally). Done: `review.report_answer`
     takes changes anywhere in the match (`touches`, `added` placed by `window_of`, `rallies`: `{start,
     winner, play, end}` by window start frame) with `Questions.page_index`; `end` answers applied by
     `web.ended` (page build, `ball_track`, the review's touch questions), touches past an end dropped;
     Python tests pass. `ClipVideo` has a `free` mode (no loop, bar re-anchored around the video, all
     rallies as bands, ±10 s buttons), not yet type-checked. Left: rewrite `ReportEditor` (the touches
     of the rallies around the video, grouped by rally with clickable headers; the winner, no play,
     "Voir 5 s de plus" and "Finir l'échange ici" for the rally the video is in, or the one just
     ended), `ReportChanges` in `lib/review.ts`, `Review.tsx` (`free`, no clamp on a touch's replay),
     locales (`review.back`, `review.forward`, the end's labels); build, restart the review server
     (it serves its built copy), check desktop and phone, commit. Until then, do not restart the review
     server on this code: the committed page sends `winner`/`play` at the top level, which it ignores.
  2. Ask the owner: their last 7 report answers (10:23, 11:04, 31:44, 54:56, 56:07, 57:25, 66:40) were
     undone from a browser on 31 Oct; restore them from
     `outputs/first_match/identity_answers.before-undo.json` unless that was meant. The 2:39 report was
     undone on their ask (its old answer in `outputs/first_match/undone-report-2m39.json`).
  3. Viewers' reports: 18 fetched on 31 Oct 23:10 (`outputs/feedback-20261031-231035.log`), the online log
     not emptied yet (ask first). 32 report questions open in the review; 18:39 (Landy) and 53:12
     (Killian) are clear enough to record if the owner wants.
  4. The first match: answers pending, not applied; the pipeline rerun waits for the owner's go.
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
copy it over; nothing restarts. With `outputs/MATCH/publish.json` (`site`, `url`, `light`, `av1`,
`club`, `upload` as `root@<OVH IP>:…/site/`, `key`), the review does all of it after each apply
(`matches.host`, refusing to upload a video copy that opens without the password) and says when:

```bash
uv run python -m volleyball_stats.web outputs/first_match --video data/first_match.mp4 --court outputs/courts/aspom_begles.json --footage none --club 1 --no-pictures --video-page video/ --feedback /volleyball/feedback --out outputs/hosted/MATCH
uv run python -m volleyball_stats.matches outputs/hosted
rsync -rt --delete -e "ssh -i ~/.ssh/id_ed25519_ovh" outputs/hosted/ root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/site/
```

A match's video goes in its `video/` folder (`--out outputs/hosted/MATCH/video --footage full
--copy-video --club both --pictures`, `--light-video` for a lighter H.264 copy on the same timeline,
`--av1-video` for an AV1 one the browsers that can play first (`ffmpeg -i VIDEO -vf
scale=1920:1080:flags=lanczos,fps=25 -c:v libsvtav1 -preset 6 -crf 40 -g 250 -c:a aac -b:a 96k
-movflags +faststart`, VMAF 90.7 at 541 kb/s against the H.264 copy's 89.0 at 1254 kb/s); the
public build links to it with `--video-page video/`, whose dialog asks the password). The
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
