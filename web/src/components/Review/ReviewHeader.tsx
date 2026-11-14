import { Fragment, useState, type ReactNode } from 'react';
import {
  Check,
  ChevronDown,
  CircleMinus,
  CirclePlus,
  CircleStop,
  Clapperboard,
  CloudDownload,
  CloudUpload,
  DatabaseBackup,
  Ellipsis,
  FolderDown,
  ExternalLink,
  History,
  LoaderCircle,
  RefreshCw,
  Shield,
  Sparkles,
  Undo2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ask } from '@/components/ask';
import { ErrorNote } from '@/components/ErrorNote';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { clock, useFormat } from '@/lib/format';
import { match } from '@/lib/match';
import { openMatch } from '@/lib/openMatch';
import { cn } from '@/lib/utils';
import { review, type Backup, type FilmCounts, type Hosted } from '@/lib/review';
import { ClubDialog } from '@/components/ClubDialog';
import { ExportDialog } from '@/components/ExportSite';
import { HostChoice } from '@/components/Review/HostChoice';
import { LateCauses } from '@/components/LateCauses';
import { Tip } from '@/components/Tip';
import type { Due } from '@/components/Update';
import { BackLink } from '@/components/BackLink';

type Action = 'undo' | 'apply' | 'sets' | 'host' | 'hostAll' | 'reports' | 'films' | 'film' | 'highlights';
type Listed = { path: string; title: string | null; name: string; teams: { name: string | null }[] | null; date: string | null; ready: boolean };

/** Between two items of the status line, which wraps on a phone. */
function Dot() {
  return (
    <span aria-hidden className="max-sm:hidden">
      ·
    </span>
  );
}

/** Ends the match where the video stood when the menu opened. */
function MatchEndItem({ at, onEnd }: { at: () => number; onEnd: (time: string) => void }) {
  const { t } = useTranslation();
  const [time] = useState(() => clock(at()));
  return (
    <DropdownMenuItem onSelect={() => void ask({ title: t('review.matchEndAt', { time }), text: t('review.matchEndAsk', { time }), confirm: t('app.confirm') }).then((yes) => yes && onEnd(time))}>
      <CircleStop aria-hidden />
      {t('review.matchEndAt', { time })}
    </DropdownMenuItem>
  );
}

/** Starts a set at the rally playing where the video stood when the menu opened, or takes away the start of the set it
 * stood in; the analysis runs again. */
function SetItems({ at, starts, onSet }: { at: () => number; starts: string[]; onSet: (change: { add: number } | { remove: string }) => void }) {
  const { t } = useTranslation();
  const [seconds] = useState(at);
  const time = clock(seconds);
  const n = starts.filter((s) => toSeconds(s) <= seconds).length;
  return (
    <>
      <DropdownMenuItem
        onSelect={() => void ask({ title: t('review.setStartAt', { time }), text: t('review.setStartAsk', { time }), confirm: t('app.confirm') }).then((yes) => yes && onSet({ add: seconds }))}
      >
        <CirclePlus aria-hidden />
        {t('review.setStartAt', { time })}
      </DropdownMenuItem>
      {n > 1 && (
        <DropdownMenuItem
          onSelect={() =>
            void ask({ title: t('review.setRemove', { n }), text: t('review.setRemoveAsk', { n, previous: n - 1 }), confirm: t('app.confirm') }).then((yes) => yes && onSet({ remove: starts[n - 1] }))
          }
        >
          <CircleMinus aria-hidden />
          {t('review.setRemove', { n })}
        </DropdownMenuItem>
      )}
    </>
  );
}

/** Seconds of a time written m:ss or h:mm:ss. */
function toSeconds(time: string): number {
  return time.split(':').reduce((total, part) => total * 60 + Number(part), 0);
}

