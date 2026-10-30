import { useRef, useState } from 'react';
import { AlertTriangle, Scissors, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { post, type Conflict, type Linking, type Named } from '@/lib/review';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import type { NameOf } from '@/components/Review/helpers/players';
import { clock } from '@/lib/format';

/** The players holding two names after the last apply, each with the answers joining them: a piece
 * to cut where the person changes, or answers to forget. Each action reloads the page. */
export function Conflicts({ conflicts, width, height, players, nameOf }: { conflicts: Conflict[]; width: number; height: number; players: Named[]; nameOf: NameOf }) {
  const { t, i18n } = useTranslation();
  const list = new Intl.ListFormat(i18n.language, { type: 'conjunction' });
  return conflicts.map((c) => (
    <Card key={`${c.team}:${c.identity}`} className="border-destructive">
      <CardHeader>
        <CardTitle>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <AlertTriangle aria-hidden className="size-5 text-destructive" />
            {t('review.conflict', { names: list.format(c.names) })}
          </h2>
        </CardTitle>
        <CardDescription>{t(c.answers.length ? 'review.conflictNote' : 'review.conflictApply')}</CardDescription>
      </CardHeader>
      {(c.answers.length > 0 || c.pinned.length > 0) && (
        <CardContent className="grid gap-6">
          {c.answers.map((a) => (
            <Linked key={a.id} answer={a} width={width} height={height} />
          ))}
          {c.pinned.length > 0 && <Pinned conflict={c} players={players} nameOf={nameOf} />}
        </CardContent>
      )}
    </Card>
  ));
}

function Linked({ answer, width, height }: { answer: Linking; width: number; height: number }) {
  const { t } = useTranslation();
  const time = useRef(0);
  const [seek, setSeek] = useState<{ time: number; n: number }>();
  const [failed, setFailed] = useState(false);
  const act = async (path: 'cut' | 'forget', at?: number) => {
    try {
      await post(path, { id: answer.id, ...(path === 'cut' ? { at: at ?? time.current } : {}) });
      location.reload();
    } catch {
      setFailed(true);
    }
  };
  const someone = (name: string | null) => name ?? t('review.someoneElse');

  if (answer.kind === 'odd') {
    return (
      <div className="grid gap-2">
        <p className="m-0 text-sm font-medium">{t('review.claimMarks')}</p>
        <div className="flex gap-1.5 overflow-x-auto p-1">
          {answer.crops.map((src, k) => (
            <figure key={src} className="m-0 grid shrink-0 justify-items-center gap-0.5 text-xs">
              <img src={src} alt="" loading="lazy" className="h-32 max-w-none rounded-md bg-muted" />
              <figcaption className="font-medium">= {someone(answer.claims[k])}</figcaption>
            </figure>
          ))}
        </div>
        <Button variant="outline" className="justify-self-start bg-card" onClick={() => void act('forget')}>
          <Trash2 aria-hidden />
          {t('review.forgetMarks')}
        </Button>
        {failed && (
          <p role="alert" className="m-0 text-sm text-destructive">
            {t('review.error')}
          </p>
        )}
      </div>
    );
  }
  return (
    <div className="grid gap-3">
      <p className="m-0 text-sm font-medium">{t('review.claimPiece', { from: clock(answer.clip.start), to: clock(answer.clip.end), name: someone(answer.claim) })}</p>
      <p className="m-0 text-sm text-muted-foreground">{t('review.diagnose')}</p>
      <div className="flex items-end gap-0.5 overflow-x-auto p-1">
        {answer.strip.map((m, k) => (
          <div key={m.time} className="flex shrink-0 items-end gap-0.5">
            {k > 0 && (
              <Button
                variant="ghost"
                size="icon"
                className="mb-6 size-7"
                aria-label={t('review.cutBetween', { a: clock(answer.strip[k - 1].time), b: clock(m.time) })}
                title={t('review.cutBetween', { a: clock(answer.strip[k - 1].time), b: clock(m.time) })}
                onClick={() => void act('cut', (answer.strip[k - 1].time + m.time) / 2)}
              >
                <Scissors aria-hidden />
              </Button>
            )}
            <button
              type="button"
              onClick={() => setSeek((s) => ({ time: m.time, n: (s?.n ?? 0) + 1 }))}
              className="grid justify-items-center gap-0.5 rounded-md p-0.5 text-xs outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <img src={m.crop} alt="" loading="lazy" className="h-32 max-w-none rounded bg-muted" />
              <span className="tabular-nums">{clock(m.time)}</span>
            </button>
          </div>
        ))}
      </div>
      {answer.moments.length > 0 && (
        <div className="grid gap-1.5">
          <p className="m-0 text-sm text-muted-foreground">{t('review.moments')}</p>
          <div className="flex flex-wrap gap-1.5">
            {answer.moments.map((m) => (
              <button
                key={m.time}
                type="button"
                onClick={() => setSeek((s) => ({ time: m.time, n: (s?.n ?? 0) + 1 }))}
                className="grid justify-items-center gap-0.5 rounded-md border bg-card p-1 text-xs outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <img src={m.crop} alt="" loading="lazy" className="h-24 max-w-none rounded bg-muted" />
                <span className="tabular-nums">{clock(m.time)}</span>
                <span className="font-medium">= {someone(m.name)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <ClipVideo clip={answer.clip} width={width} height={height} timeRef={time} seek={seek} />
        <div className="grid content-start gap-2">
          <Button variant="outline" className="justify-start bg-card" onClick={() => void act('cut')}>
            <Scissors aria-hidden />
            {t('review.cut')}
          </Button>
          <Button variant="outline" className="justify-start bg-card" onClick={() => void act('forget')}>
            <Trash2 aria-hidden />
            {t('review.forget')}
          </Button>
          {failed && (
            <p role="alert" className="m-0 text-sm text-destructive">
              {t('review.error')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** Every question answer pinning a piece on one of the conflict's names, each correctable: the
 * player picked is pinned where their name was given. */
function Pinned({ conflict, players, nameOf }: { conflict: Conflict; players: Named[]; nameOf: NameOf }) {
  const { t, i18n } = useTranslation();
  const [failed, setFailed] = useState(false);
  const repin = async (id: string, who: string) => {
    try {
      if (!(await post('repin', { id, who })).cancelled) {
        location.reload();
      }
    } catch {
      setFailed(true);
    }
  };
  return (
    <section className="grid gap-2">
      <h3 className="m-0 text-base font-semibold">{t('review.pinned', { names: new Intl.ListFormat(i18n.language, { type: 'conjunction' }).format(conflict.names) })}</h3>
      <p className="m-0 text-sm text-muted-foreground">{t('review.pinnedNote')}</p>
      <div className="flex flex-wrap gap-2">
        {conflict.pinned.map((a) => (
          <figure key={a.id} className="m-0 grid w-36 content-start gap-1 text-xs">
            <img src={a.crop} alt="" loading="lazy" className="h-40 max-w-none justify-self-center rounded-md bg-muted" />
            <figcaption className="text-center">
              <span className="tabular-nums">{clock(a.time)}</span> · <span className="font-medium">= {a.claim}</span>
            </figcaption>
            <PlayerSelect players={players} nameOf={nameOf} value="" empty={t('review.repin')} label={t('review.repin')} className="w-full" onChange={(who) => who && void repin(a.id, who)} />
          </figure>
        ))}
      </div>
      {failed && (
        <p role="alert" className="m-0 text-sm text-destructive">
          {t('review.error')}
        </p>
      )}
    </section>
  );
}
