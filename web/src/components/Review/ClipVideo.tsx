import { useEffect, useRef, useState, type PointerEvent, type ReactNode, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { Volume2, VolumeX, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SkipIcon } from '@/components/SkipIcon';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { match, rallies, teamColor, teamRing, type Group } from '@/lib/match';
import type { Clip } from '@/lib/review';
import { boxAt, panView, viewAt, wheelZoom, zoomView, type View } from '@/components/Review/helpers/box';

/** Half a second of context around a clip, played in a loop, unless the clip says otherwise. */
const AROUND = 0.5;
/** Playback speeds offered, to catch a short moment; the one picked carries over to the next clip. */
const SPEEDS = [1, 0.5, 0.25];
let picked = 1;
/** In free play, the bar spans this long before and after where it was anchored, re-anchored once the video leaves it. */
const FREE_SPAN = [20, 70];
/** In free play, the step of the buttons going back and forth. */
const FREE_STEP_S = 10;
/** A press on the video held this long plays it at HOLD_RATE until released. */
const HOLD_MS = 250;
const HOLD_RATE = 0.25;
/** Each zoom button's step, towards the middle of the view. */
const ZOOM_STEP = 1.5;
/** A press moving this far drags the zoomed view: no click, no slowing down. */
const DRAG_PX = 4;
/** Whether the match's sound is off, kept in this browser. */
const MUTED_KEY = 'review.muted';
/** Where the caption stands (its top centre, fractions of the video), as the user dragged it, kept
 * in this browser; centred above the court until then. */
const CAPTION_KEY = 'review.captionAt';
const CAPTION_AT = { x: 0.5, y: 0.08 };

function savedCaption(): { x: number; y: number } {
  try {
    const at = JSON.parse(localStorage.getItem(CAPTION_KEY) ?? 'null');
    return typeof at?.x === 'number' && typeof at?.y === 'number' ? at : CAPTION_AT;
  } catch {
    return CAPTION_AT;
  }
}

function savedMuted(): boolean {
  try {
    return localStorage.getItem(MUTED_KEY) === '1';
  } catch {
    return false;
  }
}

/** The video looping over `clip`, the player outlined in yellow, which stands out from both jerseys and the floor, and zoomed on them unless the whole frame is asked for;
 * its progress bar moves it (drag, click or arrows); with `showTime` the match time under it, `marks` (times) drawn on that bar, `onTime` told where it stands.
 * `free`: the match plays on from the clip with its sound, no loop; the bar spans FREE_SPAN around where the video stands, the rallies in yellow. `caption`: over the video where the user dragged it (CAPTION_KEY), in its team's colour.
 * `extra`: at the right end of the speeds' line. */
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
  caption,
  autoPlay = true,
  extra,
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
  caption?: { team: Group; text: string } | null;
  autoPlay?: boolean;
  extra?: ReactNode;
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
  // A press held on the video: slowed down while it lasts, no play or pause on its release.
  const held = useRef(false);
  const holdTimer = useRef(0);
  const wasPaused = useRef(false);
  const swallowClick = useRef(false);
  // The part of the frame a pinch zoomed on, null for the automatic view.
  const [pinched, setPinched] = useState<View | null>(null);
  const [muted, setMuted] = useState(() => !free || savedMuted());
  const grab = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const frame = useRef<HTMLDivElement>(null);
  const [captionAt, setCaptionAt] = useState(savedCaption);
  const captionDrag = useRef<{ x: number; y: number; from: { x: number; y: number } } | null>(null);
  const dragCaption = (event: PointerEvent) => {
    const drag = captionDrag.current;
    const r = frame.current?.getBoundingClientRect();
    if (drag && r?.width) {
      const clamp = (v: number) => Math.min(0.95, Math.max(0.02, v));
      setCaptionAt({ x: clamp(drag.from.x + (event.clientX - drag.x) / r.width), y: clamp(drag.from.y + (event.clientY - drag.y) / r.height) });
    }
  };
  const dropCaption = () => {
    if (captionDrag.current) {
      captionDrag.current = null;
      try {
        localStorage.setItem(CAPTION_KEY, JSON.stringify(captionAt));
      } catch {
        // Kept for this page only.
      }
    }
  };
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
    if (autoPlay) {
      void v.play().catch(() => {});
    }
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
      const rate = held.current ? HOLD_RATE : clip.slow && v.currentTime >= clip.start && v.currentTime <= clip.end ? Math.min(clip.slow, picked) : picked;
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

  // A moment asked for (`n` counts the asks, so the same moment can be asked again): played from
  // there (`play`), shown paused (false) or as the video was (unset).
  useEffect(() => {
    const v = video.current;
    if (v && seek) {
      v.currentTime = seek.time;
      if (seek.play !== undefined) {
        void (seek.play ? v.play().catch(() => {}) : v.pause());
      }
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
  const view = pinched ?? (zoom ? viewAt(clip, time, width, height) : { x: 0, y: 0, w: width, h: height });
  const shown = useRef(view);
  shown.current = view;
  // A trackpad pinch (sent as Ctrl + wheel; Safari's gesture events), or ⌘ or Ctrl + the wheel, zooms where the pointer is, two
  // fingers then move the zoomed view; the page neither zooms nor scrolls meanwhile.
  useEffect(() => {
    const el = frame.current;
    if (!el) {
      return;
    }
    const at = (x: number, y: number) => {
      const r = el.getBoundingClientRect();
      return [(x - r.left) / r.width, (y - r.top) / r.height, r] as const;
    };
    const wheel = (event: WheelEvent) => {
      const [fx, fy, r] = at(event.clientX, event.clientY);
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        setPinched(zoomView(shown.current, fx, fy, wheelZoom(event.deltaY, event.deltaMode), width, height));
      } else if (shown.current.w < width) {
        event.preventDefault();
        const v = shown.current;
        setPinched(panView(v, (event.deltaX * v.w) / r.width, (event.deltaY * v.h) / r.height, width, height));
      }
    };
    let last = 1;
    const gesture = (event: Event & { scale?: number; clientX?: number; clientY?: number }) => {
      event.preventDefault();
      const [fx, fy] = at(event.clientX ?? 0, event.clientY ?? 0);
      const scale = event.scale ?? 1;
      setPinched(zoomView(shown.current, fx, fy, scale / last, width, height));
      last = scale;
    };
    const start = (event: Event) => {
      event.preventDefault();
      last = 1;
    };
    el.addEventListener('wheel', wheel, { passive: false });
    el.addEventListener('gesturestart', start);
    el.addEventListener('gesturechange', gesture);
    return () => {
      el.removeEventListener('wheel', wheel);
      el.removeEventListener('gesturestart', start);
      el.removeEventListener('gesturechange', gesture);
    };
  }, [width, height]);
  // The native controls would zoom with the video: a click plays or pauses it instead.
  const own = zoom || pinched !== null;
  const toggle = () => {
    const v = video.current;
    if (swallowClick.current) {
      swallowClick.current = false;
      return;
    }
    if (v) {
      void (v.paused ? v.play().catch(() => {}) : v.pause());
    }
  };
  const press = (event: PointerEvent) => {
    grab.current = { x: event.clientX, y: event.clientY, moved: false };
    if (shown.current.w < width) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    holdTimer.current = window.setTimeout(() => {
      const v = video.current;
      if (v) {
        held.current = true;
        wasPaused.current = v.paused;
        void v.play().catch(() => {});
      }
    }, HOLD_MS);
  };
  const endHold = () => {
    window.clearTimeout(holdTimer.current);
    if (held.current) {
      held.current = false;
      swallowClick.current = true;
      if (wasPaused.current) {
        video.current?.pause();
      }
    }
  };
  const release = () => {
    grab.current = null;
    endHold();
  };
  const drag = (event: PointerEvent) => {
    const from = grab.current;
    const r = frame.current?.getBoundingClientRect();
    const v = shown.current;
    if (!from || !r?.width || v.w >= width) {
      return;
    }
    const dx = event.clientX - from.x;
    const dy = event.clientY - from.y;
    if (!from.moved && Math.hypot(dx, dy) < DRAG_PX) {
      return;
    }
    if (!from.moved) {
      endHold();
      from.moved = true;
      swallowClick.current = true;
    }
    from.x = event.clientX;
    from.y = event.clientY;
    setPinched(panView(v, (-dx * v.w) / r.width, (-dy * v.h) / r.height, width, height));
  };
  const zoomBy = (factor: number) => setPinched(zoomView(view, 0.5, 0.5, factor, width, height));
  const toggleMuted = () => {
    setMuted(!muted);
    try {
      localStorage.setItem(MUTED_KEY, muted ? '0' : '1');
    } catch {
      // Kept for this page only.
    }
  };
  return (
    <div className="grid gap-2">
      <div ref={frame} className="relative aspect-video overflow-hidden rounded-lg bg-black">
        <div className="absolute inset-0 origin-top-left" style={{ transform: `scale(${width / view.w}) translate(${(-100 * view.x) / width}%, ${(-100 * view.y) / height}%)` }}>
          <video
            ref={video}
            src={match.video ?? undefined}
            muted={muted}
            playsInline
            controls={!own}
            onClick={own ? toggle : undefined}
            onPointerDown={press}
            onPointerMove={drag}
            onPointerUp={release}
            onPointerCancel={release}
            onPointerLeave={release}
            aria-label={t('review.video')}
            className={cn('block size-full select-none', view.w < width && 'cursor-grab touch-none')}
          />
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
        {caption && (
          <span
            title={t('review.captionMove')}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              captionDrag.current = { x: event.clientX, y: event.clientY, from: captionAt };
            }}
            onPointerMove={dragCaption}
            onPointerUp={dropCaption}
            onPointerCancel={dropCaption}
            onDoubleClick={() => {
              setCaptionAt(CAPTION_AT);
              try {
                localStorage.removeItem(CAPTION_KEY);
              } catch {
                // Kept for this page only.
              }
            }}
            style={{ left: `${captionAt.x * 100}%`, top: `${captionAt.y * 100}%` }}
            className="absolute z-10 flex max-w-[calc(100%-1rem)] -translate-x-1/2 cursor-grab touch-none items-center gap-2 rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm select-none active:cursor-grabbing"
          >
            <Swatch color={teamColor(caption.team)} ring={teamRing(caption.team)} />
            <span className="truncate">{caption.text}</span>
          </span>
        )}
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
                size="icon-sm"
                className="relative bg-card"
                title={t(step < 0 ? 'review.back' : 'review.forward', { s: FREE_STEP_S })}
                aria-label={t(step < 0 ? 'review.back' : 'review.forward', { s: FREE_STEP_S })}
                onClick={() => moveTo(time + step)}
              >
                <SkipIcon seconds={step} />
              </Button>
            ))}
          </div>
        )}
        {free && (
          <div className="flex gap-1">
            <Button variant="outline" size="icon-sm" className="bg-card" title={t('review.pinchNote')} aria-label={t('review.zoomMore')} onClick={() => zoomBy(ZOOM_STEP)}>
              <ZoomIn aria-hidden />
            </Button>
            <Button variant="outline" size="icon-sm" className="bg-card" title={t('review.pinchNote')} aria-label={t('review.zoomLess')} disabled={!pinched} onClick={() => zoomBy(1 / ZOOM_STEP)}>
              <ZoomOut aria-hidden />
            </Button>
          </div>
        )}
        {/* No outline, nothing to zoom on. */}
        {clip.boxes.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            className="bg-card"
            onClick={() => {
              setPinched(null);
              setZoom((z) => !z);
            }}
          >
            {zoom ? <ZoomOut aria-hidden /> : <ZoomIn aria-hidden />}
            {t(zoom ? 'review.zoomOut' : 'review.zoomIn')}
          </Button>
        )}
        {free && (
          <Button
            variant="outline"
            size="icon-sm"
            className="bg-card"
            title={t(muted ? 'review.soundOn' : 'review.soundOff')}
            aria-label={t(muted ? 'review.soundOn' : 'review.soundOff')}
            onClick={toggleMuted}
          >
            {muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
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
        {extra && <div className="ml-auto">{extra}</div>}
      </div>
    </div>
  );
}
