"""Training frames and teacher candidates for fine-tuning the ball tracker on the reviewed matches.

Per checked rally (2 s before its first touch to 1.5 s after its end) and per random 4 s clip of dead
time, the frames the tracker gets (decode.frames' 1280 px, resized as `ball.preprocess` does to
512x288, RGB uint8) go to `rally_KEY.npy` / `clip_FIRST.npy`, and the blobs of two teachers to the
`.npz` beside it: the pretrained model at 512x288 (teacher 0, as the pipeline runs it) and at 1024x576
(teacher 1, each frame seen by one window: stride 3), positions in 4K pixels. Resumable: finished files are skipped; the jobs run in a fixed random order, so any prefix is a fair sample.

    uv run python benchmarks/ball/finetune_data.py MATCH [--limit N]
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from volleyball_stats import ball, decode

OUT = Path("outputs/benchmarks/ball_finetune")
TRUTH = Path("outputs/benchmarks/corrections")
MATCHES = Path("outputs/matches")
BEFORE_S, AFTER_S, CLIP_S, CLIP_SHARE = 2.0, 1.5, 4.0, 0.15
MARGIN = 2
MERGE_PX = 20
KEEP = 3
BATCH = {0: 8, 1: 3}
KEEP_RALLIES = (0, 2)
EVERY = 5
NATIVE_W = 3840


def match_info(match: str) -> tuple[Path, dict]:
    source = json.loads((MATCHES / match / "source.json").read_text())
    return Path(source["video"]), json.loads((TRUTH / match / "truth.json").read_text())


def rally_spans(truth: dict) -> list[tuple[int, int, int]]:
    """(key, first frame, last frame) of each checked rally with its margins."""
    fps = truth["fps"]
    out = []
    for r in truth["rallies"]:
        first = min([t["frame"] for t in r["touches"]] + [r["start_frame"]])
        out.append((r["key"], max(0, first - round(BEFORE_S * fps)), r["end_frame"] + round(AFTER_S * fps)))
    return sorted(out, key=lambda s: s[1])


def chosen(spans: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Rallies spread over the whole match: those whose rank in time is 0 or 2 modulo 5 (about 40%)."""
    return [s for i, s in enumerate(spans) if i % EVERY in KEEP_RALLIES]


def clip_spans(match: str, truth: dict, spans: list[tuple[int, int, int]], total: int, seed: int = 0) -> list[tuple[int, int]]:
    """Random clips of dead time: clear of every pipeline rally and every checked span by 2 s."""
    fps = truth["fps"]
    busy = [(a - 2 * fps, b + 2 * fps) for _, a, b in spans]
    for line in (MATCHES / match / "rallies.csv").read_text().splitlines()[1:]:
        s, e = line.split(",")[:2]
        busy.append((int(s) - 2 * fps, int(e) + 2 * fps))
    length = round(CLIP_S * fps)
    want = round(CLIP_SHARE * sum(b - a for _, a, b in chosen(spans)) / length)
    rng, out = random.Random(seed), []
    lo, hi = min(a for _, a, _ in spans), max(b for _, _, b in spans)
    for _ in range(20000):
        if len(out) >= want:
            break
        a = rng.randrange(lo, min(hi, total) - length)
        if all(a + length < s or a > e for s, e in busy) and all(a + length < c or a > c + length for c, _ in out):
            out.append((a, a + length - 1))
    return sorted(out)


def blobs(maps: np.ndarray, scale: float) -> list[list[tuple[float, float, float]]]:
    """Per map, the blobs over FLOOR as (x, y, peak) in 4K pixels, strongest first."""
    found = []
    for hm in maps:
        mask = hm >= ball.FLOOR
        if not mask.any():
            found.append([])
            continue
        count, labels = cv2.connectedComponents(mask.astype(np.uint8))
        ys, xs = np.nonzero(mask)
        lab, w = labels[ys, xs], hm[ys, xs]
        total = np.bincount(lab, w, count)
        cx, cy = np.bincount(lab, xs * w, count) / np.maximum(total, 1e-9), np.bincount(lab, ys * w, count) / np.maximum(total, 1e-9)
        peak = np.zeros(count)
        np.maximum.at(peak, lab, w)
        found.append([(round(cx[i] * scale), round(cy[i] * scale), float(peak[i])) for i in np.argsort(-peak)[:-1][:KEEP] if i])
    return found


