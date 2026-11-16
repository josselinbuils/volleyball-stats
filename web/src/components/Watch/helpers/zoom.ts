import type { View } from '@/components/Watch/helpers/overlay';

/** A view: its center (fractions of the picture) and how much it enlarges the picture. */
export type Camera = { x: number; y: number; zoom: number };

export const WHOLE: Camera = { x: 0.5, y: 0.5, zoom: 1 };

/** framing.py's CAMERA_STEP_S and CAMERA_UNIT: the camera's samples, every that many seconds, in that unit. */
const STEP_S = 0.1;
const UNIT = 1e-4;

/** video.js's runs read once: each one's start and its samples [x, y, zoom, ...] added up. */
const read = new WeakMap<number[][], { start: number; samples: Float64Array }[]>();

/** The automatic zoom's camera at `time`, from video.js's runs (framing.camera_spans: [from this time, x, y, zoom, then
 * each sample's change from the one before...]), linear between its samples as the video's copies are cut by it; the
 * whole picture outside them. */
export function cameraAt(spans: number[][], time: number): Camera {
  let runs = read.get(spans);
  if (!runs) {
    runs = spans.map((span) => {
      const samples = new Float64Array(span.length - 1);
      for (let k = 0; k < samples.length; k += 1) {
        samples[k] = (k >= 3 ? samples[k - 3] : 0) + span[k + 1];
      }
      return { start: span[0], samples };
    });
    read.set(spans, runs);
  }
  for (const { start, samples } of runs) {
    const at = (time - start) / STEP_S;
    const last = samples.length / 3 - 1;
    // A sample's own time lands a hair either side of it.
    if (at < -1e-6 || at > last + 1e-6) {
      continue;
    }
    const k = Math.min(Math.floor(Math.max(0, at)), Math.max(0, last - 1));
    const share = Math.min(1, Math.max(0, at - k));
    const value = (i: number) => (samples[3 * k + i] + ((k < last ? samples[3 * k + 3 + i] : samples[3 * k + i]) - samples[3 * k + i]) * share) * UNIT;
    return { x: value(0), y: value(1), zoom: value(2) };
  }
  return WHOLE;
}

/** The view zooming `zoom` times on `at` (fractions of the picture) in an element `width` × `height`
 * showing a `videoWidth` × `videoHeight` picture letterboxed: a scale and the translation (px) that
 * put `at` in the middle, the picture still filling its place. */
export function zoomOn(at: { x: number; y: number }, width: number, height: number, videoWidth: number, videoHeight: number, zoom: number): { scale: number; x: number; y: number } {
  const s = Math.min(width / videoWidth, height / videoHeight);
  const [w, h] = [videoWidth * s, videoHeight * s];
  const [left, top] = [(width - w) / 2, (height - h) / 2];
  const clamp = (v: number, low: number, high: number) => Math.min(high, Math.max(low, v));
  return {
    scale: zoom,
    x: clamp(width / 2 - zoom * (left + at.x * w), left + w - zoom * (left + w), left * (1 - zoom)),
    y: clamp(height / 2 - zoom * (top + at.y * h), top + h - zoom * (top + h), top * (1 - zoom)),
  };
}

/** `view` (`zoomOn`'s) of a copy cut by `cut` as a view of the whole picture, for what is drawn in its fractions: the
 * picture's place in the element `width` × `height`, letterboxed as the copy's `videoWidth` × `videoHeight`. */
export function throughCut(view: View, cut: Camera, width: number, height: number, videoWidth: number, videoHeight: number): View {
  const s = Math.min(width / videoWidth, height / videoHeight);
  const [w, h] = [videoWidth * s, videoHeight * s];
  const [left, top] = [(width - w) / 2, (height - h) / 2];
  const size = 1 / cut.zoom;
  const scale = view.scale / size;
  return {
    scale,
    x: view.x + view.scale * (left - ((cut.x - size / 2) / size) * w) - scale * left,
    y: view.y + view.scale * (top - ((cut.y - size / 2) / size) * h) - scale * top,
  };
}
