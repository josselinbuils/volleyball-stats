"""The cards' pictures of the players: each one's best moment in the video, framed, upscaled and touched up (`photos`), the one
picked in the review instead (`swap_photo`), and their scores and appearances kept beside the match (PHOTO_SCORES,
PHOTO_VECTORS). `web.build` puts them on the page."""

import csv
import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats import decode, files, likeness, updates
from volleyball_stats.court import LENGTH, WIDTH
from volleyball_stats.identity import finder, read_identities
from volleyball_stats.web import page_data, patch_people, versioned

# The players' pictures show about 240 px tall: kept at twice that for sharp high-density screens, never enlarged. They are 3
# wide for 4 tall, like a photo.
PHOTO_PX, PHOTO_RATIO = 480, 0.75
# The cards' pictures: in the pieces of a player the review shows and the user left unmarked (sure
# to be them), PHOTO_SAMPLES moments each, alone, on the court (ON_COURT m around it at most: not
# walking past the camera) and with room around them for a centred picture (ROOM of their height
# each side); of those, the PHOTO_PICKS where they stand tallest, the closest to the camera,
# PHOTO_MORE more when none faces the camera (FACED or less), and in the player's kit: their top's
# colour within KIT (Lab) of its median over their KIT_SAMPLES tallest moments in play (a rally,
# IN_PLAY_S around it) inside the court's lines, not a hoodie put on during a break or on the bench. Scored on facing the camera (`looks`,
# weighing FACING), the whole body seen (its keypoints), sharpness (weighing SHARP) and size (SIZE)
# against the player's other moments, less CROWD per other person as large as OTHER of them in the
# picture; the scores kept in MATCH/PHOTO_SCORES, a 4K frame costing a seek.
PHOTO_SAMPLES, ON_COURT, ROOM, PHOTO_PICKS, PHOTO_MORE, FACED = 24, 1.0, 0.35, 24, 72, 0.3
IN_PLAY_S, KIT_SAMPLES, KIT = 3.0, 12, 40.0
# And looking like the pictures of them the user confirmed: their re-identification embeddings'
# median cosine to those within LIKE of the player's best moment (players' own ranges differ: on the
# first ASPOM match, 0.72-0.83 for one, 0.46-0.70 for another seen in a hoodie too); kept in
# MATCH/PHOTO_VECTORS.
LIKE, PHOTO_VECTORS = 0.08, "photo_vectors.npz"
# Each player's PHOTO_CHOICES best moments, the one shown first, kept in MATCH/PHOTO_CANDIDATES by
# team:identity for the review to offer; the one the user picked instead, by name, in
# MATCH/PHOTO_PICKED.
PHOTO_CHOICES, PHOTO_CANDIDATES, PHOTO_PICKED = 8, "photo_candidates.json", "photo_choices.json"
# Where the review's card pictures were taken, by file (players/KEY.webp): the track and frame, for an
# apply to keep each picture on the player it shows until the new ones come (`kept_photos`).
PHOTO_SHOWN = "photo_shown.json"
# Raise it when what `photos` keeps of a moment's scores changes.
SCORES_FORMAT = 1
# The moments framed so far, by frame and box.
PHOTO_KEPT = "photo_moments"
FACING, SHARP, CROWD, OTHER, SIZE, PHOTO_SCORES = 3.0, 2.0, 0.5, 0.3, 2.0, "photo_scores.json"
# The picture: from HEADROOM above the head (its box's top) down BUST of the body's height (the
# waist: a closer face lacks detail in 4K), centred on the shoulders' middle, at PHOTO_RATIO;
# keypoints under KEYPOINT confidence are not used.
BUST, HEADROOM, KEYPOINT = 0.55, 0.08, 0.5
# Then upscaled 4 times by Nomos (4xNomosWebPhoto_RealPLKSR, CC-BY-4.0, trained on degraded web
# photos: cleaner and firmer than the video's compressed pixels, no face made up), downloaded once
# into UPSCALER, and brought back to PHOTO_PX tall.
UPSCALER = Path("models/4xNomosWebPhoto_RealPLKSR.safetensors")
SMEARS, CLEAN = 120, 200
UPSCALER_URL = "https://huggingface.co/Phips/4xNomosWebPhoto_RealPLKSR/resolve/main/4xNomosWebPhoto_RealPLKSR.safetensors"
# Last, the gym's yellow cast taken off by WARMTH of a gray world balance, local contrast (CLAHE at
# CONTRAST), and, without the upscaler, sharpened by SHARPEN (unsharp mask).
WARMTH, CONTRAST, SHARPEN = 0.35, 1.5, 0.4


