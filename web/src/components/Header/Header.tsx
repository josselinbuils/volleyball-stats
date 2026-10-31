import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { ThemeSwitch } from '@/components/ThemeSwitch';
import { clock, useFormat } from '@/lib/format';
import { GROUPS, groupName, hasTeams, match, rallies as allRallies, teamColor, teamRing } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { useSet } from '@/lib/sets';
import { matchTitle, tabTitle } from '@/components/Header/helpers/title';
import { setScores, setsWon } from '@/components/Header/helpers/score';
import { SetFilter } from '@/components/Header/SetFilter';
import { Swatch } from '@/components/Swatch';
import { TeamLegend } from '@/components/Header/TeamLegend';

export function Header() {
  const { t } = useTranslation();
  const f = useFormat();
  const { set, rallies, contacts } = useSet();

  const tab = tabTitle(t, f);
  useEffect(() => {
    document.title = tab;
  }, [tab]);

  // A set lasts from its first serve to its last ball.
  const span = set === null ? match.duration : rallies.length ? rallies[rallies.length - 1].end - rallies[0].start : 0;
  const inPlay = rallies.reduce((sum, r) => sum + r.end - r.start, 0);
  const touches = contacts.filter(isTouch).length;
  const scores = setScores(allRallies, match.scores);
  const shown = set === null ? scores : scores.filter((s) => s.set === set);
  const score = set === null ? setsWon(scores) : shown[0]?.score;
  const scoreMore =
    set === null
      ? t('setsScores', { list: scores.map((s) => (s.final ? s.score.join('-') : t('estimatedScore', { score: s.score.join('-') }))).join(' · ') })
      : shown[0] && !shown[0].final
        ? t('scoreEstimated')
        : undefined;
  const stats = [
    { label: t(set === null ? 'duration' : 'setDuration'), value: clock(span) },
    { label: t('ralliesStat'), value: f.num(rallies.length) },
    {
      label: t('inPlay'),
      value: clock(inPlay),
      more: span ? t(set === null ? 'ofVideo' : 'ofSet', { p: f.pct(inPlay / span) }) : undefined,
    },
    {
      label: t('contactsStat'),
      value: f.num(touches),
      more: rallies.length ? t('perRally', { n: f.dec(touches / rallies.length) }) : undefined,
    },
  ];

  return (
    <>
      <header className="grid gap-6 px-1">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">
              {t('report')}
              {match.date && (
                <>
                  {' · '}
                  <time dateTime={match.date}>{f.date(match.date)}</time>
                </>
              )}
            </p>
            <h1 className="mt-0.5 text-2xl font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-3xl">{matchTitle(t) ?? match.name}</h1>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2 sm:flex-row">
            <ThemeSwitch />
            <LanguageSwitch />
          </div>
        </div>
        <div className="-mt-3 grid gap-2.5">
          <p className="text-muted-foreground">{t(hasTeams ? 'intro' : 'introSides')}</p>
          {hasTeams && <TeamLegend />}
        </div>
      </header>
      <SetFilter />
      <dl className={cn('grid grid-cols-2 gap-3 px-1', hasTeams && score ? 'lg:grid-cols-6' : 'lg:grid-cols-4')}>
        {hasTeams && score && (
          <Card className="col-span-2 gap-0.5 px-4 py-3.5 shadow-xs">
            <dt className="text-sm text-muted-foreground">{t(set === null ? 'matchScore' : 'setScore')}</dt>
            <dd className="flex min-w-0 items-center gap-2.5 font-semibold">
              {GROUPS.map((g, k) => (
                <span key={g} className={cn('flex min-w-0 items-center gap-2', k === 0 ? 'order-1' : 'order-3 flex-row-reverse')}>
                  <Swatch color={teamColor(g)} ring={teamRing(g)} />
                  <span className="truncate">{groupName(t, g)}</span>
                </span>
              ))}
              <span className="order-2 shrink-0 text-2xl tabular-nums sm:text-3xl">
                {f.num(score[0])} – {f.num(score[1])}
              </span>
            </dd>
            {scoreMore && (
              <dd className="text-sm text-muted-foreground" title={shown.some((s) => !s.final) ? t('scoreHint') : undefined}>
                {scoreMore}
              </dd>
            )}
          </Card>
        )}
        {stats.map(({ label, value, more }) => (
          <Card key={label} className="gap-0.5 px-4 py-3.5 shadow-xs">
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="text-2xl font-semibold tabular-nums sm:text-3xl">{value}</dd>
            {more && <dd className="text-sm text-muted-foreground">{more}</dd>}
          </Card>
        ))}
      </dl>
    </>
  );
}
