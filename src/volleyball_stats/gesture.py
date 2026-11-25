"""The touch's type from its gesture: VideoMAE-base fine-tuned on a clip around each contact (the credited player's box
and the ball), its scores read with the rules' type and what the rules see (order, timing, side, the ball's 3D flight) by
small heads, which give the type (`retype`). Measured in `benchmarks/actions/README.md` "A learned type from the gesture":
each match typed by a model trained on the other three, 18 to 33 more right types a match than the rules.

Without the weights the stage does not run and the types are the rules'. The weights sit beside the matches
(`outputs/learned/gesture/`, shared by the backup as the play model's) and are trained on the matches whose every rally is
checked (`gesture_training`). The clips are kept in `outputs/cache/gesture/` by contact and crop (4 to 6 GB a match, made
again when missing: safe to delete), so a run again only cuts those of the contacts it moved.
"""

import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from volleyball_stats import actions, decode, files, jobs, ranker

FILE = "gesture.json"
WEIGHTS = Path("learned") / "gesture"
MODEL, CONFIG = "model.safetensors", "config.json"
# Weights to use instead, for a benchmark's copy of a match: a folder, or one holding a folder by match name (the weights
# trained without it, `gesture_training --held`).
OVERRIDE = "GESTURE_WEIGHTS"
CACHE = Path("cache") / "gesture"
# Its base weights are CC BY-NC 4.0, as the play model's.
BASE = "MCG-NJU/videomae-base-finetuned-kinetics"
LABELS = ("serve", "pass", "dig", "set", "attack", "block", "relance", "floor", "net", "none")
NONE = LABELS.index("none")
# A clip: 16 frames every 3 from 21 before the contact, a square around the credited player and the ball at SIZE pixels,
# read by the model at INPUT.
OFFSETS = tuple(-21 + 3 * k for k in range(16))
SIZE, INPUT = 320, 224
# Heads averaged, each from its own seed (as measured).
HEADS = 5
SIDES = {"left": 0, "right": 1}
MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)


def weights(match: Path) -> Path:
    """The model's folder for the match folder `match`."""
    given = os.environ.get(OVERRIDE)
    if given:
        return Path(given) / match.name if (Path(given) / match.name / MODEL).exists() else Path(given)
    return files.root(match) / WEIGHTS


def stamp(folder: Path) -> int | None:
    """Which weights `folder` holds (their file's time, kept by the copies between machines), None without any."""
    path = folder / MODEL
    return int(path.stat().st_mtime) if path.exists() else None


def wanted(video: Path, match: Path) -> bool:
    """Whether the stage runs on `video`: the weights are here and it is the camera's footage they were trained on (as the
    learned order's, `ranker.MIN_HEIGHT`)."""
    return stamp(weights(match)) is not None and decode.size(video)[1] >= ranker.MIN_HEIGHT


def device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"


def boxes_near(rows: Sequence, frames: set[int]) -> dict[int, dict[int, tuple]]:
    """The players' boxes (by track) at `frames` and the frames either side, from players.csv's rows."""
    wanted_frames = {f + d for f in frames for d in (-1, 0, 1)}
    out: dict[int, dict[int, tuple]] = {}
    for r in rows:
        if r.frame in wanted_frames:
            out.setdefault(r.frame, {})[r.track] = r.box
    return out


