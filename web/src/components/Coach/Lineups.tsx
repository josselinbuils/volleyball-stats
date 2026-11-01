import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { groupName, match, playerLabel, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { rallyClips } from '@/lib/playlist';
import { Section } from '@/components/Coach/Section';
import type { LineupScore, Server } from '@/components/Coach/helpers/coach';

/** The score of each six of `g`, with the points scored on each player's serves. */
export function Lineups({ lineups, g }: { lineups: LineupScore[]; g: Group }) {
  const { t } = useTranslation();
  return (
    <Section title={t('coach.lineups.title')} caption={t('coach.lineups.caption')}>
      <ul className="m-0 grid list-none gap-2 p-0">
        {lineups.map((l) => (
          <li key={l.people.join()} className="grid gap-1.5 rounded-lg border bg-card px-2.5 py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <p className="min-w-0 font-medium">{l.people.map((p) => playerLabel(t, p)).join(', ')}</p>
              <p className="whitespace-nowrap">
                <span className="text-xs text-muted-foreground">{t('coach.lineups.sets', { count: l.sets.length, list: l.sets.join(', ') })}</span>
                <b
                  aria-label={t('coach.lineups.score', { team: groupName(t, g), won: l.won, lost: l.lost })}
                  className={cn('ml-2 font-semibold tabular-nums', l.won > l.lost && 'text-[color:var(--point)]', l.won < l.lost && 'text-[color:var(--error)]')}
                >
                  {l.won}-{l.lost}
                </b>
              </p>
            </div>
            {l.servers.length > 0 && (
              <div className="flex flex-wrap items-center gap-1">
                <span className="mr-1 text-xs text-muted-foreground">{t('coach.lineups.served')}</span>
                {l.servers.map((s) => (
                  <ServerChip key={s.person} id={`coach:serve:${g}:${l.people.join()}:${s.person}:${s.rallies.length}`} server={s} />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ServerChip({ id, server }: { id: string; server: Server }) {
  const { t } = useTranslation();
  const { playlist, play } = usePlayer();
  const on = playlist?.key === id;
  return (
    <button
      type="button"
      aria-pressed={on}
      title={t('watchN', { count: server.rallies.length })}
      onClick={() => play((tr) => tr('coach.lineups.serverTitle', { name: playerLabel(tr, server.person) }), rallyClips(server.rallies, match.duration), 0, id)}
      className={cn('rounded-md border px-1.5 py-0.5 text-xs tabular-nums outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50', on && 'bg-primary/8 hover:bg-primary/12')}
    >
      {playerLabel(t, server.person)} <b className="font-semibold">{t('coach.lineups.servedRow', { won: server.won, of: server.rallies.length })}</b>
    </button>
  );
}
