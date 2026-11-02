"""Generates the commentary's audio of a built match page, once for each text (`speech.py` says which).

    uv run --group voice python -m volleyball_stats.voice outputs/first_match

Kokoro's French voice ff_siwis (Apache 2.0; the voice is CC BY, from the SIWIS dataset), about 7 times faster than real
time on the M4. Run it again after a review's changes: only the new lines are made. The next build of the page takes them.
"""

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np

from volleyball_stats.speech import clip_name, read_spoken, replay_lines, script, spelled

VOICE = "ff_siwis"
SPEED = 1.2
RATE = 24000
BITRATE = "64k"
# What the voice leaves around its words goes, but for this margin: every line has to fit between two touches.
QUIET = 0.01
MARGIN_S = 0.02


def trimmed(audio: np.ndarray) -> np.ndarray:
    """`audio` without its silence at both ends."""
    loud = np.flatnonzero(np.abs(audio) > QUIET)
    if not len(loud):
        return audio
    margin = round(MARGIN_S * RATE)
    return audio[max(0, loud[0] - margin) : loud[-1] + margin + 1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path)
    parser.add_argument("--again", action="store_true", help="make every line again, not only the missing ones")
    args = parser.parse_args()
    text = (args.match / "site" / "data.js").read_text()
    data = json.loads(text[text.index("{") : text.rindex("}") + 1])
    spoken = read_spoken(args.match)
    lines = script(data)
    said = [line["text"] for line in lines] + [line["short"] for line in lines if line.get("short")] + list(replay_lines(data).values())
    wanted = {spelled(t, spoken) for t in said}
    folder = args.match / "voice"
    folder.mkdir(exist_ok=True)
    path = folder / "durations.json"
    durations = json.loads(path.read_text()) if path.exists() and not args.again else {}
    new = sorted(t for t in wanted if clip_name(t) not in durations or not (folder / clip_name(t)).exists())
    print(f"{len(wanted)} texts, {len(new)} to make")
    if new:
        from kokoro import KPipeline

        pipeline = KPipeline(lang_code="f", repo_id="hexgrad/Kokoro-82M")
        for k, line in enumerate(new):
            audio = trimmed(np.concatenate([np.asarray(part) for _, _, part in pipeline(line, voice=VOICE, speed=SPEED)]).astype(np.float32))
            clip = clip_name(line)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", "-", "-c:a", "libmp3lame", "-b:a", BITRATE, str(folder / clip)], input=audio.tobytes(), check=True)
            durations[clip] = round(len(audio) / RATE, 2)
            if k % 25 == 0:
                print(f"  {k + 1}/{len(new)}", flush=True)
                path.write_text(json.dumps(durations))
        path.write_text(json.dumps(durations))
    print(f"{sum(durations[clip_name(t)] for t in wanted):.0f} s of audio in {folder}")


if __name__ == "__main__":
    main()
