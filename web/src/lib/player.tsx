import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import type { TFunction } from 'i18next';
import type { Clock } from '@/lib/clock';
import { rallies, type Rally } from '@/lib/match';
import { PAD, rallyAt, type Clip } from '@/lib/playlist';

/** What plays the moments: the video, or the clock replaying the court when the page has none. */
export type Media = HTMLVideoElement | Clock;

/** Clips played one after another, each stopping at its end. */
export interface Playlist {
  title: (t: TFunction) => string;
  clips: Clip[];
  at: number;
}

interface Player {
  playlist: Playlist | null;
  play: (title: Playlist['title'], clips: Clip[], at?: number) => void;
  go: (at: number) => void;
  /** Leaves the playlist and pauses the video. */
  stop: () => void;
  /** Replays the clip playing, or the rally the video is in, instead of moving on past its end. */
  loop: boolean;
  setLoop: (loop: boolean) => void;
  video: Media | null;
  setVideo: (video: Media | null) => void;
}

const PlayerContext = createContext<Player | null>(null);

/** Seconds the video fades through black, picture and sound, out before and in after each jump of ours: the next clip, a loop's start. */
const FADE_S = 0.3;

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

/** Moves `media` to `time`. A video loads nothing before it is first played or moved; from then it
 * buffers ahead of where it stands, even paused, so playing starts at once. */
export function seek(media: Media, time: number): void {
  if (media instanceof HTMLVideoElement) {
    media.preload = 'auto';
  }
  media.currentTime = time;
}

/** Plays the video if paused, else pauses it. */
export function togglePlay(video: Media | null): void {
  if (video?.paused) {
    video.play().catch(() => {});
  } else {
    video?.pause();
  }
}

export function usePlayer(): Player {
  const player = useContext(PlayerContext);
  if (!player) {
    throw new Error('usePlayer needs a PlayerProvider');
  }
  return player;
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const [video, setVideo] = useState<Media | null>(null);
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [loop, setLoop] = useState(false);
  const looping = useRef(false);
  // The playlist for the loop and the event handlers, ahead of the next render.
  const current = useRef<Playlist | null>(null);
  // A seek of ours is pending: clip ends and user seeks are ignored until it lands.
  const seeking = useRef(false);
  // Where our last seek landed, the video fading in from there.
  const landed = useRef(-Infinity);

  const update = useCallback((next: Playlist | null) => {
    current.current = next;
    seeking.current = next !== null;
    setPlaylist(next);
  }, []);

  const play = useCallback<Player['play']>(
    (title, clips, at = 0) => {
      if (!clips.length) {
        return;
      }
      update({ title, clips, at });
      // The box holding the video and its controls, not the video, scaled by the zoom past that box. Only the page
      // scrolls: scrollIntoView would also scroll that box's hidden overflow, moving the controls inside it.
      const box = video?.parentElement?.getBoundingClientRect();
      if (box && (box.top < 0 || box.bottom > innerHeight)) {
        const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;
        scrollTo({ top: scrollY + box.top + (box.height - innerHeight) / 2, behavior: smooth ? 'smooth' : 'auto' });
      }
    },
    [video, update],
  );
  const go = useCallback(
    (at: number) => {
      if (current.current) {
        update({ ...current.current, at });
      }
    },
    [update],
  );
  const stop = useCallback(() => {
    video?.pause();
    update(null);
  }, [video, update]);

  useEffect(() => {
    looping.current = loop;
  }, [loop]);

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
    // The rally the video was in at the last frame.
    let held: Rally | undefined;
    const onSeeked = () => {
      const p = current.current;
      // The user's own seek outside the clip leaves the playlist.
      if (!seeking.current && p) {
        const clip = p.clips[p.at];
        if (video.currentTime < clip.start - 0.5 || video.currentTime > clip.end) {
          update(null);
        }
      }
      if (seeking.current) {
        landed.current = video.currentTime;
      }
      seeking.current = false;
      held = rallyAt(rallies, video.currentTime);
    };
    let frame = 0;
    // One loop ends the clips and publishes the video time.
    const tick = () => {
      const p = current.current;
      const time = video.currentTime;
      const playing = !video.seeking && !video.paused;
      // A seek past the clip's end is the user's, left to onSeeked.
      if (p && !seeking.current && playing && time >= p.clips[p.at].end) {
        if (looping.current) {
          update({ ...p });
        } else if (p.at + 1 < p.clips.length) {
          update({ ...p, at: p.at + 1 });
        } else {
          video.pause();
          update(null);
        }
      }
      if (!p && looping.current && playing && held && time > held.end + PAD) {
        seeking.current = true;
        video.currentTime = Math.max(0, held.start - PAD);
      } else {
        held = rallyAt(rallies, time);
      }
      if (video instanceof HTMLVideoElement) {
        const q = current.current;
        const jump = q ? (looping.current || q.at + 1 < q.clips.length ? q.clips[q.at].end : Infinity) : looping.current && held ? held.end + PAD : Infinity;
        const fadeOut = time <= jump ? (jump - time) / FADE_S : 1;
        const fadeIn = time >= landed.current ? (time - landed.current) / FADE_S : 1;
        const shown = seeking.current ? 0 : Math.min(1, fadeOut, fadeIn);
        video.style.opacity = shown < 1 ? String(shown) : '';
        if (video.volume !== shown) {
          video.volume = shown;
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

  const value = useMemo(() => ({ playlist, play, go, stop, loop, setLoop, video, setVideo }), [playlist, play, go, stop, loop, video]);
  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}
