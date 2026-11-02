import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Court, Legend } from '@/components/Court';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasNames, hasTeams, match, playerLabel, playerMark, rallies, teamColor, teamEdge, teamRing, type Group } from '@/lib/match';
import { useVideoTime } from '@/lib/player';
import { isTouch } from '@/helpers/contacts';
import { playerKey, playersAt } from '@/helpers/players';
import { useBall3d } from '@/lib/ball3d';
import { filesKey, loadPlayersAt, positionsPending, usePlayers } from '@/lib/players';
import { rallyAt } from '@/lib/playlist';
import { ballAt, landingsAt, lastTouch, sidesAt, touchesAt, trailAt } from '@/components/Watch/helpers/replay';
import { sceneAt } from '@/components/Watch/helpers/sceneAt';
import { bodyOf, posesAt, SPEED_S } from '@/components/Watch/helpers/pose';
import { Scene3D } from '@/components/Watch/Scene3D';
import { BroadcastOverlay } from '@/components/Watch/Broadcast';
import { Feedback } from '@/components/Watch/Feedback';
import { idleCamera, rallyCamera, replayAt, replayCamera, replays } from '@/components/Watch/helpers/director';
import { scoreAt } from '@/components/Watch/helpers/score';

const FIRST_POSITIONS_MS = 500;

/** Loads the players' positions as the moment moves on, for the views that draw them. */
export function LoadPositions() {
  const time = useVideoTime((now) => now);
  const files = useVideoTime(filesKey);
  const painted = useRef(false);
  // The first positions wait for the first paint: nothing but a replay needs them.
  useEffect(() => {
    const timer = window.setTimeout(() => loadPlayersAt(time), painted.current ? 0 : FIRST_POSITIONS_MS);
    painted.current = true;
    return () => {
      clearTimeout(timer);
    };
    // Only when the moment moves on to other files.
  }, [files]);
  return null;
}

/** What the views drawing the match show at the video's time; `tv` shows an earlier moment of a rally
 * in the dead time after it. */
function useMoment(tv: boolean) {
  const time = useVideoTime((now) => now);
  const players = usePlayers();
  const chosen = useMemo(() => replays(rallies), []);
  const replay = tv ? replayAt(rallies, chosen, time) : null;
  const moment = replay?.time ?? time;
  const playing = rallyAt(rallies, time);
  const rally = replay?.rally ?? playing;
  return {
    time,
    players,
    replay,
    moment,
    playing,
    rally,
    touches: rally ? touchesAt(rally.contacts, moment) : [],
    landings: rally ? landingsAt(rally.contacts, moment) : [],
    dots: typeof players === 'object' ? playersAt(players, match.fps, moment) : [],
  };
}

/** The rally the video is on and its last touch, in a box beside the score; with the report button when `report`. */
export function NowLine({ report }: { report: boolean }) {
  const { t } = useTranslation();
  const time = useVideoTime((now) => now);
  const playing = rallyAt(rallies, time);
  const last = playing && lastTouch(playing.contacts, time);
  let now = playing ? t('rally', { n: playing.i + 1 }) : t('betweenRallies');
  if (last) {
    const who = [groupName(t, last.g), playerLabel(t, last.person)].filter(Boolean).join(', ');
    now += ` · ${t('lastTouch', { type: t(`types.${last.type}`).toLowerCase(), who })}`;
  }
  return (
    <div className="flex h-11 items-center gap-2 rounded-lg bg-muted px-3 text-sm leading-5 font-semibold">
      <p className="m-0 line-clamp-2 min-w-0 flex-1" aria-live="off" title={now}>
        {now}
      </p>
      {report && <Feedback inline />}
    </div>
  );
}

