import { useSyncExternalStore } from 'react';
import { match, versioned } from '@/lib/match';
import type { Point3 } from '@/components/Watch/helpers/flight';

declare global {
  interface Window {
    /** Each touch's 3D place: flat [index in the contacts, x, y, height, ...]. */
    MATCH_BALL3D?: number[];
  }
}

let places: Map<number, Point3> | null = null;
let started = false;
const listeners = new Set<() => void>();

/** Loads ball3d.js once, when a 3D view first shows. A touch without a place keeps its action's typical height. */
export function loadBall3d() {
  if (started || !match.ball3d) {
    return;
  }
  started = true;
  const script = document.createElement('script');
  script.src = versioned('ball3d.js');
  script.onload = () => {
    const flat = window.MATCH_BALL3D ?? [];
    const found = new Map<number, Point3>();
    for (let k = 0; k + 3 < flat.length; k += 4) {
      found.set(flat[k], { x: flat[k + 1], y: flat[k + 2], h: flat[k + 3] });
    }
    places = found;
    listeners.forEach((listener) => listener());
  };
  script.onerror = () => {
    started = false;
  };
  document.head.append(script);
}

/** The touches' 3D places by index in the contacts, null until loaded. */
export function useBall3d(): Map<number, Point3> | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    () => places,
  );
}
