import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { GROUPS, groupName, match, type Group } from '@/lib/match';
import type { Named } from '@/lib/review';
import { OptionList, useFieldPlace } from '@/components/Review/OptionList';
import { jerseyOf, matching, pictureOf, playerOptions, type NameOf } from '@/components/Review/helpers/players';

const FIELD =
  'size-full min-w-0 rounded-md border border-input bg-transparent px-1.5 shadow-xs outline-none dark:bg-input/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50';

/** A field picking one of both teams' players as `playerOptions` gives them, by name (`nameOf`)
 * when they have one or jersey number, or "not a player" if `notPlayer`: a list under it shows the players its text
 * matches, the first one highlighted; Enter or a click picks the highlighted one, the arrows move
 * it. A named player shows their picture, in the list and in the field. `value` and `onChange` hold `team:identity`, 'not_player', or '' for `empty` (an emptied
 * field). */
export function PlayerSelect({
  players,
  nameOf,
  exclude,
  notPlayer = false,
  autoFocus = false,
  openOnFocus = true,
  onDone,
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
  autoFocus?: boolean;
  /** Whether the list opens with the focus, or only once typing starts (the field focused first). */
  openOnFocus?: boolean;
  /** Called once a player is picked or the typing given up, to move the focus back. */
  onDone?: () => void;
  value: string;
  empty: string;
  label: string;
  className?: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const list = useId();
  const field = useRef<HTMLInputElement>(null);
  const { options, value: shown } = playerOptions(players, nameOf, exclude, value);
  // Numbers repeat across teams: each entry names its team.
  const entries: { key: string; label: string; picture?: string; jersey?: number | null }[] = [
    ...(notPlayer ? [{ key: 'not_player', label: t('review.notPlayer') }] : []),
    ...GROUPS.flatMap((g) =>
      options
        .filter((p) => p.team === g)
        .map((p) => {
          const name = nameOf(p.team, p.identity);
          const jersey = jerseyOf(p, players, nameOf);
          return {
            key: `${p.team}:${p.identity}`,
            picture: pictureOf(p, nameOf, Object.values(match.people)),
            jersey,
            label: `${jersey === null ? '' : `#${jersey} `}${name ?? t('player', { n: p.identity })} · ${groupName(t, g)}`,
          };
        }),
    ),
  ];
  const chosen = entries.find((e) => e.key === shown);
  const current = chosen?.label ?? '';
  const [text, setText] = useState(current);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const place = useFieldPlace(field, open);
  useEffect(() => setText(current), [current]);
  const found = matching(entries, text === current ? '' : text);
  // The picture stays while the field shows its player, not once typing starts.
  const picture = text === current ? chosen?.picture : undefined;
  const pick = (key: string) => {
    setOpen(false);
    setText(entries.find((e) => e.key === key)?.label ?? '');
    if (key !== shown) {
      onChange(key);
    }
    onDone?.();
  };

  return (
    <>
      <span className={cn('relative block h-8 text-[13px]', className)}>
        {picture && <img src={picture} alt="" className="pointer-events-none absolute top-1/2 left-1 size-6 -translate-y-1/2 rounded-sm bg-muted object-cover object-top" />}
        <input
          ref={field}
          role="combobox"
          aria-expanded={open}
          aria-controls={list}
          aria-activedescendant={open && found[active] ? `${list}-${active}` : undefined}
          aria-label={label}
          placeholder={empty}
          autoFocus={autoFocus}
          value={text}
          onFocus={(e) => {
            // Typing replaces the player shown.
            e.target.select();
            setOpen(openOnFocus);
          }}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
              e.preventDefault();
              setOpen(true);
              setActive((k) => Math.max(0, Math.min(found.length - 1, k + (e.key === 'ArrowDown' ? 1 : -1))));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              if (!text.trim()) {
                setOpen(false);
                if (shown) {
                  onChange('');
                }
              } else if (found[active]) {
                pick(found[active].key);
              }
            } else if (e.key === 'Escape') {
              setText(current);
              setOpen(false);
              onDone?.();
            }
          }}
          onBlur={() => {
            setOpen(false);
            if (!text.trim() && shown) {
              onChange('');
            } else {
              setText(current);
            }
          }}
          className={cn(FIELD, picture && 'pl-8')}
        />
      </span>
      {open && place && found.length > 0 && <OptionList id={list} label={label} place={place} options={found} active={active} onPick={pick} onActive={setActive} />}
    </>
  );
}