def cut(image: np.ndarray, x: float, top: int, bottom: int, wide: int) -> tuple[np.ndarray, tuple[int, int, float]]:
    """Rows `top` to `bottom` of `image`, `wide` wide centred on `x` (the frame's edges mirrored past
    them: the player stays in the middle), no taller than PHOTO_PX (never enlarged); and its left, top
    and scale."""
    left = round(x - wide / 2)
    height, width = image.shape[:2]
    part = image[max(0, top) : min(height, bottom), max(0, left) : min(width, left + wide)]
    if part.size:
        part = cv2.copyMakeBorder(part, max(0, -top), max(0, bottom - height), max(0, -left), max(0, left + wide - width), cv2.BORDER_REFLECT_101)
    scale = min(1.0, PHOTO_PX / max(1, part.shape[0]))
    if part.size and scale < 1:
        part = cv2.resize(part, (max(1, round(part.shape[1] * scale)), PHOTO_PX), interpolation=cv2.INTER_AREA)
    return part, (left, top, scale)


def packed(vectors: dict[str, np.ndarray]) -> bytes:
    """`vectors` as the bytes of an .npz: their names, then the vectors in float16."""
    import io

    out = io.BytesIO()
    np.savez(out, names=np.array(list(vectors)), vectors=np.array(list(vectors.values()), np.float16))
    return out.getvalue()


# Player pictures scored together (`photos`): their crops held in memory meanwhile.
SCORE_BATCH = 64


def framed(image: np.ndarray, box: tuple[int, int, int, int]) -> tuple[np.ndarray, tuple[int, int, float]]:
    """A player's whole picture from their `box`: a little room above and below them, widened to
    PHOTO_RATIO; and its left, top and scale (`cut`)."""
    from volleyball_stats.review import CROP_MARGIN

    x1, y1, x2, y2 = box
    my = round((y2 - y1) * CROP_MARGIN)
    return cut(image, (x1 + x2) / 2, y1 - my, y2 + my, max(x2 - x1, round((y2 - y1 + 2 * my) * PHOTO_RATIO)))


# The upscaler once loaded: a picture picked in the review takes a second, not its load again.
LOADED_UPSCALER: list = []


def upscaler() -> tuple | None:
    """The cards' pictures' upscaler (UPSCALER) and its device, downloaded the first time; None when
    it cannot be had (offline): the pictures stay as cut."""
    import urllib.request

    if LOADED_UPSCALER:
        return LOADED_UPSCALER[0]

    try:
        if not UPSCALER.exists():
            UPSCALER.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(UPSCALER_URL, context=updates.tls()) as response:
                files.write_bytes(UPSCALER, response.read())
    except OSError:
        return None
    from spandrel import ModelLoader

    from volleyball_stats.ball import default_device

    device = default_device()
    LOADED_UPSCALER.append((ModelLoader().load_from_file(UPSCALER).to(device).eval(), device))
    return LOADED_UPSCALER[0]


