import type { Clip } from '@/lib/review';

/** The clip's box nearest to `time`, none outside the clip. */
export function boxAt(clip: Clip, time: number): [number, number, number, number] | null {
  if (time < clip.start || time > clip.end || !clip.boxes.length) {
    return null;
  }
  let best = clip.boxes[0];
  for (const b of clip.boxes) {
    if (Math.abs(b[0] - time) < Math.abs(best[0] - time)) {
      best = b;
    }
  }
  return [best[1], best[2], best[3], best[4]];
}
