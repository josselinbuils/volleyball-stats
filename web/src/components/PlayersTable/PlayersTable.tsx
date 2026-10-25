import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { CountButton } from '@/components/CountButton';
import { SetBadge } from '@/components/SetBadge';
import { Swatch } from '@/components/Swatch';
import { useFormat } from '@/lib/format';
import { GROUPS, groupName, hasTeams, match, playerLabel, playerNumber, teamColor, teamRing, type Contact, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { lines, type Line, type Stat } from '@/components/PlayersTable/helpers/stats';

/** Each column's count and the counts under it. */
const COLUMNS: { stat: Stat; sub: Stat[] }[] = [
  { stat: 'touches', sub: [] },
  { stat: 'serves', sub: ['aces', 'serveFaults'] },
  { stat: 'receptions', sub: [] },
  { stat: 'missed', sub: [] },
  { stat: 'attacks', sub: ['attackFaults'] },
  { stat: 'kills', sub: [] },
  { stat: 'blocks', sub: ['blockPoints'] },
  { stat: 'digs', sub: [] },
  { stat: 'sets', sub: [] },
  { stat: 'points', sub: [] },
  { stat: 'faults', sub: [] },
];
// The player column stays in view while the table scrolls sideways on a phone.
const FIRST = 'sticky left-0 z-10 min-w-32 bg-card pl-3 max-sm:pl-2 max-sm:shadow-[inset_-1px_0_0_var(--border)]';

/** What each player of a team did with the ball, a count per action and how it ended. */
export function PlayersTable() {
  const { t } = useTranslation();
  const { set, contacts } = useSet();
  const [group, setGroup] = useState<Group>(1);
  if (!hasTeams || !Object.values(match.people).some((p) => p.number !== null)) {
    return null;
  }
  const table = lines(contacts, match.people, group);
  const label = (line: Line) => (tr: TFunction) => (line.id === 'rest' ? tr('players.rest') : line.id === 'total' ? groupName(tr, group) : (playerLabel(tr, line.id) ?? ''));
  const row = (line: Line) => (
    <TableRow key={line.id} className={line.id === 'total' ? 'hover:bg-transparent' : undefined}>
      {/* Level with the counts, which have their details under them. */}
      <TableCell className={cn(FIRST, 'max-w-48 py-1.5 align-top whitespace-normal', line.id === 'total' && 'font-semibold')}>
        {typeof line.id === 'number' ? (
          <Who person={line.id} g={group} />
        ) : (
          <span className={cn('flex min-h-8 items-center', line.id === 'rest' && 'text-muted-foreground')}>{t(`players.${line.id}`)}</span>
        )}
      </TableCell>
      {COLUMNS.map(({ stat, sub }) => (
        <TableCell key={stat} className="px-1 py-1.5 text-center align-top">
          <CountButton id={`players:${set}:${group}:${line.id}:${stat}`} title={(tr) => `${tr(`players.stats.${stat}`)}, ${label(line)(tr)}`} picked={line.stats[stat]} />
          {sub.some((s) => line.stats[s].length) && (
            <div className="mt-0.5 grid justify-items-center text-xs leading-snug">
              {sub.map(
                (s) =>
                  line.stats[s].length > 0 && (
                    <SubCount key={s} id={`players:${set}:${group}:${line.id}:${s}`} stat={s} title={(tr) => `${tr(`players.stats.${s}`)}, ${label(line)(tr)}`} picked={line.stats[s]} />
                  ),
              )}
            </div>
          )}
        </TableCell>
      ))}
    </TableRow>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('players.title')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t('players.caption')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <ToggleGroup
          type="single"
          variant="outline"
          spacing={0}
          value={String(group)}
          onValueChange={(v) => {
            if (v) {
              setGroup(Number(v) as Group);
            }
          }}
          aria-label={t('teamFilter')}
          className="w-full items-stretch bg-card sm:w-auto"
        >
          {GROUPS.map((g) => (
            <ToggleGroupItem
              key={g}
              value={String(g)}
              className="h-auto min-h-8 flex-1 gap-2 py-1.5 leading-tight whitespace-normal data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-none"
            >
              <Swatch color={teamColor(g)} ring={teamRing(g)} />
              {groupName(t, g)}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <Table className="tabular-nums">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className={cn(FIRST, 'text-muted-foreground')}>{t('players.player')}</TableHead>
              {COLUMNS.map(({ stat }) => (
                <TableHead key={stat} className="min-w-20 px-1 text-center leading-tight whitespace-normal text-muted-foreground">
                  {t(`players.stats.${stat}`)}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>{table.filter((line) => line.id !== 'total').map(row)}</TableBody>
          <TableFooter className="bg-transparent">{table.filter((line) => line.id === 'total').map(row)}</TableFooter>
        </Table>
        <p className="text-[13px] text-muted-foreground">{t('players.note')}</p>
      </CardContent>
    </Card>
  );
}

/** A player's number in their team's colour, and their name. */
function Who({ person, g }: { person: number; g: Group }) {
  const { t } = useTranslation();
  return (
    <span className="flex min-h-8 items-center gap-2">
      <span
        aria-hidden
        className="inline-grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold"
        style={{ background: teamColor(g), color: `var(--team${g}-text)`, boxShadow: `inset 0 0 0 1.5px ${teamRing(g)}` }}
      >
        {playerNumber(person)}
      </span>
      <span className="break-words">{playerLabel(t, person)}</span>
    </span>
  );
}

/** A count under a column's, as words ("2 aces"), that plays its touches. */
function SubCount({ id, stat, title, picked }: { id: string; stat: Stat; title: (t: TFunction) => string; picked: Contact[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play } = usePlayer();
  const on = playlist?.key === id;
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={`${t(`players.sub.${stat}`, { count: picked.length, n: f.num(picked.length) })} · ${title(t)} · ${t('watchN', { count: picked.length })}`}
      className={cn(
        'rounded px-1 whitespace-nowrap hover:text-link hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none',
        on ? 'bg-primary text-primary-foreground hover:text-primary-foreground' : 'text-muted-foreground',
      )}
      onClick={() => play(title, contactClips(picked, match.duration), 0, id)}
    >
      {t(`players.sub.${stat}`, { count: picked.length, n: f.num(picked.length) })}
    </button>
  );
}
