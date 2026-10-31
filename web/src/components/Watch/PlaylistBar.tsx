import { ChevronLeft, ChevronRight, Play, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Swatch } from '@/components/Swatch';
import { clock, useFormat } from '@/lib/format';
import { isTouch } from '@/helpers/contacts';
import { groupName, match, teamColor, teamRing } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { clipLabel, PAD, rallyClips, rallyNear } from '@/lib/playlist';
import { useSet } from '@/lib/sets';

/** What is playing, with the playlist's controls; else the rally the video is on, the one
 * highlighted below, with controls to move to another one and play from it. Its height is the same
 * in every state: nothing below it moves when playback starts, changes or stops. */
export function PlaylistBar() {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play, go, stop, video } = usePlayer();
  const { set, rallies } = useSet();
  const near = useVideoTime((time) => rallyNear(rallies, time)?.i ?? -1);
  const k = rallies.findIndex((r) => r.i === near);
  const rally = rallies[k];
  const seek = (to: number) => {
    if (video) {
      video.currentTime = Math.max(0, rallies[to].start - PAD);
    }
  };
  const playFrom = () => play((tr) => (set === null ? tr('rallies') : tr('set', { n: set })), rallyClips(rallies, match.duration), k);

  const clip = playlist?.clips[playlist.at];
  const details = playlist && clip ? `${playlist.title(t)} · ${clipLabel(clip, t, f, (g) => groupName(t, g))}` : '';

  return (
    // Laid out by its own width: it also stands in a narrow column beside the court.
    <div className="@container mt-3">
      <div className="grid gap-x-3 gap-y-2.5 rounded-lg bg-muted px-3 py-2.5 @md:grid-cols-[minmax(0,1fr)_auto] @md:items-center">
        <div aria-live="polite" className="h-15 min-w-0 text-sm leading-5 text-muted-foreground">
          {playlist && clip ? (
            <>
              <span className="block truncate text-xs leading-5 font-semibold tracking-wide text-link uppercase">
                {`${t('nowPlaying')} · ${t('iOfN', { i: f.num(playlist.at + 1), n: f.num(playlist.clips.length) })}`}
              </span>
              <span className="line-clamp-2" title={details}>
                {clip.team && <Swatch color={teamColor(clip.team)} ring={teamRing(clip.team)} className="mr-1.5 align-[-1px]" />}
                <b className="font-semibold text-foreground">{playlist.title(t)}</b>
                {` · ${clipLabel(clip, t, f, (g) => groupName(t, g))}`}
              </span>
            </>
          ) : rally ? (
            <>
              <span className="block truncate text-xs leading-5 font-semibold tracking-wide text-link uppercase">
                {`${t('selectedRally')} · ${t('iOfN', { i: f.num(k + 1), n: f.num(rallies.length) })}`}
              </span>
              <span className="line-clamp-2">
                <b className="font-semibold text-foreground">{t('rally', { n: rally.i + 1 })}</b>
                {` · ${clock(rally.start)} · ${f.secs(rally.end - rally.start)} · ${t('touchesN', { count: rally.contacts.filter(isTouch).length })}`}
              </span>
            </>
          ) : (
            <span className="line-clamp-3">{t('noRally')}</span>
          )}
        </div>
        <div className="flex flex-wrap gap-2 @md:justify-end">
          {playlist ? (
            <>
              {/* Chevrons alone when narrow, where the three labels would wrap. */}
              <Button variant="outline" className="bg-card @max-sm:px-3" title={t('prev')} disabled={playlist.at === 0} onClick={() => go(playlist.at - 1)}>
                <ChevronLeft aria-hidden />
                <span className="@max-sm:sr-only">{t('prev')}</span>
              </Button>
              <Button variant="outline" className="bg-card @max-sm:px-3" title={t('next')} disabled={playlist.at === playlist.clips.length - 1} onClick={() => go(playlist.at + 1)}>
                <span className="@max-sm:sr-only">{t('next')}</span>
                <ChevronRight aria-hidden />
              </Button>
              <Button variant="outline" className="bg-card" onClick={stop}>
                <Square aria-hidden className="fill-current" />
                {t('stop')}
              </Button>
            </>
          ) : (
            rally && (
              <>
                <Button variant="outline" className="bg-card @max-sm:px-3" title={t('prevRally')} disabled={k === 0} onClick={() => seek(k - 1)}>
                  <ChevronLeft aria-hidden />
                  <span className="@max-sm:sr-only">{t('prev')}</span>
                </Button>
                <Button variant="outline" className="bg-card @max-sm:px-3" title={t('nextRally')} disabled={k === rallies.length - 1} onClick={() => seek(k + 1)}>
                  <span className="@max-sm:sr-only">{t('next')}</span>
                  <ChevronRight aria-hidden />
                </Button>
                <Button title={t('watchRally')} onClick={playFrom}>
                  <Play aria-hidden className="fill-current" />
                  {t('playRally')}
                </Button>
              </>
            )
          )}
        </div>
      </div>
    </div>
  );
}
