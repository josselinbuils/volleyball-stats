import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
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
  const { video, setVideo } = usePlayer();
  const court = useRef<HTMLDivElement>(null);
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
              <Feedback />
              {/* Full screen takes the video with its controls. */}
              <div className="overflow-hidden rounded-lg bg-black [&:fullscreen]:flex [&:fullscreen]:flex-col [&:fullscreen]:rounded-none">
                {/* Nothing loads before the first play. */}
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
