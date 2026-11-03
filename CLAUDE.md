# CLAUDE.md

Automatic per-player volleyball stats from one fixed sideline camera (see README.md): Python
pipeline in `src/volleyball_stats/`, match page in `web/` (React + shadcn/ui), one benchmark per
step in `benchmarks/`. The owner plays at ASPOM Bègles (adult leisure). Their camera: DJI Osmo
Action 3, 4K 50 fps; their processing PC: RTX 5080 under WSL2.

## Rules

- Speak English with the owner; the page and the review page open in French (fr first, then en, in
  `web/src/locales/`). UX first: understandable by anyone, never traded for performance.
- Interface text stays light (the owner's rule, 2 Nov): the fewest words a viewer needs, judged on all they see together, without
  caveats about estimates or remarks on what the interface already shows. Write and shorten so by default, without asking.
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
- "Le coin du coach" advises the team: it never names a player for a fault or a weak number (the owner's rule, 1 Nov).
- Benchmark-driven: change a step, run its benchmark, report the numbers before and after.
- A review question about who touched the ball always offers every player of both teams: the
  touch's team is often wrong. The answer takes the picked player's team.

## Conventions

- Web commands need Node 22 (`.nvmrc`): `nvm use` first.
- Format web files with `npx prettier --single-quote --print-width 200` (no config file: the
  defaults restyle everything). Some files already differ; only format the ones you touch.
- Spacing in `web/`: the design system's values only, and coherent: mirror what the neighbouring elements use.
- The page's build is committed in `src/volleyball_stats/site/`: after any `web/` change run
  `npm run build` in `web/` and commit the build with it. It makes the page, `scene3d.js` (three.js)
  that the page loads only when the 3D view is shown, and in `matches_site/` the list of the hosted
  matches (`matches.html`, `src/matches.tsx`).
- Python style: short docstrings, comments only where needed, `ponytail:` comments for deliberate
  limits with their upgrade path. Tests in `tests/`, web tests beside their helpers.
- A new match starts with `import_match` (README): `data/MATCH/MATCH.mp4` and `outputs/MATCH/`, named like its hosted page, everything of a match in those two folders.
- The review opens without a match on the list of the matches (`review.match_list`, those with a `source.json`); opening one replaces the server's process (`review.switch`).
- A match is named by its date and teams (`rename.target_name`): changing a team's name in the review renames its folders, video and backups, and restarts the server (`rename.py`); the old name stays an alias (`source.json`) for reports and viewers' choices. The hosted page follows on its next upload, with a redirect from its old address (`matches.write_redirects`).
- `match` refuses to track at a low priority or on a busy machine (`slow_run_reasons`, `--anyway`): tell the owner what it lists, stopping their work
  (Docker, Kili sandboxes) is their call. To correct a running job: `sudo renice 0 -p PID...` in their own terminal (`renice -n 0` changes nothing on
  macOS). A run can't survive a restart: tracking writes nothing until it ends. Idle, the M4 tracks 4K at 2.87 MB/s (6 h for 84 min); progress is the
  `ffmpeg` read offset (`lsof -o`) over the file's size.

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

- Weak spots: touches and rally ends. On the first match's 129 checked rallies (`learn`, 1 Nov 21:41)
  the pipeline finds 844 of the 945 touches and 835 of its 883 are real. Of the 101 missed, 71 have no
  contact in the ball track, 23 are detected outside a window (a rally cut early or started late), 7
  are removed after detection. Rallies on two labelled 10 minutes of that match (`benchmarks/rallies`):
  pipeline F1 ±1 s 0.90 on the span the 31 Oct `served` fixes were tuned on, 0.57 on the other (a 30 s
  rally missed whose server stood out of view); a third of the school match's held-out rallies
  missed. How a rally ends (in, out, fault) is the least reliable measure, attribution is right 76-87%
  of the time on the labelled clips (pose on the wrists since 1 Nov; 607 of the 673 touches answered on
  the first match; held out, the learned order 628 of 702, the rule 615)
  (its doubts, a player twice in a row and spot checks are asked in the review as "Qui a touché le
  ballon ?"; `benchmarks/attribution/answers.py` scores the picks on those answers),
  identity IDF1 0.81-0.89. Free balls rest on one labelled example. The ball often leaves the frame
  (high serves and sets, the owner noticed): on the first match 47 of the ~950 track gaps in rallies
  go through the top; the false touches they made are dropped (`attribution.FAR`) and no net crossing
  is lost (5, all under `contacts.MAX_GAP`), so carrying the flight across them waits for a match
  where it shows.
- The first match's last "Apprendre de mes réponses", 2 Nov 10:17, brought the 2 Nov pipeline work (`docs/plan.md`): touches found 872
  of 945, 863 of 909 real, types 778 of 872, named players 679 of 761, checked winners 117 of 128; the 1 Nov figures above are before it.
  The hosted pages carry it (last upload 2 Nov, about noon).
- The first match (`data/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4`, 4K, court `outputs/courts/aspom_begles.json`): its review
  runs with `uv run python -m volleyball_stats.review outputs/2026-10-29-aspom-1-vs-aspom-2 --video data/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4
  --court outputs/courts/aspom_begles.json` (http://127.0.0.1:8765, `/review#questions`,
  `/review#match`); each apply rebuilds the pages, its "Mettre en ligne" uploads the hosted ones when the owner
  wants (`outputs/2026-10-29-aspom-1-vs-aspom-2/publish.json`); "Apprendre de mes réponses" retrains the learned attribution and reruns the pipeline (`learn --rerun`).
  Before stopping the review (a restart is needed for a server or page change), check that
  `curl -s 127.0.0.1:8765/progress` gives `{}`: otherwise an apply is running. Its review is finished
  (1 Nov 22:03): 129 rallies, all checked, sets ending 25-23, 25-12, 25-18 as given, no warning, no
  answer waiting, the viewers' reports handled (the hosted pages last uploaded 22:03).
  `outputs/feedback-conflicts.log` is no viewer's: Claude's note on two answers that disagreed (merged).
  Last rerun: the owner's "Apprendre de mes réponses", finished 1 Nov 21:41 (3 min on the M4 with the poses
  cached, 40 min without them; `outputs/2026-10-29-aspom-1-vs-aspom-2/before-rerun/`); it moves the answers onto
  the new windows itself (`learn.rerun`, `rekey`), and the rallies checked came through it unchanged.
  The review's progress names each step and the pipeline's stage, with the time left from each one's
  last duration (`outputs/MATCH/review_timings.json`).
  `uv run python -m volleyball_stats.learn outputs/2026-10-29-aspom-1-vs-aspom-2 --video data/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4 --court
  outputs/courts/aspom_begles.json` scores every step on the answers and the checked rallies, against
  its last run (`learn.json`).
  Stats: a serve, an attack or a block the other team's next touch, the rally's last, loses is a point for it, that
  touch staying the other team's fault (the owner's rule, 1 Nov: labelled so, both count; a serve's is an ace); an attack
  blocked for a point is a fault (`web.credited`). The viewers' "Signaler" reports (see Hosting) are the main source of
  corrections: fetch them, record the clear
  ones (a named player on a replayed touch, "pas une phase de jeu") as pending review answers, leave
  the rest (no comment, unsure) to the review's Match tab, which lists each rally reported; then score and fix
  the steps they point at. Kili labels (`docs/kili_labelling.md`) only where reports are not enough.
  The review also asks every touch its page credits to no named player (a player on court under
  `web.BRIEF_S` of a set is a tracking slip): the page should show no unidentified player.
- `docs/next_steps.md`: what the 1 Nov answers changed in the pipeline and what is left, with the
  numbers; the plan for learning from the review (`learn`).
- The review's Match tab (`#match`) holds the reports, no longer questions. The video plays the match freely,
  over a zoomable bar of every rally, touch and report.
  questions. The video plays the match freely, over a zoomable bar of every rally, touch and report.
  Beside it, the touches around the video: correct, add (a serve before a rally starts it, and the
  touches added after it are that rally's), remove, end a rally (`end` answers), join two rallies (`join` answers), start a rally
  at a moment (`split` answers: one missed, or the second of two taken for one; `web.rally_table`).
  A rally checked is locked as it showed: its winner (`pinned`), touches (`locked`: a rerun loses or adds
  none), their players and actions (`touch`, `action`); no question its check answers is asked; unchecking
  unlocks it. A rally's winner follows its last touch (`web.followed`). "Valider
  l'échange" saves and checks the rally: green, its reports handled, until a new report; "Retirer la
  validation" unchecks it. Saved corrections not yet in the review's page show in the editor (the
  last report answer carries them all, `review.superseded`). Automatic reports (`review.unusual`)
  flag no serve first, two serves, a reception not right after a serve, a serve not followed by a
  reception, four touches in a row, the wrong server, no touch, no winner, a set ending off the
  score given (`scoreOff`, asked again once the score moves; the list shows the running score), then the moments the ball seems in play outside that set's rallies (`missedPoint`, `review.missed_points`: of 129 rallies hidden in turn, its 5 per set hold 86), over 2.5 s between two touches, a server out of rotation order, one jersey on two players of a team (allowed, the owner's: both may wear no team jersey; handled once). Rallies are named by
  their `rallies.csv` start (`key` on the page), which an added serve moves. A line between rallies
  shows the score after each one; a rally header turns orange with a warning; the match bar colours
  each rally (orange warning, green checked, grey to check) and its arrows go to the next one to
  check. "Faute de jeu" (`fault`): a fault without the ball (net, centre line, rotation), only added in
  the review: always a fault, no touch of the ball in the checks, counted in its player's faults.
  "À rejouer" (`redo`, beside the winners): the rally stays, its touches in play, nobody scores; picking
  a winner takes it back. "Erreur d'arbitrage" (`referee` answers, `wrongCall` on the page): the winner stays the
  team that got the point, the score follows it, the last touch keeps what really happened: the true
  winner is the other team. Nothing trains on how rallies end yet: such training reads these answers. The rally's "Commentaire": the owner's note, in the review only
  (`rally_comments.json`, moved by a rerun; on no page, so never hosted), saved on leaving the field.
- Open, most useful first:
  1. `docs/plan.md`: the touches left, the page ideas left, the 3D ball and TV mode's limits. A second match, filmed by the owner (2 Nov).
  2. That second match, held out whole: everything is tuned on the first. Retrain the ranker and
     re-sweep `identity.SHARPEN` after its review.
  3. Rally ends and winners (checked winners 114 of 128): `rallies.whistled` as a fallback is in (held
     out found R 1.00, F1 ±1 s 0.57). Left on 50:00-60:00: two false windows (server bouncing the ball,
     a ball rolled back), ends cut by another court's whistle (-4.1 s) or the ball out of sight (-3.0,
     -2.3, and -10 s for 58:55), a rally joined to its dead-ball tail by the 8 s rule (+10 s); then how
     rallies end (in, out, fault).
  4. The review's rally answers and the 129 checked rallies as labels to drop false windows
     automatically (asked, not started).
  5. Node.js and library updates on the owner's services (offered by the owner, not done).
  6. Deferred: the pose check on passes, sets and digs (hands near the ball, +1-2 of 42 touches on
     the benchmark for a pose pass over every touch); the serve rotation check (unverified, ~9
     players a team rotate in).
  7. On the owner's RTX 5080 PC: measure `speed.py`, tune jersey numbers on that footage.
  8. Once the second match's run ends: `rename` it (`outputs/second_match`, its court moves inside). The first is done (3 Nov); `data/`'s and `outputs/`'s
     other folders are test clips and benchmarks.
  9. The owner's plan (3 Nov), nothing started, not before the second match is reviewed and its quality known: a helper they trust,
     then maybe other people's matches. First a job queue the Mac and the 5080 pull from (they only reach out; a busy one takes no job),
     useful alone; then the VPS's system upgraded (2 vCPU, 3.7 GB, 18 GB free, Ubuntu 20.04), a login per person and the review on it, with
     the slow steps on the workers, a process per open match (`review.switch` restarts the only server) and crops prepared from the 4K.
     About 1-2 weeks, about EUR 0-1 a month. Other people adding matches is decided later: uploads, court setup in the browser, clubs kept
     apart, workers sandboxed, consent and GDPR (advice first; the hosting rules above would change on purpose). In between, a club sends a video
     and the owner processes it. Rejected for now: rented GPUs for everything (EUR 25-45 a month, rough, from third-party prices).

