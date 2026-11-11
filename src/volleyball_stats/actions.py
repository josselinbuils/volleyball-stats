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
import json
from pathlib import Path

import numpy as np

from volleyball_stats import decode, files
from volleyball_stats.court import Calibration

# Relances (free balls): a third touch played without attacking, ball not above the player's head
# and feet on the floor; an attack is hit above the head, often jumping. Measured on the player's
# box from a pose model, whose boxes leave out the blurred hitting arm: on the labelled clips the
# ball is above the box top for 21 of 22 attacks, at or below it for the relances.
# On the first ASPOM match's answers (4K) the feet barely tell (the boxes' feet jump): the ball at
# most ABOVE over the head takes 6 of the owner's 8 relances and 2 of 24 attacks of the checked
# rallies, against none with ABOVE 0 and LIFT 0.1; the school clips' labels score the same.
POSE_MODEL = Path("models/yolo11m-pose.pt")
ABOVE, LIFT = 0.03, 0.6
# With the ball's 3D place (`by_flight`), an attack leaves from ATTACK_M or higher and rising at under
# RISE_MS: first ASPOM match's checked rallies, each set held out, 137 -> 144 of 169 attacks and relances.
ATTACK_M, RISE_MS = 2.1, 6.0
# A set that crosses the net within SET_OVER_S of its touch is a hit, not a set: both ASPOM matches' checked rallies, the
# sets over the net of 1.4 s or more are sets (the owner's), those under are attacks or relances (6 of 22 and 11 of 43 fixed, 0 and 3 broken).
SET_OVER_S = 1.3
# The player under the ball is within UNDER_PX of it horizontally (at 720p); their feet are followed
# back LIFT_S seconds by box overlap.
UNDER_PX = 15
LIFT_S = 1.0

# ponytail: rallies.py starts a window 1-7 frames after the serve contact, so windows start this
# many seconds earlier; drop it once rallies.py starts at the contact.
LEAD_S = 0.33
# A window may open up to SERVE_BEFORE_S after its serve contact (first ASPOM match, 4K 50 fps: 21 of
# the 43 labelled rallies over LEAD_S, up to 1.0 s): `serve_starts` moves it to the serve.
SERVE_BEFORE_S = 1.0
# A window may open later on a serve the ball's run missed (`late_serves`): up to LATE_MAX_S after the
# contact whose ball crosses the net within LATE_FLIGHT_S (0.6-1.0 s on the first ASPOM match), from
# over LATE_DEPTH of the way from the net to an end line, since the referee's go; without a go heard,
# up to LATE_NO_GO_S.
LATE_MAX_S, LATE_FLIGHT_S, LATE_DEPTH, LATE_NO_GO_S = 10.0, 1.2, 0.7, 2.0
# Pixels at the school court's scale (rallies.COURT_PX) within which a contact after a serve, on its
# side, is the server catching a bounce: 7-334 px at 4K on the first match (a scale of 2.16), 56 px
# on the school match; a false contact in the serve's flight lies 570 px or more from the server.
BOUNCE_PX = 200
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
# Court x (meters from the net) under which a contact is at the net: the camera stands in the net
# plane, so a ball at the net projects there whatever its height, and a landing there fell at the
# foot of the net.
NET_M = 1.0
# Touches in a row by one player from which the ball is dead, held or bounced (before a serve, say):
# nobody plays it twice running. ponytail: from 2 examples; runs of 2 are mostly attribution errors
# (71-83% right), set it on labelled matches.
DEAD_RUN = 3
# A window with this many floor contacts and no player touch is no rally (`no_play`).
IDLE_FLOORS = 2
NO_CROSSING_S = 3.0
# A ball bounced this many times in a window is played with, not in a rally: 31 in the false windows of both ASPOM matches,
# at most 13 in a real one (its dead ball's).
BOUNCED_FLOORS = 20

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


def behind_end_line(calibration: Calibration, x: float, y: float) -> bool:
    """Whether the contact at image (x, y) is past an end line, where the server stands."""
    return abs(calibration.to_court(np.array([[x, y]]))[0, 0]) > 9.0


