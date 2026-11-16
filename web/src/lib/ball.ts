import { useSyncExternalStore } from 'react';
import { match, versioned } from '@/lib/match';

/** The ball's place where it is seen in the rallies: flat [seconds, x, y, ...] samples, x and y
 * fractions of the picture, by time; and the automatic zoom's camera (framing.camera_spans, `cameraAt`). */
export interface Ball {
  samples: number[];
  camera?: number[][];
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

/** Loads ball.js once, when the video first zooms (the source) or draws on itself. */
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
