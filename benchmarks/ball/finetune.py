"""Fine-tune the ball tracker (the pretrained WASB HRNet, same input and size) on one reviewed match's labels.

    uv run python benchmarks/ball/finetune.py MATCH NAME [--passes 4] [--resume]

Samples are 3 consecutive stored frames; the loss is a CenterNet-style focal loss on the sigmoid heatmaps against a small
Gaussian at the labelled ball (positive frames), nothing but negatives (`clip_none`, `offscreen`), or negatives with an
ignored disc around the path (`unsure`); `skip` and off-path frames weigh nothing. 10% of the rallies and of the clips are
held out: the best checkpoint by their F1 goes to outputs/benchmarks/ball_finetune/weights/NAME.pth.tar, in the format
`ball.load_model` reads. The checkpoint `NAME_last.pt` resumes the run.
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import torch

from volleyball_stats import ball

sys.path.insert(0, str(Path(__file__).parent))
import finetune_eval as ev  # noqa: E402

SIGMA = 2.0
IGNORE_R = 8.0
BATCH = 16
LR = 1e-4
NEG_SHARE = 0.25
VAL_SHARE = 0.1
VAL_EVERY = 1000
VAL_THRESHOLDS = (0.2, 0.3, 0.4, 0.5)
MARGIN = 4


def windows(units: list[ev.Unit]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """(unit index, first frame index) of each window with a usable frame: those holding a positive, the others."""
    pos, rest = [], []
    for k, u in enumerate(units):
        usable = (u.kind != ev.SKIP) & ~(np.isnan(u.xy[:, 0]) & (u.kind != ev.NEG))
        for i in range(len(u.kind) - 2):
            if usable[i : i + 3].any():
                (pos if (u.kind[i : i + 3] == ev.POS).any() else rest).append((k, i))
    return pos, rest


class Windows(torch.utils.data.Dataset):
    def __init__(self, units: list[ev.Unit], items: list[tuple[int, int]]):
        self.units, self.items, self.mem = units, items, {}

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, n: int):
        k, i = self.items[n]
        u = self.units[k]
        if k not in self.mem:
            self.mem[k] = u.frames()
        frames = np.ascontiguousarray(self.mem[k][i : i + 3])
        kind = u.kind[i : i + 3].astype(np.int64)
        xy = (u.xy[i : i + 3] / ev.SCALE).astype(np.float32)
        bad = ~np.isfinite(xy[:, 0]) | (xy[:, 0] < 0) | (xy[:, 0] >= ball.WIDTH) | (xy[:, 1] < 0) | (xy[:, 1] >= ball.HEIGHT)
        kind[(kind == ev.POS) & bad] = ev.SKIP
        kind[(kind == ev.UNSURE) & ~np.isfinite(xy[:, 0])] = ev.NEG
        xy = np.nan_to_num(xy, nan=-100.0)
        return torch.from_numpy(frames), torch.from_numpy(kind), torch.from_numpy(xy)


def prepare(frames, kind, xy, device: str, train: bool):
    """Augment (flip, brightness, contrast), normalise, and build the targets and per-pixel weights."""
    x = frames.to(device).float() / 255.0
    x = x.permute(0, 1, 4, 2, 3)
    xy = xy.to(device).clone()
    n = len(x)
    if train:
        flip = torch.rand(n, device=device) < 0.5
        x = torch.where(flip.view(n, 1, 1, 1, 1), x.flip(-1), x)
        xy[..., 0] = torch.where(flip.view(n, 1), ball.WIDTH - 1 - xy[..., 0], xy[..., 0])
        contrast = 1 + (torch.rand(n, 1, 1, 1, 1, device=device) - 0.5) * 0.4
        bright = (torch.rand(n, 1, 1, 1, 1, device=device) - 0.5) * 0.2
        mid = x.mean(dim=(1, 2, 3, 4), keepdim=True)
        x = ((x - mid) * contrast + mid + bright).clamp(0, 1)
    mean = torch.tensor(ball.IMAGENET_MEAN, device=device).view(1, 1, 3, 1, 1)
    std = torch.tensor(ball.IMAGENET_STD, device=device).view(1, 1, 3, 1, 1)
    x = ((x - mean) / std).reshape(n, 9, ball.HEIGHT, ball.WIDTH)
    kind = kind.to(device)
    gx = torch.arange(ball.WIDTH, device=device).view(1, 1, 1, -1).float()
    gy = torch.arange(ball.HEIGHT, device=device).view(1, 1, -1, 1).float()
    dx, dy = gx - xy[..., 0].round().view(n, 3, 1, 1), gy - xy[..., 1].round().view(n, 3, 1, 1)
    gauss = torch.exp(-(dx**2 + dy**2) / (2 * SIGMA**2))
    pos = (kind == ev.POS).view(n, 3, 1, 1)
    target = torch.where(pos, gauss, torch.zeros_like(gauss))
    weight = (kind != ev.SKIP).view(n, 3, 1, 1).float().expand(-1, -1, ball.HEIGHT, ball.WIDTH).clone()
    unsure = (kind == ev.UNSURE).view(n, 3, 1, 1)
    near = ((gx - xy[..., 0].view(n, 3, 1, 1)) ** 2 + (gy - xy[..., 1].view(n, 3, 1, 1)) ** 2) <= IGNORE_R**2
    weight[unsure & near] = 0
    return x, target, weight, pos.sum().clamp(min=1)


def focal(logits, target, weight, count):
    """CenterNet's penalty-reduced focal loss: the peak pixel positive, the Gaussian around it softened."""
    p = logits.float().sigmoid().clamp(1e-4, 1 - 1e-4)
    peak = (target >= 0.999).float()
    pos = -((1 - p) ** 2) * torch.log(p) * peak
    neg = -((1 - target) ** 4) * p**2 * torch.log(1 - p) * (1 - peak)
    return ((pos + neg) * weight).sum() / count


