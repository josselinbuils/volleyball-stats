/** Where a moment's mark stands, its point at `y` px in a chart `height` px high: `off` px from it, first on the side
 * `away` from the zero line (-1 up, 1 down), then `step` px further each time, either side, until it is clear of the
 * marks above or below it (`taken`, their y) and inside the chart; at its first place when none is. */
export function markY(y: number, away: -1 | 1, taken: number[], height: number, off: number, step: number): number {
  const fits = (at: number) => at >= off && at <= height - off;
  const free = (at: number) => taken.every((t) => Math.abs(t - at) >= step - 2);
  for (let k = 0; k <= taken.length + 1; k++) {
    for (const side of [away, -away]) {
      const at = y + side * (off + k * step);
      if (fits(at) && free(at)) {
        return at;
      }
    }
  }
  return fits(y + away * off) ? y + away * off : y - away * off;
}
