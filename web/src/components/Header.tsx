import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { LANGUAGES, setLanguage, type Language } from '@/i18n';
import { clock, useFormat } from '@/lib/format';
import { contacts, match, rallies } from '@/lib/match';

export function Header() {
  const { t, i18n } = useTranslation();
  const f = useFormat();

  useEffect(() => {
    document.title = `${match.name} · ${t('report')}`;
  }, [t]);

  const inPlay = rallies.reduce((sum, r) => sum + r.end - r.start, 0);
  const stats = [
    { label: t('duration'), value: clock(match.duration) },
    { label: t('ralliesStat'), value: f.num(rallies.length) },
    { label: t('inPlay'), value: clock(inPlay), more: t('ofVideo', { p: f.pct(inPlay / match.duration) }) },
    {
      label: t('contactsStat'),
      value: f.num(contacts.length),
      more: rallies.length ? t('perRally', { n: f.dec(contacts.length / rallies.length) }) : undefined,
    },
  ];

  return (
    <header className="grid gap-6 px-1">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-muted-foreground">{t('report')}</p>
          <h1 className="mt-0.5 text-2xl font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-3xl">{match.name}</h1>
        </div>
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
      <p className="-mt-3 max-w-2xl text-muted-foreground">{t('intro')}</p>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map(({ label, value, more }) => (
          <Card key={label} className="gap-0.5 px-4 py-3.5 shadow-xs">
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="text-2xl font-semibold tabular-nums sm:text-3xl">{value}</dd>
            {more && <dd className="text-sm text-muted-foreground">{more}</dd>}
          </Card>
        ))}
      </dl>
    </header>
  );
}