def upscaled(upscaler: tuple, picture: np.ndarray) -> np.ndarray:
    """`picture` 4 times larger from `upscaler` (model, device), no taller than PHOTO_PX, touched up
    without sharpening; a small one blended with its plain enlargement, from none of the upscaler's
    at SMEARS px tall to all of it at CLEAN (it smears a face of a few pixels)."""
    import torch

    model, device = upscaler
    x = torch.from_numpy(cv2.cvtColor(picture, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255).unsqueeze(0).to(device)
    with torch.no_grad():
        big = cv2.cvtColor(model(x)[0].clamp(0, 1).mul(255).permute(1, 2, 0).byte().cpu().numpy(), cv2.COLOR_RGB2BGR)
    tall = min(big.shape[0], PHOTO_PX)
    size = (max(1, round(big.shape[1] * tall / big.shape[0])), tall)
    share = float(np.clip((picture.shape[0] - SMEARS) / (CLEAN - SMEARS), 0, 1))
    plain = cv2.resize(picture, size, interpolation=cv2.INTER_CUBIC)
    return touched_up(cv2.addWeighted(cv2.resize(big, size, interpolation=cv2.INTER_AREA), share, plain, 1 - share, 0), sharpen=0.0)


def touched_up(picture: np.ndarray, sharpen: float = SHARPEN) -> np.ndarray:
    """`picture` with WARMTH of its colour cast off, CONTRAST and `sharpen`."""
    means = picture.reshape(-1, 3).mean(0)
    out = np.clip(picture * (1 + WARMTH * (means.mean() / np.maximum(means, 1) - 1)), 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=CONTRAST, tileGridSize=(4, 4)).apply(lab[..., 0])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return cv2.addWeighted(out, 1 + sharpen, cv2.GaussianBlur(out, (0, 0), 1.0), -sharpen, 0)


def bust(box: tuple) -> tuple[int, int]:
    """The rows of a player's picture from their `box`: HEADROOM above the head down BUST of it."""
    span = BUST * (box[3] - box[1])
    return round(box[1] - HEADROOM * span), round(box[1] + span)


def face(image: np.ndarray, box: tuple, head: list[float] | None) -> np.ndarray:
    """A player's picture (`bust`), centred on their shoulders' middle (`head`: the nose's y, the
    shoulders' middle x and y), else on their box."""
    top, bottom = bust(box)
    return cut(image, head[1] if head else (box[0] + box[2]) / 2, top, bottom, round((bottom - top) * PHOTO_RATIO))[0]


def looks(pictures: list[tuple[np.ndarray, tuple]]) -> list[tuple[float, float, float, int, list | None, list]]:
    """(facing, whole, sharp, others, head) of each (picture, player's box in it), of the person the pose
    model finds best matching the box (0 for none): how much they face the camera (their eyes and
    nose seen, the nose midway between the eyes: off to a side in profile), its mean confidence in all
    the keypoints; the variance of the Laplacian (of the `bust`); the other people found as large as OTHER of the box; the
    nose's y and the shoulders' middle x and y, None unless all three are seen (KEYPOINT); the mean
    Lab colour of their top (the box's rows from a fifth to under half its height, its middle half)."""
    from ultralytics import YOLO

    from volleyball_stats.actions import POSE_MODEL

    model, out = YOLO(str(POSE_MODEL)), []
    for (picture, box), found in zip(pictures, model.predict([p for p, _ in pictures], imgsz=384, verbose=False, stream=True)):
        gray = cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        x1, y1, x2, y2 = box
        h, w = y2 - y1, x2 - x1
        shirt = picture[max(0, y1 + h // 5) : y1 + 9 * h // 20, max(0, x1 + w // 4) : x2 - w // 4]
        kit = cv2.cvtColor(shirt, cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(0).tolist() if shirt.size else [0.0, 0.0, 0.0]
        boxes, confidence = found.boxes.xyxy.cpu().numpy(), found.keypoints.conf
        if not len(boxes) or confidence is None:
            out.append((0.0, 0.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()), 0, None, kit))
            continue
        inter = np.clip(np.minimum(boxes[:, 2], x2) - np.maximum(boxes[:, 0], x1), 0, None) * np.clip(np.minimum(boxes[:, 3], y2) - np.maximum(boxes[:, 1], y1), 0, None)
        union = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]) + (x2 - x1) * (y2 - y1) - inter
        best = int(np.argmax(inter / np.maximum(union, 1)))
        seen = confidence.cpu().numpy()[best]
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        others = int((areas >= OTHER * (x2 - x1) * (y2 - y1)).sum()) - 1
        # COCO keypoints: 0 the nose, 5 and 6 the shoulders.
        points = found.keypoints.xy.cpu().numpy()[best]
        head = [float(points[0, 1]), float(points[5:7, 0].mean()), float(points[5:7, 1].mean())] if min(seen[0], seen[5], seen[6]) >= KEYPOINT and points[5:7, 1].mean() > points[0, 1] else None
        # Sharpness where the picture will be.
        top, bottom = bust(box)
        gray = gray[max(0, top) : bottom]
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var()) if gray.size else 0.0
        # COCO keypoints 1 and 2: the eyes.
        spread = abs(points[1, 0] - points[2, 0])
        middle = 1 - 2 * abs(points[0, 0] - (points[1, 0] + points[2, 0]) / 2) / spread if spread > 1 else 0.0
        facing = float(min(seen[0], seen[1], seen[2]) * max(0.0, middle))
        out.append((facing, float(seen.mean()), sharp, max(0, others), head, kit))
    return out