def merged(items: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    kept: list[tuple[float, float, float]] = []
    for b in sorted(items, key=lambda b: -b[2]):
        if all(abs(b[0] - k[0]) > MERGE_PX or abs(b[1] - k[1]) > MERGE_PX for k in kept):
            kept.append(b)
    return kept[:KEEP]


class Teacher:
    def __init__(self, model, device: str, size: tuple[int, int]):
        self.model, self.device, self.size = model, device, size
        if size[0] > ball.WIDTH:
            self.model = model.to(memory_format=torch.channels_last)
        self.scale = NATIVE_W / size[0]
        self.mean = torch.tensor(ball.IMAGENET_MEAN, device=device).view(1, 3, 1, 1)
        self.std = torch.tensor(ball.IMAGENET_STD, device=device).view(1, 3, 1, 1)
        self.found: dict[int, list] = {}

    @torch.no_grad()
    def run(self, windows: list[tuple[int, torch.Tensor]]) -> None:
        """windows: (first frame index, 9xHxW input)."""
        if not windows:
            return
        with torch.autocast(self.device, torch.float16, enabled=self.size[0] > ball.WIDTH):
            maps = self.model(torch.stack([w for _, w in windows]).to(self.device))[0].float().sigmoid().cpu().numpy()
        for (start, _), three in zip(windows, maps):
            for k, items in enumerate(blobs(three, self.scale)):
                self.found.setdefault(start + k, []).extend(items)


def process(video: Path, first: int, last: int, models: tuple, device: str, store: Path) -> None:
    """Decode frames first-MARGIN..last+MARGIN; store frames first..last and their candidates."""
    a, b = max(0, first - MARGIN), last + MARGIN
    t512, t1024 = Teacher(models[0], device, (512, 288)), Teacher(models[1], device, (1024, 576))
    count = last - first + 1
    frames = np.lib.format.open_memmap(store.with_suffix(".tmp.npy"), "w+", np.uint8, (count, ball.HEIGHT, ball.WIDTH, 3))
    p512, p1024, w512, w1024 = [], [], [], []
    seen = 0
    for i, frame in enumerate(decode.piped(video, *decode.scaled(*decode.size(video)), first=a, count=b - a + 1)):
        index = a + i
        if first <= index <= last:
            frames[index - first] = cv2.cvtColor(cv2.resize(frame, (ball.WIDTH, ball.HEIGHT)), cv2.COLOR_BGR2RGB)
        p512.append(torch.from_numpy(ball.preprocess(frame)))
        big = torch.from_numpy(cv2.cvtColor(cv2.resize(frame, (1024, 576), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)).to(device)
        p1024.append(((big.permute(2, 0, 1).float() / 255.0 - t1024.mean[0]) / t1024.std[0]).half())
        if len(p1024) == 3:
            w1024.append((index - 2, torch.cat(p1024)))
            p1024.clear()
            if len(w1024) == BATCH[1]:
                t1024.run(w1024)
                w1024.clear()
        seen += 1
        if len(p512) == 3:
            w512.append((index - 2, torch.cat(p512)))
            p512.pop(0)
            if len(w512) == BATCH[0]:
                t512.run(w512)
                w512.clear()
    t512.run(w512)
    t1024.run(w1024)
    frames.flush()
    del frames
    rows = []
    for teacher, t in ((0, t512), (1, t1024)):
        for index in range(first, last + 1):
            for rank, (x, y, peak) in enumerate(merged(t.found.get(index, []))):
                rows.append((index, teacher, rank, x, y, peak))
    rows = np.array(rows, dtype=np.float64).reshape(-1, 6)
    np.savez_compressed(store.with_suffix(".tmp.npz"), first=first, last=last, cand=rows)
    store.with_suffix(".tmp.npz").replace(store.with_suffix(".npz"))
    store.with_suffix(".tmp.npy").replace(store.with_suffix(".npy"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("match")
    parser.add_argument("--limit", type=int, help="Only the first N rallies and N clips (tests)")
    args = parser.parse_args()
    video, truth = match_info(args.match)
    device = ball.default_device()
    model, big_model = ball.load_model(device), ball.load_model(device)
    spans = rally_spans(truth)
    total = len(decode.timestamps(video))
    clips = clip_spans(args.match, truth, spans, total)
    jobs = [(f"rally_{k}", a, b) for k, a, b in chosen(spans)] + [(f"clip_{a}", a, b) for a, b in clips]
    (OUT / args.match).mkdir(parents=True, exist_ok=True)
    (OUT / args.match / "jobs.json").write_text(json.dumps(jobs))
    if args.limit:
        jobs = jobs[: args.limit] + [j for j in jobs if j[0].startswith("clip")][: args.limit]
    random.Random(1).shuffle(jobs)
    start = time.time()
    for n, (name, a, b) in enumerate(jobs):
        store = OUT / args.match / name
        if store.with_suffix(".npz").exists():
            continue
        t0 = time.time()
        process(video, a, min(b, total - 1 - MARGIN), (model, big_model), device, store)
        print(f"{n + 1}/{len(jobs)} {name} {b - a + 1} frames {(b - a + 1) / (time.time() - t0):.1f} fps, {time.time() - start:.0f} s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
