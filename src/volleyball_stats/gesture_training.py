"""The touch-type model (`gesture`) trained on the matches reviewed here: VideoMAE-base fine-tuned on each contact's clip
labelled by its checked rally's touch, and the heads reading its scores with the rules' type, written beside the matches
(`outputs/learned/gesture/`) where the backup shares them with the other machines.

    uv run python -m volleyball_stats.gesture_training outputs/matches/MATCH [--epochs 4] [--force] [--held DIR]

"Apprendre de mes réponses" runs it after the play model's training (`learn.train_gesture`), when the checked rallies of
the matches fully checked changed since the last training (`due`). The heads learn from scores the model gives on matches
it was not trained on: the matches are cut in folds (one a fold up to FOLDS), a model trained without each fold scoring
it; a last model is trained on all. The check comes with it: each fold typed by its fold's model and heads trained on the
other folds, against the rules. The new weights replace the old ones only when they type more touches right
(`refused.json` else, as the play model's). `--held DIR` keeps each fold's model and heads in DIR/MATCH, for
`benchmarks/corrections` to run a match with weights that never saw it. Fast on an NVIDIA card (two hours on four matches),
far longer on a Mac or a processor alone.
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from volleyball_stats import actions, files, gesture, jobs, learn, review_answers, web

TRAINED, REFUSED = "trained.json", "refused.json"
ROOT = Path(__file__).resolve().parents[2]
# The recipe measured on four matches (`benchmarks/actions/README.md`): 4 epochs of clips 2 at a time, their gradients
# added up 4 times; the heads 80 epochs of 64 rows.
EPOCHS, MICRO, ACCUMULATE = 4, 2, 4
HEAD_EPOCHS, HEAD_BATCH = 80, 64
# ponytail: at most FOLDS models trained for the heads' scores, as many matches as can be shared out; more folds (one a
# match) for many matches would cost a training each.
FOLDS = 4
# The share of the work, in seconds a clip on the PC (measured once on four matches): cut from the video, trained an
# epoch, scored.
CUT_S, EPOCH_S, SCORE_S = 0.4, 0.1, 0.05


def truth(match: Path, fps: float) -> list[dict] | None:
    """Each checked rally's frames and touches (frame, type), from the review's page; None unless every rally is checked:
    the heads learn the order of whole rallies."""
    page = web.page_data(match / "review")
    log = review_answers.load_log(match / "identity_answers.json") if (match / "identity_answers.json").exists() else []
    if not review_answers.reviewed(page, log):
        return None
    out = []
    for k, r in enumerate(page["rallies"]):
        end = round(r["end"] * fps)
        touches = [(round(c["t"] * fps), c["type"]) for c in page["contacts"] if c["rally"] == k and round(c["t"] * fps) <= end]
        out.append({"start": round(r["start"] * fps), "end": end, "touches": touches})
    return out


def labels(rallies: list[dict], table: Sequence[dict], fps: float) -> np.ndarray:
    """Each contact's class (`gesture.LABELS`): the checked touch nearest it within `learn.SAME_S` in its rally, "none"
    without one, -1 for a touch of another kind or a contact out of every rally (left out)."""
    lead, within = round(actions.LEAD_S * fps), round(learn.SAME_S * fps)
    y = np.full(len(table), -1, np.int64)
    for r in rallies:
        inside = [i for i, t in enumerate(table) if r["start"] - lead <= t["frame"] <= r["end"]]
        frames = [table[i]["frame"] for i in inside]
        best: dict[int, tuple[str, int]] = {}
        for frame, kind in r["touches"]:
            f = learn.near(frame, frames, within)
            if f is not None and (f not in best or abs(frame - f) < best[f][1]):
                best[f] = (kind, abs(frame - f))
        for i in inside:
            kind = best.get(table[i]["frame"], ("none", 0))[0]
            y[i] = gesture.LABELS.index(kind) if kind in gesture.LABELS else -1
    return y


def sources(match: Path) -> list[tuple[Path, Path]]:
    """The matches beside `match` (it too) the model can learn from on this machine, each with its video: every rally
    checked, the pipeline's tables and the video here."""
    found = []
    for source in sorted(match.parent.glob(f"*/{files.SOURCE}")):
        folder, video = source.parent, ROOT / json.loads(source.read_text())["video"]
        if video.exists() and (folder / "actions.csv").exists() and truth(folder, 50.0) is not None:
            found.append((folder, video))
    return found


