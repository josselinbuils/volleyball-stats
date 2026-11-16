import { useEffect, useRef, useState, type RefObject } from 'react';

/** Still this long while the video plays, full screen's controls hide, as YouTube's. */
const IDLE_MS = 3000;

/** Whether full screen's controls show (`active`, over the video in `box`): a move, a tap or a key brings them back,
 * and they hide once still for IDLE_MS while the video plays, unless the mouse rests on `bar` or a menu, a dialog or
 * the list of what plays is open. `tapped` is for a touch on the video: it shows them if hidden, else hides them. */
export function useAutoHide(active: boolean, box: RefObject<HTMLElement | null>, bar: RefObject<HTMLElement | null>, video: HTMLVideoElement | null) {
  const [shown, setShown] = useState(true);
  // Whether the mouse rests on the bar: a touch screen keeps `:hover` after a tap.
  const over = useRef(false);
  const timer = useRef(0);
  const arm = useRef(() => {});
  useEffect(() => {
    const element = box.current;
    if (!active || !element) {
      setShown(true);
      return;
    }
    const hide = () => {
      const kept = !video || video.paused || over.current || document.querySelector('[role="menu"], [role="dialog"], [data-watch-panel]');
      if (kept) {
        arm.current();
      } else {
        setShown(false);
      }
    };
    arm.current = () => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(hide, IDLE_MS);
    };
    const show = () => {
      setShown(true);
      arm.current();
    };
    const moved = (e: PointerEvent) => {
      if (e.pointerType === 'mouse') {
        over.current = !!bar.current?.contains(e.target as Node);
        show();
      }
    };
    // A touch shows them, but on the video: `tapped` then.
    const touched = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse' && e.target !== video) {
        show();
      }
    };
    const left = () => {
      over.current = false;
    };
    element.addEventListener('pointermove', moved);
    element.addEventListener('pointerdown', touched);
    element.addEventListener('pointerleave', left);
    document.addEventListener('keydown', show);
    video?.addEventListener('pause', show);
    video?.addEventListener('play', show);
    show();
    return () => {
      window.clearTimeout(timer.current);
      element.removeEventListener('pointermove', moved);
      element.removeEventListener('pointerdown', touched);
      element.removeEventListener('pointerleave', left);
      document.removeEventListener('keydown', show);
      video?.removeEventListener('pause', show);
      video?.removeEventListener('play', show);
    };
  }, [active, box, bar, video]);
  const tapped = () => {
    setShown(!shown);
    arm.current();
  };
  return { shown: shown || !active, tapped };
}
