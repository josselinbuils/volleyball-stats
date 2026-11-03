import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, CircleOff, CirclePause, HelpCircle, PenLine, Scissors, UserX, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BrandBar } from '@/components/BrandBar';
import { matchTitle } from '@/components/Header/helpers/title';
import { Swatch } from '@/components/Swatch';
import { clock, useFormat } from '@/lib/format';
import { groupName, match, rallies, teamColor, teamRing, type Group } from '@/lib/match';
import { allMarked, post, type Conflict, type Hosted, type LearnRun, type Named, type Question, type ReportChanges, type Saved, type Suggestion, type Timeout, type TimeoutChange } from '@/lib/review';
import { Status } from '@/components/Review/Status';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { Pictures } from '@/components/Review/Pictures';
import { Conflicts } from '@/components/Review/Conflicts';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import { sameName } from '@/components/Review/helpers/players';
import { Names } from '@/components/Review/Names';
import { MatchTab } from '@/components/Review/MatchTab';
import { Progress } from '@/components/Review/Progress';
import { matchFinished } from '@/components/Review/helpers/report';
import { ReviewHeader } from '@/components/Review/ReviewHeader';
import { ReviewTabs } from '@/components/Review/ReviewTabs';

/** One answer per key: 1, 2 the choices, 3 someone else, X not a player, S don't know. */
const KEYS: Record<string, string> = { x: 'not_player', c: 'cut', s: 'skip' };
const NOTICE_MS = 4000;
const MERGE_KEYS: Record<string, string> = { '1': 'same', '2': 'different', s: 'skip' };
const TOUCH_KEYS: Record<string, string> = { '1': 'proposed', x: 'nobody', p: 'not_play', s: 'skip' };
const RALLY_KEYS: Record<string, string> = { '1': 'rally', p: 'not_play', s: 'skip' };
const REPORT_KEYS: Record<string, string> = { s: 'skip' };
type Tab = 'questions' | 'names' | 'match' | 'progress';
// The tab survives the reload that applies the answers.
const HASHES: Record<Tab, string> = { names: '', questions: '#questions', match: '#match', progress: '#progress' };

/** The review: the players' names, then the identity step's doubts one at a time, answered on the
 * video and shown with the names given. */
