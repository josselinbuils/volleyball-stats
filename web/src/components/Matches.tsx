import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { BrandBar } from '@/components/BrandBar';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { Swatch } from '@/components/Swatch';
import { ThemeSwitch } from '@/components/ThemeSwitch';
import { useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Brand, Team } from '@/lib/match';

/** A match as matches.js lists it: its page's folder, and from its data.js what the list shows. */
export interface ListedMatch {
  path: string;
  name: string;
  date: string | null;
  title: string | null;
  teams: [Team, Team] | null;
  /** Each set's final score as the user gave it, "25-21" team 1 first, null when unknown. */
  scores: (string | null)[] | null;
  sets: number;
  rallies: number;
  /** In the review: whether its pipeline has ended, so that it can be opened. */
  ready?: boolean;
}

export interface MatchList {
  matches: ListedMatch[];
  brand: Brand | null;
  /** Listed by the review server: a card opens the match's review there. */
  review?: boolean;
}

/** Asks the review server to open the match `name`, then goes to its review once the server has restarted on it. */
async function openReview(name: string): Promise<void> {
  const response = await fetch('/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
  if (!response.ok) {
    throw new Error(`open: ${response.status}`);
  }
  const giveUp = Date.now() + 5 * 60_000;
  while (Date.now() < giveUp) {
    try {
      const current = (await (await fetch('/current')).json()) as { name: string | null };
      if (current.name === name) {
        location.href = '/review';
        return;
      }
    } catch {
      // Not listening yet: the server is restarting.
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error('open: timed out');
}

/** The match pages, newest first, each a card linking to it. */
export function Matches({ matches, brand, review = false }: MatchList) {
  const { t } = useTranslation();
  const f = useFormat();
  const [opening, setOpening] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const open = (name: string) => {
    setOpening(name);
    setFailed(false);
    openReview(name).catch(() => {
      setOpening(null);
      setFailed(true);
    });
  };
  const heading = t('matches.title');
  useEffect(() => {
    document.title = brand ? `${heading} · ${brand.name}` : heading;
  }, [heading, brand]);

  return (
    <>
      <BrandBar brand={brand} />
      <main className="mx-auto grid w-full max-w-6xl gap-5 px-4 pt-8 pb-16 max-sm:gap-4 max-sm:pt-5">
        <header className="flex items-start justify-between gap-4 px-1">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{heading}</h1>
            <p className="mt-1 text-muted-foreground">{t(review ? 'matches.pick' : 'matches.intro')}</p>
            {failed && (
              <p className="mt-1 text-sm text-destructive" role="alert">
                {t('matches.openFailed')}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2 sm:flex-row">
            <ThemeSwitch />
            <LanguageSwitch />
          </div>
        </header>
        {matches.length ? (
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {matches.map((m) => {
              const names = m.teams?.map((team, k) => team.name ?? t('team', { n: k + 1 }));
              const scores = (m.scores ?? []).filter(Boolean);
              // From the disk, a folder opens as a file listing: its page is named.
              return (
                <li key={m.path}>
                  <a
                    href={location.protocol === 'file:' ? `${m.path}index.html` : m.path}
                    aria-disabled={review && (!m.ready || opening !== null)}
                    onClick={
                      review
                        ? (event) => {
                            event.preventDefault();
                            if (m.ready && opening === null) {
                              open(m.path);
                            }
                          }
                        : undefined
                    }
                    className={cn('group block h-full rounded-[10px] outline-none focus-visible:ring-3 focus-visible:ring-ring/50', review && !m.ready && 'cursor-default opacity-60')}
                  >
                    <Card className="h-full gap-1.5 px-4 py-3.5 transition-colors group-hover:bg-muted">
                      {m.date && (
                        <time dateTime={m.date} className="text-sm font-medium text-muted-foreground">
                          {f.date(m.date)}
                        </time>
                      )}
                      <h2 className="text-lg leading-snug font-semibold [overflow-wrap:anywhere] group-hover:underline">
                        {m.title ?? (names ? t('matchTitle', { one: names[0], two: names[1] }) : m.name)}
                      </h2>
                      {m.teams && names && (
                        <span className="flex flex-wrap gap-x-4 gap-y-1">
                          {m.teams.map((team, k) => (
                            <span key={k} className="inline-flex min-w-0 items-center gap-2">
                              <Swatch color={team.colour} ring="var(--border)" />
                              <span className="truncate">{names[k]}</span>
                            </span>
                          ))}
                        </span>
                      )}
                      <span className="text-sm text-muted-foreground tabular-nums">
                        {[
                          m.sets > 0 && t('matches.setsN', { count: m.sets }),
                          m.rallies > 0 && t('ralliesN', { count: m.rallies }),
                          scores.length > 0 && scores.join(' · '),
                          opening === m.path && t('matches.opening'),
                          review && !m.ready && t('matches.processing'),
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </Card>
                  </a>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="px-1 text-muted-foreground">{t('matches.none')}</p>
        )}
      </main>
    </>
  );
}
