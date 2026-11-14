import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';
import { useFormat } from '@/lib/format';
import { match, type Contact } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';

/** A count of touches, or `value` in its place, that plays them, `tip` on hover before the
 * count; a dash for none. */
export function CountButton({ title, picked, value, tip, className }: { title: (t: TFunction) => string; picked: Contact[]; value?: string; tip?: string; className?: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { play } = usePlayer();

  if (!picked.length) {
    return (
      <span className={cn('inline-block min-w-12 text-center leading-8 text-muted-foreground max-sm:min-w-10', className)}>
        <span aria-hidden>–</span>
        <span className="sr-only">0</span>
      </span>
    );
  }
  const shown = value ?? f.num(picked.length);
  const hint = [tip, t('watchN', { count: picked.length })].filter(Boolean).join(' · ');
  return (
    <Tip label={hint}>
      <Button
        variant="ghost"
        aria-label={`${shown} · ${title(t)} · ${hint}`}
        className={cn('tap relative min-w-12 bg-primary/10 text-base font-semibold text-link hover:bg-primary hover:text-primary-foreground max-sm:min-w-10', className)}
        onClick={() => play(title, contactClips(picked, match.duration))}
      >
        {shown}
      </Button>
    </Tip>
  );
}
