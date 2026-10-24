import type { TFunction } from 'i18next';
import type { ActionType, Contact, Rally, Side } from '@/lib/match';
import { clock, type Format } from '@/lib/format';

/** Seconds of video played before and after a touch, and around a rally. */
export const BEFORE = 2;
export const AFTER = 1.5;
export const PAD = 1;

/** A stretch of video to play. A touch's clip names its action and side only when its playlist
 * mixes them; a rally's clip has its length. */
export interface Clip {
  start: number;
  end: number;
  rally: number;
  time: number;
  type?: ActionType;
  side?: Side;
  length?: number;
}

export function contactClips(contacts: Contact[], duration: number): Clip[] {
  const mixed = (key: 'type' | 'side') => new Set(contacts.map((c) => c[key])).size > 1;
  const showType = mixed('type');
  const showSide = mixed('side');
  return contacts.map((c) => ({
    start: Math.max(0, c.t - BEFORE),
    end: Math.min(duration, c.t + AFTER),
    rally: c.rally,
    time: c.t,
    type: showType ? c.type : undefined,
    side: showSide ? c.side : undefined,
  }));
}

export function rallyClips(rallies: Rally[], duration: number): Clip[] {
  return rallies.map((r) => ({
    start: Math.max(0, r.start - PAD),
    end: Math.min(duration, r.end + PAD),
    rally: r.i,
    time: r.start,
    length: r.end - r.start,
  }));
}

/** The rally whose clip holds `time`. */
export function rallyAt<R extends { start: number; end: number }>(rallies: R[], time: number): R | undefined {
  return rallies.find((r) => time >= r.start - PAD && time <= r.end + PAD);
}

export function clipLabel(clip: Clip, t: TFunction, f: Format): string {
  if (clip.length !== undefined) {
    return [t('rally', { n: clip.rally + 1 }), clock(clip.time), f.secs(clip.length)].join(' · ');
  }
  return [
    clip.type && t(`types.${clip.type}`),
    clip.side && t(`${clip.side}Side`).toLowerCase(),
    t('rallyLower', { n: clip.rally + 1 }),
    clock(clip.time),
  ]
    .filter(Boolean)
    .join(' · ');
}
