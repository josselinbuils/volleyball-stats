import { useSyncExternalStore } from 'react';
import { match, versioned } from '@/lib/match';

/** Player feet sampled every `step` frames from frame 0, each sample a flat [person, x, y, ...] list. */
export interface Players {
  step: number;
  samples: number[][];
}

/** players.js's positions: `chunks` of samples, each a JSON string of the samples' persons and each one's
 * move in cm since their last position, x then y. */
export interface PackedPlayers {
  step: number;
  chunks: string[];
}

declare global {
  interface Window {
    MATCH_PLAYERS?: PackedPlayers;
  }
}

/** Moves from a person's last position in cm: `x` and `y` by person. */
export interface Last {
  x: number[];
  y: number[];
}

/** Adds one of players.js's `chunk`s to `samples`, from the positions in `last`. */
export function unpackChunk(chunk: string, last: Last, samples: number[][]): void {
  const [persons, xs, ys] = JSON.parse(chunk) as [number[][], number[][], number[][]];
  for (let k = 0; k < persons.length; k++) {
    const flat: number[] = [];
    for (let n = 0; n < persons[k].length; n++) {
      const person = persons[k][n];
      last.x[person] = (last.x[person] ?? 0) + xs[k][n];
      last.y[person] = (last.y[person] ?? 0) + ys[k][n];
      flat.push(person, last.x[person] / 100, last.y[person] / 100);
    }
    samples.push(flat);
  }
}

// The time in ms the page keeps unpacking before letting the browser work.
const UNPACK_MS = 8;

/** Unpacks `packed` a few chunks at a time, leaving the page responsive, then calls `done`. */
function unpackAll(packed: PackedPlayers, done: (players: Players) => void) {
  const samples: number[][] = [];
  const last: Last = { x: [], y: [] };
  let k = 0;
  // Unlike a timeout, a message is not slowed down in a background tab.
  const channel = new MessageChannel();
  channel.port1.onmessage = () => {
    const until = performance.now() + UNPACK_MS;
    while (k < packed.chunks.length && performance.now() < until) {
      unpackChunk(packed.chunks[k++], last, samples);
    }
    if (k < packed.chunks.length) {
      channel.port2.postMessage(null);
    } else {
      channel.port1.close();
      done({ step: packed.step, samples });
    }
  };
  channel.port2.postMessage(null);
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
  script.onload = () => {
    const packed = window.MATCH_PLAYERS;
    window.MATCH_PLAYERS = undefined;
    if (packed) {
      unpackAll(packed, settle);
    } else {
      settle('none');
    }
  };
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
