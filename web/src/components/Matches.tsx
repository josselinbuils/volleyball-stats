import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Tabs } from '@/components/Tabs';
import type { Due } from '@/components/Update';
import type { FirstState } from '@/components/Setup/helpers/setup';
import { ClubBar } from '@/components/ClubBar';
import { Season } from '@/components/Season/Season';
import { seasonTeams } from '@/components/Season/helpers/season';
import { Swatch } from '@/components/Swatch';
import { Settings } from '@/components/Settings';
import { useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Club, Team } from '@/lib/match';
import { windowTitle } from '@/lib/appServer';

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
  /** In the review: why it waits for the update, null when up to date. */
  due?: Due | null;
}

export interface MatchList {
  matches: ListedMatch[];
  club: Club | null;
  /** Listed by the review server: the app's script (app.js) shows the list, a card opening the match's review there. */
  review?: boolean;
  /** The review server's: the guided first run (`FirstState`), shown with the list. */
  first?: FirstState;
}

/** A tab of the list: its id, its address (the list's with this hash) and its name. */
export type ListTab<T extends string> = { id: T; hash: string; label: string };

/** The tab shown among `tabs`, the one the address names (the first otherwise), and its switch, which the address follows:
 * a link to a tab (the copies' warning opens the server's) switches to it. */
export function useListTab<T extends string>(tabs: ListTab<T>[]): [T, (id: T) => void] {
  const named = () => (tabs.find((tab) => tab.hash && location.hash === tab.hash) ?? tabs[0]).id;
  const [tab, setTab] = useState<T>(named);
  useEffect(() => {
    const follow = () => setTab(named());
    window.addEventListener('hashchange', follow);
    return () => window.removeEventListener('hashchange', follow);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the tabs shown, not the array made each render
  }, [tabs.map((t) => t.id).join()]);
  const pick = (id: T) => {
    setTab(id);
    history.replaceState(null, '', tabs.find((t) => t.id === id)?.hash || location.pathname + location.search);
  };
  return [tab, pick];
}

/** The list's page: the club's band, the heading with `note` under it, then `children`. */
export function ListPage({ club, note, children }: { club: Club | null; note?: ReactNode; children: ReactNode }) {
  const { t } = useTranslation();
  const heading = t('matches.heading');
  useEffect(() => {
    document.title = windowTitle(club ? `${heading} · ${club.name}` : heading);
  }, [heading, club]);
  return (
    <>
      <ClubBar club={club} />
      <main className="mx-auto grid w-full max-w-6xl gap-5 px-4 pt-8 pb-16 max-sm:gap-4 max-sm:pt-5">
        <header className="flex items-start justify-between gap-4 px-1">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{heading}</h1>
            {note}
          </div>
          {!club && <Settings />}
        </header>
        {children}
      </main>
    </>
  );
}

/** The list's tabs, when there are several. */
export function ListTabs<T extends string>({ tabs, value, onChange }: { tabs: ListTab<T>[]; value: T; onChange: (id: T) => void }) {
  const { t } = useTranslation();
  return tabs.length > 1 ? <Tabs label={t('matches.sections')} value={value} onChange={onChange} tabs={tabs} /> : null;
}

/** What a card of the list shows beside its match, in the review: whether it opens, its state, its notes and below them `children`. */
export type CardState = { clickable?: boolean; dim?: boolean; busy?: boolean; status?: ReactNode; notes?: (string | false | undefined)[]; onOpen?: () => void; children?: ReactNode };

/** A match's card, a link to its page. */
export function MatchCard({ m, clickable = true, dim = false, busy = false, status, notes = [], onOpen, children }: { m: ListedMatch } & CardState) {
  const { t } = useTranslation();
  const f = useFormat();
  const names = m.teams?.map((team, k) => team.name ?? t('team', { n: k + 1 }));
  const scores = (m.scores ?? []).filter(Boolean);
  // From the disk, a folder opens as a file listing: its page is named.
  return (
    <a
      href={location.protocol === 'file:' ? `${m.path}index.html` : m.path}
      aria-disabled={!clickable}
      aria-busy={busy || undefined}
      onClick={
        onOpen
          ? (event) => {
              event.preventDefault();
              if (clickable) {
                onOpen();
              }
            }
          : undefined
      }
      className={cn('group block h-full rounded-[10px] outline-none focus-visible:ring-3 focus-visible:ring-ring/50', dim && 'opacity-60', busy ? 'cursor-wait' : !clickable && 'cursor-default')}
    >
      <Card className={cn('h-full gap-1.5 px-4 py-3.5 transition-colors', clickable && 'group-hover:bg-muted')}>
        {(m.date || status) && (
          <div className="flex items-center gap-2">
            {m.date && (
              <time dateTime={m.date} className="text-sm font-medium text-muted-foreground">
                {f.date(m.date)}
              </time>
            )}
            {status}
          </div>
        )}
        <h2 className={cn('text-lg leading-snug font-semibold [overflow-wrap:anywhere]', clickable && 'group-hover:underline')}>
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
          {[m.sets > 0 && t('matches.setsN', { count: m.sets }), m.rallies > 0 && t('ralliesN', { count: m.rallies }), scores.length > 0 && scores.join(' · '), ...notes].filter(Boolean).join(' · ')}
        </span>
        {children}
      </Card>
    </a>
  );
}

/** The cards of `matches`, `state` telling each one's in the review; "no match" without any. */
export function MatchCards({ matches, state }: { matches: ListedMatch[]; state?: (m: ListedMatch) => CardState }) {
  const { t } = useTranslation();
  return matches.length ? (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {matches.map((m) => (
        <li key={m.path}>
          <MatchCard m={m} {...state?.(m)} />
        </li>
      ))}
    </ol>
  ) : (
    <p className="px-1 text-muted-foreground">{t('matches.none')}</p>
  );
}

/** The online list of the match pages, newest first, each a card linking to it, and the season's tab when there is one. */
export function Matches({ matches, club }: MatchList) {
  const { t } = useTranslation();
  const tabs: ListTab<'matches' | 'season'>[] = [
    { id: 'matches', hash: '', label: t('matches.title') },
    ...(seasonTeams(matches, club?.teams).length ? [{ id: 'season' as const, hash: '#saison', label: t('season.title') }] : []),
  ];
  const [tab, setTab] = useListTab(tabs);
  return (
    <ListPage club={club}>
      <ListTabs tabs={tabs} value={tab} onChange={setTab} />
      <p className="px-1 text-muted-foreground">{t(tab === 'season' ? 'season.intro' : 'matches.intro')}</p>
      {tab === 'season' ? <Season matches={matches} club={club?.teams} /> : <MatchCards matches={matches} />}
    </ListPage>
  );
}
