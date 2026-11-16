import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';
import { match } from '@/lib/match';
import { FIGURES, HAIRS, SKINS, type HairColour, type Look } from '@/lib/looks';
import { post, type Named } from '@/lib/review';
import { cn } from '@/lib/utils';

/** The player's 3D figure, a man's or a woman's, and their hair colour over the one guessed, or bald: each saved at once by their
 * name (their next matches take it too), the page's figure following. */
export function LookChoice({ player, onError }: { player: Named; onError: () => void }) {
  const { t } = useTranslation();
  const person = Object.values(match.people).find((x) => x.team === player.team && x.number === player.identity);
  // Without a look, the figure's own: a man's, short black hair (scene.ts).
  const [look, setLook] = useState<Required<Pick<Look, 'figure' | 'hair'>>>({ figure: person?.look?.figure ?? 'man', hair: person?.look?.hair ?? 'black' });
  const [saving, setSaving] = useState<string | null>(null);
  if (!person) {
    return null;
  }
  const pick = async (field: 'figure' | 'hair', value: string) => {
    const before = look;
    setLook({ ...look, [field]: value });
    setSaving(value);
    try {
      await post('look', { team: player.team, identity: player.identity, field, value });
      person.look = { ...person.look, [field]: value };
    } catch {
      setLook(before);
      onError();
    } finally {
      setSaving(null);
    }
  };
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-2">
      <div className="grid gap-1 text-sm font-medium">
        {t('review.figure')}
        <div className="flex gap-1.5">
          {FIGURES.map((f) => (
            <Button
              key={f}
              variant={look.figure === f ? 'default' : 'outline'}
              size="sm"
              className={look.figure === f ? undefined : 'bg-card'}
              aria-pressed={look.figure === f}
              disabled={!!saving}
              busy={saving === f}
              onClick={() => look.figure !== f && void pick('figure', f)}
            >
              {t(`review.figures.${f}`)}
            </Button>
          ))}
        </div>
      </div>
      <div className="grid gap-1 text-sm font-medium">
        {t('review.hair')}
        <div className="flex gap-1.5">
          {[...(Object.keys(HAIRS) as HairColour[]), 'bald' as const].map((h) => (
            <Tip key={h} label={t(`review.hairs.${h}`)}>
              <Button
                variant="outline"
                size="icon-sm"
                className={cn('bg-card', look.hair === h && 'border-primary ring-2 ring-primary/50')}
                aria-label={t(`review.hairs.${h}`)}
                aria-pressed={look.hair === h}
                disabled={!!saving}
                busy={saving === h}
                onClick={() => look.hair !== h && void pick('hair', h)}
              >
                <span aria-hidden className="size-4 rounded-full border border-black/10" style={{ background: h === 'bald' ? SKINS[(person.look?.skin ?? 2) - 1] : HAIRS[h] }} />
              </Button>
            </Tip>
          ))}
        </div>
      </div>
    </div>
  );
}
