import { useTranslation } from 'react-i18next';
import { useFormat } from '@/lib/format';
import { match, type Contact } from '@/lib/match';
import { cellContacts } from '@/components/CourtChart/helpers/zones';
import { SvgButton } from '@/components/CourtChart/SvgButton';

/** Each zone of each half, shaded by its share of the touches. */
export function ZoneGrid({ shown, onPlay }: { shown: Contact[]; onPlay: (title: string, contacts: Contact[]) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const inside = cellContacts(shown, match.zones);
  const max = Math.max(1, ...inside.map((cs) => cs.length));

  return match.zones.map((z, k) => {
    const n = inside[k].length;
    const cell = (
      <>
        <rect x={z.x + 0.06} y={z.y + 0.06} width={z.w - 0.12} height={z.h - 0.12} rx={0.2} fill="var(--chart)" fillOpacity={0.06 + (0.6 * n) / max} className="[vector-effect:non-scaling-stroke]" />
        <text x={z.x + 0.3} y={z.y + 0.5} fontSize={0.5} fill="var(--muted-foreground)" dominantBaseline="central">
          {z.zone}
        </text>
        {n > 0 && (
          <>
            <text x={z.x + z.w / 2} y={z.y + z.h / 2 - 0.3} fontSize={0.85} fontWeight={650} textAnchor="middle" dominantBaseline="central" fill="var(--foreground)">
              {f.num(n)}
            </text>
            <text x={z.x + z.w / 2} y={z.y + z.h / 2 + 0.5} fontSize={0.55} textAnchor="middle" dominantBaseline="central" fill="var(--foreground)" opacity={0.75}>
              {f.pct(n / shown.length)}
            </text>
          </>
        )}
      </>
    );
    if (!n) {
      return <g key={k}>{cell}</g>;
    }
    const title = t('zoneTitle', { z: z.zone, half: t(z.x < 0 ? 'leftHalf' : 'rightHalf') });
    return (
      <SvgButton key={k} label={`${title} · ${t('touchesN', { count: n })}`} onActivate={() => onPlay(title, inside[k])} className="[&:focus-visible_rect]:stroke-ring [&:focus-visible_rect]:stroke-[3px] [&:hover_rect]:stroke-chart [&:hover_rect]:stroke-2">
        {cell}
      </SvgButton>
    );
  });
}
