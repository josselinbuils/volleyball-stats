import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { Histogram } from '@/components/RallyCharts/Histogram';
import { Timeline } from '@/components/RallyCharts/Timeline';

export function RallyCharts() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('rallies')}
            <SetBadge />
          </h2>
        </CardTitle>
      </CardHeader>
      {/* Side by side, the two captions share a row: the charts start and end at the same height. */}
      <CardContent className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)] lg:gap-y-4">
        <div className="grid content-start gap-4 lg:row-span-2 lg:grid-rows-subgrid">
          <p className="text-sm text-muted-foreground">{t('timelineCaption')}</p>
          <Timeline />
        </div>
        <div className="grid content-start gap-4 lg:row-span-2 lg:grid-rows-subgrid">
          <p className="text-sm text-muted-foreground">{t('histCaption')}</p>
          <Histogram />
        </div>
      </CardContent>
    </Card>
  );
}
