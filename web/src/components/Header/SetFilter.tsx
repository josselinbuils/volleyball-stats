import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { sets } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { useSet } from '@/lib/sets';

/** One filter for the whole page, shown when the match has several sets. Its label only on wider screens: on a phone
 * the sets say what they are, the row kept for them. */
export function SetFilter() {
  const { t } = useTranslation();
  const { set, pick } = useSet();
  const { playlist, stop } = usePlayer();
  if (sets.length < 2) {
    return null;
  }
  return (
    <div className="flex items-center gap-3">
      <span id="set-filter" className="font-semibold max-sm:sr-only">
        {t('setFilter')}
      </span>
      <ToggleGroup
        type="single"
        variant="outline"
        spacing={0}
        value={set === null ? 'all' : String(set)}
        onValueChange={(v) => {
          if (v) {
            // A playlist can hold clips outside the set picked, where the video cannot go.
            if (playlist) {
              stop();
            }
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
