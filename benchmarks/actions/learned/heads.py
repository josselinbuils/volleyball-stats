"""Small heads trained on cached features (frozen backbones, skeletons): out-of-fold scores on the training match, scores on the other."""

import zlib

import numpy as np
import torch
import torch.nn.functional as F

from common import LABELS


def folds(d: dict, k: int = 2) -> np.ndarray:
    """A fold of each contact, by rally."""
    return np.array([zlib.crc32(str(t["rally"]).encode()) % k for t in d["table"]])


def head_fit_predict(make, x_tr: np.ndarray, y_tr: np.ndarray, x_te: list[np.ndarray], epochs: int = 60, seeds: int = 3, lr: float = 2e-3, wd: float = 1e-2) -> list[np.ndarray]:
    """Trains `make()` (a torch module on float features) on the labelled rows, returns the class probabilities of each array of `x_te`, averaged over seeds."""
    xt, yt = torch.from_numpy(x_tr).float().cuda(), torch.from_numpy(y_tr).long().cuda()
    counts = np.bincount(y_tr, minlength=len(LABELS)) + 1
    weight = torch.tensor((counts.sum() / counts) ** 0.5, dtype=torch.float32).cuda()
    weight /= weight.mean()
    outs = [np.zeros((len(x), len(LABELS)), np.float32) for x in x_te]
    for seed in range(seeds):
        torch.manual_seed(seed)
        net = make().cuda()
        opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
        steps = epochs * ((len(xt) + 63) // 64)
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps)
        for _ in range(epochs):
            net.train()
            order = torch.randperm(len(xt)).cuda()
            for s in range(0, len(xt), 64):
                b = order[s : s + 64]
                loss = F.cross_entropy(net(xt[b]), yt[b], weight=weight, label_smoothing=0.1)
                opt.zero_grad()
                loss.backward()
                opt.step()
                sched.step()
        net.eval()
        with torch.no_grad():
            for o, x in zip(outs, x_te):
                o += net(torch.from_numpy(x).float().cuda()).softmax(1).cpu().numpy() / seeds
    return outs


def cross_predict(make, tr: dict, te: dict, x_tr: np.ndarray, x_te: np.ndarray, **kw) -> dict:
    """Out-of-fold scores on the training match (2 folds by rally) and the test match's from the model on all of it."""
    keep = np.flatnonzero(tr["y"] >= 0)
    fold = folds(tr)
    oof = np.zeros((len(tr["y"]), len(LABELS)), np.float32)
    for f in range(2):
        fit = keep[fold[keep] != f]
        hold = np.flatnonzero(fold == f)
        oof[hold] = head_fit_predict(make, x_tr[fit], tr["y"][fit], [x_tr[hold]], **kw)[0]
    test = head_fit_predict(make, x_tr[keep], tr["y"][keep], [x_te], **kw)[0]
    return {"oof": oof, "test": test}
