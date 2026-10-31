import { useSyncExternalStore } from 'react';
import { match, versioned } from '@/lib/match';

/** The ball's place where it is seen in the rallies: flat [frame, x, y, ...] samples, x and y
 * fractions of the picture. */
export interface Ball {
  fps: number;
  samples: number[];
}

declare global {
  interface Window {
    MATCH_BALL?: Ball;
  }
}

/** `loading` until ball.js has run, `none` without it (a page without the video). */
type State = Ball | 'idle' | 'loading' | 'none';

let state: State = match.video ? 'idle' : 'none';
const listeners = new Set<() => void>();

function settle(next: State) {
  state = next;
  listeners.forEach((listener) => listener());
}

/** Loads ball.js once, when the video first zooms on the ball. */
export function loadBall() {
  if (state !== 'idle') {
    return;
  }
  settle('loading');
  const script = document.createElement('script');
  script.src = versioned('ball.js');
  script.onload = () => settle(window.MATCH_BALL ?? 'none');
  script.onerror = () => settle('none');
  document.head.append(script);
}

export function useBall(): State {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => state,
  );
}
