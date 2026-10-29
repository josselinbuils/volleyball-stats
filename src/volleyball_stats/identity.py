"""Player identity: the player tracks linked into one identity per real player for the whole match,
numbered 1..N per team.

players.py's tracks break at occlusions and swap players where two cross (at the net, in the huddles
after a point). Each track is cut in the middle of every crowd episode, where its box lies under
another one, into segments that hold one player nearly always. A segment is described by a person
re-identification embedding (OSNet-AIN trained on MSMT17, whole box plus upper and lower halves)
averaged over its clearest boxes, then whitened within its team: teammates share the jersey and
differ in faint directions. Per team, segments are followed in time order and handed to identities
by an optimal assignment on the distance to each identity's prototype, under hard constraints: two
segments seen at the same time, or too far apart for the time between them, are never one player.
Identities on court at the first serve are numbered by zone (1 back right, 2 front right, 3 front
middle, 4 front left, 5 back left, 6 back middle), the later ones by first appearance; a rerun keeps
the numbers of the previous identities.csv. Inside a rally, where the tracks keep their player
through crowds, each track then holds one number. See benchmarks/identity/README.md for the numbers
behind the constants.

    uv run python -m volleyball_stats.identity outputs/VIDEO --video VIDEO [--squad N[,N]]

Reads players.csv, rallies.csv and actions.csv of a match run with --players and, when present,
identity_answers.json (the user's answers, hard constraints overriding the model), the previous
identities.csv, the embedding cache embeddings.npz and player_names.json (the names the user gave,
constraints too: one name one player). Writes identities.csv, identity_candidates.json and the
cache, and refreshes actions.csv's identity column: a rerun without new tracks takes seconds.
Jersey numbers, once read (4K footage), enter `identify` as `jerseys`: the same number is one
player, two numbers are two.
"""

import argparse
import csv
import json
from bisect import bisect_right
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np

from volleyball_stats.court import zone
from volleyball_stats.players import Row
from volleyball_stats.teams import SEEK, side_group

REID = Path("models/osnet_ain_x1_0_msmt17.pth")
REID_GDRIVE_ID = "1SigwBE6mPdqiJMqhuIY4aqC7--5CsMal"
REID_SIZE = (128, 256)
MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])
# Weight of the box halves' embeddings next to the whole box's; three 512-d parts.
HALF, DIM = 0.7, 3 * 512
# A track is in a crowd where another box covers CROWD of its box or more; crowd frames up to
# CROWD_GAP apart are one episode, cut in its middle.
CROWD, CROWD_GAP = 0.3, 5
# Up to CROPS boxes per segment are embedded, the clear ones (covered less than CLEAR) first.
CROPS, CLEAR = 12, 0.1
# Crops embedded per `describe` call, a multiple of its batch, as the frames are read.
CHUNK = 16 * 64
# Segments of CORE_S seconds or more build the identities, the shorter ones join them after.
CORE_S = 5.0
# A segment leans to its track's neighbouring pieces' identity by CONTINUITY.
CONTINUITY = 0.3
# Principal components of a team's segment embeddings kept, whitened.
WHITEN = 32
# Segments starting within BATCH frames of each other share out the free identities; a new
# identity costs a distance of NEW.
BATCH, NEW = 90, 0.9
# Identities whose longest unit is shorter than LONGEST_S are no identity: their segments, crowd
# pieces left over, get no number.
LONGEST_S = 10.0
# A segment starting LINK_GAP_S or less after another ended cannot be the same player when its feet
# are farther than a run at RUN_SPEED m/s plus RUN_REACH m (feet of half-hidden boxes jump).
LINK_GAP_S, RUN_SPEED, RUN_REACH = 3.0, 8.0, 2.0
# Uncertainty of a decision taken by a distance gap g: exp(-g / GAP_SCALE). A contact weighs as much
# as CONTACT_S seconds of play in the ranking of the questions; QUESTIONS of each kind are kept.
GAP_SCALE, CONTACT_S, QUESTIONS = 0.1, 10.0, 50
# The first serve's positions are read within SERVE_S of the first rally's start.
SERVE_S = 1.0
NAMES = "player_names.json"

Key = tuple[int, int]


@dataclass
class Segment:
    """A piece of a track between two crowd episodes, its team, its identity (0 for none) and the
    nearest other identity it could be (`runner_up`, 0 for none) with the confidence of the choice."""

    track: int
    frames: list[int]
    feet: list[tuple[float, float]]
    team: int = 0
    identity: int = 0
    runner_up: int = 0
    confidence: float = 1.0

    @property
    def start(self) -> int:
        return self.frames[0]

    @property
    def end(self) -> int:
        return self.frames[-1]


def covers(rows: list[Row]) -> dict[Key, float]:
    """Share of each (frame, track) box lying under the box of another track of the frame, the most
    covering one; boxes nobody covers are left out (0)."""
    by_frame: dict[int, list[Row]] = {}
    for r in rows:
        by_frame.setdefault(r.frame, []).append(r)
    out: dict[Key, float] = {}
    for frame, here in by_frame.items():
        b = np.array([r.box for r in here])
        area = np.maximum((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]), 1e-6)
        w = np.clip(np.minimum(b[:, None, 2], b[None, :, 2]) - np.maximum(b[:, None, 0], b[None, :, 0]), 0, None)
        h = np.clip(np.minimum(b[:, None, 3], b[None, :, 3]) - np.maximum(b[:, None, 1], b[None, :, 1]), 0, None)
        inter = w * h
        np.fill_diagonal(inter, 0)
        for r, c in zip(here, (inter / area[:, None]).max(axis=1)):
            if c > 0:
                out[r.frame, r.track] = float(c)
    return out


