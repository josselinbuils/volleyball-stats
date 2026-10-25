import { useTranslation } from 'react-i18next';
import { Court, Legend } from '@/components/Court';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasNames, hasTeams, match, playerLabel, playerNumber, rallies, teamColor, teamEdge, teamRing, type Group } from '@/lib/match';
import { useVideoTime } from '@/lib/player';
import { usePlayers } from '@/lib/players';
import { rallyAt } from '@/lib/playlist';
import { ballAt, playersAt, sidesAt, touchesAt, trailAt } from '@/components/Watch/helpers/replay';

/** The court seen from above, players and ball following the video. */
export function Replay() {
  const { t } = useTranslation();
  const time = useVideoTime((now) => now);
  const players = usePlayers();
  const rally = rallyAt(rallies, time);
  const sides = sidesAt(rallies, time);
  const ball = rally ? ballAt(rally.contacts, time) : null;
  const trail = rally ? trailAt(rally.contacts, time) : [];
  const touches = rally ? touchesAt(rally.contacts, time) : [];
  const last = rally?.contacts.filter((c) => c.t <= time).pop();
  const dots = typeof players === 'object' ? playersAt(players, match.fps, time) : [];

  let now = rally ? t('rally', { n: rally.i + 1 }) : t('betweenRallies');
  if (last) {
    const who = [groupName(t, last.g), playerLabel(t, last.person)].filter(Boolean).join(', ');
    now += ` · ${t('lastTouch', { type: t(`types.${last.type}`).toLowerCase(), who })}`;
  }
  const ends: [string, string] | undefined = hasTeams && sides ? [groupName(t, sides.left), groupName(t, (3 - sides.left) as Group)] : undefined;

  return (
    <figure className="m-0 min-w-0">
      {/* Boxed like the score bar beside it, at the same height. */}
      <p className="mb-3 flex h-11 items-center rounded-lg bg-muted px-3 text-sm leading-5 font-semibold" aria-live="off" title={now}>
        <span className="line-clamp-2">{now}</span>
      </p>
      {/* The court's top margin is mostly empty: it tucks under the box. */}
      <div className="relative -mt-4">
        <Court role="img" aria-label={t('replayLabel')} ends={ends}>
          {dots.map(({ person, x, y }) => {
            const team = match.people[person]?.team ?? 1;
            const n = playerNumber(person);
            const name = match.people[person]?.name;
            return (
              <g key={person}>
                {name && <title>{name}</title>}
                <circle cx={x} cy={y} r={0.7} className="player-mark" fill={teamColor(team)} stroke={teamEdge(team)} />
                {n !== null && (
                  <text x={x} y={y} className="player-text" fill={`var(--team${team}-text)`}>
                    {n}
                  </text>
                )}
              </g>
            );
          })}
          {/* A comet tail behind the ball, widening and darkening towards it. */}
          {/* A ring widening and fading around the player who touches the ball. */}
          {touches.map(({ touch, f }) => {
            const at = dots.find((d) => d.person === touch.person) ?? (touch.x !== null && touch.y !== null ? { x: touch.x, y: touch.y } : null);
            return at && <circle key={touch.i} cx={at.x} cy={at.y} r={0.9 + 0.9 * f} className="touch-ring" opacity={1 - f} />;
          })}
          {trail.slice(1).map((p, k) => (
            <line key={k} x1={trail[k].x} y1={trail[k].y} x2={p.x} y2={p.y} className="ball-trail" strokeWidth={0.12 + (0.5 * (k + 1)) / trail.length} opacity={(0.65 * (k + 1)) / trail.length} />
          ))}
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
          {players !== 'none' && `${t(hasNames ? 'numbersNoteNamed' : 'numbersNote')} `}
          {t('replayNote')}
        </p>
      </figcaption>
    </figure>
  );
}
