import { Fragment, useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Swatch } from '@/components/Swatch';
import { Tip } from '@/components/Tip';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useFormat } from '@/lib/format';
import { groupName, match, rallies as allRallies, teamColor, teamRing, timeoutLabel } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { rallyAt, rallyClips } from '@/lib/playlist';
import { usePhone } from '@/lib/phone';
import { useSet } from '@/lib/sets';
import { markY } from '@/components/Story/helpers/marks';
import { momentText } from '@/components/Story/helpers/momentText';
import type { Chapter, Moment } from '@/components/Story/helpers/story';

// The gap the scale shows at least, and the room between two sets, in rallies.
const MIN_GAP = 5;
const SET_ROOM = 3;
// Two moments' marks closer than this share of the width stand one above the other: a mark's width and a little on a
// phone's row.
const MARK_ROOM = 0.035;
const PHONE_MARK_ROOM = 0.1;
// The chart's height, a mark's distance from the curve and from the mark below it, in px.
const HEIGHT = 192;
const PHONE_HEIGHT = 144;
const MARK_OFF = 14;
const MARK_STEP = 26;

/** The score gap after each rally, set after set: above the line team 1 leads, below team 2, with
 * the moments' numbered marks and the timeouts' dashed lines; a rally replays from where it is clicked, a
 * timeout the points after it. On a phone each set has a row of its own, all on one scale: side by side their marks
 * would overlap. */
export function Curve({ chapters, moments }: { chapters: Chapter[]; moments: Moment[] }) {
  const { t } = useTranslation();
  const phone = usePhone();
  const gaps = chapters.flatMap((c) => c.points.map((p) => p.gap));
  const top = Math.max(MIN_GAP, ...gaps);
  const bottom = Math.max(MIN_GAP, ...gaps.map((g) => -g));
  const rows = phone ? chapters.map((c) => [c]) : [chapters];
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {([1, 2] as const).map((g) => (
          <span key={g} className="flex items-center gap-1.5">
            <Swatch color={teamColor(g)} ring={teamRing(g)} />
            {g === 1 ? '↑ ' : '↓ '}
            {t('story.ahead', { team: groupName(t, g) })}
          </span>
        ))}
        {chapters.some((c) => c.timeouts.length > 0) && (
          <span className="flex items-center gap-1.5">
            <svg aria-hidden viewBox="0 0 2 12" className="h-3 w-0.5 overflow-visible">
              <line x1="1" x2="1" y1="0" y2="12" stroke="currentColor" strokeWidth="2" strokeDasharray="3 2" />
            </svg>
            {t('timeout')}
          </span>
        )}
      </div>
      <div className="grid gap-5">
        {rows.map((row) => (
          <Chart key={row[0]?.set} chapters={row} moments={moments} top={top} bottom={bottom} named={chapters.length > 1} height={phone ? PHONE_HEIGHT : HEIGHT} />
        ))}
      </div>
    </div>
  );
}

