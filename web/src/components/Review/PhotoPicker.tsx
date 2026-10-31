import { useState } from 'react';
import { ImageIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { match } from '@/lib/match';
import { post, review, type Named } from '@/lib/review';

/** The player's card picture as the match page shows it, and the other moments to pick for it, once
 * named (a pick is kept by name); a pick rebuilds the pages, then the review reloads. */
export function PhotoPicker({ player, named, onError }: { player: Named; named: boolean; onError: () => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const found = review?.photos?.[`${player.team}:${player.identity}`] ?? [];
  const current = Object.values(match.people).find((x) => x.team === player.team && x.number === player.identity)?.photo;
  if (!found.length && !current) {
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
        {current && <img src={current} alt={t('review.currentPhoto')} className="h-24 w-18 rounded-md bg-muted object-cover object-top" />}
        {found.length > 0 && (
          <Button variant="outline" size="sm" className="bg-card" disabled={!named || saving} title={named ? undefined : t('review.photoNeedsName')} onClick={() => setOpen((o) => !o)}>
            <ImageIcon aria-hidden />
            {saving ? t('review.saving') : t('review.changePhoto')}
          </Button>
        )}
      </div>
      {open && (
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
