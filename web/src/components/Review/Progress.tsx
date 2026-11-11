import { Fragment, useState } from 'react';
import { ArrowDown, ArrowUp, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { compared } from '@/components/Review/helpers/comparison';
import { Tip } from '@/components/Tip';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useFormat } from '@/lib/format';
import type { Comparison, LearnRun } from '@/lib/review';
import { cn } from '@/lib/utils';

// learn.json's measures, by step, with their label key: each a share of answers or labels right.
const GROUPS: [string, [string, string][]][] = [
  [
    'who',
    [
      ['attribution: answered touches', 'touched'],
      ['attribution: held out, learned', 'heldLearned'],
      ['attribution: held out, rule', 'heldRule'],
    ],
  ],
  [
    'touches',
    [
      ['contacts: added touches found', 'added'],
      ['contacts: false ones gone', 'false'],
      ['actions: types set', 'types'],
    ],
  ],
  [
    'rallies',
    [
      ['rallies: kept', 'kept'],
      ['rallies: dropped', 'dropped'],
      ['rallies: labelled serves with a window', 'serves'],
      ['points: labelled servers', 'servers'],
      ['points: labelled winners', 'winners'],
    ],
  ],
  [
    'checked',
    [
      ['checked: touches found', 'checkedFound'],
      ['checked: pipeline touches kept', 'checkedKept'],
      ['checked: types', 'checkedTypes'],
      ['checked: named players', 'checkedPlayers'],
      ['checked: winners', 'checkedWinners'],
    ],
  ],
];

// The sparkline's box, in SVG units: the full height is 0 to 100%.
const W = 240;
const H = 56;
const PAD = 6;

/** The last run against the results it replaced, then in a history each step's share right on the
 * answers of all the matches over the analysis runs (learn.json, each counting every match so far):
 * the last run, its change since the one before and a curve of every run, then a table of all of them;
 * above them the button making a new run (`onLearn`), `reviewed` saying it leaves the match as it is. */
