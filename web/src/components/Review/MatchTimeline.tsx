import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, Maximize2, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { clock } from '@/lib/format';
import { contacts, groupName, match, playerLabel, rallies, teamColor, teamEdge, type Group } from '@/lib/match';
import { isTouch, labelled } from '@/helpers/contacts';
import type { ReportChanges, Timeout } from '@/lib/review';
import { tickStep, zoomed } from '@/components/Review/helpers/timeline';

/** The closest zoom, in pixels a second: a touch a few pixels from the next. */
const MAX_SCALE = 40;
/** Each zoom button's step. */
const STEP = 2;
/** After the user scrolls the bar, it stops following the video this long. */
const HOLD_MS = 3000;
const HEIGHT = 64;

/** The whole match on one bar under the video: each rally a band, its winner's colour along its
 * bottom, orange with a warning, else green once checked, the sets parted; buttons go to the rally
 * to check (a warning, or not checked) before or after the video; each touch a tick in its team's colour (grey once removed), the viewers'
 * reports as red flags, the warnings as orange ones, the corrections saved and not applied as dots, the timeouts as grey dashed bands. A click moves the video there.
 * It zooms (buttons, or ctrl/⌘ and the wheel or a pinch, around the pointer) and scrolls sideways,
 * following the video unless just scrolled. */
