"""Held-out scores of the candidates, both ways, and their fusions with the rules.

    uv run python benchmarks/actions/learned/evaluate.py CANDIDATE...

A candidate is the name of the files `preds/NAME_<train match>.npz` (`oof` on the training match, `test` on the other).
`NAME` alone is the model's own best touch class; `NAME>rules` keeps the rules' type unless the model's class is above a
confidence tuned on the training match's out-of-fold scores; `NAME+stack` is a head on [log scores, rules' type and features]
trained on those out-of-fold scores.
"""

import sys

import numpy as np

from common import LABELS, MATCHES, NONE, OUT, cells, load
from heads import head_fit_predict
import torch.nn as nn


def tune_overturn(d: dict, prob: np.ndarray) -> float:
    """The confidence from which the model's class replaces the rules', best on the labelled contacts of `d`."""
    touch = (d["y"] >= 0) & (d["y"] != NONE)
    top, pred = prob[:, :NONE].max(1), prob[:, :NONE].argmax(1)
    best, thr = -1, 1.01
    for t in np.arange(0.3, 1.01, 0.02):
        use = np.where(top > t, pred, d["rules"])
        right = (use[touch] == d["y"][touch]).sum()
        if right > best:
            best, thr = right, t
    return float(thr)


def tune_none(d: dict, prob: np.ndarray) -> float:
    """The probability of 'none' from which a contact is flagged false, best on `d` (false touches caught minus real ones lost)."""
    false, touch = d["y"] == NONE, (d["y"] >= 0) & (d["y"] != NONE)
    best, thr = 0, 1.01
    for t in np.arange(0.3, 1.0, 0.02):
        flagged = prob[:, NONE] > t
        gain = (flagged & false).sum() - (flagged & touch).sum()
        if gain > best:
            best, thr = gain, t
    return float(thr)


def stack(tr: dict, te: dict, oof: np.ndarray, test: np.ndarray) -> np.ndarray:
    x_tr = np.concatenate([np.log(oof + 1e-3), tr["tab"]], 1)
    x_te = np.concatenate([np.log(test + 1e-3), te["tab"]], 1)
    keep = np.flatnonzero(tr["y"] >= 0)
    n = x_tr.shape[1]
    make = lambda: nn.Sequential(nn.Dropout(0.1), nn.Linear(n, 64), nn.GELU(), nn.Dropout(0.2), nn.Linear(64, len(LABELS)))
    return head_fit_predict(make, x_tr[keep], tr["y"][keep], [x_te], epochs=80, seeds=5)[0]


def main() -> None:
    data = {m: load(m) for m in MATCHES}
    rows = []
    for name in sys.argv[1:]:
        for tr_name, te_name in (MATCHES, MATCHES[::-1]):
            tr, te = data[tr_name], data[te_name]
            z = np.load(OUT / "preds" / f"{name}_{tr_name[:10]}.npz")
            variants = {name: z["test"], f"{name}>rules": None, f"{name}+stack": stack(tr, te, z["oof"], z["test"])}
            thr = tune_overturn(tr, z["oof"])
            pred = np.where(z["test"][:, :NONE].max(1) > thr, z["test"][:, :NONE].argmax(1), te["rules"])
            onehot = np.zeros_like(z["test"])
            onehot[np.arange(len(pred)), pred] = 1
            onehot[:, NONE] = z["test"][:, NONE]
            variants[f"{name}>rules"] = onehot
            for v, prob in variants.items():
                nthr = tune_none(tr, z["oof"])
                touch = (te["y"] >= 0) & (te["y"] != NONE)
                p = prob[:, :NONE].argmax(1)
                right, rules = int((p[touch] == te["y"][touch]).sum()), int((te["rules"][touch] == te["y"][touch]).sum())
                flagged = z["test"][:, NONE] > nthr
                caught, lost = int((flagged & (te["y"] == NONE)).sum()), int((flagged & touch).sum())
                moved = "; ".join(f"{k} {n}" for k, n in list(cells(te, p).items())[:7])
                print(f"{te_name[:10]} <- {tr_name[:10]} | {v:22} right {right}/{int(touch.sum())} (rules {rules}, {right - rules:+d}) | none: caught {caught}/{int((te['y'] == NONE).sum())} lost {lost} (thr {nthr:.2f}) | {moved}")


if __name__ == "__main__":
    main()
