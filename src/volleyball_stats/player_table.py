"""players.csv as numpy columns, kept beside it once read (`CACHE`): the review, the pages and the pipeline read it again
and again, 3 M rows parsed in 3-11 s, loaded in 0.05 s (18 Nov)."""

import itertools
import warnings
from pathlib import Path

import numpy as np

from volleyball_stats import files, jobs

COLUMNS = ("frame", "track", "team", "x1", "y1", "x2", "y2", "conf", "feet_x", "feet_y", "court_x", "court_y")
# The decimals players.write_csv keeps: the numbers stored whole (half the room of floats), back the same as parsed.
SCALES = {"x1": 10, "y1": 10, "x2": 10, "y2": 10, "conf": 1000, "feet_x": 10, "feet_y": 10, "court_x": 100, "court_y": 100}
CACHE = "players.npz"
CHUNK_LINES = 200_000


def read(path: Path, share: jobs.Share = jobs.quiet) -> dict[str, np.ndarray]:
    """`path`'s columns: frame and track as ints, team as text, the rest as floats; from the cache beside it when made
    from this very file, else parsed (the share read told as it goes) and cached. ValueError for other columns or a
    blank number."""
    cache = path.with_name(CACHE) if path.name == "players.csv" else path.with_suffix(".npz")
    stat = path.stat()
    stamp = np.array([stat.st_size, stat.st_mtime_ns], dtype=np.int64)
    try:
        with np.load(cache) as kept:
            if np.array_equal(kept["stamp"], stamp):
                table = unpacked(kept)
                share(1.0)
                return table
    except (OSError, ValueError, KeyError):
        pass
    table = parsed(path, share)
    try:
        with files.replacing(cache, "wb") as f:
            np.savez(f, stamp=stamp, **packed(table))
    except OSError:
        # ponytail: a read-only or full disk only loses the cache; a warning when that happens would say why it is slow.
        pass
    return table


def parsed(path: Path, share: jobs.Share = jobs.quiet) -> dict[str, np.ndarray]:
    """`path`'s columns parsed, CHUNK_LINES at a time."""
    size, done, numbers, teams = max(path.stat().st_size, 1), 0, [], []
    with open(path) as f, warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        header = f.readline()
        if tuple(header.strip().split(",")) != COLUMNS:
            raise ValueError(f"{path}: not players.csv's columns")
        done += len(header)
        while lines := list(itertools.islice(f, CHUNK_LINES)):
            numbers.append(np.loadtxt(lines, delimiter=",", usecols=(0, 1, *range(3, 12)), ndmin=2))
            teams.append(np.loadtxt(lines, delimiter=",", usecols=(2,), dtype=str, ndmin=1))
            done += sum(map(len, lines))
            share(min(1.0, done / size))
    share(1.0)
    rows = np.concatenate(numbers) if numbers else np.zeros((0, 11))
    table = {"frame": rows[:, 0].astype(np.int64), "track": rows[:, 1].astype(np.int64), "team": np.concatenate(teams) if teams else np.zeros(0, dtype=str)}
    return table | {name: rows[:, 2 + k] for k, name in enumerate(COLUMNS[3:])}


def packed(table: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """`table` for the cache: whole numbers where they come back exactly, the teams as codes."""
    names, codes = np.unique(table["team"], return_inverse=True)
    out = {"frame": table["frame"].astype(np.int32), "track": table["track"].astype(np.int32), "team_names": names, "team": codes.astype(np.int8)}
    for name, scale in SCALES.items():
        values = table[name]
        whole = np.rint(values * scale)
        exact = len(values) == 0 or (np.abs(whole).max() < 2**31 and np.array_equal(whole / scale, values))
        out[name] = whole.astype(np.int32) if exact else values
        # A whole number has no -0.0, which players.csv writes ("-0.0" metres on the court) and the page then shows.
        out[f"{name}_minus_zero"] = np.flatnonzero((values == 0) & np.signbit(values))
    return out


def unpacked(kept) -> dict[str, np.ndarray]:
    """The table `packed` stored."""
    table = {"frame": kept["frame"].astype(np.int64), "track": kept["track"].astype(np.int64), "team": kept["team_names"][kept["team"]]}
    for name, scale in SCALES.items():
        values = kept[name]
        table[name] = values / scale if values.dtype.kind == "i" else values
        table[name][kept[f"{name}_minus_zero"]] = -0.0
    return table

