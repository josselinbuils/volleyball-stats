"""VideoMAE stacked on the rules, each reviewed match tested on a model trained on the others (leave one match out).

    ACT_DIR=act-20nov uv run python benchmarks/actions/learned/lomo.py [--epochs 4] [--only MATCH]
    ACT_DIR=act-20nov uv run python benchmarks/actions/learned/lomo.py --evaluate

Training: out-of-fold scores on each training match from a model trained on the other training matches, then the model on
all of them scored on the test match; `--evaluate` stacks a head on [log scores, the rules' type and features] (as
`evaluate.py`) and counts the test match's right types against the rules'. Writes preds/lomo_MATCH.npz under ACT_DIR.
"""

import argparse

import numpy as np
import torch

from common import LABELS, NONE, OUT, cells, load
from evaluate import stack, tune_overturn
from videomae import fit, predict

MATCHES = sorted(p.parent.name for p in OUT.glob("*/clips.done"))


class Joined:
    """Several matches' clips indexed as one array."""

    def __init__(self, sets: list[dict]) -> None:
        self.parts = [np.load(d["clips"], mmap_mode="r") for d in sets]
        self.start = np.cumsum([0] + [len(d["y"]) for d in sets])

    def __getitem__(self, i: int) -> np.ndarray:
        k = int(np.searchsorted(self.start, i, side="right") - 1)
        return self.parts[k][i - self.start[k]]


def join(sets: list[dict]) -> dict:
    return {"match": "+".join(d["match"][:10] for d in sets), "table": [t for d in sets for t in d["table"]], "y": np.concatenate([d["y"] for d in sets]),
            "rules": np.concatenate([d["rules"] for d in sets]), "tab": np.concatenate([d["tab"] for d in sets]), "clips": Joined(sets)}


def train(test: str, data: dict, epochs: int) -> None:
    others = [m for m in MATCHES if m != test]
    oof = []
    for m in others:
        inner = join([data[o] for o in others if o != m])
        net = fit(inner, np.flatnonzero(inner["y"] >= 0), False, epochs, 0)
        oof.append(predict(net, data[m], np.arange(len(data[m]["y"]))))
        del net
        torch.cuda.empty_cache()
        print(test[:10], "oof", m[:10], flush=True)
    full = join([data[o] for o in others])
    net = fit(full, np.flatnonzero(full["y"] >= 0), False, epochs, 9)
    scores = predict(net, data[test], np.arange(len(data[test]["y"])))
    (OUT / "preds").mkdir(exist_ok=True)
    np.savez(OUT / "preds" / f"lomo_{test[:10]}.npz", oof=np.concatenate(oof), test=scores)
    print(test[:10], "done", flush=True)


def evaluate(data: dict) -> None:
    total = [0, 0, 0]
    for test in MATCHES:
        path = OUT / "preds" / f"lomo_{test[:10]}.npz"
        if not path.exists():
            continue
        z = np.load(path)
        tr, te = join([data[o] for o in MATCHES if o != test]), data[test]
        touch = (te["y"] >= 0) & (te["y"] != NONE)
        rules = int((te["rules"][touch] == te["y"][touch]).sum())
        thr = tune_overturn(tr, z["oof"])
        over = np.where(z["test"][:, :NONE].max(1) > thr, z["test"][:, :NONE].argmax(1), te["rules"])
        stacked = stack(tr, te, z["oof"], z["test"])[:, :NONE].argmax(1)
        alone = z["test"][:, :NONE].argmax(1)
        line = [f"{test[:10]} touches {int(touch.sum())} rules {rules}"]
        for name, p in (("alone", alone), ("over the rules", over), ("stacked", stacked)):
            line.append(f"{name} {int((p[touch] == te['y'][touch]).sum()) - rules:+d}")
        print(" | ".join(line))
        print("   stacked moves:", "; ".join(f"{k} {n}" for k, n in list(cells(te, stacked).items())[:10]))
        total[0] += int((stacked[touch] == te["y"][touch]).sum()) - rules
        total[1] += int((over[touch] == te["y"][touch]).sum()) - rules
        total[2] += int(touch.sum())
    print(f"four: stacked {total[0]:+d}, over the rules {total[1]:+d}, of {total[2]} touches")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--only")
    p.add_argument("--evaluate", action="store_true")
    a = p.parse_args()
    data = {m: load(m) for m in MATCHES}
    print({m[:10]: (len(d["y"]), int((d["y"] >= 0).sum())) for m, d in data.items()}, LABELS, flush=True)
    if a.evaluate:
        evaluate(data)
        return
    for test in MATCHES:
        if (not a.only or test.startswith(a.only)) and not (OUT / "preds" / f"lomo_{test[:10]}.npz").exists():
            train(test, data, a.epochs)


if __name__ == "__main__":
    main()
