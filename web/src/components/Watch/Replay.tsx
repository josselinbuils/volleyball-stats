import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';
import { Court, Legend } from '@/components/Court';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasNames, hasTeams, match, playerLabel, playerMark, rallies, teamColor, teamEdge, teamRing, timeoutAt, timeoutLabel, type Group } from '@/lib/match';
import { togglePlay, usePlayer, useVideoTime } from '@/lib/player';
import { isTouch } from '@/helpers/contacts';
import { playerKey, playersAt } from '@/helpers/players';
import { useBall3d } from '@/lib/ball3d';
import { filesKey, loadPlayersAt, positionsPending, usePlayers } from '@/lib/players';
import { rallyAt } from '@/lib/playlist';
import { ballAt, landingsAt, lastTouch, sidesAt, touchesAt, trailAt } from '@/components/Watch/helpers/replay';
import { sceneAt } from '@/components/Watch/helpers/sceneAt';
import { bodyOf, posesAt, SPEED_S } from '@/components/Watch/helpers/pose';
import { canDraw3d, Scene3D } from '@/components/Watch/Scene3D';
import { BroadcastControls, BroadcastOverlay } from '@/components/Watch/Broadcast';
import { Feedback } from '@/components/Watch/Feedback';
import { idleCamera, rallyCamera, replayAt, replayCamera, replays } from '@/components/Watch/helpers/director';
import { scoreAt } from '@/components/Watch/helpers/score';
import { Tip } from '@/components/Tip';

const STORED = 'court-view';
const VIEWS = ['2d', '3d', 'tv'] as const;
type View = (typeof VIEWS)[number];
const FIRST_POSITIONS_MS = 500;

/** The court seen from above, players and ball following the video; its legend under it unless
 * `captioned` is false, the page then showing `ReplayCaption` itself. */
