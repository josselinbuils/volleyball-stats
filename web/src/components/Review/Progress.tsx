import { useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { compared } from '@/components/Review/helpers/comparison';
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
 * the last run, its change since the one before and a curve of every run, then a table of all of them. */
export function Progress({ runs, comparison }: { runs: LearnRun[]; comparison: Comparison | null }) {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const stamp = new Intl.DateTimeFormat(i18n.language, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  // learn.json's local time, yyyy-mm-dd hh:mm.
  const when = (run: LearnRun) => stamp.format(new Date(run.time.replace(' ', 'T')));

  if (!runs.length) {
    return <p className="rounded-lg border bg-card px-4 py-3 text-muted-foreground">{t('review.progress.none')}</p>;
  }
  const last = runs[runs.length - 1];
  const checked = last.scores['checked: rallies']?.[0];
  const matches = new Set(runs.map((r) => r.match)).size;
  return (
    <div className="grid gap-6">
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
            <div className="overflow-x-auto rounded-lg border bg-card px-4 py-3">
              <table className="w-full text-sm tabular-nums">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="py-1 pr-4 font-normal">{t('review.progress.measureColumn')}</th>
                    {runs.map((r, k) => (
                      <th key={k} className="py-1 pr-4 font-normal whitespace-nowrap">
                        {when(r)} <span className="text-xs">{r.commit}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {GROUPS.flatMap(([, measures]) => measures).map(([key, label]) => (
                    <tr key={key} className="border-t">
                      <td className="py-1 pr-4">{t(`review.progress.measure.${label}`)}</td>
                      {runs.map((r, k) => (
                        <td key={k} className="py-1 pr-4 whitespace-nowrap">
                          {r.scores[key]?.[1] ? `${r.scores[key][0]}/${r.scores[key][1]}` : '–'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </details>
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
