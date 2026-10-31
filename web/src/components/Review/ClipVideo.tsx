import { useEffect, useRef, useState, type PointerEvent, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { clock } from '@/lib/format';
import { match, rallies } from '@/lib/match';
import type { Clip } from '@/lib/review';
import { boxAt, viewAt } from '@/components/Review/helpers/box';

/** Half a second of context around a clip, played in a loop, unless the clip says otherwise. */
const AROUND = 0.5;
/** Playback speeds offered, to catch a short moment; the one picked carries over to the next clip. */
const SPEEDS = [1, 0.5, 0.25];
let picked = 1;
/** In free play, the bar spans this long before and after where it was anchored, re-anchored once the video leaves it. */
const FREE_SPAN = [20, 70];
/** In free play, the step of the buttons going back and forth. */
const FREE_STEP_S = 10;

/** The video looping over `clip`, the player outlined in yellow, which stands out from both jerseys and the floor, and zoomed on them unless the whole frame is asked for;
 * its progress bar moves it (drag, click or arrows); with `showTime` the match time under it, `marks` (times) drawn on that bar, `onTime` told where it stands.
 * `free`: the match plays on from the clip, no loop; the bar spans FREE_SPAN around where the video stands, the rallies in yellow. */
export function ClipVideo({
  clip,
  width,
  height,
  timeRef,
  seek,
  marks = [],
  showTime = false,
  free = false,
  onTime,
}: {
  clip: Clip;
  width: number;
  height: number;
  timeRef?: RefObject<number>;
  seek?: { time: number; n: number; play?: boolean };
  marks?: number[];
  showTime?: boolean;
  free?: boolean;
  onTime?: (time: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  const [time, setTime] = useState(clip.start);
  const [zoom, setZoom] = useState(true);
  const [speed, setSpeed] = useState(picked);
  const [anchor, setAnchor] = useState(clip.start);
  const anchored = useRef(clip.start);
  const dragging = useRef(false);
  // Loading the video resets its rate to the default one: both are set.
  useEffect(() => {
    if (video.current) {
      video.current.defaultPlaybackRate = speed;
      video.current.playbackRate = speed;
    }
  }, [speed]);

  const around = clip.around ?? AROUND;
  useEffect(() => {
    const v = video.current;
    if (!v) {
      return;
    }
    v.currentTime = Math.max(0, clip.start - around);
    void v.play().catch(() => {});
    let frame = 0;
    const tick = () => {
      if (!free && v.currentTime > clip.end + around) {
        v.currentTime = Math.max(0, clip.start - around);
      }
      const a = anchored.current;
      if (free && !dragging.current && (v.currentTime < a - FREE_SPAN[0] || v.currentTime > a + FREE_SPAN[1] - 2)) {
        anchored.current = v.currentTime;
        setAnchor(v.currentTime);
      }
      const rate = clip.slow && v.currentTime >= clip.start && v.currentTime <= clip.end ? Math.min(clip.slow, picked) : picked;
      if (v.playbackRate !== rate) {
        v.playbackRate = rate;
      }
      setTime(v.currentTime);
      if (timeRef) {
        timeRef.current = v.currentTime;
      }
      onTime?.(v.currentTime);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [clip]);

  // A moment asked for (`n` counts the asks, so the same moment can be asked again): shown paused,
  // or played from there (`play`).
  useEffect(() => {
    const v = video.current;
    if (v && seek) {
      v.currentTime = seek.time;
      void (seek.play ? v.play().catch(() => {}) : v.pause());
    }
  }, [seek]);

  const box = boxAt(clip, time);
  // Where the bar stands, and the outlined parts of it: the clip, or in free play the rallies there.
  const from = free ? Math.max(0, anchor - FREE_SPAN[0]) : Math.max(0, clip.start - around);
  const to = free ? Math.min(match.duration, anchor + FREE_SPAN[1]) : clip.end + around;
  const bands = free ? rallies.filter((r) => r.end > from && r.start < to).map((r) => [r.start, r.end]) : [[clip.start, clip.end]];
  const share = (at: number) => `${(100 * (Math.min(to, Math.max(from, at)) - from)) / (to - from)}%`;
  const moveTo = (at: number) => {
    const v = video.current;
    if (v) {
      v.currentTime = free ? Math.min(match.duration, Math.max(0, at)) : Math.min(to, Math.max(from, at));
      setTime(v.currentTime);
    }
  };
  const moveToPointer = (event: PointerEvent) => {
    const place = bar.current?.getBoundingClientRect();
    if (place?.width) {
      moveTo(from + ((event.clientX - place.left) / place.width) * (to - from));
    }
  };
  const keys: Record<string, (step: number) => number> = { ArrowLeft: (step) => time - step, ArrowRight: (step) => time + step, Home: () => from, End: () => to };
  const view = zoom ? viewAt(clip, time, width, height) : { x: 0, y: 0, w: width, h: height };
  // The native controls would zoom with the video: a click plays or pauses it instead.
  const toggle = () => {
    const v = video.current;
    if (v) {
      void (v.paused ? v.play().catch(() => {}) : v.pause());
    }
  };
  return (
    <div className="grid gap-2">
      <div className="relative aspect-video overflow-hidden rounded-lg bg-black">
        <div className="absolute inset-0 origin-top-left" style={{ transform: `scale(${width / view.w}) translate(${(-100 * view.x) / width}%, ${(-100 * view.y) / height}%)` }}>
          <video ref={video} src={match.video ?? undefined} muted playsInline controls={!zoom} onClick={zoom ? toggle : undefined} aria-label={t('review.video')} className="block size-full" />
          <svg viewBox={`0 0 ${width} ${height}`} aria-hidden className="pointer-events-none absolute inset-0 size-full">
            {box && (
              <rect
                x={box[0] - 6}
                y={box[1] - 6}
                width={box[2] - box[0] + 12}
                height={box[3] - box[1] + 12}
                rx={6}
                fill="none"
                stroke="#ffd400"
                strokeWidth={3}
                vectorEffect="non-scaling-stroke"
                className="drop-shadow-[0_0_3px_rgba(0,0,0,0.9)]"
              />
            )}
          </svg>
        </div>
      </div>
      <div
        ref={bar}
        role="slider"
        tabIndex={0}
        aria-label={t('review.position')}
        aria-valuemin={Math.round(from)}
        aria-valuemax={Math.round(to)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={clock(time)}
        className="group flex h-5 cursor-pointer touch-none items-center rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          dragging.current = true;
          moveToPointer(event);
        }}
        onLostPointerCapture={() => (dragging.current = false)}
        onPointerMove={(event) => event.currentTarget.hasPointerCapture(event.pointerId) && moveToPointer(event)}
        onKeyDown={(event) => {
          const next = keys[event.key];
          if (next) {
            event.preventDefault();
            moveTo(next(event.shiftKey ? 5 : 1));
          }
        }}
      >
        <div className="relative h-1.5 w-full rounded-full bg-muted">
          {bands.map(([a, b]) => (
            <div key={a} className="absolute inset-y-0 rounded-full bg-[#ffd400]" style={{ left: share(a), right: `calc(100% - ${share(b)})` }} />
          ))}
          {marks.map((m) => (
            <div key={m} className="absolute -inset-y-1.5 w-1 -translate-x-1/2 rounded-full bg-primary" style={{ left: share(m) }} />
          ))}
          <div className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground shadow-sm transition-transform group-hover:scale-125" style={{ left: share(time) }} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {showTime && <span className="min-w-12 text-sm font-medium tabular-nums">{clock(time)}</span>}
        {free && (
          <div className="flex gap-1">
            {[-FREE_STEP_S, FREE_STEP_S].map((step) => (
              <Button
                key={step}
                variant="outline"
                size="sm"
                className="bg-card tabular-nums"
                aria-label={t(step < 0 ? 'review.back' : 'review.forward', { s: FREE_STEP_S })}
                onClick={() => moveTo(time + step)}
              >
                {step < 0 ? `−${FREE_STEP_S} s` : `+${FREE_STEP_S} s`}
              </Button>
            ))}
          </div>
        )}
        {/* No outline, nothing to zoom on. */}
        {clip.boxes.length > 0 && (
          <Button variant="outline" size="sm" className="bg-card" onClick={() => setZoom((z) => !z)}>
            {zoom ? <ZoomOut aria-hidden /> : <ZoomIn aria-hidden />}
            {t(zoom ? 'review.zoomOut' : 'review.zoomIn')}
          </Button>
        )}
        <div role="group" aria-label={t('review.speed')} className="flex gap-1">
          {SPEEDS.map((s) => (
            <Button
              key={s}
              variant={s === speed ? 'default' : 'outline'}
              size="sm"
              className={s === speed ? undefined : 'bg-card'}
              aria-pressed={s === speed}
              onClick={() => {
                picked = s;
                setSpeed(s);
              }}
            >
              {`${new Intl.NumberFormat(i18n.language).format(s)}×`}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}
