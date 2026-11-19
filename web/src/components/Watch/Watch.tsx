import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { LoaderCircle, Lock, Play, ZoomOut } from 'lucide-react';
import { VideoError } from '@/components/VideoError';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { loadVideoData, useVideoData } from '@/lib/video';
import { useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
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
import { useLayout } from '@/components/Watch/LayoutMenu';
import { BELOW_TOWER, Overlay, SCORED, type Paint } from '@/components/Watch/Overlay';
import { askVideo } from '@/components/VideoChoice';
import { cameraAt, throughCut, zoomOn } from '@/components/Watch/helpers/zoom';
import { useHandZoom } from '@/components/Watch/useHandZoom';
import { useAutoHide } from '@/components/Watch/useAutoHide';

const UNZOOMED = { scale: 1, x: 0, y: 0 };
// Whether the video shows the ball's trail, the score and the measured numbers, kept in this browser: shown unless turned off.
const DRAWN_KEY = 'videoOverlay';

function savedDrawn(): boolean {
  try {
    return localStorage.getItem(DRAWN_KEY) !== '0';
  } catch {
    return true;
  }
}
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
// A wait this long with nothing more loaded is stuck: the video reloads where it stands, each try twice as long after the
// last (asking again for that moment waits on the same stuck request: a request held 60 s, 15 Nov).
const STUCK_MS = 2500;
const STUCK_MOST_MS = 20000;

export function Watch() {
  const { t } = useTranslation();
  const f = useFormat();
  const { video, setVideo, playlist } = usePlayer();
  const pause = useVideoTime(timeoutAt);
  const court = useRef<HTMLDivElement>(null);
  // The automatic zoom (framing.camera, in video.js), close calls' bounces included: the hosted copies come cut by it
  // (`match.zoomed`); the source on this machine, or copies made before 16 Nov, are zoomed by it here.
  const ball = useVideoData();
  // What the pipeline knows drawn on the video (`Overlay`), by the zoom's loop: the two move as one.
  const [drawn, setDrawn] = useState(savedDrawn);
  const toggleDrawn = () => {
    setDrawn(!drawn);
    try {
      localStorage.setItem(DRAWN_KEY, drawn ? '0' : '1');
    } catch {
      // Kept for this page only.
    }
  };
  const paint = useRef<Paint>(null);
  // The zoom by hand, over the automatic one.
  const hand = useHandZoom(video instanceof HTMLVideoElement ? video : null);
  const zoomed = hand.zoom.scale > 1;
  useEffect(() => {
    if (drawn || !match.zoomed) {
      loadVideoData();
    }
  }, [drawn]);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement)) {
      return;
    }
    const camera = typeof ball === 'object' ? (ball.camera ?? []) : [];
    const zooming = camera.length > 0 && !match.zoomed;
    let frame = 0;
    const tick = () => {
      const view = cameraAt(zooming ? camera : [], video.currentTime);
      const [width, height] = [video.clientWidth, video.clientHeight];
      const auto = view.zoom < 1.0005 || !video.videoWidth ? UNZOOMED : zoomOn(view, width, height, video.videoWidth, video.videoHeight, view.zoom);
      const z = hand.current.current;
      const byHand = { scale: z.scale, x: z.x * width, y: z.y * height };
      const css = { scale: byHand.scale * auto.scale, x: byHand.scale * auto.x + byHand.x, y: byHand.scale * auto.y + byHand.y };
      if (css.scale === 1) {
        video.style.transform = '';
      } else {
        video.style.transformOrigin = '0 0';
        video.style.transform = `translate(${css.x}px, ${css.y}px) scale(${css.scale})`;
      }
      // What is drawn follows the picture: on a cut copy, the cut of the frame shown.
      paint.current?.(match.zoomed ? (at) => throughCut(byHand, cameraAt(camera, at), width, height, video.videoWidth, video.videoHeight) : () => css);
      // Nothing to zoom nor draw: the loop stops.
      if (!zooming && !drawn && !zoomed) {
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [video, ball, drawn, zoomed]);
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
  // The 720p copy while the player is small; the 1440p one in full screen or wide, or zoomed here (copies made before the
  // zoom was cut in them).
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement)) {
      return;
    }
    const observer = new ResizeObserver(() => setWide(video.clientWidth * devicePixelRatio > WIDE_PX));
    observer.observe(video);
    return () => observer.disconnect();
  }, [video]);
  const src = match.small && match.zoomed && !full && !wide ? match.small : BIG;
  // Full screen: the video fills the screen, its controls over it hiding when still, as what else sits on it.
  const player = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  const controls = useAutoHide(full, player, bar, video instanceof HTMLVideoElement ? video : null);
  const hidden = !controls.shown;
  const fade = cn('transition-opacity duration-300', hidden && 'pointer-events-none opacity-0');
  // Whether the video was touched rather than clicked: a tap shows or hides full screen's controls.
  const touch = useRef(false);
  // The bar's height, which the replay in the corner rises over while it shows.
  const [barHeight, setBarHeight] = useState(0);
  useEffect(() => {
    const element = bar.current;
    if (!full || !element) {
      return;
    }
    const observer = new ResizeObserver(() => setBarHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, [full]);
  // Full screen shows the court's replay beside the video or in its corner, as chosen. The same replay moves there from
  // the page (its 3D view kept, not drawn again), its place in the page keeping its height meanwhile.
  const [layout, setLayout] = useLayout();
  const courtFull = full && layout !== 'video';
  const [host] = useState(() => {
    const div = document.createElement('div');
    div.style.display = 'contents';
    return div;
  });
  const slot = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const place = slot.current;
    const target = courtFull ? panel.current : place;
    if (!place || !target) {
      return;
    }
    place.style.minHeight = courtFull ? `${place.offsetHeight}px` : '';
    target.appendChild(host);
  }, [courtFull, layout, host]);
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
              <div className="relative p-3 pb-2 [:fullscreen>&]:min-h-0 [:fullscreen>&]:flex-1 [:fullscreen>&]:p-0">
                <Replay captioned={false} />
                <PlayCue />
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
              {/* Full screen takes the video with its controls, and the court's replay as chosen. */}
              <div
                ref={player}
                data-player
                className={cn('relative overflow-hidden rounded-lg bg-black [&:fullscreen]:flex [&:fullscreen]:flex-col [&:fullscreen]:rounded-none', hidden && 'cursor-none [&_*]:cursor-none')}
              >
                {/* Beside the video, under it on a screen held upright (both centred); else in its bottom right corner. */}
                <div className={cn('relative [:fullscreen>&]:flex [:fullscreen>&]:min-h-0 [:fullscreen>&]:flex-1', courtFull && layout === 'side' && 'portrait:flex-col portrait:justify-center')}>
                  {/* The video's own box: the zoom stays inside it. */}
                  <div
                    className={cn(
                      'relative overflow-hidden [:fullscreen_&]:min-h-0 [:fullscreen_&]:min-w-0 [:fullscreen_&]:flex-[3]',
                      courtFull && layout === 'side' && '[:fullscreen_&]:portrait:flex-none',
                    )}
                  >
                    {full && <Feedback className={fade} />}
                    {/* Zoomed by hand: back to the whole picture, under Signaler. */}
                    {zoomed && (
                      <button
                        type="button"
                        onClick={hand.reset}
                        className={cn(
                          fade,
                          'absolute right-2 z-10 inline-flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm outline-none hover:bg-black/75 focus-visible:ring-3 focus-visible:ring-white/60',
                          match.feedback ? 'top-11.5' : 'top-2',
                        )}
                      >
                        <ZoomOut aria-hidden className="size-4" />
                        {t('zoomOutView')}
                      </button>
                    )}
                    {!LOCAL && playlist && reached === playlist.clips && playlist.at + 1 < playlist.clips.length && <Preload src={src} clips={playlist.clips} at={playlist.at} />}
                    {/* What plays, over the video: the bar below is out of sight from the stats and in full screen; else a timeout. */}
                    {(playlist || pause) && (
                      <span
                        aria-hidden
                        className={cn(
                          fade,
                          'pointer-events-none absolute top-2 left-2 z-10 max-w-[calc(100%-8.5rem)] truncate rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm',
                          drawn && SCORED && typeof ball === 'object' && BELOW_TOWER,
                        )}
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
                      onPointerDown={(e) => (touch.current = e.pointerType !== 'mouse')}
                      onClick={() => (full && touch.current ? controls.tapped() : togglePlay(video))}
                      className={cn(
                        'block aspect-video w-full [:fullscreen_&]:aspect-auto [:fullscreen_&]:h-full',
                        zoomed ? 'cursor-grab touch-none active:cursor-grabbing' : 'cursor-pointer touch-pan-x touch-pan-y',
                        courtFull && layout === 'side' && '[:fullscreen_&]:portrait:aspect-video [:fullscreen_&]:portrait:h-auto',
                      )}
                    />
                    {drawn && video instanceof HTMLVideoElement && typeof ball === 'object' && <Overlay video={video} ball={ball} paint={paint} />}
                    <PlayCue />
                    {video instanceof HTMLVideoElement && <Buffering video={video} />}
                    {video instanceof HTMLVideoElement && <VideoError video={video} />}
                  </div>
                  {/* Dark as the video around it, in a 16/10 box: centred beside the video, or that box in its corner. */}
                  {courtFull && (
                    <div
                      className={cn(
                        'dark text-foreground',
                        layout === 'side' ? 'flex min-h-0 min-w-0 flex-[2] flex-col justify-center portrait:flex-none' : 'absolute right-3 z-[5] w-[30%] min-w-60 transition-[bottom] duration-300',
                      )}
                      style={layout === 'side' ? undefined : { bottom: `calc(${hidden ? 0 : barHeight}px + 0.75rem)` }}
                    >
                      <div ref={panel} className={cn('relative aspect-[16/10] w-full overflow-hidden bg-background', layout === 'inset' && 'rounded-lg shadow-lg ring-1 ring-white/20')} />
                    </div>
                  )}
                </div>
                {/* Full screen: over the picture's bottom, on a shade for the white to read. */}
                <div ref={bar} className={cn(full && 'absolute inset-x-0 bottom-0 z-10', full && fade)}>
                  {full && <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-[calc(100%+3rem)] bg-linear-to-t from-black/75 to-transparent" />}
                  <VideoControls over={full} drawn={drawn} onDrawn={ball === 'none' ? undefined : toggleDrawn} layout={layout} onLayout={setLayout} />
                </div>
              </div>
            </div>
            <PlaylistBar />
          </div>
          {/* In the sheet too, under the player on a phone: what plays, to pick from. */}
          <div className="min-w-0 lg:order-last lg:col-span-2 lg:mt-2">
            <RallyCards />
          </div>
          <div ref={slot} className="min-w-0" />
          {createPortal(<Replay />, host)}
        </PlayerSheet>
      </CardContent>
    </Card>
  );
}

/** Over a playlist started from elsewhere on the page, waiting at its start: a tap anywhere on the picture plays it. */
function PlayCue() {
  const { t } = useTranslation();
  const { waiting, video } = usePlayer();
  if (!waiting) {
    return null;
  }
  return (
    <button type="button" onClick={() => video?.play().catch(() => {})} className="group absolute inset-0 z-[5] grid cursor-pointer place-items-center outline-none">
      <span className="inline-flex items-center gap-2 rounded-full bg-black/60 px-5 py-3 text-base font-semibold text-white backdrop-blur-sm group-hover:bg-black/75 group-focus-visible:ring-3 group-focus-visible:ring-white/60">
        <Play aria-hidden className="size-6 fill-current" />
        {t('playCue')}
      </span>
    </button>
  );
}

/** Whether `video` waits for data, to play on or to show the moment it moved to. */
const waits = (video: HTMLVideoElement) => !video.error && (video.seeking || (!video.paused && video.readyState < HTMLMediaElement.HAVE_FUTURE_DATA));

/** The seconds `video` holds from where it stands on. */
function heldAhead(video: HTMLVideoElement): number {
  const { buffered, currentTime } = video;
  for (let k = 0; k < buffered.length; k += 1) {
    if (buffered.start(k) <= currentTime + 0.1 && currentTime <= buffered.end(k)) {
      return buffered.end(k) - currentTime;
    }
  }
  return 0;
}

/** Gets `video` going again when a wait for its data makes no progress (a browser's request can hang, mostly after a
 * jump): it reloads the copy there, its speed and play kept. */
function useUnstuck(video: HTMLVideoElement) {
  useEffect(() => {
    // Since when the wait made no progress, what it held then, and the tries made in it.
    let since = 0;
    let held = -1;
    let tries = 0;
    // A new jump is a new wait.
    const restart = () => {
      since = performance.now();
      held = -1;
    };
    const timer = window.setInterval(() => {
      if (!waits(video)) {
        tries = 0;
        restart();
        return;
      }
      const ahead = heldAhead(video);
      if (ahead > held + 0.05) {
        since = performance.now();
        held = ahead;
        return;
      }
      if (performance.now() - since < Math.min(STUCK_MOST_MS, STUCK_MS * 2 ** tries)) {
        return;
      }
      const { currentTime, paused, playbackRate } = video;
      video.load();
      video.currentTime = currentTime;
      video.playbackRate = playbackRate;
      if (!paused) {
        video.play().catch(() => {});
      }
      tries += 1;
      restart();
    }, 250);
    video.addEventListener('seeking', restart);
    return () => {
      window.clearInterval(timer);
      video.removeEventListener('seeking', restart);
    };
  }, [video]);
}

/** A spinner over `video` while it waits for data, getting it going again when that wait is stuck. */
function Buffering({ video }: { video: HTMLVideoElement }) {
  const { t } = useTranslation();
  const { waiting } = usePlayer();
  const [shown, setShown] = useState(false);
  useUnstuck(video);
  useEffect(() => {
    let timer = 0;
    const check = () => {
      window.clearTimeout(timer);
      if (waits(video)) {
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
  // Under the cue to play, nothing more.
  if (!shown || waiting) {
    return null;
  }
  // Over the picture, in the video's own box.
  return (
    <div role="status" aria-label={t('videoLoading')} className="pointer-events-none absolute inset-0 grid place-items-center">
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
