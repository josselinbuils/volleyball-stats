import { useTranslation } from 'react-i18next';
import { Swatch } from '@/components/Swatch';
import { useFormat } from '@/lib/format';
import { GROUPS, groupName, match, rallies, teamColor, teamRing } from '@/lib/match';
import { useVideoTime } from '@/lib/player';
import { scoreAt } from '@/components/Watch/helpers/score';

/** The set and its score at the video's time, above the video. */
export function Scoreboard() {
  const { t } = useTranslation();
  const f = useFormat();
  const now = scoreAt(rallies, useVideoTime((time) => time), match.scores);
  if (!now) {
    return null;
  }
  const [a, b] = GROUPS.map((g) => groupName(t, g));
  return (
    <div
      role="status"
      aria-label={t('scoreLabel', { set: now.set, a, b, s1: now.score[0], s2: now.score[1] })}
      className="mb-3 flex h-11 items-center gap-3 rounded-lg bg-muted px-3 text-sm"
    >
      <span className="shrink-0 rounded-md bg-primary px-2 py-0.5 font-semibold text-primary-foreground">{t('set', { n: now.set })}</span>
      <span className="flex min-w-0 flex-1 items-center justify-center gap-2.5 font-semibold">
        <Swatch color={teamColor(1)} ring={teamRing(1)} />
        <span className="truncate">{a}</span>
        <span className="shrink-0 text-xl tabular-nums">
          {f.num(now.score[0])} – {f.num(now.score[1])}
        </span>
        <span className="truncate">{b}</span>
        <Swatch color={teamColor(2)} ring={teamRing(2)} />
      </span>
      <span className="shrink-0 text-xs text-muted-foreground" title={now.final ? undefined : t('scoreHint')}>
        {t(now.final ? 'scoreFinal' : 'scoreEstimated')}
      </span>
    </div>
  );
}
