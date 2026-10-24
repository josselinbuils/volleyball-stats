import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Histogram } from '@/components/RallyCharts/Histogram';
import { Timeline } from '@/components/RallyCharts/Timeline';

export function RallyCharts() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t('rallies')}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <div>
          <p className="mb-4 text-sm text-muted-foreground">{t('timelineCaption')}</p>
          <Timeline />
        </div>
        <div>
          <p className="mb-4 text-sm text-muted-foreground">{t('histCaption')}</p>
          <Histogram />
        </div>
      </CardContent>
    </Card>
  );
}
