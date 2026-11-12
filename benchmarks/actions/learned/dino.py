"""DINOv2-base (frozen) on frames of the clips, with a small head: 3 frames around the contact, or the 16 in a temporal head.

    uv run python benchmarks/actions/learned/dino.py TRAIN TEST
"""

import sys
import time

import numpy as np
import torch
import torch.nn as nn

from common import MATCHES, OUT, load
from heads import cross_predict

MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
THREE = [5, 7, 9]


@torch.no_grad()
def extract(match: str) -> np.ndarray:
    path = OUT / match / "dino.npy"
    if path.exists():
        return np.load(path)
    from transformers import AutoModel

    model = AutoModel.from_pretrained("facebook/dinov2-base").cuda().eval().half()
    clips = np.load(OUT / match / "clips.npy", mmap_mode="r")
    out = np.zeros((len(clips), 16, 1536), np.float16)
    t0 = time.time()
    for i in range(len(clips)):
        x = torch.from_numpy(np.ascontiguousarray(clips[i])).cuda().permute(0, 3, 1, 2).flip(1).float() / 255
        x = nn.functional.interpolate(x, size=(224, 224), mode="bilinear", antialias=True)
        h = model(pixel_values=((x - MEAN.cuda()) / STD.cuda()).half()).last_hidden_state
        out[i] = torch.cat([h[:, 0], h[:, 1:].mean(1)], 1).float().cpu().numpy()
    print(match, "features", f"{time.time() - t0:.0f}s", f"{(time.time() - t0) / len(clips) * 1000:.0f} ms a clip of 16 frames", flush=True)
    np.save(path, out)
    return out


class Mlp(nn.Module):
    def __init__(self, n: int, tab: int) -> None:
        super().__init__()
        self.n, self.f = n, tab
        self.net = nn.Sequential(nn.LayerNorm(n + tab), nn.Dropout(0.3), nn.Linear(n + tab, 256), nn.GELU(), nn.Dropout(0.3), nn.Linear(256, 10))

    def forward(self, x):
        return self.net(x)


class Temporal(nn.Module):
    def __init__(self, tab: int) -> None:
        super().__init__()
        self.tab = tab
        self.inp = nn.Sequential(nn.LayerNorm(1536), nn.Dropout(0.3), nn.Linear(1536, 128), nn.GELU())
        self.conv = nn.Sequential(nn.Conv1d(128, 128, 3, padding=1), nn.GELU(), nn.Conv1d(128, 128, 3, padding=1), nn.GELU())
        self.out = nn.Sequential(nn.Dropout(0.3), nn.Linear(256 + tab, 10))

    def forward(self, x):
        v = x[:, : 16 * 1536].view(len(x), 16, 1536)
        h = self.conv(self.inp(v).transpose(1, 2))
        return self.out(torch.cat([h.mean(2), h.amax(2), x[:, 16 * 1536 :]], 1))


def main() -> None:
    tr = load(next(m for m in MATCHES if m.startswith(sys.argv[1])))
    te = load(next(m for m in MATCHES if m.startswith(sys.argv[2])))
    ftr, fte = extract(tr["match"]), extract(te["match"])
    preds = OUT / "preds"
    preds.mkdir(exist_ok=True)
    for tab in (False, True):
        t_tr, t_te = (tr["tab"], te["tab"]) if tab else (np.zeros((len(tr["y"]), 0), np.float32),) * 2
        t_te = t_te if tab else np.zeros((len(te["y"]), 0), np.float32)
        x3_tr = np.concatenate([ftr[:, THREE].reshape(len(ftr), -1).astype(np.float32), t_tr], 1)
        x3_te = np.concatenate([fte[:, THREE].reshape(len(fte), -1).astype(np.float32), t_te], 1)
        r = cross_predict(lambda: Mlp(len(THREE) * 1536, t_tr.shape[1]), tr, te, x3_tr, x3_te)
        np.savez(preds / f"dino3{'+tab' if tab else ''}_{tr['match'][:10]}.npz", **r)
        x_tr = np.concatenate([ftr.reshape(len(ftr), -1).astype(np.float32), t_tr], 1)
        x_te = np.concatenate([fte.reshape(len(fte), -1).astype(np.float32), t_te], 1)
        r = cross_predict(lambda: Temporal(t_tr.shape[1]), tr, te, x_tr, x_te, epochs=40)
        np.savez(preds / f"dino16{'+tab' if tab else ''}_{tr['match'][:10]}.npz", **r)
        print("done tab" if tab else "done image", flush=True)


if __name__ == "__main__":
    main()
