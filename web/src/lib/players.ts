import { useSyncExternalStore } from 'react';
import { match, versioned } from '@/lib/match';

/** Player feet sampled every `step` frames from frame 0, each sample a flat [person, x, y, ...] list, only
 * those of the files loaded so far. */
export interface Players {
  step: number;
  samples: number[][];
}

/** A file of positions: its samples' count, then per person the runs of samples they are away and there, in turn, and their
 * moves since their last position in the file, in the match's `cm`. */
type Packed = [number, [number, number[], number[], number[]][]];

declare global {
  interface Window {
    MATCH_POSITIONS?: (file: number, packed: Packed) => void;
  }
}

// From this close to a file's end, in seconds, the next one loads too.
const AHEAD_S = 10;

/** Puts a file's samples in `samples`, the `file`th of `every` samples each, its moves in `cm`. */
export function unpackFile(samples: number[][], every: number, file: number, [count, columns]: Packed, cm: number): void {
  const flats = Array.from({ length: count }, () => [] as number[]);
  for (const [person, runs, xs, ys] of columns) {
    let k = 0;
    let move = 0;
    let [x, y] = [0, 0];
    runs.forEach((run, n) => {
      if (n % 2) {
        for (const end = k + run; k < end; k++, move++) {
          x += xs[move];
          y += ys[move];
          flats[k].push(person, (x * cm) / 100, (y * cm) / 100);
        }
      } else {
        k += run;
      }
    });
  }
  flats.forEach((flat, k) => {
    samples[file * every + k] = flat;
  });
}

/** The files to have at `time`: the one holding it, and the next near its end. None past the last. */
export function filesAt(time: number, seconds: number, files: number): number[] {
  const file = Math.floor(time / seconds);
  return [file, ...(time - file * seconds >= seconds - AHEAD_S ? [file + 1] : [])].filter((n) => n >= 0 && n < files);
}

const positions = match.positions;
/** `none` when the match has no player positions. */
type State = Players | 'none';

let state: State = positions ? { step: positions.step, samples: [] } : 'none';
const asked = new Set<number>();
const listeners = new Set<() => void>();

if (positions) {
  window.MATCH_POSITIONS = (file, packed) => {
    if (typeof state === 'object') {
      unpackFile(state.samples, positions.every, file, packed, positions.cm);
      state = { ...state };
      listeners.forEach((listener) => listener());
    }
  };
}

const fileSeconds = () => (positions ? (positions.every * positions.step) / match.fps : 1);

/** What the positions to have at `time` are named by, to load them when it changes. */
export const filesKey = (time: number) => (positions ? filesAt(time, fileSeconds(), positions.files).join() : '');

/** Loads the positions' files for `time` not asked for yet, as classic scripts: they work from file://. */
export function loadPlayersAt(time: number) {
  if (!positions) {
    return;
  }
  for (const file of filesAt(time, fileSeconds(), positions.files)) {
    if (!asked.has(file)) {
      asked.add(file);
      const script = document.createElement('script');
      script.src = versioned(`positions/${file}.js`);
      // Asked again the next time that moment plays.
      script.onerror = () => asked.delete(file);
      document.head.append(script);
    }
  }
}

/** Whether the positions at `time` exist but have not arrived yet. */
export function positionsPending(time: number): boolean {
  if (!positions || typeof state !== 'object') {
    return false;
  }
  const sample = Math.round((time * match.fps) / positions.step);
  return sample < positions.every * positions.files && state.samples[sample] === undefined;
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
