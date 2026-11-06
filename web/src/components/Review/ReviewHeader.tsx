import { useState } from 'react';
import { Check, ChevronDown, Clapperboard, CloudDownload, CloudUpload, Ellipsis, ExternalLink, RefreshCw, Sparkles, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { useFormat } from '@/lib/format';
import { match } from '@/lib/match';
import { openMatch } from '@/lib/openMatch';
import { cn } from '@/lib/utils';
import type { FilmCounts, Hosted } from '@/lib/review';
import { HostChoice } from '@/components/Review/HostChoice';
import { Tip } from '@/components/Tip';

type Action = 'undo' | 'apply' | 'rerun' | 'host' | 'hostAll' | 'reports' | 'films' | 'highlights';
type Listed = { path: string; title: string | null; name: string; teams: { name: string | null }[] | null; date: string | null; ready: boolean };

/** Between two items of the status line, which wraps on a phone. */
function Dot() {
  return <span className="mr-1.5 max-sm:hidden">·</span>;
}

/** The match's name, opening the list of the others to go to one of them. */
function MatchSwitch({ title, disabled, onFailed }: { title: string; disabled: boolean; onFailed: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [matches, setMatches] = useState<Listed[] | null>(null);
  const [opening, setOpening] = useState(false);
  const load = (open: boolean) => {
    if (open) {
      fetch('/matches.json')
        .then((response) => response.json())
        .then(setMatches)
        .catch(onFailed);
    }
  };
  const go = (path: string) => {
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
        {matches?.map((m) => (
          <DropdownMenuItem key={m.path} disabled={!m.ready} onSelect={() => m.path !== match.name && go(m.path)}>
            <Check aria-hidden className={cn(m.path !== match.name && 'invisible')} />
            <span className="grid min-w-0">
              <span className="truncate">{m.title ?? (m.teams ? t('matchTitle', { one: m.teams[0].name, two: m.teams[1].name }) : m.name)}</span>
              <span className="text-xs text-muted-foreground">{m.ready ? m.date && f.date(m.date) : t('matches.processing')}</span>
            </span>
          </DropdownMenuItem>
        ))}
        {matches && <DropdownMenuSeparator />}
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
  fetched,
  filmsError,
  films,
  pending,
  busy,
  run,
  onFailed,
}: {
  title: string;
  answered: number;
  hosted?: Hosted | null;
  backup?: { at: string; error: string | null } | null;
  /** A copy asked for is being made. */
  backingUp?: boolean;
  /** Makes a copy now. */
  onBackup?: () => void;
  fetched?: { at: string; count: number; error: string | null } | null;
  filmsError?: string | null;
  films: FilmCounts;
  pending: { answers: number; changed: boolean; names: boolean };
  busy: Action | null;
  run: (action: Action, body?: object) => void;
  onFailed: () => void;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const [choosing, setChoosing] = useState(false);
  const toApply = pending.changed || pending.names;
  const running =
    busy === 'rerun' ? t('review.rerunning') : busy === 'reports' ? t('review.fetching') : busy === 'films' ? t('review.filmsMaking') : busy === 'highlights' ? t('review.highlightsMaking') : null;
  return (
    <header className="grid gap-1.5 px-1">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 items-center gap-1">
          <MatchSwitch title={title} disabled={busy !== null} onFailed={onFailed} />
          <Button variant="ghost" size="icon" asChild>
            <Tip label={t('review.matchPage')}>
              <a href="./" aria-label={t('review.matchPage')}>
                <ExternalLink aria-hidden />
              </a>
            </Tip>
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Tip label={t('review.undo')}>
            <Button variant="ghost" size="icon" aria-label={busy === 'undo' ? t('review.undoing') : t('review.undo')} disabled={!answered || busy !== null} onClick={() => run('undo')}>
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
              <Tip label={t('review.rerunNote')}>
                <DropdownMenuItem onSelect={() => window.confirm(t('review.rerunConfirm')) && run('rerun')}>
                  <RefreshCw aria-hidden />
                  {t('review.rerun')}
                </DropdownMenuItem>
              </Tip>
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
              {films.players.total > 0 && (
                <DropdownMenuItem disabled={!films.players.stale} onSelect={() => run('films')}>
                  <Clapperboard aria-hidden />
                  {films.players.stale ? t('review.films', { count: films.players.stale }) : t('review.filmsDone')}
                </DropdownMenuItem>
              )}
              {films.highlights.total > 0 && (
                <DropdownMenuItem disabled={!films.highlights.stale} onSelect={() => run('highlights')}>
                  <Sparkles aria-hidden />
                  {films.highlights.stale ? t('review.highlights') : t('review.highlightsDone')}
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          {toApply || busy === 'apply' ? (
            <Button disabled={busy !== null} onClick={() => run('apply')}>
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
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-muted-foreground max-sm:gap-x-3" aria-live="polite">
        <span>{t('review.answers', { count: answered })}</span>
        {backup && (
          <Tip label={backup.error ?? undefined}>
            <span className={cn('inline-flex items-center gap-1.5', backup.error && 'text-destructive')}>
              <Dot />
              {backingUp ? t('review.backingUp') : backup.error ? t('review.backupFailed', { at: backup.at }) : t('review.savedAt', { at: backup.at })}
              {backup.error && onBackup && (
                <Button variant="outline" size="sm" className="ml-1.5 bg-card" disabled={backingUp} onClick={onBackup}>
                  <RefreshCw aria-hidden />
                  {t('review.backupRetry')}
                </Button>
              )}
            </span>
          </Tip>
        )}
        {fetched && (
          <Tip label={fetched.error ?? undefined}>
            <span className={cn(fetched.error && 'text-destructive')}>
              <Dot />
              {fetched.error ? t('review.fetchFailed', { at: fetched.at }) : t('review.fetched', { count: fetched.count, at: fetched.at })}
            </span>
          </Tip>
        )}
        {filmsError && (
          <Tip label={filmsError}>
            <span className="text-destructive">
              <Dot />
              {t('review.filmsFailed')}
            </span>
          </Tip>
        )}
        {running && (
          <span>
            <Dot />
            {running}
          </span>
        )}
        {hosted && (
          <Tip label={hosted.error ?? undefined}>
            <span className={cn('inline-flex items-center gap-1.5', hosted.error && 'text-destructive')}>
              <Dot />
              {hosted.behind && !hosted.error && <span aria-hidden className="size-2 shrink-0 rounded-full bg-primary" />}
              {hosted.error
                ? t('review.hostedFailed', { at: hosted.at })
                : hosted.behind
                  ? t('review.hostedLate')
                  : hosted.day
                    ? t('review.hostedDay', { day: f.date(hosted.day), at: hosted.at })
                    : t('review.hosted', { at: hosted.at })}

              {(hosted.behind || hosted.error) && (
                <Button variant="outline" size="sm" className="ml-1.5 bg-card" disabled={busy !== null} onClick={() => (hosted.chosen ? run('host') : setChoosing(true))}>
                  <CloudUpload aria-hidden />
                  {busy === 'host' ? t('review.hosting') : t('review.host')}
                </Button>
              )}
            </span>
          </Tip>
        )}
      </div>
      {choosing && (
        <HostChoice
          onChoose={(body) => {
            setChoosing(false);
            run('host', body);
          }}
          onCancel={() => setChoosing(false)}
        />
      )}
    </header>
  );
}