export function MatchTimeline({
  now,
  saved,
  reports,
  warnings,
  green,
  warned,
  comments,
  timeouts,
  onSeek,
}: {
  now: number;
  saved: Partial<ReportChanges>;
  reports: { time: number }[];
  warnings: { time: number }[];
  /** The rallies checked with no report open since, by their key: green. */
  green: Set<number>;
  /** The rallies with a warning, by their key: orange. */
  warned: Set<number>;
  /** The owner's notes on the rallies, by their key: a mark above each. */
  comments: Record<number, string>;
  /** Each a grey dashed band. */
  timeouts: Timeout[];
  onSeek: (time: number) => void;
}) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el) {
      return;
    }
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  const fit = width ? width / match.duration : 0;
  const [chosen, setChosen] = useState<number | null>(null);
  const scale = Math.max(fit, chosen ?? fit);
  // The moment to keep under the same x after a zoom.
  const anchor = useRef<{ time: number; x: number } | null>(null);
  const zoom = (factor: number, x?: number) => {
    const el = box.current;
    if (!el || !fit) {
      return;
    }
    const at = x ?? Math.min(el.clientWidth, Math.max(0, now * scale - el.scrollLeft));
    anchor.current = { time: (el.scrollLeft + at) / scale, x: at };
    setChosen(zoomed(scale, factor, fit, MAX_SCALE));
  };
  useLayoutEffect(() => {
    const el = box.current;
    if (el && anchor.current) {
      el.scrollLeft = anchor.current.time * scale - anchor.current.x;
      anchor.current = null;
    }
  }, [scale]);
  // ctrl/⌘ and the wheel (a trackpad's pinch sends it so) zoom; the page must not.
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  useEffect(() => {
    const el = box.current;
    if (!el) {
      return;
    }
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        zoomRef.current(Math.exp(-event.deltaY * 0.01), event.clientX - el.getBoundingClientRect().left);
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);
  // Following the video: back in view a third from the left when it leaves it.
  const scrolled = useRef(0);
  useEffect(() => {
    const el = box.current;
    if (!el || Date.now() - scrolled.current < HOLD_MS) {
      return;
    }
    const x = now * scale;
    if (x < el.scrollLeft || x > el.scrollLeft + el.clientWidth - 16) {
      el.scrollLeft = x - el.clientWidth / 3;
    }
  }, [now, scale]);

  const removed = new Set((saved.touches ?? []).filter((c) => c.player === 'none').map((c) => c.frame));
  const touches = [
    ...contacts
      .filter((c) => isTouch(c) || c.type === 'fault')
      .map((c) => ({ key: `c${c.i}`, time: c.t, team: c.g, removed: removed.has(c.f ?? Math.round(c.t * match.fps)), label: touchLabel(t, c.type, labelled(c), c.g, c.person) })),
    ...(saved.added ?? []).map((a) => ({ key: `a${a.frame}`, time: a.frame / match.fps, team: a.team, removed: false, label: touchLabel(t, a.type, a.result, a.team, null) })),
  ];
  const marks = [...(saved.touches ?? []), ...(saved.added ?? [])].map((c) => c.frame / match.fps);
  const step = tickStep(scale || 1);
  const total = Math.max(width, match.duration * scale);
  const sets = rallies.filter((r, k) => k === 0 || r.set !== rallies[k - 1].set);
  const toCheck = rallies.filter((r) => r.key === undefined || warned.has(r.key) || !green.has(r.key));
  const previous = toCheck.findLast((r) => r.end < now);
  const next = toCheck.find((r) => r.start > now + 0.5);
  const seekTo = (event: MouseEvent<SVGSVGElement>) => {
    const left = event.currentTarget.getBoundingClientRect().left;
    onSeek(Math.min(match.duration, Math.max(0, (event.clientX - left) / scale)));
  };

  return (
    <div className="grid gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t('review.timeline')}</span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="size-8 bg-card"
            title={t('review.previousToCheck')}
            aria-label={t('review.previousToCheck')}
            disabled={!previous}
            onClick={() => previous && onSeek(previous.start)}
          >
            <ChevronLeft aria-hidden />
          </Button>
          <span className="text-sm tabular-nums">{t('review.toCheck', { count: toCheck.length })}</span>
          <Button
            variant="outline"
            size="icon"
            className="size-8 bg-card"
            title={t('review.nextToCheck')}
            aria-label={t('review.nextToCheck')}
            disabled={!next}
            onClick={() => next && onSeek(next.start)}
          >
            <ChevronRight aria-hidden />
          </Button>
        </div>
        <div className="ml-auto flex gap-1">
          <Button
            variant="outline"
            size="icon"
            className="size-8 bg-card"
            title={t('review.zoomOutTimeline')}
            aria-label={t('review.zoomOutTimeline')}
            disabled={scale <= fit}
            onClick={() => zoom(1 / STEP)}
          >
            <ZoomOut aria-hidden />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-8 bg-card"
            title={t('review.zoomInTimeline')}
            aria-label={t('review.zoomInTimeline')}
            disabled={scale >= MAX_SCALE}
            onClick={() => zoom(STEP)}
          >
            <ZoomIn aria-hidden />
          </Button>
          <Button variant="outline" size="sm" className="bg-card" disabled={scale <= fit} onClick={() => setChosen(null)}>
            <Maximize2 aria-hidden />
            {t('review.wholeMatch')}
          </Button>
        </div>
      </div>
      <div ref={box} className="overflow-x-auto overscroll-x-contain rounded-md border bg-card" onScroll={() => (scrolled.current = Date.now())} onPointerDown={() => (scrolled.current = Date.now())}>
        {width > 0 && (
          <svg width={total} height={HEIGHT} className="block cursor-pointer select-none" onClick={seekTo} aria-label={t('review.timeline')}>
            {timeouts.map((o) => (
              <rect
                key={o.start}
                x={(o.start / match.fps) * scale}
                y={14}
                width={Math.max(3, ((o.end - o.start) / match.fps) * scale)}
                height={26}
                fill="var(--muted-foreground)"
                fillOpacity={0.2}
                stroke="var(--muted-foreground)"
                strokeDasharray="3 2"
              >
                <title>{`${t('review.timeout')} · ${clock(o.start / match.fps)}${o.team ? ` · ${groupName(t, o.team)}` : ''}`}</title>
              </rect>
            ))}
            {rallies.map((r) => (
              <g key={r.i}>
                <rect
                  x={r.start * scale}
                  y={14}
                  width={Math.max(3, (r.end - r.start) * scale)}
                  height={26}
                  rx={Math.min(3, ((r.end - r.start) * scale) / 2)}
                  className={
                    r.key !== undefined && warned.has(r.key)
                      ? 'fill-amber-400 dark:fill-amber-600'
                      : r.key !== undefined && green.has(r.key)
                        ? 'fill-emerald-300 dark:fill-emerald-800'
                        : 'fill-muted-foreground/25'
                  }
                >
                  <title>{`${t('review.reportRally', { n: r.i + 1, from: clock(r.start), to: clock(r.end) })}${r.winner ? ` · ${t('review.wonBy', { team: groupName(t, r.winner) })}` : r.redo ? ` · ${t('review.reportRedo')}` : ''}${r.wrongCall ? ` · ${t('review.reportWrongCall')}` : ''}`}</title>
                </rect>
                {r.winner && <rect x={r.start * scale} y={36} width={Math.max(1, (r.end - r.start) * scale)} height={4} fill={teamColor(r.winner)} stroke={teamEdge(r.winner)} strokeWidth={0.75} />}
                {/* Its number, where the band has room for it. */}
                {(r.end - r.start) * scale >= 22 && (
                  <text x={r.start * scale + 3} y={24} className="pointer-events-none fill-muted-foreground text-[9px] tabular-nums">
                    {r.i + 1}
                  </text>
                )}
              </g>
            ))}
            {sets.map((r) => (
              <g key={`s${r.set}`}>
                {r.i > 0 && <line x1={r.start * scale - 4} x2={r.start * scale - 4} y1={0} y2={44} className="stroke-foreground" strokeDasharray="3 3" />}
                <text x={r.start * scale + 2} y={10} className="fill-muted-foreground text-[10px]">
                  {t('set', { n: r.set })}
                </text>
              </g>
            ))}
            {touches.map((c) => (
              // Outlined: a white jersey's touch stands out from the bar.
              <rect
                key={c.key}
                x={c.time * scale - (scale > 4 ? 1.5 : 1)}
                y={26}
                width={scale > 4 ? 3 : 2}
                height={9}
                fill={c.removed ? 'none' : teamColor(c.team)}
                stroke={c.removed ? 'var(--muted-foreground)' : teamEdge(c.team)}
                strokeWidth={0.75}
                strokeDasharray={c.removed ? '2 1' : undefined}
              >
                <title>{`${clock(c.time)} · ${c.label}`}</title>
              </rect>
            ))}
            {marks.map((time, k) => (
              <circle key={k} cx={time * scale} cy={7} r={2.5} className="fill-muted-foreground" />
            ))}
            {rallies.flatMap((r) =>
              r.key !== undefined && comments[r.key]
                ? [
                    <path key={`c${r.i}`} d={`M ${((r.start + r.end) / 2) * scale} 3 l 4 4 l -4 4 l -4 -4 z`} className="fill-sky-500">
                      <title>{comments[r.key]}</title>
                    </path>,
                  ]
                : [],
            )}
            {warnings.map((w, k) => (
              <Flag key={k} x={w.time * scale} className="text-orange-500 dark:text-orange-400" />
            ))}
            {reports.map((r, k) => (
              <Flag key={k} x={r.time * scale} className="text-red-600 dark:text-red-500" />
            ))}
            {Array.from({ length: Math.floor(match.duration / step) + 1 }, (_, k) => k * step).map((time) => (
              <g key={time}>
                <line x1={time * scale} x2={time * scale} y1={44} y2={48} className="stroke-muted-foreground" />
                <text x={time * scale + 2} y={58} className="fill-muted-foreground text-[10px] tabular-nums">
                  {clock(time)}
                </text>
              </g>
            ))}
            <line x1={now * scale} x2={now * scale} y1={0} y2={HEIGHT} className="stroke-foreground" strokeWidth={2} />
          </svg>
        )}
      </div>
    </div>
  );
}

function Flag({ x, className }: { x: number; className: string }) {
  return (
    <g className={className}>
      <line x1={x} x2={x} y1={2} y2={40} stroke="currentColor" strokeWidth={1.5} />
      <path d={`M ${x} 2 l 7 3 l -7 3 z`} fill="currentColor" />
    </g>
  );
}

/** A touch in a tip: its action and how it ended, its team, its player when known. */
function touchLabel(t: ReturnType<typeof useTranslation>['t'], type: string, result: string, team: Group, person: number | null): string {
  return [t(`actions.${type}.${result}`, { defaultValue: t(`types.${type}`) }), groupName(t, team), playerLabel(t, person)].filter(Boolean).join(' · ');
}
