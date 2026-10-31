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

- Weak spots: `rallies.py` misses about a third of the rallies on the held-out clip, how a rally
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
  Stats: each team's points plus the other's faults give 74-53 (75-53 played). The viewers'
  "Signaler" reports (see Hosting) are the main source of corrections: fetch them, turn them into
  labels for the steps they point at (a "pas une phase de jeu" one becomes a pending rally answer in
  the review), score and fix those steps; Kili labels (`docs/kili_labelling.md`) only where reports
  are not enough.
- Open, most useful first:
  1. Missed rallies (`rallies.py`'s recall, its README's proposed fixes): the largest error left in
     the score.
  2. The review's rally answers (`identity_answers.json` "rally": 6 no play, 7 rallies) as labels to
     drop false windows automatically.
  3. Names: Théo and Maeva both have jersey 10 (a typo for one); a player without a jersey shows their
     tracking number (Sylvain: 10), which can clash with real jerseys: show initials instead?
  4. Deferred: the pose check on passes, sets and digs (hands near the ball, +1-2 of 42 touches on
     the benchmark for a pose pass over every touch); the serve rotation check (unverified, ~9
     players a team rotate in).
  5. On the owner's RTX 5080 PC: measure `speed.py`, tune jersey numbers on that footage.
  6. Later: a 3D view that looks like the ASPOM gymnasium of the first match.

## Hosting

https://josselinbuils.dev/volleyball/ lists the matches, each at `/volleyball/DATE-TEAM-vs-TEAM/`
(the first match at `/volleyball/2026-10-29-aspom-01-vs-aspom-02/`), from the OVH server (`ssh root@<OVH IP> -i ~/.ssh/id_ed25519_ovh`): a
`volleyballstats` nginx service in `/home/ubuntu/docker` (the owner's `docker` repo; that service is
only in the server's copy), the site in `volleyball-stats/site`, the `/volleyball` route in
`reverse-proxy/config.json`. Cloudflare caches the `.js` files for 4 hours: the unhashed ones load
with the build's hash (`?v=`), so a new build shows at once. `outputs/hosted/` holds the hosted
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

Hosted pages are built with `--feedback /volleyball/feedback`: viewers report what is wrong in a
moment, the service's nginx logs each report (POST only, 2 KB, 5 a minute per visitor) to
`volleyball-stats/feedback/feedback.log`. Fetch and list them to correct the analysis:

```bash
scp -i ~/.ssh/id_ed25519_ovh root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/feedback/feedback.log outputs/feedback.log
uv run python -m volleyball_stats.feedback outputs/feedback.log
```

Sponsors live in `branding/aspom/sponsors/`, git-ignored: brands stay off GitHub, the
hosted page's build reads them from this machine.
