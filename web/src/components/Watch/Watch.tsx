import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { loadBall, useBall } from '@/lib/ball';
import { useFormat } from '@/lib/format';
import { match } from '@/lib/match';
import { Clock } from '@/lib/clock';
import { togglePlay, usePlayer } from '@/lib/player';
import { Feedback } from '@/components/Watch/Feedback';
import { PlaylistBar } from '@/components/Watch/PlaylistBar';
import { RallyCards } from '@/components/Watch/RallyCards';
import { Replay, ReplayCaption } from '@/components/Watch/Replay';
import { Scoreboard } from '@/components/Watch/Scoreboard';
import { VideoControls } from '@/components/Watch/VideoControls';
import { askVideo } from '@/components/VideoChoice';
import { ballAt, zoomOn } from '@/components/Watch/helpers/zoom';

// Share of the way to the zoom's target covered each frame: the view follows the ball within a fifth of a second.
const EASE = 0.1;
// What web.py's --av1-video takes: 1080p, 8-bit, level 4.0; a browser that cannot play it takes the next source.
const AV1 = 'video/mp4; codecs="av01.0.08M.08"';

export function Watch() {
  const { t } = useTranslation();
  const f = useFormat();
  const { video, setVideo, playlist } = usePlayer();
  const court = useRef<HTMLDivElement>(null);
  // Zoomed on the ball, the view eases toward it each frame, back to the whole picture when off or
  // with no ball near.
  const [follow, setFollow] = useState(false);
  const ball = useBall();
  const view = useRef({ scale: 1, x: 0, y: 0 });
  useEffect(() => {
    if (follow) {
      loadBall();
    }
  }, [follow]);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement)) {
      return;
    }
    const now = view.current;
    let frame = 0;
    const tick = () => {
      const at = follow && typeof ball === 'object' ? ballAt(ball, video.currentTime) : null;
      const target = at && video.videoWidth ? zoomOn(at, video.clientWidth, video.clientHeight, video.videoWidth, video.videoHeight) : { scale: 1, x: 0, y: 0 };
      for (const k of ['scale', 'x', 'y'] as const) {
        now[k] += (target[k] - now[k]) * EASE;
      }
      if (!follow && Math.abs(now.scale - 1) < 0.002) {
        Object.assign(now, { scale: 1, x: 0, y: 0 });
        video.style.transform = '';
        return;
      }
      video.style.transformOrigin = '0 0';
      video.style.transform = `translate(${now.x}px, ${now.y}px) scale(${now.scale})`;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [video, follow, ball]);
  // A playlist's next clip loads once the video has reached the one it plays: both at once would
  // slow its start.
  const [reached, setReached] = useState<typeof playlist>(null);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement) || !playlist) {
      return;
    }
    const on = () => setReached(playlist);
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
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="text-lg font-semibold">
              {t('replayTitle')}
              <SetBadge />
            </h2>
          </CardTitle>
          <CardDescription>{t('replayCaption')}</CardDescription>
          {match.videoPage && (
            <Button variant="outline" size="sm" className="mt-2 justify-self-start bg-card" onClick={askVideo}>
              <Lock aria-hidden />
              {t('videoPage')}
            </Button>
          )}
        </CardHeader>
        <CardContent className="grid gap-8">
          {/* Wide screens: the legend and the rally controls in a column beside the court. */}
          <div className="mx-auto grid w-full max-w-3xl min-w-0 gap-3 lg:max-w-none lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-x-6">
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
              <ReplayCaption className="lg:mt-0" />
              <PlaylistBar />
            </div>
          </div>
          <RallyCards />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
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
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <Scoreboard />
            <div className="relative">
              {!full && <Feedback />}
              {/* Full screen takes the video with its controls. */}
              <div className="relative overflow-hidden rounded-lg bg-black [&:fullscreen]:flex [&:fullscreen]:flex-col [&:fullscreen]:rounded-none">
                {full && <Feedback />}
                {playlist && reached === playlist && playlist.at + 1 < playlist.clips.length && <Preload time={playlist.clips[playlist.at + 1].start} />}
                {/* What plays, over the video: the bar below is out of sight from the stats and in full screen. */}
                {playlist && (
                  <span
                    aria-hidden
                    className="pointer-events-none absolute top-2 left-2 z-10 max-w-[calc(100%-8.5rem)] truncate rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm"
                  >
                    {`${playlist.title(t)} · ${t('iOfN', { i: f.num(playlist.at + 1), n: f.num(playlist.clips.length) })}`}
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
                >
                  {match.av1 && <source src={match.av1} type={AV1} />}
                  <source src={match.video} />
                </video>
                <VideoControls follow={follow} onFollow={() => setFollow((f) => !f)} />
              </div>
            </div>
            <PlaylistBar />
          </div>
          <Replay />
        </div>
        <RallyCards />
      </CardContent>
    </Card>
  );
}

/** A hidden copy of the video waiting at `time`, the next clip's start: the browser keeps what it
 * fetches for the video, which then jumps there without waiting. */
function Preload({ time }: { time: number }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.currentTime = time;
    }
  }, [time]);
  return (
    <video ref={ref} muted playsInline preload="auto" aria-hidden className="hidden">
      {match.av1 && <source src={match.av1} type={AV1} />}
      <source src={match.video ?? undefined} />
    </video>
  );
}
