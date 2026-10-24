import { ChevronLeft, ChevronRight, Play, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useFormat } from '@/lib/format';
import { match, rallies } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { clipLabel, rallyClips } from '@/lib/playlist';

/** What is playing, with the playlist's controls. */
export function PlaylistBar() {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play, go, stop } = usePlayer();

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2.5 rounded-lg bg-muted px-3 py-2.5">
      <div aria-live="polite" className="min-w-0 flex-[1_1_16rem] text-sm text-muted-foreground">
        {playlist ? (
          <>
            <span className="block text-xs font-semibold tracking-wide text-link uppercase">{t('nowPlaying')}</span>
            <b className="font-semibold text-foreground">{playlist.title(t)}</b>
            {` · ${t('iOfN', { i: f.num(playlist.at + 1), n: f.num(playlist.clips.length) })} · ${clipLabel(playlist.clips[playlist.at], t, f)}`}
          </>
        ) : (
          t('idle')
        )}
      </div>
      {playlist ? (
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="bg-card" disabled={playlist.at === 0} onClick={() => go(playlist.at - 1)}>
            <ChevronLeft aria-hidden />
            {t('prev')}
          </Button>
          <Button variant="outline" className="bg-card" disabled={playlist.at === playlist.clips.length - 1} onClick={() => go(playlist.at + 1)}>
            {t('next')}
            <ChevronRight aria-hidden />
          </Button>
          <Button variant="outline" className="bg-card" onClick={stop}>
            <Square aria-hidden className="fill-current" />
            {t('stop')}
          </Button>
        </div>
      ) : (
        rallies.length > 0 && (
          <Button onClick={() => play((tr) => tr('allRallies'), rallyClips(rallies, match.duration))}>
            <Play aria-hidden className="fill-current" />
            {t('watchAll')}
          </Button>
        )
      )}
    </div>
  );
}
