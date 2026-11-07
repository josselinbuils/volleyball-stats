import { useMemo, useState, type ReactNode } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Legend } from '@/components/Court';
import { match, playerLabel, teamColor, teamEdge, type Contact, type Group } from '@/lib/match';
import { remembered } from '@/lib/me';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useFormat, type Format } from '@/lib/format';
import { Section } from '@/components/Coach/Section';
import { attacksOn, defenders, OFF_M, sideOf, SIDES, type Place, type Position, type Side } from '@/components/Coach/helpers/defense';
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

const median = (xs: number[]) => [...xs].sort((a, b) => a - b)[xs.length >> 1];

/** A player picked among `g`'s defenders, a defence system and the side the other team attacks from; for each position
 * the player defended there, the attacks and where they went, where the player usually stood at the hit and their spot. */
export function Placement({ g, contacts }: { g: Group; contacts: Contact[] }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState(0);
  const attacks = useMemo(() => attacksOn(contacts, g), [contacts, g]);
  const [side, setSide] = useState<Side>(() => SIDES.reduce((a, b) => (attacks.filter((c) => sideOf(c) === b).length > attacks.filter((c) => sideOf(c) === a).length ? b : a)));
  const bySide = useMemo(() => Object.fromEntries(SIDES.map((s) => [s, defenders(contacts, g, match.people, mode, s)])), [contacts, g, mode]);
  const players = useMemo(() => {
    const all = new Map(SIDES.flatMap((s) => bySide[s].map((d) => [d.key, d.person] as const)));
    return [...all].map(([key, person]) => ({ key, person, label: playerLabel(t, person) ?? key })).sort((a, b) => a.label.localeCompare(b.label));
  }, [bySide, t]);
  const [key, setKey] = useState(remembered);
  if (!players.length) {
    return null;
  }
  const picked = players.find((p) => p.key === key) ?? players[0];
  const positions = bySide[side].find((d) => d.key === picked.key)?.positions ?? [];
  const modeName = match.defenseModes[mode];
  return (
    <Section title={t('coach.placement.title')} caption={t('coach.placement.caption')}>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={picked.key} onValueChange={setKey}>
          <SelectTrigger aria-label={t('coach.placement.pick')} className="w-full bg-card sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {players.map((p) => (
              <SelectItem key={p.key} value={p.key}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={String(mode)} onValueChange={(v) => setMode(Number(v))}>
          <SelectTrigger aria-label={t('coach.placement.system')} className="w-full bg-card sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {match.defenseModes.map((m, n) => (
              <SelectItem key={m} value={String(n)}>
                {t(`coach.placement.modes.${m}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2 max-sm:w-full">
          <span className="text-sm text-muted-foreground">{t('coach.placement.attack')}</span>
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            value={side}
            onValueChange={(v) => {
              if (v) {
                setSide(v as Side);
              }
            }}
            aria-label={t('coach.placement.from')}
            className="bg-card max-sm:flex-1"
          >
            {SIDES.map((s) => (
              <ToggleGroupItem key={s} value={s} className="h-9 min-w-0 px-3 data-[state=on]:bg-primary data-[state=on]:font-semibold data-[state=on]:text-primary-foreground max-sm:flex-1">
                {t(`coach.placement.sides.${s}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </div>
      {modeName === 'learned' && match.learned && <p className="text-sm text-muted-foreground">{t('coach.placement.learned', { count: match.learned.matches, balls: match.learned.balls })}</p>}
      <Legend>
        <Glyph label={t('coach.placement.attacker')}>
          <circle r={0.8} fill={teamColor((3 - g) as Group)} stroke={teamEdge((3 - g) as Group)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
        <Glyph label={t('coach.placement.ball')}>
          <line x1={-0.9} x2={0.9} y1={0} y2={0} stroke={teamColor((3 - g) as Group)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
        <Glyph label={t('coach.placement.usual')}>
          <circle r={0.8} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
        <Glyph label={t('coach.placement.spot')}>
          <circle r={0.8} fill="none" stroke="var(--foreground)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
      </Legend>
      {positions.length ? (
        <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-3">
          {positions.map((p) => (
            <Card key={p.position} position={p} person={picked.person} g={g} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{t('coach.placement.none')}</p>
      )}
    </Section>
  );
}

function Glyph({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg aria-hidden viewBox="-1 -1 2 2" className="size-3">
        {children}
      </svg>
      {label}
    </span>
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
      <HalfCourt position={position} g={g} />
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

/** One half seen from behind its end line, the net at the top and the other team's 3 m beyond it: the attacker where
 * they usually hit from, each attack's ball to where it went, each place's spot ringed, the usual place a dot, an arrow
 * from it to the spot. One unit is a metre: x toward the defenders' right, y away from the net. */
function HalfCourt({ position, g }: { position: Position; g: Group }) {
  const flights = position.attacks.map((c) => c.flight as number[]);
  const them = (3 - g) as Group;
  const [hitDepth, hitAcross] = [median(flights.map((f) => f[0])), median(flights.map((f) => f[1]))];
  return (
    <svg aria-hidden viewBox="-5 -3.6 10 13.1" className="block h-auto w-full max-w-48 self-center">
      <rect x={-4.5} y={-3} width={9} height={3} className="fill-court opacity-50" />
      <rect x={-4.5} y={0} width={9} height={9} className="fill-court" />
      <rect x={-4.5} y={0} width={9} height={9} className="court-line" />
      <line x1={-4.5} x2={4.5} y1={3} y2={3} className="court-line" />
      <line x1={-4.5} x2={4.5} y1={-3} y2={-3} className="court-line opacity-50" />
      <line x1={-5} x2={5} y1={0} y2={0} stroke="var(--muted-foreground)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {flights
        .filter((f) => f.length === 4)
        .map((f, k) => (
          <g key={k} opacity={0.4}>
            <line x1={f[1]} y1={f[0]} x2={f[3]} y2={f[2]} stroke={teamColor(them)} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            <circle cx={f[3]} cy={f[2]} r={0.15} fill={teamColor(them)} />
          </g>
        ))}
      <circle cx={hitAcross} cy={Math.max(hitDepth, -3)} r={DOT} fill={teamColor(them)} stroke={teamEdge(them)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      {position.places.map(({ role, usual: [uy, ux], spot: [sy, sx] }) => {
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
