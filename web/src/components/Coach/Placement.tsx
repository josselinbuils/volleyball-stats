import { useMemo, useState } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Legend } from '@/components/Court';
import { match, playerLabel, teamColor, teamEdge, type Group } from '@/lib/match';
import { remembered } from '@/lib/me';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useFormat, type Format } from '@/lib/format';
import { Section } from '@/components/Coach/Section';
import { OFF_M, type Defender, type Place, type Position } from '@/components/Coach/helpers/defense';
import { Tip } from '@/components/Tip';

// From a small screen up, each position in its place on the court: the front row 4 3 2, then 5 6 1.
const CELLS: Record<number, string> = {
  4: 'sm:col-start-1 sm:row-start-1',
  3: 'sm:col-start-2 sm:row-start-1',
  2: 'sm:col-start-3 sm:row-start-1',
  5: 'sm:col-start-1 sm:row-start-2',
  6: 'sm:col-start-2 sm:row-start-2',
  1: 'sm:col-start-3 sm:row-start-2',
};
const RING = 0.5;
const DOT = 0.4;

/** A player picked among `g`'s defenders, and for each position they defended, where they usually stood at the other
 * team's hits and where the perimeter defence puts them. */
export function Placement({ g, defenders }: { g: Group; defenders: Defender[] }) {
  const { t } = useTranslation();
  const sorted = useMemo(() => [...defenders].sort((a, b) => (playerLabel(t, a.person) ?? '').localeCompare(playerLabel(t, b.person) ?? '')), [defenders, t]);
  const [key, setKey] = useState(remembered);
  const shown = sorted.find((d) => d.key === key) ?? sorted[0];
  return (
    <Section title={t('coach.placement.title')} caption={t('coach.placement.caption')}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Select value={shown.key} onValueChange={setKey}>
          <SelectTrigger aria-label={t('coach.placement.pick')} className="w-full bg-card sm:w-72">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {sorted.map((d) => (
              <SelectItem key={d.key} value={d.key}>
                {playerLabel(t, d.person)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Legend>
          <span className="inline-flex items-center gap-1.5">
            <svg aria-hidden viewBox="-1 -1 2 2" className="size-3">
              <circle r={0.8} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            </svg>
            {t('coach.placement.usual')}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <svg aria-hidden viewBox="-1 -1 2 2" className="size-3">
              <circle r={0.8} fill="none" stroke="var(--foreground)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            </svg>
            {t('coach.placement.spot')}
          </span>
        </Legend>
      </div>
      <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-3">
        {shown.positions.map((p) => (
          <Card key={p.position} position={p} person={shown.person} g={g} />
        ))}
      </ul>
    </Section>
  );
}

/** What to do at a place, to the half metre: the places are not finer. */
function ways(t: TFunction, { num, dec }: Format, { usual, spot }: Place): string {
  const metres = (x: number) => {
    const m = Math.round(Math.abs(x) * 2) / 2;
    return Number.isInteger(m) ? num(m) : dec(m);
  };
  const [back, right] = [spot[0] - usual[0], spot[1] - usual[1]];
  const out = [
    ...(Math.abs(back) >= OFF_M ? [t(back > 0 ? 'coach.placement.back' : 'coach.placement.forward', { m: metres(back) })] : []),
    ...(Math.abs(right) >= OFF_M ? [t(right > 0 ? 'coach.placement.right' : 'coach.placement.left', { m: metres(right) })] : []),
  ];
  return out.length ? out.join(', ') : t('coach.placement.fine');
}

function Card({ position, person, g }: { position: Position; person: number; g: Group }) {
  const { t } = useTranslation();
  const format = useFormat();
  const { play } = usePlayer();
  const body = (
    <>
      <span className="flex items-center justify-between gap-2">
        <b className="font-semibold">{t('coach.placement.position', { n: position.position })}</b>
        {position.off.length > 0 && <Play aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />}
      </span>
      <HalfCourt places={position.places} g={g} />
      <span className="grid gap-0.5 text-[13px] text-muted-foreground">
        {position.places.map((p) => (
          <span key={p.role}>{p.role === 'back' ? ways(t, format, p) : t('coach.placement.line', { role: t(`coach.placement.roles.${p.role}`), ways: ways(t, format, p) })}</span>
        ))}
      </span>
    </>
  );
  const box = 'flex h-full w-full flex-col gap-1.5 rounded-lg border bg-card px-2.5 py-2 text-left';
  return (
    <li className={CELLS[position.position]}>
      {position.off.length ? (
        <Tip label={t('watchN', { count: position.off.length })}>
          <button
            type="button"
            onClick={() =>
              play(
                (tr) => tr('coach.placement.playing', { player: playerLabel(tr, person), n: position.position }),
                contactClips(position.off, match.duration).map(({ player: _, name: __, ...clip }) => clip),
              )
            }
            className={`${box} transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50`}
          >
            {body}
          </button>
        </Tip>
      ) : (
        <div className={box}>{body}</div>
      )}
    </li>
  );
}

/** One half seen from behind its end line, the net at the top: each place's spot ringed, the usual place a dot, an arrow
 * from it to the spot. One unit is a metre: x toward the player's right, y away from the net. */
function HalfCourt({ places, g }: { places: Place[]; g: Group }) {
  return (
    <svg aria-hidden viewBox="-5 -0.8 10 10.3" className="block h-auto w-full max-w-48 self-center overflow-visible">
      <rect x={-4.5} y={0} width={9} height={9} className="fill-court" />
      <rect x={-4.5} y={0} width={9} height={9} className="court-line" />
      <line x1={-4.5} x2={4.5} y1={3} y2={3} className="court-line" />
      <line x1={-5} x2={5} y1={0} y2={0} stroke="var(--muted-foreground)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {places.map(({ role, usual: [uy, ux], spot: [sy, sx] }) => {
        const far = Math.hypot(sx - ux, sy - uy);
        const [dx, dy] = [(sx - ux) / far, (sy - uy) / far];
        const [tx, ty] = [sx - dx * RING, sy - dy * RING];
        return (
          <g key={role}>
            <circle cx={sx} cy={sy} r={RING} fill="none" stroke="var(--foreground)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            {far > RING + DOT && (
              <>
                <line x1={ux + dx * DOT} y1={uy + dy * DOT} x2={tx - dx * 0.4} y2={ty - dy * 0.4} stroke="var(--foreground)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
                <polygon points={`${tx},${ty} ${tx - dx * 0.55 - dy * 0.3},${ty - dy * 0.55 + dx * 0.3} ${tx - dx * 0.55 + dy * 0.3},${ty - dy * 0.55 - dx * 0.3}`} fill="var(--foreground)" />
              </>
            )}
            <circle cx={ux} cy={uy} r={DOT} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
    </svg>
  );
}
