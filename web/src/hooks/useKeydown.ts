import { useEffect, useRef } from 'react';

/** `onKey` for each key pressed in the window, as the last render gave it: it reads that render's state without listening
 * again. */
export function useKeydown(onKey: (event: KeyboardEvent) => void) {
  const latest = useRef(onKey);
  latest.current = onKey;
  useEffect(() => {
    const listen = (event: KeyboardEvent) => latest.current(event);
    window.addEventListener('keydown', listen);
    return () => window.removeEventListener('keydown', listen);
  }, []);
}
