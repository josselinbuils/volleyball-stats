import { useState } from 'react';
import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { Group } from '@/lib/match';
import { marked, pieceKey, post, type Named, type Piece } from '@/lib/review';
import { PlayerSelect } from '@/components/Review/PlayerSelect';

/** The pictures of `owner`, an identity; clicking one marks it as someone else than the others, and
 * a list under it says who, among `players` (`nameOf` their names). Saved at once and applied with
 * the answers; `onSaved` gets the number of answers saved. */
export function Pictures({
  crops,
  pieces,
  owner,
  players,
  nameOf,
  onSaved,
  onError,
}: {
  crops: string[];
  pieces: Piece[];
  owner: { team: Group; identity: number };
  players: Named[];
  nameOf: (team: Group, identity: number) => string | null;
  onSaved: (answered: number) => void;
  onError: () => void;
}) {
  const { t } = useTranslation();
  const [odd, setOdd] = useState(() => new Map(pieces.map(pieceKey).flatMap((k) => (marked.has(k) ? [[k, marked.get(k) ?? null] as const] : []))));

  const save = async (next: Map<string, string | null>) => {
    const out = pieces.filter((p) => next.has(pieceKey(p)));
    const to = out.map((p) => {
      const who = next.get(pieceKey(p));
      return who === 'not_player' ? who : who ? { team: Number(who.split(':')[0]), identity: Number(who.split(':')[1]) } : null;
    });
    try {
      const { answered } = await post('odd', { odd: out, rest: pieces.filter((p) => !next.has(pieceKey(p))), to });
      pieces.forEach((p) => marked.delete(pieceKey(p)));
      next.forEach((who, k) => marked.set(k, who));
      setOdd(next);
      if (answered !== undefined) {
        onSaved(answered);
      }
    } catch {
      onError();
    }
  };
  const toggle = (piece: Piece) => {
    const next = new Map(odd);
    if (!next.delete(pieceKey(piece))) {
      next.set(pieceKey(piece), null);
    }
    void save(next);
  };

  return (
    <div className="grid gap-1.5">
      <div className="flex gap-1.5 overflow-x-auto p-1">
        {crops.map((src, k) => {
          const key = pieceKey(pieces[k]);
          const isOdd = odd.has(key);
          return (
            <div key={src} className="grid shrink-0 content-start gap-1">
              <button
                type="button"
                aria-pressed={isOdd}
                aria-label={t('review.oddMark')}
                title={t('review.oddMark')}
                onClick={() => toggle(pieces[k])}
                className={cn('relative rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50', isOdd && 'ring-2 ring-destructive')}
              >
                <img src={src} alt="" loading="lazy" className={cn('h-52 max-w-none rounded-md bg-muted', isOdd && 'opacity-40')} />
                {isOdd && <X aria-hidden className="absolute inset-0 m-auto size-10 text-destructive" />}
              </button>
              {isOdd && (
                <PlayerSelect
                  players={players}
                  nameOf={nameOf}
                  exclude={owner}
                  notPlayer
                  value={odd.get(key) ?? ''}
                  empty={t('review.other')}
                  label={t('review.oddWho')}
                  className="w-0 min-w-full"
                  onChange={(who) => void save(new Map(odd).set(key, who || null))}
                />
              )}
            </div>
          );
        })}
      </div>
      {crops.length > 1 && <p className="m-0 text-[13px] text-muted-foreground">{t('review.oddHint')}</p>}
    </div>
  );
}
