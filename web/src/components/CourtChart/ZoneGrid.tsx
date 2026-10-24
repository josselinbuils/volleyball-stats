import { useTranslation } from 'react-i18next';
import { useFormat } from '@/lib/format';
import { groupName, match, teamColor, teamRing, type Contact, type Group } from '@/lib/match';
import { cellContacts } from '@/components/CourtChart/helpers/zones';
import { SvgButton } from '@/components/CourtChart/SvgButton';

/** Each zone of each half, shaded by its share of the touches in the colour of the team playing
 * there (`left` on the left half), neutral when both teams played on it (`left` null), in the
 * colour of the `only` team shown when one is. */
export function ZoneGrid({ shown, left, only, onPlay }: { shown: Contact[]; left: Group | null; only: Group | null; onPlay: (title: string, contacts: Contact[]) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const inside = cellContacts(shown, match.zones);
  const max = Math.max(1, ...inside.map((cs) => cs.length));

  return match.zones.map((z, k) => {
    const n = inside[k].length;
    const team = only ?? (left === null ? null : ((z.x < 0 ? left : 3 - left) as Group));
    const cell = (
      <>
        <rect x={z.x + 0.06} y={z.y + 0.06} width={z.w - 0.12} height={z.h - 0.12} rx={0.2} fill={team ? teamColor(team) : 'var(--muted-foreground)'} stroke={team ? teamRing(team) : undefined} fillOpacity={0.06 + (0.5 * n) / max} className="[vector-effect:non-scaling-stroke]" />
        <text x={z.x + 0.3} y={z.y + 0.5} fontSize={0.5} fill="var(--muted-foreground)" dominantBaseline="central">
          {z.zone}
        </text>
        {n > 0 && (
          <>
            <text x={z.x + z.w / 2} y={z.y + z.h / 2 - 0.3} fontSize={0.85} fontWeight={650} textAnchor="middle" dominantBaseline="central" fill="var(--foreground)" className="halo">
              {f.num(n)}
            </text>
            <text x={z.x + z.w / 2} y={z.y + z.h / 2 + 0.5} fontSize={0.55} textAnchor="middle" dominantBaseline="central" fill="var(--foreground)" className="halo">
              {f.pct(n / shown.length)}
            </text>
          </>
        )}
      </>
    );
    if (!n) {
      return <g key={k}>{cell}</g>;
    }
    const title = t('zoneTitle', { z: z.zone, half: team ? groupName(t, team) : t(z.x < 0 ? 'leftSide' : 'rightSide') });
    return (
      <SvgButton key={k} label={`${title} · ${t('touchesN', { count: n })}`} onActivate={() => onPlay(title, inside[k])} className="[&:focus-visible_rect]:stroke-ring [&:focus-visible_rect]:stroke-[3px] [&:hover_rect]:stroke-foreground [&:hover_rect]:stroke-2">
        {cell}
      </SvgButton>
    );
  });
}
