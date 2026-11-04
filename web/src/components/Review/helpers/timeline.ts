/** Where `now` falls on a list's rail, in pixels: it reaches a row's top at `at`, the moment the row
 * becomes active (in order), and the last row's bottom past it. */
export function railAt(rows: { at: number; top: number; bottom: number }[], now: number): number {
  if (!rows.length) {
    return 0;
  }
  // A rally's first touch can light up before its header: a row is reached by the time the next one is.
  const ats = rows.map((r) => r.at);
  for (let i = ats.length - 2; i >= 0; i--) {
    ats[i] = Math.min(ats[i], ats[i + 1]);
  }
  const next = ats.findIndex((at) => at > now);
  if (next === 0) {
    return rows[0].top;
  }
  if (next < 0) {
    return rows[rows.length - 1].bottom;
  }
  const [a, b] = [rows[next - 1], rows[next]];
  return a.top + ((b.top - a.top) * (now - ats[next - 1])) / (ats[next] - ats[next - 1]);
}

/** How far the rows listed both `before` and `after` moved (their tops by key), 0 with none. */
export function shiftOf(before: Map<string, number>, after: Map<string, number>): number {
  for (const [key, top] of after) {
    const was = before.get(key);
    if (was !== undefined) {
      return top - was;
    }
  }
  return 0;
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
