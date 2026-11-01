import { useMemo } from 'react';
import { BatteryFull, Crosshair, Hammer, Hourglass, Mountain, Music, Shield, ShieldCheck, Timer, Users, type LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { useFormat } from '@/lib/format';
import { GROUPS, hasTeams, match, playerLabel, rallies as allRallies } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips, rallyClips, type Clip } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { lines } from '@/components/Stats/helpers/stats';
import { GOLD_CSS } from '@/components/Stats/Mvp';
import { trophies, type Trophy } from '@/components/Trophies/helpers/trophies';

const ICONS: Record<string, LucideIcon> = {
  touches: BatteryFull,
  kills: Hammer,
  blockPoints: Shield,
  aces: Crosshair,
  digs: ShieldCheck,
  sets: Music,
  perfect: Mountain,
  serveRun: Timer,
  duo: Users,
  longest: Hourglass,
};

/** Who won a trophy, a tie's players joined, the last two by "and". */
function winners(t: TFunction, trophy: Trophy): string | null {
  if (trophy.kind === 'longest') {
    return null;
  }
  if (trophy.kind === 'duo') {
    return t('trophies.duoNames', { setter: playerLabel(t, trophy.setter), attacker: playerLabel(t, trophy.attacker) });
  }
  const names = trophy.people.map((p) => playerLabel(t, p) ?? '');
  return names.length > 1 ? t('trophies.and', { a: names.slice(0, -1).join(', '), b: names[names.length - 1] }) : names[0];
}

function clips(trophy: Trophy): Clip[] {
  if (trophy.kind === 'longest') {
    return rallyClips([trophy.rally], match.duration);
  }
  if (trophy.kind === 'serveRun') {
    return rallyClips(
      allRallies.filter((r) => trophy.rallies.includes(r.i)),
      match.duration,
    );
  }
  return contactClips(trophy.contacts, match.duration);
}

/** The match's awards, for what players did well, each replaying its moments. */
export function Trophies() {
  const { t } = useTranslation();
  const { set, contacts, rallies } = useSet();
  const withPlayers = hasTeams && Object.values(match.people).some((p) => p.number !== null);
  const won = useMemo(
    () =>
      withPlayers
        ? trophies(
            GROUPS.flatMap((g) => lines(contacts, match.people, g)),
            contacts,
            rallies,
            match.people,
          )
        : [],
    [withPlayers, contacts, rallies],
  );
  if (!won.length) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('trophies.title')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t('trophies.caption')}</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-2 p-0">
          {won.map((trophy) => (
            <Award key={trophy.kind} id={`trophy:${set}:${trophy.kind}`} trophy={trophy} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function Award({ id, trophy }: { id: string; trophy: Trophy }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play } = usePlayer();
  const Icon = ICONS[trophy.kind];
  const on = playlist?.key === id;
  const name = t(`trophies.names.${trophy.kind}`);
  const who = winners(t, trophy);
  const detail =
    trophy.kind === 'longest'
      ? t('trophies.details.longest', { n: trophy.n, seconds: f.secs(trophy.seconds) })
      : t(`trophies.details.${trophy.kind}`, { count: trophy.n, of: trophy.kind === 'duo' ? trophy.of : undefined });
  return (
    <li>
      <button
        type="button"
        aria-pressed={on}
        title={t('watchN', { count: clips(trophy).length })}
        onClick={() => play((tr) => [tr(`trophies.names.${trophy.kind}`), winners(tr, trophy)].filter(Boolean).join(', '), clips(trophy), 0, id)}
        className={cn(
          'flex h-full w-full items-start gap-2.5 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
          on && 'border-primary bg-primary/8 hover:bg-primary/12',
        )}
      >
        <span aria-hidden className="inline-grid size-9 shrink-0 place-items-center rounded-full text-[#3a2a00] shadow-sm" style={{ background: GOLD_CSS }}>
          <Icon className="size-5" />
        </span>
        <span className="grid min-w-0 gap-0.5">
          <b className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{name}</b>
          {who && <span className="font-semibold [overflow-wrap:anywhere]">{who}</span>}
          <span className="text-[13px] text-muted-foreground">{detail}</span>
        </span>
      </button>
    </li>
  );
}
