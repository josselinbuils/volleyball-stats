import { useTranslation } from 'react-i18next';
import { Court, Legend } from '@/components/Court';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasTeams, match, playerNumber, rallies, teamColor, teamEdge, teamRing, type Group } from '@/lib/match';
import { useVideoTime } from '@/lib/player';
import { usePlayers } from '@/lib/players';
import { rallyAt } from '@/lib/playlist';
import { ballAt, playersAt, sidesAt } from '@/components/Watch/helpers/replay';

/** The court seen from above, players and ball following the video. */
export function Replay() {
  const { t } = useTranslation();
  const time = useVideoTime((now) => now);
  const players = usePlayers();
  const rally = rallyAt(rallies, time);
  const sides = sidesAt(rallies, time);
  const ball = rally ? ballAt(rally.contacts, time) : null;
  const last = rally?.contacts.filter((c) => c.t <= time).pop();
  const dots = typeof players === 'object' ? playersAt(players, match.fps, time) : [];

  let now = rally ? t('rally', { n: rally.i + 1 }) : t('betweenRallies');
  if (last) {
    const who = [groupName(t, last.g), last.player !== null && t('player', { n: last.player })].filter(Boolean).join(', ');
    now += ` · ${t('lastTouch', { type: t(`types.${last.type}`).toLowerCase(), who })}`;
  }
  const ends: [string, string] | undefined = hasTeams && sides ? [groupName(t, sides.left), groupName(t, (3 - sides.left) as Group)] : undefined;

  return (
    <figure className="m-0 min-w-0">
      <p className="line-clamp-2 h-12 font-semibold" aria-live="off" title={now}>
        {now}
      </p>
      {/* Up into the room left for a second line of the title: the court's top margin is mostly empty. */}
      <div className="relative -mt-4">
        <Court role="img" aria-label={t('replayLabel')} ends={ends}>
          {dots.map(({ person, x, y }) => {
            const team = match.people[person]?.team ?? 1;
            const n = playerNumber(person);
            return (
              <g key={person}>
                <circle cx={x} cy={y} r={0.7} className="player-mark" fill={teamColor(team)} stroke={teamEdge(team)} />
                {n !== null && (
                  <text x={x} y={y} className="player-text" fill={`var(--team${team}-text)`}>
                    {n}
                  </text>
                )}
              </g>
            );
          })}
          {ball && <circle cx={ball.x} cy={ball.y} r={0.28} className="ball-mark" />}
        </Court>
        {players === 'loading' && (
          <p className="pointer-events-none absolute inset-x-0 top-0 bottom-6 m-0 grid place-items-center">
            <span className="rounded-md bg-card/90 px-2.5 py-1 text-sm text-muted-foreground shadow-xs">{t('loadingPlayers')}</span>
          </p>
        )}
      </div>
      <figcaption className="mt-3 grid gap-2">
        <Legend>
          {GROUPS.map((g) => (
            <span key={g} className="inline-flex min-w-0 items-center gap-2">
              <Swatch color={teamColor(g)} ring={teamRing(g)} />
              <span className="truncate">{hasTeams ? groupName(t, g) : t(g === 1 ? 'leftTeam' : 'rightTeam')}</span>
            </span>
          ))}
          <span className="inline-flex items-center gap-2">
            <span aria-hidden className="inline-block size-2.5 shrink-0 rounded-full border-2 border-foreground" />
            {t('ball')}
          </span>
        </Legend>
        <p className="text-[13px] text-muted-foreground">
          {players === 'none' && `${t('noPlayers')} `}
          {players !== 'none' && `${t('numbersNote')} `}
          {t('replayNote')}
        </p>
      </figcaption>
    </figure>
  );
}
