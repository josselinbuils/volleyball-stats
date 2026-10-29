"""Action classification of a rally's ball contacts, by the rules of volleyball.

The first contact of a rally is the serve, unless it is inside the court, where no serve is taken:
that contact is a dig. A rally window opening on such a contact is no rally but the ball thrown back
to the server, and `served` drops it. After each net
crossing the receiving side touches the ball at most 3 times: 1 is the pass when the ball comes from
the serve and the dig otherwise, 2 the set, 3 the attack. A touch shortly after an attack is the opposing block, which does not count. A
touch by the serving side before the ball crosses is the net. A contact at floor level is the floor,
and every contact after it too: the ball is dead.

Sides are left and right of the net as seen from the camera, which films from a sideline aligned
with the net: the net plane projects to a line, whichever the ball's height. Floor level comes from
the court calibration: a contact taken on the floor (its floor projection) lands where the ball is
only if the ball is on the floor; a ball in the air projects farther from the camera.
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.court import Calibration

# Relances (free balls): a third touch played without attacking, ball not above the player's head
# and feet on the floor; an attack is hit above the head, often jumping. Measured on the player's
# box from a pose model, whose boxes leave out the blurred hitting arm: on the labelled clips the
# ball is above the box top for 21 of 22 attacks, at or below it for the relances.
# ponytail: thresholds from 1 labelled relance and 3 likely ones; set them on labelled matches.
POSE_MODEL = Path("models/yolo11m-pose.pt")
ABOVE, LIFT = 0.0, 0.1
# The player under the ball is within UNDER_PX of it horizontally (at 720p); their feet are followed
# back LIFT_S seconds by box overlap.
UNDER_PX = 15
LIFT_S = 1.0

# ponytail: rallies.py starts a window 1-7 frames after the serve contact, so windows start this
# many seconds earlier; drop it once rallies.py starts at the contact.
LEAD_S = 0.33
# Seconds after an attack within which a touch is the block: 0.1-0.2 s on the labelled clips, the
# next dig 0.67 s or more.
BLOCK_S = 0.33
# Court y (meters, toward the camera) from which a contact's floor projection is on the floor: any
# contact past FLOOR_Y (digs project under 1.3 m on the labelled clips), the rally's last contact
# past the far sideline. Projections over MARGIN outside the court are balls in the air, or above
# the horizon (mapped behind the camera).
FLOOR_Y, LAST_FLOOR_Y = 2.0, -4.5
MARGIN = 2.0
# Court x (meters from the net) under which a first contact's floor projection is inside the court:
# a ball in the air only projects farther, even past the far sideline, and the labelled serves
# project from 12.3 m (11.1 m on full_match, whose balls tossed back to the server project under 6 m).
SERVE_X = 8.0
# Touches in a row by one player from which the ball is dead, held or bounced (before a serve, say):
# nobody plays it twice running. ponytail: from 2 examples; runs of 2 are mostly attribution errors
# (71-83% right), set it on labelled matches.
DEAD_RUN = 3

Contact = tuple[int, int, int]
Typed = tuple[int, int, int, str, str]


def net_u(calibration: Calibration | None, net_x: float, v: float) -> float:
    """Image x of the net at image row v: the line through the net's feet on both sidelines.

    ponytail: a straight line only from a camera in the net plane; the labelled clips' camera is
    within about 1 m of it (the net spans x 598-632 px), so a ball at the net can fall on either side.
    """
    if calibration is None:
        return net_x
    (u0, v0), (u1, v1) = calibration.to_image(np.array([[0.0, -4.5], [0.0, 4.5]]))
    return u0 + (v - v0) * (u1 - u0) / (v1 - v0)


def on_floor(calibration: Calibration | None, x: float, y: float, last: bool) -> bool:
    """Whether the contact at image (x, y) is on the floor, `last` when it is the rally's last.

    ponytail: one image point cannot tell a low dig far from the camera from a floor bounce, so
    away from the camera only the last contact can be the floor; it assumes the window ends at the
    dead ball. The ball's height from its parabola (3D by physics) is the upgrade. Without a
    calibration there is no floor.
    """
    if calibration is None:
        return False
    cx, cy = calibration.to_court(np.array([[x, y]]))[0]
    return abs(cx) <= 9 + MARGIN and (LAST_FLOOR_Y if last else FLOOR_Y) <= cy <= 4.5 + MARGIN


def in_court(calibration: Calibration | None, x: float, y: float) -> bool:
    """Whether the contact at image (x, y) is surely over the court, short of its end lines.

    ponytail: a ball above the horizon maps behind the camera and is never inside; the toucher's
    feet would tell, once attribution runs before typing.
    """
    if calibration is None:
        return False
    cx, cy = calibration.to_court(np.array([[x, y]]))[0]
    return abs(cx) < SERVE_X and cy <= 4.5 + MARGIN


def classify_rally(contacts: list[Contact], crossings: list[int], fps: float, net_x: float, calibration: Calibration | None = None) -> list[Typed]:
    """(frame, x, y, type, side) of a rally's contacts, in frame order."""
    out: list[Typed] = []
    touches, crossed, blocked, attack, dead, thrown = 0, 0, False, None, False, 0
    contacts = sorted(contacts)
    for frame, x, y in contacts:
        now = sum(c <= frame for c in crossings)
        if not out and not now and in_court(calibration, x, y):
            # Counted as after a crossing that was no serve's.
            thrown = 1
        now += thrown
        if now > crossed:
            touches, crossed = 0, now
        side = "left" if x < net_u(calibration, net_x, y) else "right"
        if dead or on_floor(calibration, x, y, frame == contacts[-1][0]):
            kind, dead = "floor", True
        elif not out and not crossed:
            kind = "serve"
        elif attack and frame - attack[0] <= BLOCK_S * fps:
            kind, side, touches, blocked = "block", "left" if attack[1] == "right" else "right", 0, True
        elif not crossed:
            # ponytail: only a serve into the net; a ball into the net after a crossing is typed by
            # its touch number. Add a rule at the net line once a few are labelled (1 today).
            kind = "net"
        else:
            touches += 1
            # A crossing before the first contact is an unseen serve's. ponytail: every touch from the
            # 3rd is the attack, a bump that saves a bad set included.
            kind = {1: "pass" if crossed == 1 and not blocked and not thrown else "dig", 2: "set"}.get(touches, "attack")
        # A second blocker's touch is a block too.
        attack = (frame, side) if kind == "attack" else attack if kind == "block" else None
        out.append((frame, x, y, kind, side))
    return out