/** The curve of `chapters` between the gaps `top` and `-bottom`, `height` px high; the sets `named` above it. */
function Chart({ chapters, moments, top, bottom, named, height }: { chapters: Chapter[]; moments: Moment[]; top: number; bottom: number; named: boolean; height: number }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { play } = usePlayer();
  const { set, rallies } = useSet();
  const clip = useId();
  const current = useVideoTime((time) => rallyAt(rallies, time)?.i ?? -1);
  const phone = usePhone();

  // Each point's place along the width, a set starting level.
  const placed: { rally: number; gap: number; x: number; set: number }[] = [];
  let x = 0;
  for (const c of chapters) {
    x++;
    for (const p of c.points) {
      placed.push({ ...p, x, set: c.set });
      x++;
    }
    x += SET_ROOM;
  }
  const width = Math.max(1, x - SET_ROOM - 1);
  const px = (at: number) => (100 * at) / width;
  const py = (gap: number) => (100 * (top - gap)) / (top + bottom);
  const level = py(0);
  const paths = chapters.map((c) => {
    const of = placed.filter((p) => p.set === c.set);
    const start = (of[0]?.x ?? 1) - 1;
    const line = [`${px(start)},${level}`, ...of.map((p) => `${px(p.x)},${py(p.gap)}`)];
    return { set: c.set, start, end: of[of.length - 1]?.x ?? start, line: line.join(' ') };
  });
  const byRally = new Map(placed.map((p) => [p.rally, p]));
  // Each timeout between the points around it.
  const pauses = chapters.flatMap((c, k) =>
    c.timeouts.map((o) => {
      const before = placed.filter((p) => p.set === c.set && p.rally <= o.after).at(-1);
      return { ...o, set: c.set, x: (before?.x ?? paths[k].start) + 0.5 };
    }),
  );
  const playAt = (rally: number) => {
    const k = rallies.findIndex((r) => r.i === rally);
    play((tr) => (set === null ? tr('rallies') : tr('set', { n: set })), rallyClips(rallies, match.duration), k);
  };
  const score = (rally: number) => allRallies[rally]?.score?.join('-') ?? '';
  const shown = byRally.get(current);

  // A mark at the end of its moment, away from the line, those too close moved clear of each other.
  const marks: { moment: Moment; n: number; left: number; y: number }[] = [];
  moments.forEach((moment, k) => {
    const at = byRally.get(moment.rallies[moment.rallies.length - 1]);
    if (at) {
      const left = px(at.x);
      const taken = marks.filter((m) => Math.abs(m.left - left) < (phone ? PHONE_MARK_ROOM : MARK_ROOM) * 100).map((m) => m.y);
      marks.push({ moment, n: k + 1, left, y: markY((py(at.gap) * height) / 100, at.gap >= 0 ? -1 : 1, taken, height, MARK_OFF, MARK_STEP) });
    }
  });

  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 text-xs text-muted-foreground tabular-nums">
      <div aria-hidden className="col-start-2 relative mx-3 h-4">
        {named &&
          paths.map((p) => (
            <span key={p.set} className="absolute font-semibold whitespace-nowrap text-foreground" style={{ left: `${px(p.start)}%` }}>
              {t('set', { n: p.set })}
            </span>
          ))}
      </div>
      <div aria-hidden className="relative w-9" style={{ height }}>
        {[top, 0, -bottom].map((gap) => (
          <span key={gap} className="absolute right-0 -translate-y-1/2" style={{ top: `${py(gap)}%` }}>
            {gap === 0 ? t('story.tied') : `+${Math.abs(gap)}`}
          </span>
        ))}
      </div>
      <div className="relative mx-3" style={{ height }}>
        <svg aria-hidden viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
          <defs>
            <clipPath id={`${clip}-1`}>
              <rect x="-1" y="-1" width="102" height={level + 1} />
            </clipPath>
            <clipPath id={`${clip}-2`}>
              <rect x="-1" y={level} width="102" height={101 - level} />
            </clipPath>
          </defs>
          {paths.map((p) => (
            <Fragment key={p.set}>
              {([1, 2] as const).map((g) => (
                <g key={g} clipPath={`url(#${clip}-${g})`}>
                  <polygon points={`${p.line} ${px(p.end)},${level}`} fill={teamColor(g)} fillOpacity={0.7} />
                  {/* A jersey the colour of the card shows through its team's ring, transparent otherwise. */}
                  <polygon points={`${p.line} ${px(p.end)},${level}`} fill={teamRing(g)} fillOpacity={0.35} />
                </g>
              ))}
              <line x1={px(p.start)} x2={px(p.end)} y1={level} y2={level} stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
              <polyline points={p.line} fill="none" stroke="var(--foreground)" strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            </Fragment>
          ))}
        </svg>
        {shown && <div aria-hidden className="pointer-events-none absolute inset-y-0 w-px bg-foreground" style={{ left: `${px(shown.x)}%` }} />}
        {placed.map((p) => {
          const label = `${t('story.point', { n: p.rally + 1, score: score(p.rally) })} · ${t('watchRally')}`;
          return (
            <Tooltip key={p.rally}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={label}
                  onClick={() => playAt(p.rally)}
                  className="absolute inset-y-0 -translate-x-1/2 cursor-pointer rounded-sm outline-none hover:bg-foreground/10 focus-visible:ring-3 focus-visible:ring-ring/60"
                  style={{ left: `${px(p.x)}%`, width: `max(8px, ${100 / width}%)` }}
                />
              </TooltipTrigger>
              <TooltipContent>{t('story.point', { n: p.rally + 1, score: score(p.rally) })}</TooltipContent>
            </Tooltip>
          );
        })}
        {pauses.map((o) => {
          const label = `${timeoutLabel(t, o)} · ${o.score.join('-')}`;
          return (
            <Tip key={`${o.set}:${o.after}:${o.x}`} label={label}>
              <button
                type="button"
                aria-label={label}
                disabled={!o.next.length}
                onClick={() =>
                  play(
                    (tr) => `${timeoutLabel(tr, o)} · ${o.score.join('-')}`,
                    rallyClips(
                      allRallies.filter((r) => o.next.includes(r.i)),
                      match.duration,
                    ),
                  )
                }
                className="absolute inset-y-0 w-2 -translate-x-1/2 cursor-pointer pointer-coarse:after:absolute pointer-coarse:after:inset-y-0 pointer-coarse:after:-inset-x-1.5 pointer-coarse:after:content-[''] rounded-sm outline-none hover:bg-foreground/10 focus-visible:ring-3 focus-visible:ring-ring/60"
                style={{ left: `${px(o.x)}%` }}
              >
                <span aria-hidden className="absolute inset-y-0 left-1/2 border-l-2 border-dashed border-foreground/60" />
                {o.team && (
                  <span aria-hidden className="absolute -top-2 left-1/2 -translate-x-1/2">
                    <Swatch color={teamColor(o.team)} ring={teamRing(o.team)} />
                  </span>
                )}
              </button>
            </Tip>
          );
        })}
        {marks.map(({ moment, n, left, y }) => (
          <Tooltip key={n}>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`${n} · ${momentText(t, moment, f.secs)}`}
                onClick={() =>
                  play(
                    (tr) => momentText(tr, moment, f.secs),
                    rallyClips(
                      allRallies.filter((r) => moment.rallies.includes(r.i)),
                      match.duration,
                    ),
                  )
                }
                className="tap absolute inline-grid size-6 -translate-x-1/2 -translate-y-1/2 cursor-pointer place-items-center rounded-full bg-foreground text-xs font-semibold text-background ring-2 ring-card outline-none focus-visible:ring-3 focus-visible:ring-ring/60"
                style={{ left: `${left}%`, top: y }}
              >
                {n}
              </button>
            </TooltipTrigger>
            <TooltipContent>{momentText(t, moment, f.secs)}</TooltipContent>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}
