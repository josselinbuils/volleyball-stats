"""The toucher's keypoints over the clip and the ball's path relative to them, in a small temporal network.

    uv run python benchmarks/actions/learned/skel.py TRAIN TEST
"""

import csv
import os
import sys

import numpy as np
import torch
import torch.nn as nn

from common import BASE, MATCHES, OUT, load
from heads import cross_predict


def ball_path(d: dict) -> np.ndarray:
    """The ball in the crop's units (x, y, seen) at each of the clip's 16 frames."""
    run = BASE / d["match"] / "runs" / os.environ.get("ACT_RUN", "players-near") / d["match"]
    with open(run / "ball.csv") as f:
        ball = {int(r["frame"]): (float(r["x"]), float(r["y"])) for r in csv.DictReader(f) if r["visible"] == "1"}
    offsets = np.array(OFFSETS(d))
    out = np.zeros((len(d["table"]), 16, 3), np.float32)
    for i, t in enumerate(d["table"]):
        x0, y0, s = t["crop"]
        for k, o in enumerate(offsets):
            p = ball.get(t["frame"] + int(o))
            if p is not None:
                out[i, k] = [(p[0] - x0) / s, (p[1] - y0) / s, 1]
    return out


def OFFSETS(d):
    return [-21 + 3 * k for k in range(16)]


def features(d: dict) -> np.ndarray:
    z = np.load(OUT / d["match"] / "pose.npz")
    keys, boxes = z["keys"], z["boxes"]
    ball = ball_path(d)
    n = len(keys)
    centre = boxes[:, 7]
    h = np.maximum(centre[:, 3] - centre[:, 1], 0.05)
    c = np.stack([(centre[:, 0] + centre[:, 2]) / 2, (centre[:, 1] + centre[:, 3]) / 2], 1)
    seen = boxes.any(2)
    # Where a frame has no person, the nearest frame's keypoints stand in.
    for i in range(n):
        for k in range(16):
            if not seen[i, k] and seen[i].any():
                j = np.flatnonzero(seen[i])[np.abs(np.flatnonzero(seen[i]) - k).argmin()]
                keys[i, k], boxes[i, k] = keys[i, j], boxes[i, j]
    xy = (keys[..., :2] - c[:, None, None, :]) / h[:, None, None, None]
    conf = keys[..., 2:]
    box_c = np.stack([(boxes[..., 0] + boxes[..., 2]) / 2, (boxes[..., 1] + boxes[..., 3]) / 2], -1)
    move = (box_c - c[:, None, :]) / h[:, None, None]
    size = ((boxes[..., 3] - boxes[..., 1]) / h[:, None])[..., None]
    rel = (ball[..., :2] - c[:, None, :]) / h[:, None, None] * ball[..., 2:]
    vel = np.zeros_like(rel)
    vel[:, 1:] = (rel[:, 1:] - rel[:, :-1]) * (ball[:, 1:, 2:] * ball[:, :-1, 2:])
    vk = np.zeros_like(xy)
    vk[:, 1:] = xy[:, 1:] - xy[:, :-1]
    x = np.concatenate([xy.reshape(n, 16, -1), conf.reshape(n, 16, -1), vk.reshape(n, 16, -1) * 3, move, size, rel, vel, ball[..., 2:], seen[..., None].astype(np.float32)], 2)
    return np.clip(np.nan_to_num(x), -6, 6).astype(np.float32)


class Net(nn.Module):
    def __init__(self, channels: int, tab: int) -> None:
        super().__init__()
        self.c = channels
        self.conv = nn.Sequential(nn.Conv1d(channels, 96, 3, padding=1), nn.BatchNorm1d(96), nn.GELU(), nn.Dropout(0.2), nn.Conv1d(96, 96, 3, padding=1), nn.BatchNorm1d(96), nn.GELU(),
                                  nn.Conv1d(96, 96, 3, padding=1), nn.GELU())
        self.out = nn.Sequential(nn.Dropout(0.3), nn.Linear(192 + tab, 10))

    def forward(self, x):
        h = self.conv(x[:, : 16 * self.c].view(len(x), 16, self.c).transpose(1, 2))
        return self.out(torch.cat([h.mean(2), h.amax(2), x[:, 16 * self.c :]], 1))


def main() -> None:
    tr = load(next(m for m in MATCHES if m.startswith(sys.argv[1])))
    te = load(next(m for m in MATCHES if m.startswith(sys.argv[2])))
    ftr, fte = features(tr), features(te)
    c = ftr.shape[2]
    for tab in (False, True):
        t_tr = tr["tab"] if tab else np.zeros((len(tr["y"]), 0), np.float32)
        t_te = te["tab"] if tab else np.zeros((len(te["y"]), 0), np.float32)
        x_tr = np.concatenate([ftr.reshape(len(ftr), -1), t_tr], 1)
        x_te = np.concatenate([fte.reshape(len(fte), -1), t_te], 1)
        r = cross_predict(lambda: Net(c, t_tr.shape[1]), tr, te, x_tr, x_te, epochs=80, seeds=5)
        np.savez(OUT / "preds" / f"skel{'+tab' if tab else ''}_{tr['match'][:10]}.npz", **r)
        print("done", "tab" if tab else "skeleton only", flush=True)


if __name__ == "__main__":
    main()
