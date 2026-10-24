import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { sets } from '@/lib/match';
import { useSet } from '@/lib/sets';

/** One filter for the whole page, shown when the match has several sets. */
export function SetFilter() {
  const { t } = useTranslation();
  const { set, pick } = useSet();
  if (sets.length < 2) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span id="set-filter" className="font-semibold">
        {t('setFilter')}
      </span>
      <ToggleGroup
        type="single"
        variant="outline"
        spacing={0}
        value={set === null ? 'all' : String(set)}
        onValueChange={(v) => {
          if (v) {
            pick(v === 'all' ? null : Number(v));
          }
        }}
        aria-labelledby="set-filter"
        className="bg-card"
      >
        {['all', ...sets.map(String)].map((v) => (
          <ToggleGroupItem key={v} value={v} className="h-9 px-4 text-[15px] data-[state=on]:bg-primary data-[state=on]:font-semibold data-[state=on]:text-primary-foreground">
            {v === 'all' ? t('allSets') : t('set', { n: v })}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}
