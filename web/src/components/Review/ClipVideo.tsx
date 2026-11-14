import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type ReactNode, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { Pause, Play, ScanSearch, Snail, Volume2, VolumeX, ZoomIn, ZoomOut } from 'lucide-react';
import { VideoError } from '@/components/VideoError';
import { VideoButton } from '@/components/VideoButton';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { match, rallies, teamColor, teamRing, type Group } from '@/lib/match';
import type { Clip } from '@/lib/review';
import { autoView, boxAt, exchangeAt, panView, viewAt, wheelZoom, zoomView, type View } from '@/components/Review/helpers/box';
import { coarse, frameTime, nearTouch, nudgeOf } from '@/components/Review/helpers/scrub';
import { Tip } from '@/components/Tip';

/** Half a second of context around a clip, played in a loop, unless the clip says otherwise. */
const AROUND = 0.5;
/** Playback speeds offered, to catch a short moment; the one picked carries over to the next clip. */
const SPEEDS = [1, 0.5, 0.25];
let picked = 1;
/** In free play, the bar spans this long before and after where it was anchored, re-anchored once the video leaves it. */
const FREE_SPAN = [20, 70];
/** In free play, the step of the left and right arrow keys. */
const ARROW_STEP_S = 1;
/** A press on the video held this long plays it at HOLD_RATE until released. */
const HOLD_MS = 250;
const HOLD_RATE = 0.25;
/** Each zoom button's step, towards the middle of the view. */
const ZOOM_STEP = 1.5;
/** A press moving this far drags the zoomed view: no click, no slowing down. */
const DRAG_PX = 4;
/** A press on the bar this close to its thumb grabs it where it stands. */
const THUMB_PX = 8;
/** Whether the match's sound is off, kept in this browser. */
const MUTED_KEY = 'review.muted';
/** Whether the automatic zoom is on, kept in this browser. */
const AUTO_KEY = 'review.autoZoom';
/** Whether the video slows down at each touch, kept in this browser; how slow. */
const SLOW_KEY = 'review.slowTouches';
const SLOW_RATE = 0.25;
/** The control bar's height under the video (its seek bar, gap, buttons and padding), to fit both in full screen. */
const BAR_REM = 4.25;
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

function savedFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

function saveFlag(key: string, on: boolean) {
  try {
    localStorage.setItem(key, on ? '1' : '0');
  } catch {
    // Kept for this page only.
  }
}

