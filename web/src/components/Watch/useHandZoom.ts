import { useEffect, useRef, useState } from 'react';
import { clampView, wheelZoom, zoomAt, type Zoom } from '@/components/helpers/zoom';

/** A mouse press moving this far drags the zoomed video: no click, no play or pause. */
const DRAG_PX = 6;
const WHOLE: Zoom = { scale: 1, x: 0, y: 0 };
type Point = { x: number; y: number };

const mid = ([a, b]: Point[]): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
const gap = ([a, b]: Point[]) => Math.hypot(a.x - b.x, a.y - b.y);

/** `video` zoomed by hand where one points: ⌘ or Ctrl + the wheel (a trackpad's pinch, Safari's gesture events), or two
 * fingers, which also move it; dragged once zoomed, by the mouse or one finger. The wheel alone scrolls the page, zoomed
 * or not. The zoom in fractions of the video's box (x, y: where its top left corner sits), the box always covered;
 * `current` for a loop reading it each frame. */
export function useHandZoom(video: HTMLVideoElement | null) {
  const [zoom, setZoom] = useState<Zoom>(WHOLE);
  const current = useRef(zoom);
  current.current = zoom;
  useEffect(() => {
    if (!video) {
      return;
    }
    // The video's place unzoomed: its own rect is the zoomed picture's.
    const box = () => {
      const around = video.offsetParent?.getBoundingClientRect();
      return { left: (around?.left ?? 0) + video.offsetLeft, top: (around?.top ?? 0) + video.offsetTop, width: video.offsetWidth || 1, height: video.offsetHeight || 1 };
    };
    const at = (x: number, y: number): Point => {
      const r = box();
      return { x: (x - r.left) / r.width, y: (y - r.top) / r.height };
    };
    const by = (factor: number, point: Point) => setZoom((z) => zoomAt(z, factor, point, 1, 1));
    const move = (dx: number, dy: number) => {
      const r = box();
      setZoom((z) => clampView({ ...z, x: z.x + dx / r.width, y: z.y + dy / r.height }, 1, 1));
    };
    const wheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        by(wheelZoom(e.deltaY, e.deltaMode), at(e.clientX, e.clientY));
      }
    };
    // Touch: two fingers zoom and move it, one moves it once zoomed; else the page scrolls as usual.
    let fingers: Point[] = [];
    const touched = (e: TouchEvent) => {
      fingers = [...e.touches].map((t) => ({ x: t.clientX, y: t.clientY }));
    };
    const touchMove = (e: TouchEvent) => {
      const before = fingers;
      touched(e);
      // Not cancelable: the page already scrolls.
      if (!e.cancelable || before.length !== fingers.length) {
        return;
      }
      if (fingers.length === 2) {
        e.preventDefault();
        const [from, to] = [mid(before), mid(fingers)];
        move(to.x - from.x, to.y - from.y);
        if (gap(before) > 0) {
          by(gap(fingers) / gap(before), at(to.x, to.y));
        }
      } else if (fingers.length === 1 && current.current.scale > 1) {
        e.preventDefault();
        move(fingers[0].x - before[0].x, fingers[0].y - before[0].y);
      }
    };
    // Safari's trackpad pinch; on a touch screen the fingers already zoom.
    let last = 1;
    const gestureStart = (e: Event) => {
      e.preventDefault();
      last = 1;
    };
    const gesture = (e: Event & { scale?: number; clientX?: number; clientY?: number }) => {
      e.preventDefault();
      const scale = e.scale ?? 1;
      if (!fingers.length) {
        by(scale / last, at(e.clientX ?? 0, e.clientY ?? 0));
      }
      last = scale;
    };
    // The mouse drags it once zoomed; the click ending a drag neither plays nor pauses.
    let press: (Point & { moved: boolean }) | null = null;
    let dragged = false;
    const down = (e: PointerEvent) => {
      dragged = false;
      if (e.pointerType !== 'touch' && e.button === 0 && current.current.scale > 1) {
        press = { x: e.clientX, y: e.clientY, moved: false };
      }
    };
    const drag = (e: PointerEvent) => {
      if (!press || (!press.moved && Math.hypot(e.clientX - press.x, e.clientY - press.y) < DRAG_PX)) {
        return;
      }
      if (!press.moved) {
        press.moved = true;
        video.setPointerCapture(e.pointerId);
      }
      move(e.clientX - press.x, e.clientY - press.y);
      press.x = e.clientX;
      press.y = e.clientY;
    };
    const up = () => {
      dragged = press?.moved ?? false;
      press = null;
    };
    const click = (e: MouseEvent) => {
      if (dragged) {
        e.stopPropagation();
        dragged = false;
      }
    };
    const listeners: [string, EventListener, AddEventListenerOptions?][] = [
      ['wheel', wheel as EventListener, { passive: false }],
      ['touchstart', touched as EventListener],
      ['touchmove', touchMove as EventListener, { passive: false }],
      ['touchend', touched as EventListener],
      ['touchcancel', touched as EventListener],
      ['gesturestart', gestureStart],
      ['gesturechange', gesture as EventListener],
      ['pointerdown', down as EventListener],
      ['pointermove', drag as EventListener],
      ['pointerup', up],
      ['pointercancel', up],
      ['click', click as EventListener],
    ];
    for (const [type, listener, options] of listeners) {
      video.addEventListener(type, listener, options);
    }
    return () => {
      for (const [type, listener] of listeners) {
        video.removeEventListener(type, listener);
      }
      setZoom(WHOLE);
    };
  }, [video]);
  return { zoom, current, reset: () => setZoom(WHOLE) };
}
