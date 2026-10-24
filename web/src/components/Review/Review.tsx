import { useCallback, useEffect, useState } from 'react';
import { Check, HelpCircle, Undo2, UserX, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BrandBar } from '@/components/BrandBar';
import { matchTitle } from '@/components/Header/helpers/title';
import { Swatch } from '@/components/Swatch';
import { useFormat } from '@/lib/format';
import { groupName, match, teamColor, teamRing } from '@/lib/match';
import { post, type Question } from '@/lib/review';
import { ClipVideo } from '@/components/Review/ClipVideo';

/** One answer per key: 1, 2 the choices, 3 someone else, X not a player, S don't know. */
const KEYS: Record<string, string> = { '1': '0', '2': '1', '3': 'other', x: 'not_player', s: 'skip' };
const MERGE_KEYS: Record<string, string> = { '1': 'same', '2': 'different', s: 'skip' };

/** The review: the identity step's doubts one at a time, answered on the video. */
export function Review({ width, height, answered: before, questions: initial }: { width: number; height: number; answered: number; questions: Question[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [questions, setQuestions] = useState(initial);
  const [answered, setAnswered] = useState(before);
  const [busy, setBusy] = useState<'apply' | null>(null);
  const [showOther, setShowOther] = useState(false);
  const [error, setError] = useState(false);
  const question = questions[0];

  const answer = useCallback(
    async (choice: string) => {
      if (!question) {
        return;
      }
      try {
        await post('answer', { id: question.id, choice });
        setQuestions((qs) => qs.slice(1));
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
    setBusy(path === 'apply' ? 'apply' : null);
    try {
      await post(path);
      location.reload();
    } catch {
      setBusy(null);
      setError(true);
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || !question || busy) {
        return;
      }
      const choice = (question.kind === 'merge' ? MERGE_KEYS : KEYS)[event.key.toLowerCase()];
      if (choice && (choice.length > 1 || Number(choice) < question.choices.length)) {
        event.preventDefault();
        void answer(choice);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [question, answer, busy]);

  const title = matchTitle(t) ?? match.name;
  useEffect(() => {
    document.title = `${t('review.title')} · ${title}`;
  }, [t, title]);
  return (
    <>
      <BrandBar />
      <main className="mx-auto grid w-full max-w-6xl gap-4 px-4 pt-6 pb-16 max-sm:pt-5">
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 px-1">
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <h1 className="mt-0.5 text-2xl font-semibold tracking-tight">{t('review.title')}</h1>
            <p className="mt-1 text-sm text-muted-foreground" aria-live="polite">
              {`${t('review.answers', { count: answered })} · ${t('review.left', { count: questions.length })}`}
              {' · '}
              <a href="./" className="text-link underline underline-offset-2">
                {t('review.matchPage')}
              </a>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="bg-card" disabled={!answered || busy !== null} onClick={() => void reload('undo')}>
              <Undo2 aria-hidden />
              {t('review.undo')}
            </Button>
            <Button disabled={!answered || busy !== null} onClick={() => void reload('apply')}>
              <Check aria-hidden />
              {busy === 'apply' ? t('review.applying') : answered ? t('review.apply', { count: answered }) : t('review.applyNone')}
            </Button>
          </div>
        </header>
        <p className="px-1 text-muted-foreground">{t('review.intro')}</p>
        {error && (
          <p role="alert" className="rounded-lg border border-destructive px-3 py-2 text-sm text-destructive">
            {t('review.error')}
          </p>
        )}
        {question ? (
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
                <ClipVideo key={`${question.id}${showOther}`} clip={showOther && question.other ? question.other : question.clip} width={width} height={height} />
                {question.kind === 'merge' && (
                  <div className="flex flex-wrap gap-2">
                    {question.choices.map((c, k) => (
                      <Button key={c.identity} variant={showOther === (k === 1) ? 'default' : 'outline'} size="sm" onClick={() => setShowOther(k === 1)}>
                        {t('review.show', { n: c.identity })}
                      </Button>
                    ))}
                  </div>
                )}
                {question.crops.length > 0 && (
                  <div className="flex flex-wrap gap-2" aria-label={t('review.outlined')}>
                    {question.crops.map((src) => (
                      <img key={src} src={src} alt="" className="h-32 rounded-md bg-muted ring-2 ring-[#ffd400]" />
                    ))}
                  </div>
                )}
                <p className="text-[13px] text-muted-foreground">{t(question.kind === 'piece' ? 'review.pieceNote' : 'review.mergeNote')}</p>
              </div>
              <div className="grid gap-3">
                {question.choices.map((c, k) => (
                  <div key={c.identity} className="grid gap-2 rounded-lg border bg-card p-3">
                    <div className="flex gap-1.5 overflow-hidden">
                      {c.crops.map((src) => (
                        <img key={src} src={src} alt="" loading="lazy" className="h-24 rounded-md bg-muted" />
                      ))}
                    </div>
                    {question.kind === 'piece' && (
                      <Button variant="outline" className="justify-between bg-card" onClick={() => void answer(String(k))}>
                        {t('review.isN', { n: c.identity })}
                        <kbd className="rounded border px-1.5 text-xs text-muted-foreground">{k + 1}</kbd>
                      </Button>
                    )}
                    {question.kind === 'merge' && <p className="m-0 text-sm font-medium">{t('player', { n: c.identity })}</p>}
                  </div>
                ))}
                {question.kind === 'piece' ? (
                  <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                    <AnswerButton icon={<Users aria-hidden />} label={t('review.other')} hint="3" onClick={() => void answer('other')} />
                    <AnswerButton icon={<UserX aria-hidden />} label={t('review.notPlayer')} hint="X" onClick={() => void answer('not_player')} />
                    <AnswerButton icon={<HelpCircle aria-hidden />} label={t('review.skip')} hint="S" onClick={() => void answer('skip')} />
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
