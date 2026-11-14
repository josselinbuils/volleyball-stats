import type { TFunction } from 'i18next';
import { clock, type Format } from '@/lib/format';
import { contacts, groupName, match, rallies as allRallies, type Contact, type Rally } from '@/lib/match';
import { seek, usePlayer, useVideoTime } from '@/lib/player';
import { PAD, rallyClips, rallyNear, type Clip } from '@/lib/playlist';
import { isTouch } from '@/helpers/contacts';
import { useSet } from '@/lib/sets';

/** One line of the list: a rally, or a playlist's clip with its rally and, for a touch's clip, its touch. */
export interface Entry {
  rally: Rally;
  clip?: Clip;
  contact?: Contact;
}

/** What the player's lists show: the playlist playing, else the set's rallies, the one the video is on current (`at`).
 * `whole` when they are the set's rallies (a playlist of them too). `pick` plays from an entry; `step` moves to the
 * next or previous one, a rally only shown when nothing plays. */
export function useWatchList() {
  const { playlist, play, go, video } = usePlayer();
  const { set, rallies } = useSet();
  const near = useVideoTime((time) => rallyNear(rallies, time)?.i ?? -1);
  const ralliesTitle = (tr: TFunction) => (set === null ? tr('rallies') : tr('set', { n: set }));
  if (playlist) {
    const { clips, at } = playlist;
    return {
      title: playlist.title,
      playing: true,
      whole: clips.length === rallies.length && clips.every((c, k) => c.length !== undefined && c.rally === rallies[k].i),
      entries: clips.map((clip): Entry => ({ rally: allRallies[clip.rally], clip, contact: clip.contact === undefined ? undefined : contacts[clip.contact] })),
      at,
      pick: go,
      step: (by: number) => go(at + by),
    };
  }
  const at = rallies.findIndex((r) => r.i === near);
  return {
    title: ralliesTitle,
    playing: false,
    whole: true,
    entries: rallies.map((rally): Entry => ({ rally })),
    at,
    pick: (k: number) => play(ralliesTitle, rallyClips(rallies, match.duration), k),
    step: (by: number) => video && seek(video, Math.max(0, rallies[at + by].start - PAD)),
  };
}

/** When an entry happens: its touch's time, else its rally's start. */
export function entryTime(e: Entry): string {
  return clock(e.contact?.t ?? e.rally.start);
}

/** What an entry shows besides its rally: a touch's action, team and player, each only when its playlist mixes them (its
 * title says the rest; empty then); a rally's length and touches. */
export function entryDetail(e: Entry, t: TFunction, f: Format): string {
  const { clip, contact } = e;
  if (contact && clip) {
    return [
      clip.type && t(clip.result ? `actions.${clip.type}.${clip.result}` : `types.${clip.type}`, { defaultValue: t(`types.${clip.type}`) }),
      clip.team && groupName(t, clip.team),
      clip.name ?? (clip.player && t('player', { n: clip.player })),
    ]
      .filter(Boolean)
      .join(' · ');
  }
  return `${f.secs(e.rally.end - e.rally.start)} · ${t('touchesN', { count: e.rally.contacts.filter(isTouch).length })}`;
}
