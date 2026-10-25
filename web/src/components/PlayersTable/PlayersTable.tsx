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
import { GROUPS, groupName, hasTeams, match, playerLabel, playerNumber, teamColor, teamRing, type Group } from '@/lib/match';
import { useSet } from '@/lib/sets';
import { lines, type Line, type Stat } from '@/components/PlayersTable/helpers/stats';

/** The columns, each a count of touches (`stat`) under its group's title (`of`), named by `label`
 * within it. */
const COLUMNS: { stat: Stat; of: Stat | 'overall'; label: string }[] = [
  { stat: 'touches', of: 'touches', label: 'total' },
  { stat: 'serves', of: 'serves', label: 'total' },
  { stat: 'aces', of: 'serves', label: 'aces' },
  { stat: 'serveFaults', of: 'serves', label: 'faults' },
  { stat: 'receptions', of: 'receptions', label: 'total' },
  { stat: 'missed', of: 'receptions', label: 'faults' },
  { stat: 'unattacked', of: 'receptions', label: 'unattacked' },
  { stat: 'attacks', of: 'attacks', label: 'total' },
  { stat: 'kills', of: 'attacks', label: 'kills' },
  { stat: 'attackFaults', of: 'attacks', label: 'faults' },
  { stat: 'blocks', of: 'blocks', label: 'total' },
  { stat: 'digs', of: 'digs', label: 'total' },
  { stat: 'digFaults', of: 'digs', label: 'faults' },
  { stat: 'unattackedDigs', of: 'digs', label: 'unattacked' },
  { stat: 'sets', of: 'sets', label: 'total' },
  { stat: 'points', of: 'overall', label: 'points' },
  { stat: 'faults', of: 'overall', label: 'faults' },
];
// A line parts each group from its neighbours.
const parts = (k: number) => k > 0 && COLUMNS[k - 1].of !== COLUMNS[k].of;
const HEAD = 'px-1 text-center leading-tight whitespace-normal text-muted-foreground';
// The player column stays in view while the table scrolls sideways on a phone.
const FIRST = 'sticky left-0 z-10 min-w-32 bg-card pl-3 shadow-[inset_-1px_0_0_var(--border)] max-sm:pl-2';

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
      {COLUMNS.map(({ stat }, k) => (
        <TableCell key={stat} className={cn('px-1 py-1.5 text-center', parts(k) && 'border-l')}>
          <CountButton id={`players:${set}:${group}:${line.id}:${stat}`} title={(tr) => `${tr(`players.stats.${stat}`)}, ${label(line)(tr)}`} picked={line.stats[stat]} className="min-w-10" />
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
            <TableRow className="border-b-0 hover:bg-transparent">
              <TableHead rowSpan={2} className={cn(FIRST, 'text-muted-foreground')}>
                {t('players.player')}
              </TableHead>
              {COLUMNS.map(
                ({ of }, k) =>
                  (k === 0 || parts(k)) && (
                    <TableHead key={of} colSpan={COLUMNS.filter((c) => c.of === of).length} className={cn(HEAD, 'h-8 border-b font-semibold text-foreground', parts(k) && 'border-l')}>
                      {t(`players.stats.${of}`)}
                    </TableHead>
                  ),
              )}
            </TableRow>
            <TableRow className="hover:bg-transparent">
              {COLUMNS.map(({ stat, label }, k) => (
                <TableHead key={stat} className={cn(HEAD, 'h-8 min-w-14', parts(k) && 'border-l')}>
                  {t(`players.columns.${label}`)}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>{table.filter((line) => line.id !== 'total').map(row)}</TableBody>
          <TableFooter className="bg-transparent">{table.filter((line) => line.id === 'total').map(row)}</TableFooter>
        </Table>
        <p className="text-[13px] text-muted-foreground">{[t('players.note'), t('players.noteUnattacked'), t('players.noteVideo')].join(' ')}</p>
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
