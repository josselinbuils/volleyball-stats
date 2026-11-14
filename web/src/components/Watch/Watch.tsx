import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { LoaderCircle, Lock } from 'lucide-react';
import { VideoError } from '@/components/VideoError';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { loadBall, useBall } from '@/lib/ball';
import { useFormat } from '@/lib/format';
import { match, timeoutAt, timeoutLabel } from '@/lib/match';
import { Clock } from '@/lib/clock';
import { togglePlay, usePlayer, useVideoTime } from '@/lib/player';
import type { Clip } from '@/lib/playlist';
import { Feedback } from '@/components/Watch/Feedback';
import { PlayerSheet } from '@/components/Watch/PlayerSheet';
import { PlaylistBar } from '@/components/Watch/PlaylistBar';
import { RallyCards } from '@/components/Watch/RallyCards';
import { Replay, ReplayCaption } from '@/components/Watch/Replay';
import { Scoreboard } from '@/components/Watch/Scoreboard';
import { VideoControls } from '@/components/Watch/VideoControls';
import { askVideo } from '@/components/VideoChoice';
import { smoothFrameAt, spring, zoomOn } from '@/components/Watch/helpers/zoom';

// A jump in the video this long cuts to its view: no pan across the court.
const CUT_S = 0.5;
const WHOLE = { x: 0.5, y: 0.5, zoom: 1 };
// What web.py's --av1-video takes: 1440p, 8-bit, level 5.0; a browser that cannot play it takes the H.264 copy.
const AV1 = 'video/mp4; codecs="av01.0.12M.08"';
const BIG = match.av1 && document.createElement('video').canPlayType(AV1) ? match.av1 : match.video;
// Wider than this on the screen (in its pixels), the 720p copy would be stretched: the player takes the 1440p one.
const WIDE_PX = 1600;
// A playlist's clips loaded ahead of the one playing, one after another.
const AHEAD = 3;
// The page served from this machine (the review, or opened from the disk): its video comes at once, nothing to preload.
const LOCAL = ['localhost', '127.0.0.1', '[::1]', ''].includes(location.hostname);
// How often the playlist's hidden copy checks whether it holds the clip it loads.
const PRELOAD_MS = 250;
// A wait for the video's data shorter than this shows nothing.
const BUFFERING_MS = 300;

