"""Scores a model's cache files (run.py) against the reviewed matches, offline, as the pipeline would use them: the
right picks on the answered touches (rule and learned order held out), the jump benchmark's measures, the attack and
relance types of the checked rallies. `yolo11m-pose` reads the pipeline's own caches.

    python benchmarks/pose/score.py MODEL [--clips] [--parts wrists jumps relances] [--conf 0.7] [--keypoint-conf 0.3]
"""

import argparse
import contextlib
import importlib.util
import io
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("ranker_bench", HERE.parent / "attribution" / "ranker.py")
rk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rk)
spec = importlib.util.spec_from_file_location("jumps_bench", HERE.parent / "jumps" / "bench.py")
jb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jb)

from volleyball_stats import actions, attribution, jumps, ranker, web  # noqa: E402
from volleyball_stats.court import Calibration  # noqa: E402

MATCHES = ["2026-10-29-aspom-1-vs-aspom-2", "2026-11-02-avia-1-vs-aspom-2"]
POSES = Path("outputs/benchmarks/pose/runs")
FPS = 50.0


def cache_of(model: str, match: str, part: str) -> Path:
    return Path("outputs/matches") / match / f"{part}.json" if model == "pipeline" else POSES / model / match / f"{part}.json"


def wrists(model: str, clips: bool) -> dict:
    scratch = POSES / model / "ranker-cache"
    scratch.mkdir(parents=True, exist_ok=True)
    rk.CACHE = scratch
    data = []
    for match in MATCHES:
        folder = Path("outputs/matches") / match
        source = json.loads((folder / "source.json").read_text())
        shutil.copy(cache_of(model, match, "wrists"), scratch / f"{match}_wrists.json")
        part = rk.from_match(folder, Path(source["video"]), Path(source["court"]))
        data += part
    if clips:
        data += [d for c in ("side_club", "side_long", "side_holdout") for d in rk.from_clip(c)]
    groups = sorted({d["group"] for d in data})
    out = {m: {"touches": 0, "rule": 0, "learned": 0, "among": 0, "second": 0} for m in MATCHES}
    for g in groups:
        test = [d for d in data if d["group"] == g]
        if g in ("side_club", "side_long", "side_holdout"):
            continue
        match = next(m for m in MATCHES if g.startswith(m))
        model_ = ranker.fit(rk.trainable([d for d in data if d["group"] != g]), 0.01)
        o = out[match]
        o["touches"] += len(test)
        o["rule"] += sum(d["right"][d["tracks"].index(d["rule"])] for d in test)
        o["learned"] += sum(d["right"][rk.pick(model_, d)] for d in test)
        o["among"] += sum(any(d["right"]) for d in test)
    return out


def jump_scores(model: str, heldout: bool) -> dict:
    out = {}
    for match in MATCHES:
        labels = [r for r in __import__("csv").DictReader(open(jb.HELDOUT if heldout else jb.LABELS)) if r["match"] == match]
        folder = Path("outputs/matches") / match
        source = json.loads((folder / "source.json").read_text())
        attacks = [(int(r["frame"]), int(r["track"])) for r in labels]
        tracks = jumps.read_tracks(folder / "players.csv", {t for _, t in attacks})
        poses = jumps.pose_all(Path(source["video"]), attacks, {(f, t): tracks[t] for f, t in attacks}, FPS, cache_of(model, match, "jumps"))
        ball = jumps.read_ball(folder / "ball.csv", {f for a, _ in attacks for f in jumps.window(a, FPS)})
        data = {"labels": labels, "tracks": tracks, "poses": poses, "ball": ball, "calibration": Calibration.load(Path(source["court"]))}
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            jb.score(data)
        out[match] = buffer.getvalue()
    return out


def relance_scores(model: str) -> dict:
    out = {}
    for match in MATCHES:
        folder = Path("outputs/matches") / match
        truth = json.loads(Path(f"outputs/benchmarks/corrections/{match}/truth.json").read_text())
        touches = sorted((t["frame"], t["type"]) for r in truth["rallies"] for t in r["touches"])
        frames = np.array([f for f, _ in touches])
        cache = cache_of(model, match, "relances")
        kept = json.loads(cache.read_text())
        rows = [r for r in web.read_csv(folder / "actions.csv") if r["type"] in ("attack", "relance") and str(int(r["frame"])) in kept]
        typed = [(int(r["frame"]), int(r["x"]), int(r["y"]), "attack", r["side"]) for r in rows]
        actions.decode.frames_at = lambda video, wanted: iter(())  # the cache holds the frames the rule reads
        marked = actions.mark_relances(Path(json.loads((folder / "source.json").read_text())["video"]), typed, FPS, cache)
        got = {t[0]: t[3] for t in marked}
        right = wrong = false_relance = missed_relance = 0
        for frame, kind in got.items():
            k = int(np.abs(frames - frame).argmin()) if len(frames) else None
            if k is None or abs(frames[k] - frame) > 5 or touches[k][1] not in ("attack", "relance"):
                continue
            ok = (kind == "relance") == (touches[k][1] == "relance")
            right += ok
            wrong += not ok
            false_relance += (not ok) and kind == "relance"
            missed_relance += (not ok) and kind != "relance"
        out[match] = {"checked": right + wrong, "right": right, "relance_for_attack": false_relance, "attack_for_relance": missed_relance, "marked": sum(v == "relance" for v in got.values()), "of": len(got)}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("--clips", action="store_true")
    parser.add_argument("--parts", nargs="*", default=["wrists", "jumps", "relances"])
    parser.add_argument("--conf", type=float, help="attribution.WRIST_CONF")
    parser.add_argument("--keypoint-conf", type=float, help="jumps.KEYPOINT_CONF")
    args = parser.parse_args()
    if args.conf is not None:
        attribution.WRIST_CONF = args.conf
    if args.keypoint_conf is not None:
        jumps.KEYPOINT_CONF = args.keypoint_conf
    result = {}
    if "wrists" in args.parts:
        result["wrists"] = wrists(args.model, args.clips)
        print(json.dumps(result["wrists"]), flush=True)
    if "jumps" in args.parts:
        for heldout in (False, True):
            result[f"jumps{'_heldout' if heldout else ''}"] = jump_scores(args.model, heldout)
            for m, text in result[f"jumps{'_heldout' if heldout else ''}"].items():
                print("jumps", "heldout" if heldout else "tuned", m[:10], re.sub(r"\s+", " ", text), flush=True)
    if "relances" in args.parts:
        result["relances"] = relance_scores(args.model)
        print(json.dumps(result["relances"]), flush=True)
    path = POSES / args.model
    path.mkdir(parents=True, exist_ok=True)
    tag = f"_conf{args.conf}_k{args.keypoint_conf}" if args.conf or args.keypoint_conf else ""
    (path / f"scores{tag}.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
