import { useTranslation } from 'react-i18next';
import { groupName, playerLabel, type Group } from '@/lib/match';
import { Section } from '@/components/Coach/Section';
import type { LineupScore } from '@/components/Coach/helpers/coach';

/** The score of each six of `g`. */
export function Lineups({ lineups, g }: { lineups: LineupScore[]; g: Group }) {
  const { t } = useTranslation();
  return (
    <Section title={t('coach.lineups.title')} caption={t('coach.lineups.caption')}>
      <ul className="m-0 grid list-none gap-2 p-0">
        {lineups.map((l) => (
          <li key={l.people.join()} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 rounded-lg border bg-card px-2.5 py-2">
            <p className="min-w-0 font-medium">{l.people.map((p) => playerLabel(t, p)).join(', ')}</p>
            <p className="whitespace-nowrap">
              <span className="text-xs text-muted-foreground">{t('coach.lineups.sets', { count: l.sets.length, list: l.sets.join(', ') })}</span>
              <b aria-label={t('coach.lineups.score', { team: groupName(t, g), won: l.won, lost: l.lost })} className="ml-2 font-semibold tabular-nums">
                {l.won}-{l.lost}
              </b>
            </p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
