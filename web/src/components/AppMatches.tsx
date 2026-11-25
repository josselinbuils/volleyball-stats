import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { JobProgress } from '@/components/JobProgress';
import { ListPage, ListTabs, MatchCards, useListTab, type ListTab, type ListedMatch, type MatchList } from '@/components/Matches';
import { Tasks, taskLabel } from '@/components/Tasks';
import { Behind } from '@/components/Behind';
import { NewReports } from '@/components/NewReports';
import { ProgressTab } from '@/components/Progress/Progress';
import { Season } from '@/components/Season/Season';
import { seasonTeams } from '@/components/Season/helpers/season';
import { Setup } from '@/components/Setup/Setup';
import { SiteTab } from '@/components/SiteTab';
import { openMatch, pullMatch } from '@/lib/openMatch';
import { withRemote } from '@/lib/remoteMatches';
import { useTasks } from '@/lib/tasks';

type View = 'matches' | 'season' | 'progress' | 'site';

/** The review server's list of the matches: the app's screens (importing a match and preparing it until its review opens),
 * the matches, a card opening its review, and the tabs of the site and the progress. Part of app.js, never online. */
export function AppMatches({ matches: here, club }: MatchList) {
  const { t } = useTranslation();
  // The matches only on the server, asked after the page shows: reaching it takes a second.
  const [remote, setRemote] = useState<ListedMatch[]>([]);
  useEffect(() => {
    fetch('remote.json')
      .then((r) => (r.ok ? (r.json() as Promise<ListedMatch[]>) : []))
      .then(setRemote)
      .catch(() => setRemote([]));
  }, []);
  const matches = remote.length ? withRemote(here, remote) : here;
  // The matches being prepared show in the app's screens.
  const listed = matches.filter((m) => m.ready || m.remote || m.missing);
  // The app's tasks: a match's own shows on its card.
  const tasks = useTasks();
  const [opening, setOpening] = useState<string | null>(null);
  const [failed, setFailed] = useState<'open' | 'pull' | 'busy' | null>(null);
  const tabs: ListTab<View>[] = [
    { id: 'matches', hash: '', label: t('matches.title') },
    ...(seasonTeams(matches, club?.teams).length ? [{ id: 'season' as const, hash: '#saison', label: t('season.title') }] : []),
    { id: 'progress', hash: '#progres', label: t('progress.tab') },
    { id: 'site', hash: '#site', label: t('server.title') },
  ];
  const [view, setView] = useListTab(tabs);
  const open = (name: string, remote = false) => {
    setOpening(name);
    setFailed(null);
    (remote ? pullMatch(name) : openMatch(name)).catch((error: Error) => {
      setOpening(null);
      setFailed(remote ? 'pull' : error.message === 'busy' ? 'busy' : 'open');
    });
  };

  return (
    <>
      <ListPage
        club={club}
        note={failed && <ErrorNote text={t({ pull: 'matches.pullFailed', busy: 'error.busy', open: 'matches.openFailed' }[failed])} log={failed !== 'busy'} className="mt-1 text-sm" />}
      >
        <Behind />
        <NewReports />
        <Setup />
        <ListTabs tabs={tabs} value={view} onChange={setView} />
        <p className="px-1 text-muted-foreground">{t({ site: 'server.intro', progress: 'progress.intro', season: 'season.intro', matches: 'matches.pick' }[view])}</p>
        {/* Kept while hidden: their state stays as the tabs switch. */}
        <div className={view === 'site' ? undefined : 'hidden'}>
          <SiteTab />
        </div>
        <div className={view === 'progress' ? undefined : 'hidden'}>
          <ProgressTab />
        </div>
        {view === 'site' || view === 'progress' ? null : view === 'season' ? (
          <Season matches={matches} club={club?.teams} />
        ) : (
          <MatchCards
            matches={listed}
            state={(m) => {
              // A card waits for its pipeline, and all wait while one opens.
              const busy = opening === m.path;
              const task = tasks.find((x) => x.running && x.match === m.path);
              const clickable = (m.ready || m.remote) && opening === null;
              return {
                clickable,
                busy,
                dim: !m.ready || (opening !== null && !busy),
                onOpen: () => open(m.path, m.remote),
                status: busy && (
                  <span role="status" className="ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium">
                    <LoaderCircle aria-hidden className="size-3.5 animate-spin" />
                    {t(m.remote ? 'matches.pulling' : 'matches.opening')}
                  </span>
                ),
                notes: [!busy && m.remote && t('matches.toPull'), m.missing && t(m.missing === 'video' ? 'matches.noVideo' : 'matches.noCourt')],
                children: (
                  <>
                    {task && (
                      <JobProgress label={taskLabel(t, task)} fraction={task.fraction ?? null} left={task.left} battery={task.battery} task={task.id} className="mt-1">
                        {taskLabel(t, task)}
                      </JobProgress>
                    )}
                    {m.due && !m.remote && (
                      <span className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground">
                        <span aria-hidden className="size-2 shrink-0 rounded-full bg-primary" />
                        {t(`update.short.${m.due}`)}
                      </span>
                    )}
                  </>
                ),
              };
            }}
          />
        )}
      </ListPage>
      <Tasks />
    </>
  );
}
