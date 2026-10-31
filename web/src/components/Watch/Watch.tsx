import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
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

// What web.py's --av1-video takes: 1080p, 8-bit, level 4.0; a browser that cannot play it takes the next source.
const AV1 = 'video/mp4; codecs="av01.0.08M.08"';

export function Watch() {
  const { t } = useTranslation();
  const f = useFormat();
  const { video, setVideo, playlist } = usePlayer();
  const court = useRef<HTMLDivElement>(null);
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
                <VideoControls />
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