def scores_stamp(video: Path) -> str:
    """What the pictures' scores and appearances depend on: the video, the dependencies, the two
    models and the code computing them, not the rest of this module: a new score costs minutes.
    SCORES_FORMAT stands for `scored`, inside `photos`."""
    from volleyball_stats.actions import POSE_MODEL
    from volleyball_stats.identity import REID, describe, load_reid
    from volleyball_stats.review_questions import CROP_MARGIN

    return files.cache_stamp(video, [POSE_MODEL, REID], f"{SCORES_FORMAT}:{CROP_MARGIN}:" + files.code_text(looks, framed, describe, load_reid))


# The re-identification model, its device and `describe`, once loaded: the review makes pictures after each apply.
LOADED_REID: list = []


class Stopped(Exception):
    """The pictures given up (`photos`' `stop`): the review opened another match."""


def photos(match: Path, video: Path, people: dict[int, dict], folder: Path, teams: set[int] = {1, 2}, record: Path | None = None, stop: Callable[[], bool] = lambda: False) -> dict[int, tuple]:
    """A picture of each numbered player of `teams` among `people` in `folder`, as their `photo`: their
    best moment (PHOTO_PICKS), framed, and their `look` for the 3D figures from it (`likeness.dress`); returns each
    pictured player's (frame, box, head). `record` (PHOTO_SHOWN) gets where each picture was taken. Stopped once `stop`
    says so, between two frames read."""
    from volleyball_stats.decode import frames_apart
    from volleyball_stats.review_answers import log_of, piece_key
    from volleyball_stats.review_questions import ALONE, IDENTITY_CROPS, Questions

    if not teams or not (match / "identity_candidates.json").exists():
        return {}
    fps = decode.fps(video)
    questions = Questions(match, fps)
    width, height = decode.size(video)
    marked = {piece_key(o) for e in log_of(match) for o in e.get("odd", [])}

    def room(box: tuple) -> bool:
        x1, y1, x2, y2 = box
        side = ROOM * (y2 - y1)
        return (x1 + x2) / 2 - side >= 0 and (x1 + x2) / 2 + side <= width and y1 > 0 and y2 < height - 1

    with open(match / "rallies.csv", encoding="utf-8") as f:
        rallies = [(int(r["start_frame"]), int(r["end_frame"])) for r in csv.DictReader(f)]
    margin = IN_PLAY_S * fps

    def in_play(frame: int) -> bool:
        return any(start - margin <= frame <= end + margin for start, end in rallies)

    moments: dict[int, list[tuple[int, tuple]]] = {}
    spare: dict[int, list[tuple[int, tuple]]] = {}
    kits: dict[int, list[tuple[int, tuple]]] = {}
    confirmed: dict[int, list[tuple[int, tuple]]] = {}
    for key, person in people.items():
        if person["number"] and person["team"] in teams:
            team, number = person["team"], person["number"]
            pieces = questions.pieces(team, number)[:IDENTITY_CROPS]
            kept = [((track, start, end), p) for (track, start, end, _, _), p in zip(pieces, questions.faces(team, number)["pieces"]) if piece_key(p) not in marked and track in questions.rows]
            shown = [piece for piece, _ in kept]
            confirmed[key] = [(p["frame"], questions.box(p["track"], p["frame"])) for _, p in kept]
            found, playing_in = [], []
            for track, start, end in shown:
                rows = questions.track_rows(track, start, end)
                found += [
                    (int(questions.frame_of[r]), tuple(int(v) for v in questions.box_of[r]))
                    for r in rows[:: max(1, len(rows) // PHOTO_SAMPLES)]
                    if questions.covered(r) < ALONE and abs(questions.court_of[r][0]) <= LENGTH / 2 + ON_COURT and abs(questions.court_of[r][1]) <= WIDTH / 2 + ON_COURT
                ]
                # Inside the court's lines: playing, not waiting at its edge.
                playing_in += [
                    (int(questions.frame_of[r]), tuple(int(v) for v in questions.box_of[r]))
                    for r in rows[:: max(1, len(rows) // PHOTO_SAMPLES)]
                    if in_play(int(questions.frame_of[r])) and abs(questions.court_of[r][0]) <= LENGTH / 2 and abs(questions.court_of[r][1]) <= WIDTH / 2
                ]
            fitting = sorted((m for m in found if room(m[1])), key=lambda m: m[1][1] - m[1][3])
            if fitting or found:
                moments[key] = fitting[:PHOTO_PICKS] or sorted(found, key=lambda m: m[1][1] - m[1][3])[:1]
                spare[key] = fitting[PHOTO_PICKS : PHOTO_PICKS + PHOTO_MORE]
                kits[key] = sorted(playing_in, key=lambda m: m[1][1] - m[1][3])[:KIT_SAMPLES] or moments[key][:KIT_SAMPLES]
    # The scores and the appearances are kept under what makes them; another stamp's start again.
    # The appearances are written first, so scores under a stamp mean appearances under it too.
    stamp = scores_stamp(video)
    path = match / PHOTO_SCORES
    saved = files.read_json(path, {})
    current = saved.get("stamp") == stamp
    scores = saved["scores"] if current else {}
    name = lambda frame, box: f"{frame}:{','.join(map(str, box))}"  # noqa: E731

    vectors_path = match / PHOTO_VECTORS
    vectors: dict[str, np.ndarray] = {}
    if current and vectors_path.exists():
        with np.load(vectors_path) as found:
            vectors = dict(zip(found["names"].tolist(), found["vectors"].astype(np.float32)))
    reid = LOADED_REID

    def scored(moments: dict[int, list]) -> None:
        """`scores` holding every one of `moments` (`looks`) and `vectors` their appearance (the
        re-identification embedding of their box), read from the video where missing, SCORE_BATCH
        pictures at a time: a long match's cut all at once took the machine's memory (13 Nov)."""
        wanted: dict[int, list[tuple]] = {}
        for f, b in {m for found in moments.values() for m in found if len(scores.get(name(*m), ())) != 6 or name(*m) not in vectors}:
            wanted.setdefault(f, []).append(b)
        pictures: dict[str, tuple] = {}
        boxes: dict[str, np.ndarray] = {}

        def flush() -> None:
            if boxes:
                if not reid:
                    from volleyball_stats.ball import default_device
                    from volleyball_stats.identity import describe, load_reid

                    device = default_device()
                    reid.extend([load_reid(device), device, describe])
                model, device, describe = reid
                vectors.update(zip(boxes, describe(list(boxes.values()), model, device)))
            if pictures:
                for key, (facing, whole, sharp, others, head, kit) in zip(pictures, looks([(p, b) for p, b, _ in pictures.values()])):
                    left, top, scale = pictures[key][2]
                    # The head back in the frame's pixels.
                    scores[key] = [facing, whole, sharp, others, head and [top + head[0] / scale, left + head[1] / scale, top + head[2] / scale], kit]
            pictures.clear()
            boxes.clear()

        scored_any = False
        for frame, image in frames_apart(video, wanted):
            if stop():
                raise Stopped
            for box in wanted[frame]:
                part, (left, top, scale) = framed(image, box)
                # Copies: a view would keep the whole 4K frame alive.
                pictures[name(frame, box)] = (part.copy(), tuple(round((v - o) * scale) for v, o in zip(box, (left, top, left, top))), (left, top, scale))
                x1, y1, x2, y2 = box
                boxes[name(frame, box)] = image[max(0, y1) : y2, max(0, x1) : x2].copy()
                scored_any = True
            if len(boxes) >= SCORE_BATCH:
                flush()
        flush()
        if scored_any:
            files.write_bytes(vectors_path, packed(vectors))
            files.write_text(path, json.dumps({"stamp": stamp, "scores": scores}))

    scored(moments)
    scored(kits)
    scored(confirmed)
    # Players facing the camera in none of their closest moments: their farther ones too.
    turned = {key: spare[key] for key, found in moments.items() if spare.get(key) and max(scores[name(*m)][0] for m in found) <= FACED}
    scored(turned)
    for key, more in turned.items():
        moments[key] = moments[key] + more
    # In their kit: a top like the one they play in, their moments in play among the candidates (all
    # the closest may be in a hoodie); and looking like the pictures the user confirmed (a piece's
    # track may switch to someone else).
    facing_card: dict[int, list] = {}
    for key, found in moments.items():
        kit = np.median([scores[name(*m)][5] for m in kits[key]], axis=0)
        found = list(dict.fromkeys(found + [m for m in kits[key] if room(m[1])]))
        found = [m for m in found if np.linalg.norm(np.subtract(scores[name(*m)][5], kit)) <= KIT] or found
        seen = np.array([vectors[name(*m)] for m in confirmed[key]])
        alike = {m: float(np.median(seen @ vectors[name(*m)])) for m in found}
        moments[key] = [m for m in found if alike[m] >= max(alike.values()) - LIKE]
        # The card's own pictures facing the camera, offered first: the closest moments are often from behind.
        facing_card[key] = sorted({m for m in confirmed[key] if scores[name(*m)][0] > FACED}, key=lambda m: -scores[name(*m)][0])
        fitting_card = [m for m in facing_card[key] if room(m[1]) and np.linalg.norm(np.subtract(scores[name(*m)][5], kit)) <= KIT]
        moments[key] = list(dict.fromkeys(moments[key] + fitting_card))
    # The moments the user picked, by the player's name, else on their card while it still holds that moment.
    path = match / PHOTO_PICKED
    taken = files.read_json(path, {})

    def pick_of(person: dict) -> dict | None:
        if person.get("name") in taken:
            return taken[person["name"]]
        found = taken.get(f"{person['team']}:{person['number']}")
        return found if found and any(a <= found["frame"] <= b for _, a, b, _, _ in questions.pieces(person["team"], person["number"])) else None

    own = {key: (found["frame"], tuple(found["box"])) for key in moments if (found := pick_of(people[key]))}
    scored({key: [m] for key, m in own.items()})
    chosen: dict[int, list] = {}
    picked: dict[int, tuple] = {}
    offered: dict[str, list] = {}
    for key, found in moments.items():
        top = [max(scores[name(f, b)][2] for f, b in found), max(b[3] - b[1] for _, b in found)]

        def score(moment: tuple[int, tuple]) -> float:
            facing, whole, sharp, others, _, _ = scores[name(*moment)]
            return FACING * facing + whole + SHARP * sharp / max(top[0], 1e-9) + SIZE * (moment[1][3] - moment[1][1]) / max(top[1], 1) - CROWD * others

        ranked = sorted(found, key=score, reverse=True)
        frame, box = own.get(key, ranked[0])
        offered[f"{people[key]['team']}:{people[key]['number']}"] = [{"frame": f, "box": list(b)} for f, b in list(dict.fromkeys([(frame, box), *facing_card[key], *ranked]))[:PHOTO_CHOICES]]
        chosen.setdefault(frame, []).append((key, box))
        picked[key] = (frame, box, scores[name(frame, box)][4])
    files.write_changed(match / PHOTO_CANDIDATES, json.dumps(offered))
    folder.mkdir(parents=True, exist_ok=True)
    # A moment already framed and upscaled is not decoded again: most stay from one apply to the next.
    # They are kept under what makes them, by frame, box and head; any other stamp's go.
    stamp = files.cache_stamp(video, [Path(__file__)])
    kept = match / PHOTO_KEPT / stamp
    for old in (match / PHOTO_KEPT).glob("*"):
        if old != kept:
            shutil.rmtree(old, ignore_errors=True)
    kept.mkdir(parents=True, exist_ok=True)

    def kept_at(frame: int, box: tuple) -> Path:
        return moment_file(kept, frame, box, scores[name(frame, box)][4])

    missing = {frame: pairs for frame, pairs in chosen.items() if any(not kept_at(frame, box).exists() for _, box in pairs)}
    up = upscaler() if missing else None
    for frame, image in frames_apart(video, missing):
        for _, box in missing[frame]:
            part = face(image, box, scores[name(frame, box)][4])
            if part.size:
                cv2.imwrite(str(kept_at(frame, box)), upscaled(up, part) if up else touched_up(part), [cv2.IMWRITE_WEBP_QUALITY, 80])
    taken_at = {}
    for frame, pairs in chosen.items():
        for key, box in pairs:
            if kept_at(frame, box).exists():
                shutil.copyfile(kept_at(frame, box), folder / f"{key}.webp")
                people[key]["photo"] = versioned(folder / f"{key}.webp", folder.name)
                taken_at[f"{folder.name}/{key}.webp"] = {"track": questions.track_at(frame, box), "frame": frame}
    if record:
        files.write_changed(record, json.dumps(taken_at))
    likeness.dress(match, people, {key: folder / f"{key}.webp" for key in picked if (folder / f"{key}.webp").exists()})
    return picked


def moment_file(kept: Path, frame: int, box: tuple, head: list | None) -> Path:
    """Where the picture framed at `frame` in `box` around `head` is kept, in PHOTO_KEPT's folder `kept`."""
    digest = hashlib.sha256(json.dumps(head).encode()).hexdigest()[:8]
    return kept / f"{frame}_{'_'.join(str(v) for v in box)}_{digest}.webp"


def swap_photo(match: Path, video: Path, site: Path, team: int, number: int, frame: int, box: list[int], track_at: Callable[[int, tuple], int | None]) -> dict | None:
    """The page at `site` with the card picture of identity `number` of `team` the one taken at `frame` in `box` (PHOTO_PICKED
    has it), its look from it; PHOTO_SHOWN and PHOTO_CANDIDATES following, and the page MATCH/site too when it shows the
    player's picture. Only that picture is cut (a second, against a whole page's build). Returns the player's `photo` and
    `look`; None when the moment was not scored (`photos` scores every one it offers) or the page has no such player: the
    pages are to be built again."""
    people = (page_data(site) or {}).get("people") or {}
    key = next((k for k, p in people.items() if (p["team"], p["number"]) == (team, number)), None)
    path = match / PHOTO_SCORES
    saved = files.read_json(path, {})
    box = tuple(int(v) for v in box)
    scored = saved.get("scores", {}).get(f"{frame}:{','.join(map(str, box))}") if saved.get("stamp") == scores_stamp(video) else None
    if key is None or not scored or len(scored) != 6:
        return None
    kept = match / PHOTO_KEPT / files.cache_stamp(video, [Path(__file__)])
    picture = moment_file(kept, frame, box, scored[4])
    if not picture.exists():
        image = decode.frame_at(video, frame)
        part = face(image, box, scored[4]) if image is not None else np.empty(0)
        if not part.size:
            return None
        up = upscaler()
        kept.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(picture), upscaled(up, part) if up else touched_up(part), [cv2.IMWRITE_WEBP_QUALITY, 80])
    folder = site / "players"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(picture, folder / f"{key}.webp")
    person = people[key]
    person["photo"] = versioned(folder / f"{key}.webp", folder.name)
    likeness.dress(match, {key: person}, {key: folder / f"{key}.webp"})
    patch_people(site, people)
    shown = match / PHOTO_SHOWN
    taken = files.read_json(shown, {})
    taken[f"{folder.name}/{key}.webp"] = {"track": track_at(frame, box), "frame": frame}
    files.write_text(shown, json.dumps(taken))
    offered = match / PHOTO_CANDIDATES
    if offered.exists():
        found = json.loads(offered.read_text(encoding="utf-8"))
        mine = found.get(f"{team}:{number}", [])
        found[f"{team}:{number}"] = [{"frame": frame, "box": list(box)}, *(m for m in mine if (m["frame"], tuple(m["box"])) != (frame, box))]
        files.write_text(offered, json.dumps(found))
    # The page to publish, with its own pictures when it has them: the same player's swapped too.
    published = page_data(match / "site") if (match / "page.json").exists() else None
    other = next((p for p in (published or {}).get("people", {}).values() if (p["team"], p["number"]) == (team, number) and p.get("photo")), None)
    if other:
        found_at = match / "site" / other["photo"].split("?")[0]
        shutil.copyfile(picture, found_at)
        other["photo"] = versioned(found_at, found_at.parent.name)
        patch_people(match / "site", published["people"])
    return {"photo": person["photo"], "look": person.get("look")}


def kept_photos(people: dict[int, dict], site: Path, match: Path, kept: tuple[str, ...] = ("photo", "look")) -> None:
    """`people` with the pictures the page at `site` shows and the looks that go with them (`kept`), each on
    the player it shows now: the (team, number) whose piece holds where it was taken (PHOTO_SHOWN), else
    the player of the same name; none for the others until the new pictures come. An apply moves numbers
    between players."""
    path = match / PHOTO_SHOWN
    taken = files.read_json(path, {})
    find = finder(read_identities(match / "identities.csv")) if taken and (match / "identities.csv").exists() else None
    by_card: dict[tuple[int, int], dict] = {}
    by_name: dict[str, dict] = {}
    for p in (page_data(site) or {}).get("people", {}).values():
        file = (p.get("photo") or "").split("?")[0]
        if not file or not (site / file).exists():
            continue
        at = taken.get(file)
        if at and at.get("track") is not None and find:
            now = find(at["track"], at["frame"])
            if now:
                by_card.setdefault(now, p)
        elif p.get("name"):
            by_name.setdefault(p["name"], p)
    for person in people.values():
        found = by_card.get((person["team"], person["number"])) or by_name.get(person.get("name") or "")
        for field in kept:
            if found and found.get(field):
                person[field] = found[field]


def refresh_photos(match: Path, video: Path, site: Path, stop: Callable[[], bool] = lambda: False) -> dict:
    """The people of the page at `site` with new pictures in its folder, for `patch_people`; Stopped once `stop` says so."""
    people = page_data(site)["people"]
    photos(match, video, people, site / "players", {1, 2}, match / PHOTO_SHOWN, stop)
    return people