def table(
    typed: Sequence[actions.Typed], touchers: Sequence[int | None], windows: Sequence[tuple[int, int]], fps: float, calibration, places: dict, boxes: dict, size: tuple[int, int]
) -> list[dict]:
    """Each contact with what the heads read beside the clip (its rules' type, its rally's other contacts, the ball's 3D
    place and flight to the next) and its crop: the credited track's box, else the nearest to the ball, with the ball."""
    lead = round(actions.LEAD_S * fps)
    rows = []
    for (frame, x, y, kind, side), track in zip(typed, touchers):
        rally = next((k for k, (start, end) in enumerate(windows) if start - lead <= frame <= end), None)
        rows.append({"frame": int(frame), "x": int(x), "y": int(y), "rules": kind, "side": side, "track": track, "rally": -1 - len(rows) if rally is None else rally})
    by_rally: dict[int, list[dict]] = {}
    for t in rows:
        by_rally.setdefault(t["rally"], []).append(t)
    for group in by_rally.values():
        group.sort(key=lambda t: t["frame"])
        for k, t in enumerate(group):
            prev, nxt = group[k - 1] if k else None, group[k + 1] if k + 1 < len(group) else None
            t["index"], t["count"] = k, len(group)
            t["prev_s"] = (t["frame"] - prev["frame"]) / fps if prev else -1.0
            t["next_s"] = (nxt["frame"] - t["frame"]) / fps if nxt else -1.0
            t["prev_type"], t["next_type"] = (prev["rules"] if prev else "start"), (nxt["rules"] if nxt else "end")
            t["prev_side"], t["next_side"] = (prev["side"] if prev else ""), (nxt["side"] if nxt else "")
            n = 0
            for u in reversed(group[: k + 1]):
                if u["side"] != t["side"]:
                    break
                n += u["rules"] not in ("floor", "block", "net")
            t["side_run"] = n
            cx, cy = calibration.to_court(np.array([[t["x"], t["y"]]], float))[0]
            t["court_x"], t["court_y"] = float(cx), float(cy)
            p, q = places.get(t["frame"]), places.get(nxt["frame"]) if nxt else None
            t["place"] = None if p is None else [float(v) for v in p]
            t["rise"] = t["speed"] = None
            if p is not None and q is not None and t["next_s"] > 0:
                s = t["next_s"]
                t["rise"] = float((q[2] - p[2] + 9.81 * s * s / 2) / s)
                t["speed"] = float(np.hypot(*(np.asarray(q[:2]) - np.asarray(p[:2]))) / s)
    width, height = size
    for t in rows:
        f = t["frame"]
        near = boxes.get(f) or boxes.get(f - 1) or boxes.get(f + 1) or {}
        box = near.get(t["track"]) if t["track"] is not None else None
        if box is None and near:
            box = min(near.values(), key=lambda b: np.hypot((b[0] + b[2]) / 2 - t["x"], (b[1] + b[3]) / 2 - t["y"]))
        t["has_box"] = box is not None
        x1, y1, x2, y2 = box if box is not None else (t["x"] - 150, t["y"] - 300, t["x"] + 150, t["y"] + 300)
        x1, y1, x2, y2 = min(x1, t["x"]), min(y1, t["y"]), max(x2, t["x"]), max(y2, t["y"])
        side = int(min(1000, max(360, 1.3 * max(x2 - x1, y2 - y1))))
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        t["crop"] = [int(min(max(cx - side / 2, 0), width - side)), int(min(max(cy - side / 2, 0), height - side)), side]
    return rows


def onehot(names: list[str], vocab: Sequence[str]) -> np.ndarray:
    out = np.zeros((len(names), len(vocab)), np.float32)
    for i, n in enumerate(names):
        if n in vocab:
            out[i, list(vocab).index(n)] = 1
    return out


def tabular(rows: list[dict]) -> np.ndarray:
    """What the heads read beside the clip's scores, a row a contact (`table`)."""
    types = LABELS[:NONE]
    cols = [onehot([t["rules"] for t in rows], types), onehot([t["prev_type"] for t in rows], ("start", *types)), onehot([t["next_type"] for t in rows], ("end", *types))]
    num = []
    for t in rows:
        p = t["place"]
        num.append([
            min(t["side_run"], 4) / 4, min(t["index"], 8) / 8, t["index"] == t["count"] - 1, min(t["prev_s"], 4) / 2 if t["prev_s"] >= 0 else -1,
            min(t["next_s"], 4) / 2 if t["next_s"] >= 0 else -1, t["prev_side"] == t["side"] if t["prev_s"] >= 0 else 0, t["next_side"] == t["side"] if t["next_s"] >= 0 else 0,
            SIDES.get(t["side"], 0), abs(t["court_x"]) / 9, t["court_y"] / 5, p is not None, (p[2] / 3 if p else 0), (t["rise"] / 8 if t["rise"] is not None else 0), t["rise"] is not None,
            (t["speed"] / 15 if t["speed"] is not None else 0), t["has_box"],
        ])  # fmt: skip
    return np.concatenate([*cols, np.array(num, np.float32).reshape(len(rows), 16)], 1).astype(np.float32)


