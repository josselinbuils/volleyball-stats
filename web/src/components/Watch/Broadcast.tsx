import { useMemo } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { groupName, match, rallies as allRallies, teamColor, teamRing, timeoutAt, timeoutLabel, timeouts } from '@/lib/match';
import { Swatch } from '@/components/Swatch';
import { usePlayer } from '@/lib/player';
import { useSet } from '@/lib/sets';
import { useSaid } from '@/components/Watch/Commentary';
import { broadcastClips, replays, type ReplayMoment } from '@/components/Watch/helpers/director';
import type { Score } from '@/components/Watch/helpers/score';

/** What the TV view shows over the picture: the score, the replay's tag, a timeout's card and the commentary's words. */
export function BroadcastOverlay({ time, rally, replay, score }: { time: number; rally: number | null; replay: ReplayMoment | null; score: Score | null }) {
  const { t } = useTranslation();
  const { text } = useSaid(time, rally, replay);
  const pause = replay ? null : timeoutAt(time);

  return (
    <div className="pointer-events-none absolute inset-0 z-[1] overflow-hidden">
      {score && (
        <p className="absolute top-2 left-2 m-0 flex max-w-[calc(100%-1rem)] items-center gap-2 rounded-md bg-black/75 px-2 py-1 text-xs font-semibold text-white tabular-nums sm:text-sm">
          <span className="truncate">{groupName(t, 1)}</span>
          <span>
            {score.score[0]}-{score.score[1]}
          </span>
          <span className="truncate">{groupName(t, 2)}</span>
          <span className="font-normal text-white/70">{t('set', { n: score.set })}</span>
        </p>
      )}
      {pause && (
        <p className="absolute top-1/2 left-1/2 m-0 flex -translate-1/2 items-center gap-2 rounded-md bg-black/75 px-4 py-2 font-bold tracking-wide whitespace-nowrap text-white uppercase sm:text-lg">
          {pause.team && <Swatch color={teamColor(pause.team)} ring={teamRing(pause.team)} />}
          {timeoutLabel(t, pause)}
        </p>
      )}
      {replay && <p className="absolute top-2 right-2 m-0 rounded-md bg-primary px-2 py-1 text-xs font-bold tracking-wide text-primary-foreground uppercase">{t('broadcast.replayTag')}</p>}
      <p
        aria-live="off"
        className={cn(
          'absolute inset-x-2 bottom-2 m-0 rounded-md bg-black/75 px-3 py-1.5 text-center text-sm leading-snug font-medium text-white transition-opacity sm:inset-x-[10%] sm:text-base',
          !text && 'opacity-0',
        )}
      >
        {text || ' '}
      </p>
    </div>
  );
}

/** Under the TV view: watching the match shown from the start. */
export function BroadcastControls() {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const { rallies } = useSet();
  const chosen = useMemo(() => replays(allRallies), []);
  const clips = useMemo(() => broadcastClips(rallies, chosen, match.duration, timeouts), [rallies, chosen]);
  return (
    <div className="mt-3 grid gap-2 [[data-player]:fullscreen_&]:hidden">
      <Button size="sm" className="justify-self-start" disabled={!clips.length} onClick={() => play((tr) => tr('broadcast.watching'), clips)}>
        <Play aria-hidden />
        {t('broadcast.watch')}
      </Button>
      <p className="m-0 text-[13px] text-muted-foreground">
        {t('broadcast.caption')}
        {match.voice && ` ${t('broadcast.voiceCredit')}`}
      </p>
    </div>
  );
}
