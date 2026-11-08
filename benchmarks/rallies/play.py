"""A play / no-play clip model (VideoMAE-base fine-tuned on a match's checked rallies), the experiment.

    uv run python benchmarks/rallies/play.py frames MATCH            # the video at 8 fps, 448x224, once (~15 min a match on the 5080)
    uv run python benchmarks/rallies/play.py train TRAIN_MATCH... --test MATCH --tag TAG [--wide]   # P(play) on MATCH every 0.25 s

A clip is 16 frames at 8 fps (2 s), labelled by its middle: play from a checked rally's serve to just after its last touch,
no play from a few seconds after it (`load`). Frames and models under outputs/benchmarks/bench/play/.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import torch

from volleyball_stats import actions, review

OUT = Path("outputs/benchmarks/bench/play")
FPS, T = 8, 16
# The whole width, the top 1920 of 2160 rows (the court and the air above it; the camera's foot of the floor cut).
WIDTH, HEIGHT, FULL_HEIGHT = 448, 224, 252
# Clips whose middle lies this close to a rally's boundary are left out of training: the label is unsure there.
EDGE_S = 0.25
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
BASE = "MCG-NJU/videomae-base-finetuned-kinetics"


def match_dir(name: str) -> Path:
    return Path("outputs/matches") / name


def frames(name: str) -> None:
    """Decode the match's video at FPS, scaled on the GPU, into a uint8 memmap (N, HEIGHT, WIDTH, 3)."""
    video = json.loads((match_dir(name) / "source.json").read_text())["video"]
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video], capture_output=True, text=True, check=True)
    total = int(float(probe.stdout) * FPS) + FPS
    out = OUT / name
    out.mkdir(parents=True, exist_ok=True)
    store = np.lib.format.open_memmap(out / "frames.npy", mode="w+", dtype=np.uint8, shape=(total, HEIGHT, WIDTH, 3))
    vf = f"fps={FPS},scale_cuda={WIDTH}:{FULL_HEIGHT},hwdownload,format=nv12,format=rgb24"
    cmd = ["ffmpeg", "-v", "error", "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", "-i", video, "-an", "-vf", vf, "-f", "rawvideo", "-"]
    size = FULL_HEIGHT * WIDTH * 3
    start, n = time.time(), 0
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as proc:
        while n < total and (buf := proc.stdout.read(size)) and len(buf) == size:
            store[n] = np.frombuffer(buf, np.uint8).reshape(FULL_HEIGHT, WIDTH, 3)[:HEIGHT]
            n += 1
            if n % (FPS * 600) == 0:
                print(f"{n / FPS / 60:.0f} min in {time.time() - start:.0f} s", flush=True)
    store.flush()
    (out / "frames.json").write_text(json.dumps({"count": n, "fps": FPS}))
    print(f"{n} frames, {time.time() - start:.0f} s")


def spans(name: str) -> list[tuple[float, float, float]]:
    """Each checked rally's serve (LEAD_S before its window), its last player touch and its window's end, in seconds: the
    review checks the touches, not the ends, which are mostly the pipeline's."""
    d = match_dir(name)
    page = review.page_data(d / "review")
    keys = set(review.checked(review.load_log(d / "identity_answers.json")))
    last: dict[int, float] = {}
    for c in page["contacts"]:
        if c["type"] not in ("floor", "net", "fault"):
            last[c["rally"]] = max(last.get(c["rally"], 0.0), c["t"])
    return sorted((r["start"] - actions.LEAD_S, last.get(k, r["start"]), r["end"]) for k, r in enumerate(page["rallies"]) if r["key"] in keys)


# Play runs to the last touch and PLAY_AFTER_S on (the ball's flight to the floor: 0.3-2.5 s on the labelled ends); no play
# starts DEAD_AFTER_S after it, or at the window's end when later; between them the label is unsure.
PLAY_AFTER_S, DEAD_AFTER_S = 0.5, 3.0


