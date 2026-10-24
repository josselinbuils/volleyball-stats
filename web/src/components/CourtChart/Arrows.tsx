import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { color, teamColor, teamEdge, type Contact, type Placed } from '@/lib/match';
import type { Arrow } from '@/components/CourtChart/helpers/arrows';
import { SvgButton } from '@/components/CourtChart/SvgButton';

const DIM = 0.12;

/** Serves and attacks as the ball's flights, coloured by outcome, from the player who played them
 * to the next player or the ball on the floor. Points and faults lie over the balls still in play;
 * pointing at one flight dims the others. */
export function Arrows({ arrows, describe, onPlay }: { arrows: Arrow[]; describe: (c: Contact) => string; onPlay: (c: Contact) => void }) {
  const { t } = useTranslation();
  const [active, setActive] = useState<number | null>(null);
  const order = [...arrows].sort((a, b) => Number(a.result !== 'play') - Number(b.result !== 'play'));
  const opacity = (a: Arrow) => (active === null || a.from.i === active ? 1 : DIM);

  return (
    <>
      {order.map((a) => (
        <SvgButton
          key={a.from.i}
          label={`${describe(a.from)} → ${t(`types.${a.to.type}`).toLowerCase()} · ${t(`results.${a.result}`).toLowerCase()}`}
          onActivate={() => onPlay(a.from)}
          onMouseEnter={() => setActive(a.from.i)}
          onMouseLeave={() => setActive(null)}
          onFocus={() => setActive(a.from.i)}
          onBlur={() => setActive(null)}
          opacity={opacity(a)}
          className="transition-opacity duration-150"
          style={{ color: color(a.result) }}
        >
          <path d={a.shape} fill="currentColor" fillOpacity={a.result === 'play' ? 0.5 : 0.9} />
          <path d={a.curve} fill="none" stroke="transparent" strokeWidth={0.8} />
        </SvgButton>
      ))}
      {/* The players and balls above every flight; a click goes through to the flight. */}
      <g aria-hidden pointerEvents="none">
        {order.map((a) => (
          <g key={a.from.i} opacity={opacity(a)} className="transition-opacity duration-150">
            {a.landing ? <circle cx={a.to.x} cy={a.to.y} className="ball-mark" /> : <Dot c={a.to} />}
            <Dot c={a.from} />
          </g>
        ))}
      </g>
    </>
  );
}

/** A player's dot in their team's colour, with their number when known. */
function Dot({ c }: { c: Placed }) {
  return (
    <>
      <circle cx={c.x} cy={c.y} className="dot-mark" fill={teamColor(c.g)} stroke={teamEdge(c.g)} />
      {c.player !== null && (
        <text x={c.x} y={c.y} className="dot-text" fill={`var(--team${c.g}-text)`}>
          {c.player}
        </text>
      )}
    </>
  );
}