def validate(model, units: list[ev.Unit], device: str) -> dict:
    model.eval()
    found = {u.name: ev.picks(model, u.frames(), device) for u in units}
    model.train()
    scores = {t: ev.score(units, found, t) for t in VAL_THRESHOLDS}
    best = max(VAL_THRESHOLDS, key=lambda t: scores[t]["f1"])
    return {"f1_at_0.2": float(scores[0.2]["f1"]), "best_f1": float(scores[best]["f1"]), "best_threshold": best, "recall_0.2": float(scores[0.2]["recall"]), "wrong_plus_dead_0.2": int(scores[0.2]["wrong_plus_dead"])}


def split(units: list[ev.Unit]) -> tuple[list[ev.Unit], list[ev.Unit]]:
    rng = np.random.default_rng(0)
    out = ([], [])
    for prefix in ("rally_", "clip_"):
        group = [u for u in units if u.name.startswith(prefix)]
        held = set(rng.choice(len(group), max(1, round(VAL_SHARE * len(group))), replace=False))
        for k, u in enumerate(group):
            out[k in held].append(u)
    return out


def save(path: Path, model, **extra) -> None:
    torch.save({"model_state_dict": model.state_dict(), **extra}, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match")
    parser.add_argument("name")
    parser.add_argument("--passes", type=float, default=4.0, help="Passes over the windows holding a positive")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    device = ball.default_device()
    train_units, val_units = split(ev.load_units(args.match))
    pos, rest = windows(train_units)
    rng = np.random.default_rng(1)
    per_pass = len(pos) + round(NEG_SHARE * len(pos))
    total = int(args.passes * per_pass / BATCH)
    print(f"train {len(train_units)} files ({len(pos)} windows with a positive, {len(rest)} others), val {len(val_units)} files; {total} steps", flush=True)

    model = ball.load_model(device).train()
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    step, best, history = 0, -1.0, []
    ev.WEIGHTS.mkdir(parents=True, exist_ok=True)
    last = ev.WEIGHTS / f"{args.name}_last.pt"
    if args.resume and last.exists():
        state = torch.load(last, map_location="cpu", weights_only=False)
        model.load_state_dict(state["model"])
        opt.load_state_dict(state["opt"])
        step, best, history = state["step"], state["best"], state["history"]
    if step == 0:
        history.append({"step": 0, **validate(model, val_units, device)})
        print(history[-1], flush=True)
    sched = lambda s: 0.5 * (1 + math.cos(math.pi * min(s, total) / total))  # noqa: E731

    def epoch_items() -> list[tuple[int, int]]:
        return [pos[j] for j in rng.permutation(len(pos))] + [rest[j] for j in rng.choice(len(rest), min(len(rest), round(NEG_SHARE * len(pos))), replace=False)]

    start = time.time()
    while step < total:
        items = epoch_items()
        rng.shuffle(items)
        skip = (step * BATCH) % max(len(items), 1) if args.resume else 0
        loader = torch.utils.data.DataLoader(Windows(train_units, items[skip:]), batch_size=BATCH, shuffle=False, num_workers=args.workers, drop_last=True, persistent_workers=False, prefetch_factor=4)
        for frames, kind, xy in loader:
            if step >= total:
                break
            for g in opt.param_groups:
                g["lr"] = LR * sched(step)
            x, target, weight, count = prepare(frames, kind, xy, device, True)
            with torch.autocast(device, torch.bfloat16):
                logits = model(x)[0]
            loss = focal(logits, target, weight, count)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            step += 1
            if step % 100 == 0:
                print(f"step {step}/{total} loss {loss.item():.4f} {(time.time() - start) / 60:.1f} min", flush=True)
            if step % VAL_EVERY == 0 or step == total:
                result = {"step": step, **validate(model, val_units, device)}
                history.append(result)
                print(result, flush=True)
                if result["best_f1"] > best:
                    best = result["best_f1"]
                    save(ev.WEIGHTS / f"{args.name}.pth.tar", model, **result)
                    print("saved best", flush=True)
                torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "step": step, "best": best, "history": history}, last)
        args.resume = False
    (ev.WEIGHTS / f"{args.name}_history.json").write_text(json.dumps(history, indent=1))
    print("done", (time.time() - start) / 60, "min", flush=True)


if __name__ == "__main__":
    sys.exit(main())
