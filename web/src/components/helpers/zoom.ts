/** A view zoomed on a box: its scale and where its top left corner sits, in the box's pixels. */
export interface Zoom {
  scale: number;
  x: number;
  y: number;
}

/** The most a view zooms. */
export const MAX_SCALE = 8;

/** `zoom` kept covering the `w` × `h` box: no edge of the view inside it. */
export function clampView(zoom: Zoom, w: number, h: number): Zoom {
  return { scale: zoom.scale, x: Math.min(0, Math.max(w - w * zoom.scale, zoom.x)), y: Math.min(0, Math.max(h - h * zoom.scale, zoom.y)) };
}

/** `zoom` scaled by `factor` around `point` (box pixels), which stays put; whole again under 1. */
export function zoomAt(zoom: Zoom, factor: number, point: { x: number; y: number }, w: number, h: number): Zoom {
  const scale = Math.min(MAX_SCALE, zoom.scale * factor);
  if (scale <= 1.01) {
    return { scale: 1, x: 0, y: 0 };
  }
  const k = scale / zoom.scale;
  return clampView({ scale, x: point.x - (point.x - zoom.x) * k, y: point.y - (point.y - zoom.y) * k }, w, h);
}

const WHEEL_SPEED = 0.01;
const WHEEL_MAX_DELTA = 30;
const WHEEL_LINE_PX = 33;

/** The zoom of one wheel event: a pinch's small deltas as they are, a mouse notch (100 or more, or lines) held to WHEEL_MAX_DELTA. */
export function wheelZoom(deltaY: number, deltaMode: number): number {
  const pixels = deltaMode === 1 ? deltaY * WHEEL_LINE_PX : deltaY;
  return Math.exp(-Math.max(-WHEEL_MAX_DELTA, Math.min(WHEEL_MAX_DELTA, pixels)) * WHEEL_SPEED);
}
