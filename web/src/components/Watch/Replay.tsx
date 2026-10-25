import { useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';
import { Court, Legend } from '@/components/Court';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasNames, hasTeams, match, playerLabel, playerNumber, rallies, teamColor, teamEdge, teamRing, type Group } from '@/lib/match';
import { togglePlay, usePlayer, useVideoTime } from '@/lib/player';
import { usePlayers } from '@/lib/players';
import { rallyAt } from '@/lib/playlist';
import { ballAt, landingsAt, playersAt, sidesAt, touchesAt, trailAt } from '@/components/Watch/helpers/replay';
import { ball3dAt, jumpAt, trail3dAt } from '@/components/Watch/helpers/flight';
import { canDraw3d, Scene3D } from '@/components/Watch/Scene3D';

const STORED = 'court-view';

/** The court seen from above, players and ball following the video; its legend under it unless
 * `captioned` is false, the page then showing `ReplayCaption` itself. */
export function Replay({ captioned = true }: { captioned?: boolean }) {
  const { t } = useTranslation();
  const time = useVideoTime((now) => now);
  const players = usePlayers();
  const { video } = usePlayer();
  // Where the pointer went down: a click plays or pauses, a drag turning the 3D view does not.
  const down = useRef({ x: 0, y: 0 });
  const rally = rallyAt(rallies, time);
  const sides = sidesAt(rallies, time);
  const ball = rally ? ballAt(rally.contacts, time) : null;
  const trail = rally ? trailAt(rally.contacts, time) : [];
  const touches = rally ? touchesAt(rally.contacts, time) : [];
  const landings = rally ? landingsAt(rally.contacts, time) : [];
  const last = rally?.contacts.filter((c) => c.t <= time).pop();
  const dots = typeof players === 'object' ? playersAt(players, match.fps, time) : [];
  // The player under the pointer, named above their mark.
  const [hover, setHover] = useState<number | null>(null);
  const hovered = dots.find((d) => d.person === hover);
  const tip = hovered && playerLabel(t, hovered.person);
  // The view chosen last time, remembered by the browser when it can.
  const [view, setView] = useState<'2d' | '3d'>(() => {
    try {
      return localStorage.getItem(STORED) === '3d' && canDraw3d() ? '3d' : '2d';
    } catch {
      return '2d';
    }
  });
  const choose = (next: '2d' | '3d') => {
    setView(next);
    try {
      localStorage.setItem(STORED, next);
    } catch {
      // Private browsing: the choice lasts for the page only.
    }
  };

  let now = rally ? t('rally', { n: rally.i + 1 }) : t('betweenRallies');
  if (last) {
    const who = [groupName(t, last.g), playerLabel(t, last.person)].filter(Boolean).join(', ');
    now += ` · ${t('lastTouch', { type: t(`types.${last.type}`).toLowerCase(), who })}`;
  }
  const ends: [string, string] | undefined = hasTeams && sides ? [groupName(t, sides.left), groupName(t, (3 - sides.left) as Group)] : undefined;

  return (
    <figure className="m-0 min-w-0">
      {/* Boxed like the score bar beside it, at the same height. */}
      <div className="mb-3 flex h-11 items-center gap-2 rounded-lg bg-muted px-3 text-sm leading-5 font-semibold">
        <p className="m-0 line-clamp-2 min-w-0 flex-1" aria-live="off" title={now}>
          {now}
        </p>
        {canDraw3d() && (
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            spacing={0}
            value={view}
            onValueChange={(v) => v && choose(v as '2d' | '3d')}
            aria-label={t('scene3d.label')}
            className="shrink-0 bg-card"
          >
            {(['2d', '3d'] as const).map((v) => (
              <ToggleGroupItem key={v} value={v} className="px-2.5 text-xs data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                {t(`scene3d.${v}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
      </div>
      <div
        className="cursor-default select-none"
        onPointerDown={(e) => {
          down.current = { x: e.clientX, y: e.clientY };
        }}
        onClick={(e) => {
          if (Math.hypot(e.clientX - down.current.x, e.clientY - down.current.y) < 5) {
            togglePlay(video);
          }
        }}
      >
        {view === '3d' && (
          <Scene3D
            state={{
              players: dots.map(({ person, x, y }) => ({
                key: person,
                x,
                y,
                jump: rally ? jumpAt(rally.contacts, person, time) : 0,
                team: match.people[person]?.team ?? 1,
                label: String(playerNumber(person) ?? ''),
                tip: person === hover ? (tip ?? undefined) : undefined,
              })),
              ball: rally ? ball3dAt(rally.contacts, time) : null,
              trail: rally ? trail3dAt(rally.contacts, time) : [],
              rings: touches.flatMap(({ touch, f }) => {
                const at = dots.find((d) => d.person === touch.person) ?? (touch.x !== null && touch.y !== null ? { x: touch.x, y: touch.y } : null);
                return at ? [{ x: at.x, y: at.y, f }] : [];
              }),
              landings,
            }}
            onHover={setHover}
          />
        )}
        {/* The court's top margin is mostly empty: it tucks under the box. */}
        <div className={cn('relative -mt-4', view === '3d' && 'hidden')}>
          <Court role="img" aria-label={t('replayLabel')} ends={ends}>
            {dots.map(({ person, x, y }) => {
              const team = match.people[person]?.team ?? 1;
              const n = playerNumber(person);
              return (
                <g key={person} onPointerEnter={() => setHover(person)} onPointerLeave={() => setHover((h) => (h === person ? null : h))}>
                  <circle cx={x} cy={y} r={0.7} className="player-mark" fill={teamColor(team)} stroke={teamEdge(team)} />
                  {n !== null && (
                    <text x={x} y={y} className="player-text" fill={`var(--team${team}-text)`}>
                      {n}
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
          {players === 'loading' && (
            <p className="pointer-events-none absolute inset-x-0 top-0 bottom-6 m-0 grid place-items-center">
              <span className="rounded-md bg-card/90 px-2.5 py-1 text-sm text-muted-foreground shadow-xs">{t('loadingPlayers')}</span>
            </p>
          )}
        </div>
      </div>
      {captioned && <ReplayCaption />}
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

/** The court replay's legend: the teams, the ball, and how to read the players and the ball. */
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
    </div>
  );
}
