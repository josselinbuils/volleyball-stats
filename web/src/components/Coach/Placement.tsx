import { useMemo, useState, type ReactNode } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Legend } from '@/components/Court';
import { color, match, playerLabel, teamColor, teamEdge, type Contact, type Group } from '@/lib/match';
import { remembered } from '@/lib/me';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useFormat, type Format } from '@/lib/format';
import type { TFunction } from 'i18next';
import { Section } from '@/components/Coach/Section';
import { defenders, OFF_M, type Place, type Situation } from '@/components/Coach/helpers/defense';
import { Tip } from '@/components/Tip';

const DOT = 0.4;

const median = (xs: number[]) => [...xs].sort((a, b) => a - b)[xs.length >> 1];

/** A player picked among `g`'s defenders and a defence system; a card per situation the player defended (position,
 * side the attack came from, block, role): the attacks and where they went, every position's spot, where the player usually
 * stood at the hit and their spot. */
export function Placement({ g, contacts }: { g: Group; contacts: Contact[] }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState(0);
  const found = useMemo(() => defenders(contacts, g, match.people, mode), [contacts, g, mode]);
  const players = useMemo(() => found.map((d) => ({ ...d, label: playerLabel(t, d.person) ?? d.key })).sort((a, b) => a.label.localeCompare(b.label)), [found, t]);
  const [key, setKey] = useState(remembered);
  if (!players.length) {
    return null;
  }
  const picked = players.find((p) => p.key === key) ?? players[0];
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
      </div>
      {match.defenseModes[mode] === 'learned' && match.learned && (
        <p className="text-sm text-muted-foreground">{t('coach.placement.learned', { count: match.learned.matches, balls: match.learned.balls })}</p>
      )}
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
          <circle r={0.8} fill={color('point')} stroke="var(--card)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
      </Legend>
      <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-3 lg:grid-cols-5">
        {picked.situations.map((s) => (
          <Card key={`${s.position} ${s.side} ${s.block} ${s.place.role}`} situation={s} person={picked.person} g={g} />
        ))}
      </ul>
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

/** After a role and a colon, the advice starts lowercase. */
const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

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

/** A situation's court, replaying the attacks its player stood OFF_M or more off their spot. */
function Card({ situation, person, g }: { situation: Situation; person: number; g: Group }) {
  const { t } = useTranslation();
  const format = useFormat();
  const { play } = usePlayer();
  const { place, position } = situation;
  const body = (
    <>
      <span className="flex items-center justify-between gap-2">
        <b className="font-semibold">{t('coach.placement.position', { n: position })}</b>
        {situation.off.length > 0 && <Play aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />}
      </span>
      <HalfCourt situation={situation} g={g} />
      <span className="text-[13px] text-muted-foreground">
        {t(`coach.placement.sides.${situation.side}`)} · {t('coach.placement.blocks', { count: situation.block })}
      </span>
      <span className="text-[13px]">
        {place.role === 'back' ? ways(t, format, place) : t('coach.placement.line', { role: t(`coach.placement.roles.${place.role}`), ways: lower(ways(t, format, place)) })}
      </span>
    </>
  );
  const box = 'flex h-full w-full flex-col gap-1.5 rounded-lg border bg-card px-2.5 py-2 text-left';
  return (
    <li>
      {situation.off.length ? (
        <Tip label={t('watchN', { count: situation.off.length })}>
          <button
            type="button"
            onClick={() =>
              play(
                (tr) => tr('coach.placement.playing', { player: playerLabel(tr, person), n: position }),
                contactClips(situation.off, match.duration).map(({ player: _, name: __, ...clip }) => clip),
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
 * they usually hit from, the balls theirs to play to where they went, every position's spot a pale green dot numbered, the
 * player's usual place a dot in the team's colour, their spot a green one, an arrow between them. One unit is a metre:
 * x toward the defenders' right, y away from the net. */
function HalfCourt({ situation, g }: { situation: Situation; g: Group }) {
  const flights = situation.mine.map((c) => c.flight as number[]);
  const them = (3 - g) as Group;
  const hits = situation.attacks.map((c) => c.flight as number[]);
  const [hitDepth, hitAcross] = [median(hits.map((f) => f[0])), median(hits.map((f) => f[1]))];
  const {
    usual: [uy, ux],
    spot: [sy, sx],
  } = situation.place;
  const far = Math.hypot(sx - ux, sy - uy);
  const [dx, dy] = [(sx - ux) / far, (sy - uy) / far];
  const [tx, ty] = [sx - dx * DOT, sy - dy * DOT];
  const number = (x: number, y: number, n: number, fill: string) => (
    <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={0.55} fontWeight={700} fill={fill}>
      {n}
    </text>
  );
  return (
    <svg aria-hidden viewBox="-5 -3.6 10 13.1" className="block h-auto w-full">
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
      <circle cx={Math.min(4.5, Math.max(-4.5, hitAcross))} cy={Math.max(hitDepth, -3)} r={DOT} fill={teamColor(them)} stroke={teamEdge(them)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      {situation.spots
        .filter((s) => s.position !== situation.position)
        .map(({ position, spot: [y, x] }) => (
          <g key={position}>
            <circle cx={x} cy={y} r={DOT} fill={color('point')} opacity={0.35} />
            {number(x, y, position, 'var(--foreground)')}
          </g>
        ))}
      <circle cx={ux} cy={uy} r={DOT} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      {far > 2 * DOT + 0.7 && (
        <>
          <line x1={ux + dx * DOT} y1={uy + dy * DOT} x2={tx - dx * 0.4} y2={ty - dy * 0.4} stroke="var(--foreground)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          <polygon points={`${tx},${ty} ${tx - dx * 0.55 - dy * 0.3},${ty - dy * 0.55 + dx * 0.3} ${tx - dx * 0.55 + dy * 0.3},${ty - dy * 0.55 - dx * 0.3}`} fill="var(--foreground)" />
        </>
      )}
      <circle cx={sx} cy={sy} r={DOT} fill={color('point')} stroke="var(--card)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      {number(sx, sy, situation.position, 'white')}
    </svg>
  );
}
