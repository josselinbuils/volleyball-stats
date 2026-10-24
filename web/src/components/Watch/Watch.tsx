import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { match } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { PlaylistBar } from '@/components/Watch/PlaylistBar';
import { RallyCards } from '@/components/Watch/RallyCards';
import { Replay } from '@/components/Watch/Replay';
import { Scoreboard } from '@/components/Watch/Scoreboard';

export function Watch() {
  const { t } = useTranslation();
  const { setVideo } = usePlayer();

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
            {/* Nothing loads before the first play. */}
            <video ref={setVideo} src={match.video} poster={match.poster} controls playsInline preload="none" aria-label={t('video')} className="block aspect-video w-full rounded-lg bg-black" />
            <PlaylistBar />
          </div>
          <Replay />
        </div>
        <RallyCards />
      </CardContent>
    </Card>
  );
}
