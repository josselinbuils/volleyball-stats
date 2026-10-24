import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { LANGUAGES, setLanguage, type Language } from '@/i18n';
import { clock, useFormat } from '@/lib/format';
import { hasTeams, match } from '@/lib/match';
import { useSet } from '@/lib/sets';
import { matchTitle, tabTitle } from '@/components/Header/helpers/title';
import { SetFilter } from '@/components/Header/SetFilter';
import { TeamLegend } from '@/components/Header/TeamLegend';
import { ThemeSwitch } from '@/components/Header/ThemeSwitch';

export function Header() {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const { set, rallies, contacts } = useSet();

  const tab = tabTitle(t, f);
  useEffect(() => {
    document.title = tab;
  }, [tab]);

  // A set lasts from its first serve to its last ball.
  const span = set === null ? match.duration : rallies.length ? rallies[rallies.length - 1].end - rallies[0].start : 0;
  const inPlay = rallies.reduce((sum, r) => sum + r.end - r.start, 0);
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
      value: f.num(contacts.length),
      more: rallies.length ? t('perRally', { n: f.dec(contacts.length / rallies.length) }) : undefined,
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
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              spacing={0}
              value={i18n.language}
              onValueChange={(lang) => {
                if (lang) {
                  setLanguage(lang as Language);
                }
              }}
              aria-label={`${t('language')} / ${i18n.language === 'fr' ? 'Language' : 'Langue'}`}
              className="shrink-0 bg-card"
            >
              {Object.entries(LANGUAGES).map(([code, name]) => (
                <ToggleGroupItem key={code} value={code} lang={code} aria-label={name} className="px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                  {code.toUpperCase()}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </div>
        </div>
        <div className="-mt-3 grid gap-2.5">
          <p className="text-muted-foreground">{t(hasTeams ? 'intro' : 'introSides')}</p>
          {hasTeams && <TeamLegend />}
        </div>
      </header>
      <SetFilter />
      <dl className="grid grid-cols-2 gap-3 px-1 lg:grid-cols-4">
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
