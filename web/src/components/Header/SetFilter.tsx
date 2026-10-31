import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { sets } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { useSet } from '@/lib/sets';

/** One filter for the whole page, shown when the match has several sets; it stays at the top of the
 * screen while the page scrolls. */
export function SetFilter() {
  const { t } = useTranslation();
  const { set, pick } = useSet();
  const { playlist, stop } = usePlayer();
  if (sets.length < 2) {
    return null;
  }
  return (
    <div className="sticky top-0 z-30 -mx-4 flex flex-wrap items-center gap-x-3 gap-y-2 bg-background/95 px-5 py-2.5 shadow-[0_1px_0_var(--border)] backdrop-blur-sm max-sm:-my-1">
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
