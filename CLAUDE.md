# CLAUDE.md

Automatic per-player volleyball stats from one fixed sideline camera (see README.md): Python
pipeline in `src/volleyball_stats/`, match page in `web/` (React + shadcn/ui), one benchmark per
step in `benchmarks/`. The owner plays at ASPOM Bègles (adult leisure). Their camera: DJI Osmo
Action 3, 4K 50 fps; their processing PC: RTX 5080 under WSL2.

## Rules

- Speak English with the owner; the page and the review page open in French (fr first, then en, in
  `web/src/locales/`). UX first: understandable by anyone, never traded for performance.
- Interface text stays light (the owner's rule): the fewest words a viewer needs, judged on all they see together, without
  caveats about estimates or remarks on what the interface already shows. Write and shorten so by default, without asking.
- Never publish, host or share anything without the owner. The hosted page has no password: it
  never carries real footage or player pictures (nor anything cut from them) without every
  player's consent; the names given in the review stay on it (the owner's choice). Footage may go
  online without that consent only behind a password, unreachable by direct link without it. Never
  republish the YouTube clips in `data/`.
- Commit with the personal identity (`Josselin BUILS <josselin.buils@gmail.com>`), never a work email.
- A fix or feature done: commit it, push it to `main` and restart the review without asking, once `curl -s 127.0.0.1:8765/progress` gives `{}` (otherwise an apply is running). A restart passes `--no-browser`: the page is already open. Only a first start opens it.
- No new Python dependency without asking (no scipy: numpy and what is installed).
- The review server binds 127.0.0.1 only. `outputs/` (gitignored) holds names of real people
  (`player_names.json`, `roster.json`): never commit it.
- "Le coin du coach" advises the team: it never names a player for a fault or a weak number (the owner's rule).
- Benchmark-driven: change a step, run its benchmark, report the numbers before and after.
- A review question about who touched the ball always offers every player of both teams: the
  touch's team is often wrong. The answer takes the picked player's team.

## Conventions

- Web commands need Node 22 (`.nvmrc`): `nvm use` first.
- Format web files with `npx prettier --single-quote --print-width 200` (no config file: the
  defaults restyle everything). Some files already differ; only format the ones you touch.
- Spacing in `web/`: the design system's values only, and coherent: mirror what the neighbouring elements use.
- Tooltips in `web/`: `Tip` only, never a `title` (one look everywhere, full screen included; `Tip.test.ts` checks).
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
```

In browser checks mute the videos and check a phone width (no horizontal page scroll).

## Read when needed

These are not loaded at the start of a session: read the one a task touches.

| For | Read |
|---|---|
| What is next, the weak spots, the owner's plans: start here when asked what to do | [docs/state.md](docs/state.md) |
| The review: running it, its questions, Match tab, stats rule, the match list, renames | [docs/review.md](docs/review.md) |
| Importing and running a match, a busy machine, checking the page on the short clips | [docs/running.md](docs/running.md) |
| The server, uploads, password, viewers' reports, crawlers, backups, films, voice | [docs/hosting.md](docs/hosting.md) |
| Pipeline changes and their numbers; ideas for the page | [docs/next_steps.md](docs/next_steps.md), [docs/plan.md](docs/plan.md) |
| Setup, recording, every command and option, the page's sections and stats, each pipeline step | [docs/setup.md](docs/setup.md), [docs/recording.md](docs/recording.md), [docs/processing.md](docs/processing.md), [docs/match-page.md](docs/match-page.md), [docs/pipeline.md](docs/pipeline.md) |