def signature(found: list[tuple[Path, Path]]) -> dict[str, str]:
    """What each match teaches, by name: any change to its checked touches moves it."""
    return {m.name: hashlib.sha256(json.dumps(truth(m, 50.0)).encode()).hexdigest()[:16] for m, _ in found}


def trained(folder: Path) -> dict:
    path = folder / TRAINED
    return json.loads(path.read_text()) if path.exists() and gesture.stamp(folder) is not None else {}


def refused(folder: Path) -> dict[str, str] | None:
    path = folder / REFUSED
    return json.loads(path.read_text())["matches"] if path.exists() else None


def due(match: Path) -> list[tuple[Path, Path]]:
    """The matches to train on, none when the weights already know them as they are, when this machine lacks one they
    were trained on, or under two matches (ponytail: the heads need scores of a match the model did not see; one match
    would need its rallies cut in folds, as measured first)."""
    found = sources(match)
    folder = gesture.weights(match)
    before, now = trained(folder).get("matches", {}), signature(found)
    return found if len(found) >= 2 and now != before and set(before) <= set(now) and now != refused(folder) else []


def contacts(match: Path, video: Path) -> list[dict]:
    """The match's contacts as the stage reads them (`gesture.table`): its gesture.json when the stage ran, else made from
    the pipeline's tables (the types there the rules')."""
    path = match / gesture.FILE
    if path.exists():
        return json.loads(path.read_text())["contacts"]
    from volleyball_stats import attribution, ball3d, decode
    from volleyball_stats.court import Calibration

    fps = decode.fps(video)
    calibration = Calibration.load(ROOT / json.loads((match / files.SOURCE).read_text())["court"])
    rows = learn.read_rows(match / "actions.csv")
    typed = [(int(r["frame"]), int(r["x"]), int(r["y"]), r["type"], r["side"]) for r in rows]
    touchers = [int(r["track"]) if r["track"] != "" else None for r in rows]
    windows = [(int(w["start_frame"]), int(w["end_frame"])) for w in learn.read_rows(match / "rallies.csv")]
    places = ball3d.flight_places(typed, windows, round(actions.LEAD_S * fps), match / "ball.csv", calibration, fps) if calibration.lens else {}
    boxes = gesture.boxes_near(attribution.read_players(match / "players.csv"), {t[0] for t in typed})
    return gesture.table(typed, touchers, windows, fps, calibration, places, boxes, decode.size(video))


class Clips:
    """Several matches' clips indexed as one (a match's store and each of its contacts' row there)."""

    def __init__(self, parts: list[tuple[np.ndarray, list[int]]]) -> None:
        self.parts = parts
        self.start = np.cumsum([0] + [len(at) for _, at in parts])

    def __len__(self) -> int:
        return int(self.start[-1])

    def __getitem__(self, i: int) -> np.ndarray:
        k = int(np.searchsorted(self.start, i, side="right") - 1)
        store, at = self.parts[k]
        return store[at[i - self.start[k]]]


def weight_of(y: np.ndarray, on: str):
    """The classes' loss weights: the square root of their rarity, averaging 1."""
    import torch

    counts = np.bincount(y, minlength=len(gesture.LABELS)) + 1
    weight = torch.tensor((counts.sum() / counts) ** 0.5, dtype=torch.float32, device=on)
    return weight / weight.mean()