## Hosting

https://josselinbuils.dev/volleyball/ lists the matches, each at `/volleyball/DATE-TEAM-vs-TEAM/`
(the first match at `/volleyball/2026-10-29-aspom-1-vs-aspom-2/`), from the OVH server (`ssh root@<OVH IP> -i ~/.ssh/id_ed25519_ovh`): a
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
`club`, `upload` as `root@<OVH IP>:…/site/`, `key`; a match's video copies in its `data/MATCH/`), the review's "Mettre en ligne" does all of it
(`matches.host`, refusing to upload a video copy that opens without the password) and says when:

```bash
uv run python -m volleyball_stats.web outputs/2026-10-29-aspom-1-vs-aspom-2 --video data/2026-10-29-aspom-1-vs-aspom-2/2026-10-29-aspom-1-vs-aspom-2.mp4 --court outputs/courts/aspom_begles.json --footage none --club 1 --no-pictures --video-page video/ --feedback /volleyball/feedback --out outputs/hosted/MATCH
uv run python -m volleyball_stats.matches outputs/hosted --url https://josselinbuils.dev/volleyball/
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

The players' films and the match's summary (`film.py`, real footage): the review's "Créer N films" makes those whose `plan` changed, never an apply; only behind the page's password (the owner's rule, 2 Nov): `web.copy_films` puts them only beside a page with the video, and `matches.host` refuses to upload a video outside a `video/` folder or a film that opens without the password. `uv run python -m volleyball_stats.film outputs/MATCH --video VIDEO --court COURT [--names A,B]` does the same. Files in `outputs/MATCH/films/`, outside the backup.

The commentary's voice: `uv run --group voice python -m volleyball_stats.voice outputs/MATCH` after a page's build makes the missing audio in
`outputs/MATCH/voice/`, the next build takes it (a line no longer true of the match is left out), so after a review's changes run it, then upload.

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

Test the report endpoint without writing to that log (it holds viewers' reports): a GET writes an empty line too, which `feedback.read` skips.

Link previews: `matches.build` with a `url` tags the list and each match page (`og:*`) with a `preview.png` drawn there from teams, colours, score and date: never footage or a player.

Crawlers: the service's nginx answers 403 to the user agents of its `$blocked_bot` list (search engines, AI scrapers, SEO tools; link previews stay) and sends `X-Robots-Tag: noindex` on all, the pages carry the same meta tag. A bot lying about its name gets through; the domain's `robots.txt` has no rule, Cloudflare's bot settings are the owner's. A change of a mounted config from `git pull` needs `docker compose up -d --force-recreate --no-deps volleyballstats`: the running container keeps the old file.

Backup: while the review runs, every 10 minutes if something changed (and `uv run python -m volleyball_stats.backup
outputs/MATCH`), `backup.py` copies the match's folder (no old `backup-*`, no built pages), the courts, roster, reports
and sponsors to `/root/backups/volleyball-stats/DAY/` on the OVH server: outside the website, root only, unchanged
files hard-linked, the last 30 copies kept, none under 5 GB free. Restore command in `backup.py`. The source video
is not in it (42 GB, 18 GB free there): the owner backed the first match's up elsewhere (2 Nov).

Sponsors live in `branding/aspom/sponsors/`, git-ignored: brands stay off GitHub, the
hosted page's build reads them from this machine.
