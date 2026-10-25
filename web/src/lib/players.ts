import { useSyncExternalStore } from 'react';
import { match, versioned } from '@/lib/match';

/** Player feet sampled every `step` frames from frame 0, each sample a flat [person, x, y, ...] list. */
export interface Players {
  step: number;
  samples: number[][];
}

declare global {
  interface Window {
    MATCH_PLAYERS?: Players;
  }
}

/** `loading` until players.js has run, `none` when the match has no player positions. */
type State = Players | 'loading' | 'none';

let state: State = Object.keys(match.people).length ? 'loading' : 'none';
let started = false;
const listeners = new Set<() => void>();

function settle(next: State) {
  state = next;
  listeners.forEach((listener) => listener());
}

/** Loads players.js, the players' positions over the whole video, as a classic script: it works
 * from file:// and stays out of the first render. */
export function loadPlayers() {
  if (started || state === 'none') {
    return;
  }
  started = true;
  const script = document.createElement('script');
  script.src = versioned('players.js');
  script.onload = () => settle(window.MATCH_PLAYERS ?? 'none');
  script.onerror = () => settle('none');
  document.head.append(script);
}

export function usePlayers(): State {
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
