import { useMemo, useState } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Legend } from '@/components/Court';
import { color, match, playerLabel, teamColor, teamEdge, type Contact, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { Section } from '@/components/Coach/Section';
import { Arrow, DOT, Glyph, HalfCourt } from '@/components/Coach/CourtMarks';
import { FORMATIONS, MODES, receivers, type Formation, type Mode, type Taken } from '@/components/Coach/helpers/reception';
import { Tip } from '@/components/Tip';

// The player select's value for nobody.
const NOBODY = 'nobody';
// Where the players staying at the net stand, [x, y, width, height] in metres, drawn as one zone.
const NET_ZONE = [-2.25, 0.2, 4.5, 2.6] as const;

/** A reception system and, if picked, one of `g`'s players; one card with the system's spots and, where the player took
 * them, their usual place at each, and at the net. */
export function Reception({ g, contacts }: { g: Group; contacts: Contact[] }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>('three');
  const formation = FORMATIONS[mode];
  const found = useMemo(() => receivers(contacts, g, match.people, formation), [contacts, g, formation]);
  const players = useMemo(() => found.map((r) => ({ ...r, label: playerLabel(t, r.person) ?? r.key })).sort((a, b) => a.label.localeCompare(b.label)), [found, t]);
  const [key, setKey] = useState<string | null>(null);
  const picked = players.find((p) => p.key === key) ?? null;
  return (
    <Section title={t('coach.reception.title')} caption={t('coach.reception.caption')}>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={mode} onValueChange={(v) => setMode(v as Mode)}>
          <SelectTrigger aria-label={t('coach.reception.system')} className="w-full bg-card sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODES.map((m) => (
              <SelectItem key={m} value={m}>
                {t(`coach.reception.modes.${m}`)}
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
        {picked && (
          <Glyph label={t('coach.placement.usual')}>
            <circle r={0.8} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          </Glyph>
        )}
        <Glyph label={t('coach.placement.spot')}>
          <circle r={0.8} fill={color('point')} stroke="var(--card)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        </Glyph>
        <Glyph label={t('coach.reception.net')}>
          <rect x={-0.9} y={-0.7} width={1.8} height={1.4} rx={0.3} className="fill-foreground/15 stroke-foreground/40" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        </Glyph>
      </Legend>
      <ul className="m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-3 lg:gap-4">
        <Card formation={formation} taken={picked?.taken ?? []} person={picked?.person ?? null} g={g} />
      </ul>
    </Section>
  );
}

/** The court, replaying the serves the picked player stood 1 m or more off their spot. */
function Card({ formation, taken, person, g }: { formation: Formation; taken: Taken[]; person: number | null; g: Group }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const off = taken.flatMap((x) => x.off).sort((a, b) => a.t - b.t);
  const body = (
    <>
      <span className="flex items-start justify-between gap-2">
        <b className="font-semibold">{t('coach.reception.serve')}</b>
        {off.length > 0 && <Play aria-hidden className="mt-1 size-3.5 shrink-0 text-muted-foreground" />}
      </span>
      <HalfCourt>
        <rect x={NET_ZONE[0]} y={NET_ZONE[1]} width={NET_ZONE[2]} height={NET_ZONE[3]} rx={0.4} className="fill-foreground/15 stroke-foreground/40" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        {taken.map(({ spot, usual: [uy, ux] }) => (
          <circle key={spot ?? 'net'} cx={ux} cy={uy} r={DOT} fill={teamColor(g)} stroke={teamEdge(g)} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        ))}
        {formation.spots.map(([y, x], k) => (
          <circle key={k} cx={x} cy={y} r={DOT} fill={color('point')} stroke="var(--card)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        ))}
        {taken.map(({ spot, usual: [uy, ux] }) => spot !== null && <Arrow key={spot} from={[ux, uy]} to={[formation.spots[spot][1], formation.spots[spot][0]]} />)}
      </HalfCourt>
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
                (tr) => tr('coach.reception.playing', { player: playerLabel(tr, person) }),
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
