import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { match, playerLabel } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { Section } from '@/components/Coach/Section';
import type { Jumper } from '@/components/Coach/helpers/jumps';
import { Tip } from '@/components/Tip';

/** Each attacker's advice on their jumps, each row replaying the measured ones. */
export function Jumps({ jumpers }: { jumpers: Jumper[] }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  return (
    <Section title={t('coach.jumps.title')} caption={t('coach.jumps.caption')}>
      <ul className="m-0 grid list-none gap-2 p-0 lg:grid-cols-3">
        {jumpers.map((j) => (
          <li key={j.person}>
            <Tip label={t('watchN', { count: j.attacks.length })}>
              <button
                type="button"
                onClick={() => play((tr) => tr('coach.jumps.playing', { player: playerLabel(tr, j.person) }), contactClips(j.attacks, match.duration))}
                className="flex h-full w-full items-start gap-2.5 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span className="grid min-w-0 flex-1 gap-0.5">
                  <b className="truncate font-semibold">{playerLabel(t, j.person)}</b>
                  {j.tips.map((tip) => (
                    <span key={tip} className="text-sm">
                      {t(`coach.jumps.tips.${tip}`)}
                    </span>
                  ))}
                </span>
                <Play aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
              </button>
            </Tip>
          </li>
        ))}
      </ul>
    </Section>
  );
}
