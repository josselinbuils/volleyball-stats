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
  player's consent. Never republish the YouTube clips in `data/`.
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
  ends (in, out, fault) is the least reliable measure, attribution is right 71-83% of the time,
  identity IDF1 0.81-0.89. Free balls rest on one labelled example.
- Next: the owner films a first match (with consent); measure `speed.py` on the RTX 5080; tune
  rallies, contacts and jersey numbers on that 4K footage.

## Hosting

https://josselinbuils.dev/volleyball/ lists the matches, each at `/volleyball/DATE/` (`full_match`
at `/volleyball/2026-10-25/`), from the OVH server (`ssh root@<OVH IP> -i ~/.ssh/id_ed25519_ovh`): a
`volleyballstats` nginx service in `/home/ubuntu/docker` (the owner's `docker` repo; that service is
only in the server's copy), the site in `volleyball-stats/site`, the `/volleyball` route in
`reverse-proxy/config.json`. Cloudflare caches the `.js` files for 4 hours: the unhashed ones load
with the build's hash (`?v=`), so a new build shows at once. `outputs/hosted/` holds the hosted
site: build each match into it without footage or pictures, list them, copy it over; nothing
restarts:

```bash
uv run python -m volleyball_stats.web outputs/full_match --video data/full_match.mp4 --court outputs/court/side_holdout.json --footage none --club 1 --no-pictures --out outputs/hosted/2026-10-25
uv run python -m volleyball_stats.matches outputs/hosted
rsync -rt --delete -e "ssh -i ~/.ssh/id_ed25519_ovh" outputs/hosted/ root@<OVH IP>:/home/ubuntu/docker/volleyball-stats/site/
```

The first run rewrites `outputs/full_match/page.json`: put back the local build's options after.
Sponsors live in `branding/aspom/sponsors/`, git-ignored: brands stay off GitHub, the
hosted page's build reads them from this machine.
