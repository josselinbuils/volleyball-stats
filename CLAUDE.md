# CLAUDE.md

Automatic per-player volleyball stats from one fixed sideline camera (see README.md): Python
pipeline in `src/volleyball_stats/`, match page in `web/` (React + shadcn/ui), one benchmark per
step in `benchmarks/`. The owner plays at ASPOM Bègles (adult leisure). Their camera: DJI Osmo
Action 3, 4K 50 fps; their processing PC: RTX 5080 under WSL2.

## Rules

- At a session's start, `git fetch`, then warn the owner if the branch is behind its remote.
- Speak English with the owner; the page and the review page open in French (fr first, then en, in
  `web/src/locales/`). UX first: understandable by anyone, never traded for performance.
- Interface text stays light (the owner's rule): the fewest words a viewer needs, judged on all they see together, without
  caveats about estimates or remarks on what the interface already shows. Write and shorten so by default, without asking.
- A change done, check that the names around it still fit what they name (titles, buttons, labels, docs, code), and
  propose a new name where one no longer does, e.g. a dialog grown past its title.
- Never publish, host or share anything without the owner. The hosted page has no password: it
  never carries real footage or player pictures (nor anything cut from them) without every
  player's consent; the names given in the review stay on it (the owner's choice). Footage may go
  online without that consent only behind a password, unreachable by direct link without it. Never
  republish the YouTube clips in `data/benchmarks/`.
- Commit with the personal identity (`Josselin BUILS <josselin.buils@gmail.com>`), never a work email.
- A fix or feature done: commit it, push it to `main` and restart the review without asking: `uv run stats stop` (it refuses while an apply runs: wait and retry), then start it again on what was open (`curl -s 127.0.0.1:8765/current` names the match, null for the list). A restart is `uv run stats server [MATCH]`, with `--with-window` when the running one has it (`ps -o args= -p "$(lsof -ti tcp:8765 -sTCP:LISTEN)"`: started by `stats`, it stops once its window closes): the page is already open. Only a first start opens it. Start it with the Bash tool's `run_in_background`, in any shell: `[ -n "$ZSH_VERSION" ] && setopt no_bg_nice; uv run stats server` (zsh lowers background jobs' priority, which the jobs it starts would inherit; it refuses to start so). Then check it runs at nice 0: `ps -o ni= -p "$(lsof -ti tcp:8765 -sTCP:LISTEN)"`.
- No new Python dependency without asking (no scipy: numpy and what is installed).
- The review server binds 127.0.0.1 only. `outputs/` (gitignored) holds names of real people
  (`player_names.json`, `roster.json`): never commit it.
- "Le coin du coach" advises the team: it never names a player for a fault or a weak number (the owner's rule), but in
  "Placement en défense", "Placement en réception" and "Le saut d'attaque" (the owner's call, for now).
- Benchmark-driven: change a step, run its benchmark, report the numbers before and after.
- A generic project (the owner's rule): it runs on as many operating systems as it can, at least Windows and macOS as today.
  Nothing relies on one of them: no feature, model or step for a single system or machine. A more optimised pipeline on
  some of them is fine.
- Every action is done in the app (the owner's rule): `uv run stats` (or `install.sh`, or its shortcut) is the
  only command a user types. A new step or command gets its place in the app, for anyone to use without computing knowledge.
- A review question about who touched the ball always offers every player of both teams: the
  touch's team is often wrong. The answer takes the picked player's team.

## Conventions

- Web commands need Node 22 (`.nvmrc`): `nvm use` first.
- Format web files with `npx prettier --single-quote --print-width 200` (no config file: the
  defaults restyle everything). Some files already differ; only format the ones you touch.
- Spacing in `web/`: the design system's values only, and coherent: mirror what the neighbouring elements use.
- Anything loaded after the page shows (a fetch, a server's answer, a lazy part) has a placeholder or a loader
  while it comes: never an empty space that fills in later.
- A button starting an async action is disabled with a loader inside while it runs (`Button`'s `busy`, `useRunning`),
  the buttons beside it that would start another disabled too.
- Tooltips in `web/`: `Tip` only, never a `title` (one look everywhere, full screen included; `Tip.test.ts` checks).
- The page's build is committed in `src/volleyball_stats/site/`: after any `web/` change run
  `npm run build` in `web/` and commit the build with it. It makes the page, `scene3d.js` (three.js)
  that the page loads only when the 3D view is shown, `review-app.js` (the review's screens) that it loads
  only in the review, and in `matches_site/` the list of the hosted matches (`matches.html`, `src/matches.tsx`) with
  `app.js`, the app's screens the review server's list loads (`src/appPanel.tsx`, never hosted).
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
| The app (one command, everything else in the browser), importing and running a match, a busy machine, checking the page on the short clips | [docs/running.md](docs/running.md) |
| The server, uploads, password, viewers' reports, crawlers, backups, two machines (sync), films, voice | [docs/hosting.md](docs/hosting.md) |
| Pipeline changes and their numbers; ideas for the page | [docs/next_steps.md](docs/next_steps.md), [docs/plan.md](docs/plan.md) |
| Setup, recording, every command and option, the page's sections and stats, each pipeline step | [docs/setup.md](docs/setup.md), [docs/recording.md](docs/recording.md), [docs/processing.md](docs/processing.md), [docs/match-page.md](docs/match-page.md), [docs/pipeline.md](docs/pipeline.md) |