def classify_rally(contacts: list[Contact], crossings: list[int], fps: float, net_x: float, calibration: Calibration | None = None) -> list[Typed]:
    """(frame, x, y, type, side) of a rally's contacts, in frame order. A touch over NET_M from the
    net on the other side of the previous touch (blocks aside) follows a crossing, seen or not."""
    out: list[Typed] = []
    touches, crossed, blocked, attack, dead, thrown, unseen, previous = 0, 0, False, None, False, 0, 0, None
    # The server's bounces behind the end line before the serve: the ball is not dead yet.
    bounces = 0
    # Each contact's count of crossings before it.
    crossed_at: list[int] = []
    contacts = sorted(contacts)
    for frame, x, y in contacts:
        now = sum(c <= frame for c in crossings) + unseen
        if len(out) == bounces and not now and in_court(calibration, x, y):
            # Counted as after a crossing that was no serve's.
            thrown = 1
        now += thrown
        side = "left" if x < net_u(calibration, net_x, y) else "right"
        away = calibration is not None and abs(calibration.to_court(np.array([[x, y]]))[0, 0]) > NET_M
        if previous and previous[1] == now and previous[0] != side and away:
            # A crossing the ball track missed.
            unseen += 1
            now += 1
        if now > crossed:
            touches, crossed = 0, now
        if len(out) == bounces and not now and not dead and on_floor(calibration, x, y, False) and behind_end_line(calibration, x, y):
            kind, bounces = "floor", bounces + 1
        elif dead or on_floor(calibration, x, y, frame == contacts[-1][0]):
            kind, dead = "floor", True
        elif len(out) == bounces and not crossed:
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
        previous = previous if kind in ("block", "floor") else (side, now)
        out.append((frame, x, y, kind, side))
        crossed_at.append(now)
    # A dig that sends the ball straight to the other side is an attack; a rally's first contact
    # typed dig receives a serve nobody saw.
    for k, (a, b) in enumerate(zip(out, out[1:])):
        if k and a[3] == "dig" and (crossed_at[k + 1] > crossed_at[k] or b[4] != a[4]):
            out[k] = (*a[:3], "attack", a[4])
        # A serve the ball bounces after behind the same end line, uncrossed, was the server catching it.
        if a[3] == "serve" and b[3] == "floor" and crossed_at[k + 1] == crossed_at[k] and b[4] == a[4] and behind_end_line(calibration, b[1], b[2]):
            out[k] = (*a[:3], "floor", a[4])
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


def serve_starts(
    rallies: list[tuple[int, int]], contacts: list[Contact], crossings: list[int], fps: float, net_x: float, calibration: Calibration | None = None, scale: float = 1.0
) -> list[tuple[int, int]]:
    """`rallies` with each one whose contacts, from SERVE_BEFORE_S before it and after the previous
    one's end, open on a serve before its LEAD_S starting LEAD_S after that serve, where a window
    found by the ball starts."""
    lead, before = round(LEAD_S * fps), round(SERVE_BEFORE_S * fps)
    out: list[tuple[int, int]] = []
    for start, end in rallies:
        since = max(start - before, out[-1][1] + 1 if out else 0)
        typed = classify_rally([c for c in contacts if since <= c[0] <= end], [c for c in crossings if since <= c <= end], fps, net_x, calibration)
        # The serving side touching it again near the server before it crosses: the server bounced
        # the ball first (farther, a false contact in the serve's flight).
        bounced = len(typed) > 1 and typed[1][3] == "net" and np.hypot(typed[1][1] - typed[0][1], typed[1][2] - typed[0][2]) < BOUNCE_PX * scale
        if typed and typed[0][3] == "serve" and typed[0][0] < start - lead and not bounced:
            start = typed[0][0] + lead
        out.append((start, end))
    return out


def late_serves(
    rallies: list[tuple[int, int]], contacts: list[Contact], crossings: list[int], whistle_times: list[tuple[float, float]], fps: float, net_x: float, calibration: Calibration
) -> list[tuple[int, int]]:
    """`rallies` with each one opening after its serve starting LEAD_S after it: the serve is the
    contact deep behind the first crossing since the previous window and the referee's go."""
    lead = round(LEAD_S * fps)
    ends = calibration.to_image(np.array([[-9.0, 0.0], [9.0, 0.0]]))[:, 0]
    onsets = [w[0] * fps for w in whistle_times]
    out: list[tuple[int, int]] = []
    for start, end in rallies:
        since = out[-1][1] + 1 if out else 0
        go = [o for o in onsets if since <= o < start]
        since = max(since, start - LATE_MAX_S * fps, go[-1] if go else start - LATE_NO_GO_S * fps)

        def serve_before(crossing: int) -> int | None:
            sent = [c for c in contacts if since <= c[0] < crossing and crossing - c[0] <= LATE_FLIGHT_S * fps]
            if not sent:
                return None
            frame, x, y = max(sent)
            return frame if (x - net_x) / (ends[int(x > net_x)] - net_x) >= LATE_DEPTH and not on_floor(calibration, x, y, False) else None

        serves = [f for f in (serve_before(c) for c in crossings if since < c <= start + fps) if f is not None]
        # A window already opening on a serve stays: an earlier one is a ball thrown over the net.
        if serves and not any(f >= start - lead for f in serves):
            start = serves[0] + lead
        out.append((start, end))
    return out