def served(rallies: list[tuple[int, int]], contacts: list[Contact], fps: float, calibration: Calibration | None = None) -> list[tuple[int, int]]:
    """`rallies` without the windows opening on a contact inside the court: their first contact
    comes before the window, so it sent the flight the window starts on, and no serve is taken
    there. A first contact later in the window follows a serve the detector missed."""
    lead = round(LEAD_S * fps)
    out = []
    for start, end in rallies:
        first = min((c for c in contacts if start - lead <= c[0] <= end), default=None)
        if first is None or first[0] > start or not in_court(calibration, first[1], first[2]):
            out.append((start, end))
    return out


def classify(contacts: list[Contact], crossings: list[int], rallies: list[tuple[int, int]], fps: float, net_x: float, calibration: Calibration | None = None) -> list[Typed]:
    """Typed contacts of every rally; contacts outside the rallies are dropped."""
    out: list[Typed] = []
    for start, end in rallies:
        start -= round(LEAD_S * fps)
        inside = [c for c in contacts if start <= c[0] <= end]
        out += classify_rally(inside, [c for c in crossings if start <= c <= end], fps, net_x, calibration)
    return out


def mark_dead(typed: list[Typed], touchers: list[int | None], rallies: list[int | None]) -> tuple[list[Typed], list[int | None]]:
    """`typed` and `touchers` with each run of DEAD_RUN touches or more in a row by one track, and
    the rest of its rally, retyped "floor" without a toucher; `rallies` holds each contact's rally."""
    typed, touchers = list(typed), list(touchers)
    k = 0
    while k < len(typed):
        end = k + 1
        while end < len(typed) and touchers[k] is not None and touchers[end] == touchers[k] and rallies[end] == rallies[k]:
            end += 1
        if end - k >= DEAD_RUN:
            while end < len(typed) and rallies[end] == rallies[k]:
                end += 1
            for m in range(k, end):
                typed[m] = (*typed[m][:3], "floor", typed[m][4])
                touchers[m] = None
        k = end
    return typed, touchers


