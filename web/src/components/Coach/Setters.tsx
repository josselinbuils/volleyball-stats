import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Swatch } from '@/components/Swatch';
import { color, match, playerLabel, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { Section } from '@/components/Coach/Section';
import type { Contact } from '@/lib/match';
import type { Setter } from '@/components/Coach/helpers/coach';

const RESULTS = [
  { result: 'point', key: 'won' },
  { result: 'play', key: 'play' },
  { result: 'error', key: 'fault' },
] as const;

/** A setter's attackers with a single attack, together one row when there are several. */
const once = (s: Setter) => s.attackers.filter((a) => a.attacks.length === 1);

/** Each setter and the attacks after their sets, each row replaying them. */
export function Setters({ setters, g, rallies }: { setters: Setter[]; g: Group; rallies: number }) {
  const { t } = useTranslation();
  const most = Math.max(...setters.flatMap((s) => s.attackers.map((a) => a.attacks.length)));
  return (
    <Section title={t('coach.setters.title')} caption={t('coach.setters.caption')}>
      <ul aria-hidden className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-xs text-muted-foreground">
        {RESULTS.map(({ result, key }) => (
          <li key={key} className="inline-flex items-center gap-1.5">
            <Swatch color={color(result)} className="size-2.5" />
            {t(`coach.setters.${key}`)}
          </li>
        ))}
      </ul>
      <div className="grid items-start gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        {setters.map((s) => (
          <div key={s.person} className="grid gap-1">
            <p className="px-1.5 text-sm">
              <b className="font-semibold">{playerLabel(t, s.person)}</b>
              <span className="text-muted-foreground">
                {' · '}
                {t('coach.setters.sets', { count: s.sets, attacked: s.attackers.reduce((n, a) => n + a.attacks.length, 0) })}
              </span>
            </p>
            <ul className="m-0 grid list-none gap-0.5 p-0">
              {s.attackers
                .filter((a) => a.attacks.length > 1 || once(s).length < 2)
                .map((a) => (
                  <Row
                    key={a.person}
                    id={`coach:duo:${g}:${s.person}:${a.person}:${rallies}`}
                    label={playerLabel(t, a.person) ?? ''}
                    title={(tr) => tr('coach.setters.playing', { setter: playerLabel(tr, s.person), attacker: playerLabel(tr, a.person) })}
                    attacks={a.attacks}
                    most={most}
                  />
                ))}
              {once(s).length > 1 && (
                <Row
                  id={`coach:duo:${g}:${s.person}:others:${rallies}`}
                  label={t('coach.setters.others', { count: once(s).length })}
                  title={(tr) => tr('coach.setters.playingOthers', { setter: playerLabel(tr, s.person) })}
                  attacks={once(s).flatMap((a) => a.attacks)}
                  most={most}
                />
              )}
            </ul>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Row({ id, label, title, attacks, most }: { id: string; label: string; title: (t: TFunction) => string; attacks: Contact[]; most: number }) {
  const { t } = useTranslation();
  const { playlist, play } = usePlayer();
  const n = (result: string) => attacks.filter((c) => c.result === result).length;
  const on = playlist?.key === id;
  return (
    <li>
      <button
        type="button"
        aria-pressed={on}
        title={t('coach.setters.detail', { kills: n('point'), play: n('play'), faults: n('error') })}
        onClick={() => play(title, contactClips(attacks, match.duration), 0, id)}
        className={cn(
          'grid w-full grid-cols-[minmax(0,6rem)_minmax(0,1fr)_auto_auto] items-center gap-2 rounded-md px-1.5 py-1 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
          on && 'bg-primary/8 hover:bg-primary/12',
        )}
      >
        <span className="truncate">{label}</span>
        <span aria-hidden className="flex h-2 overflow-hidden rounded-full bg-muted">
          <span className="flex h-full" style={{ width: `${(100 * attacks.length) / most}%` }}>
            {RESULTS.map(({ result }) => (
              <span key={result} className="h-full" style={{ flexGrow: n(result), background: color(result) }} />
            ))}
          </span>
        </span>
        <span className="text-right whitespace-nowrap tabular-nums">{t('coach.setters.row', { kills: n('point'), count: attacks.length })}</span>
        <Play aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
      </button>
    </li>
  );
}
