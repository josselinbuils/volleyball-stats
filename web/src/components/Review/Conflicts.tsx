import { useRef, useState } from 'react';
import { AlertTriangle, Scissors, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { post, type Conflict, type Linking } from '@/lib/review';

/** The players holding two names after the last apply, each with the answers joining them: a piece
 * to cut where the person changes, or answers to forget. Each action reloads the page. */
export function Conflicts({ conflicts, width, height }: { conflicts: Conflict[]; width: number; height: number }) {
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
      {c.answers.length > 0 && (
        <CardContent className="grid gap-6">
          {c.answers.map((a) => (
            <Linked key={a.id} answer={a} width={width} height={height} />
          ))}
        </CardContent>
      )}
    </Card>
  ));
}

function Linked({ answer, width, height }: { answer: Linking; width: number; height: number }) {
  const { t } = useTranslation();
  const time = useRef(0);
  const [failed, setFailed] = useState(false);
  const act = async (path: 'cut' | 'forget') => {
    try {
      await post(path, { id: answer.id, ...(path === 'cut' ? { at: time.current } : {}) });
      location.reload();
    } catch {
      setFailed(true);
    }
  };
  return (
    <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      {answer.kind === 'piece' ? <ClipVideo clip={answer.clip} width={width} height={height} timeRef={time} /> : <p className="m-0 text-sm text-muted-foreground">{t('review.conflictMarks')}</p>}
      <div className="grid content-start gap-2">
        <div className="flex gap-1.5 overflow-x-auto p-1">
          {answer.crops.map((src) => (
            <img key={src} src={src} alt="" loading="lazy" className="h-40 max-w-none rounded-md bg-muted" />
          ))}
        </div>
        {answer.kind === 'piece' && (
          <Button variant="outline" className="justify-start bg-card" onClick={() => void act('cut')}>
            <Scissors aria-hidden />
            {t('review.cut')}
          </Button>
        )}
        <Button variant="outline" className="justify-start bg-card" onClick={() => void act('forget')}>
          <Trash2 aria-hidden />
          {t(answer.kind === 'piece' ? 'review.forget' : 'review.forgetMarks')}
        </Button>
        {failed && (
          <p role="alert" className="m-0 text-sm text-destructive">
            {t('review.error')}
          </p>
        )}
      </div>
    </div>
  );
}
