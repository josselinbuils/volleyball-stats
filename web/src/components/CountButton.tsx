import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useFormat } from '@/lib/format';
import { match, type Contact } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';

/** A count of touches that plays them, highlighted while they play; a dash for none. */
export function CountButton({ id, title, picked, className }: { id: string; title: (t: TFunction) => string; picked: Contact[]; className?: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play } = usePlayer();

  if (!picked.length) {
    return (
      <span className={cn('inline-block min-w-12 text-center leading-8 text-muted-foreground max-sm:min-w-10', className)} aria-label="0">
        –
      </span>
    );
  }
  const on = playlist?.key === id;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          aria-pressed={on}
          aria-label={`${f.num(picked.length)} · ${title(t)} · ${t('watchN', { count: picked.length })}`}
          className={cn(
            'min-w-12 text-base font-semibold max-sm:min-w-10',
            on ? 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : 'bg-primary/10 text-link hover:bg-primary hover:text-primary-foreground',
            className,
          )}
          onClick={() => play(title, contactClips(picked, match.duration), 0, id)}
        >
          {f.num(picked.length)}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{t('watchN', { count: picked.length })}</TooltipContent>
    </Tooltip>
  );
}
