import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { GROUPS, groupName, type Group } from '@/lib/match';
import type { Named } from '@/lib/review';
import { entryOf, playerOptions, type NameOf } from '@/components/Review/helpers/players';

const FIELD = 'h-8 rounded-md border border-input bg-transparent px-1.5 text-[13px] shadow-xs outline-none dark:bg-input/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50';

/** A field picking one of both teams' players as `playerOptions` gives them, by name (`nameOf`)
 * when they have one, or "not a player" if `notPlayer`: typing suggests the matching ones, and Enter
 * picks the one left. `value` and `onChange` hold `team:identity`, 'not_player', or '' for `empty`
 * (an emptied field). */
export function PlayerSelect({
  players,
  nameOf,
  exclude,
  notPlayer = false,
  value,
  empty,
  label,
  className,
  onChange,
}: {
  players: Named[];
  nameOf: NameOf;
  exclude?: { team: Group; identity: number };
  notPlayer?: boolean;
  value: string;
  empty: string;
  label: string;
  className?: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const list = useId();
  const { options, value: shown } = playerOptions(players, nameOf, exclude, value);
  // Numbers repeat across teams: each entry names its team.
  const entries = [
    ...(notPlayer ? [{ key: 'not_player', label: t('review.notPlayer') }] : []),
    ...GROUPS.flatMap((g) =>
      options
        .filter((p) => p.team === g)
        .map((p) => {
          const name = nameOf(p.team, p.identity);
          return { key: `${p.team}:${p.identity}`, label: `${name ? t('review.namedPlayer', { name, n: p.identity }) : t('player', { n: p.identity })} · ${groupName(t, g)}` };
        }),
    ),
  ];
  const current = entries.find((e) => e.key === shown)?.label ?? '';
  const [text, setText] = useState(current);
  useEffect(() => setText(current), [current]);

  const pick = (key: string | null) => {
    if (key === null) {
      return;
    }
    setText(entries.find((e) => e.key === key)?.label ?? '');
    if (key !== shown) {
      onChange(key);
    }
  };
  const settle = () => {
    if (!text.trim()) {
      setText('');
      if (shown) {
        onChange('');
      }
    } else {
      pick(entryOf(entries, text));
    }
  };

  return (
    <>
      <input
        list={list}
        aria-label={label}
        placeholder={empty}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          // A suggestion clicked fills in its whole label.
          if (entries.some((x) => x.label === e.target.value)) {
            pick(entries.find((x) => x.label === e.target.value)!.key);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            settle();
          } else if (e.key === 'Escape') {
            setText(current);
          }
        }}
        onBlur={() => (text.trim() ? setText(current) : settle())}
        className={cn(FIELD, className)}
      />
      <datalist id={list}>
        {entries.map((e) => (
          <option key={e.key} value={e.label} />
        ))}
      </datalist>
    </>
  );
}
