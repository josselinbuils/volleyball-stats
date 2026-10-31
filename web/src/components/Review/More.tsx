import { useRef, useState } from 'react';
import { Images, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { lookAlikes, pieceKey, post, type Found, type Named, type Saved } from '@/lib/review';

/** A button opening the pieces that look most like `player` (`label` naming them), a batch at a
 * time: those left unmarked are confirmed as them, the marked ones as someone else, then the next
 * batch comes. `onSaved` gets what the server tells after saving. */
export function More({ player, label, onSaved, onError }: { player: Named; label: string; onSaved: (saved: Saved) => void; onError: () => void }) {
  const { t } = useTranslation();
  const dialog = useRef<HTMLDialogElement>(null);
  const [pieces, setPieces] = useState<Found[] | null>(null);
  const [odd, setOdd] = useState<Set<string>>(new Set());

  const load = async () => {
    setPieces(null);
    setOdd(new Set());
    try {
      setPieces(await lookAlikes(player.team, player.identity));
    } catch {
      onError();
    }
  };
  const confirm = async () => {
    if (!pieces?.length) {
      return;
    }
    const ref = ({ track, frame }: Found) => ({ track, frame });
    try {
      const saved = await post('more', {
        team: player.team,
        identity: player.identity,
        yes: pieces.filter((p) => !odd.has(pieceKey(p))).map(ref),
        no: pieces.filter((p) => odd.has(pieceKey(p))).map(ref),
      });
      if (saved.cancelled) {
        return;
      }
      onSaved(saved);
      void load();
    } catch {
      onError();
    }
  };
  const toggle = (p: Found) => {
    const next = new Set(odd);
    if (!next.delete(pieceKey(p))) {
      next.add(pieceKey(p));
    }
    setOdd(next);
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="justify-self-start bg-card"
        onClick={() => {
          dialog.current?.showModal();
          void load();
        }}
      >
        <Images aria-hidden />
        {t('review.more', { name: label })}
      </Button>
      <dialog
        ref={dialog}
        aria-label={t('review.more', { name: label })}
        className="m-auto max-h-[calc(100dvh-2rem)] w-[min(64rem,calc(100vw-2rem))] rounded-lg border bg-card p-0 text-card-foreground backdrop:bg-black/60"
      >
        <div className="grid gap-4 p-4">
          <h2 className="m-0 text-lg font-semibold">{t('review.more', { name: label })}</h2>
          <p className="m-0 text-sm text-muted-foreground">{t('review.moreHint', { name: label })}</p>
          {pieces === null ? (
            <p className="m-0 text-sm">{t('review.moreLoading')}</p>
          ) : pieces.length === 0 ? (
            <p className="m-0 text-sm">{t('review.moreNone')}</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {pieces.map((p) => {
                const isOdd = odd.has(pieceKey(p));
                return (
                  <button
                    key={pieceKey(p)}
                    type="button"
                    aria-pressed={isOdd}
                    aria-label={t('review.oddMark')}
                    title={t('review.oddMark')}
                    onClick={() => toggle(p)}
                    className={cn('relative rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50', isOdd && 'ring-2 ring-destructive')}
                  >
                    <img src={p.crop} alt="" loading="lazy" className={cn('h-40 max-w-none rounded-md bg-muted', isOdd && 'opacity-40')} />
                    {isOdd && <X aria-hidden className="absolute inset-0 m-auto size-10 text-destructive" />}
                  </button>
                );
              })}
            </div>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" onClick={() => dialog.current?.close()}>
              {t('review.moreClose')}
            </Button>
            <Button disabled={!pieces?.length} onClick={() => void confirm()}>
              {t('review.moreConfirm')}
            </Button>
          </div>
        </div>
      </dialog>
    </>
  );
}