export function Review({
  width,
  height,
  answered: before,
  pending: waiting,
  changed,
  namesPending: renamed,
  corrections: savedCorrections,
  checked: savedChecked,
  comments: savedComments,
  timeouts: savedTimeouts,
  questions: initial,
  players,
  roster,
  conflicts,
  hosted,
  learning = [],
  fetched,
  backup,
  films: savedFilms,
  filmsError,
}: {
  width: number;
  height: number;
  answered: number;
  pending: number;
  changed: boolean;
  namesPending: boolean;
  corrections: Partial<ReportChanges>;
  comments: Record<number, string>;
  timeouts: Timeout[];
  checked: number[];
  questions: Question[];
  players: Named[];
  roster: [Suggestion[], Suggestion[]];
  conflicts: Conflict[];
  hosted?: Hosted | null;
  learning?: LearnRun[];
  fetched?: { at: string; count: number; error: string | null } | null;
  backup?: { at: string; error: string | null } | null;
  films?: { total: number; stale: number };
  filmsError?: string | null;
}) {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const [questions, setQuestions] = useState(initial);
  const [answered, setAnswered] = useState(before);
  // What an apply would take in: answers not applied yet, answers and names changed since.
  const [pending, setPending] = useState({ answers: waiting, changed, names: renamed });
  const [corrections, setCorrections] = useState(savedCorrections);
  const [checked, setChecked] = useState(savedChecked);
  const [comments, setComments] = useState(savedComments);
  const [timeouts, setTimeouts] = useState(savedTimeouts);
  const onSaved = (saved: Saved) => {
    if (saved.corrections !== undefined) {
      setCorrections(saved.corrections);
    }
    if (saved.checked !== undefined) {
      setChecked(saved.checked);
    }
    if (saved.answered !== undefined) {
      setAnswered(saved.answered);
    }
    if (saved.pending !== undefined) {
      setPending({ answers: saved.pending, changed: saved.changed ?? false, names: saved.namesPending ?? false });
    }
  };
  const films = savedFilms ?? { total: 0, stale: 0 };
  const [busy, setBusy] = useState<'apply' | 'undo' | 'rerun' | 'host' | 'reports' | 'films' | null>(null);
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
  const [tab, setTab] = useState<Tab>(() => (Object.keys(HASHES) as Tab[]).find((k) => HASHES[k] && HASHES[k] === location.hash) ?? 'names');
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
  // The viewers' reports are handled in the match tab.
  const open = questions.filter((q) => q.kind !== 'report' && !(q.kind === 'merge' && (q.choices.some(allMarked) || sameName(at(q, 0), at(q, 1), nameOf))));
  const question = open[0];
  const reports = questions.filter((q) => q.kind === 'report');
  const show = (next: Tab) => {
    setTab(next);
    history.replaceState(null, '', HASHES[next] || location.pathname);
  };
  // A report marked handled, with the corrections as they stand.
  const handled = async (report: Question, changes: ReportChanges) => {
    try {
      const saved = await post('answer', { id: report.id, choice: 'report', changes });
      setDone((d) => [...d, report]);
      setQuestions((qs) => qs.filter((q) => q.id !== report.id));
      onSaved(saved);
      setError(false);
    } catch {
      setError(true);
    }
  };
  // Corrections saved from the match tab, about no question, the `rally` checked with them: its
  // reports are handled.
  // A rally checked by mistake, or to look at again: its corrections stay.
  const uncheck = async (rally: number) => {
    try {
      onSaved(await post('answer', { id: `edit:${Date.now()}`, choice: 'report', unchecked: [rally] }));
      setError(false);
    } catch {
      setError(true);
    }
  };
  // Shown at once: the editor starting again from `comments` must not lose one being saved.
  const saveComment = async (rally: number, text: string) => {
    setComments((all) => {
      const out = { ...all };
      delete out[rally];
      return text ? { ...out, [rally]: text } : out;
    });
    try {
      await post('comment', { rally, text });
      setError(false);
      return true;
    } catch {
      setError(true);
      return false;
    }
  };

  const saveTimeout = async (change: TimeoutChange) => {
    try {
      const saved = await post('timeout', change);
      if (saved.timeouts) {
        setTimeouts(saved.timeouts);
      }
      setError(false);
    } catch {
      setError(true);
    }
  };

  const saveEdits = async (changes: ReportChanges, rally: number) => {
    try {
      onSaved(await post('answer', { id: `edit:${Date.now()}`, choice: 'report', changes, checked: [rally] }));
      setQuestions((qs) => qs.filter((q) => !(q.kind === 'report' && q.rally === rally)));
      setError(false);
    } catch {
      setError(true);
    }
  };

  const answer = useCallback(
    async (choice: string, extra: object = {}) => {
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
        const saved = await post('answer', { id: question.id, choice, ...extra, ...(choice === 'cut' ? { at } : {}) });
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

  /** Where the server's run stands: its step (and the pipeline's stage), which of how many, the time
   * spent and left, and whether it takes longer than last time. */
  const [progress, setProgress] = useState<{ fraction: number; step: string; stage: string | null; n: number; of: number; elapsed: number; left: number; late: boolean } | null>(null);
  const minutes = (s: number) => (s < 60 ? t('review.lessThanMinute') : t('review.minutes', { count: Math.round(s / 60) }));
  const reload = async (path: 'undo' | 'apply' | 'rerun' | 'host' | 'reports' | 'films') => {
    setBusy(path);
    // The server's steps and the time left, from how long each one took last time.
    const poll = window.setInterval(async () => {
      try {
        const p = (await (await fetch('progress')).json()) as { steps?: string[]; done: number; stage: string | null; elapsed: number; left: number; late: boolean };
        if (p.steps) {
          setProgress({
            fraction: Math.min(0.99, p.elapsed / Math.max(1, p.elapsed + p.left)),
            step: p.steps[p.done],
            stage: p.stage,
            n: p.done + 1,
            of: p.steps.length,
            elapsed: p.elapsed,
            left: p.left,
            late: p.late,
          });
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
      const key = { piece: KEYS, merge: MERGE_KEYS, touch: TOUCH_KEYS, rally: RALLY_KEYS, report: REPORT_KEYS }[question.kind][event.key.toLowerCase()];
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
      <main className="mx-auto grid w-full max-w-6xl grid-cols-[minmax(0,1fr)] gap-4 px-4 pt-6 pb-16 max-sm:pt-5">
        <ReviewHeader
          title={title}
          answered={answered}
          hosted={hosted}
          backup={backup}
          fetched={fetched}
          filmsError={filmsError}
          films={films}
          pending={pending}
          busy={busy}
          run={(action) => void reload(action)}
          onFailed={() => setError(true)}
        />
        {progress && (
          <div role="progressbar" aria-label={t('review.applying')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress.fraction * 100)} className="grid gap-1 px-1">
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${progress.fraction * 100}%` }} />
            </div>
            <p className="m-0 text-sm">
              {t(`review.step.${progress.step}`)}
              {progress.stage && ` · ${t(`review.stage.${progress.stage}`, { defaultValue: progress.stage })}`}
              <span className="text-muted-foreground"> · {t('review.stepOf', { n: progress.n, of: progress.of })}</span>
            </p>
            <p className="m-0 text-xs text-muted-foreground tabular-nums">
              {progress.late
                ? t('review.progressLate', { elapsed: minutes(progress.elapsed) })
                : t('review.progressLeft', {
                    left: minutes(progress.left),
                    end: new Date(Date.now() + progress.left * 1000).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' }),
                    elapsed: minutes(progress.elapsed),
                  })}
            </p>
          </div>
        )}
        {players.length > 0 && (
          <ReviewTabs
            tab={tab}
            show={show}
            named={named}
            players={players.length}
            questions={open.length}
            reports={reports.length}
            matchDone={matchFinished(
              rallies.map((r) => r.key ?? Math.round(r.start * match.fps)),
              checked,
              reports.length,
            )}
          />
        )}
        <p className="px-1 text-muted-foreground">{t({ names: 'review.namesIntro', questions: 'review.intro', match: 'review.matchIntro', progress: 'review.progressIntro' }[tab])}</p>
        <Conflicts conflicts={conflicts} width={width} height={height} players={players} nameOf={nameOf} />
        {error && (
          <p role="alert" className="rounded-lg border border-destructive px-3 py-2 text-sm text-destructive">
            {t('review.error')}
          </p>
        )}
        {tab === 'progress' ? (
          <Progress runs={learning} />
        ) : tab === 'names' ? (
          <Names players={players} roster={roster} onNamed={setGiven} onSaved={onSaved} onError={() => setError(true)} />
        ) : tab === 'match' ? (
          <MatchTab
            width={width}
            height={height}
            players={players}
            nameOf={nameOf}
            saved={corrections}
            checked={checked}
            comments={comments}
            onComment={saveComment}
            timeouts={timeouts}
            onTimeout={(change) => void saveTimeout(change)}
            reports={reports}
            onSave={saveEdits}
            onUncheck={uncheck}
            onHandled={handled}
          />
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
            <CardContent className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              {(question.kind === 'piece' || question.kind === 'touch') && (
                <label className="grid max-w-md gap-1 text-sm font-medium lg:col-span-2">
                  {t('review.whoIs')}
                  <PlayerSelect
                    key={question.id}
                    // Both teams: the touch's team, or for an ace the side the ball lands on, is only a guess.
                    players={players}
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
                    <AnswerButton icon={<CirclePause aria-hidden />} label={t('review.notPlay')} hint="P" onClick={() => void answer('not_play')} />
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
