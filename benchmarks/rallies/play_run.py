"""`benchmarks/corrections/bench.py run` with a held-out P(play) file put in the scratch copy first, so the rerun uses it.

    uv run python benchmarks/rallies/play_run.py RUN MATCH P_NPZ [--uses ends,starts,keep,alive]

Then score it as any run: `bench.py score RUN MATCH --compare players-near`, `breakdown.py RUN`.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "corrections"))
import bench  # noqa: E402

from volleyball_stats import learn, playing  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run")
    ap.add_argument("match")
    ap.add_argument("npz", type=Path)
    ap.add_argument("--uses", default=",".join(playing.USES))
    args = ap.parse_args()
    name = bench.matches(args.match)[0]
    z = dict(np.load(args.npz))
    rerun = learn.rerun

    def with_play(scratch, *rest):
        np.savez(scratch / playing.FILE, **z, uses=args.uses)
        return rerun(scratch, *rest)

    learn.rerun = with_play
    bench.run(name, args.run)


if __name__ == "__main__":
    main()