def player_under(ball: tuple[float, float], boxes: np.ndarray, reach: float) -> int | None:
    """Index of the box horizontally within `reach` of the ball whose top is nearest to it."""
    dx = np.maximum(0, np.maximum(boxes[:, 0] - ball[0], ball[0] - boxes[:, 2])) if len(boxes) else np.array([])
    near = np.flatnonzero(dx <= reach)
    return int(near[np.argmin(np.abs(boxes[near, 1] - ball[1]))]) if len(near) else None


def relance_cues(ball: tuple[float, float], box: np.ndarray, feet: list[float]) -> tuple[float, float]:
    """Ball height above the box top, and how far the feet (box bottoms, the contact's first) are
    lifted over the lowest of them, both in player heights."""
    height = box[3] - box[1]
    return (box[1] - ball[1]) / height, (max(feet) - feet[0]) / height


def overlap(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1, y1 = np.maximum(box[:2], boxes[:, :2]).T
    x2, y2 = np.minimum(box[2:], boxes[:, 2:]).T
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    return inter / ((box[2] - box[0]) * (box[3] - box[1]) + (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]) - inter)


def mark_relances(video: Path, typed: list[Typed], fps: float) -> list[Typed]:
    """`typed` with the attacks played as relances retyped "relance".

    ponytail: runs after the rules, so a touch right after a relance stays typed as its block.
    """
    attacks = [t for t in typed if t[3] == "attack"]
    if not attacks:
        return typed
    from ultralytics import YOLO

    model = YOLO(str(POSE_MODEL))
    cap = cv2.VideoCapture(str(video))
    reach = UNDER_PX * cap.get(cv2.CAP_PROP_FRAME_HEIGHT) / 720

    def boxes_at(frame: int) -> np.ndarray:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, image = cap.read()
        return model.predict(image, imgsz=1280, conf=0.25, verbose=False)[0].boxes.xyxy.cpu().numpy() if ok else np.empty((0, 4))

    relances = set()
    step = max(1, round(0.1 * fps))
    for frame, x, y, _, _ in attacks:
        boxes = boxes_at(frame)
        i = player_under((x, y), boxes, reach)
        if i is None:
            continue
        box = current = boxes[i]
        feet = [box[3]]
        for earlier in range(frame - step, frame - round(LIFT_S * fps) - 1, -step):
            candidates = boxes_at(earlier)
            if not len(candidates) or overlap(current, candidates).max() < 0.3:
                break
            current = candidates[overlap(current, candidates).argmax()]
            feet.append(current[3])
        above, lift = relance_cues((x, y), box, feet)
        if above <= ABOVE and lift < LIFT:
            relances.add(frame)
    cap.release()
    return [(f, x, y, "relance" if f in relances else kind, side) for f, x, y, kind, side in typed]


def read_rows(path: Path) -> list[list[int]]:
    with open(path) as f:
        return [[int(v) for v in row.values()] for row in csv.DictReader(f)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify the ball contacts of each rally.")
    parser.add_argument("contacts", type=Path, help="frame,x,y CSV from contacts.py")
    parser.add_argument("net", type=Path, help="Net crossing frames CSV from contacts.py")
    parser.add_argument("rallies", type=Path, help="start_frame,end_frame CSV from rallies.py")
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--net-x", type=float, help="Net plane in pixels, needed without --court")
    parser.add_argument("--court", type=Path, help="Court calibration JSON from court.py")
    parser.add_argument("--video", type=Path, help="The match video, to tell relances from attacks")
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    if args.court is None and args.net_x is None:
        parser.error("--net-x is needed without --court")

    calibration = Calibration.load(args.court) if args.court else None
    contacts = [tuple(r) for r in read_rows(args.contacts)]
    crossings = [r[0] for r in read_rows(args.net)]
    windows = served([tuple(r) for r in read_rows(args.rallies)], contacts, args.fps, calibration)
    typed = classify(contacts, crossings, windows, args.fps, args.net_x, calibration)
    if args.video:
        typed = mark_relances(args.video, typed, args.fps)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.contacts.stem.removesuffix('_contacts')}_actions.csv"
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([["frame", "x", "y", "type", "side"], *typed])
    print(f"{len(typed)} contacts -> {path}")


if __name__ == "__main__":
    main()
