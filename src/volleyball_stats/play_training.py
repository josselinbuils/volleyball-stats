"""The play / no-play model (`playing`) trained on the matches reviewed here: VideoMAE-base fine-tuned on clips labelled by
their checked rallies, written beside the matches (`outputs/learned/play/`) where the backup shares it with the other machines.

    uv run python -m volleyball_stats.play_training outputs/matches/MATCH [--steps 2000] [--force]

"Apprendre de mes réponses" runs it on a match whose every rally is checked (`learn.train_play`), when the checked rallies
of such matches changed since the last training (`due`). It runs on any machine: fast on an NVIDIA card (half an hour),
hours on a Mac or a processor alone. Each match's frames at the model's size are kept in `outputs/cache/play/` (10 GB a
match, made again when missing: safe to delete).
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import time
from pathlib import Path

import numpy as np

from volleyball_stats import actions, files, playing, review

# Its weights are CC BY-NC 4.0.
BASE = "MCG-NJU/videomae-base-finetuned-kinetics"
TRAINED = "trained.json"
CACHE = Path("cache") / "play"
ROOT = Path(__file__).resolve().parents[2]
# 2000 steps of 8 clips, half of them play: the recipe measured on two matches (`benchmarks/rallies/README.md`).
STEPS, BATCH, LR = 2000, 8, 5e-5
# Clips at a time off an NVIDIA card, their gradients added up to BATCH: the memory of a Mac.
SMALL_BATCH = 2
# Play runs from a checked rally's serve to PLAY_AFTER_S after its last player touch (the ball's flight to the floor);
# no play starts DEAD_AFTER_S after it, or at the window's end when later; between them, and EDGE_S around a serve, a
# clip is left out: its label is unsure.
PLAY_AFTER_S, DEAD_AFTER_S, EDGE_S = 0.5, 3.0, 0.25

Span = tuple[float, float, float]


def spans(match: Path) -> list[Span] | None:
    """Each rally's serve (LEAD_S before its window), last player touch and window's end in seconds, from the review's
    page; None unless every rally is checked: an unchecked one would teach play as no play."""
    page, log = review.page_data(match / "review"), review.load_log(match / "identity_answers.json") if (match / "identity_answers.json").exists() else []
    if not review.reviewed(page, log):
        return None
    last: dict[int, float] = {}
    for c in page["contacts"]:
        if c["type"] not in ("floor", "net", "fault"):
            last[c["rally"]] = max(last.get(c["rally"], 0.0), c["t"])
    return sorted((r["start"] - actions.LEAD_S, last.get(k, r["start"]), r["end"]) for k, r in enumerate(page["rallies"]))


def labels(found: list[Span], count: int) -> tuple[np.ndarray, np.ndarray]:
    """Each clip start's label (1 play) among `count` frames, and whether it is sure."""
    middle = (np.arange(max(count - playing.T + 1, 0)) + playing.T / 2) / playing.FPS
    label, sure = np.zeros(len(middle), np.int64), np.ones(len(middle), bool)
    for serve, touch, end in found:
        label[(middle >= serve) & (middle <= touch + PLAY_AFTER_S)] = 1
        sure &= (np.abs(middle - serve) > EDGE_S) & ~((middle > touch + PLAY_AFTER_S) & (middle < max(end, touch + DEAD_AFTER_S)))
    return label, sure


def sources(match: Path) -> list[tuple[Path, Path]]:
    """The matches beside `match` (it too) the model can learn from on this machine, each with its video: every rally
    checked, the review's page and the video here."""
    found = []
    for source in sorted(match.parent.glob(f"*/{files.SOURCE}")):
        video = ROOT / json.loads(source.read_text())["video"]
        if video.exists() and spans(source.parent) is not None:
            found.append((source.parent, video))
    return found


def signature(found: list[tuple[Path, Path]]) -> dict[str, str]:
    """What each match teaches, by name: any change to its checked rallies moves it."""
    return {m.name: hashlib.sha256(json.dumps(spans(m)).encode()).hexdigest()[:16] for m, _ in found}


def trained(folder: Path) -> dict:
    """What the weights of `folder` were trained on (TRAINED), empty without weights."""
    path = folder / TRAINED
    return json.loads(path.read_text()) if path.exists() and playing.stamp(folder) is not None else {}


def due(match: Path) -> list[tuple[Path, Path]]:
    """The matches to train on, none when the weights already know them as they are, or when this machine lacks one
    they were trained on (its video or its review): fewer matches would not replace them."""
    found = sources(match)
    before = trained(playing.weights(match)).get("matches", {})
    now = signature(found)
    return found if found and now != before and set(before) <= set(now) else []