/** The match's name, opening the list of the others to go to one of them. */
function MatchSwitch({ title, disabled, mayLeave, onFailed }: { title: string; disabled: boolean; mayLeave: () => Promise<boolean>; onFailed: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [matches, setMatches] = useState<Listed[] | 'failed' | null>(null);
  const [opening, setOpening] = useState(false);
  const load = (open: boolean) => {
    if (open) {
      fetch('/matches.json')
        .then((response) => (response.ok ? (response.json() as Promise<Listed[]>) : Promise.reject(new Error(`matches: ${response.status}`))))
        .then(setMatches)
        .catch(() => setMatches((m) => (Array.isArray(m) ? m : 'failed')));
    }
  };
  const go = async (path: string) => {
    if (!(await mayLeave())) {
      return;
    }
    setOpening(true);
    openMatch(path).catch(() => {
      setOpening(false);
      onFailed();
    });
  };
  return (
    <DropdownMenu onOpenChange={load}>
      <Tip label={t('review.otherMatch')}>
        <DropdownMenuTrigger
          disabled={disabled || opening}
          aria-label={t('review.otherMatch')}
          className="group -mx-1 inline-flex min-w-0 items-center gap-1.5 rounded-lg px-1 text-left outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60"
        >
          <h1 className="min-w-0 text-2xl font-semibold tracking-tight [overflow-wrap:anywhere]">{opening ? t('matches.opening') : title}</h1>
          <ChevronDown aria-hidden className="size-5 shrink-0 text-muted-foreground" />
        </DropdownMenuTrigger>
      </Tip>
      <DropdownMenuContent align="start">
        {matches === null && (
          <DropdownMenuItem disabled>
            <LoaderCircle aria-hidden className="animate-spin" />
            {t('review.matchesLoading')}
          </DropdownMenuItem>
        )}
        {matches === 'failed' && <ErrorNote text={t('error.loadFailed')} className="px-2 py-1.5" />}
        {Array.isArray(matches) &&
          matches.map((m) => (
            <DropdownMenuItem key={m.path} disabled={!m.ready} onSelect={() => m.path !== match.name && void go(m.path)}>
              <Check aria-hidden className={cn(m.path !== match.name && 'invisible')} />
              <span className="grid min-w-0">
                <span className="truncate">{m.title ?? (m.teams ? t('matchTitle', { one: m.teams[0].name, two: m.teams[1].name }) : m.name)}</span>
                <span className="text-xs text-muted-foreground">{m.ready ? m.date && f.date(m.date) : t('matches.processing')}</span>
              </span>
            </DropdownMenuItem>
          ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <a href="/matches/">{t('review.allMatches')}</a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The review's title, its actions, the main one standing out, and on one line where things stand. */
export function ReviewHeader({
  title,
  answered,
  hosted,
  backup,
  backingUp = false,
  onBackup,
  onAutoBackup,
  fetched,
  filmsError,
  films,
  pending,
  busy,
  run,
  mayLeave,
  due,
  onUpdate,
  here,
  onFailed,
}: {
  title: string;
  answered: number;
  hosted?: Hosted | null;
  /** The copies on the hosting server, none without one. */
  backup?: Backup | null;
  /** A copy asked for is being made. */
  backingUp?: boolean;
  /** Makes a copy now. */
  onBackup?: () => void;
  /** Switches the copies every 10 minutes on or off. */
  onAutoBackup?: (on: boolean) => void;
  fetched?: { at: string; count: number; error: string | null } | null;
  filmsError?: string | null;
  films: FilmCounts;
  pending: { answers: number; changed: boolean; names: boolean };
  /** What runs: one of the actions, or the app's update. */
  busy: Action | 'update' | null;
  run: (action: Action, body?: object) => void;
  /** Why the match waits for the app's update, null when up to date; `onUpdate` starts it. */
  due?: Due | null;
  onUpdate?: () => void;
  /** Whether the page may go, corrections not saved being lost. */
  mayLeave: () => Promise<boolean>;
  /** On the Match tab: where the video stands, ending the match there (taken away with ''), and the set starts to change
   * there. */
  here?: { at: () => number; onEnd: (time: string) => void; sets: string[]; onSet: (change: { add: number } | { remove: string }) => void };
  onFailed: () => void;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const [choosing, setChoosing] = useState(false);
  const toApply = pending.changed || pending.names;
  // Where things stand, each item only while it has something to say.
  const status: ReactNode[] = [];
  if (backup && (backingUp || backup.at)) {
    status.push(
      <Tip label={backup.error ?? undefined}>
        <span className={cn('inline-flex items-center gap-1.5', backup.error && !backingUp && 'text-destructive')}>
          {backingUp ? t('review.backingUp') : backup.error ? t(backup.auto ? 'review.backupFailed' : 'review.backupFailedOnce', { at: backup.at }) : t('review.savedAt', { at: backup.at })}
          {backup.error && onBackup && (
            <Button variant="outline" size="sm" className="ml-1.5 bg-card" busy={backingUp} onClick={onBackup}>
              <RefreshCw aria-hidden />
              {t('review.backupRetry')}
            </Button>
          )}
        </span>
      </Tip>,
    );
  }
  if (fetched) {
    status.push(
      <Tip label={fetched.error ?? undefined}>
        <span className={cn(fetched.error && 'text-destructive')}>{fetched.error ? t('review.fetchFailed', { at: fetched.at }) : t('review.fetched', { count: fetched.count, at: fetched.at })}</span>
      </Tip>,
    );
  }
  if (filmsError) {
    status.push(
      <Tip label={filmsError}>
        <span className="text-destructive">{t('review.filmsFailed')}</span>
      </Tip>,
    );
  }
  if (hosted) {
    status.push(
      <Tip label={hosted.error ?? (hosted.behind && hosted.changes?.length ? <LateCauses changes={hosted.changes} /> : undefined)}>
        <span className={cn('inline-flex items-center gap-1.5', hosted.error && 'text-destructive')}>
          {hosted.behind && !hosted.error && <span aria-hidden className="size-2 shrink-0 rounded-full bg-primary" />}
          {hosted.error
            ? t('review.hostedFailed', { at: hosted.at })
            : hosted.behind
              ? t('review.hostedLate')
              : hosted.day
                ? t('review.hostedDay', { day: f.date(hosted.day), at: hosted.at })
                : t('review.hosted', { at: hosted.at })}
          {(hosted.behind || hosted.error) && (
            <Button variant="outline" size="sm" className="ml-1.5 bg-card" busy={busy === 'host'} disabled={busy !== null} onClick={() => (hosted.chosen ? run('host') : setChoosing(true))}>
              <CloudUpload aria-hidden />
              {busy === 'host' ? t('review.hosting') : t('review.host')}
            </Button>
          )}
        </span>
      </Tip>,
    );
  }
  if (due) {
    status.push(
      <Tip label={t(`update.why.${due}`)}>
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="size-2 shrink-0 rounded-full bg-primary" />
          {t('update.badge')}
          <Button variant="outline" size="sm" className="ml-1.5 bg-card" busy={busy === 'update'} disabled={busy !== null} onClick={onUpdate}>
            <RefreshCw aria-hidden />
            {t('update.start')}
          </Button>
        </span>
      </Tip>,
    );
  }
  // The menu's groups: the match's end on the Match tab, the uploads, export and films, the copies.
  const [clubOpen, setClubOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  return (
    <header className="grid gap-1.5 px-1">
      <BackLink href="/matches/" label={t('review.allMatches')} className="mb-1.5" />
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 items-center gap-1">
          <MatchSwitch title={title} disabled={busy !== null} mayLeave={mayLeave} onFailed={onFailed} />
          <Button variant="ghost" size="icon" asChild>
            <Tip label={t('review.matchPage')}>
              <a href="page" aria-label={t('review.matchPage')}>
                <ExternalLink aria-hidden />
              </a>
            </Tip>
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Tip label={t('review.undo')}>
            <Button
              variant="ghost"
              size="icon"
              aria-label={busy === 'undo' ? t('review.undoing') : t('review.undo')}
              busy={busy === 'undo'}
              disabled={!answered || busy !== null}
              onClick={() => run('undo')}
            >
              <Undo2 aria-hidden />
            </Button>
          </Tip>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Tip label={t('review.more')}>
                <Button variant="ghost" size="icon" aria-label={t('review.more')} disabled={busy !== null}>
                  <Ellipsis aria-hidden />
                </Button>
              </Tip>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {here && (
                <>
                  <SetItems at={here.at} starts={here.sets} onSet={here.onSet} />
                  <MatchEndItem at={here.at} onEnd={here.onEnd} />
                  {review?.matchEnd && (
                    <DropdownMenuItem onSelect={() => here.onEnd('')}>
                      <Undo2 aria-hidden />
                      {t('review.matchEndRemove', { time: review.matchEnd })}
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                </>
              )}
              {hosted && (
                <Tip label={t('review.fetchNote')}>
                  <DropdownMenuItem onSelect={() => run('reports')}>
                    <CloudDownload aria-hidden />
                    {t('review.fetch')}
                  </DropdownMenuItem>
                </Tip>
              )}
              {hosted?.chosen && (
                <DropdownMenuItem onSelect={() => run('hostAll')}>
                  <CloudUpload aria-hidden />
                  {t('review.hostAll')}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onSelect={() => setExportOpen(true)}>
                <FolderDown aria-hidden />
                {t('export.title')}
              </DropdownMenuItem>
              {films.players.total > 0 && (
                <DropdownMenuItem disabled={!films.players.stale.length} onSelect={() => run('films')}>
                  <Clapperboard aria-hidden />
                  {films.players.stale.length ? t('review.films', { count: films.players.stale.length }) : t('review.filmsDone')}
                </DropdownMenuItem>
              )}
              {films.highlights.total > 0 && (
                <DropdownMenuItem disabled={!films.highlights.stale.length} onSelect={() => run('highlights')}>
                  <Sparkles aria-hidden />
                  {films.highlights.stale.length ? t('review.highlights') : t('review.highlightsDone')}
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setClubOpen(true)}>
                <Shield aria-hidden />
                {t('app.club.open')}
              </DropdownMenuItem>
              {backup && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem disabled={backingUp} onSelect={onBackup}>
                    <DatabaseBackup aria-hidden />
                    {t('review.backUp')}
                  </DropdownMenuItem>
                  <DropdownMenuCheckboxItem checked={backup.auto} onCheckedChange={(on) => onAutoBackup?.(on === true)}>
                    <History aria-hidden />
                    {t('review.autoBackup')}
                  </DropdownMenuCheckboxItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          {toApply || busy === 'apply' ? (
            <Button busy={busy === 'apply'} disabled={busy !== null} onClick={() => run('apply')}>
              <Check aria-hidden />
              {busy === 'apply'
                ? t('review.applying')
                : pending.names
                  ? t(pending.changed ? 'review.applyBoth' : 'review.applyNames')
                  : pending.answers
                    ? t('review.apply', { count: pending.answers })
                    : t('review.applyChanges')}
            </Button>
          ) : (
            <span className="inline-flex items-center gap-1.5 pl-1 text-sm text-muted-foreground">
              <Check aria-hidden className="size-4" />
              {t('review.applied')}
            </span>
          )}
        </div>
      </div>
      {status.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-muted-foreground max-sm:gap-x-3" aria-live="polite">
          {status.map((item, k) => (
            <Fragment key={k}>
              {k > 0 && <Dot />}
              {item}
            </Fragment>
          ))}
        </div>
      )}
      {choosing && (
        <HostChoice
          onChoose={(body) => {
            setChoosing(false);
            run('host', body);
          }}
          onCancel={() => setChoosing(false)}
        />
      )}
      {clubOpen && <ClubDialog onClose={() => setClubOpen(false)} />}
      {exportOpen && <ExportDialog onClose={() => setExportOpen(false)} />}
    </header>
  );
}
