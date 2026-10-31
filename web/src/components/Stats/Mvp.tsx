import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { clock } from '@/lib/format';
import { GOLD } from '@/components/Stats/helpers/cardPicture';
import type { Stats } from '@/components/Stats/helpers/stats';

export const GOLD_CSS = `linear-gradient(135deg, ${GOLD.map(([at, c]) => `${c} ${at * 100}%`).join(', ')})`;

/** The MVP badge, why on hover, focus or tap as the tables' column titles: a tap does not open a
 * tooltip on its own. `seconds` is the player's time on the court. */
export function Mvp({ stats, seconds, className }: { stats: Stats; seconds: number; className?: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const points = stats.points.length;
  const faults = stats.faults.length;
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-mvp
          className={cn('shrink-0 rounded-full px-2 py-0.5 text-xs font-black tracking-wider text-[#3a2a00] shadow-sm outline-none focus-visible:ring-3 focus-visible:ring-current/50', className)}
          style={{ background: GOLD_CSS }}
          onClick={(e) => {
            // Kept open: the trigger's own click handler would close it.
            e.preventDefault();
            setOpen(true);
          }}
        >
          {t('players.cards.mvp')}
        </button>
      </TooltipTrigger>
      <TooltipContent>{t('players.cards.mvpWhy', { points, faults, balance: points - faults, time: clock(seconds) })}</TooltipContent>
    </Tooltip>
  );
}
