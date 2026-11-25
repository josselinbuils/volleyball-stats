"""Each player's hair and skin for the 3D figures, guessed from their card's picture: a human-parsing model
(SegFormer trained on ATR, MIT licence) splits it into hair, face, arms and legs; their colours and the hair's shape
pick a hair colour, a hairstyle and a skin tone among the few the page draws. It tells the looks that stand out (grey or
blond hair, a very dark skin, long loose hair), not a ponytail seen from the front nor the middle
skin tones (the owner's call, 15 Nov: not a big deal). The Names tab sets the figure, a man's or a woman's, and corrects
the hair colour (likeness_choices.json, by name): the rest is the guess's alone (the owner's call, 16 Nov)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import files

MODEL = "mattmdjaga/segformer_b2_clothes"
# The model's classes used: hair, face, then the legs and arms.
HAIR, FACE, LIMBS = 2, 11, (12, 13, 14, 15)

# What the page draws (web/src/lib/looks.ts holds their colours and the figures).
HAIRS = ("black", "dark", "brown", "blond", "red", "grey")
STYLES = ("short", "mid", "ponytail", "long")
SKINS = 5
FIGURES = ("man", "woman")
# What the Names tab sets: the figure, and the hair colour over the guess's, or bald (never guessed: see `guess`).
ALLOWED = {"figure": FIGURES, "hair": (*HAIRS, "bald")}

# Room around the box above and on the sides: a raised hand or loose hair leaves it.
ABOVE, SIDES = 0.06, 0.1
# The head's part of the box, where its blob must start; and the least head width measured, px.
HEAD_ZONE, MIN_HEAD = 0.25, 8
# Pixels of hair or skin a picture needs for its colour.
MIN_PIXELS = 12
# Pictures parsed at once: about 0.7 GB of the GPU's memory each (16 took 11.5 GB, 15 Nov, RTX 5080), and a full GPU
# spills into the computer's memory, outside WSL's limit: the PC froze. 2 take 1.5 GB at 60 ms a picture.
BATCH = 2

# `guess`'s thresholds on the card's picture, OpenCV's 8-bit Lab (L 0-255), set on 53 labelled players of the three
# first matches (benchmarks/likeness): the skin's L under DARK_SKIN is the darkest tone (the card's picture is touched
# up, its contrast evened: the middle tones mix); the hair's L under which it is black, dark, brown, from which it is
# blond; between, grey. Never bald: hair the picture does not show (under MIN_PIXELS of it: a shaved head, hair cut
# short, the light) is short and black (the owner's call, 16 Nov: a player wrongly made bald). Hair over LONG_SHARE of
# the head, as wide as LONG_LOW head widths low down, falls loose.
DARK_SKIN, HAIR_L, BLOND_L = 90.0, (28.0, 50.0, 66.0), 100.0
LONG_SHARE, LONG_LOW = 0.8, 0.9
# Parsings kept by card picture (its content's hash): an apply makes the same pictures again.
SEEN = "likeness_seen.json"

# The review's corrections, by the player's name else by their card ("team:number").
CHOICES = "likeness_choices.json"
# The name a card gets from its jersey number alone (`review_answers.propose`): another player in each match, whose choices stay in it.
NUMBERED = re.compile(r"Joueur \d+")

LOADED: list = []


def model() -> tuple | None:
    """The parsing model, its processor and device, downloaded the first time; None when it cannot
    be had (offline): the figures keep their made-up looks."""
    if not LOADED:
        try:
            from transformers import AutoModelForSemanticSegmentation, SegformerImageProcessor

            from volleyball_stats.ball import default_device

            device = default_device()
            LOADED.append((AutoModelForSemanticSegmentation.from_pretrained(MODEL).to(device).eval(), SegformerImageProcessor.from_pretrained(MODEL), device))
        except OSError:
            LOADED.append(None)
    return LOADED[0]


def parse(pictures: list[tuple[np.ndarray, tuple]]) -> list[list[float] | None]:
    """Of each (picture, player's box in it): its head's width in px, how far its hair reaches below
    the head's top and how wide it is there (head widths), the shares of the head that are hair and
    face, the hair's median Lab colour and its pixel count, the skin's (face, arms, legs) and its;
    None without a head seen or without the model."""
    loaded = model()
    if loaded is None or not pictures:
        return [None] * len(pictures)
    import torch

    net, processor, device = loaded
    parts = []
    for picture, (x1, y1, x2, y2) in pictures:
        w, h = x2 - x1, y2 - y1
        left, top = max(0, round(x1 - SIDES * w)), max(0, round(y1 - ABOVE * h))
        parts.append((picture[top : max(top + 1, y2), left : max(left + 1, round(x2 + SIDES * w))], y1 - top, h))
    out = []
    for start in range(0, len(parts), BATCH):
        batch = parts[start : start + BATCH]
        x = processor(images=[cv2.cvtColor(p, cv2.COLOR_BGR2RGB) for p, _, _ in batch], return_tensors="pt")["pixel_values"].to(device)
        with torch.no_grad():
            logits = net(pixel_values=x).logits
        for (part, head_top, tall), found in zip(batch, logits):
            labels = torch.nn.functional.interpolate(found[None], size=part.shape[:2], mode="bilinear")[0].argmax(0).cpu().numpy()
            out.append(measure(part, labels, head_top, tall))
    # What the batches held, back to the GPU's other users (the review's server keeps the model loaded).
    if device == "cuda":
        torch.cuda.empty_cache()
    return out


def measure(part: np.ndarray, labels: np.ndarray, head_top: int, tall: int) -> list[float] | None:
    """`parse`'s numbers of one picture from its `labels`, the box's top in it and its height."""
    head = np.isin(labels, (HAIR, FACE)).astype(np.uint8)
    count, blobs, stats, _ = cv2.connectedComponentsWithStats(head)
    # The head: the largest blob starting in the box's top, the player's (another's may show beside).
    starts = [k for k in range(1, count) if stats[k, cv2.CC_STAT_TOP] <= head_top + HEAD_ZONE * tall]
    if not starts:
        return None
    blob = blobs == max(starts, key=lambda k: stats[k, cv2.CC_STAT_AREA])
    rows = np.flatnonzero(blob.any(1))
    widths = blob.sum(1)
    top = rows[0]
    # Its width: the widest row of its first part, before any hair falling on the shoulders.
    first = widths[top : top + max(2, int(1.2 * widths[top : top + 4 * MIN_HEAD].max()))]
    across = float(first.max())
    if across < MIN_HEAD:
        return None
    hair = blob & (labels == HAIR)
    face = blob & (labels == FACE)
    hair_rows = np.flatnonzero(hair.any(1))
    reach = float((hair_rows[-1] - top + 1) / across) if len(hair_rows) else 0.0
    below = hair[top + round(1.1 * across) :]
    low = float(below.sum(1).max() / across) if below.size and below.any() else 0.0
    lab = cv2.cvtColor(part, cv2.COLOR_BGR2LAB)
    eroded = lambda m: m if m.sum() < 4 * MIN_PIXELS else cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)  # noqa: E731
    skin = eroded(face | np.isin(labels, LIMBS))
    hair_in = eroded(hair)
    hair_lab = np.median(lab[hair_in], axis=0).tolist() if hair_in.sum() >= MIN_PIXELS else [0.0, 0.0, 0.0]
    skin_lab = np.median(lab[skin], axis=0).tolist() if skin.sum() >= MIN_PIXELS else [0.0, 0.0, 0.0]
    size = float(blob.sum())
    return [across, reach, low, float(hair.sum()) / size, float(face.sum()) / size, *hair_lab, float(hair_in.sum()), *skin_lab, float(skin.sum())]


def guess(found: list[float] | None) -> dict | None:
    """A player's hair colour, hairstyle and skin tone from `parse`'s numbers of their card's picture; None without."""
    if found is None:
        return None
    _, _, low, share, _, hair_l, _, _, hair_n, skin_l, _, _, skin_n = found
    out: dict = {}
    if skin_n >= MIN_PIXELS:
        out["skin"] = SKINS if skin_l < DARK_SKIN else 2
    if hair_n < MIN_PIXELS:
        return {**out, "hair": "black", "style": "short"}
    out["hair"] = "black" if hair_l < HAIR_L[0] else "dark" if hair_l < HAIR_L[1] else "brown" if hair_l < HAIR_L[2] else "blond" if hair_l >= BLOND_L else "grey"
    out["style"] = "long" if low >= LONG_LOW and share >= LONG_SHARE else "short"
    return out


def dress(match: Path, people: dict[int, dict], cards: dict[int, Path]) -> None:
    """`people` with their `look`: guessed from their card's picture (`cards`, by key), with the figure and hair colour
    the Names tab set (`chosen`, by name else by card); none for a player with neither."""
    path = match / SEEN
    seen = files.read_json(path, {})
    hashes = {key: hashlib.sha256(card.read_bytes()).hexdigest()[:16] for key, card in cards.items()}
    new = [key for key in cards if hashes[key] not in seen]
    if new:
        found = parse([(picture, (0, 0, picture.shape[1], picture.shape[0])) for picture in (cv2.imread(str(cards[key])) for key in new)])
        if LOADED and LOADED[0] is not None:
            seen.update({hashes[key]: f for key, f in zip(new, found)})
            files.write_text(path, json.dumps({h: seen[h] for h in set(hashes.values()) if h in seen}))
        else:
            seen.update({hashes[key]: None for key in new})
    given = chosen(match)
    for key, person in people.items():
        if not person.get("number"):
            continue
        look = corrected(guess(seen.get(hashes[key])) if key in hashes else None, given.get(person.get("name") or "") or given.get(f"{person['team']}:{person['number']}"))
        if look:
            person["look"] = look
        else:
            person.pop("look", None)


def corrected(guessed: dict | None, given: dict | None) -> dict | None:
    """`guessed` with the Names tab's choices `given` over it; None with neither."""
    out = {**(guessed or {}), **(given or {})}
    return out or None


def chosen(match: Path) -> dict[str, dict]:
    """The Names tab's choices (CHOICES), by name or card, the ALLOWED ones only; a name's in another match too (the latest's), a
    player looking the same from one match to the next, but a NUMBERED one's."""
    out: dict[str, dict] = {}
    others = sorted((p for p in match.parent.glob(f"*/{CHOICES}") if p.parent != match), key=lambda p: p.stat().st_mtime)
    for path in others:
        out.update({who: look for who, look in json.loads(path.read_text()).items() if ":" not in who and not NUMBERED.fullmatch(who)})
    path = match / CHOICES
    for who, look in (files.read_json(path, {})).items():
        out[who] = {**out.get(who, {}), **look}
    return {who: kept for who, look in out.items() if (kept := {k: v for k, v in look.items() if v in ALLOWED.get(k, ())})}


def choose(match: Path, who: str, field: str, value: str | None) -> None:
    """CHOICES with `who`'s `field` (an ALLOWED one) set to `value`, None taking it off. ValueError for anything else."""
    if field not in ALLOWED or (value is not None and value not in ALLOWED[field]):
        raise ValueError(f"{field} {value!r}")
    path = match / CHOICES
    taken = files.read_json(path, {})
    mine = taken.setdefault(who, {})
    if value is None:
        mine.pop(field, None)
    else:
        mine[field] = value
    if not mine:
        taken.pop(who)
    files.write_text(match / CHOICES, json.dumps(taken, indent=1, ensure_ascii=False) + "\n")
