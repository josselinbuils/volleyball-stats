import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type PointerEvent, type ReactNode, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Clock } from '@/lib/clock';
import { match } from '@/lib/match';
import { togglePlay, usePlayer } from '@/lib/player';
import { cn } from '@/lib/utils';
import { BroadcastControls, canSpeak } from '@/components/Watch/Broadcast';
import { arrange, clampRatio, pageHeight, stacked, swapped, swappedSides, toggled, VIEWS, type Divider, type Layout, type View } from '@/components/Watch/helpers/layout';
import { useLayout } from '@/components/Watch/hooks/useLayout';
import { PlaylistBar } from '@/components/Watch/PlaylistBar';
import { CourtView, LoadPositions, ReplayCaption, SceneView } from '@/components/Watch/Replay';
import { canDraw3d } from '@/components/Watch/Scene3D';
import { Scoreboard } from '@/components/Watch/Scoreboard';
import { VideoControls } from '@/components/Watch/VideoControls';
import { VideoPanel } from '@/components/Watch/VideoPanel';

// Narrower than this, the page stacks the views.
const STACK_PX = 640;
// What the page keeps on screen around the views: the score above, the controls below.
const AROUND_PX = 128;
// A bar's width under the pointer, wider than the gap it sits in.
const BAR_PX = 12;
// A finger needs more: the line takes touches a little around it.
const TOUCH_AREA = 'before:absolute pointer-coarse:before:-inset-2';
const KEY_STEP = 0.02;
const DRAG_PX = 5;
const MOVE_MS = 250;

const LABELS: Record<View, string> = { video: 'video', '2d': 'scene3d.2d', '3d': 'scene3d.3d', tv: 'scene3d.tv' };

const subscribeResize = (listener: () => void) => {
  window.addEventListener('resize', listener);
  return () => window.removeEventListener('resize', listener);
};

/** The video, the court from above, the 3D scene and the TV view, those the viewer picks, side by side
 * above the controls they share; full screen takes all of it. */