/** The court seen from above, players and ball following the video. */
export function CourtView() {
  const { t } = useTranslation();
  const { time, rally, moment, dots, touches, landings } = useMoment(false);
  const sides = sidesAt(rallies, time);
  const ball = rally ? ballAt(rally.contacts, moment) : null;
  const trail = rally ? trailAt(rally.contacts, moment) : [];
  // The player under the pointer, named above their mark.
  const [hover, setHover] = useState<number | null>(null);
  const hovered = dots.find((d) => d.person === hover);
  const tip = hovered && playerLabel(t, hovered.person);
  const ends: [string, string] | undefined = hasTeams && sides ? [groupName(t, sides.left), groupName(t, (3 - sides.left) as Group)] : undefined;
  return (
    // As large as the view allows, its end labels over its bottom.
    <div className="relative size-full">
      <Court role="img" aria-label={t('replayLabel')} ends={ends} className="relative flex h-full flex-col [&>div]:absolute [&>div]:inset-x-0 [&>div]:bottom-1 [&>svg]:min-h-0 [&>svg]:flex-1">
        {dots.map(({ person, x, y }) => {
          const team = match.people[person]?.team ?? 1;
          const mark = playerMark(person);
          return (
            <g key={person} onPointerEnter={() => setHover(person)} onPointerLeave={() => setHover((h) => (h === person ? null : h))}>
              <circle cx={x} cy={y} r={0.7} className="player-mark" fill={teamColor(team)} stroke={teamEdge(team)} />
              {mark !== null && (
                <text x={x} y={y} className="player-text" fill={`var(--team${team}-text)`}>
                  {mark}
                </text>
              )}
            </g>
          );
        })}
        {/* Where the ball hits the floor: a mark and two rings rippling out, fading. */}
        {landings.map(({ x, y, f, i }) => (
          <g key={i} className="landing" opacity={1 - f}>
            <circle cx={x} cy={y} r={0.2 + 0.25 * f} className="landing-mark" />
            <circle cx={x} cy={y} r={0.4 + 1.6 * f} className="landing-ring" />
            {f > 0.2 && <circle cx={x} cy={y} r={0.4 + 1.6 * (f - 0.2)} className="landing-ring" />}
          </g>
        ))}
        {/* A ring widening and fading around the player who touches the ball. */}
        {touches.map(({ touch, f }) => {
          const at = dots.find((d) => d.person === touch.person) ?? (touch.x !== null && touch.y !== null ? { x: touch.x, y: touch.y } : null);
          return at && <circle key={touch.i} cx={at.x} cy={at.y} r={0.9 + 0.9 * f} className="touch-ring" opacity={1 - f} />;
        })}
        {/* A comet tail behind the ball, widening and darkening towards it. */}
        {trail.slice(1).map((p, k) => (
          <line key={k} x1={trail[k].x} y1={trail[k].y} x2={p.x} y2={p.y} className="ball-trail" strokeWidth={0.12 + (0.5 * (k + 1)) / trail.length} opacity={(0.65 * (k + 1)) / trail.length} />
        ))}
        {ball && <circle cx={ball.x} cy={ball.y} r={0.28} className="ball-mark" />}
        {hovered && tip && <CourtTip x={hovered.x} y={hovered.y} text={tip} />}
      </Court>
      {positionsPending(time) && (
        <p className="pointer-events-none absolute inset-x-0 top-0 bottom-6 m-0 grid place-items-center">
          <span className="rounded-md bg-card/90 px-2.5 py-1 text-sm text-muted-foreground shadow-xs">{t('loadingPlayers')}</span>
        </p>
      )}
    </div>
  );
}

/** The match in 3D, turned with the pointer; `tv` films it as a broadcast, with its replays and commentary. */
export function SceneView({ tv, voice }: { tv: boolean; voice: boolean }) {
  const { t } = useTranslation();
  const places = useBall3d();
  const { time, players, replay, moment, playing, rally, dots, touches, landings } = useMoment(tv);
  const score = scoreAt(rallies, time, match.scores);
  const followed = replay ? (dots.find((d) => playerKey(d.person, match.people) === playerKey(replay.contact.person, match.people)) ?? undefined) : undefined;
  const poses =
    typeof players !== 'object' ? null : posesAt(rally, moment, dots, playersAt(players, match.fps, moment - SPEED_S), playersAt(players, match.fps, moment + SPEED_S), places, match.people);
  const camera = !tv
    ? null
    : replay
      ? replayCamera(replay, followed && { ...followed, jump: poses?.get(followed.person)?.jump ?? 0 }, places)
      : rally
        ? rallyCamera(rally, moment, places)
        : idleCamera(time);
  const firstTouch = rally?.contacts.find(isTouch);
  const server = firstTouch && bodyOf(firstTouch, places?.get(firstTouch.i) ?? null, dots, match.people);
  // The player under the pointer, named above their body.
  const [hover, setHover] = useState<number | null>(null);
  const hovered = dots.find((d) => d.person === hover);
  const tip = hovered && playerLabel(t, hovered.person);
  return (
    <Scene3D
      badge={!tv}
      overlay={tv ? <BroadcastOverlay time={time} rally={playing?.i ?? null} replay={replay} score={score} voice={voice} /> : null}
      state={sceneAt({
        dots,
        poses,
        rally,
        moment,
        touches,
        landings,
        server,
        places,
        board: score && { teams: [groupName(t, 1), groupName(t, 2)], score: score.score, set: t('set', { n: score.set }) },
        camera,
        hidden: followed?.person ?? null,
        tipOf: (person) => (person === hover ? (tip ?? undefined) : undefined),
      })}
      onHover={setHover}
    />
  );
}

/** `text` on a dark band above the player standing at (x, y), sized to the text once drawn. */
function CourtTip({ x, y, text }: { x: number; y: number; text: string }) {
  const label = useRef<SVGTextElement>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => setWidth(label.current?.getComputedTextLength() ?? 0), [text]);
  return (
    <g className="pointer-events-none" opacity={width ? 1 : 0}>
      <rect x={x - width / 2 - 0.3} y={y - 1.95} width={width + 0.6} height={0.95} rx={0.22} className="fill-foreground" />
      <text ref={label} x={x} y={y - 1.47} className="player-tip">
        {text}
      </text>
    </g>
  );
}

/** The court replay's legend: the teams, and how to read the players. */
export function ReplayCaption({ className }: { className?: string }) {
  const { t } = useTranslation();
  const players = usePlayers();
  return (
    <div className={cn('mt-3 grid gap-2', className)}>
      <Legend>
        {GROUPS.map((g) => (
          <span key={g} className="inline-flex min-w-0 items-center gap-2">
            <Swatch color={teamColor(g)} ring={teamRing(g)} />
            <span className="truncate">{hasTeams ? groupName(t, g) : t(g === 1 ? 'leftTeam' : 'rightTeam')}</span>
          </span>
        ))}
      </Legend>
      <p className="text-[13px] text-muted-foreground">{players === 'none' ? t('noPlayers') : t(hasNames ? 'numbersNoteNamed' : 'numbersNote')}</p>
    </div>
  );
}
