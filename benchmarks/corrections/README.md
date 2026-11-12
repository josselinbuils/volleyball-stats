# Corrections benchmark

Counts the corrections the owner makes in the review (touches to add or remove, types, players, winners) for the current code,
on the reviewed matches. The real folders in `outputs/matches/` are only read; everything is written to
`outputs/benchmarks/corrections/MATCH/` (gitignored, it holds names).

    uv run python benchmarks/corrections/bench.py freeze            # once: truth.json from review/data.js (checked rallies)
    uv run python benchmarks/corrections/bench.py run NAME          # copy + learn.rerun on the copy, no training (3 min per match)
    uv run python benchmarks/corrections/bench.py run NAME MATCH --ball PATH  # same, with the ball track PATH (a ball.csv) in the copy
    uv run python benchmarks/corrections/bench.py score NAME [--compare OTHER]
    uv run python benchmarks/corrections/bench.py score real        # the real folder, read-only
    uv run python benchmarks/corrections/breakdown.py NAME          # outputs/benchmarks/corrections/breakdown.md

`score` prints the five "checked" metrics of `learn.from_checked`, then the counts (add, remove, type, player, winner, total, per
rally, rallies at zero) and writes `corrections.json` and `summary.json` beside the run.

Differences from `learn.from_checked`: the truth is the frozen file, and a rally's pipeline winner comes from the window of
`rallies.csv` overlapping the truth rally the most (not the window with the exact same start): reviewed rallies the review split,
merged or moved still find their window. A rally with no window, or no winner on the page and not a redo, counts as a winner to fix.
Touches match as in `from_checked`: within `SAME_S`, in the rally's span with `LEAD_S` before it; a pipeline touch can serve two
truth touches, as there.

A run copies the match folder without what a rerun does not read (films, voice, backups, photos, site, crops, review but data.js)
and runs `learn.rerun` on it with the scratch parent as `--out`. The pipeline writes only inside that folder
(plus ffprobe's frame-times cache in the system temp folder). The copy sees no play model's weights (`playing.weights`): it keeps the
match folder's `play.npz` when it has one, and `benchmarks/rallies/play_run.py` puts a held-out one in.