/** The video looping over `clip`, the player outlined in yellow, which stands out from both jerseys and the floor, and zoomed on them unless the whole frame is asked for;
 * its progress bar moves it (drag, click or arrows; where a pixel of it spans more than a frame, a small drag pauses it and moves it frame by frame); with `showTime` the match time under it, `marks` (times) drawn on that bar, `onTime` told where it stands.
 * `free`: the match plays on from the clip with its sound, no loop, the arrow keys moving it; the bar spans FREE_SPAN around where the video stands, the rallies in yellow. `caption`: over the video where the user dragged it (CAPTION_KEY), in its team's colour. Zooming by hand overrides the automatic zoom until the next rally.
 * `touches`: the ball's touches (times, sorted), which a button beside the speeds slows the video down at.
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
  touches,
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
  touches?: number[];
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
  // Where a drag on the bar goes frame by frame from (see helpers/scrub), null once it follows the pointer, until released; the frames it moved.
  const fine = useRef<{ x: number; frame: number; n: number } | null>(null);
  const [nudge, setNudge] = useState<number | null>(null);
  // A press held on the video: slowed down while it lasts, no play or pause on its release.
  const held = useRef(false);
  const holdTimer = useRef(0);
  const wasPaused = useRef(false);
  const [paused, setPaused] = useState(true);
  const swallowClick = useRef(false);
  // The part of the frame a pinch zoomed on, null for the automatic view.
  const [pinched, setPinched] = useState<View | null>(null);
  const [muted, setMuted] = useState(() => !free || savedFlag(MUTED_KEY));
  const views = free && match.views.length ? match.views : null;
  const [auto, setAuto] = useState(() => savedFlag(AUTO_KEY));
  const [slow, setSlow] = useState(() => savedFlag(SLOW_KEY));
  // Read by the playing loop.
  const slowAt = useRef<number[] | null>(null);
  slowAt.current = slow && touches ? touches : null;
  const zoomedByHand = useRef(false);
  zoomedByHand.current = pinched !== null && pinched.w < width;
  const following = useRef(false);
  following.current = views !== null && auto;
  const zoomedIn = useRef(-1);
  // Back at the whole frame by hand, the automatic zoom must not zoom in again.
  const zoomByHand = (next: View | null) => {
    zoomedIn.current = exchangeAt(rallies, video.current?.currentTime ?? 0);
    setPinched(next ?? (following.current ? { x: 0, y: 0, w: width, h: height } : null));
  };
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
      const slowed = clip.slow && v.currentTime >= clip.start && v.currentTime <= clip.end ? clip.slow : slowAt.current && nearTouch(slowAt.current, v.currentTime) ? SLOW_RATE : 1;
      const rate = held.current ? HOLD_RATE : Math.min(slowed, picked);
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

  const exchange = exchangeAt(rallies, time);
  useEffect(() => {
    if (following.current && exchange !== zoomedIn.current) {
      setPinched(null);
    }
  }, [exchange]);

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
  // Where the bar is coarser than the video, a small drag moves it frame by frame, a larger one follows the pointer.
  const precise = () => coarse((bar.current?.getBoundingClientRect().width ?? 0) / (to - from), match.fps);
  const pressBar = (event: PointerEvent<HTMLDivElement>) => {
    // No text selection, nor the browser's drag of it (a "no drop" cursor) while seeking.
    event.preventDefault();
    event.currentTarget.focus({ preventScroll: true });
    event.currentTarget.setPointerCapture(event.pointerId);
    dragging.current = true;
    const place = event.currentTarget.getBoundingClientRect();
    const thumb = place.left + ((Math.min(to, Math.max(from, video.current?.currentTime ?? time)) - from) / (to - from)) * place.width;
    if (!precise() || Math.abs(event.clientX - thumb) > THUMB_PX) {
      moveToPointer(event);
    }
    fine.current = precise() && video.current ? { x: event.clientX, frame: Math.round(video.current.currentTime * match.fps), n: 0 } : null;
  };
  const dragBar = (event: PointerEvent<HTMLDivElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
      return;
    }
    const f = fine.current;
    const n = f && nudgeOf(event.clientX - f.x);
    if (f && n !== null) {
      if (n !== f.n) {
        f.n = n;
        video.current?.pause();
        moveTo(frameTime(f.frame + n, match.fps));
        setNudge(n);
      }
      return;
    }
    fine.current = null;
    setNudge(null);
    moveToPointer(event);
  };
  const dropBar = () => {
    dragging.current = false;
    fine.current = null;
    setNudge(null);
  };
  // Fields and menus keep their arrows, and the bar when focused handles its own (it prevents the default).
  useEffect(() => {
    if (!free) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      const step = { ArrowLeft: -ARROW_STEP_S, ArrowRight: ARROW_STEP_S }[event.key];
      const typing = event.target instanceof HTMLElement && event.target.closest('input, textarea, select');
      if (step && video.current && !event.defaultPrevented && !typing && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
        event.preventDefault();
        moveTo(video.current.currentTime + step);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [free]);
  const keys: Record<string, (step: number) => number> = { ArrowLeft: (step) => time - step, ArrowRight: (step) => time + step, Home: () => from, End: () => to };
  const view = pinched ?? (views && auto ? autoView(views, time, width, height) : zoom ? viewAt(clip, time, width, height) : { x: 0, y: 0, w: width, h: height });
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
        zoomByHand(zoomView(shown.current, fx, fy, wheelZoom(event.deltaY, event.deltaMode), width, height));
      } else if (zoomedByHand.current) {
        event.preventDefault();
        const v = shown.current;
        zoomByHand(panView(v, (event.deltaX * v.w) / r.width, (event.deltaY * v.h) / r.height, width, height));
      }
    };
    let last = 1;
    const gesture = (event: Event & { scale?: number; clientX?: number; clientY?: number }) => {
      event.preventDefault();
      const [fx, fy] = at(event.clientX ?? 0, event.clientY ?? 0);
      const scale = event.scale ?? 1;
      zoomByHand(zoomView(shown.current, fx, fy, scale / last, width, height));
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
  // A click on the video plays or pauses it: the bar under it holds the controls.
  const playPause = () => {
    const v = video.current;
    if (v) {
      void (v.paused ? v.play().catch(() => {}) : v.pause());
    }
  };
  const toggle = () => {
    if (swallowClick.current) {
      swallowClick.current = false;
      return;
    }
    playPause();
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
    zoomByHand(panView(v, (-dx * v.w) / r.width, (-dy * v.h) / r.height, width, height));
  };
  const zoomBy = (factor: number) => zoomByHand(zoomView(view, 0.5, 0.5, factor, width, height));
  const toggleAuto = () => {
    setPinched(null);
    if (!auto || !pinched) {
      saveFlag(AUTO_KEY, !auto);
      setAuto(!auto);
    }
  };
  const autoShown = auto && !pinched;
  const toggleMuted = () => {
    setMuted(!muted);
    saveFlag(MUTED_KEY, !muted);
  };
  return (
    // In full screen, the room left holds the video whole with its bar (BAR_REM high) under it, no wider: the buttons stay
    // near it.
    <div className="min-h-0 lg:[:fullscreen_&]:@container-size">
      {/* One black block, the controls under the picture. */}
      <div
        className="overflow-hidden rounded-lg bg-black text-white lg:[:fullscreen_&]:mx-auto lg:[:fullscreen_&]:w-[min(100cqw,calc((100cqh-var(--bar))*16/9))]"
        style={{ '--bar': `${BAR_REM}rem` } as CSSProperties}
      >
        <div ref={frame} className="relative aspect-video overflow-hidden">
          <div
            className={cn('absolute inset-0 origin-top-left', free && !pinched && 'transition-transform duration-700 ease-in-out motion-reduce:transition-none')}
            style={{ transform: `scale(${width / view.w}) translate(${(-100 * view.x) / width}%, ${(-100 * view.y) / height}%)` }}
          >
            <video
              ref={video}
              src={match.video ?? undefined}
              muted={muted}
              playsInline
              onClick={toggle}
              onPlay={() => setPaused(false)}
              onPause={() => setPaused(true)}
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
          <VideoError video={video} />
          {caption && (
            <Tip label={t('review.captionMove')}>
              <span
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
            </Tip>
          )}
        </div>
        <div className="grid gap-0.5 px-2 pt-1.5 pb-1">
          <div
            ref={bar}
            role="slider"
            tabIndex={0}
            aria-label={t('review.position')}
            aria-valuemin={Math.round(from)}
            aria-valuemax={Math.round(to)}
            aria-valuenow={Math.round(time)}
            aria-valuetext={clock(time)}
            className="group flex h-5 cursor-pointer touch-none items-center rounded-sm outline-none select-none focus-visible:ring-3 focus-visible:ring-white/70"
            onPointerDown={pressBar}
            onLostPointerCapture={dropBar}
            onDragStart={(event) => event.preventDefault()}
            onPointerMove={dragBar}
            onKeyDown={(event) => {
              const next = keys[event.key];
              if (next) {
                event.preventDefault();
                moveTo(next(event.shiftKey ? 5 : 1));
              }
            }}
          >
            <div className="relative h-1.5 w-full rounded-full bg-white/20">
              {bands.map(([a, b]) => (
                <div key={a} className="absolute inset-y-0 rounded-full bg-[#ffd400]" style={{ left: share(a), right: `calc(100% - ${share(b)})` }} />
              ))}
              {marks.map((m) => (
                <div key={m} className="absolute -inset-y-1.5 w-1 -translate-x-1/2 rounded-full bg-primary" style={{ left: share(m) }} />
              ))}
              <div className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-sm transition-transform group-hover:scale-125" style={{ left: share(time) }} />
              {/* The frames a small drag moved. */}
              {nudge !== null && nudge !== 0 && (
                <div
                  className="pointer-events-none absolute bottom-full mb-2.5 -translate-x-1/2 rounded-sm bg-white px-1.5 py-0.5 text-xs font-medium text-black tabular-nums"
                  style={{ left: share(time) }}
                >
                  {new Intl.NumberFormat(i18n.language, { signDisplay: 'always' }).format(nudge)}
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-1">
            <VideoButton label={t(paused ? 'review.playVideo' : 'review.pauseVideo')} onClick={playPause}>
              {paused ? <Play aria-hidden className="fill-current" /> : <Pause aria-hidden className="fill-current" />}
            </VideoButton>
            {showTime && <span className="min-w-12 px-1 text-sm tabular-nums">{clock(time)}</span>}
            {free && (
              <>
                <VideoButton label={t('review.zoomMore')} tip={t('review.pinchNote')} onClick={() => zoomBy(ZOOM_STEP)}>
                  <ZoomIn aria-hidden />
                </VideoButton>
                <VideoButton label={t('review.zoomLess')} tip={t('review.pinchNote')} disabled={view.w >= width} onClick={() => zoomBy(1 / ZOOM_STEP)}>
                  <ZoomOut aria-hidden />
                </VideoButton>
                {views && (
                  <VideoButton label={t('review.autoZoom')} pressed={autoShown} onClick={toggleAuto}>
                    <ScanSearch aria-hidden />
                  </VideoButton>
                )}
              </>
            )}
            {/* No outline, nothing to zoom on. */}
            {clip.boxes.length > 0 && (
              <VideoButton
                label={t(zoom ? 'review.zoomOut' : 'review.zoomIn')}
                onClick={() => {
                  setPinched(null);
                  setZoom((z) => !z);
                }}
              >
                {zoom ? <ZoomOut aria-hidden /> : <ZoomIn aria-hidden />}
              </VideoButton>
            )}
            {touches && (
              <VideoButton
                label={t('review.slowTouches')}
                pressed={slow}
                onClick={() => {
                  saveFlag(SLOW_KEY, !slow);
                  setSlow(!slow);
                }}
              >
                <Snail aria-hidden />
              </VideoButton>
            )}
            <div role="group" aria-label={t('review.speed')} className="flex gap-x-1">
              {SPEEDS.map((s) => (
                <VideoButton
                  key={s}
                  label={`${new Intl.NumberFormat(i18n.language).format(s)}×`}
                  tip={t('review.speed')}
                  pressed={s === speed}
                  className="px-1.5"
                  onClick={() => {
                    picked = s;
                    setSpeed(s);
                  }}
                >
                  {`${new Intl.NumberFormat(i18n.language).format(s)}×`}
                </VideoButton>
              ))}
            </div>
            {free && (
              <VideoButton label={t(muted ? 'review.soundOn' : 'review.soundOff')} onClick={toggleMuted}>
                {muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
              </VideoButton>
            )}
            {extra && <div className="ml-auto flex">{extra}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