def load(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The frames, each clip start's label (1 play) and whether its label is sure."""
    count = json.loads((OUT / name / "frames.json").read_text())["count"]
    store = np.load(OUT / name / "frames.npy", mmap_mode="r")[:count]
    middle = (np.arange(count - T + 1) + T / 2) / FPS
    label, sure = np.zeros(len(middle), np.int64), np.ones(len(middle), bool)
    for serve, touch, end in spans(name):
        label[(middle >= serve) & (middle <= touch + PLAY_AFTER_S)] = 1
        sure &= (np.abs(middle - serve) > EDGE_S) & ~((middle > touch + PLAY_AFTER_S) & (middle < max(end, touch + DEAD_AFTER_S)))
    return store, label, sure


def batch(store: np.ndarray, starts, size: tuple[int, int], flip=None) -> torch.Tensor:
    """(B, T, 3, H, W) normalised, on the GPU."""
    x = torch.from_numpy(np.stack([store[s : s + T] for s in starts])).cuda()
    x = x.permute(0, 1, 4, 2, 3).float().div_(255)
    if flip is not None:
        x[flip] = x[flip].flip(-1)
    b = x.shape[0]
    x = x.reshape(b * T, 3, HEIGHT, WIDTH)
    if size != (HEIGHT, WIDTH):
        x = torch.nn.functional.interpolate(x, size=size, mode="bilinear", antialias=True, align_corners=False)
    x = (x - MEAN.cuda()) / STD.cuda()
    return x.reshape(b, T, 3, *size)


def model_for(size: tuple[int, int]):
    from transformers import VideoMAEForVideoClassification

    return VideoMAEForVideoClassification.from_pretrained(BASE, num_labels=2, ignore_mismatched_sizes=True, image_size=list(size)).cuda()


@torch.no_grad()
def probabilities(model, store: np.ndarray, size: tuple[int, int], stride: int = 2, bs: int = 32) -> tuple[np.ndarray, np.ndarray]:
    """Clip starts every `stride` frames and their P(play)."""
    model.eval()
    starts = np.arange(0, len(store) - T + 1, stride)
    out = []
    for i in range(0, len(starts), bs):
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits = model(pixel_values=batch(store, starts[i : i + bs], size)).logits
        out.append(logits.float().softmax(-1)[:, 1].cpu().numpy())
    model.train()
    return starts, np.concatenate(out)


def auc(p: np.ndarray, y: np.ndarray) -> float:
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))


def report(tag: str, p: np.ndarray, y: np.ndarray) -> dict:
    out = {"auc": round(auc(p, y), 4), "acc": round(float(((p > 0.5) == y).mean()), 4), "n": int(len(y)), "play": round(float(y.mean()), 3)}
    print(tag, out, flush=True)
    return out


def train(names: list[str], test: str, wide: bool, steps: int, bs: int, lr: float, tag: str) -> None:
    size = (HEIGHT, WIDTH) if wide else (224, 224)
    data = [load(n) for n in names]
    pools = [[(k, s) for k, (_, label, sure) in enumerate(data) for s in np.flatnonzero(sure & (label == c))] for c in (0, 1)]
    print("clips", [len(p) for p in pools], "size", size, flush=True)
    test_store, test_label, test_sure = load(test)
    model = model_for(size)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.05)
    warm = steps // 10
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda i: min(1, (i + 1) / warm) * 0.5 * (1 + np.cos(np.pi * min(1, i / steps))))
    rng = np.random.default_rng(0)
    out = OUT / "models" / tag
    out.mkdir(parents=True, exist_ok=True)
    log = []
    start = time.time()
    for step in range(1, steps + 1):
        # Half play, half no play.
        picks = [pools[c][rng.integers(len(pools[c]))] for c in rng.integers(0, 2, bs)]
        xs = torch.cat([batch(data[k][0], [s], size) for k, s in picks])
        flip = torch.from_numpy(rng.random(bs) < 0.5).cuda()
        xs[flip] = xs[flip].flip(-1)
        y = torch.tensor([data[k][1][s] for k, s in picks]).cuda()
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = torch.nn.functional.cross_entropy(model(pixel_values=xs).logits.float(), y, label_smoothing=0.1)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        sched.step()
        if step % 50 == 0:
            print(f"step {step} loss {loss.item():.3f} {time.time() - start:.0f} s", flush=True)
        if step % (steps // 4) == 0 or step == steps:
            starts, p = probabilities(model, test_store, size, stride=8)
            keep = test_sure[starts]
            log.append({"step": step, **report(f"test {test} step {step}", p[keep], test_label[starts][keep])})
    model.save_pretrained(out)
    starts, p = probabilities(model, test_store, size)
    np.savez(out / f"{test}.npz", starts=starts, p=p, fps=FPS, T=T)
    (out / "log.json").write_text(json.dumps({"train": names, "test": test, "size": size, "steps": steps, "bs": bs, "lr": lr, "log": log}, indent=1))
    report(f"final {test}", p[test_sure[starts]], test_label[starts][test_sure[starts]])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("frames").add_argument("match")
    t = sub.add_parser("train")
    t.add_argument("matches", nargs="+")
    t.add_argument("--test", required=True)
    t.add_argument("--wide", action="store_true")
    t.add_argument("--steps", type=int, default=2000)
    t.add_argument("--bs", type=int, default=8)
    t.add_argument("--lr", type=float, default=5e-5)
    t.add_argument("--tag", required=True)
    args = parser.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = True
    if args.cmd == "frames":
        frames(args.match)
    else:
        train(args.matches, args.test, args.wide, args.steps, args.bs, args.lr, args.tag)


if __name__ == "__main__":
    main()
