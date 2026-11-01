import type { Rally } from '@/lib/match';

/** A report's video starts this long before the reported moment, and a touch's replay before the touch. */
export const REPORT_LEAD_S = 2;

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

/** The index of the rally a touch of `type` added at `time` belongs to, as the server files it: the
 * one it falls in; else a serve the next one's (the rally missed it), another touch `rallyAt`'s. */
/** `rallies` each starting at a serve `added` before it, as the server files them: the touches added
 * after such a serve are that rally's. */
export function withServes<R extends Pick<Rally, 'start' | 'end'>>(rallies: R[], added: { time: number; type: string }[]): R[] {
  const out = rallies.map((r) => ({ ...r }));
  for (const a of added) {
    const k = a.type === 'serve' ? rallyOf(out, a.time, 'serve') : -1;
    if (out[k]) {
      out[k].start = Math.min(out[k].start, a.time);
    }
  }
  return out;
}

export function rallyOf(rallies: Pick<Rally, 'start' | 'end'>[], time: number, type: string): number {
  const inside = rallies.findIndex((r) => r.start - LEAD_S <= time && time <= r.end);
  const next = rallies.findIndex((r) => r.start > time);
  return inside < 0 && type === 'serve' && next >= 0 ? next : rallyAt(rallies, time);
}
