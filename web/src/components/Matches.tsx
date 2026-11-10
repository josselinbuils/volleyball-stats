import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Tabs } from '@/components/Tabs';
import { Behind } from '@/components/Behind';
import { BrandBar } from '@/components/BrandBar';
import { LanguageSwitch } from '@/components/LanguageSwitch';
import { Season } from '@/components/Season/Season';
import { seasonTeams } from '@/components/Season/helpers/season';
import { Swatch } from '@/components/Swatch';
import { ThemeSwitch } from '@/components/ThemeSwitch';
import { useFormat } from '@/lib/format';
import { openMatch, pullMatch } from '@/lib/openMatch';
import { withRemote } from '@/lib/remoteMatches';
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
  /** The build's hash, in its data.js's URL. */
  v?: string | null;
  /** In the review: whether its pipeline has ended, so that it can be opened. */
  ready?: boolean;
  /** In the review: only on the server, to download. */
  remote?: boolean;
  /** In the review: its video is not on this machine. */
  missing?: 'video' | 'court';
}

export interface MatchList {
  matches: ListedMatch[];
  brand: Brand | null;
  /** Listed by the review server: a card opens the match's review there. */
  review?: boolean;
}

declare global {
  interface Window {
    VolleyAppBundle?: { mount: (element: HTMLElement) => void };
  }
}

/** The match pages, newest first, each a card linking to it. In the review, the app's screens above them (app.js):
 * importing a match and preparing it until its review opens. */
// The season's own address: the list's with this hash.
const SEASON = '#saison';

export function Matches({ matches: here, brand, review = false }: MatchList) {
  const { t } = useTranslation();
  const f = useFormat();
  // In the review, the matches only on the server, asked after the page shows: reaching it takes a second.
  const [remote, setRemote] = useState<ListedMatch[]>([]);
  useEffect(() => {
    if (review) {
      fetch('remote.json')
        .then((r) => (r.ok ? (r.json() as Promise<ListedMatch[]>) : []))
        .then(setRemote)
        .catch(() => setRemote([]));
    }
  }, [review]);
  const matches = remote.length ? withRemote(here, remote) : here;
  // The matches being prepared show in the app's screens.
  const listed = review ? matches.filter((m) => m.ready || m.remote || m.missing) : matches;
  const setup = useRef<HTMLDivElement>(null);
  const loaded = useRef(false);
  useEffect(() => {
    if (!review || loaded.current) {
      return;
    }
    loaded.current = true;
    const script = document.createElement('script');
    script.src = 'app.js';
    script.onload = () => setup.current && window.VolleyAppBundle?.mount(setup.current);
    document.head.append(script);
  }, [review]);
  const [opening, setOpening] = useState<string | null>(null);
  const [failed, setFailed] = useState<'open' | 'pull' | null>(null);
  const hasSeason = seasonTeams(matches).length > 0;
  const [view, setView] = useState<'matches' | 'season'>(() => (hasSeason && location.hash === SEASON ? 'season' : 'matches'));
  const open = (name: string, remote = false) => {
    setOpening(name);
    setFailed(null);
    (remote ? pullMatch(name) : openMatch(name)).catch(() => {
      setOpening(null);
      setFailed(remote ? 'pull' : 'open');
    });
  };
  const heading = t('matches.heading');
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
            {failed && (
              <p className="mt-1 text-sm text-destructive" role="alert">
                {t(failed === 'pull' ? 'matches.pullFailed' : 'matches.openFailed')}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2 sm:flex-row">
            <ThemeSwitch />
            <LanguageSwitch />
          </div>
        </header>
        {review && <Behind />}
        {review && <div ref={setup} />}
        {hasSeason && (
          <Tabs
            label={t('season.view')}
            value={view}
            onChange={(v) => {
              setView(v);
              history.replaceState(null, '', v === 'season' ? SEASON : location.pathname + location.search);
            }}
            tabs={[
              { id: 'matches', label: t('matches.title') },
              { id: 'season', label: t('season.title') },
            ]}
          />
        )}
        <p className="px-1 text-muted-foreground">{t(view === 'season' ? 'season.intro' : review ? 'matches.pick' : 'matches.intro')}</p>
        {view === 'season' ? (
          <Season matches={matches} />
        ) : listed.length ? (
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {listed.map((m) => {
              const names = m.teams?.map((team, k) => team.name ?? t('team', { n: k + 1 }));
              const scores = (m.scores ?? []).filter(Boolean);
              // From the disk, a folder opens as a file listing: its page is named.
              return (
                <li key={m.path}>
                  <a
                    href={location.protocol === 'file:' ? `${m.path}index.html` : m.path}
                    aria-disabled={review && (!(m.ready || m.remote) || opening !== null)}
                    onClick={
                      review
                        ? (event) => {
                            event.preventDefault();
                            if ((m.ready || m.remote) && opening === null) {
                              open(m.path, m.remote);
                            }
                          }
                        : undefined
                    }
                    className={cn(
                      'group block h-full rounded-[10px] outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                      review && !m.ready && 'opacity-60',
                      review && !m.ready && !m.remote && 'cursor-default',
                    )}
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
                          opening === m.path && t(m.remote ? 'matches.pulling' : 'matches.opening'),
                          review && opening !== m.path && m.remote && t('matches.toPull'),
                          review && m.missing && t(m.missing === 'video' ? 'matches.noVideo' : 'matches.noCourt'),
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
