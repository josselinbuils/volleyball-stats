import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { match } from '@/lib/match';
import { Clock } from '@/lib/clock';
import { usePlayer } from '@/lib/player';
import { PlaylistBar } from '@/components/Watch/PlaylistBar';
import { RallyCards } from '@/components/Watch/RallyCards';
import { Replay } from '@/components/Watch/Replay';
import { Scoreboard } from '@/components/Watch/Scoreboard';
import { VideoControls } from '@/components/Watch/VideoControls';

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
        </CardHeader>
        <CardContent className="grid gap-8">
          <div className="mx-auto grid w-full max-w-3xl min-w-0 gap-3">
            <Scoreboard />
            {/* Full screen takes the court with its controls. */}
            <div ref={court} className="overflow-hidden rounded-lg border bg-card [&:fullscreen]:grid [&:fullscreen]:content-center [&:fullscreen]:p-6">
              <div className="p-3 pb-0">
                <Replay />
              </div>
              <div className="border-t bg-muted">
                <VideoControls light />
              </div>
            </div>
            <PlaylistBar />
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
            {/* Full screen takes the video with its controls. */}
            <div className="overflow-hidden rounded-lg bg-black [&:fullscreen]:flex [&:fullscreen]:flex-col [&:fullscreen]:rounded-none">
              {/* Nothing loads before the first play. */}
              <video
                ref={setVideo}
                src={match.video}
                poster={match.poster}
                playsInline
                preload="none"
                aria-label={t('video')}
                onClick={() => (video?.paused ? void video.play().catch(() => {}) : video?.pause())}
                className="block aspect-video w-full cursor-pointer [:fullscreen>&]:aspect-auto [:fullscreen>&]:min-h-0 [:fullscreen>&]:flex-1"
              />
              <VideoControls />
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
