import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, CircleOff, CirclePause, HelpCircle, PenLine, Scissors, Undo2, UserX, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { BrandBar } from '@/components/BrandBar';
import { matchTitle } from '@/components/Header/helpers/title';
import { Swatch } from '@/components/Swatch';
import { clock, useFormat } from '@/lib/format';
import { groupName, match, teamColor, teamRing, type Group } from '@/lib/match';
import { cn } from '@/lib/utils';
import { allMarked, post, type Conflict, type Named, type Question, type Saved, type Suggestion } from '@/lib/review';
import { Status } from '@/components/Review/Status';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { Pictures } from '@/components/Review/Pictures';
import { Conflicts } from '@/components/Review/Conflicts';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import { sameName } from '@/components/Review/helpers/players';
import { Names } from '@/components/Review/Names';

/** One answer per key: 1, 2 the choices, 3 someone else, X not a player, S don't know. */
const KEYS: Record<string, string> = { x: 'not_player', c: 'cut', s: 'skip' };
const NOTICE_MS = 4000;
const MERGE_KEYS: Record<string, string> = { '1': 'same', '2': 'different', s: 'skip' };
const TOUCH_KEYS: Record<string, string> = { '1': 'proposed', x: 'nobody', p: 'not_play', s: 'skip' };
const RALLY_KEYS: Record<string, string> = { '1': 'rally', p: 'not_play', s: 'skip' };

type Tab = 'questions' | 'names';
// The tab survives the reload that applies the answers.
const QUESTIONS_HASH = '#questions';

/** The review: the players' names, then the identity step's doubts one at a time, answered on the
 * video and shown with the names given. */
