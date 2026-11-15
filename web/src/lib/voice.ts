import { useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { match, versioned } from '@/lib/match';

/** The commentary's audio: `lines` by time [seconds, file, length, words as shown], and what a replay says by the name of
 * who it follows. */
export interface Recorded {
  lines: [number, string, number, string?][];
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

/** Whether the commentary is heard, as last chosen in this browser; at first, where the match's own voice speaks the page's language. */
const ON_KEY = 'commentary';
let chosen: boolean | null = (() => {
  try {
    const saved = localStorage.getItem(ON_KEY);
    return saved === null ? null : saved === '1';
  } catch {
    return null;
  }
})();
const switched = new Set<() => void>();

/** Whether the match's recorded voice speaks `language`: else the browser's voice reads the lines. */
export const recordedIn = (language: string) => match.voice && language === 'fr';

export function setCommentary(on: boolean) {
  chosen = on;
  try {
    localStorage.setItem(ON_KEY, on ? '1' : '0');
  } catch {
    // Kept for this page only.
  }
  switched.forEach((listener) => listener());
}

export function useCommentary(): boolean {
  const { i18n } = useTranslation();
  const on = useSyncExternalStore(
    (listener) => {
      switched.add(listener);
      return () => {
        switched.delete(listener);
      };
    },
    () => chosen,
  );
  return on ?? recordedIn(i18n.language);
}
