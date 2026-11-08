import { useMemo, useState } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SetBadge } from '@/components/SetBadge';
import { GROUPS, groupName, hasTeams, match, type Group } from '@/lib/match';
import { remembered } from '@/lib/me';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { Section } from '@/components/Coach/Section';
import { Setters } from '@/components/Coach/Setters';
import { Placement } from '@/components/Coach/Placement';
import { Reception } from '@/components/Coach/Reception';
import { Jumps } from '@/components/Coach/Jumps';
import { setters, things, type Thing } from '@/components/Coach/helpers/coach';
import { attacksOn } from '@/components/Coach/helpers/defense';
import { jumpers } from '@/components/Coach/helpers/jumps';
import { servesOn } from '@/components/Coach/helpers/reception';
import { Tip } from '@/components/Tip';

/** What a coach reads for one team: what cost it points, who sets whom, each attacker's advice on their jumps and each
 * player's places in reception and in defence, those the only parts naming a player for a weak point (the owner's call). */
export function Coach() {
  const { t } = useTranslation();
  const { contacts, rallies } = useSet();
  const [picked, pick] = useState<Group>(() => (Number(remembered()?.split(':')[0]) === 2 ? 2 : 1));
  const read = useMemo(
    () =>
      GROUPS.map((g) => ({
        things: things(rallies, g),
        setters: setters(contacts, g, match.people),
        jumpers: jumpers(contacts, g, match.people),
        defended: attacksOn(contacts, g).length > 0,
        received: servesOn(contacts, g).length > 0,
      })),
    [contacts, rallies],
  );
  if (!hasTeams || read.every((r) => !r.things.found.length && !r.setters.length && !r.jumpers.length && !r.defended && !r.received)) {
    return null;
  }
  const { things: lost, setters: setting, jumpers: jumping, defended, received } = read[picked - 1];
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('coach.title')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t('coach.caption')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <ToggleGroup
          type="single"
          variant="outline"
          spacing={0}
          value={String(picked)}
          onValueChange={(v) => {
            if (v) {
              pick(Number(v) as Group);
            }
          }}
          aria-label={t('coach.teamFilter')}
          className="bg-card"
        >
          {GROUPS.map((g) => (
            <ToggleGroupItem key={g} value={String(g)} className="h-9 min-w-0 px-4 text-[15px] data-[state=on]:bg-primary data-[state=on]:font-semibold data-[state=on]:text-primary-foreground">
              <span className="truncate">{groupName(t, g)}</span>
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {lost.found.length > 0 && (
          <Section title={t('coach.things.title')} caption={t('coach.things.caption', { team: groupName(t, picked), count: lost.lost })}>
            <ol className="m-0 grid list-none gap-2 p-0 lg:grid-cols-3">
              {lost.found.map((thing, k) => (
                <ThingRow key={thing.cause} thing={thing} rank={k + 1} g={picked} />
              ))}
            </ol>
          </Section>
        )}
        {setting.length > 0 && <Setters setters={setting} />}
        {jumping.length > 0 && <Jumps jumpers={jumping} />}
        {received && <Reception key={picked} g={picked} contacts={contacts} />}
        {defended && <Placement key={picked} g={picked} contacts={contacts} />}
      </CardContent>
    </Card>
  );
}

function ThingRow({ thing, rank, g }: { thing: Thing; rank: number; g: Group }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const title = (tr: TFunction) => tr(`coach.things.names.${thing.cause}`);
  return (
    <li>
      <Tip label={t('watchN', { count: thing.n })}>
        <button
          type="button"
          onClick={() =>
            play(
              title,
              contactClips(thing.contacts, match.duration).map(({ player: _, name: __, ...clip }) => clip),
            )
          }
          className="flex h-full w-full items-start gap-2.5 rounded-lg border bg-card px-2.5 py-2 text-left transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <span aria-hidden className="inline-grid size-6 shrink-0 place-items-center rounded-full bg-foreground text-sm font-semibold text-background tabular-nums">
            {rank}
          </span>
          <span className="grid min-w-0 flex-1 gap-0.5">
            <b className="font-semibold">{title(t)}</b>
            <span className="text-sm font-medium tabular-nums">{t('coach.things.count', { count: thing.n, other: thing.other, team: groupName(t, (3 - g) as Group) })}</span>
            <span className="text-[13px] text-muted-foreground">{t(`coach.things.tips.${thing.cause}`)}</span>
          </span>
          <Play aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </Tip>
    </li>
  );
}