def fit(clips: Clips, y: np.ndarray, epochs: int, seed: int, on: str, share: jobs.Share = jobs.quiet, told=print):
    """The model fine-tuned on the labelled clips (y >= 0), the share of its steps told to `share`."""
    import torch
    import torch.nn.functional as F

    torch.manual_seed(seed)
    np.random.seed(seed)
    net = gesture.network().to(on)
    net.body.gradient_checkpointing_enable()
    keep = np.flatnonzero(y >= 0)
    labels_on = torch.from_numpy(y).to(on)
    body = [p for n, p in net.named_parameters() if n.startswith("body")]
    rest = [p for n, p in net.named_parameters() if n.startswith(("norm", "head."))]
    optimizer = torch.optim.AdamW([{"params": body, "lr": 4e-5}, {"params": rest, "lr": 1e-3}], weight_decay=0.05)
    steps = epochs * math.ceil(len(keep) / (MICRO * ACCUMULATE))
    schedule = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda s: min(1, (s + 1) / 20) * 0.5 * (1 + math.cos(math.pi * min(s, steps) / steps)))
    weight = weight_of(y[keep], on)
    seen = jobs.every(epochs * len(keep), share)
    net.train()
    start, done = time.time(), 0
    for epoch in range(epochs):
        order = np.random.permutation(keep)
        total, n = 0.0, 0
        for s in range(0, len(order), MICRO):
            ids = sorted(order[s : s + MICRO])
            with torch.autocast(on, dtype=torch.bfloat16, enabled=on == "cuda"):
                logits = net(gesture.pixels(clips, ids, on, train=True))
            loss = F.cross_entropy(logits.float(), labels_on[ids], weight=weight, label_smoothing=0.1)
            (loss / ACCUMULATE).backward()
            total, n = total + loss.item(), n + 1
            if (s // MICRO + 1) % ACCUMULATE == 0 or s + MICRO >= len(order):
                torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                schedule.step()
            done += len(ids)
            seen(done - 1)
        told(f"epoch {epoch + 1}/{epochs} loss {total / n:.3f} {time.time() - start:.0f} s")
    return net


def fit_heads(x: np.ndarray, y: np.ndarray, on: str) -> list:
    """`gesture.HEADS` heads trained on the rows `x` (`gesture.head_input`) of the labelled contacts (y >= 0), a seed each."""
    import torch
    import torch.nn.functional as F

    keep = y >= 0
    xt, yt = torch.from_numpy(x[keep]).to(on), torch.from_numpy(y[keep]).to(on)
    weight = weight_of(y[keep], on)
    heads = []
    for seed in range(gesture.HEADS):
        torch.manual_seed(seed)
        head = gesture.head(x.shape[1]).to(on)
        optimizer = torch.optim.AdamW(head.parameters(), lr=2e-3, weight_decay=1e-2)
        schedule = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=2e-3, total_steps=HEAD_EPOCHS * math.ceil(len(xt) / HEAD_BATCH))
        for _ in range(HEAD_EPOCHS):
            head.train()
            order = torch.randperm(len(xt), device=on)
            for s in range(0, len(xt), HEAD_BATCH):
                b = order[s : s + HEAD_BATCH]
                loss = F.cross_entropy(head(xt[b]), yt[b], weight=weight, label_smoothing=0.1)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                schedule.step()
        heads.append(head.eval())
    return heads


def right(p: np.ndarray, y: np.ndarray) -> int:
    """The touches (labelled, not "none") whose best touch class in `p` is the label."""
    touch = (y >= 0) & (y != gesture.NONE)
    return int((p[touch, : gesture.NONE].argmax(1) == y[touch]).sum())


def save(net, heads: list, folder: Path, about: dict) -> None:
    """The model and its heads in `folder`, the weights last: their time says which ones typed a match."""
    from safetensors.torch import save_file

    for k, h in enumerate(heads):
        net.heads[k].load_state_dict(h.state_dict())
    folder.mkdir(parents=True, exist_ok=True)
    made = folder / (gesture.MODEL + ".part")
    net.body.config.to_json_file(str(folder / gesture.CONFIG))
    save_file({k: v.detach().contiguous().cpu() for k, v in net.state_dict().items()}, str(made))
    os.replace(made, folder / gesture.MODEL)
    files.write_text(folder / TRAINED, json.dumps(about, indent=1) + "\n")


