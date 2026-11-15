import { useState, type ReactNode } from 'react';
import { LoaderCircle, Shirt } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';
import { match } from '@/lib/match';
import { HAIRS, SKINS, STYLES, type HairColour, type Look } from '@/lib/looks';
import { post, type Named } from '@/lib/review';

type Field = keyof Look;

/** The player's 3D figure's skin, hair colour and hairstyle, guessed from the video, to correct in a tap each: saved at once
 * by their name (their next matches take it too), the page's figure following. */
export function LookPicker({ player, stale, onError }: { player: Named; stale: boolean; onError: () => void }) {
  const { t } = useTranslation();
  const person = Object.values(match.people).find((x) => x.team === player.team && x.number === player.identity);
  const [look, setLook] = useState<Look>(person?.look ?? {});
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState<string | null>(null);
  if (!person) {
    return null;
  }
  const pick = async (field: Field, value: string | number) => {
    const before = look;
    const after = { ...look, [field]: value };
    setLook(after);
    setSaving(`${field}:${value}`);
    try {
      await post('look', { team: player.team, identity: player.identity, field, value });
      person.look = after;
    } catch {
      setLook(before);
      onError();
    } finally {
      setSaving(null);
    }
  };
  const dot = (field: Field, value: string | number, color: string, label: string) => {
    const chosen = look[field] === value;
    return (
      <Tip key={value} label={label}>
        <button
          type="button"
          aria-label={label}
          aria-pressed={chosen}
          disabled={!!saving || stale}
          className={cn('grid size-7 place-items-center rounded-full outline-none focus-visible:ring-3 focus-visible:ring-ring/50', chosen && 'ring-2 ring-primary ring-offset-2 ring-offset-card')}
          style={{ background: color, boxShadow: 'inset 0 0 0 1px rgb(0 0 0 / 0.15)' }}
          onClick={() => void pick(field, value)}
        >
          {saving === `${field}:${value}` && <LoaderCircle aria-hidden className="size-3.5 animate-spin text-white mix-blend-difference" />}
        </button>
      </Tip>
    );
  };
  const row = (label: string, children: ReactNode) => (
    <div className="grid gap-1.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );

  return (
    <div className="grid gap-2">
      <Button variant="outline" size="sm" className="justify-self-start bg-card" disabled={stale} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Shirt aria-hidden />
        {t('review.look')}
        {look.skin && <span aria-hidden className="size-3 rounded-full" style={{ background: SKINS[look.skin - 1] }} />}
        {look.hair && <span aria-hidden className="-ml-1 size-3 rounded-full" style={{ background: HAIRS[look.hair] }} />}
      </Button>
      {open && !stale && (
        <div className="grid gap-2.5">
          {row(
            t('review.lookSkin'),
            SKINS.map((color, k) => dot('skin', k + 1, color, t('review.skinN', { n: k + 1 }))),
          )}
          {row(
            t('review.lookHair'),
            (Object.keys(HAIRS) as HairColour[]).map((hair) => dot('hair', hair, HAIRS[hair], t(`review.hair.${hair}`))),
          )}
          {row(
            t('review.lookStyle'),
            STYLES.map((style) => (
              <Button
                key={style}
                variant={look.style === style ? 'default' : 'outline'}
                size="sm"
                className={cn(look.style !== style && 'bg-card')}
                aria-pressed={look.style === style}
                disabled={!!saving}
                busy={saving === `style:${style}`}
                onClick={() => void pick('style', style)}
              >
                {t(`review.style.${style}`)}
              </Button>
            )),
          )}
        </div>
      )}
    </div>
  );
}
