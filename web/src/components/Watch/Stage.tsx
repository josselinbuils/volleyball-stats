import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type PointerEvent, type ReactNode, type RefObject } from 'react';
import { ArrowLeftRight, ArrowUpDown, GripHorizontal, Maximize2, Minimize2, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Clock } from '@/lib/clock';
import { match } from '@/lib/match';
import { togglePlay, usePlayer } from '@/lib/player';
import { cn } from '@/lib/utils';
import { BroadcastControls, canSpeak } from '@/components/Watch/Broadcast';
import { arrange, clampRatio, pageHeight, stacked, swapped, swappedSides, toggled, VIEWS, zoomed, type Divider, type Layout, type View } from '@/components/Watch/helpers/layout';
import { useLayout } from '@/components/Watch/hooks/useLayout';
import { PlaylistBar } from '@/components/Watch/PlaylistBar';
import { CourtView, LoadPositions, NowLine, ReplayCaption, SceneView } from '@/components/Watch/Replay';
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
const KEY_STEP = 0.02;
const DRAG_PX = 5;
const MOVE_MS = 250;

const LABELS: Record<View, string> = { video: 'video', '2d': 'scene3d.2d', '3d': 'scene3d.3d', tv: 'scene3d.tv' };

const subscribeResize = (listener: () => void) => {
  window.addEventListener('resize', listener);
  return () => window.removeEventListener('resize', listener);
};

/** The video, the court from above, the 3D scene and the TV view, those the viewer picks, side by side
 * above the controls they share; full screen takes all of it and has its own layout. */
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
  const [layout, update] = useLayout(full, available);
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
  // The title being dragged, and the view under it.
  const [dragged, setDragged] = useState<View | null>(null);
  const [over, setOver] = useState<View | null>(null);
  const viewAt = (clientX: number, clientY: number): View | null => {
    const box = area.current?.getBoundingClientRect();
    if (!box) {
      return null;
    }
    const [x, y] = [clientX - box.left, clientY - box.top];
    return (
      layout.order.find((v) => {
        const r = placed.rects[v];
        return r && x >= r.left && x <= r.left + r.width && y >= r.top && y <= r.top + r.height;
      }) ?? null
    );
  };
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
          <div className={cn('grid gap-3 lg:auto-cols-fr lg:grid-flow-col', full && 'p-2')}>
            <Scoreboard />
            <NowLine report={!shows('video')} />
          </div>
        )}
        <div className={cn('group/stage overflow-hidden bg-border', full ? 'flex min-h-0 flex-1 flex-col' : 'rounded-lg border')}>
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
                  {rect && (
                    <PanelTitle
                      view={view}
                      layout={layout}
                      onZoom={() => move((now) => zoomed(now, view))}
                      onMoveNext={() => {
                        const at = layout.order.indexOf(view);
                        move((now) => swapped(now, view, layout.order[(at + 1) % layout.order.length]));
                      }}
                      onDrag={(x, y) => {
                        setDragged(view);
                        setOver(viewAt(x, y));
                      }}
                      onDrop={(x, y) => {
                        const target = viewAt(x, y);
                        setDragged(null);
                        setOver(null);
                        if (target && target !== view) {
                          move((now) => swapped(now, view, target));
                        }
                      }}
                      voice={
                        view === 'tv' && full && canSpeak() ? (
                          <button
                            type="button"
                            className={TITLE_BUTTON}
                            aria-pressed={voice}
                            aria-label={t(voice ? 'broadcast.voiceOn' : 'broadcast.voiceOff')}
                            title={t(voice ? 'broadcast.voiceOn' : 'broadcast.voiceOff')}
                            onClick={() => setVoice(!voice)}
                          >
                            {voice ? <Volume2 aria-hidden /> : <VolumeX aria-hidden />}
                          </button>
                        ) : null
                      }
                    />
                  )}
                  {dragged && over === view && dragged !== view && <div aria-hidden className="pointer-events-none absolute inset-0 z-30 bg-primary/20 ring-3 ring-primary ring-inset" />}
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
          </div>
          <VideoControls light={!match.video} stage={stage} follow={follow} onFollow={shows('video') ? () => setFollow((on) => !on) : undefined}>
            {available.length > 1 && (
              <ToggleGroup
                type="multiple"
                variant="outline"
                size="sm"
                spacing={0}
                value={layout.order}
                aria-label={t('layout.views')}
                className={cn('mx-1 shrink-0', match.video ? 'text-white' : 'bg-card')}
              >
                {available.map((view) => (
                  <ToggleGroupItem
                    key={view}
                    value={view}
                    onClick={() => move((now) => toggled(now, view))}
                    className={cn('px-2.5 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground', match.video && 'border-white/30 hover:bg-white/15 hover:text-white')}
                  >
                    {t(LABELS[view])}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            )}
          </VideoControls>
        </div>
      </div>
      <PlaylistBar />
      {shows('tv') && !full && <BroadcastControls voice={voice} onVoice={setVoice} />}
      {replayShown && <ReplayCaption />}
    </div>
  );
}

const TITLE_BUTTON = 'inline-flex size-7 items-center justify-center rounded-full outline-none hover:bg-white/20 focus-visible:ring-2 focus-visible:ring-white/70 [&_svg]:size-4';

/** Over a view when the pointer is on it: its name, dragged onto another view to trade places with it,
 * a click trading with the next one; and the zoom on it. */
function PanelTitle({
  view,
  layout,
  voice,
  onZoom,
  onMoveNext,
  onDrag,
  onDrop,
}: {
  view: View;
  layout: Layout;
  voice: ReactNode;
  onZoom: () => void;
  onMoveNext: () => void;
  onDrag: (x: number, y: number) => void;
  onDrop: (x: number, y: number) => void;
}) {
  const { t } = useTranslation();
  const start = useRef<{ x: number; y: number } | null>(null);
  const dragging = useRef(false);
  const name = t(LABELS[view]);
  const several = layout.order.length > 1;
  if (!several && !layout.before && !voice) {
    return null;
  }
  const moveTo = (e: PointerEvent<HTMLButtonElement>) => {
    if (start.current && (dragging.current || Math.hypot(e.clientX - start.current.x, e.clientY - start.current.y) > DRAG_PX)) {
      dragging.current = true;
      onDrag(e.clientX, e.clientY);
    }
  };
  return (
    <div
      className="absolute top-2 left-1/2 z-20 flex -translate-x-1/2 items-center rounded-full bg-black/60 text-white opacity-0 backdrop-blur-sm transition-opacity group-hover/panel:opacity-100 focus-within:opacity-100 pointer-coarse:top-auto pointer-coarse:right-2 pointer-coarse:bottom-2 pointer-coarse:left-auto pointer-coarse:translate-x-0 pointer-coarse:opacity-100"
      onPointerDown={(e) => e.stopPropagation()}
    >
      {several ? (
        <button
          type="button"
          aria-label={t('layout.move', { view: name })}
          title={t('layout.move', { view: name })}
          className="inline-flex h-7 cursor-grab touch-none items-center gap-1 rounded-full px-2 text-xs font-medium outline-none hover:bg-white/20 focus-visible:ring-2 focus-visible:ring-white/70 active:cursor-grabbing [&_svg]:size-4"
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            start.current = { x: e.clientX, y: e.clientY };
            dragging.current = false;
          }}
          onPointerMove={moveTo}
          onPointerUp={(e) => {
            if (dragging.current) {
              onDrop(e.clientX, e.clientY);
            }
            start.current = null;
          }}
          onClick={() => {
            if (!dragging.current) {
              onMoveNext();
            }
            dragging.current = false;
          }}
        >
          <GripHorizontal aria-hidden />
          <span className="pointer-coarse:hidden">{name}</span>
        </button>
      ) : (
        <span className="px-2.5 text-xs font-medium pointer-coarse:hidden">{name}</span>
      )}
      {voice}
      {(several || layout.before) && (
        <button type="button" className={TITLE_BUTTON} aria-label={t(layout.before ? 'layout.restore' : 'layout.zoom')} title={t(layout.before ? 'layout.restore' : 'layout.zoom')} onClick={onZoom}>
          {layout.before ? <Minimize2 aria-hidden /> : <Maximize2 aria-hidden />}
        </button>
      )}
    </div>
  );
}

