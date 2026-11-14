import { Fragment, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { CountButton } from '@/components/CountButton';
import { Settings } from '@/components/Settings';
import { clock, ofName, useFormat } from '@/lib/format';
import { GROUPS, groupName, hasTeams, match, rallies as allRallies, teamColor, teamRing } from '@/lib/match';
import { isTouch } from '@/helpers/contacts';
import { useSet } from '@/lib/sets';
import { matchTitle, tabTitle } from '@/components/Header/helpers/title';
import { pointSplit, setScores, setsWon } from '@/components/Header/helpers/score';
import { StickyBar } from '@/components/Header/StickyBar';
import { Swatch } from '@/components/Swatch';
import { TeamLegend } from '@/components/Header/TeamLegend';
import { Tip } from '@/components/Tip';
import { onAppServer, windowTitle } from '@/lib/appServer';
import { BackLink } from '@/components/BackLink';

export function Header() {
  const { t } = useTranslation();
  const f = useFormat();
  const { set, rallies, contacts } = useSet();

  const tab = tabTitle(t, f);
  useEffect(() => {
    document.title = windowTitle(tab);
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
            {/* In the app, the page is the review's preview. */}
            {onAppServer() && <BackLink href="/review" label={t('backToReview')} className="mb-3 flex w-fit" />}
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
          {/* On the club's band when there is one. */}
          {!match.club && <Settings />}
        </div>
        <div className="-mt-3 grid gap-2.5">
          <p className="text-muted-foreground">{t(hasTeams ? 'intro' : 'introSides')}</p>
          {hasTeams && <TeamLegend />}
        </div>
      </header>
      <StickyBar />
      {/* The score beside the other figures two by two, which together take its height. */}
      <div className={cn('grid gap-3 px-1', hasTeams && score && 'lg:grid-cols-2')}>
        {hasTeams && score && (
          <dl className="grid">
            <Card className="gap-0.5 px-4 py-3.5 shadow-xs">
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
                <Tip label={shown.some((s) => !s.final) ? t('scoreHint') : undefined}>
                  <dd className="text-sm text-muted-foreground">{scoreMore}</dd>
                </Tip>
              )}
              <Tip label={t('pointsSplitHint')}>
                <dd className="mt-auto grid grid-cols-[minmax(0,1fr)_auto_auto] items-center pt-2 gap-x-3 gap-y-1 text-sm">
                  <span />
                  <span className="text-center text-xs text-muted-foreground">{t('pointsDirectHead')}</span>
                  <span className="text-center text-xs text-muted-foreground">{t('pointsFaultsHead')}</span>
                  {GROUPS.map((g) => {
                    const split = pointSplit(rallies, g);
                    return (
                      <Fragment key={g}>
                        <span className="flex min-w-0 items-center gap-2">
                          <Swatch color={teamColor(g)} ring={teamRing(g)} />
                          <span className="truncate">{groupName(t, g)}</span>
                        </span>
                        <CountButton
                          title={(tr) => tr('pointsDirectTitle', { team: groupName(tr, g), ofTeam: ofName(groupName(tr, g)) })}
                          picked={split.direct}
                          className="h-7 justify-self-center text-sm"
                        />
                        <CountButton
                          title={(tr) => tr('pointsFaultsTitle', { team: groupName(tr, g), ofTeam: ofName(groupName(tr, g)) })}
                          picked={split.faults}
                          className="h-7 justify-self-center text-sm"
                        />
                      </Fragment>
                    );
                  })}
                </dd>
              </Tip>
            </Card>
          </dl>
        )}
        <dl className={cn('grid grid-cols-2 gap-3', !(hasTeams && score) && 'lg:grid-cols-4')}>
          {stats.map(({ label, value, more }) => (
            <Card key={label} className="gap-0.5 px-4 py-3.5 shadow-xs">
              <dt className="text-sm text-muted-foreground">{label}</dt>
              <dd className="text-2xl font-semibold tabular-nums sm:text-3xl">{value}</dd>
              {more && <dd className="text-sm text-muted-foreground">{more}</dd>}
            </Card>
          ))}
        </dl>
      </div>
    </>
  );
}
