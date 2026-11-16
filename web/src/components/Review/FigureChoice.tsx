import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { match } from '@/lib/match';
import { FIGURES, type Figure } from '@/lib/looks';
import { post, type Named } from '@/lib/review';

/** The player's 3D figure, a man's or a woman's: saved at once by their name (their next matches take it too), the page's
 * figure following. */
export function FigureChoice({ player, onError }: { player: Named; onError: () => void }) {
  const { t } = useTranslation();
  const person = Object.values(match.people).find((x) => x.team === player.team && x.number === player.identity);
  const [figure, setFigure] = useState<Figure>(person?.look?.figure ?? 'man');
  const [saving, setSaving] = useState<Figure | null>(null);
  if (!person) {
    return null;
  }
  const pick = async (next: Figure) => {
    const before = figure;
    setFigure(next);
    setSaving(next);
    try {
      await post('figure', { team: player.team, identity: player.identity, figure: next });
      person.look = { ...person.look, figure: next };
    } catch {
      setFigure(before);
      onError();
    } finally {
      setSaving(null);
    }
  };
  return (
    <div className="grid gap-1 text-sm font-medium">
      {t('review.figure')}
      <div className="flex gap-1.5">
        {FIGURES.map((f) => (
          <Button
            key={f}
            variant={figure === f ? 'default' : 'outline'}
            size="sm"
            className={figure === f ? undefined : 'bg-card'}
            aria-pressed={figure === f}
            disabled={!!saving}
            busy={saving === f}
            onClick={() => figure !== f && void pick(f)}
          >
            {t(`review.figures.${f}`)}
          </Button>
        ))}
      </div>
    </div>
  );
}
