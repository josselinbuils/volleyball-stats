import { useTranslation } from 'react-i18next';
import { color, teamColor, teamEdge, type Contact } from '@/lib/match';
import type { Arrow } from '@/components/CourtChart/helpers/arrows';
import { SvgButton } from '@/components/CourtChart/SvgButton';

/** Serve and attack arrows, coloured by outcome, from the player who played them: their team's
 * colour and number. */
export function Arrows({ arrows, describe, onPlay }: { arrows: Arrow[]; describe: (c: Contact) => string; onPlay: (c: Contact) => void }) {
  const { t } = useTranslation();
  return (
    <>
      {arrows.map(({ from, to, result, landing, line: [x1, y1, x2, y2], head }) => (
        <SvgButton
          key={from.i}
          label={`${describe(from)} → ${t(`types.${to.type}`).toLowerCase()} · ${t(`results.${result}`).toLowerCase()}`}
          onActivate={() => onPlay(from)}
          opacity={0.8}
          className="hover:opacity-100 focus-visible:opacity-100 [&:focus-visible_.shaft]:stroke-[0.18]"
          style={{ color: color(result) }}
        >
          <line x1={x1} y1={y1} x2={x2} y2={y2} className="shaft" stroke="currentColor" strokeWidth={0.09} strokeLinecap="round" />
          <polygon points={head} fill="currentColor" />
          {landing && (
            <>
              <ellipse cx={to.x} cy={to.y} rx={0.45} ry={0.3} fill="currentColor" fillOpacity={0.25} />
              <circle cx={to.x} cy={to.y} r={0.18} fill="currentColor" stroke="var(--card)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
            </>
          )}
          <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="transparent" strokeWidth={0.8} />
        </SvgButton>
      ))}
      {/* The players above every arrow; a click goes through to the arrow. */}
      <g aria-hidden pointerEvents="none">
        {arrows.map(({ from }) => (
          <g key={from.i}>
            <circle cx={from.x} cy={from.y} className="dot-mark" fill={teamColor(from.g)} stroke={teamEdge(from.g)} />
            {from.player !== null && (
              <text x={from.x} y={from.y} className="dot-text" fill={`var(--team${from.g}-text)`}>
                {from.player}
              </text>
            )}
          </g>
        ))}
      </g>
    </>
  );
}
