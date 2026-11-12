"""Shared by the touch-type candidates: the cached sets, the rules' features and the scores."""

import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
# ACT_DIR: another folder for a set built on another reference run.
OUT = ROOT / "outputs/benchmarks" / os.environ.get("ACT_DIR", "act")
BASE = ROOT / "outputs/benchmarks/corrections"
MATCHES = ["2026-10-29-aspom-1-vs-aspom-2", "2026-11-02-avia-1-vs-aspom-2"]
LABELS = ["serve", "pass", "dig", "set", "attack", "block", "relance", "floor", "net", "none"]
NONE = LABELS.index("none")
TYPES = ["serve", "pass", "dig", "set", "attack", "block", "relance", "floor", "net"]
SIDE = {"left": 0, "right": 1}


def load(match: str) -> dict:
    """The match's contacts: labels y (-1 for a type outside LABELS), rules' type index, tabular features."""
    table = json.loads((OUT / match / "table.json").read_text())["contacts"]
    y = np.array([LABELS.index(t["label"]) if t["label"] in LABELS else -1 for t in table])
    rules = np.array([LABELS.index(t["rules"]) for t in table])
    return {"match": match, "table": table, "y": y, "rules": rules, "tab": tabular(table), "clips": OUT / match / "clips.npy"}


def onehot(names: list[str], vocab: list[str]) -> np.ndarray:
    out = np.zeros((len(names), len(vocab)), np.float32)
    for i, n in enumerate(names):
        if n in vocab:
            out[i, vocab.index(n)] = 1
    return out


def tabular(table: list[dict]) -> np.ndarray:
    """What the rules see and a clip does not: their type, contact order, timing, side, net distance, the ball's 3D height and speeds."""
    prevs = ["start"] + LABELS[:-1]
    nexts = ["end"] + LABELS[:-1]
    cols = [onehot([t["rules"] for t in table], LABELS[:-1]), onehot([t["prev_type"] for t in table], prevs), onehot([t["next_type"] for t in table], nexts)]
    num = []
    for t in table:
        p = t["place"]
        num.append([
            min(t["side_run"], 4) / 4, min(t["index"], 8) / 8, t["index"] == t["count"] - 1, min(t["prev_s"], 4) / 2 if t["prev_s"] >= 0 else -1,
            min(t["next_s"], 4) / 2 if t["next_s"] >= 0 else -1, t["prev_side"] == t["side"] if t["prev_s"] >= 0 else 0, t["next_side"] == t["side"] if t["next_s"] >= 0 else 0,
            SIDE[t["side"]], abs(t["court_x"]) / 9, t["court_y"] / 5, p is not None, (p[2] / 3 if p else 0), (t["rise"] / 8 if t["rise"] is not None else 0), t["rise"] is not None,
            (t["speed"] / 15 if t["speed"] is not None else 0), t["has_box"],
        ])
    return np.concatenate([*cols, np.array(num, np.float32)], 1).astype(np.float32)


def report(name: str, d: dict, prob: np.ndarray, none_thr: float | None = None) -> dict:
    """Right types over the contacts the truth has a touch for, against the rules', and the 'none' scores.
    The type is the best touch class; 'none' is judged apart (probability of none above 0.5, or `none_thr`)."""
    y, rules = d["y"], d["rules"]
    touch = (y >= 0) & (y != NONE)
    pred = prob[:, :NONE].argmax(1)
    right_rules, right = int((rules[touch] == y[touch]).sum()), int((pred[touch] == y[touch]).sum())
    thr = 0.5 if none_thr is None else none_thr
    flagged = prob[:, NONE] > thr
    false = y == NONE
    out = {"name": name, "match": d["match"][:10], "touches": int(touch.sum()), "rules_right": right_rules, "right": right,
           "none_caught": int((flagged & false).sum()), "none_total": int(false.sum()), "touch_lost": int((flagged & touch).sum())}
    return out


def cells(d: dict, pred: np.ndarray) -> dict[str, int]:
    """Confusion cells (truth -> predicted) that differ between the rules and `pred`, as net moves: right gained."""
    y, rules = d["y"], d["rules"]
    touch = (y >= 0) & (y != NONE)
    out: dict[str, int] = {}
    for a, b, t in zip(rules[touch], pred[touch], y[touch]):
        if a != b:
            if b == t:
                key = f"{LABELS[t]}: rules {LABELS[a]} -> fixed"
            elif a == t:
                key = f"{LABELS[t]}: broken to {LABELS[b]}"
            else:
                continue
            out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
