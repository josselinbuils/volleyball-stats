import { Shirt } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, teamColor, teamRing, teams } from '@/lib/match';

/** Each team's name with its colour on the charts and its real jersey colour. */
export function TeamLegend() {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1.5">
      {GROUPS.map((g) => (
        <li key={g} className="inline-flex min-w-0 items-center gap-2 font-medium">
          <Swatch color={teamColor(g)} ring={teamRing(g)} className="size-3" />
          <span className="[overflow-wrap:anywhere]">{groupName(t, g)}</span>
          {teams && (
            <Shirt aria-label={t('jersey')} role="img" className="size-5 shrink-0 text-muted-foreground" fill={teams[g - 1].colour} strokeWidth={1.5}>
              <title>{t('jersey')}</title>
            </Shirt>
          )}
        </li>
      ))}
    </ul>
  );
}
