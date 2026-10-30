import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, HelpCircle, PenLine, Scissors, Undo2, UserX, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { BrandBar } from '@/components/BrandBar';
import { matchTitle } from '@/components/Header/helpers/title';
import { Swatch } from '@/components/Swatch';
import { useFormat } from '@/lib/format';
import { groupName, match, teamColor, teamRing, type Group } from '@/lib/match';
import { allMarked, post, type Conflict, type Named, type Question, type Suggestion } from '@/lib/review';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { Pictures } from '@/components/Review/Pictures';
import { Conflicts } from '@/components/Review/Conflicts';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import { sameName } from '@/components/Review/helpers/players';
import { Names } from '@/components/Review/Names';

/** One answer per key: 1, 2 the choices, 3 someone else, X not a player, S don't know. */
const KEYS: Record<string, string> = { '1': '0', '2': '1', '3': 'other', x: 'not_player', c: 'cut', s: 'skip' };
const MERGE_KEYS: Record<string, string> = { '1': 'same', '2': 'different', s: 'skip' };

type Tab = 'questions' | 'names';
// The tab survives the reload that applies the answers.
const QUESTIONS_HASH = '#questions';

/** The review: the players' names, then the identity step's doubts one at a time, answered on the
 * video and shown with the names given. */
export function Review({
  width,
  height,
  answered: before,
  questions: initial,
  players,
  roster,
  conflicts,
}: {
  width: number;
  height: number;
  answered: number;
  questions: Question[];
  players: Named[];
  roster: [Suggestion[], Suggestion[]];
  conflicts: Conflict[];
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const [questions, setQuestions] = useState(initial);
  const [answered, setAnswered] = useState(before);
  const [busy, setBusy] = useState<'apply' | 'undo' | null>(null);
  const [showOther, setShowOther] = useState(false);
  const [error, setError] = useState(false);
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
  const hidden = (q: Question, k: number) => allMarked(q.choices[k]) || q.choices.slice(0, k).some((_, j) => sameName(at(q, j), at(q, k), nameOf));
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
      try {
        // A cut falls where the clip stands: paused when the outlined person changed.
        const saved = await post('answer', { id: question.id, choice, ...(choice === 'cut' ? { at: clipTime.current } : {}) });
        if (saved.cancelled) {
          return;
        }
        setDone((d) => [...d, question]);
        setQuestions((qs) => qs.filter((q) => q.id !== question.id));
        setAnswered((n) => n + 1);
        setShowOther(false);
        setError(false);
      } catch {
        setError(true);
      }
    },
    [question],
  );

  const reload = async (path: 'undo' | 'apply') => {
    setBusy(path);
    try {
      const saved = await post(path);
      // An answer not applied yet comes back without rebuilding anything.
      const last = done[done.length - 1];
      if (path === 'undo' && !saved.rebuilt && last?.id === saved.undone) {
        setQuestions((qs) => [last, ...qs]);
        setDone((d) => d.slice(0, -1));
        setAnswered(saved.answered ?? 0);
        setBusy(null);
        return;
      }
      location.reload();
    } catch {
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
      const choice = (question.kind === 'merge' ? MERGE_KEYS : KEYS)[event.key.toLowerCase()];
      if (choice && (choice.length > 1 || (Number(choice) < question.choices.length && !hidden(question, Number(choice))))) {
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
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="bg-card" disabled={!answered || busy !== null} onClick={() => void reload('undo')}>
              <Undo2 aria-hidden />
              {busy === 'undo' ? t('review.undoing') : t('review.undo')}
            </Button>
            <Button disabled={(!answered && !named) || busy !== null} onClick={() => void reload('apply')}>
              <Check aria-hidden />
              {busy === 'apply' ? t('review.applying') : named ? t(answered ? 'review.applyBoth' : 'review.applyNames') : answered ? t('review.apply', { count: answered }) : t('review.applyNone')}
            </Button>
          </div>
        </header>
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
          <Names players={players} roster={roster} onNamed={setGiven} onMarked={setAnswered} onError={() => setError(true)} />
        ) : question ? (
          <Card>
            <CardHeader>
              <CardTitle>
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <Swatch color={teamColor(question.team)} ring={teamRing(question.team)} />
                  {question.kind === 'piece' ? t('review.who') : t('review.mergeQuestion', { a: question.choices[0].identity, b: question.choices[1].identity })}
                </h2>
              </CardTitle>
              <CardDescription>
                {[groupName(t, question.team), t('review.atStake', { s: f.secs(question.seconds) }), question.contacts > 0 && t('touchesN', { count: question.contacts })].filter(Boolean).join(' · ')}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
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
                <p className="text-[13px] text-muted-foreground">{t(question.kind === 'piece' ? 'review.pieceNote' : 'review.mergeNote')}</p>
              </div>
              <div className="grid gap-3">
                {question.choices.map((c, k) =>
                  question.kind === 'piece' && hidden(question, k) ? null : (
                    <div key={c.identity} className="grid gap-2 rounded-lg border bg-card p-3">
                      <Pictures
                        crops={c.crops}
                        pieces={c.pieces}
                        owner={{ team: question.team, identity: c.identity }}
                        players={players}
                        nameOf={nameOf}
                        onSaved={setAnswered}
                        onError={() => setError(true)}
                      />
                      {question.kind === 'piece' && (
                        <Button variant="outline" className="justify-between bg-card" onClick={() => void answer(String(k))}>
                          {nameOf(question.team, c.identity) ? t('review.isNamed', { name: nameOf(question.team, c.identity), n: c.identity }) : t('review.isN', { n: c.identity })}
                          <kbd className="rounded border px-1.5 text-xs text-muted-foreground">{k + 1}</kbd>
                        </Button>
                      )}
                      {question.kind === 'merge' && (
                        <p className="m-0 text-sm font-medium">
                          {nameOf(question.team, c.identity) ? t('review.namedPlayer', { name: nameOf(question.team, c.identity), n: c.identity }) : t('player', { n: c.identity })}
                        </p>
                      )}
                    </div>
                  ),
                )}
                {question.kind === 'piece' ? (
                  <div className="grid gap-3">
                    <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                      <AnswerButton icon={<Users aria-hidden />} label={t('review.other')} hint="3" onClick={() => void answer('other')} />
                      <AnswerButton icon={<UserX aria-hidden />} label={t('review.notPlayer')} hint="X" onClick={() => void answer('not_player')} />
                      <AnswerButton icon={<Scissors aria-hidden />} label={t('review.cut')} hint="C" onClick={() => void answer('cut')} />
                      <AnswerButton icon={<HelpCircle aria-hidden />} label={t('review.skip')} hint="S" onClick={() => void answer('skip')} />
                    </div>
                    <p className="m-0 text-[13px] text-muted-foreground">{t('review.cutNote')}</p>
                    <label className="grid gap-1 text-sm font-medium">
                      {t('review.whoIs')}
                      <PlayerSelect
                        key={question.id}
                        players={players}
                        nameOf={nameOf}
                        value=""
                        empty={t('review.pickPlayer')}
                        label={t('review.whoIs')}
                        className="h-9 w-full text-[15px] font-normal"
                        onChange={(who) => who && void answer(`player:${who}`)}
                      />
                    </label>
                  </div>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                    <AnswerButton icon={<Check aria-hidden />} label={t('review.same')} hint="1" onClick={() => void answer('same')} />
                    <AnswerButton icon={<Users aria-hidden />} label={t('review.different')} hint="2" onClick={() => void answer('different')} />
                    <AnswerButton icon={<HelpCircle aria-hidden />} label={t('review.skip')} hint="S" onClick={() => void answer('skip')} />
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="text-lg font-semibold">{t('review.done')}</p>
              <p className="mt-1 text-muted-foreground">{t(answered ? 'review.doneApply' : 'review.doneNothing')}</p>
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
