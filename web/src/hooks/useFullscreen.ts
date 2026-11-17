import { useSyncExternalStore, type RefObject } from 'react';

const onFullscreen = (change: () => void) => {
  document.addEventListener('fullscreenchange', change);
  return () => document.removeEventListener('fullscreenchange', change);
};

/** The element in full screen, null if none. */
export function useFullscreenElement() {
  return useSyncExternalStore(
    onFullscreen,
    () => document.fullscreenElement,
    () => null,
  );
}

/** Whether `block` fills the screen, and what puts it in or out. */
export function useFullscreen(block: RefObject<HTMLElement | null>) {
  const full = useFullscreenElement() === block.current && block.current !== null;
  const toggle = () => void (full ? document.exitFullscreen() : block.current?.requestFullscreen());
  return [full, toggle] as const;
}