TAB = 3 * NONE + 2 + 16


def key(t: dict) -> str:
    return "{}:{}:{}:{}".format(t["frame"], *t["crop"])


def clips(video: Path, rows: list[dict], folder: Path, share: jobs.Share = jobs.quiet) -> tuple[np.ndarray, list[int]]:
    """The clips kept in `folder` (a memmap, a clip a row: 16 frames of SIZE x SIZE, BGR) and each contact's row in it, the
    missing ones cut from `video` first (the share of their frames read told to `share`). Kept while the video is the
    same; a clip written in full before the index names it."""
    import cv2

    index, data = folder / "index.json", folder / "clips.u8"
    made = {"size": video.stat().st_size, "time": int(video.stat().st_mtime)}
    known = files.read_json(index, {})
    if {k: known.get(k) for k in made} != made:
        known = {**made, "keys": {}}
    keys: dict[str, int] = known["keys"]
    shape, nbytes = (len(OFFSETS), SIZE, SIZE, 3), len(OFFSETS) * SIZE * SIZE * 3
    missing = {key(t): t for t in rows if key(t) not in keys}
    if missing:
        folder.mkdir(parents=True, exist_ok=True)
        need: dict[int, list[tuple[str, int]]] = {}
        for k, t in missing.items():
            for slot, offset in enumerate(OFFSETS):
                need.setdefault(max(t["frame"] + offset, 0), []).append((k, slot))
        left = {k: len(OFFSETS) for k in missing}
        open_clips: dict[str, np.ndarray] = {}
        seen = jobs.every(len(need), share)
        with open(data, "r+b" if data.exists() else "wb") as f:
            f.truncate(len(keys) * nbytes)
            f.seek(len(keys) * nbytes)

            def write(k: str) -> None:
                f.write(open_clips.pop(k, np.zeros(shape, np.uint8)).tobytes())
                keys[k] = len(keys)

            for n, (frame, image) in enumerate(decode.frames_apart(video, need)):
                for k, slot in need[frame]:
                    x0, y0, s = missing[k]["crop"]
                    clip = open_clips.setdefault(k, np.zeros(shape, np.uint8))
                    clip[slot] = cv2.resize(image[y0 : y0 + s, x0 : x0 + s], (SIZE, SIZE), interpolation=cv2.INTER_AREA)
                    left[k] -= 1
                    if not left[k]:
                        write(k)
                seen(n)
            # Past the video's end: the frames there are black, as in the clips measured.
            for k in [k for k in missing if k not in keys]:
                write(k)
        files.write_text(index, json.dumps({**made, "keys": keys}))
        share(1.0)
    store = np.memmap(data, np.uint8, "r", shape=(len(keys), *shape)) if keys else np.zeros((0, *shape), np.uint8)
    return store, [keys[key(t)] for t in rows]


def network(tab: int = TAB, config: Path | None = None):
    """The model: VideoMAE's pooled features to the types (`LABELS`), and the heads reading its log scores with `tab`
    columns of `tabular`. From the base weights to train, else from `config` to load trained weights into."""
    import torch
    import torch.nn as nn
    from transformers import VideoMAEConfig, VideoMAEModel

    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.body = VideoMAEModel(VideoMAEConfig.from_json_file(str(config))) if config else VideoMAEModel.from_pretrained(BASE)
            self.norm = nn.LayerNorm(self.body.config.hidden_size)
            self.head = nn.Linear(self.body.config.hidden_size, len(LABELS))
            self.drop = nn.Dropout(0.3)
            self.heads = nn.ModuleList(head(len(LABELS) + tab) for _ in range(HEADS))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.head(self.drop(self.norm(self.body(pixel_values=x).last_hidden_state.mean(1))))

    return Net()


def head(width: int):
    import torch.nn as nn

    return nn.Sequential(nn.Dropout(0.1), nn.Linear(width, 64), nn.GELU(), nn.Dropout(0.2), nn.Linear(64, len(LABELS)))