export function Review({
  width,
  height,
  answered: before,
  pending: waiting,
  changed,
  namesPending: renamed,
  questions: initial,
  players,
  roster,
  conflicts,
  hosted,
}: {
  width: number;
  height: number;
  answered: number;
  pending: number;
  changed: boolean;
  namesPending: boolean;
  questions: Question[];
  players: Named[];
  roster: [Suggestion[], Suggestion[]];
  conflicts: Conflict[];
  hosted?: { at: string; error: string | null } | null;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const [questions, setQuestions] = useState(initial);
  const [answered, setAnswered] = useState(before);
  // What an apply would take in: answers not applied yet, answers and names changed since.
  const [pending, setPending] = useState({ answers: waiting, changed, names: renamed });
  const onSaved = (saved: Saved) => {
    if (saved.answered !== undefined) {
      setAnswered(saved.answered);
    }
    if (saved.pending !== undefined) {
      setPending({ answers: saved.pending, changed: saved.changed ?? false, names: saved.namesPending ?? false });
    }
  };
  const [busy, setBusy] = useState<'apply' | 'undo' | null>(null);
  const [showOther, setShowOther] = useState(false);
  const [error, setError] = useState(false);
  // What the last action did, shown for NOTICE_MS.
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (!notice) {
      return;
    }
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);
  const [tab, setTab] = useState<Tab>(location.hash === QUESTIONS_HASH ? 'questions' : 'names');
  const [given, setGiven] = useState(() => new Map(players.map((p) => [`${p.team}:${p.identity}`, { name: p.name ?? '', jersey: p.jersey === null ? '' : String(p.jersey) }])));
  const named = [...given.values()].filter((g) => g.name.trim() || g.jersey).length;
  const nameOf = (team: Group, n: number) => given.get(`${team}:${n}`)?.name.trim() || null;
  const clipTime = useRef(0);
  // The questions answered here, last on top, to bring back on undo.
  const [done, setDone] = useState<Question[]>([]);
  // A proposed player whose pictures are all marked as someone else is no longer offered, nor a
  // namesake of a player offered before; whether two players are one makes no sense with such a
  // player, or once both carry the same name: that question goes.
  const at = (q: Question, k: number) => ({ team: q.team, identity: q.choices[k].identity });
  const open = questions.filter((q) => !(q.kind === 'merge' && (q.choices.some(allMarked) || sameName(at(q, 0), at(q, 1), nameOf))));
  const question = open[0];
  const show = (next: Tab) => {
    setTab(next);
    history.replaceState(null, '', next === 'questions' ? QUESTIONS_HASH : location.pathname);
  };

  const answer = useCallback(
    async (choice: string) => {
      if (!question) {
        return;
      }
      // A cut falls where the clip stands when asked, playing or paused, inside the outlined piece.
      const at = clipTime.current;
      if (choice === 'cut' && !(at > question.clip.start && at < question.clip.end)) {
        setNotice(t('review.cutWhere'));
        return;
      }
      try {
        const saved = await post('answer', { id: question.id, choice, ...(choice === 'cut' ? { at } : {}) });
        if (saved.cancelled) {
          return;
        }
        if (choice === 'cut') {
          setNotice(t('review.cutDone', { at: clock(at) }));
        }
        setDone((d) => [...d, question]);
        setQuestions((qs) => qs.filter((q) => q.id !== question.id));
        onSaved(saved);
        setShowOther(false);
        setError(false);
      } catch {
        setError(true);
      }
    },
    [question, t],
  );

  const [progress, setProgress] = useState<{ fraction: number; step: string } | null>(null);
  const reload = async (path: 'undo' | 'apply') => {
    setBusy(path);
    // The server's steps, each advancing as long as it took last time.
    const poll = window.setInterval(async () => {
      try {
        const p = (await (await fetch('progress')).json()) as { steps?: string[]; done: number; took: Record<string, number>; elapsed: number };
        if (p.steps) {
          const time = (step: string) => p.took[step] ?? 1;
          const total = p.steps.reduce((sum, step) => sum + time(step), 0);
          const done = p.steps.slice(0, p.done).reduce((sum, step) => sum + time(step), 0);
          const step = p.steps[p.done];
          setProgress({ fraction: Math.min(0.99, (done + Math.min(p.elapsed, time(step))) / total), step });
        }
      } catch {
        // The bar waits for the next poll.
      }
    }, 400);
    try {
      const saved = await post(path);
      window.clearInterval(poll);
      // An answer not applied yet comes back without rebuilding anything.
      const last = done[done.length - 1];
      if (path === 'undo' && !saved.rebuilt && last?.id === saved.undone) {
        setQuestions((qs) => [last, ...qs]);
        setDone((d) => d.slice(0, -1));
        onSaved(saved);
        setBusy(null);
        return;
      }
      location.reload();
    } catch {
      window.clearInterval(poll);
      setProgress(null);
      setBusy(null);
      setError(true);
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLElement && event.target.closest('input, textarea, select');
      if (event.ctrlKey || event.metaKey || event.altKey || !question || busy || tab !== 'questions' || typing) {
        return;
      }
      const key = { piece: KEYS, merge: MERGE_KEYS, touch: TOUCH_KEYS, rally: RALLY_KEYS }[question.kind][event.key.toLowerCase()];
      const choice = key === 'proposed' ? question.proposed != null && `player:${question.team}:${question.proposed}` : key;
      if (choice) {
        event.preventDefault();
        void answer(choice);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [question, answer, busy, tab]);

  const title = matchTitle(t) ?? match.name;
  useEffect(() => {
    document.title = `${t('review.title')} · ${title}`;
  }, [t, title]);
  return (
    <>
      <BrandBar brand={match.brand} />
      <Status notice={notice} />
      <main className="mx-auto grid w-full max-w-6xl gap-4 px-4 pt-6 pb-16 max-sm:pt-5">
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 px-1">
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <h1 className="mt-0.5 text-2xl font-semibold tracking-tight">{t('review.title')}</h1>
            <p className="mt-1 text-sm text-muted-foreground" aria-live="polite">
              {`${t('review.answers', { count: answered })} · ${t('review.left', { count: open.length })}`}
              {' · '}
              <a href="./" className="text-link underline underline-offset-2">
                {t('review.matchPage')}
              </a>
            </p>
            {hosted && (
              <p className={cn('mt-0.5 text-sm', hosted.error ? 'text-destructive' : 'text-muted-foreground')} title={hosted.error ?? undefined}>
                {hosted.error ? t('review.hostedFailed', { at: hosted.at }) : t('review.hosted', { at: hosted.at })}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="bg-card" disabled={!answered || busy !== null} onClick={() => void reload('undo')}>
              <Undo2 aria-hidden />
              {busy === 'undo' ? t('review.undoing') : t('review.undo')}
            </Button>
            <Button disabled={(!pending.changed && !pending.names) || busy !== null} onClick={() => void reload('apply')}>
              <Check aria-hidden />
              {busy === 'apply'
                ? t('review.applying')
                : pending.names
                  ? t(pending.changed ? 'review.applyBoth' : 'review.applyNames')
                  : !pending.changed
                    ? t('review.applied')
                    : pending.answers
                      ? t('review.apply', { count: pending.answers })
                      : t('review.applyChanges')}
            </Button>
          </div>
        </header>
        {progress && (
          <div role="progressbar" aria-label={t('review.applying')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress.fraction * 100)} className="grid gap-1 px-1">
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${progress.fraction * 100}%` }} />
            </div>
            <p className="m-0 text-xs text-muted-foreground">{t(`review.step.${progress.step}`)}</p>
          </div>
        )}
        {players.length > 0 && (
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            value={tab}
            onValueChange={(v) => {
              if (v) {
                show(v as Tab);
              }
            }}
            aria-label={t('review.tabs')}
            className="w-full items-stretch bg-card sm:w-auto sm:justify-self-start"
          >
            <ToggleGroupItem value="names" className="h-9 flex-1 px-4 text-[15px] data-[state=on]:bg-primary data-[state=on]:font-semibold data-[state=on]:text-primary-foreground sm:flex-none">
              {t('review.tabNames', { n: named, total: players.length })}
            </ToggleGroupItem>
            <ToggleGroupItem value="questions" className="h-9 flex-1 px-4 text-[15px] data-[state=on]:bg-primary data-[state=on]:font-semibold data-[state=on]:text-primary-foreground sm:flex-none">
              {t('review.tabQuestions', { count: open.length })}
            </ToggleGroupItem>
          </ToggleGroup>
        )}
        <p className="px-1 text-muted-foreground">{t(tab === 'names' ? 'review.namesIntro' : 'review.intro')}</p>
        <Conflicts conflicts={conflicts} width={width} height={height} players={players} nameOf={nameOf} />
        {error && (
          <p role="alert" className="rounded-lg border border-destructive px-3 py-2 text-sm text-destructive">
            {t('review.error')}
          </p>
        )}
        {tab === 'names' ? (
          <Names players={players} roster={roster} onNamed={setGiven} onSaved={onSaved} onError={() => setError(true)} />
        ) : question ? (
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  {question.kind !== 'rally' && question.reason !== 'ace' && <Swatch color={teamColor(question.team)} ring={teamRing(question.team)} />}
                  {question.kind === 'piece'
                    ? t('review.who')
                    : question.kind === 'touch'
                      ? t(question.reason === 'ace' ? 'review.aceQuestion' : 'review.touchQuestion')
                      : question.kind === 'rally'
                        ? t('review.rallyQuestion')
                        : t('review.mergeQuestion', { a: question.choices[0].identity, b: question.choices[1].identity })}
                </h2>
              </CardTitle>
              <CardDescription>
                {(question.kind === 'touch'
                  ? [question.reason !== 'ace' && groupName(t, question.team), t(`types.${question.action}`), clock(question.time ?? 0), t(`review.touchWhy.${question.reason}`)]
                  : question.kind === 'rally'
                    ? [question.set && t('set', { n: question.set }), clock(question.time ?? 0), f.secs(question.seconds), t('review.rallyWhy')]
                    : [groupName(t, question.team), t('review.atStake', { s: f.secs(question.seconds) }), question.contacts > 0 && t('touchesN', { count: question.contacts })]
                )
                  .filter(Boolean)
                  .join(' · ')}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              {(question.kind === 'piece' || question.kind === 'touch') && (
                <label className="grid max-w-md gap-1 text-sm font-medium lg:col-span-2">
                  {t('review.whoIs')}
                  <PlayerSelect
                    key={question.id}
                    // Who missed an ace: both teams, the side the ball lands on is only a guess.
                    players={question.kind === 'touch' && question.reason !== 'ace' ? players.filter((p) => p.team === question.team) : players}
                    nameOf={nameOf}
                    value=""
                    empty={t('review.pickPlayer')}
                    label={t('review.whoIs')}
                    className="h-9 w-full text-[15px] font-normal"
                    autoFocus
                    openOnFocus={false}
                    onChange={(who) => who && void answer(`player:${who}`)}
                  />
                </label>
              )}
              <div className="grid min-w-0 gap-3">
                <ClipVideo key={`${question.id}${showOther}`} clip={showOther && question.other ? question.other : question.clip} width={width} height={height} timeRef={clipTime} />
                {question.kind === 'merge' && (
                  <div className="flex flex-wrap gap-2">
                    {question.choices.map((c, k) => (
                      <Button key={c.identity} variant={showOther === (k === 1) ? 'default' : 'outline'} size="sm" onClick={() => setShowOther(k === 1)}>
                        {nameOf(question.team, c.identity) ? t('review.showNamed', { name: nameOf(question.team, c.identity) }) : t('review.show', { n: c.identity })}
                      </Button>
                    ))}
                  </div>
                )}
                {question.crops.length > 0 && (
                  <div className="flex flex-wrap gap-2" aria-label={t('review.outlined')}>
                    {question.crops.map((src) => (
                      <img key={src} src={src} alt="" className="h-56 rounded-md bg-muted ring-2 ring-[#ffd400]" />
                    ))}
                  </div>
                )}
                <p className="text-[13px] text-muted-foreground">{t(question.reason === 'ace' ? 'review.aceNote' : `review.${question.kind}Note`)}</p>
              </div>
              <div className="grid gap-3">
                {question.kind === 'rally' ? (
                  <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                    <AnswerButton icon={<Check aria-hidden />} label={t('review.isRally')} hint="1" onClick={() => void answer('rally')} />
                    <AnswerButton icon={<CirclePause aria-hidden />} label={t('review.notPlay')} hint="P" onClick={() => void answer('not_play')} />
                    <AnswerButton icon={<HelpCircle aria-hidden />} label={t('review.skip')} hint="S" onClick={() => void answer('skip')} />
                  </div>
                ) : question.kind === 'touch' ? (
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                    {question.proposed != null && (
                      <AnswerButton
                        icon={<Check aria-hidden />}
                        label={t('review.touchProposed', { name: nameOf(question.team, question.proposed) ?? t('player', { n: question.proposed }) })}
                        hint="1"
                        onClick={() => void answer(`player:${question.team}:${question.proposed}`)}
                      />
                    )}
                    <AnswerButton icon={<CircleOff aria-hidden />} label={t(question.reason === 'ace' ? 'review.aceNobody' : 'review.nobody')} hint="X" onClick={() => void answer('nobody')} />
                    {question.reason !== 'ace' && <AnswerButton icon={<CirclePause aria-hidden />} label={t('review.notPlay')} hint="P" onClick={() => void answer('not_play')} />}
                    <AnswerButton icon={<HelpCircle aria-hidden />} label={t('review.skip')} hint="S" onClick={() => void answer('skip')} />
                  </div>
                ) : question.kind === 'piece' ? (
                  <div className="grid gap-3">
                    <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                      <AnswerButton icon={<UserX aria-hidden />} label={t('review.notPlayer')} hint="X" onClick={() => void answer('not_player')} />
                      <AnswerButton icon={<Scissors aria-hidden />} label={t('review.cut')} hint="C" onClick={() => void answer('cut')} />
                      <AnswerButton icon={<HelpCircle aria-hidden />} label={t('review.skip')} hint="S" onClick={() => void answer('skip')} />
                    </div>
                    <p className="m-0 text-[13px] text-muted-foreground">{t('review.cutNote')}</p>
                  </div>
                ) : (
                  <>
                    {question.choices.map((c) => (
                      <div key={c.identity} className="grid gap-2 rounded-lg border bg-card p-3">
                        <Pictures
                          crops={c.crops}
                          pieces={c.pieces}
                          owner={{ team: question.team, identity: c.identity }}
                          players={players}
                          nameOf={nameOf}
                          onSaved={onSaved}
                          onError={() => setError(true)}
                        />
                        <p className="m-0 text-sm font-medium">
                          {nameOf(question.team, c.identity) ? t('review.namedPlayer', { name: nameOf(question.team, c.identity), n: c.identity }) : t('player', { n: c.identity })}
                        </p>
                      </div>
                    ))}
                    <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                      <AnswerButton icon={<Check aria-hidden />} label={t('review.same')} hint="1" onClick={() => void answer('same')} />
                      <AnswerButton icon={<Users aria-hidden />} label={t('review.different')} hint="2" onClick={() => void answer('different')} />
                      <AnswerButton icon={<HelpCircle aria-hidden />} label={t('review.skip')} hint="S" onClick={() => void answer('skip')} />
                    </div>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="text-lg font-semibold">{t('review.done')}</p>
              <p className="mt-1 text-muted-foreground">{t(pending.changed || pending.names ? 'review.doneApply' : 'review.doneNothing')}</p>
              {players.length > 0 && (
                <Button className="mt-4" onClick={() => show('names')}>
                  <PenLine aria-hidden />
                  {t('review.goNames')}
                </Button>
              )}
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}

function AnswerButton({ icon, label, hint, onClick }: { icon: React.ReactNode; label: string; hint: string; onClick: () => void }) {
  return (
    <Button variant="outline" className="justify-between bg-card" onClick={onClick}>
      <span className="inline-flex items-center gap-2">
        {icon}
        {label}
      </span>
      <kbd className="rounded border px-1.5 text-xs text-muted-foreground">{hint}</kbd>
    </Button>
  );
}