export function Replay({ captioned = true }: { captioned?: boolean }) {
  const { t } = useTranslation();
  const time = useVideoTime((now) => now);
  const players = usePlayers();
  const places = useBall3d();
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
  const { video } = usePlayer();
  // Where the pointer went down: a click plays or pauses, a drag turning the 3D view does not.
  const down = useRef({ x: 0, y: 0 });
  // The view chosen last time, remembered by the browser when it can.
  const [view, setView] = useState<View>(() => {
    try {
      const stored = localStorage.getItem(STORED);
      return (stored === '3d' || stored === 'tv') && canDraw3d() ? stored : '2d';
    } catch {
      return '2d';
    }
  });
  const choose = (next: View) => {
    setView(next);
    try {
      localStorage.setItem(STORED, next);
    } catch {
      // Private browsing: the choice lasts for the page only.
    }
  };
  const [voice, setVoice] = useState(false);
  const chosen = useMemo(() => replays(rallies), []);
  const tv = view === 'tv';
  // A replay shows an earlier moment of its rally in the dead time after it.
  const replay = tv ? replayAt(rallies, chosen, time) : null;
  const moment = replay?.time ?? time;
  const playing = rallyAt(rallies, time);
  const rally = replay?.rally ?? playing;
  const sides = sidesAt(rallies, time);
  const ball = rally ? ballAt(rally.contacts, moment) : null;
  const trail = rally ? trailAt(rally.contacts, moment) : [];
  const touches = rally ? touchesAt(rally.contacts, moment) : [];
  const landings = rally ? landingsAt(rally.contacts, moment) : [];
  const last = playing && lastTouch(playing.contacts, time);
  const dots = typeof players === 'object' ? playersAt(players, match.fps, moment) : [];
  const score = scoreAt(rallies, time, match.scores);
  const followed = replay ? (dots.find((d) => playerKey(d.person, match.people) === playerKey(replay.contact.person, match.people)) ?? undefined) : undefined;
  const poses =
    view === '2d' || typeof players !== 'object'
      ? null
      : posesAt(rally, moment, dots, playersAt(players, match.fps, moment - SPEED_S), playersAt(players, match.fps, moment + SPEED_S), places, match.people);
  const camera = !tv
    ? null
    : replay
      ? replayCamera(replay, followed && { ...followed, jump: poses?.get(followed.person)?.jump ?? 0 }, places)
      : rally
        ? rallyCamera(rally, moment, places)
        : idleCamera(time);
  const firstTouch = rally?.contacts.find(isTouch);
  const server = firstTouch && bodyOf(firstTouch, places?.get(firstTouch.i) ?? null, dots, match.people);
  // The player under the mouse, named above their mark; on a touch screen the one tapped, until the next tap.
  const [hover, setHover] = useState<number | null>(null);
  // A tap on a player: it names them instead of playing or pausing.
  const named = useRef(false);
  const hovered = dots.find((d) => d.person === hover);
  const tip = hovered && playerLabel(t, hovered.person);
  const pause = playing ? null : timeoutAt(time);
  let now = playing ? t('rally', { n: playing.i + 1 }) : pause ? timeoutLabel(t, pause) : t('betweenRallies');
  if (last) {
    const who = [groupName(t, last.g), playerLabel(t, last.person)].filter(Boolean).join(', ');
    now += ` · ${t('lastTouch', { type: t(`types.${last.type}`).toLowerCase(), who })}`;
  }
  const ends: [string, string] | undefined = hasTeams && sides ? [groupName(t, sides.left), groupName(t, (3 - sides.left) as Group)] : undefined;

  return (
    <figure className="m-0 min-w-0 [:fullscreen_&]:relative [:fullscreen_&]:flex [:fullscreen_&]:h-full [:fullscreen_&]:flex-col">
      {/* Boxed like the score bar beside it, at the same height; in full screen its content alone over the view. */}
      <div className="mb-3 flex h-11 items-center gap-2 rounded-lg bg-muted px-3 text-sm leading-5 font-semibold [:fullscreen_&]:absolute [:fullscreen_&]:inset-x-2 [:fullscreen_&]:top-2 [:fullscreen_&]:z-10 [:fullscreen_&]:mb-0 [:fullscreen_&]:bg-transparent [:fullscreen_&]:[text-shadow:0_0_4px_var(--background),0_0_10px_var(--background)]">
        <Tip label={now}>
          <p className="m-0 line-clamp-2 min-w-0 flex-1" aria-live="off">
            {now}
          </p>
        </Tip>
        {canDraw3d() && (
          <ToggleGroup type="single" variant="outline" size="sm" spacing={0} value={view} onValueChange={(v) => v && choose(v as View)} aria-label={t('scene3d.label')} className="shrink-0 bg-card">
            {VIEWS.map((v) => (
              <ToggleGroupItem key={v} value={v} className="px-2.5 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                {t(`scene3d.${v}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
        {!match.video && <Feedback inline />}
      </div>
      <div
        className="cursor-default select-none [:fullscreen_&]:min-h-0 [:fullscreen_&]:flex-1"
        onPointerDownCapture={() => {
          named.current = false;
        }}
        onPointerDown={(e) => {
          down.current = { x: e.clientX, y: e.clientY };
          // A tap away from a name shown only hides it.
          if (e.pointerType !== 'mouse' && !named.current && hover !== null) {
            named.current = true;
            setHover(null);
          }
        }}
        onClick={(e) => {
          if (!named.current && Math.hypot(e.clientX - down.current.x, e.clientY - down.current.y) < 5) {
            togglePlay(video);
          }
        }}
      >
        {view !== '2d' && (
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
        )}
        {/* Full screen: the court as large as the space allows, its end labels over its bottom. */}
        <div className={cn('relative [:fullscreen_&]:h-full', view !== '2d' && 'hidden')}>
          <Court
            role="img"
            aria-label={t('replayLabel')}
            ends={ends}
            className="[:fullscreen_&]:relative [:fullscreen_&]:flex [:fullscreen_&]:h-full [:fullscreen_&]:flex-col [:fullscreen_&>div]:absolute [:fullscreen_&>div]:inset-x-0 [:fullscreen_&>div]:bottom-1 [:fullscreen_&>svg]:min-h-0 [:fullscreen_&>svg]:flex-1"
          >
            {dots.map(({ person, x, y }) => {
              const team = match.people[person]?.team ?? 1;
              const mark = playerMark(person);
              return (
                <g
                  key={person}
                  onPointerEnter={(e) => e.pointerType === 'mouse' && setHover(person)}
                  onPointerLeave={(e) => e.pointerType === 'mouse' && setHover((h) => (h === person ? null : h))}
                  onPointerDown={(e) => {
                    if (e.pointerType !== 'mouse') {
                      named.current = true;
                      setHover((h) => (h === person ? null : person));
                    }
                  }}
                >
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
      </div>
      {captioned && <ReplayCaption />}
      {tv && <BroadcastControls voice={voice} onVoice={setVoice} />}
    </figure>
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
