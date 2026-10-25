import type { TFunction } from 'i18next';
import type { ActionType, Contact, Group, Rally } from '@/lib/match';
import { clock, type Format } from '@/lib/format';

/** Seconds of video played before and after a touch, and around a rally. */
export const BEFORE = 2;
export const AFTER = 1.5;
export const PAD = 1;

/** A stretch of video to play. A touch's clip names its action, team and player (name or number,
 * when known) only when its playlist mixes them; a rally's clip has its length. */
export interface Clip {
  start: number;
  end: number;
  rally: number;
  time: number;
  type?: ActionType;
  team?: Group;
  player?: number;
  name?: string;
  length?: number;
}

export function contactClips(contacts: Contact[], duration: number): Clip[] {
  const mixed = (key: 'type' | 'g' | 'person') => new Set(contacts.map((c) => c[key])).size > 1;
  const showType = mixed('type');
  const showTeam = mixed('g');
  const showPlayer = mixed('person');
  return contacts.map((c) => ({
    start: Math.max(0, c.t - BEFORE),
    end: Math.min(duration, c.t + AFTER),
    rally: c.rally,
    time: c.t,
    type: showType ? c.type : undefined,
    team: showTeam ? c.g : undefined,
    player: showPlayer ? (c.player ?? undefined) : undefined,
    name: showPlayer ? (c.name ?? undefined) : undefined,
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

/** The rally to show at `time` when nothing plays: the one whose clip holds it, else the next one,
 * else the last. */
export function rallyNear<R extends { start: number; end: number }>(rallies: R[], time: number): R | undefined {
  return rallyAt(rallies, time) ?? rallies.find((r) => r.start - PAD > time) ?? rallies[rallies.length - 1];
}

/** What a clip shows, `name` naming a team. */
export function clipLabel(clip: Clip, t: TFunction, f: Format, name: (g: Group) => string): string {
  if (clip.length !== undefined) {
    return [t('rally', { n: clip.rally + 1 }), clock(clip.time), f.secs(clip.length)].join(' · ');
  }
  return [
    clip.type && t(`types.${clip.type}`),
    clip.team && name(clip.team),
    clip.name ?? (clip.player && t('player', { n: clip.player })),
    t('rallyLower', { n: clip.rally + 1 }),
    clock(clip.time),
  ]
    .filter(Boolean)
    .join(' · ');
}