def classify(contacts: list[Contact], crossings: list[int], rallies: list[tuple[int, int]], fps: float, net_x: float, calibration: Calibration | None = None) -> list[Typed]:
    """Typed contacts of every rally; contacts outside the rallies are dropped. A contact in two
    windows, the next one's lead overlapping, stays the first's: answers name a touch by its frame."""
    out: list[Typed] = []
    for start, end in rallies:
        start -= round(LEAD_S * fps)
        inside = [c for c in contacts if start <= c[0] <= end]
        taken = {t[0] for t in out}
        out += [t for t in classify_rally(inside, [c for c in crossings if start <= c <= end], fps, net_x, calibration) if t[0] not in taken]
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


def no_play(typed: list[Typed], rallies: list[int | None], windows: list[tuple[int, int]] | None = None, crossings: list[int] | None = None, fps: float = 0.0) -> set[int]:
    """The rallies whose contacts are IDLE_FLOORS floor contacts or more and no player touch: the
    next server bouncing the ball, a ball rolled back (first ASPOM match: the 2 such windows of
    50:00-60:00, labelled no rally, and none other on the match); `rallies` holds each contact's.
    With the windows, also those with no player touch at all and those over NO_CROSSING_S with no
    crossing: a serve into the net is over before that (at most 1.6 s, the 2 longer false). A window
    with touches and no serve stays: the server out of view (second ASPOM match: 7 such rallies, 3 false)."""
    found: dict[int, list[str]] = {}
    for t, k in zip(typed, rallies):
        if k is not None:
            found.setdefault(k, []).append(t[3])
    idle = {k for k, kinds in found.items() if kinds.count("floor") >= IDLE_FLOORS and set(kinds) <= {"floor", "net"} or kinds.count("floor") >= BOUNCED_FLOORS}
    if windows is None:
        return idle
    lead = round(LEAD_S * fps)
    for k, (start, end) in enumerate(windows):
        crossed = any(start - lead <= c <= end for c in crossings or [])
        if not set(found.get(k, [])) - {"floor", "net"} or (not crossed and (end - start) / fps >= NO_CROSSING_S):
            idle.add(k)
    return idle


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


def mark_relances(video: Path, typed: list[Typed], fps: float, cache: Path | None = None) -> list[Typed]:
    """`typed` with the attacks played as relances retyped "relance"; the pose boxes of each frame
    looked at kept in `cache` (JSON, by frame) for the next runs.

    ponytail: runs after the rules, so a touch right after a relance stays typed as its block.
    """
    attacks = [t for t in typed if t[3] == "attack"]
    if not attacks:
        return typed
    kept = json.loads(cache.read_text()) if cache and cache.exists() else {}
    model, fresh = None, False
    reach = UNDER_PX * decode.size(video)[1] / 720
    # The frames an attack may look at, decoded in one pass: one ffmpeg a frame cost 0.7 s each in 4K.
    images: dict[int, np.ndarray] = {}

    def boxes_at(frame: int) -> np.ndarray:
        nonlocal model, fresh
        if str(frame) not in kept:
            if model is None:
                from ultralytics import YOLO

                model = YOLO(str(POSE_MODEL))
            image = images.get(frame)
            found = model.predict(image, imgsz=1280, conf=0.25, verbose=False)[0].boxes.xyxy.cpu().numpy() if image is not None else np.empty((0, 4))
            kept[str(frame)], fresh = np.round(found, 1).tolist(), True
        return np.array(kept[str(frame)], dtype=float).reshape(-1, 4)

    relances = set()
    step = max(1, round(0.1 * fps))
    for frame, x, y, _, _ in attacks:
        images.clear()
        images.update(decode.frames_at(video, [f for f in range(frame, frame - round(LIFT_S * fps) - 1, -step) if f >= 0 and str(f) not in kept]))
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
    if cache and fresh:
        files.write_text(cache, json.dumps(kept, separators=(",", ":")))
    return [(f, x, y, "relance" if f in relances else kind, side) for f, x, y, kind, side in typed]


def by_flight(typed: list[Typed], places: dict[int, np.ndarray], fps: float, longest: float = 2.2, gravity: float = 9.81) -> list[Typed]:
    """`typed` with the attacks and relances retyped from the ball's 3D `places` by frame: how high
    it leaves and how fast it rises until the next contact, which is under `longest` seconds away;
    those with no such flight stay. A set sent over the net within SET_OVER_S is one too, an attack when its flight is unknown."""
    out = list(typed)
    for k, (frame, x, y, kind, side) in enumerate(typed):
        if kind not in ("attack", "relance", "set") or k + 1 == len(typed):
            continue
        after = typed[k + 1][0]
        seconds = (after - frame) / fps
        if kind == "set":
            if typed[k + 1][4] == side or seconds > SET_OVER_S:
                continue
            out[k] = (frame, x, y, "attack", side)
        if frame in places and after in places and 0 < seconds <= longest:
            rise = (places[after][2] - places[frame][2] + gravity * seconds**2 / 2) / seconds
            out[k] = (frame, x, y, "attack" if places[frame][2] >= ATTACK_M and rise <= RISE_MS else "relance", side)
    return out


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
