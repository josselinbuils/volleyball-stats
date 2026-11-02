import { useSyncExternalStore } from 'react';
import { match, versioned } from '@/lib/match';

/** The commentary's audio: `lines` by time [seconds, file, length], and what a replay says by the name of who it follows. */
export interface Recorded {
  lines: [number, string, number][];
  replay: Record<string, string>;
}

declare global {
  interface Window {
    MATCH_VOICE?: Recorded;
  }
}

let recorded: Recorded | null = null;
let started = false;
const listeners = new Set<() => void>();

/** Loads voice/index.js once, when the voice is first turned on. */
export function loadVoice() {
  if (started || !match.voice) {
    return;
  }
  started = true;
  const script = document.createElement('script');
  script.src = versioned('voice/index.js');
  script.onload = () => {
    recorded = window.MATCH_VOICE ?? null;
    listeners.forEach((listener) => listener());
  };
  script.onerror = () => {
    started = false;
  };
  document.head.append(script);
}

export function useRecorded(): Recorded | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => recorded,
  );
}

/** The line starting within `window` seconds before `time`. */
export function lineStarting(lines: Recorded['lines'], time: number, window: number): Recorded['lines'][number] | undefined {
  return lines.findLast(([t]) => t <= time && time - t < window);
}
