import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import type { TFunction } from 'i18next';
import type { Clip } from '@/lib/playlist';

/** Clips played one after another, each stopping at its end. `key` names the control that started
 * it, to highlight it. */
export interface Playlist {
  title: (t: TFunction) => string;
  clips: Clip[];
  at: number;
  key?: string;
}

interface Player {
  playlist: Playlist | null;
  play: (title: Playlist['title'], clips: Clip[], at?: number, key?: string) => void;
  go: (at: number) => void;
  /** Leaves the playlist and pauses the video. */
  stop: () => void;
  setVideo: (video: HTMLVideoElement | null) => void;
}

const PlayerContext = createContext<Player | null>(null);

// ponytail: one video per page, so its time lives in a module-level store.
let now = 0;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** A value derived from the video time, re-rendering when it changes; `select` returns a primitive. */
export function useVideoTime<T>(select: (time: number) => T): T {
  return useSyncExternalStore(subscribe, () => select(now));
}

export function usePlayer(): Player {
  const player = useContext(PlayerContext);
  if (!player) {
    throw new Error('usePlayer needs a PlayerProvider');
  }
  return player;
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  // The playlist for the loop and the event handlers, ahead of the next render.
  const current = useRef<Playlist | null>(null);
  // A seek of ours is pending: clip ends and user seeks are ignored until it lands.
  const seeking = useRef(false);

  const update = useCallback((next: Playlist | null) => {
    current.current = next;
    seeking.current = next !== null;
    setPlaylist(next);
  }, []);

  const play = useCallback<Player['play']>(
    (title, clips, at = 0, key) => {
      if (!clips.length) {
        return;
      }
      update({ title, clips, at, key });
      const box = video?.getBoundingClientRect();
      if (video && box && (box.top < 0 || box.bottom > innerHeight)) {
        const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;
        video.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'center' });
      }
    },
    [video, update],
  );
  const go = useCallback((at: number) => {
    if (current.current) {
      update({ ...current.current, at });
    }
  }, [update]);
  const stop = useCallback(() => {
    video?.pause();
    update(null);
  }, [video, update]);

  // Every new playlist or clip seeks to the clip's start.
  useEffect(() => {
    if (video && playlist) {
      video.currentTime = playlist.clips[playlist.at].start;
      video.play().catch(() => {});
    }
  }, [video, playlist]);

  useEffect(() => {
    if (!video) {
      return;
    }
    const onSeeked = () => {
      const p = current.current;
      // The user's own seek outside the clip leaves the playlist.
      if (!seeking.current && p) {
        const clip = p.clips[p.at];
        if (video.currentTime < clip.start - 0.5 || video.currentTime > clip.end) {
          update(null);
        }
      }
      seeking.current = false;
    };
    let frame = 0;
    // One loop ends the clips and publishes the video time.
    const tick = () => {
      const p = current.current;
      const time = video.currentTime;
      // A seek past the clip's end is the user's, left to onSeeked.
      if (p && !seeking.current && !video.seeking && !video.paused && time >= p.clips[p.at].end) {
        if (p.at + 1 < p.clips.length) {
          update({ ...p, at: p.at + 1 });
        } else {
          video.pause();
          update(null);
        }
      }
      if (time !== now) {
        now = time;
        listeners.forEach((listener) => listener());
      }
      frame = requestAnimationFrame(tick);
    };
    video.addEventListener('seeked', onSeeked);
    tick();
    return () => {
      video.removeEventListener('seeked', onSeeked);
      cancelAnimationFrame(frame);
    };
  }, [video, update]);

  const value = useMemo(() => ({ playlist, play, go, stop, setVideo }), [playlist, play, go, stop]);
  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}