export function Watch() {
  const { t } = useTranslation();
  const f = useFormat();
  const { video, setVideo, playlist } = usePlayer();
  const pause = useVideoTime(timeoutAt);
  const court = useRef<HTMLDivElement>(null);
  // The automatic zoom, on from the start where the match has views, frames the players as the review does, moving only
  // to keep the ball in, looking a second ahead and behind; the view springs to it each frame, back to the whole picture when off.
  const [follow, setFollow] = useState(match.views.length > 0);
  const ball = useBall();
  const camera = useRef({ now: { ...WHOLE }, speed: { x: 0, y: 0, zoom: 0 } });
  useEffect(() => {
    if (follow) {
      loadBall();
    }
  }, [follow]);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement)) {
      return;
    }
    const { now, speed } = camera.current;
    let frame = 0;
    let last = performance.now();
    let shown = video.currentTime;
    const tick = (stamp: number) => {
      const dt = Math.min(0.05, Math.max(0, stamp - last) / 1000);
      last = stamp;
      const time = video.currentTime;
      const target = follow ? smoothFrameAt(match.views, time, typeof ball === 'object' ? ball : null) : WHOLE;
      if (Math.abs(time - shown) > CUT_S) {
        Object.assign(now, target);
        Object.assign(speed, { x: 0, y: 0, zoom: 0 });
      }
      shown = time;
      spring(now, speed, target, dt);
      if (!follow && Math.abs(now.zoom - 1) < 0.002) {
        Object.assign(now, WHOLE);
        Object.assign(speed, { x: 0, y: 0, zoom: 0 });
        video.style.transform = '';
        return;
      }
      if (video.videoWidth) {
        const v = zoomOn(now, video.clientWidth, video.clientHeight, video.videoWidth, video.videoHeight, Math.max(1, now.zoom));
        video.style.transformOrigin = '0 0';
        video.style.transform = `translate(${v.x}px, ${v.y}px) scale(${v.scale})`;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [video, follow, ball]);
  // A playlist's next clips load once the video has reached its first one: both at once would
  // slow its start.
  const [reached, setReached] = useState<Clip[] | null>(null);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement) || !playlist) {
      return;
    }
    const on = () => setReached(playlist.clips);
    video.addEventListener('seeked', on);
    return () => video.removeEventListener('seeked', on);
  }, [video, playlist]);
  // The report button sits over the video, its form free to run past it, but full screen shows only
  // the video's box: the button moves into it then.
  const [full, setFull] = useState(false);
  useEffect(() => {
    const sync = () => setFull(document.fullscreenElement !== null);
    document.addEventListener('fullscreenchange', sync);
    return () => document.removeEventListener('fullscreenchange', sync);
  }, []);
  // The 720p copy while the player is small; the 1440p one in full screen, zoomed or wide.
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement)) {
      return;
    }
    const observer = new ResizeObserver(() => setWide(video.clientWidth * devicePixelRatio > WIDE_PX));
    observer.observe(video);
    return () => observer.disconnect();
  }, [video]);
  const src = match.small && !full && !follow && !wide ? match.small : BIG;
  // A copy taking over carries on where the video stands, playing if it was.
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement) || !src || video.getAttribute('src') === src) {
      return;
    }
    const { readyState, currentTime, paused } = video;
    video.src = src;
    if (readyState > 0) {
      video.preload = 'auto';
      video.currentTime = currentTime;
      if (!paused) {
        video.play().catch(() => {});
      }
    }
  }, [video, src]);
  // Without a video, a clock plays the moments on the court's top view.
  useEffect(() => {
    if (match.video || !court.current) {
      return;
    }
    const clock = new Clock(court.current, match.duration);
    setVideo(clock);
    return () => {
      clock.pause();
      setVideo(null);
    };
  }, [setVideo]);

  if (!match.video) {
    return (
      <Card id="replay">
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">
              {t('replayTitle')}
              <SetBadge />
            </h2>
          </CardTitle>
          <CardDescription>{t('replayCaption')}</CardDescription>
          {match.videoPage && (
            <Button variant="outline" size="sm" className="tap relative mt-2 justify-self-start bg-card" onClick={askVideo}>
              <Lock aria-hidden />
              {t('videoPage')}
            </Button>
          )}
        </CardHeader>
        <CardContent className="grid gap-8">
          {/* Wide screens: the legend and the rally controls in a column beside the court. */}
          <PlayerSheet title={t('replayTitle')} className="mx-auto grid w-full max-w-3xl min-w-0 gap-3 lg:max-w-none lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-x-6">
            <Scoreboard />
            {/* Full screen: the view fills the screen above the controls, its title bar over it. */}
            <div ref={court} className="overflow-hidden lg:col-start-1 rounded-lg border bg-card [&:fullscreen]:flex [&:fullscreen]:flex-col [&:fullscreen]:rounded-none [&:fullscreen]:border-0">
              <div className="p-3 pb-2 [:fullscreen>&]:min-h-0 [:fullscreen>&]:flex-1 [:fullscreen>&]:p-0">
                <Replay captioned={false} />
              </div>
              <div className="border-t bg-muted">
                <VideoControls light />
              </div>
            </div>
            <div className="grid content-start gap-3 lg:col-start-2 lg:row-start-2">
              {/* Narrower, under the court: the playlist's controls first, in sight with it. */}
              <ReplayCaption className="max-lg:order-last lg:mt-0" />
              <PlaylistBar />
            </div>
            {/* In the sheet too: what plays, to pick from. */}
            <div className="mt-5 min-w-0 lg:col-span-2">
              <RallyCards />
            </div>
          </PlayerSheet>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card id="replay">
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('video')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t('videoCaption')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-8">
        <PlayerSheet title={t('video')} className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <Scoreboard />
            <div className="relative">
              {!full && <Feedback />}
              {/* Full screen takes the video with its controls. */}
              <div className="relative overflow-hidden rounded-lg bg-black [&:fullscreen]:flex [&:fullscreen]:flex-col [&:fullscreen]:rounded-none">
                {full && <Feedback />}
                {!LOCAL && playlist && reached === playlist.clips && playlist.at + 1 < playlist.clips.length && <Preload src={src} clips={playlist.clips} at={playlist.at} />}
                {/* What plays, over the video: the bar below is out of sight from the stats and in full screen; else a timeout. */}
                {(playlist || pause) && (
                  <span
                    aria-hidden
                    className="pointer-events-none absolute top-2 left-2 z-10 max-w-[calc(100%-8.5rem)] truncate rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm"
                  >
                    {playlist ? `${playlist.title(t)} · ${t('iOfN', { i: f.num(playlist.at + 1), n: f.num(playlist.clips.length) })}` : pause && timeoutLabel(t, pause)}
                  </span>
                )}
                {/* Nothing loads before the video is first played or moved (`seek`). */}
                <video
                  ref={setVideo}
                  poster={match.poster}
                  playsInline
                  preload="none"
                  aria-label={t('video')}
                  onClick={() => togglePlay(video)}
                  className="block aspect-video w-full cursor-pointer [:fullscreen>&]:aspect-auto [:fullscreen>&]:min-h-0 [:fullscreen>&]:flex-1"
                />
                {video instanceof HTMLVideoElement && <Buffering video={video} />}
                {video instanceof HTMLVideoElement && <VideoError video={video} />}
                <VideoControls follow={follow} onFollow={() => setFollow((f) => !f)} />
              </div>
            </div>
            <PlaylistBar />
          </div>
          {/* In the sheet too, under the player on a phone: what plays, to pick from. */}
          <div className="min-w-0 lg:order-last lg:col-span-2 lg:mt-2">
            <RallyCards />
          </div>
          <Replay />
        </PlayerSheet>
      </CardContent>
    </Card>
  );
}

