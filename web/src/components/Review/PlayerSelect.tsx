import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { GROUPS, groupName, type Group } from '@/lib/match';
import { allMarked, type Named } from '@/lib/review';

const SELECT = 'h-8 rounded-md border border-input bg-transparent px-1.5 text-[13px] shadow-xs outline-none dark:bg-input/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50';

/** A list of both teams' players, by name (`nameOf`) when they have one, but `exclude` and those
 * whose every picture is marked as someone else (unless chosen); `value` and `onChange` hold
 * `team:identity`, or '' for `empty`. */
export function PlayerSelect({
  players,
  nameOf,
  exclude,
  value,
  empty,
  label,
  className,
  onChange,
}: {
  players: Named[];
  nameOf: (team: Group, identity: number) => string | null;
  exclude?: { team: Group; identity: number };
  value: string;
  empty: string;
  label: string;
  className?: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className={cn(SELECT, className)}>
      <option value="">{empty}</option>
      {GROUPS.map((g) => (
        <optgroup key={g} label={groupName(t, g)}>
          {players
            .filter((p) => p.team === g && !(exclude && p.team === exclude.team && p.identity === exclude.identity) && (!allMarked(p) || value === `${p.team}:${p.identity}`))
            .map((p) => {
              const name = nameOf(p.team, p.identity);
              return (
                <option key={p.identity} value={`${p.team}:${p.identity}`}>
                  {name ? t('review.namedPlayer', { name, n: p.identity }) : t('player', { n: p.identity })}
                </option>
              );
            })}
        </optgroup>
      ))}
    </select>
  );
}
