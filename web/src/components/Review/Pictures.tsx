import { useState } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { pieceKey, post, review, type Piece } from '@/lib/review';

/** Pieces marked as someone else, shared by every strip showing them. */
const marked = new Set(review?.odd ?? []);

/** An identity's pictures; clicking one marks it as someone else than the others, saved at once and
 * applied with the answers. `onSaved` gets the number of answers saved. */
export function Pictures({ crops, pieces, onSaved, onError }: { crops: string[]; pieces: Piece[]; onSaved: (answered: number) => void; onError: () => void }) {
  const { t } = useTranslation();
  const [odd, setOdd] = useState(() => new Set(pieces.map(pieceKey).filter((k) => marked.has(k))));

  const toggle = async (piece: Piece) => {
    const key = pieceKey(piece);
    const next = new Set(odd);
    if (!next.delete(key)) {
      next.add(key);
    }
    try {
      const { answered } = await post('odd', { odd: pieces.filter((p) => next.has(pieceKey(p))), rest: pieces.filter((p) => !next.has(pieceKey(p))) });
      pieces.forEach((p) => marked.delete(pieceKey(p)));
      next.forEach((k) => marked.add(k));
      setOdd(next);
      if (answered !== undefined) {
        onSaved(answered);
      }
    } catch {
      onError();
    }
  };

  return (
    <div className="grid gap-1.5">
      <div className="flex gap-1.5 overflow-x-auto p-1">
        {crops.map((src, k) => {
          const isOdd = odd.has(pieceKey(pieces[k]));
          return (
            <button
              key={src}
              type="button"
              aria-pressed={isOdd}
              aria-label={t('review.oddMark')}
              title={t('review.oddMark')}
              onClick={() => void toggle(pieces[k])}
              className={cn('relative shrink-0 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50', isOdd && 'ring-2 ring-destructive')}
            >
              <img src={src} alt="" loading="lazy" className={cn('h-52 max-w-none rounded-md bg-muted', isOdd && 'opacity-40')} />
              {isOdd && <X aria-hidden className="absolute inset-0 m-auto size-10 text-destructive" />}
            </button>
          );
        })}
      </div>
      {crops.length > 1 && <p className="m-0 text-[13px] text-muted-foreground">{t('review.oddHint')}</p>}
    </div>
  );
}