def frames(video: Path, cache: Path, name: str) -> np.ndarray:
    """The video's frames as the model sees them (`playing.frames`), kept in `cache` and read from it while the video is
    the same."""
    path, note = cache / f"{name}.u8", cache / f"{name}.json"
    shape = (playing.HEIGHT, playing.WIDTH, 3)
    made = {"size": video.stat().st_size, "time": int(video.stat().st_mtime)}
    if path.exists() and note.exists():
        known = json.loads(note.read_text())
        if {k: known.get(k) for k in made} == made:
            return np.memmap(path, np.uint8, "r", shape=(known["count"], *shape))
    cache.mkdir(parents=True, exist_ok=True)
    count = 0
    with files.replacing(path, "wb") as f:
        for frame in playing.frames(video):
            f.write(frame.tobytes())
            count += 1
    files.write_text(note, json.dumps({**made, "count": count}))
    return np.memmap(path, np.uint8, "r", shape=(count, *shape))


def train(found: list[tuple[Path, Path]], outputs: Path, steps: int = STEPS, on: str | None = None, told=print) -> None:
    """The model fine-tuned on the matches of `found` (folder, video), its weights put in `outputs`' learned folder once
    done, with what they were trained on."""
    import torch
    from transformers import VideoMAEForVideoClassification

    on = on or playing.device()
    data = []
    for match, video in found:
        told(f"frames {match.name}")
        store = frames(video, outputs / CACHE, match.name)
        data.append((store, *labels(spans(match), len(store))))
    pools = [[(k, s) for k, (_, label, sure) in enumerate(data) for s in np.flatnonzero(sure & (label == c))] for c in (0, 1)]
    if not pools[0] or not pools[1]:
        raise ValueError("no clip of play or of no play to learn from")
    told(f"training on {on}: {len(pools[1])} clips of play, {len(pools[0])} of no play, {steps} steps")
    size = (playing.HEIGHT, playing.WIDTH)
    model = VideoMAEForVideoClassification.from_pretrained(BASE, num_labels=2, ignore_mismatched_sizes=True, image_size=list(size)).to(on)
    mean = torch.tensor([0.485, 0.456, 0.406], device=on).view(1, 1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device=on).view(1, 1, 3, 1, 1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.05)
    warm = max(steps // 10, 1)
    schedule = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda i: min(1, (i + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(1, i / steps))))
    rng = np.random.default_rng(0)
    small = BATCH if on == "cuda" else SMALL_BATCH
    start = time.time()
    model.train()
    for step in range(1, steps + 1):
        picks = [pools[c][rng.integers(len(pools[c]))] for c in rng.integers(0, 2, BATCH)]
        flips = rng.random(BATCH) < 0.5
        for a in range(0, BATCH, small):
            part = picks[a : a + small]
            x = torch.from_numpy(np.stack([data[k][0][s : s + playing.T] for k, s in part])).to(on).permute(0, 1, 4, 2, 3).float().div_(255)
            flip = torch.from_numpy(flips[a : a + small]).to(on)
            x[flip] = x[flip].flip(-1)
            y = torch.tensor([int(data[k][1][s]) for k, s in part], device=on)
            with torch.autocast(on, dtype=torch.bfloat16, enabled=on == "cuda"):
                logits = model(pixel_values=((x - mean) / std).contiguous()).logits
            loss = torch.nn.functional.cross_entropy(logits.float(), y, label_smoothing=0.1)
            (loss * len(part) / BATCH).backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        schedule.step()
        if step % 50 == 0 or step == steps:
            told(f"step {step}/{steps} loss {loss.item():.3f} {time.time() - start:.0f} s")
    made = outputs / CACHE / "weights"
    model.save_pretrained(made)
    folder = outputs / playing.WEIGHTS
    folder.mkdir(parents=True, exist_ok=True)
    # The weights last: their time says which ones a match's P(play) was made with.
    os.replace(made / "config.json", folder / "config.json")
    os.replace(made / playing.MODEL, folder / playing.MODEL)
    files.write_text(folder / TRAINED, json.dumps({"trained": time.strftime("%Y-%m-%d %H:%M"), "matches": signature(found), "steps": steps, "base": BASE, "device": on}, indent=1) + "\n")
    shutil.rmtree(made, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("match", type=Path, help="A match folder: the model learns from every match beside it whose rallies are all checked")
    parser.add_argument("--steps", type=int, default=STEPS)
    parser.add_argument("--force", action="store_true", help="Train even when the weights already know these matches")
    args = parser.parse_args()
    found = sources(args.match) if args.force else due(args.match)
    if not found:
        print("Nothing new to learn: the weights know every match checked here, or a match they know is not on this machine.")
        return
    train(found, files.root(args.match), args.steps)


if __name__ == "__main__":
    main()
