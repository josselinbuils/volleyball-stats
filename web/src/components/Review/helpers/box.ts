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

/** Seconds of the player's path averaged into the view's center, against the boxes' jitter. */
const SMOOTH_S = 0.4;
/** Heights of the player, median over the clip, that the view spans. */
const VIEW_HEIGHTS = 4;

/** The part of the `width` × `height` frame to zoom on at `time`: centered on the player, at the frame's aspect ratio, inside the frame; the whole frame without boxes. */
export function viewAt(clip: Clip, time: number, width: number, height: number): { x: number; y: number; w: number; h: number } {
  if (!clip.boxes.length) {
    return { x: 0, y: 0, w: width, h: height };
  }
  const heights = clip.boxes.map((b) => b[4] - b[2]).sort((a, b) => a - b);
  const h = Math.min(height, VIEW_HEIGHTS * heights[Math.floor(heights.length / 2)]);
  const w = (h * width) / height;
  const at = Math.min(clip.end, Math.max(clip.start, time));
  const near = clip.boxes.filter((b) => Math.abs(b[0] - at) <= SMOOTH_S);
  const path = near.length ? near : [clip.boxes.reduce((best, b) => (Math.abs(b[0] - at) < Math.abs(best[0] - at) ? b : best))];
  const cx = path.reduce((sum, b) => sum + (b[1] + b[3]) / 2, 0) / path.length;
  const cy = path.reduce((sum, b) => sum + (b[2] + b[4]) / 2, 0) / path.length;
  return { x: Math.min(width - w, Math.max(0, cx - w / 2)), y: Math.min(height - h, Math.max(0, cy - h / 2)), w, h };
}
