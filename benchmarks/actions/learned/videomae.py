"""VideoMAE-base (Kinetics) fine-tuned on the clips of one match, scored on the other's, with out-of-fold scores on the training match.

    uv run python benchmarks/actions/learned/videomae.py TRAIN TEST {video|fused} [--epochs 6] [--folds 2] [--no-final]

`fused` adds the rules' type and features to the pooled clip features before the head. Writes outputs/benchmarks/act/preds/.
"""

import argparse
import math
import time
import zlib

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from common import LABELS, MATCHES, OUT, load

CHECKPOINT = "MCG-NJU/videomae-base-finetuned-kinetics"
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 1, 3, 1, 1)


class Net(nn.Module):
    def __init__(self, tab: int, fused: bool) -> None:
        super().__init__()
        from transformers import VideoMAEModel

        self.body = VideoMAEModel.from_pretrained(CHECKPOINT)
        self.body.gradient_checkpointing_enable()
        self.norm = nn.LayerNorm(768)
        self.tab = nn.Sequential(nn.Linear(tab, 128), nn.GELU(), nn.Dropout(0.2)) if fused else None
        self.head = nn.Linear(768 + (128 if fused else 0), len(LABELS))
        self.drop = nn.Dropout(0.3)

    def forward(self, x: torch.Tensor, tab: torch.Tensor) -> torch.Tensor:
        h = self.norm(self.body(pixel_values=x).last_hidden_state.mean(1))
        if self.tab is not None:
            h = torch.cat([h, self.tab(tab)], 1)
        return self.head(self.drop(h))


def batch(clips: np.ndarray, idx: list[int], train: bool) -> torch.Tensor:
    x = torch.from_numpy(np.stack([clips[i] for i in idx])).cuda().permute(0, 1, 4, 2, 3).flip(2).float() / 255
    b, t, c, h, w = x.shape
    if train:
        out = []
        for k in range(b):
            s = int(h * np.random.uniform(0.75, 1.0))
            y0, x0 = np.random.randint(0, h - s + 1), np.random.randint(0, w - s + 1)
            v = x[k, :, :, y0 : y0 + s, x0 : x0 + s]
            if np.random.rand() < 0.5:
                v = v.flip(-1)
            v = v * np.random.uniform(0.8, 1.2) + np.random.uniform(-0.08, 0.08)
            out.append(F.interpolate(v, size=(224, 224), mode="bilinear", antialias=True, align_corners=False))
        x = torch.stack(out)
    else:
        x = F.interpolate(x.reshape(b * t, c, h, w), size=(224, 224), mode="bilinear", antialias=True, align_corners=False).reshape(b, t, c, 224, 224)
    return (x.clamp(0, 1) - MEAN.cuda()) / STD.cuda()


def fit(train: dict, idx: np.ndarray, fused: bool, epochs: int, seed: int) -> Net:
    torch.manual_seed(seed)
    np.random.seed(seed)
    net = Net(train["tab"].shape[1], fused).cuda()
    clips = np.load(train["clips"], mmap_mode="r")
    tab = torch.from_numpy(train["tab"]).cuda()
    y = torch.from_numpy(train["y"]).cuda()
    body = [p for n, p in net.named_parameters() if n.startswith("body")]
    rest = [p for n, p in net.named_parameters() if not n.startswith("body")]
    opt = torch.optim.AdamW([{"params": body, "lr": 4e-5}, {"params": rest, "lr": 1e-3}], weight_decay=0.05)
    micro, accumulate = 2, 4
    steps = epochs * math.ceil(len(idx) / (micro * accumulate))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, (s + 1) / 20) * 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps)))
    counts = np.bincount(train["y"][idx], minlength=len(LABELS)) + 1
    weight = torch.tensor((counts.sum() / counts) ** 0.5, dtype=torch.float32).cuda()
    weight /= weight.mean()
    net.train()
    t0 = time.time()
    for epoch in range(epochs):
        order = np.random.permutation(idx)
        total, n = 0.0, 0
        for s in range(0, len(order), micro):
            ids = sorted(order[s : s + micro])
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits = net(batch(clips, ids, True), tab[ids])
            loss = F.cross_entropy(logits.float(), y[ids], weight=weight, label_smoothing=0.1)
            (loss / accumulate).backward()
            total, n = total + loss.item(), n + 1
            if (s // micro + 1) % accumulate == 0 or s + micro >= len(order):
                nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                opt.step()
                opt.zero_grad()
                sched.step()
        print(f"epoch {epoch} loss {total / n:.3f} {time.time() - t0:.0f}s mem {torch.cuda.max_memory_allocated() / 2**30:.1f}G", flush=True)
    return net


@torch.no_grad()
def predict(net: Net, d: dict, idx: np.ndarray) -> np.ndarray:
    net.eval()
    clips = np.load(d["clips"], mmap_mode="r")
    tab = torch.from_numpy(d["tab"]).cuda()
    out = np.zeros((len(d["y"]), len(LABELS)), np.float32)
    for s in range(0, len(idx), 4):
        ids = list(idx[s : s + 4])
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits = net(batch(clips, ids, False), tab[ids]).float()
        out[ids] = logits.softmax(1).cpu().numpy()
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("train")
    p.add_argument("test")
    p.add_argument("mode", choices=["video", "fused"])
    p.add_argument("--epochs", type=int, default=6)
    p.add_argument("--folds", type=int, default=2)
    p.add_argument("--no-final", action="store_true")
    a = p.parse_args()
    tr = load(next(m for m in MATCHES if m.startswith(a.train)))
    te = load(next(m for m in MATCHES if m.startswith(a.test)))
    fused = a.mode == "fused"
    keep = np.flatnonzero(tr["y"] >= 0)
    rally = np.array([zlib.crc32(str(t["rally"]).encode()) % a.folds for t in tr["table"]])
    out = OUT / "preds"
    out.mkdir(exist_ok=True)
    oof = np.zeros((len(tr["y"]), len(LABELS)), np.float32)
    for f in range(a.folds if a.folds > 1 else 0):
        net = fit(tr, keep[rally[keep] != f], fused, a.epochs, f)
        oof += predict(net, tr, np.flatnonzero(rally == f))
        del net
        torch.cuda.empty_cache()
    test = np.zeros((len(te["y"]), len(LABELS)), np.float32)
    if not a.no_final:
        net = fit(tr, keep, fused, a.epochs, 9)
        t0 = time.time()
        test = predict(net, te, np.arange(len(te["y"])))
        print(f"predict {len(te['y'])} clips {time.time() - t0:.0f}s", flush=True)
        (OUT / "weights").mkdir(exist_ok=True)
        torch.save(net.state_dict(), OUT / "weights" / f"videomae-{a.mode}-{tr['match'][:10]}.pt")
    np.savez(out / f"videomae-{a.mode}_{tr['match'][:10]}.npz", oof=oof, test=test)


if __name__ == "__main__":
    main()