/** A spinner over `video` while it waits for data, to play on or to show the moment it moved to. */
function Buffering({ video }: { video: HTMLVideoElement }) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(false);
  useEffect(() => {
    let timer = 0;
    const check = () => {
      window.clearTimeout(timer);
      if (!video.error && (video.seeking || (!video.paused && video.readyState < HTMLMediaElement.HAVE_FUTURE_DATA))) {
        timer = window.setTimeout(() => setShown(true), BUFFERING_MS);
      } else {
        setShown(false);
      }
    };
    const events = ['waiting', 'playing', 'canplay', 'seeking', 'seeked', 'play', 'pause', 'emptied', 'error'];
    events.forEach((e) => video.addEventListener(e, check));
    return () => {
      window.clearTimeout(timer);
      events.forEach((e) => video.removeEventListener(e, check));
    };
  }, [video]);
  if (!shown) {
    return null;
  }
  // Over the picture, the controls below it; in full screen over the whole screen.
  return (
    <div
      role="status"
      aria-label={t('videoLoading')}
      className="pointer-events-none absolute inset-x-0 top-0 grid aspect-video place-items-center [:fullscreen>&]:bottom-0 [:fullscreen>&]:aspect-auto"
    >
      <span className="rounded-full bg-black/60 p-2.5 text-white backdrop-blur-sm">
        <LoaderCircle aria-hidden className="size-8 animate-spin" />
      </span>
    </div>
  );
}

/** A hidden copy of the video (`src`, the copy playing) loading the starts of the AHEAD `clips` after `at` one after
 * another, each until the browser holds enough of it to play it; the same for the whole playlist, it remembers those
 * done. The browser keeps what it fetches for the video, which then jumps there without waiting. */
function Preload({ src, clips, at }: { src: string | null; clips: Clip[]; at: number }) {
  const ref = useRef<HTMLVideoElement>(null);
  const done = useRef(new Set<number>());
  useEffect(() => {
    done.current = new Set();
  }, [src]);
  useEffect(() => {
    const preload = ref.current;
    if (!preload) {
      return;
    }
    const ahead = clips.slice(at + 1, at + 1 + AHEAD).map((c) => c.start);
    const step = () => {
      const target = ahead.find((t) => !done.current.has(t));
      if (target === undefined) {
        return;
      }
      if (Math.abs(preload.currentTime - target) > 0.5) {
        preload.currentTime = target;
        return;
      }
      // Enough to play, or as much as the browser fetches for a video that does not play.
      const held = preload.readyState === HTMLMediaElement.HAVE_ENOUGH_DATA || (preload.readyState === HTMLMediaElement.HAVE_FUTURE_DATA && preload.networkState === HTMLMediaElement.NETWORK_IDLE);
      if (!preload.seeking && held) {
        done.current.add(target);
        step();
      }
    };
    step();
    const timer = window.setInterval(step, PRELOAD_MS);
    return () => window.clearInterval(timer);
  }, [clips, at, src]);
  return <video ref={ref} src={src ?? undefined} muted playsInline preload="auto" aria-hidden className="hidden" />;
}
