import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { match } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { PlaylistBar } from '@/components/Watch/PlaylistBar';
import { RallyCards } from '@/components/Watch/RallyCards';
import { Replay } from '@/components/Watch/Replay';
import { Scoreboard } from '@/components/Watch/Scoreboard';
import { VideoControls } from '@/components/Watch/VideoControls';

export function Watch() {
  const { t } = useTranslation();
  const { video, setVideo } = usePlayer();

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