def learn_from(found: list[tuple[Path, Path]], outputs: Path, weights: Path, epochs: int = EPOCHS, held: Path | None = None, told=print, share: jobs.Share = jobs.tell) -> bool:
    """The weights in `weights` trained on the matches of `found` when the check passes (more touches typed right than the
    rules, over all the folds); else they stay and the matches are written as refused (`due` skips them). Whether they
    were trained."""
    import torch

    from volleyball_stats import decode

    on = gesture.device()
    tables = [contacts(m, v) for m, v in found]
    ys = [labels(truth(m, decode.fps(v)), t, decode.fps(v)) for (m, v), t in zip(found, tables)]
    folds = [list(range(k, len(found), min(FOLDS, len(found)))) for k in range(min(FOLDS, len(found)))]
    cache = outputs / gesture.CACHE
    missing = []
    for (m, v), t in zip(found, tables):
        index = cache / m.name / "index.json"
        known = json.loads(index.read_text())["keys"] if index.exists() else {}
        missing.append(sum(gesture.key(c) not in known for c in t))
    labelled = [int((y >= 0).sum()) for y in ys]
    total = sum(labelled)
    work = {"clips": CUT_S * sum(missing) + 1}
    for k, fold in enumerate(folds):
        work[f"fold{k}"] = EPOCH_S * epochs * (total - sum(labelled[i] for i in fold)) + SCORE_S * sum(len(tables[i]) for i in fold)
    work["final"] = EPOCH_S * epochs * total
    part = jobs.parts(share, work)
    cut = part("clips")
    stores = []
    for k, ((m, v), t) in enumerate(zip(found, tables)):
        told(f"clips {m.name}: {missing[k]} to cut")
        before = sum(missing[:k])
        stores.append(gesture.clips(v, t, cache / m.name, lambda s, b=before, n=missing[k]: cut((b + s * n) / max(sum(missing), 1))))
    cut(1.0)
    tabs = [gesture.tabular(t) for t in tables]
    scores: list[np.ndarray | None] = [None] * len(found)
    nets = []
    for k, fold in enumerate(folds):
        rest = [i for i in range(len(found)) if i not in fold]
        told(f"model without {', '.join(found[i][0].name for i in fold)}")
        fold_part = jobs.parts(part(f"fold{k}"), {"fit": work[f"fold{k}"] - SCORE_S * sum(len(tables[i]) for i in fold), "score": SCORE_S * sum(len(tables[i]) for i in fold)})
        net = fit(Clips([stores[i] for i in rest]), np.concatenate([ys[i] for i in rest]), epochs, 0, on, fold_part("fit"), told)
        for j, i in enumerate(fold):
            scores[i] = gesture.scores(net, *stores[i], on, lambda s, j=j: fold_part("score")((j + s) / len(fold)))
        if held:
            nets.append((fold, net.cpu()))
        del net
        if on == "cuda":
            torch.cuda.empty_cache()
    x = [gesture.head_input(p, tab) for p, tab in zip(scores, tabs)]
    gain, rules, of = 0, 0, 0
    checked = {}
    for k, fold in enumerate(folds):
        rest = [i for i in range(len(found)) if i not in fold]
        heads = fit_heads(np.concatenate([x[i] for i in rest]), np.concatenate([ys[i] for i in rest]), on)
        for i in fold:
            p = gesture.stacked(heads, scores[i], tabs[i], on)
            by_rules = gesture.onehot([t["rules"] for t in tables[i]], gesture.LABELS)
            m = found[i][0].name
            checked[m] = {"rules": right(by_rules, ys[i]), "model": right(p, ys[i]), "of": int(((ys[i] >= 0) & (ys[i] != gesture.NONE)).sum())}
            told(f"{m} held out: {checked[m]['model']} right types with the model, {checked[m]['rules']} with the rules, of {checked[m]['of']}")
            gain, rules, of = gain + checked[m]["model"] - checked[m]["rules"], rules + checked[m]["rules"], of + checked[m]["of"]
        if held:
            net = next(n for f, n in nets if f == fold)
            for i in fold:
                save(net, heads, held / found[i][0].name, {"trained": time.strftime("%Y-%m-%d %H:%M"), "without": found[i][0].name, "matches": signature([found[j] for j in rest])})
    told(f"held out: {gain:+d} right types over the rules ({rules} of {of})")
    nets.clear()
    if gain <= 0:
        weights.mkdir(parents=True, exist_ok=True)
        files.write_text(weights / REFUSED, json.dumps({"matches": signature(found), "checked": checked}, indent=1) + "\n")
        told("The gesture model's weights stay as they were: trained without each match, it would not type its touches better than the rules.")
        return False
    told("model on all the matches")
    net = fit(Clips(stores), np.concatenate(ys), epochs, 9, on, part("final"), told)
    heads = fit_heads(np.concatenate(x), np.concatenate(ys), on)
    about = {"trained": time.strftime("%Y-%m-%d %H:%M"), "matches": signature(found), "epochs": epochs, "base": gesture.BASE, "device": on, "checked": checked, "gain": gain}
    save(net, heads, weights, about)
    (weights / REFUSED).unlink(missing_ok=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("match", type=Path, help="A match folder: the model learns from every match beside it whose rallies are all checked")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--force", action="store_true", help="Train even when the weights already know these matches")
    parser.add_argument("--held", type=Path, help="Keep each match's model trained without it in HELD/MATCH (for benchmarks/corrections)")
    args = parser.parse_args()
    found = sources(args.match) if args.force else due(args.match)
    if len(found) < 2:
        print("Nothing new to learn: the weights know every match checked here, a match they know is not on this machine, or fewer than two are checked.")
        return
    if args.held:
        shutil.rmtree(args.held, ignore_errors=True)
    learn_from(found, files.root(args.match), gesture.weights(args.match), args.epochs, args.held, lambda line: print(line, flush=True))


if __name__ == "__main__":
    main()