/** The bar between views, moved to resize those on both sides at once, with a button trading its two sides. */
function Bar({ divider, area, value, onChange, onSwap }: { divider: Divider; area: RefObject<HTMLDivElement | null>; value: number; onChange: (value: number) => void; onSwap: () => void }) {
  const { t } = useTranslation();
  const across = divider.axis === 'x';
  const follow = (e: PointerEvent<HTMLDivElement>) => {
    const box = area.current?.getBoundingClientRect();
    if (box && e.currentTarget.hasPointerCapture(e.pointerId)) {
      onChange(clampRatio(across ? (e.clientX - box.left) / box.width : (e.clientY - box.top) / box.height));
    }
  };
  const [before, after] = across ? ['ArrowLeft', 'ArrowRight'] : ['ArrowUp', 'ArrowDown'];
  const place = across
    ? { left: divider.at - BAR_PX / 2, top: divider.start, width: BAR_PX, height: divider.length }
    : { left: divider.start, top: divider.at - BAR_PX / 2, width: divider.length, height: BAR_PX };
  return (
    <div className="absolute z-20" style={place}>
      <div
        role="separator"
        tabIndex={0}
        aria-orientation={across ? 'vertical' : 'horizontal'}
        aria-label={t('layout.resize')}
        aria-valuemin={20}
        aria-valuemax={80}
        aria-valuenow={Math.round(value * 100)}
        className={cn('group/bar absolute inset-0 touch-none outline-none', across ? 'cursor-col-resize' : 'cursor-row-resize')}
        onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
        onPointerMove={follow}
        onKeyDown={(e) => {
          if (e.key === before || e.key === after) {
            e.preventDefault();
            onChange(clampRatio(value + (e.key === after ? KEY_STEP : -KEY_STEP)));
          }
        }}
      >
        <div
          className={cn(
            'absolute bg-primary opacity-0 transition-opacity group-hover/bar:opacity-100 group-focus-visible/bar:opacity-100 group-active/bar:opacity-100',
            across ? 'inset-y-0 left-1/2 w-1 -translate-x-1/2' : 'inset-x-0 top-1/2 h-1 -translate-y-1/2',
          )}
        />
      </div>
      <button
        type="button"
        aria-label={t('layout.swap')}
        title={t('layout.swap')}
        className="absolute inline-flex size-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border bg-card text-foreground opacity-0 shadow-xs transition-opacity outline-none group-hover/stage:opacity-100 hover:bg-accent focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50 pointer-coarse:opacity-100 [&_svg]:size-4"
        style={across ? { left: BAR_PX / 2, top: divider.button } : { left: divider.button, top: BAR_PX / 2 }}
        onClick={onSwap}
      >
        {across ? <ArrowLeftRight aria-hidden /> : <ArrowUpDown aria-hidden />}
      </button>
    </div>
  );
}
