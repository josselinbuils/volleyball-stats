import { useState } from 'react';
import { ImageIcon, LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';
import { match } from '@/lib/match';
import { post, review, type Named } from '@/lib/review';

/** The player's card picture as the match page shows it, and the other moments to pick for it; a pick
 * rebuilds the pages, then the review reloads. While `stale` (an apply came since), the picture shows as out of date,
 * or a placeholder for none, and none can be picked. */
export function PhotoPicker({ player, stale, onError }: { player: Named; stale: boolean; onError: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const found = review?.photos?.[`${player.team}:${player.identity}`] ?? [];
  const current = Object.values(match.people).find((x) => x.team === player.team && x.number === player.identity)?.photo;
  if (!found.length && !current && !stale) {
    return null;
  }
  const pick = async (frame: number, box: number[]) => {
    setSaving(true);
    try {
      await post('photo', { team: player.team, identity: player.identity, frame, box });
      location.reload();
    } catch {
      setSaving(false);
      onError();
    }
  };

  return (
    <div className="grid gap-2">
      <div className="flex items-end gap-3">
        {stale ? (
          <Tip label={t('review.photoUpdating')}>
            <div className="relative grid h-24 w-18 place-items-center overflow-hidden rounded-md bg-muted" role="img" aria-label={t('review.photoUpdating')}>
              {current && <img src={current} alt="" className="absolute inset-0 size-full object-cover object-top opacity-40" />}
              <LoaderCircle aria-hidden className="relative size-5 animate-spin text-foreground" />
            </div>
          </Tip>
        ) : (
          current && <img src={current} alt={t('review.currentPhoto')} className="h-24 w-18 rounded-md bg-muted object-cover object-top" />
        )}
        {found.length > 0 && (
          <Button variant="outline" size="sm" className="bg-card" disabled={saving || stale} onClick={() => setOpen((o) => !o)}>
            <ImageIcon aria-hidden />
            {saving ? t('review.saving') : t('review.changePhoto')}
          </Button>
        )}
      </div>
      {open && !stale && (
        <div className="grid grid-cols-4 gap-1.5">
          {found.map((m, k) => (
            <button
              key={`${m.frame}:${m.box.join(',')}`}
              type="button"
              disabled={saving}
              aria-pressed={k === 0}
              className={cn('overflow-hidden rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50', k === 0 ? 'ring-2 ring-primary' : 'opacity-90 hover:opacity-100')}
              onClick={() => (k === 0 ? setOpen(false) : void pick(m.frame, m.box))}
            >
              <img src={m.crop} alt={k === 0 ? t('review.currentPhoto') : t('review.photoN', { n: k + 1 })} loading="lazy" className="aspect-[3/4] w-full bg-muted object-cover object-top" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
