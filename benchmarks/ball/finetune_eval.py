"""Detection scores of ball models on the fine-tuning set's stored frames, run as the pipeline does (stride 1, strongest blob).

    uv run python benchmarks/ball/finetune_eval.py MATCH [--weights PATH ...] [--thresholds 0.2 0.3 0.4]

`pretrained` is the shipped model. Raw per-frame picks (position in 4K pixels, peak) are cached beside the weights
(`picks_NAME_MATCH.npz`); the table is the scores at each threshold on the labels of `finetune_labels.py`.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import torch

from volleyball_stats import ball

OUT = Path("outputs/benchmarks/ball_finetune")
WEIGHTS = OUT / "weights"
TOL = 45.0
SCALE = 3840 / ball.WIDTH
SKIP, POS, NEG, UNSURE = 0, 1, 2, 3
KINDS = {"ball": POS, "clip_ball": POS, "clip_none": NEG, "offscreen": NEG, "unsure": UNSURE, "skip": SKIP}


class Unit:
    """One stored file: its frames (memory-mapped RGB uint8) and per-frame label arrays."""

    def __init__(self, folder: Path, name: str, rows: list[dict]):
        self.name, self.folder = name, folder
        self.first = int(np.load(folder / f"{name}.npz")["first"])
        n = len(np.load(folder / f"{name}.npy", mmap_mode="r"))
        self.kind = np.zeros(n, np.int8)
        self.xy = np.full((n, 2), np.nan)
        self.kindname = np.array(["skip"] * n, dtype="U10")
        self.also512 = np.zeros(n, bool)
        for r in rows:
            i = int(r["frame"]) - self.first
            if 0 <= i < n:
                self.kind[i], self.kindname[i], self.also512[i] = KINDS[r["kind"]], r["kind"], r["also512"] == "1"
                if r["x"]:
                    self.xy[i] = float(r["x"]), float(r["y"])

    def frames(self) -> np.ndarray:
        return np.load(self.folder / f"{self.name}.npy", mmap_mode="r")


def load_units(match: str) -> list[Unit]:
    """Every stored file of the match with its labels; frames off the pretrained model's path (offpath.csv) are skipped."""
    folder = OUT / match
    rows: dict[str, list[dict]] = {}
    with (folder / "labels.csv").open() as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["unit"], []).append(r)
    off = {}
    with (folder / "offpath.csv").open() as f:
        for r in csv.DictReader(f):
            off.setdefault(r["unit"], set()).add(int(r["frame"]))
    units = []
    for name in sorted(rows):
        if not (folder / f"{name}.npz").exists():
            continue
        u = Unit(folder, name, rows[name])
        for frame in off.get(name, ()):
            if 0 <= frame - u.first < len(u.kind):
                u.kind[frame - u.first] = SKIP
        units.append(u)
    return units


def load(weights: str | None, device: str):
    return ball.load_model(device, Path(weights)) if weights and weights != "pretrained" else ball.load_model(device)


@torch.no_grad()
def picks(model, frames: np.ndarray, device: str, batch: int = 16) -> np.ndarray:
    """Per frame (x, y, peak) of the strongest blob over its up to 3 windows (stride 1, as `ball.track_frames`), x and y in 4K pixels, NaN when none."""
    n = len(frames)
    mean, std = torch.tensor(ball.IMAGENET_MEAN, device=device).view(1, 3, 1, 1), torch.tensor(ball.IMAGENET_STD, device=device).view(1, 3, 1, 1)
    out = np.full((n, 3), np.nan)
    starts = list(range(max(n - 2, 0))) + [-1]
    for b in range(0, len(starts), batch):
        chunk, real = starts[b : b + batch], []
        idx = []
        for s in chunk:
            if s >= 0:
                idx.append([s, s + 1, s + 2]), real.append(3)
            else:
                idx.append([n - 2, n - 1, n - 1]), real.append(2)
        raw = torch.from_numpy(np.stack([frames[i] for i in idx])).to(device)
        x = ((raw.float() / 255.0).permute(0, 1, 4, 2, 3) - mean) / std
        maps = model(x.reshape(len(chunk), 9, ball.HEIGHT, ball.WIDTH))[0].sigmoid().cpu().numpy()
        for ids, r, three in zip(idx, real, maps):
            for k in range(r):
                blob = ball.best_blob(three[k])
                if blob and (np.isnan(out[ids[k], 2]) or blob[2] > out[ids[k], 2]):
                    out[ids[k]] = blob[0] * SCALE, blob[1] * SCALE, blob[2]
    return out


