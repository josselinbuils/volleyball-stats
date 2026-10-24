import { ChevronLeft, ChevronRight, Play, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Swatch } from '@/components/Swatch';
import { useFormat } from '@/lib/format';
import { groupName, match, teamColor } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { clipLabel, rallyClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';

/** What is playing, with the playlist's controls. Its height is the same in every state: nothing
 * below it moves when playback starts, changes or stops. */
export function PlaylistBar() {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play, go, stop } = usePlayer();
  const { set, rallies } = useSet();

  const clip = playlist?.clips[playlist.at];
  const details = playlist && clip ? `${playlist.title(t)} · ${clipLabel(clip, t, f, (g) => groupName(t, g))}` : '';

  return (
    <div className="mt-3 grid gap-x-3 gap-y-2.5 rounded-lg bg-muted px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div aria-live="polite" className="h-15 min-w-0 text-sm leading-5 text-muted-foreground">
        {playlist && clip ? (
          <>
            <span className="block truncate text-xs leading-5 font-semibold tracking-wide text-link uppercase">
              {`${t('nowPlaying')} · ${t('iOfN', { i: f.num(playlist.at + 1), n: f.num(playlist.clips.length) })}`}
            </span>
            <span className="line-clamp-2" title={details}>
              {clip.team && <Swatch color={teamColor(clip.team)} className="mr-1.5 align-[-1px]" />}
              <b className="font-semibold text-foreground">{playlist.title(t)}</b>
              {` · ${clipLabel(clip, t, f, (g) => groupName(t, g))}`}
            </span>
          </>
        ) : (
          <span className="line-clamp-3" title={t('idle')}>
            {t('idle')}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-2 sm:justify-end">
        {playlist ? (
          <>
            {/* Chevrons alone on a phone, where the three labels would wrap. */}
            <Button variant="outline" className="bg-card max-sm:px-3" title={t('prev')} disabled={playlist.at === 0} onClick={() => go(playlist.at - 1)}>
              <ChevronLeft aria-hidden />
              <span className="max-sm:sr-only">{t('prev')}</span>
            </Button>
            <Button variant="outline" className="bg-card max-sm:px-3" title={t('next')} disabled={playlist.at === playlist.clips.length - 1} onClick={() => go(playlist.at + 1)}>
              <span className="max-sm:sr-only">{t('next')}</span>
              <ChevronRight aria-hidden />
            </Button>
            <Button variant="outline" className="bg-card" onClick={stop}>
              <Square aria-hidden className="fill-current" />
              {t('stop')}
            </Button>
          </>
        ) : (
          rallies.length > 0 && (
            <Button onClick={() => play((tr) => (set === null ? tr('allRallies') : tr('set', { n: set })), rallyClips(rallies, match.duration))}>
              <Play aria-hidden className="fill-current" />
              {t('watchAll')}
            </Button>
          )
        )}
      </div>
    </div>
  );
}
