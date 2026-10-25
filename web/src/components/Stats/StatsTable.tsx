import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { CountButton } from '@/components/CountButton';
import type { Stat, Stats } from '@/components/Stats/helpers/stats';

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
  { stat: 'sets', of: 'sets', label: 'total' },
  { stat: 'attacks', of: 'attacks', label: 'total' },
  { stat: 'kills', of: 'attacks', label: 'kills' },
  { stat: 'attackFaults', of: 'attacks', label: 'faults' },
  { stat: 'relances', of: 'relances', label: 'total' },
  { stat: 'relanceFaults', of: 'relances', label: 'faults' },
  { stat: 'blocks', of: 'blocks', label: 'total' },
  { stat: 'digs', of: 'digs', label: 'total' },
  { stat: 'digFaults', of: 'digs', label: 'faults' },
  { stat: 'unattackedDigs', of: 'digs', label: 'unattacked' },
  { stat: 'points', of: 'overall', label: 'points' },
  { stat: 'faults', of: 'overall', label: 'faults' },
];
// A line parts each group from its neighbours.
const parts = (k: number) => k > 0 && COLUMNS[k - 1].of !== COLUMNS[k].of;
const HEAD = 'px-1 text-center leading-tight whitespace-normal text-muted-foreground';
// The first column stays in view while the table scrolls sideways.
const FIRST = 'sticky left-0 z-10 min-w-32 bg-card pl-3 shadow-[inset_-1px_0_0_var(--border)] max-sm:pl-2';

/** A row: its first cell (`name`), its name in a playlist's title, its counts; a `total` row sits in
 * the footer. */
export interface Row {
  key: string | number;
  name: ReactNode;
  title: (t: TFunction) => string;
  stats: Stats;
  total?: boolean;
}

/** Counts of touches per action and how they ended, `first` heading the rows' column; each count
 * plays its touches. */
export function StatsTable({ id, first, rows }: { id: string; first: string; rows: Row[] }) {
  const { t } = useTranslation();
  const row = (r: Row) => (
    <TableRow key={r.key} className={r.total ? 'hover:bg-transparent' : undefined}>
      <TableCell className={cn(FIRST, 'max-w-48 py-1.5 whitespace-normal', r.total && 'font-semibold')}>{r.name}</TableCell>
      {COLUMNS.map(({ stat }, k) => (
        <TableCell key={stat} className={cn('px-1 py-1.5 text-center', parts(k) && 'border-l')}>
          <CountButton id={`${id}:${r.key}:${stat}`} title={(tr) => `${tr(`stats.names.${stat}`)}, ${r.title(tr)}`} picked={r.stats[stat]} className="min-w-10" />
        </TableCell>
      ))}
    </TableRow>
  );
  const totals = rows.filter((r) => r.total);

  return (
    <Table className="tabular-nums">
      <TableHeader>
        <TableRow className="border-b-0 hover:bg-transparent">
          <TableHead rowSpan={2} className={cn(FIRST, 'text-muted-foreground')}>
            {first}
          </TableHead>
          {COLUMNS.map(
            ({ of }, k) =>
              (k === 0 || parts(k)) && (
                <TableHead key={of} colSpan={COLUMNS.filter((c) => c.of === of).length} className={cn(HEAD, 'h-8 border-b font-semibold text-foreground', parts(k) && 'border-l')}>
                  {t(`stats.names.${of}`)}
                </TableHead>
              ),
          )}
        </TableRow>
        <TableRow className="hover:bg-transparent">
          {COLUMNS.map(({ stat, label }, k) => (
            <TableHead key={stat} className={cn(HEAD, 'h-8 min-w-14', parts(k) && 'border-l')}>
              {t(`stats.columns.${label}`)}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>{rows.filter((r) => !r.total).map(row)}</TableBody>
      {totals.length > 0 && <TableFooter className="bg-transparent">{totals.map(row)}</TableFooter>}
    </Table>
  );
}
