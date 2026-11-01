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