export function Progress({
  runs,
  comparison,
  reviewed,
  busy,
  learning,
  onLearn,
}: {
  runs: LearnRun[];
  comparison: Comparison | null;
  reviewed: boolean;
  busy: boolean;
  /** The learning asked here runs. */
  learning: boolean;
  onLearn: () => void;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  // learn.json's local time, yyyy-mm-dd hh:mm.
  const when = (run: LearnRun) => f.when(run.time.replace(' ', 'T'));

  const learn = (
    <Tip label={t(reviewed ? 'review.rerunNoteReviewed' : 'review.rerunNote')}>
      <Button
        variant="outline"
        className="justify-self-start bg-card"
        busy={learning}
        disabled={busy}
        onClick={() => {
          if (window.confirm(t(reviewed ? 'review.rerunConfirmReviewed' : 'review.rerunConfirm'))) {
            onLearn();
          }
        }}
      >
        <RefreshCw aria-hidden />
        {t('review.rerun')}
      </Button>
    </Tip>
  );
  if (!runs.length) {
    return (
      <div className="grid gap-6">
        {learn}
        <p className="m-0 rounded-lg border bg-card px-4 py-3 text-muted-foreground">{t('review.progress.none')}</p>
      </div>
    );
  }
  const last = runs[runs.length - 1];
  const checked = last.scores['checked: rallies']?.[0];
  const matches = new Set(runs.map((r) => r.match)).size;
  return (
    <div className="grid gap-6">
      {learn}
      <p className="m-0 px-1 text-sm text-muted-foreground">
        {t('review.progress.runs', { count: runs.length, last: when(last), commit: last.commit })}
        {checked ? ` ${t('review.progress.checked', { count: checked })}` : ''}
        {matches > 1 ? ` ${t('review.progress.matches', { count: matches })}` : ''}
      </p>
      {comparison ? <Verdict comparison={comparison} /> : <p className="m-0 rounded-lg border bg-card px-4 py-3 text-muted-foreground">{t('review.progress.verdictSoon')}</p>}
      <details open={!comparison}>
        <summary className="cursor-pointer px-1 font-medium">{t('review.progress.history')}</summary>
        <div className="mt-3 grid gap-6">
          {GROUPS.map(([group, measures]) => {
            const shown = measures.filter(([key]) => runs.some((r) => r.scores[key]?.[1]));
            return (
              shown.length > 0 && (
                <section key={group} className="grid gap-3">
                  <h2 className="m-0 px-1 text-base font-semibold">{t(`review.progress.group.${group}`)}</h2>
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {shown.map(([key, label]) => (
                      <Tile key={key} label={t(`review.progress.measure.${label}`)} points={runs.map((r) => ({ run: r, score: r.scores[key] }))} when={when} f={f} />
                    ))}
                  </div>
                </section>
              )
            );
          })}
          <section className="grid gap-3">
            <h2 className="m-0 px-1 text-base font-semibold">{t('review.progress.table')}</h2>
            <MeasureTable runs={runs} when={when} />
          </section>
        </div>
      </details>
    </div>
  );
}

/** Every measure of every run, newest first and by step: the share right, the counts under it. */
function MeasureTable({ runs, when }: { runs: LearnRun[]; when: (run: LearnRun) => string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const newest = [...runs].reverse();
  const edge = (k: number) => cn(k === newest.length - 1 && 'pr-4');
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table className="tabular-nums">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="sticky left-0 z-10 bg-card pl-4 font-normal text-muted-foreground">{t('review.progress.measureColumn')}</TableHead>
            {newest.map((r, k) => (
              <TableHead key={k} className={cn('h-auto py-2 text-right', k > 0 && 'font-normal text-muted-foreground', edge(k))}>
                {when(r)}
                <span className="block text-xs font-normal text-muted-foreground">{r.commit}</span>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {GROUPS.map(([group, measures]) => {
            const shown = measures.filter(([key]) => runs.some((r) => r.scores[key]?.[1]));
            return (
              shown.length > 0 && (
                <Fragment key={group}>
                  <TableRow className="bg-muted/50 hover:bg-muted/50">
                    <TableCell colSpan={newest.length + 1} className="pl-4 font-medium">
                      <span className="sticky left-4">{t(`review.progress.group.${group}`)}</span>
                    </TableCell>
                  </TableRow>
                  {shown.map(([key, label]) => (
                    <TableRow key={key} className="hover:bg-transparent">
                      <TableCell className="sticky left-0 z-10 max-w-40 min-w-36 bg-card pl-4 whitespace-normal sm:max-w-none sm:whitespace-nowrap">{t(`review.progress.measure.${label}`)}</TableCell>
                      {newest.map((r, k) => {
                        const score = r.scores[key];
                        return (
                          <TableCell key={k} className={cn('text-right', edge(k))}>
                            {score?.[1] ? (
                              <>
                                <span className={cn(k === 0 ? 'font-semibold' : 'text-muted-foreground')}>{f.pct(score[0] / score[1])}</span>
                                <span className="block text-xs text-muted-foreground">
                                  {score[0]}/{score[1]}
                                </span>
                              </>
                            ) : (
                              <span className="text-muted-foreground">–</span>
                            )}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  ))}
                </Fragment>
              )
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

/** What the last run changed: how many measures went each way, then those that moved, the worse first. */
function Verdict({ comparison }: { comparison: Comparison }) {
  const { t } = useTranslation();
  const measures = GROUPS.flatMap(([, list]) => list);
  const { better, worse, same } = compared(
    comparison,
    measures.map(([key]) => key),
  );
  const label = (key: string) => t(`review.progress.measure.${measures.find(([k]) => k === key)![1]}`);
  const counts = [
    { name: 'better', count: better.length, tone: better.length ? 'text-emerald-700 dark:text-emerald-400' : '' },
    { name: 'worse', count: worse.length, tone: worse.length ? 'text-destructive' : '' },
    { name: 'same', count: same, tone: '' },
  ];
  const score = ([right, total]: [number, number]) => `${right}/${total}`;
  return (
    <section className="grid gap-3 rounded-lg border bg-card p-4">
      <h2 className="m-0 text-base font-semibold">{t('review.progress.verdict')}</h2>
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {counts.map(({ name, count, tone }) => (
          <div key={name} className="flex items-baseline gap-2">
            <span className={cn('text-3xl font-semibold tabular-nums', tone)}>{count}</span>
            <span className="text-sm text-muted-foreground">{t(`review.progress.${name}`)}</span>
          </div>
        ))}
      </div>
      {better.length + worse.length > 0 && (
        <ul className="m-0 grid list-none gap-2 p-0">
          {[...worse, ...better].map((key) => (
            <li key={key} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2 text-sm">
              {worse.includes(key) ? <ArrowDown aria-hidden className="size-4 text-destructive" /> : <ArrowUp aria-hidden className="size-4 text-emerald-700 dark:text-emerald-400" />}
              <span>{label(key)}</span>
              <span className="ml-auto text-muted-foreground tabular-nums">
                {score(comparison.before[key])} → {score(comparison.after[key])}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Point = { run: LearnRun; score: [number, number] | undefined };

/** One measure: its last share in large, the change in points since the run before, the curve of its
 * runs; hovering or focusing a point reads that run under it. */
function Tile({ label, points, when, f }: { label: string; points: Point[]; when: (run: LearnRun) => string; f: ReturnType<typeof useFormat> }) {
  const { t } = useTranslation();
  const known = points.filter((p): p is { run: LearnRun; score: [number, number] } => !!p.score?.[1]);
  const [hover, setHover] = useState<number | null>(null);
  const share = (p: (typeof known)[number]) => p.score[0] / p.score[1];
  const last = known[known.length - 1];
  const before = known.length > 1 ? known[known.length - 2] : null;
  const delta = before ? Math.round((share(last) - share(before)) * 100) : 0;
  const x = (k: number) => (known.length === 1 ? W / 2 : PAD + (k * (W - 2 * PAD)) / (known.length - 1));
  const y = (v: number) => PAD + (1 - v) * (H - 2 * PAD);
  const read = known[hover ?? known.length - 1];
  return (
    <div className="grid gap-2 rounded-lg border bg-card p-4">
      <p className="m-0 text-sm text-muted-foreground">{label}</p>
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-semibold">{f.pct(share(last))}</span>
        <span className="text-sm text-muted-foreground tabular-nums">
          {last.score[0]}/{last.score[1]}
        </span>
        {before && delta !== 0 && (
          <span className={cn('ml-auto flex items-center gap-0.5 text-sm font-medium', delta > 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-destructive')}>
            {delta > 0 ? <ArrowUp aria-hidden className="size-4" /> : <ArrowDown aria-hidden className="size-4" />}
            {t('review.progress.delta', { count: Math.abs(delta), sign: delta > 0 ? '+' : '−' })}
          </span>
        )}
      </div>
      {/* The lines stretch with the tile; the dots, HTML on top, stay round. */}
      <div className="relative h-14" role="img" aria-label={t('review.progress.curve', { label })} onMouseLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible" aria-hidden>
          {[0, 0.5, 1].map((v) => (
            <line key={v} x1={0} x2={W} y1={y(v)} y2={y(v)} className="stroke-border" strokeWidth={1} vectorEffect="non-scaling-stroke" />
          ))}
          {known.length > 1 && (
            <polyline
              points={known.map((p, k) => `${x(k)},${y(share(p))}`).join(' ')}
              fill="none"
              className="stroke-primary"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
        {known.map((p, k) => (
          <button
            key={k}
            type="button"
            aria-label={t('review.progress.read', { when: when(p.run), commit: p.run.commit, right: p.score[0], total: p.score[1], share: f.pct(share(p)) })}
            onMouseEnter={() => setHover(k)}
            onFocus={() => setHover(k)}
            onBlur={() => setHover(null)}
            className="absolute flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
            style={{ left: `${(x(k) / W) * 100}%`, top: `${(y(share(p)) / H) * 100}%` }}
          >
            {(k === known.length - 1 || k === hover) && <span className="size-3 rounded-full border-2 border-card bg-primary" />}
          </button>
        ))}
      </div>
      <p className="m-0 text-xs text-muted-foreground tabular-nums" aria-live="polite">
        {t('review.progress.read', { when: when(read.run), commit: read.run.commit, right: read.score[0], total: read.score[1], share: f.pct(share(read)) })}
      </p>
    </div>
  );
}
