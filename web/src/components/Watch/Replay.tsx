import { useTranslation } from 'react-i18next';
import { Court, Legend } from '@/components/Court';
import { Swatch } from '@/components/Swatch';
import { color, match, rallies } from '@/lib/match';
import { useVideoTime } from '@/lib/player';
import { rallyAt } from '@/lib/playlist';
import { ballAt, playersAt } from '@/components/Watch/helpers/replay';

const hasPlayers = match.players.spans.some((span) => span.samples.some(([left, right]) => left.length || right.length));

/** The court seen from above, players and ball following the video. */
export function Replay() {
  const { t } = useTranslation();
  const time = useVideoTime((now) => now);
  const rally = rallyAt(rallies, time);
  const ball = rally ? ballAt(rally.contacts, time) : null;
  const last = rally?.contacts.filter((c) => c.t <= time).pop();
  const players = playersAt(match.players, match.fps, time);

  let now = rally ? t('rally', { n: rally.i + 1 }) : t('betweenRallies');
  if (last) {
    now += ` · ${t('lastTouch', { type: t(`types.${last.type}`).toLowerCase(), side: t(`${last.side}Side`).toLowerCase() })}`;
  }

  return (
    <figure className="m-0 min-w-0">
      <Court role="img" aria-label={t('replayLabel')}>
        {players.map((flat, team) =>
          Array.from({ length: flat.length / 2 }, (_, i) => (
            <circle key={`${team}-${i}`} cx={flat[2 * i]} cy={flat[2 * i + 1]} r={0.34} className="player-mark" fill={color(team ? 'right' : 'left')} />
          )),
        )}
        {ball && <circle cx={ball.x} cy={ball.y} r={0.28} className="ball-mark" />}
      </Court>
      <figcaption className="mt-3 grid gap-2">
        <p className="min-h-6 font-semibold" aria-live="off">
          {now}
        </p>
        <Legend>
          <span className="inline-flex items-center gap-2">
            <Swatch color={color('left')} />
            {t('leftTeam')}
          </span>
          <span className="inline-flex items-center gap-2">
            <Swatch color={color('right')} />
            {t('rightTeam')}
          </span>
          <span className="inline-flex items-center gap-2">
            <Swatch color={color('foreground')} />
            {t('ball')}
          </span>
        </Legend>
        <p className="text-[13px] text-muted-foreground">{hasPlayers ? t('replayNote') : `${t('noPlayers')} ${t('replayNote')}`}</p>
      </figcaption>
    </figure>
  );
}
