import type { Rally } from '@/lib/match';

/** A touch counts in its rally from this long before its start, as on the page (actions.LEAD_S). */
export const LEAD_S = 0.33;

/** The index of the rally `time` falls in (from LEAD_S before it), else of the last one started
 * before it (just ended), else of the first: as the server places an added touch. */
export function rallyAt(rallies: Pick<Rally, 'start' | 'end'>[], time: number): number {
  const inside = rallies.findIndex((r) => r.start - LEAD_S <= time && time <= r.end);
  if (inside >= 0) {
    return inside;
  }
  const before = rallies.findLastIndex((r) => r.start <= time);
  return Math.max(0, before);
}
