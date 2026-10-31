import { useTranslation } from 'react-i18next';
import { teamColor, teamEdge, type Contact, type Placed } from '@/lib/match';
import { SvgButton } from '@/components/CourtChart/SvgButton';

/** One dot per touch in its team's colour, lettered with its action. Hundreds of them stay out of
 * the tab order: the zones view is the keyboard's way to the touches. */
export function ContactDots({ shown, describe, onPlay }: { shown: Placed[]; describe: (c: Contact) => string; onPlay: (c: Contact) => void }) {
  const { t } = useTranslation();
  return shown.map((c) => (
    <SvgButton key={c.i} label={describe(c)} onActivate={() => onPlay(c)} tabIndex={-1}>
      <circle cx={c.x} cy={c.y} r={0.7} fill="transparent" />
      <circle cx={c.x} cy={c.y} r={0.36} className="dot-mark" fill={teamColor(c.g)} stroke={teamEdge(c.g)} />
      <text x={c.x} y={c.y} className="dot-text" fill={`var(--team${c.g}-text)`}>
        {t(`short.${c.type}`)}
      </text>
    </SvgButton>
  ));
}