def pixels(store: np.ndarray, rows: Sequence[int], on: str, train: bool = False):
    """The model's input for the clips at `rows`: RGB, cut at random and flipped half the time when `train`, at INPUT."""
    import torch
    import torch.nn.functional as F

    # Resized on an NVIDIA card as measured, on the processor elsewhere (antialias everywhere).
    work = on if on == "cuda" else "cpu"
    x = torch.from_numpy(np.stack([store[i] for i in rows])).to(work).permute(0, 1, 4, 2, 3).flip(2).float() / 255
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
            out.append(F.interpolate(v, size=(INPUT, INPUT), mode="bilinear", antialias=True, align_corners=False))
        x = torch.stack(out)
    else:
        x = F.interpolate(x.reshape(b * t, c, h, w), size=(INPUT, INPUT), mode="bilinear", antialias=True, align_corners=False).reshape(b, t, c, INPUT, INPUT)
    mean, std = torch.tensor(MEAN, device=work).view(1, 1, 3, 1, 1), torch.tensor(STD, device=work).view(1, 1, 3, 1, 1)
    return ((x.clamp(0, 1) - mean) / std).to(on)


def scores(net, store: np.ndarray, rows: Sequence[int], on: str, share: jobs.Share = jobs.quiet, batch: int = 4) -> np.ndarray:
    """The model's class probabilities for the clips at `rows`, the share done told to `share`."""
    import torch

    net.eval()
    out = np.zeros((len(rows), len(LABELS)), np.float32)
    seen = jobs.every(len(rows), share)
    with torch.no_grad():
        for s in range(0, len(rows), batch):
            with torch.autocast(on, dtype=torch.bfloat16, enabled=on == "cuda"):
                logits = net(pixels(store, rows[s : s + batch], on)).float()
            out[s : s + batch] = logits.softmax(1).cpu().numpy()
            seen(min(s + batch, len(rows)) - 1)
    return out


def head_input(p: np.ndarray, tab: np.ndarray) -> np.ndarray:
    return np.concatenate([np.log(p + 1e-3), tab], 1).astype(np.float32)


def stacked(heads: Sequence, p: np.ndarray, tab: np.ndarray, on: str) -> np.ndarray:
    """The heads' class probabilities, averaged, from the model's `p` and the contacts' `tab`."""
    import torch

    x = torch.from_numpy(head_input(p, tab)).to(on)
    out = np.zeros((len(p), len(LABELS)), np.float32)
    with torch.no_grad():
        for h in heads:
            h.eval()
            out += h(x).softmax(1).cpu().numpy() / len(heads)
    return out


def load(folder: Path, on: str):
    from safetensors.torch import load_file

    net = network(config=folder / CONFIG)
    net.load_state_dict(load_file(str(folder / MODEL)))
    return net.to(on).eval()


def typed_by(probabilities: np.ndarray, rules: Sequence[str]) -> list[str]:
    """Each contact's type: the heads' best touch class ("none" left out), the rules' for a type they do not give."""
    return [LABELS[int(p[:NONE].argmax())] if kind in LABELS[:NONE] else kind for p, kind in zip(probabilities, rules)]


def retype(
    video: Path, match: Path, typed: list[actions.Typed], touchers: Sequence[int | None], windows: Sequence[tuple[int, int]], rows: Sequence, calibration, places: dict, fps: float,
    share: jobs.Share = jobs.quiet, told: Callable[[str], None] = print,
) -> list[actions.Typed]:
    """`typed` with each contact's type from its gesture (`typed_by`), the contacts as the heads saw them written to the
    match's FILE (the rules' type in `rules`, for the training)."""
    folder = weights(match)
    on = device()
    found = table(typed, touchers, windows, fps, calibration, places, boxes_near(rows, {t[0] for t in typed}), decode.size(video))
    part = jobs.parts(share, {"clips": 8, "model": 1})
    store, at = clips(video, found, files.root(match) / CACHE / match.name, part("clips"))
    net = load(folder, on)
    kinds = typed_by(stacked(net.heads, scores(net, store, at, on, part("model")), tabular(found), on), [t["rules"] for t in found])
    for t, kind in zip(found, kinds):
        t["type"] = kind
    told(f"gesture: {sum(t['type'] != t['rules'] for t in found)} of {len(found)} types changed")
    files.write_text(match / FILE, json.dumps({"weights": stamp(folder), "contacts": found}))
    return [(*t[:3], kind, t[4]) for t, kind in zip(typed, kinds)]
