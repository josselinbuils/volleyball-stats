import { useTranslation } from 'react-i18next';
import { Lock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { match } from '@/lib/match';
import { askVideo } from '@/components/VideoChoice';
import { RallyCards } from '@/components/Watch/RallyCards';
import { Stage } from '@/components/Watch/Stage';

export function Watch() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t(match.video ? 'video' : 'replayTitle')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t(match.video ? 'videoCaption' : 'replayCaption')}</CardDescription>
        {!match.video && match.videoPage && (
          <Button variant="outline" size="sm" className="mt-2 justify-self-start bg-card" onClick={askVideo}>
            <Lock aria-hidden />
            {t('videoPage')}
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-8">
        <Stage />
        <RallyCards />
      </CardContent>
    </Card>
  );
}