def split(rows: list[Row], cover: dict[Key, float]) -> list[Segment]:
    """Each track cut in the middle of each crowd episode, sorted by start."""
    by_track: dict[int, list[Row]] = {}
    for r in sorted(rows, key=lambda r: r.frame):
        by_track.setdefault(r.track, []).append(r)
    out = []
    for track, track_rows in by_track.items():
        episodes: list[list[int]] = []
        for r in track_rows:
            if cover.get((r.frame, track), 0.0) >= CROWD:
                if episodes and r.frame - episodes[-1][1] <= CROWD_GAP:
                    episodes[-1][1] = r.frame
                else:
                    episodes.append([r.frame, r.frame])
        cuts = [(a + b) // 2 for a, b in episodes]
        pieces: list[list[Row]] = [[]]
        for r in track_rows:
            while len(pieces) <= len(cuts) and r.frame > cuts[len(pieces) - 1]:
                pieces.append([])
            pieces[-1].append(r)
        out += [Segment(track, [r.frame for r in p], [r.court for r in p]) for p in pieces if p]
    return sorted(out, key=lambda s: (s.start, s.track))


def picks(segment: Segment, cover: dict[Key, float]) -> list[int]:
    """Frames of up to CROPS boxes spread over the segment, among its clear boxes when it has some,
    else among its least covered ones."""
    frames = [f for f in segment.frames if cover.get((f, segment.track), 0.0) < CLEAR]
    if not frames:
        frames = sorted(sorted(segment.frames, key=lambda f: cover.get((f, segment.track), 0.0))[:CROPS])
    return sorted({frames[i] for i in np.linspace(0, len(frames) - 1, min(CROPS, len(frames))).astype(int)})


def frames_at(video: Path, wanted: Iterable[int]) -> Iterator[tuple[int, np.ndarray]]:
    """The video's frames at the `wanted` indices in order, decoded through short gaps, seeking over
    long ones."""
    cap, position = cv2.VideoCapture(str(video)), 0
    for frame in sorted(set(wanted)):
        if frame - position > SEEK:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
            position = frame
        while position < frame:
            cap.grab()
            position += 1
        ok, image = cap.read()
        position += 1
        if not ok:
            break
        yield frame, image
    cap.release()


def load_reid(device: str, path: Path = REID):
    import torch

    from volleyball_stats.vendor.osnet_ain import osnet_ain_x1_0

    if not path.exists():
        import gdown

        path.parent.mkdir(parents=True, exist_ok=True)
        gdown.download(id=REID_GDRIVE_ID, output=str(path), quiet=True)
    state = {k.removeprefix("module."): v for k, v in torch.load(path, map_location="cpu", weights_only=True).items()}
    model = osnet_ain_x1_0(num_classes=state["classifier.weight"].shape[0], pretrained=False)
    model.load_state_dict(state)
    return model.to(device).eval()


def describe(crops: list[np.ndarray], model, device: str, batch: int = 64) -> np.ndarray:
    """Unit re-identification embedding of each BGR crop: the whole box, then its upper and lower
    halves weighted by HALF (teammates share the jersey, not the hair, shorts or shoes), each summed
    with its mirror image."""
    import torch

    def run(images: list[np.ndarray], size: tuple[int, int]) -> np.ndarray:
        x = np.stack([((cv2.cvtColor(cv2.resize(c, size), cv2.COLOR_BGR2RGB) / 255 - MEAN) / STD).transpose(2, 0, 1) for c in images])
        with torch.no_grad():
            t = torch.from_numpy(x.astype(np.float32)).to(device)
            f = (model(t) + model(torch.flip(t, dims=[3]))).cpu().numpy()
        return f / np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-9)

    out = []
    for i in range(0, len(crops), batch):
        part = [c if c.shape[0] >= 2 else np.repeat(c, 2, axis=0) for c in crops[i : i + batch]]
        upper = run([c[: c.shape[0] // 2] for c in part], (REID_SIZE[0], REID_SIZE[0]))
        lower = run([c[c.shape[0] // 2 :] for c in part], (REID_SIZE[0], REID_SIZE[0]))
        out.append(np.hstack([run(part, REID_SIZE), HALF * upper, HALF * lower]))
    vectors = np.concatenate(out) if out else np.empty((0, DIM))
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)


def embed(video: Path, rows: list[Row], segments: list[Segment], cover: dict[Key, float], cache: Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Unit embedding of each segment, the mean of its `picks` boxes', and the number of boxes it
    averages; read from `cache` for the segments it holds (same track, frames and first box), else
    computed and the cache rewritten.

    ponytail: a second decoding pass over the video, by OpenCV on the CPU at full size for the crops:
    on 4K footage 60% of the frames are picked and all decoded, 37 s for 2 min on the M4 Pro.
    ffmpeg's GPU decoding (decode.py) would need the picked frames selected before the pipe, 4K
    frames being 25 MB each.
    """
    # Boxes of the segments' first frames, the cache's keys; those of the picked frames on a miss.
    firsts = {(s.start, s.track) for s in segments}
    boxes = {(r.frame, r.track): r.box for r in rows if (r.frame, r.track) in firsts}
    keys = [(s.track, s.start, s.end, *boxes[s.start, s.track]) for s in segments]
    stored: dict[tuple, tuple[np.ndarray, float]] = {}
    if cache and cache.exists():
        data = np.load(cache)
        stored = {tuple(k): (v.astype(np.float32), float(n)) for k, v, n in zip(data["keys"].round(1).tolist(), data["vectors"], data["counts"])}
    keys = [tuple(np.round(k, 1).tolist()) for k in keys]
    missing = [k for k, key in enumerate(keys) if key not in stored]
    if missing:
        from volleyball_stats.ball import default_device

        device, wanted = default_device(), {}
        for k in missing:
            for f in picks(segments[k], cover):
                wanted.setdefault(f, []).append(k)
        picked = {(f, segments[k].track) for f, ks in wanted.items() for k in ks}
        boxes.update({(r.frame, r.track): r.box for r in rows if (r.frame, r.track) in picked})
        model, sums, counts = load_reid(device), np.zeros((len(segments), DIM)), np.zeros(len(segments))
        crops: list[np.ndarray] = []
        owners: list[int] = []

        def add(n: int) -> None:
            if n:
                np.add.at(sums, np.array(owners[:n]), describe(crops[:n], model, device))
                np.add.at(counts, np.array(owners[:n]), 1)
                del crops[:n], owners[:n]

        for frame, image in frames_at(video, wanted):
            for k in wanted[frame]:
                x1, y1, x2, y2 = (round(v) for v in boxes[frame, segments[k].track])
                crop = image[max(0, y1) : max(y2, y1 + 2), max(0, x1) : max(x2, x1 + 2)]
                if crop.size:
                    # A copy, not a view holding the whole frame: crops wait for a chunk to fill.
                    crops.append(crop.copy())
                    owners.append(k)
            if len(crops) >= CHUNK:
                add(CHUNK)
        add(len(crops))
        for k in missing:
            stored[keys[k]] = (sums[k] / counts[k] if counts[k] else np.zeros(DIM), float(counts[k]))
        if cache:
            np.savez_compressed(cache, keys=np.array(keys, float), vectors=np.array([stored[k][0] for k in keys], np.float16).reshape(len(keys), DIM),
                                counts=np.array([stored[k][1] for k in keys]))
    v = np.array([stored[k][0] for k in keys], float).reshape(len(keys), DIM)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9), np.array([max(1.0, stored[k][1]) for k in keys])


def cannot_links(segments: list[Segment], fps: float) -> list[set[int]]:
    """Per segment (sorted by start), the segments of its team it cannot be one player with: sharing
    a frame, or starting within LINK_GAP_S after it ended (or it after them), farther than a player
    runs. Teams are grouped apart, so segments of different teams are not listed."""
    out: list[set[int]] = [set() for _ in segments]
    frames = [set(s.frames) for s in segments]
    for i, a in enumerate(segments):
        for j in range(i + 1, len(segments)):
            b = segments[j]
            if b.start > a.end + LINK_GAP_S * fps:
                break
            if b.team != a.team:
                continue
            if b.start <= a.end:
                blocked = not frames[i].isdisjoint(frames[j])
            else:
                blocked = float(np.hypot(*np.subtract(a.feet[-1], b.feet[0]))) > RUN_SPEED * (b.start - a.end) / fps + RUN_REACH
            if blocked:
                out[i].add(j)
                out[j].add(i)
    return out


def whiten(v: np.ndarray, weights: np.ndarray, dims: int) -> np.ndarray:
    """Unit vectors of `v` centred and whitened by their weighted principal components, the first
    `dims` kept: teammates' embeddings differ in faint directions next to the shared jersey's."""
    x = v - weights @ v / weights.sum()
    # The principal axes from the weighted covariance, the size of a vector squared, not of the team.
    values, axes = np.linalg.eigh((x * (weights[:, None] / weights.sum())).T @ x)
    order = np.argsort(values)[::-1][:dims]
    scale, axes = np.sqrt(np.maximum(values[order], 0)), axes[:, order].T
    out = x @ axes.T / (scale + 1e-3)
    out = np.pad(out, ((0, 0), (0, dims - out.shape[1])))
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)


def follow(v: np.ndarray, weights: np.ndarray, starts: np.ndarray, cannot: list[set[int]], before: np.ndarray, order: np.ndarray, count: int | None = None, protos: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Identity of the segments of `order` (-1 for the others) and the identities' prototypes:
    segments taken by start, those starting within BATCH frames of each other together, each batch
    given the free identities (no segment assigned to it that a segment of the batch cannot be with)
    by an optimal one-to-one assignment on the distance to their prototype, CONTINUITY off for the
    identity of the piece of the same track just `before` (-1: none); a new identity costs NEW,
    none beyond `count`. `protos` fixes the prototypes, else each is the weighted mean of its
    segments so far."""
    from ultralytics.utils.ops import linear_sum_assignment

    label = np.full(len(v), -1)
    fixed = protos is not None
    sums = list(protos) if fixed else []
    blocked = [np.zeros(len(v), bool) for _ in sums]
    queue = order[np.argsort(starts[order], kind="stable")]
    first = 0
    while first < len(queue):
        last = int(np.searchsorted(starts[queue], starts[queue[first]] + BATCH, side="right"))
        batch, first = queue[first:last], last
        known = np.array([s / max(np.linalg.norm(s), 1e-9) for s in sums]).reshape(len(sums), v.shape[1])
        cost = np.full((len(batch), len(sums) + len(batch)), 9.0)
        for i, k in enumerate(batch):
            for c in range(len(sums)):
                if not blocked[c][k]:
                    cost[i, c] = 1 - known[c] @ v[k] - (CONTINUITY if before[k] >= 0 and label[before[k]] == c else 0.0)
            if count is None or len(sums) + i < count:
                cost[i, len(sums) + i] = NEW
        rows, cols = linear_sum_assignment(cost)
        for i, c in zip(rows, cols):
            if cost[i, c] >= 9.0:
                continue
            k = batch[i]
            if c >= len(sums):
                c = len(sums)
                sums.append(np.zeros(v.shape[1]))
                blocked.append(np.zeros(len(v), bool))
            label[k] = c
            blocked[c][list(cannot[k])] = True
            if not fixed:
                sums[c] = sums[c] + weights[k] * v[k]
    known = np.array([s / max(np.linalg.norm(s), 1e-9) for s in sums]).reshape(len(sums), v.shape[1])
    return label, known


def segment_teams(segments: list[Segment], windows: list[tuple[int, int]], left: list[int | None]) -> None:
    """Team of each segment: the team on its median side of the net in its rally (teams.side_group,
    team 1 on the left without rally sides), so a track swapping players across the net splits
    between the teams."""
    known = [(w, g - 1) for w, g in zip(windows, left) if g is not None]
    for s in segments:
        found = side_group(np.array(s.frames), np.array([x for x, _ in s.feet]), known)
        s.team = (int(np.median([x for x, _ in s.feet]) >= 0) if found is None else found) + 1


def group(v: np.ndarray, weights: np.ndarray, mass: np.ndarray, starts: np.ndarray, cannot: list[set[int]], must: Iterable[tuple[int, int]], before: np.ndarray, fps: float, count: int | None = None) -> np.ndarray:
    """Identity (0, 1, ...) of each segment of a team: the `must` pairs joined into units first;
    units of CORE_S seconds or more followed twice (`follow`), building the prototypes then with
    them fixed; then the other units, heaviest first, each to the nearest prototype it can join
    (CONTINUITY off per neighbouring piece of its track with it), else its own identity."""
    unit = np.arange(len(v))
    for a, b in must:
        unit[unit == unit[b]] = unit[a]
    unit = np.unique(unit, return_inverse=True)[1]
    n = unit.max() + 1 if len(v) else 0
    uv = np.zeros((n, v.shape[1]))
    np.add.at(uv, unit, v * weights[:, None])
    uv /= np.maximum(np.linalg.norm(uv, axis=1, keepdims=True), 1e-9)
    uw, umass = np.bincount(unit, weights, n), np.bincount(unit, mass, n)
    ustart = np.full(n, np.inf)
    np.minimum.at(ustart, unit, starts)
    ucannot: list[set[int]] = [set() for _ in range(n)]
    for k, others in enumerate(cannot):
        ucannot[unit[k]].update(unit[j] for j in others)
    ubefore = np.full(n, -1)
    after: list[list[int]] = [[] for _ in range(n)]
    for k, b in enumerate(before):
        if b >= 0 and unit[b] != unit[k]:
            ubefore[unit[k]] = unit[b]
            after[unit[b]].append(unit[k])
    core = np.nonzero((umass >= CORE_S * fps) | (np.bincount(unit, minlength=n) > 1))[0]
    label, protos = follow(uv, uw, ustart, ucannot, ubefore, core, count)
    label, protos = follow(uv, uw, ustart, ucannot, ubefore, core, count, protos)
    blocked = [np.zeros(n, bool) for _ in range(len(protos))]
    for u in np.nonzero(label >= 0)[0]:
        blocked[label[u]][list(ucannot[u])] = True
    for k in sorted(set(range(n)) - set(core[label[core] >= 0]), key=lambda k: -uw[k]):
        cost = 1 - protos @ uv[k] if len(protos) else np.empty(0)
        for nb in [ubefore[k], *after[k]]:
            if nb >= 0 and label[nb] >= 0:
                cost[label[nb]] -= CONTINUITY
        free = [c for c in np.argsort(cost) if not blocked[c][k]]
        if free:
            label[k] = free[0]
        elif count is None or len(protos) < count:
            label[k] = len(protos)
            protos = np.vstack([protos, uv[k]]) if len(protos) else uv[k][None]
            blocked.append(np.zeros(n, bool))
        else:
            continue
        blocked[label[k]][list(ucannot[k])] = True
    longest = np.zeros(len(protos))
    np.maximum.at(longest, label[label >= 0], umass[label >= 0])
    label[(label >= 0) & (longest[np.maximum(label, 0)] < LONGEST_S * fps)] = -1
    found = np.full(n, -1)
    found[label >= 0] = np.unique(label[label >= 0], return_inverse=True)[1]
    return found[unit]


def resolve(ref: dict, segments: list[Segment], before: list[tuple[int, int] | None]) -> list[int]:
    """Segments an answer refers to: {"track": T} all of track T's, {"track": T, "frame": F} the one
    of track T holding F (else the nearest), {"team": K, "identity": N} those numbered N in team K
    by the previous run (`before`: each segment's previous team and number)."""
    if "identity" in ref:
        return [k for k, b in enumerate(before) if b == (ref["team"], ref["identity"])]
    mine = [k for k, s in enumerate(segments) if s.track == ref["track"]]
    if ref.get("frame") is None or not mine:
        return mine
    frame = ref["frame"]
    return [min(mine, key=lambda k: max(segments[k].start - frame, frame - segments[k].end, 0))]


def previous_labels(segments: list[Segment], previous: dict[Key, tuple[int, int]] | None) -> list[tuple[int, int] | None]:
    """Previous (team, number) held by most of each segment's boxes, None for none."""
    out = []
    for s in segments:
        votes: dict[tuple[int, int], int] = {}
        for f in s.frames:
            if previous and (f, s.track) in previous:
                votes[previous[f, s.track]] = votes.get(previous[f, s.track], 0) + 1
        out.append(max(votes, key=votes.get) if votes else None)
    return out


def jersey_links(segments: list[Segment], jerseys: dict[Key, int]) -> tuple[list[list[int]], list[list[list[int]]]]:
    """"same" groups of segment indices and "different" pairs of such groups, from jersey numbers
    read on (frame, track) boxes: per team, the segments read with one number are one player, two
    numbers two."""
    read: dict[tuple[int, int], list[int]] = {}
    for k, s in enumerate(segments):
        numbers = {jerseys[f, s.track] for f in s.frames if (f, s.track) in jerseys}
        if len(numbers) == 1:
            read.setdefault((s.team, numbers.pop()), []).append(k)
    return links(read)


def name_links(segments: list[Segment], names: list[tuple[dict, str]], before: list[tuple[int, int] | None]) -> tuple[list[list[int]], list[list[list[int]]]]:
    """`jersey_links` for the names the user gave, (ref, name): one name one player, whatever the
    case, two names of a team two."""
    read: dict[tuple[int, str], list[int]] = {}
    for ref, name in names:
        for k in resolve(ref, segments, before):
            read.setdefault((segments[k].team, name.strip().casefold()), []).append(k)
    return links(read)


def links(read: dict[tuple[int, int | str], list[int]]) -> tuple[list[list[int]], list[list[list[int]]]]:
    """"same" groups and "different" pairs of groups from the segments of each (team, label)."""
    same = [g for g in read.values() if len(g) > 1]
    different = [[a, b] for (ta, na), a in read.items() for (tb, nb), b in read.items() if ta == tb and na < nb]
    return same, different


def number(segments: list[Segment], serve: int | None, fps: float, previous: dict[Key, tuple[int, int]] | None = None) -> None:
    """Numbers each segment's identity (its cluster in `identity` on entry, 0 for none) 1, 2, ...
    per team: the previous number of the identity sharing most boxes with a previous one, then the
    identities on court within SERVE_S of the `serve` frame by zone, then the others by first
    appearance, after the previous numbers."""
    clusters: dict[int, list[Segment]] = {}
    for s in segments:
        if s.identity:
            clusters.setdefault(s.identity, []).append(s)
    numbers: dict[int, int] = {}
    for team in sorted({s.team for s in segments}):
        mine = [c for c, members in clusters.items() if members[0].team == team]
        taken: set[int] = set()
        if previous:
            shared: dict[tuple[int, int], int] = {}
            for c in mine:
                for s in clusters[c]:
                    for f in s.frames:
                        old = previous.get((f, s.track))
                        if old and old[0] == team:
                            shared[c, old[1]] = shared.get((c, old[1]), 0) + 1
            for (c, old), _ in sorted(shared.items(), key=lambda kv: -kv[1]):
                if c not in numbers and old not in taken:
                    numbers[c] = old
                    taken.add(old)
        near: dict[int, tuple[int, tuple[float, float]]] = {}
        if serve is not None:
            for c in mine:
                for s in clusters[c]:
                    for f, xy in zip(s.frames, s.feet):
                        if abs(f - serve) <= SERVE_S * fps and (c not in near or abs(f - serve) < near[c][0]):
                            near[c] = (abs(f - serve), xy)
        rest = [c for c in mine if c not in numbers]
        starters = sorted((c for c in rest if c in near), key=lambda c: (zone(*near[c][1]), near[c][1][1]))
        later = sorted((c for c in rest if c not in near), key=lambda c: min(s.start for s in clusters[c]))
        # A number freed by a merge stays retired: new identities come after the previous ones.
        numbers.update(zip(starters + later, range(max(taken, default=0) + 1, len(mine) + max(taken, default=0) + 1)))
    for s in segments:
        s.identity = numbers.get(s.identity, 0)


def doubts(segments: list[Segment], v: np.ndarray, weights: np.ndarray, cannot: list[set[int]], fps: float, contacts: dict[int, int]) -> dict:
    """identity_candidates.json's content, each list ranked by impact, (seconds + CONTACT_S per
    contact) x exp(-gap / GAP_SCALE), and each segment's `runner_up` and `confidence`
    (1 - exp(-gap / GAP_SCALE)):
    - segments: the segments, numbered or not (identity null), whose identity is least sure, with
      the nearest other identity they could join (`runner_up`); `gap`: their distance to it minus
      to the rest of their own identity (NEW without one);
    - merges: the pairs of identities of a team never seen together that might be one player;
      `gap`: their prototypes' distance minus NEW.
    `v` holds the segments' embeddings in their team's whitened space."""
    keys = sorted({(s.team, s.identity) for s in segments if s.identity})
    index = {key: c for c, key in enumerate(keys)}
    key_of = np.array([index.get((s.team, s.identity), -1) for s in segments], int)
    member = np.zeros((len(segments), len(keys)))
    member[key_of >= 0, key_of[key_of >= 0]] = 1
    sums = member.T @ (v * weights[:, None])
    protos = sums / np.maximum(np.linalg.norm(sums, axis=1, keepdims=True), 1e-9)
    # Identities a segment cannot join, and pairs of identities seen together.
    blocked = np.zeros((len(segments), len(keys)), bool)
    together = np.zeros((len(keys), len(keys)), bool)
    for k, others in enumerate(cannot):
        for j in others:
            if key_of[j] >= 0:
                blocked[k, key_of[j]] = True
                if key_of[k] >= 0:
                    together[key_of[k], key_of[j]] = True
    seconds = np.array([len(s.frames) / fps for s in segments])
    touches = np.array([contacts.get(k, 0) for k in range(len(segments))])

    def entry(gap: float, size: float, extra: dict) -> dict:
        u = float(np.exp(-max(gap, 0.0) / GAP_SCALE))
        return {**extra, "gap": round(gap, 3), "confidence": round(1 - u, 3), "impact": round(size * u, 2)}

    out: dict[str, list] = {"segments": [], "merges": []}
    for k, s in enumerate(segments):
        own = keys.index((s.team, s.identity)) if s.identity else None
        others = [c for c in range(len(keys)) if c != own and keys[c][0] == s.team and not blocked[k, c]]
        if not others:
            s.runner_up, s.confidence = 0, 1.0
            continue
        rest = sums[own] - weights[k] * v[k] if own is not None else np.zeros(v.shape[1])
        inside = float(1 - v[k] @ rest / np.linalg.norm(rest)) if np.linalg.norm(rest) > 1e-6 else NEW
        best = min(others, key=lambda c: 1 - v[k] @ protos[c])
        found = entry(float(1 - v[k] @ protos[best]) - inside, seconds[k] + CONTACT_S * touches[k], {
            "track": s.track, "start_frame": s.start, "end_frame": s.end, "team": s.team, "identity": s.identity or None,
            "runner_up": keys[best][1], "seconds": round(float(seconds[k]), 1), "contacts": int(touches[k]),
        })
        s.runner_up, s.confidence = keys[best][1], found["confidence"]
        out["segments"].append(found)
    longest = {key: max((s for s in segments if (s.team, s.identity) == key), key=lambda s: len(s.frames)) for key in keys}
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            if keys[a][0] != keys[b][0] or together[a, b]:
                continue
            sizes = [(float(seconds @ member[:, c]), int(touches @ member[:, c])) for c in (a, b)]
            small = min(sizes)
            out["merges"].append(entry(float(1 - protos[a] @ protos[b]) - NEW, small[0] + CONTACT_S * small[1], {
                "team": keys[a][0], "identities": [keys[a][1], keys[b][1]],
                "seconds": [round(x, 1) for x, _ in sizes], "contacts": [t for _, t in sizes],
                "examples": [{"track": longest[keys[c]].track, "start_frame": longest[keys[c]].start, "end_frame": longest[keys[c]].end} for c in (a, b)],
            }))
    for kind in out:
        out[kind] = sorted(out[kind], key=lambda q: -q["impact"])[:QUESTIONS]
    return out


def hold(segments: list[Segment], windows: list[tuple[int, int]]) -> list[Segment]:
    """The segments cut at the rallies' ends, each track holding one number per team inside a rally:
    the number of most of its frames there, unless a track seen at the same time in the rally holds
    it with more frames (then the track's next one, else none). Inside a rally the tracks keep their
    player through crowds: a segment's number changing there is wrong."""
    edges = sorted({a for a, _ in windows} | {b + 1 for _, b in windows})
    starts = [a for a, _ in windows]
    parts = []
    rallies: dict[tuple[int, int], list[Segment]] = {}
    for s in segments:
        key = np.searchsorted(edges, s.frames, side="right")
        for idx in np.split(np.arange(len(s.frames)), np.nonzero(np.diff(key))[0] + 1):
            p = replace(s, frames=[s.frames[i] for i in idx], feet=[s.feet[i] for i in idx])
            parts.append(p)
            w = bisect_right(starts, p.start) - 1
            if p.identity and w >= 0 and p.end <= windows[w][1]:
                rallies.setdefault((w, p.team), []).append(p)
    for inside in rallies.values():
        mass: dict[tuple[int, int], int] = {}
        span: dict[int, tuple[int, int]] = {}
        for p in inside:
            mass[p.track, p.identity] = mass.get((p.track, p.identity), 0) + len(p.frames)
            lo, hi = span.get(p.track, (p.start, p.end))
            span[p.track] = (min(lo, p.start), max(hi, p.end))
        chosen: dict[int, int] = {}
        for t, i in sorted(mass, key=mass.get, reverse=True):
            if t not in chosen and not any(j == i and span[u][0] <= span[t][1] and span[t][0] <= span[u][1] for u, j in chosen.items()):
                chosen[t] = i
        for p in inside:
            p.identity = chosen.get(p.track, 0)
    return parts


def identify(
    video: Path,
    rows: list[Row],
    windows: list[tuple[int, int]],
    left: list[int | None],
    fps: float,
    cache: Path | None = None,
    answers: dict | None = None,
    previous: dict[Key, tuple[int, int]] | None = None,
    squad: tuple[int, int] | None = None,
    contacts: Iterable[Key] = (),
    jerseys: dict[Key, int] | None = None,
    names: list[tuple[dict, str]] | None = None,
) -> tuple[list[Segment], dict]:
    """The segments of the players' tracks with their team, identity number (0 for none) and doubt,
    and the doubts' questions (`doubts`). `answers` (identity_answers.json, segments referred to as
    `resolve` says) override the model: "not_player" segments get no team nor identity, each "same" group is one
    player, each "different" group's members are different players; `previous` holds a previous
    run's (team, number) by (frame, track); `squad` the number of players of each team, when known;
    `contacts` the (frame, track) of the attributed contacts, for the questions' ranking; `jerseys`
    the jersey numbers read by (frame, track), as constraints (`jersey_links`), and `names` the
    names the user gave, (ref, name), likewise (`name_links`)."""
    answers = answers or {}
    cover = covers(rows)
    segments = split(rows, cover)
    before = previous_labels(segments, previous)
    dropped = {k for ref in answers.get("not_player", []) for k in resolve(ref, segments, before)}
    removed = [s for k, s in enumerate(segments) if k in dropped]
    segments, before = [s for k, s in enumerate(segments) if k not in dropped], [b for k, b in enumerate(before) if k not in dropped]
    segment_teams(segments, windows, left)
    same = [[k for ref in group for k in resolve(ref, segments, before)] for group in answers.get("same", [])]
    different = [[resolve(ref, segments, before) for ref in group] for group in answers.get("different", [])]
    if jerseys:
        read_same, read_different = jersey_links(segments, jerseys)
        same, different = same + read_same, different + read_different
    if names:
        named_same, named_different = name_links(segments, names, before)
        same, different = same + named_same, different + named_different
    for group_ in same:
        for k in group_:
            segments[k].team = segments[group_[0]].team
    v, weights = embed(video, rows, segments, cover, cache)
    cannot = cannot_links(segments, fps)
    for group_ in same:
        for k in group_:
            cannot[k].difference_update(group_)
    for group_ in different:
        for a in range(len(group_)):
            for b in range(a + 1, len(group_)):
                for x in group_[a]:
                    for y in group_[b]:
                        cannot[x].add(y)
                        cannot[y].add(x)
    last: dict[int, int] = {}
    pieces = []
    for k, s in enumerate(segments):
        if s.track in last:
            pieces.append((last[s.track], k))
        last[s.track] = k
    labels, wv = np.full(len(segments), -1), np.zeros((len(segments), WHITEN))
    for team in sorted({s.team for s in segments}):
        idx = np.array([k for k, s in enumerate(segments) if s.team == team])
        local = {k: i for i, k in enumerate(idx)}
        must = [(local[g[0]], local[k]) for g in same for k in g[1:] if g[0] in local and k in local]
        earlier = np.full(len(idx), -1)
        for a, b in pieces:
            if a in local and b in local:
                earlier[local[b]] = local[a]
        mass = np.array([len(segments[k].frames) for k in idx], float)
        count = squad[team - 1] if squad and team in (1, 2) else None
        wv[idx] = whiten(v[idx], weights[idx], WHITEN)
        local_cannot = [{local[j] for j in cannot[k] if j in local} for k in idx]
        found = group(wv[idx], weights[idx], mass, np.array([segments[k].start for k in idx]), local_cannot, must, earlier, fps, count)
        labels[idx] = np.where(found >= 0, found + labels.max() + 1, -1)
    for s, label in zip(segments, labels):
        s.identity = int(label) + 1
    number(segments, windows[0][0] if windows else None, fps, previous)
    touches: dict[int, int] = {}
    for frame, track in contacts:
        found = resolve({"track": track, "frame": frame}, segments, before)
        if found:
            touches[found[0]] = touches.get(found[0], 0) + 1
    found = doubts(segments, wv, weights, cannot, fps, touches)
    return sorted(hold(segments, windows) + removed, key=lambda s: (s.start, s.track)), found


def write_identities(path: Path, segments: list[Segment]) -> None:
    """identities.csv: one row per segment, `start_frame`..`end_frame` of `track`, identity 0 for
    none."""
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows([
            ["track", "start_frame", "end_frame", "team", "identity", "runner_up", "confidence"],
            *([s.track, s.start, s.end, s.team, s.identity, s.runner_up or "", s.confidence] for s in sorted(segments, key=lambda s: (s.track, s.start))),
        ])


def read_identities(path: Path) -> list[tuple[int, int, int, int, int]]:
    """identities.csv rows: track, start frame, end frame, team, identity."""
    with open(path) as f:
        return [tuple(int(r[k]) for k in ("track", "start_frame", "end_frame", "team", "identity")) for r in csv.DictReader(f)]


def lookup(table: list[tuple[int, int, int, int, int]], track: int | None, frame: int) -> tuple[int, int] | None:
    """(team, identity) of `track` at `frame`: its segment holding the frame, else the nearest one;
    None for no segment or one without identity."""
    mine = [r for r in table if r[0] == track]
    if not mine:
        return None
    _, _, _, team, identity = min(mine, key=lambda r: max(r[1] - frame, frame - r[2], 0))
    return (team, identity) if identity else None


def read_names(match: Path) -> list[dict]:
    """player_names.json's entries: a player's `ref` (a piece of track, as answers refer to it), the
    `name` and `jersey` number the user gave them, either None."""
    path = match / NAMES
    return json.loads(path.read_text())["players"] if path.exists() else []


def named(table: list[tuple[int, int, int, int, int]], names: list[dict]) -> dict[tuple[int, int], dict]:
    """The name and jersey number of each (team, identity) of identities.csv's `table` that the user
    named, the first entry winning."""
    by_track: dict[int, list] = {}
    for r in table:
        by_track.setdefault(r[0], []).append(r)
    out: dict[tuple[int, int], dict] = {}
    for e in names:
        found = lookup(by_track.get(e["ref"]["track"], []), e["ref"]["track"], e["ref"]["frame"])
        if found and found not in out:
            out[found] = {"name": e.get("name") or None, "jersey": e.get("jersey")}
    return out


def run(match: Path, video: Path, rows: list[Row], windows: list[tuple[int, int]], left: list[int | None], fps: float, squad: tuple[int, int] | None = None, contacts: Iterable[Key] = ()) -> list[tuple[int, int, int, int, int]]:
    """`identify` with the match folder's answers, previous numbers and embedding cache; writes
    identities.csv and identity_candidates.json and returns identities.csv's rows."""
    answers_path, path = match / "identity_answers.json", match / "identities.csv"
    answers = json.loads(answers_path.read_text()) if answers_path.exists() else None
    names = [(e["ref"], e["name"]) for e in read_names(match) if e.get("name")]
    previous = None
    if path.exists():
        frames: dict[int, list[int]] = {}
        for r in rows:
            frames.setdefault(r.track, []).append(r.frame)
        previous = {}
        for track, start, end, team, number_ in read_identities(path):
            if number_:
                previous.update(((f, track), (team, number_)) for f in frames.get(track, []) if start <= f <= end)
    segments, found = identify(video, rows, windows, left, fps, match / "embeddings.npz", answers, previous, squad, contacts, names=names)
    write_identities(path, segments)
    (match / "identity_candidates.json").write_text(json.dumps(found, indent=1) + "\n")
    return read_identities(path)


def parse_squad(text: str) -> tuple[int, int]:
    """Players per team from "N" (both teams) or "N1,N2"."""
    parts = [int(p) for p in text.split(",")]
    if len(parts) not in (1, 2):
        raise ValueError(text)
    return parts[0], parts[-1]


def rerun(match: Path, video: Path, squad: tuple[int, int] | None = None) -> list[tuple[int, int, int, int, int]]:
    """`run` on a match folder run with --players, its actions.csv's identity column refreshed."""
    from volleyball_stats.attribution import read_players

    with open(match / "rallies.csv") as f:
        rallies = list(csv.DictReader(f))
    windows = [(int(r["start_frame"]), int(r["end_frame"])) for r in rallies]
    left = [int(r["left"]) if r.get("left") else None for r in rallies]
    actions = match / "actions.csv"
    with open(actions) as f:
        typed = list(csv.DictReader(f))
    fps = cv2.VideoCapture(str(video)).get(cv2.CAP_PROP_FPS)
    rows = read_players(match / "players.csv")
    table = run(match, video, rows, windows, left, fps, squad, [(int(r["frame"]), int(r["track"])) for r in typed if r.get("track")])
    for r in typed:
        found = lookup(table, int(r["track"]), int(r["frame"])) if r.get("track") else None
        r["identity"] = "" if found is None or str(found[0]) != r.get("team") else found[1]
    with open(actions, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*[k for k in typed[0] if k != "identity"], "identity"] if typed else ["identity"])
        writer.writeheader()
        writer.writerows(typed)
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description="Link the player tracks into one identity per player for the whole match.")
    parser.add_argument("match", type=Path, help="The match's outputs directory (outputs/VIDEO), run with --players")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--squad", type=parse_squad, help="Players per team, N or N1,N2 (team 1 is on the left at the first rally)")
    args = parser.parse_args()

    table = rerun(args.match, args.video, args.squad)
    counts = {team: len({r[4] for r in table if r[3] == team and r[4]}) for team in (1, 2)}
    print(f"{len(table)} segments, identities: team 1 {counts[1]}, team 2 {counts[2]} -> {args.match / 'identities.csv'}")


if __name__ == "__main__":
    main()
