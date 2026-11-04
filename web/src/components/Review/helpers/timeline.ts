/** Where `now` falls on a list's rail, in pixels: between the middles of the rows around it (`at` their
 * time, in order), from the first's top to the last's bottom. */
export function railAt(rows: { at: number; top: number; bottom: number }[], now: number): number {
  if (!rows.length) {
    return 0;
  }
  const next = rows.findIndex((r) => r.at > now);
  if (next === 0) {
    return rows[0].top;
  }
  if (next < 0) {
    return rows[rows.length - 1].bottom;
  }
  const [a, b] = [rows[next - 1], rows[next]];
  const [from, to] = [(a.top + a.bottom) / 2, (b.top + b.bottom) / 2];
  return from + ((to - from) * (now - a.at)) / (b.at - a.at);
}

/** The steps between the time labels, in seconds. */
const STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900];

/** The shortest step putting `gap` pixels or more between two labels at `scale` pixels a second. */
export function tickStep(scale: number, gap = 64): number {
  return STEPS.find((s) => s * scale >= gap) ?? STEPS[STEPS.length - 1];
}

/** `scale` times `factor`, within `fit` (the whole match in view) and `max` pixels a second. */
export function zoomed(scale: number, factor: number, fit: number, max: number): number {
  return Math.min(max, Math.max(fit, scale * factor));
}
