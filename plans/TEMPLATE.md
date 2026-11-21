# <Area> — improvements

One entry per finding, most valuable first. IDs are `<PREFIX>-NN`.

## <PREFIX>-01 Short title

- **Type**: bug | security | data-loss | performance | UX | accessibility | i18n | maintainability | tests | docs | cross-platform | feature
- **Impact**: high | medium | low — who is hit and how, in one sentence
- **Effort**: S (under an hour) | M (half a day) | L (days)
- **Confidence**: confirmed (ran or reproduced it) | read (traced in the code, callers included) | suspected (say what is left to check)
- **Where**: `path/file.py:123` (every place the change touches)
- **Problem**: what is wrong, with the evidence: a short code quote, a command and its output, or a number.
- **Plan**:
  1. Concrete step: file, function, what changes.
  2. The test to add or the benchmark to run (`benchmarks/<step>`), before and after.
- **Check**: the command or the manual steps proving it is fixed.
