import { useMemo, useState } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Legend } from '@/components/Court';
import { color, match, playerLabel, teamColor, teamEdge, type Contact, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { Section } from '@/components/Coach/Section';
import { BLOCKS, defenders, SIDES, spotsOf, type Played, type Side } from '@/components/Coach/helpers/defense';
import { Tip } from '@/components/Tip';
import { Arrow, DOT, Glyph, HalfCourt as Court } from '@/components/Coach/CourtMarks';

// The attacker 1 m off the net, across as `match.defense` puts them, the spots drawn against them.
const HIT_DEPTH = -1;
// The player select's value for nobody.
const NOBODY = 'nobody';
// Where the setter plays in front: the team's at 2, else at 3.
const SETTERS = [2, 3];

/** A defence system, the setter's position and, if picked, one of `g`'s players; a card per side the other team attacks from and block, with
 * every position's spot in the system and, where the player defended there, their usual place at each position. */
export function Placement({ g, contacts }: { g: Group; contacts: Contact[] }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState(0);
  const [setter, setSetter] = useState(2);
  const found = useMemo(() => defenders(contacts, g, match.people, mode, setter), [contacts, g, mode, setter]);
  const players = useMemo(() => found.map((d) => ({ ...d, label: playerLabel(t, d.person) ?? d.key })).sort((a, b) => a.label.localeCompare(b.label)), [found, t]);
  const [key, setKey] = useState<string | null>(null);
  if (!match.defense) {
    return null;
  }
  const picked = players.find((p) => p.key === key) ?? null;
  return (
    <Section title={t('coach.placement.title')} caption={t('coach.placement.caption')}>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={String(mode)} onValueChange={(v) => setMode(Number(v))}>
          <SelectTrigger aria-label={t('coach.placement.system')} className="w-full bg-card sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {match.defense.modes.map((m, n) => (
              <SelectItem key={m} value={String(n)}>
                {t(`coach.placement.modes.${m}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={String(setter)} onValueChange={(v) => setSetter(Number(v))}>
          <SelectTrigger aria-label={t('coach.placement.setter')} className="w-full bg-card sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SETTERS.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {t('coach.placement.setterAt', { n })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={picked?.key ?? NOBODY} onValueChange={(v) => setKey(v === NOBODY ? null : v)}>
          <SelectTrigger aria-label={t('coach.placement.pick')} className="w-full bg-card sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NOBODY}>{t('coach.placement.nobody')}</SelectItem>
            {players.map((p) => (
              <SelectItem key={p.key} value={p.key}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Legend>
        <Glyph label={t('coach.placement.attacker')}>
          <circle r={0.8} fill={teamColor((3 - g) as Group)} stroke={teamEdge((3 - g) as Group)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
        {picked && (
          <Glyph label={t('coach.placement.usual')}>
            <circle r={0.8} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          </Glyph>
        )}
        <Glyph label={t('coach.placement.spot')}>
          <circle r={0.8} fill={color('point')} stroke="var(--card)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
      </Legend>
      <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-3 lg:gap-4">
        {BLOCKS.flatMap((block) =>
          SIDES.map((side) => (
            <Card
              key={`${side} ${block}`}
              side={side}
              block={block}
              mode={mode}
              setter={setter}
              played={picked?.played.filter((p) => p.side === side && p.block === block) ?? []}
              person={picked?.person ?? null}
              g={g}
            />
          )),
        )}
      </ul>
    </Section>
  );
}

/** A side and block's court, replaying the attacks the picked player stood 1 m or more off their spot. */
function Card({ side, block, mode, setter, played, person, g }: { side: Side; block: number; mode: number; setter: number; played: Played[]; person: number | null; g: Group }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const off = played.flatMap((p) => p.off).sort((a, b) => a.t - b.t);
  const body = (
    <>
      {/* The block goes whole to a second line where both do not fit; two lines kept there, so the courts line up. */}
      <span className="flex min-h-[2lh] items-start justify-between gap-2 lg:min-h-0">
        <span className="flex flex-wrap gap-x-1">
          <b className="font-semibold">
            {t(`coach.placement.sides.${side}`)}
            <span className="font-normal text-muted-foreground">,</span>
          </b>
          <span className="whitespace-nowrap text-muted-foreground">{t('coach.placement.blocks', { count: block })}</span>
        </span>
        {off.length > 0 && <Play aria-hidden className="mt-1 size-3.5 shrink-0 text-muted-foreground" />}
      </span>
      <HalfCourt side={side} block={block} mode={mode} setter={setter} played={played} g={g} />
    </>
  );
  const box = 'flex h-full w-full flex-col gap-1.5 rounded-lg border bg-card px-2.5 py-2 text-left';
  return (
    <li>
      {off.length && person !== null ? (
        <Tip label={t('watchN', { count: off.length })}>
          <button
            type="button"
            onClick={() =>
              play(
                (tr) => tr('coach.placement.playing', { player: playerLabel(tr, person) }),
                contactClips(off, match.duration).map(({ player: _, name: __, ...clip }) => clip),
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

/** A half court (`Court`): the attacker, every position's spot a green dot numbered and, for each position the player
 * defended there, their usual place a dot in the team's colour numbered too, an arrow from it to the spot. */
function HalfCourt({ side, block, mode, setter, played, g }: { side: Side; block: number; mode: number; setter: number; played: Played[]; g: Group }) {
  const them = (3 - g) as Group;
  const spots = spotsOf(mode, side, block, setter);
  const number = (x: number, y: number, n: number, fill: string) => (
    <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={0.7} fontWeight={700} fill={fill}>
      {n}
    </text>
  );
  return (
    <Court>
      <circle cx={match.defense?.attackers[side] ?? 0} cy={HIT_DEPTH} r={DOT} fill={teamColor(them)} stroke={teamEdge(them)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      {played.map(({ position, usual: [uy, ux] }) => (
        <g key={position}>
          <circle cx={ux} cy={uy} r={DOT} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          {number(ux, uy, position, `var(--team${g}-text)`)}
        </g>
      ))}
      {spots.map(({ position, spot: [y, x] }) => (
        <g key={position}>
          <circle cx={x} cy={y} r={DOT} fill={color('point')} stroke="var(--card)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          {number(x, y, position, 'white')}
        </g>
      ))}
      {played.map(({ position, usual: [uy, ux] }) => {
        const [sy, sx] = (spots.find((s) => s.position === position) as { spot: [number, number] }).spot;
        return <Arrow key={position} from={[ux, uy]} to={[sx, sy]} />;
      })}
    </Court>
  );
}
