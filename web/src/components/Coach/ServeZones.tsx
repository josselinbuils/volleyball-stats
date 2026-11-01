import { useTranslation } from 'react-i18next';
import { groupName, match, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { SvgButton } from '@/components/CourtChart/SvgButton';
import { Section } from '@/components/Coach/Section';
import type { ZoneServes } from '@/components/Coach/helpers/coach';

/** Where `g`'s serves cause trouble, and where the other team's cause `g` trouble. */
export function ServeZones({ own, against, g, rallies }: { own: Map<number, ZoneServes>; against: Map<number, ZoneServes>; g: Group; rallies: number }) {
  const { t } = useTranslation();
  const name = groupName(t, g);
  return (
    <Section title={t('coach.zones.title')} caption={t('coach.zones.caption')}>
      <div className="grid max-w-2xl grid-cols-2 gap-3 sm:gap-6">
        <HalfCourt title={t('coach.zones.own', { team: name })} id={`coach:zone:own:${g}:${rallies}`} zones={own} />
        <HalfCourt title={t('coach.zones.against', { team: name })} id={`coach:zone:against:${g}:${rallies}`} zones={against} />
      </div>
    </Section>
  );
}

/** One half of the court, the net on the right, each zone with the serves there causing trouble out of all of them. A
 * zone is the same on either half, so serves from both ends add up. */
function HalfCourt({ title, id, zones }: { title: string; id: string; zones: Map<number, ZoneServes> }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const cells = match.zones.filter((z) => z.x < 0);
  return (
    <figure className="m-0 grid min-w-0 content-start gap-1">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <svg viewBox="-9.1 -4.6 9.6 9.2" className="block h-auto w-full">
        <rect x={-9} y={-4.5} width={9} height={9} className="fill-court" />
        {cells.map((z) => {
          const found = zones.get(z.zone);
          const of = found?.all.length ?? 0;
          const trouble = found?.trouble.length ?? 0;
          const cell = (
            <>
              <rect
                x={z.x + 0.06}
                y={z.y + 0.06}
                width={z.w - 0.12}
                height={z.h - 0.12}
                rx={0.2}
                fill="var(--error)"
                fillOpacity={of ? 0.06 + (0.6 * trouble) / of : 0}
                className="[vector-effect:non-scaling-stroke]"
              />
              <text x={z.x + 0.25} y={z.y + 0.45} fontSize={0.5} fill="var(--muted-foreground)" dominantBaseline="central">
                {z.zone}
              </text>
              {of > 0 && (
                <text x={z.x + z.w / 2} y={z.y + z.h / 2} fontSize={0.8} fontWeight={650} textAnchor="middle" dominantBaseline="central" fill="var(--foreground)" className="halo">
                  {trouble}/{of}
                </text>
              )}
            </>
          );
          if (!trouble) {
            return <g key={z.zone}>{cell}</g>;
          }
          return (
            <SvgButton
              key={z.zone}
              label={t('coach.zones.cell', { zone: z.zone, trouble, of })}
              onActivate={() => play((tr) => tr('coach.zones.cellTitle', { title, zone: z.zone }), contactClips(found?.trouble ?? [], match.duration), 0, `${id}:${z.zone}`)}
              className="[&:focus-visible_rect]:stroke-ring [&:focus-visible_rect]:stroke-[3px] [&:hover_rect]:stroke-foreground [&:hover_rect]:stroke-2"
            >
              {cell}
            </SvgButton>
          );
        })}
        <rect x={-9} y={-4.5} width={9} height={9} fill="none" className="court-line" />
        <line x1={0} x2={0} y1={-4.6} y2={4.6} stroke="var(--muted-foreground)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      </svg>
    </figure>
  );
}
