import { useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { CountButton } from '@/components/CountButton';
import { clock, useFormat } from '@/lib/format';
import { match } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import type { Insight } from '@/components/Stats/helpers/insights';
import { meanRating, type Stat, type Stats } from '@/components/Stats/helpers/stats';

/** The columns, each a count of touches (`stat`) under its group's title (`of`), named by `label`
 * within it. */
export const COLUMNS: { stat: Stat; of: Stat | 'overall'; label: string }[] = [
  { stat: 'touches', of: 'touches', label: 'total' },
  { stat: 'serves', of: 'serves', label: 'total' },
  { stat: 'aces', of: 'serves', label: 'aces' },
  { stat: 'serveFaults', of: 'serves', label: 'faults' },
  { stat: 'receptions', of: 'receptions', label: 'total' },
  { stat: 'missed', of: 'receptions', label: 'faults' },
  { stat: 'unattacked', of: 'receptions', label: 'unattacked' },
  { stat: 'rated', of: 'receptions', label: 'rating' },
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
  { stat: 'between', of: 'overall', label: 'between' },
];
const HEAD = 'px-1 text-center leading-tight whitespace-normal text-muted-foreground';
// The first column stays in view while the table scrolls sideways.
const FIRST = 'sticky left-0 z-10 min-w-32 bg-card pl-3 shadow-[inset_-1px_0_0_var(--border)] max-sm:pl-2';

/** A row: its first cell (`name`), its name in a playlist's title, its counts and what their hover
 * adds (`tips`), its strengths and things to work on; a `total` row sits in the footer. */
export interface Row {
  key: string | number;
  name: ReactNode;
  title: (t: TFunction) => string;
  stats: Stats;
  tips?: Partial<Record<Stat, string>>;
  insights?: Insight[];
  total?: boolean;
  /** A player's time on the court, in seconds. */
  seconds?: number;
}

/** Counts of touches per action and how they ended in `columns`, `first` heading the rows' column,
 * then the rows' strengths and things to work on when `insights`; each count and each of those
 * plays its touches. The receptions' rating shows their mean grade. A column's title sorts the rows
 * by it, most first, then fewest first, then back to their order. */
export function StatsTable({ id, first, rows, columns = COLUMNS, insights = false }: { id: string; first: string; rows: Row[]; columns?: typeof COLUMNS; insights?: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [sort, setSort] = useState<{ stat: Stat | 'time'; desc: boolean } | null>(null);
  const sortBy = (stat: Stat | 'time') => setSort((s) => (s?.stat !== stat ? { stat, desc: true } : s.desc ? { stat, desc: false } : null));
  const value = (r: Row, stat: Stat | 'time') => (stat === 'time' ? (r.seconds ?? -1) : stat === 'rated' ? (meanRating(r.stats) ?? -1) : r.stats[stat].length);
  const order = (stat: Stat | 'time') => (sort?.stat === stat ? (sort.desc ? 'descending' : 'ascending') : undefined);
  // The players' time on the court, beside their names.
  const timed = rows.some((r) => r.seconds !== undefined);
  const body = rows.filter((r) => !r.total);
  const sorted = sort ? [...body].sort((a, b) => (value(b, sort.stat) - value(a, sort.stat)) * (sort.desc ? 1 : -1)) : body;
  // A line parts each group from its neighbours.
  const parts = (k: number) => k > 0 && columns[k - 1].of !== columns[k].of;
  const tip = (r: Row, stat: Stat) =>
    stat === 'rated' ? t('stats.ratingDetail', { perfect: r.stats.perfect.length, good: r.stats.good.length, poor: r.stats.poor.length, missed: r.stats.missed.length }) : r.tips?.[stat];
  const row = (r: Row) => (
    <TableRow key={r.key} className={r.total ? 'hover:bg-transparent' : undefined}>
      <TableCell className={cn(FIRST, 'max-w-48 py-1.5 whitespace-normal', r.total && 'font-semibold')}>{r.name}</TableCell>
      {timed && <TableCell className="border-r px-2 py-1.5 text-center text-muted-foreground">{r.seconds !== undefined && clock(r.seconds)}</TableCell>}
      {columns.map(({ stat }, k) => (
        <TableCell key={stat} className={cn('px-1 py-1.5 text-center', parts(k) && 'border-l')}>
          <CountButton
            id={`${id}:${r.key}:${stat}`}
            title={(tr) => `${tr(`stats.names.${stat}`)}, ${r.title(tr)}`}
            picked={r.stats[stat]}
            value={stat === 'rated' && r.stats.rated.length ? f.dec(meanRating(r.stats)!) : undefined}
            tip={tip(r, stat)}
            className="min-w-10"
          />
        </TableCell>
      ))}
      {insights &&
        [true, false].map((strength) => (
          <TableCell key={String(strength)} className={cn('min-w-44 px-2 py-1.5', strength && 'border-l')}>
            <div className="flex flex-wrap gap-1">
              {r.insights
                ?.filter((i) => i.strength === strength)
                .map((i) => (
                  <InsightChip key={i.key} id={`${id}:${r.key}:${i.key}`} insight={i} who={r.title} />
                ))}
            </div>
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
          {timed && (
            <TableHead rowSpan={2} aria-sort={order('time')} className={cn(HEAD, 'min-w-16 border-r')}>
              <ColumnTitle title={t('stats.columns.time')} about={t('stats.about.time')} order={order('time')} onSort={() => sortBy('time')} />
            </TableHead>
          )}
          {columns.map(
            ({ of }, k) =>
              (k === 0 || parts(k)) && (
                <TableHead key={of} colSpan={columns.filter((c) => c.of === of).length} className={cn(HEAD, 'h-8 border-b font-semibold text-foreground', parts(k) && 'border-l')}>
                  {t(`stats.names.${of}`)}
                </TableHead>
              ),
          )}
          {insights && (
            <TableHead colSpan={2} className={cn(HEAD, 'h-8 border-b border-l font-semibold text-foreground')}>
              {t('stats.insights.title')}
            </TableHead>
          )}
        </TableRow>
        <TableRow className="hover:bg-transparent">
          {columns.map(({ stat, label }, k) => (
            <TableHead key={stat} aria-sort={order(stat)} className={cn(HEAD, 'h-8 min-w-14', parts(k) && 'border-l')}>
              <ColumnTitle title={t(`stats.columns.${label}`)} about={t(`stats.about.${stat}`)} order={order(stat)} onSort={() => sortBy(stat)} />
            </TableHead>
          ))}
          {insights &&
            (['strengths', 'toWorkOn'] as const).map((key) => (
              <TableHead key={key} className={cn(HEAD, 'h-8', key === 'strengths' && 'border-l')}>
                <ColumnTitle title={t(`stats.insights.${key}`)} about={t(`stats.about.${key}`)} />
              </TableHead>
            ))}
        </TableRow>
      </TableHeader>
      <TableBody>{sorted.map(row)}</TableBody>
      {totals.length > 0 && <TableFooter className="bg-transparent">{totals.map(row)}</TableFooter>}
    </Table>
  );
}

/** A column's title, `about` explaining it on hover, focus or tap (a tap does not open a tooltip on
 * its own); a click also sorts by it (`onSort`), its `order` shown by an arrow. */
function ColumnTitle({ title, about, order, onSort }: { title: string; about: string; order?: 'ascending' | 'descending'; onSort?: () => void }) {
  const [open, setOpen] = useState(false);
  const Arrow = order === 'ascending' ? ArrowUp : ArrowDown;
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn('inline-flex items-center gap-0.5 rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50', order && 'font-semibold text-foreground')}
          onClick={(e) => {
            // Kept open: the trigger's own click handler would close it.
            e.preventDefault();
            setOpen(true);
            onSort?.();
          }}
        >
          {title}
          {order && <Arrow aria-hidden className="size-3 shrink-0" />}
        </button>
      </TooltipTrigger>
      <TooltipContent>{about}</TooltipContent>
    </Tooltip>
  );
}

/** A strength (green) or a thing to work on (amber), its comparison with the rest of the team on
 * hover; a click plays its touches. */
export function InsightChip({ id, insight: i, who }: { id: string; insight: Insight; who: (t: TFunction) => string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play } = usePlayer();
  const label = (tr: TFunction) => tr(`stats.insights.${i.key}`, { count: i.n, of: i.of });
  const detail = t('stats.insights.detail', { n: i.n, of: i.of, p: f.pct(i.n / i.of), restN: i.restN, restOf: i.restOf, restP: f.pct(i.restN / i.restOf) });
  const on = playlist?.key === id;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-pressed={on}
          aria-label={`${label(t)} · ${detail} · ${t('watchN', { count: i.picked.length })}`}
          className={cn(
            'rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
            i.strength
              ? 'bg-emerald-100 text-emerald-900 hover:bg-emerald-200 dark:bg-emerald-950 dark:text-emerald-200 dark:hover:bg-emerald-900'
              : 'bg-amber-100 text-amber-900 hover:bg-amber-200 dark:bg-amber-950 dark:text-amber-200 dark:hover:bg-amber-900',
            on && 'ring-2 ring-primary',
          )}
          onClick={() => play((tr) => `${label(tr)}, ${who(tr)}`, contactClips(i.picked, match.duration), 0, id)}
        >
          {label(t)}
        </button>
      </TooltipTrigger>
      <TooltipContent>{detail}</TooltipContent>
    </Tooltip>
  );
}
