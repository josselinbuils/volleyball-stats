import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { Maximize, Minimize, ZoomIn, ZoomOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';
import { cn } from '@/lib/utils';
import { clampView, zoomAt, type Zoom } from './helpers/zoom';

const onFullscreen = (change: () => void) => {
  document.addEventListener('fullscreenchange', change);
  return () => document.removeEventListener('fullscreenchange', change);
};

// A button's step, a double click's zoom.
const STEP = 1.6;
const DOUBLE = 2.5;

/** A picture or a video (`children`, filling the box) to look at closely: zoomed by its buttons, a double click, a pinch
 * or the wheel with Ctrl (the wheel alone once zoomed), moved by dragging, and full screen. `controls` sit beside the
 * zoom's buttons (a player's). */
export function Zoomable({ children, className, controls }: { children: ReactNode; className?: string; controls?: ReactNode }) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState<Zoom>({ scale: 1, x: 0, y: 0 });
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  // The zoom as the wheel's listener, added once, reads it.
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const full = useSyncExternalStore(
    onFullscreen,
    () => document.fullscreenElement === box.current,
    () => false,
  );
  const size = () => ({ w: box.current?.clientWidth ?? 1, h: box.current?.clientHeight ?? 1 });
  const at = (clientX: number, clientY: number) => {
    const r = box.current?.getBoundingClientRect();
    return { x: clientX - (r?.left ?? 0), y: clientY - (r?.top ?? 0) };
  };
  const zoomBy = (factor: number, point?: { x: number; y: number }) => {
    const { w, h } = size();
    setZoom((z) => zoomAt(z, factor, point ?? { x: w / 2, y: h / 2 }, w, h));
  };

  // The wheel zooms with Ctrl (a trackpad's pinch), or once zoomed; else the page scrolls.
  useEffect(() => {
    const el = box.current;
    if (!el) {
      return;
    }
    const wheel = (e: WheelEvent) => {
      if (!e.ctrlKey && zoomRef.current.scale <= 1) {
        return;
      }
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const { w, h } = { w: el.clientWidth, h: el.clientHeight };
      setZoom((z) => zoomAt(z, Math.exp(-Math.max(-100, Math.min(100, e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY)) * 0.0025), { x: e.clientX - r.left, y: e.clientY - r.top }, w, h));
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  }, []);
  // Back within the box when it changes size (full screen).
  useEffect(() => {
    const { w, h } = size();
    setZoom((z) => clampView(z, w, h));
  }, [full]);

  return (
    <div
      ref={box}
      className={cn('relative touch-none overflow-hidden bg-muted select-none', full ? 'bg-black' : 'rounded-md', zoom.scale > 1 && 'cursor-grab active:cursor-grabbing', className)}
      onDoubleClick={(e) => (zoom.scale > 1 ? setZoom({ scale: 1, x: 0, y: 0 }) : zoomBy(DOUBLE, at(e.clientX, e.clientY)))}
      onPointerDown={(e) => {
        if ((e.target as HTMLElement).closest('button, input')) {
          return;
        }
        pointers.current.set(e.pointerId, at(e.clientX, e.clientY));
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        const last = pointers.current.get(e.pointerId);
        if (!last) {
          return;
        }
        const now = at(e.clientX, e.clientY);
        const others = [...pointers.current.entries()].filter(([id]) => id !== e.pointerId).map(([, p]) => p);
        const { w, h } = size();
        if (others.length === 1) {
          // A pinch: the distance between the fingers.
          const [o] = others;
          const before = Math.hypot(last.x - o.x, last.y - o.y);
          const after = Math.hypot(now.x - o.x, now.y - o.y);
          if (before > 0) {
            setZoom((z) => zoomAt(z, after / before, { x: (now.x + o.x) / 2, y: (now.y + o.y) / 2 }, w, h));
          }
        } else if (others.length === 0) {
          setZoom((z) => clampView({ ...z, x: z.x + now.x - last.x, y: z.y + now.y - last.y }, w, h));
        }
        pointers.current.set(e.pointerId, now);
      }}
      onPointerUp={(e) => pointers.current.delete(e.pointerId)}
      onPointerCancel={(e) => pointers.current.delete(e.pointerId)}
    >
      <div className="size-full origin-top-left" style={{ transform: `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.scale})` }}>
        {children}
      </div>
      <div className="absolute right-1.5 bottom-1.5 left-1.5 flex items-center justify-end gap-1">
        {controls}
        <Tip label={t('zoomOutView')}>
          <Button type="button" variant="secondary" size="icon-sm" aria-label={t('zoomOutView')} disabled={zoom.scale <= 1} onClick={() => zoomBy(1 / STEP)}>
            <ZoomOut aria-hidden />
          </Button>
        </Tip>
        <Tip label={t('zoomInView')}>
          <Button type="button" variant="secondary" size="icon-sm" aria-label={t('zoomInView')} onClick={() => zoomBy(STEP)}>
            <ZoomIn aria-hidden />
          </Button>
        </Tip>
        {document.fullscreenEnabled && (
          <Tip label={t(full ? 'exitFullscreen' : 'fullscreen')}>
            <Button
              type="button"
              variant="secondary"
              size="icon-sm"
              aria-label={t(full ? 'exitFullscreen' : 'fullscreen')}
              onClick={() => void (full ? document.exitFullscreen() : box.current?.requestFullscreen())}
            >
              {full ? <Minimize aria-hidden /> : <Maximize aria-hidden />}
            </Button>
          </Tip>
        )}
      </div>
    </div>
  );
}
