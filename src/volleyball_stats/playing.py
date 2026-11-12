"""Where play goes on: a clip model's P(play) every 0.25 s (`play.npz` of the match folder) and what the rally windows take from it.

Each use is separate (`USES`): the ends carried on through play the ball track lost, the starts pulled back to where play began,
the windows with play all along kept (`actions.no_play`), and play going on after a floor contact or a dead-ball run (`goes_on`).
Without the weights the stage does not run and the pipeline is as before.
"""

import subprocess
from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np

from volleyball_stats import actions, decode, rallies

FILE = "play.npz"
# VideoMAE-base fine-tuned on the reviewed matches (`benchmarks/rallies/play.py`; its base weights are CC BY-NC 4.0), beside the
# project's other models.
WEIGHTS = Path(__file__).resolve().parents[2] / "models" / "play"
# A clip: T frames at FPS, the whole width and the top 224 of 252 rows, a P(play) every STRIDE frames.
FPS, T, WIDTH, HEIGHT, FULL_HEIGHT, STRIDE = 8, 16, 448, 224, 252, 2
USES = ("ends", "starts", "keep", "alive")
# Play goes on after a contact when it is live all through this span of seconds after it (`goes_on`).
ALIVE_S = (1.0, 3.0)
# A window a model sees play in for KEEP_FRAC of its length or more is no dead ball (`actions.no_play`).
KEEP_FRAC = 0.85
THRESHOLD = 0.3
GAP_S = 1.0
# An end is moved when play goes on 1.5 s or more past it, up to 15 s and never into the next window.
MARGIN_S, AHEAD_S = 1.5, 15.0
# A start is pulled back when play began 2 s or more before it, up to 30 s and never into the previous window.
START_MARGIN_S, BACK_S = 2.0, 30.0


def load(path: Path) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    """The seconds of each clip's middle, its P(play) and the uses wanted (a benchmark writes `uses` to try them one by one)."""
    z = np.load(path)
    return (z["starts"] + z["T"] / 2) / z["fps"], z["p"], tuple(str(z["uses"]).split(",")) if "uses" in z else USES


def live(p: np.ndarray, step: float, threshold: float = THRESHOLD, gap_s: float = GAP_S) -> np.ndarray:
    """P over `threshold`, dips shorter than `gap_s` between two live moments bridged."""
    out = p > threshold
    for a, b in rallies.runs(~out, 0, 1):
        if b - a + 1 <= gap_s / step and a > 0 and b + 1 < len(out):
            out[a : b + 1] = True
    return out


def moved(windows: list[rallies.Rally], fps: float, times: np.ndarray, p: np.ndarray, uses: tuple[str, ...] = USES) -> list[rallies.Rally]:
    """The windows (in order) with their ends and starts moved by P(play), as `uses` asks."""
    if not len(times) or not windows:
        return windows
    step = float(times[1] - times[0])
    on = live(p, step)
    lead = actions.LEAD_S
    out = [(s / fps, e / fps) for s, e in windows]
    if "ends" in uses:
        for k, (s, e) in enumerate(out):
            following = out[k + 1][0] - lead if k + 1 < len(out) else np.inf
            i = min(int(np.searchsorted(times, e)), len(times) - 1)
            if on[(times >= s) & (times <= e)].any() and on[i]:
                hi = min(e + AHEAD_S, following)
                while i + 1 < len(times) and on[i + 1] and times[i + 1] <= hi:
                    i += 1
                if times[i] - e >= MARGIN_S:
                    out[k] = (s, float(times[i]))
    if "starts" in uses:
        for k, (s, e) in enumerate(out):
            previous = out[k - 1][1] if k else -np.inf
            i = int(np.searchsorted(times, s))
            i = min(i, len(times) - 1)
            if on[max(i - 1, 0)] or on[i]:
                lo = max(s - BACK_S, previous)
                while i > 0 and on[i - 1] and times[i - 1] >= lo:
                    i -= 1
                if s - (times[i] + lead) >= START_MARGIN_S:
                    out[k] = (float(times[i]) + lead, e)
    return [(round(s * fps), round(e * fps)) for s, e in out]


def confirmed(windows: list[rallies.Rally], fps: float, times: np.ndarray, p: np.ndarray) -> set[int]:
    """Indexes of the windows play goes on in all along."""
    on = live(p, float(times[1] - times[0])) if len(times) > 1 else np.zeros(0, bool)
    out = set()
    for k, (s, e) in enumerate(windows):
        inside = (times >= s / fps) & (times <= e / fps)
        if inside.sum() >= 4 and on[inside].mean() >= KEEP_FRAC:
            out.add(k)
    return out


def goes_on(times: np.ndarray, p: np.ndarray, fps: float) -> Callable[[int], bool]:
    """Whether play goes on after a frame: a floor contact or a dead-ball run followed by play is none (`actions`)."""
    on = live(p, float(times[1] - times[0])) if len(times) > 1 else np.zeros(0, bool)

    def alive(frame: int) -> bool:
        after = on[(times >= frame / fps + ALIVE_S[0]) & (times <= frame / fps + ALIVE_S[1])]
        return len(after) >= 4 and bool(after.all())

    return alive


def available() -> bool:
    return (WEIGHTS / "model.safetensors").exists()


def predict(video: Path, out: Path, batch: int = 32) -> None:
    """P(play) of the clips of `video`, streamed (16 frames in memory), written to `out` as `load` reads it."""
    import torch
    from transformers import VideoMAEForVideoClassification

    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    model = VideoMAEForVideoClassification.from_pretrained(WEIGHTS).to(device).eval()
    mean = torch.tensor([0.485, 0.456, 0.406], device=device).view(1, 1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device=device).view(1, 1, 3, 1, 1)
    hardware = decode.hardware(video)
    if hardware[1:] == ("cuda",):
        # Scaled on the card, as the training frames were (`benchmarks/rallies/play.py`): no 4K frame leaves it.
        hardware, scale = (*hardware, "-hwaccel_output_format", "cuda"), f"scale_cuda={WIDTH}:{FULL_HEIGHT},hwdownload,format=nv12"
    else:
        scale = f"scale={WIDTH}:{FULL_HEIGHT}"
    command = ["ffmpeg", "-v", "error", *hardware, "-i", str(video), "-an", "-sn", "-dn", "-vf", f"fps={FPS},{scale},format=rgb24", "-f", "rawvideo", "-"]
    size = FULL_HEIGHT * WIDTH * 3
    window: deque[np.ndarray] = deque(maxlen=T)
    clips, starts, probabilities = [], [], []

    def flush() -> None:
        x = torch.from_numpy(np.stack(clips)).to(device).permute(0, 1, 4, 2, 3).float().div_(255)
        with torch.no_grad(), torch.autocast(device, dtype=torch.bfloat16, enabled=device == "cuda"):
            logits = model(pixel_values=((x - mean) / std).contiguous()).logits
        probabilities.extend(logits.float().softmax(-1)[:, 1].cpu().tolist())
        clips.clear()

    with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
        n = 0
        while (buf := process.stdout.read(size)) and len(buf) == size:
            window.append(np.frombuffer(buf, np.uint8).reshape(FULL_HEIGHT, WIDTH, 3)[:HEIGHT].copy())
            n += 1
            if n >= T and (n - T) % STRIDE == 0:
                clips.append(np.stack(window))
                starts.append(n - T)
                if len(clips) == batch:
                    flush()
        if clips:
            flush()
    np.savez(out, starts=np.array(starts), p=np.array(probabilities), fps=FPS, T=T)
