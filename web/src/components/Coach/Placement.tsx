import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { match, playerLabel } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useFormat } from '@/lib/format';
import { Section } from '@/components/Coach/Section';
import { OFF_M, type Placement as Cue } from '@/components/Coach/helpers/defense';
import { Tip } from '@/components/Tip';

/** Each player's cue for the perimeter defence, each row replaying the attacks they stood off their spot. */
export function Placement({ cues }: { cues: Cue[] }) {
  const { t } = useTranslation();
  return (
    <Section title={t('coach.placement.title')} caption={t('coach.placement.caption')}>
      <ul className="m-0 grid list-none gap-2 p-0 lg:grid-cols-3">
        {cues.map((cue) => (
          <Row key={cue.person} cue={cue} />
        ))}
      </ul>
    </Section>
  );
}

function Row({ cue }: { cue: Cue }) {
  const { t } = useTranslation();
  const { num, dec } = useFormat();
  const { play } = usePlayer();
  // To the half metre: the places are not finer.
  const metres = (x: number) => {
    const m = Math.round(Math.abs(x) * 2) / 2;
    return Number.isInteger(m) ? num(m) : dec(m);
  };
  const ways = [
    ...(Math.abs(cue.back) >= OFF_M ? [t(cue.back > 0 ? 'coach.placement.back' : 'coach.placement.forward', { m: metres(cue.back) })] : []),
    ...(Math.abs(cue.out) >= OFF_M ? [t(cue.out > 0 ? 'coach.placement.out' : 'coach.placement.in', { m: metres(cue.out) })] : []),
  ];
  return (
    <li>
      <Tip label={t('watchN', { count: cue.off.length })}>
        <button
          type="button"
          onClick={() =>
            play(
              (tr) => tr('coach.placement.playing', { player: playerLabel(tr, cue.person) }),
              contactClips(cue.off, match.duration).map(({ player: _, name: __, ...clip }) => clip),
            )
          }
          className="flex h-full w-full items-start gap-2.5 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <span className="grid min-w-0 flex-1 gap-0.5">
            <b className="font-semibold">{playerLabel(t, cue.person)}</b>
            <span className="text-sm font-medium">{t(`coach.placement.spots.${cue.spot}`)}</span>
            <span className="text-[13px] text-muted-foreground">{ways.join(', ')}</span>
          </span>
          <Play aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </Tip>
    </li>
  );
}