def run_model(name: str, weights: str | None, match: str, device: str, units: list[Unit] | None = None) -> dict[str, np.ndarray]:
    path = WEIGHTS / f"picks_{name}_{match}.npz"
    if path.exists():
        return dict(np.load(path))
    units, model = units or load_units(match), load(weights, device)
    found = {u.name: picks(model, u.frames(), device) for u in units}
    np.savez_compressed(path, **found)
    return found


def score(units: list[Unit], found: dict[str, np.ndarray], threshold: float) -> dict[str, float]:
    """Counts at one threshold over the units' labels (see the README of the task: recall within TOL, wrong place, dead time, jitter)."""
    c = dict(ball=0, hit=0, hit_both=0, n_both=0, hit_only=0, n_only=0, wrong=0, none_frames=0, none_det=0, clipball=0, clipball_agree=0, unsure=0, unsure_det=0, offscreen_det=0, offscreen=0)
    dist = []
    for u in units:
        p = found[u.name]
        has = ~np.isnan(p[:, 2]) & (p[:, 2] >= threshold)
        d = np.hypot(p[:, 0] - u.xy[:, 0], p[:, 1] - u.xy[:, 1])
        for kind in ("ball", "clip_ball", "clip_none", "unsure", "offscreen"):
            m = u.kindname == kind
            m &= u.kind != SKIP
            if kind == "ball":
                near = m & has & (d <= TOL)
                c["ball"] += m.sum()
                c["hit"] += near.sum()
                c["wrong"] += (m & has & (d > TOL)).sum()
                both, only = m & u.also512, m & ~u.also512
                c["n_both"] += both.sum()
                c["hit_both"] += (near & both).sum()
                c["n_only"] += only.sum()
                c["hit_only"] += (near & only).sum()
                dist += list(d[near])
            elif kind == "clip_none":
                c["none_frames"] += m.sum()
                c["none_det"] += (m & has).sum()
            elif kind == "clip_ball":
                c["clipball"] += m.sum()
                c["clipball_agree"] += (m & has & (d <= TOL)).sum()
            elif kind == "unsure":
                c["unsure"] += m.sum()
                c["unsure_det"] += (m & has & (d <= TOL)).sum()
            else:
                c["offscreen"] += m.sum()
                c["offscreen_det"] += (m & has).sum()
    tp = c["hit"]
    fp = c["wrong"] + c["none_det"] + c["offscreen_det"]
    fn = c["ball"] - tp
    f1 = 2 * tp / max(2 * tp + fp + fn, 1)
    return {
        "recall": tp / max(c["ball"], 1),
        "recall_both": c["hit_both"] / max(c["n_both"], 1),
        "recall_1024only": c["hit_only"] / max(c["n_only"], 1),
        "wrong": c["wrong"],
        "dead_time_det": c["none_det"],
        "dead_time_frames": c["none_frames"],
        "clip_ball_agree": c["clipball_agree"] / max(c["clipball"], 1),
        "unsure_rate": c["unsure_det"] / max(c["unsure"], 1),
        "offscreen_det": c["offscreen_det"],
        "jitter_median_px": float(np.median(dist)) if dist else float("nan"),
        "f1": f1,
        "wrong_plus_dead": c["wrong"] + c["none_det"],
    }


def table(units: list[Unit], models: dict[str, dict[str, np.ndarray]], thresholds: list[float]) -> None:
    keys = None
    for name, found in models.items():
        for t in thresholds:
            s = score(units, found, t)
            keys = keys or list(s)
            if name == next(iter(models)) and t == thresholds[0]:
                print("model threshold " + " ".join(f"{k:>16}" for k in keys))
            print(f"{name:10} {t:9.2f} " + " ".join(f"{s[k]:16.3f}" for k in keys))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match")
    parser.add_argument("--weights", nargs="*", default=[], help="NAME=PATH pairs")
    parser.add_argument("--thresholds", type=float, nargs="*", default=[0.2, 0.3, 0.4, 0.5])
    args = parser.parse_args()
    device = ball.default_device()
    units = load_units(args.match)
    models = {"pretrained": run_model("pretrained", None, args.match, device, units)}
    for pair in args.weights:
        name, path = pair.split("=")
        models[name] = run_model(name, path, args.match, device, units)
    table(units, models, args.thresholds)


if __name__ == "__main__":
    sys.exit(main())