export function Stage() {
  const { t } = useTranslation();
  const { video, setVideo } = usePlayer();
  const [available] = useState(() => VIEWS.filter((v) => (v === 'video' ? !!match.video : v === '2d' || canDraw3d())));
  const stage = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const sync = () => setFull(document.fullscreenElement !== null);
    document.addEventListener('fullscreenchange', sync);
    return () => document.removeEventListener('fullscreenchange', sync);
  }, []);
  const [layout, update] = useLayout(available);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const element = area.current;
    if (!element) {
      return;
    }
    const measure = () => setSize({ width: element.clientWidth, height: element.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const windowHeight = useSyncExternalStore(subscribeResize, () => innerHeight);
  const stack = !full && size.width < STACK_PX;
  const placed = stack
    ? stacked(layout.order, size.width)
    : full
      ? arrange(layout, size.width, size.height, size.height > size.width)
      : arrange(layout, size.width, pageHeight(layout, size.width, windowHeight - AROUND_PX));
  // Views glide to a place the viewer gave them, not while a bar moves or the screen changes.
  const [moving, setMoving] = useState(false);
  const moved = useRef(0);
  useEffect(() => () => clearTimeout(moved.current), []);
  const move = (change: (now: Layout) => Layout) => {
    setMoving(true);
    clearTimeout(moved.current);
    moved.current = window.setTimeout(() => setMoving(false), MOVE_MS);
    update(change);
  };
  const [follow, setFollow] = useState(false);
  const [voice, setVoice] = useState(false);
  // Where the pointer went down: a click plays or pauses, a drag turning the 3D view does not.
  const down = useRef({ x: 0, y: 0 });
  // Without a video, a clock plays the moments on the court's top view.
  useEffect(() => {
    if (match.video || !stage.current) {
      return;
    }
    const clock = new Clock(stage.current, match.duration);
    setVideo(clock);
    return () => {
      clock.pause();
      setVideo(null);
    };
  }, [setVideo]);

  const shows = (view: View) => layout.order.includes(view);
  const replayShown = layout.order.some((v) => v !== 'video');
  const views: Partial<Record<View, ReactNode>> = {
    '2d': <CourtView />,
    '3d': <SceneView tv={false} voice={false} />,
    tv: <SceneView tv voice={voice} />,
  };

  return (
    <div className="min-w-0">
      <div ref={stage} className={cn('grid gap-3', full && 'flex h-full flex-col gap-0 bg-background')}>
        {/* Over the video alone, full screen shows nothing but it. */}
        {(!full || replayShown) && (
          <div className={cn(full && 'p-2')}>
            <Scoreboard report={!shows('video')} />
          </div>
        )}
        <div className={cn('overflow-hidden bg-border', full ? 'flex min-h-0 flex-1 flex-col' : 'rounded-lg border')}>
          <div ref={area} className={cn('relative', full && 'min-h-0 flex-1')} style={full ? undefined : { height: placed.height }}>
            {replayShown && <LoadPositions />}
            {available.map((view) => {
              const rect = placed.rects[view];
              // Hidden, the video keeps playing, and the height of the views for a playlist to scroll to.
              if (!rect && view !== 'video') {
                return null;
              }
              const style = rect ?? { left: 0, top: 0, width: 0, height: placed.height };
              return (
                <div
                  key={view}
                  className={cn(
                    'group/panel absolute overflow-hidden',
                    view === 'video' ? 'bg-black' : 'cursor-default bg-card select-none',
                    !rect && 'invisible',
                    moving && 'transition-[left,top,width,height] duration-200 motion-reduce:transition-none',
                  )}
                  style={style}
                  onPointerDown={(e) => {
                    down.current = { x: e.clientX, y: e.clientY };
                  }}
                  onClick={(e) => {
                    const target = e.target as Element;
                    // A dialog opened from a view is no click on it, though its events pass through.
                    if (e.currentTarget.contains(target) && !target.closest('button') && Math.hypot(e.clientX - down.current.x, e.clientY - down.current.y) < DRAG_PX) {
                      togglePlay(video);
                    }
                  }}
                >
                  {view === 'video' ? <VideoPanel follow={follow} big={full && layout.order.length === 1} shown={!!rect} /> : views[view]}
                </div>
              );
            })}
            {placed.dividers.map((divider) => (
              <Bar
                key={divider.ratio}
                divider={divider}
                area={area}
                value={layout[divider.ratio]}
                onChange={(value) => update((now) => ({ ...now, [divider.ratio]: value }))}
                onSwap={() => move((now) => swappedSides(now, divider.ratio))}
              />
            ))}
            {placed.swaps.map(({ at, between: [a, b] }) => (
              <LineButton key={at} at={at} onSwap={() => move((now) => swapped(now, a, b))} />
            ))}
          </div>
          <VideoControls
            light={!match.video}
            stage={stage}
            follow={follow}
            onFollow={shows('video') ? () => setFollow((on) => !on) : undefined}
            voice={full && shows('tv') && canSpeak() ? { on: voice, toggle: () => setVoice(!voice) } : undefined}
            views={
              available.length > 1
                ? (inMenu) => {
                    const dark = !!match.video && !inMenu;
                    return (
                      <ToggleGroup
                        type="multiple"
                        variant="outline"
                        size="sm"
                        spacing={0}
                        value={layout.order}
                        aria-label={t('layout.views')}
                        className={cn('shrink-0', inMenu ? 'w-full' : 'mx-1', dark ? 'text-white' : 'bg-card')}
                      >
                        {available.map((view) => (
                          <ToggleGroupItem
                            key={view}
                            value={view}
                            onClick={() => move((now) => toggled(now, view))}
                            className={cn(
                              'px-2.5 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground',
                              inMenu && 'flex-1',
                              dark && 'border-white/30 hover:bg-white/15 hover:text-white',
                            )}
                          >
                            {t(LABELS[view])}
                          </ToggleGroupItem>
                        ))}
                      </ToggleGroup>
                    );
                  }
                : undefined
            }
          />
        </div>
      </div>
      <PlaylistBar />
      {shows('tv') && !full && <BroadcastControls voice={voice} onVoice={setVoice} />}
      {replayShown && <ReplayCaption />}
    </div>
  );
}

/** The line between views: dragged it resizes those on both sides at once, clicked it trades its two sides. */
function Bar({ divider, area, value, onChange, onSwap }: { divider: Divider; area: RefObject<HTMLDivElement | null>; value: number; onChange: (value: number) => void; onSwap: () => void }) {
  const { t } = useTranslation();
  const across = divider.axis === 'x';
  const start = useRef<{ x: number; y: number } | null>(null);
  const dragging = useRef(false);
  const follow = (e: PointerEvent<HTMLDivElement>) => {
    const box = area.current?.getBoundingClientRect();
    if (!box || !start.current) {
      return;
    }
    dragging.current ||= Math.hypot(e.clientX - start.current.x, e.clientY - start.current.y) > DRAG_PX;
    if (dragging.current) {
      onChange(clampRatio(across ? (e.clientX - box.left) / box.width : (e.clientY - box.top) / box.height));
    }
  };
  const [before, after] = across ? ['ArrowLeft', 'ArrowRight'] : ['ArrowUp', 'ArrowDown'];
  const place = across
    ? { left: divider.at - BAR_PX / 2, top: divider.start, width: BAR_PX, height: divider.length }
    : { left: divider.start, top: divider.at - BAR_PX / 2, width: divider.length, height: BAR_PX };
  return (
    <div
      role="separator"
      tabIndex={0}
      aria-orientation={across ? 'vertical' : 'horizontal'}
      aria-label={t('layout.line')}
      title={t('layout.line')}
      aria-valuemin={20}
      aria-valuemax={80}
      aria-valuenow={Math.round(value * 100)}
      className={cn('group/bar absolute z-20 touch-none outline-none', TOUCH_AREA, across ? 'cursor-col-resize' : 'cursor-row-resize')}
      style={place}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        start.current = { x: e.clientX, y: e.clientY };
        dragging.current = false;
      }}
      onPointerMove={follow}
      onPointerUp={() => {
        if (start.current && !dragging.current) {
          onSwap();
        }
        start.current = null;
      }}
      onPointerCancel={() => {
        start.current = null;
      }}
      onKeyDown={(e) => {
        if (e.key === before || e.key === after) {
          e.preventDefault();
          onChange(clampRatio(value + (e.key === after ? KEY_STEP : -KEY_STEP)));
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSwap();
        }
      }}
    >
      <div
        className={cn(
          'absolute bg-primary opacity-0 transition-opacity group-hover/bar:opacity-100 group-focus-visible/bar:opacity-100 group-active/bar:opacity-100',
          across ? 'inset-y-0 left-1/2 w-1 -translate-x-1/2' : 'inset-x-0 top-1/2 h-1 -translate-y-1/2',
        )}
      />
      <Grabber across={across} />
    </div>
  );
}

/** The line between stacked views: tapped, it swaps them. */
function LineButton({ at, onSwap }: { at: number; onSwap: () => void }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      aria-label={t('layout.swap')}
      title={t('layout.swap')}
      className={cn('group/bar absolute inset-x-0 z-20 cursor-pointer outline-none', TOUCH_AREA)}
      style={{ top: at - BAR_PX / 2, height: BAR_PX }}
      onClick={onSwap}
    >
      <span className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 bg-primary opacity-0 transition-opacity group-hover/bar:opacity-100 group-focus-visible/bar:opacity-100 group-active/bar:opacity-100" />
      <Grabber across={false} />
    </button>
  );
}

/** A small mark in the middle of a line, on touch screens: nothing shows there when hovering. */
function Grabber({ across }: { across: boolean }) {
  return <span aria-hidden className={cn('absolute top-1/2 left-1/2 hidden -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground/50 pointer-coarse:block', across ? 'h-6 w-1' : 'h-1 w-6')} />;
}
