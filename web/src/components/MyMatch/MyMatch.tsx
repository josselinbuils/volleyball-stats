import { useMemo, useState, type ReactNode } from 'react';
import { Play, Trophy } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select';
import { SetBadge } from '@/components/SetBadge';
import { clock, useFormat } from '@/lib/format';
import { contacts as allContacts, GROUPS, groupName, hasTeams, match, playerLabel, rallies as allRallies, type Contact, type Group } from '@/lib/match';
import { remember, remembered } from '@/lib/me';
import { playerKey } from '@/helpers/players';
import { duos, serveRun } from '@/helpers/plays';
import { usePlayer } from '@/lib/player';
import { contactClips, rallyClips, type Clip } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { bestPlayer, playingTime } from '@/components/Stats/helpers/best';
import { strengths, toWorkOn } from '@/components/Stats/helpers/strengths';
import { lines, type Stat } from '@/components/Stats/helpers/stats';
import { InsightChip } from '@/components/Stats/StatsTable';
import { highlights, measures, tops } from '@/components/MyMatch/helpers/myMatch';
import { PlayerCard, type CardRow } from '@/components/MyMatch/PlayerCard';

// What a player can lead their team in.
const TOPS: readonly Stat[] = ['points', 'kills', 'aces', 'blockPoints', 'digs', 'receptions', 'sets'];
// What a player mostly does, the serves left out: everyone serves.
const MAIN = ['sets', 'attacks', 'receptions', 'digs'] as const;
const DUOS_SHOWN = 4;

/** Every identified player who touched the ball in the match, by team, named first. */
function everyone(t: TFunction): { g: Group; players: { key: string; label: string }[] }[] {
  return GROUPS.map((g) => ({
    g,
    players: lines(allContacts, match.people, g)
      .flatMap((l) => {
        const key = typeof l.id === 'number' ? playerKey(l.id, match.people) : null;
        return key !== null && typeof l.id === 'number' ? [{ key, label: playerLabel(t, l.id) ?? key }] : [];
      })
      .sort((a, b) => a.label.localeCompare(b.label)),
  }));
}

/** One player's match: their name picked once, what they did, their best points, who they play with
 * and their card. */
export function MyMatch() {
  const { t } = useTranslation();
  const groups = useMemo(() => everyone(t), [t]);
  const known = groups.flatMap((g) => g.players);
  const [key, setKey] = useState(remembered);
  const picked = known.some((p) => p.key === key) ? key : null;

  if (!hasTeams || !known.length) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('myMatch.title')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t('myMatch.caption')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <Select
          value={picked ?? undefined}
          onValueChange={(v) => {
            setKey(v);
            remember(v);
          }}
        >
          <SelectTrigger aria-label={t('myMatch.pick')} className="w-full bg-card sm:w-72">
            <SelectValue placeholder={t('myMatch.pick')} />
          </SelectTrigger>
          <SelectContent>
            {groups.map(({ g, players }) => (
              <SelectGroup key={g}>
                <SelectLabel>{groupName(t, g)}</SelectLabel>
                {players.map((p) => (
                  <SelectItem key={p.key} value={p.key}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
        {picked && <Player key={picked} player={picked} />}
      </CardContent>
    </Card>
  );
}

function Player({ player }: { player: string }) {
  const { t } = useTranslation();
  const { set, contacts, rallies } = useSet();
  const g = Number(player.split(':')[0]) as Group;
  const f = useFormat();
  const best = useMemo(bestPlayer, []);
  const found = useMemo(() => lines(contacts, match.people, g), [contacts, g]);
  const line = found.find((l): l is (typeof found)[number] & { id: number } => typeof l.id === 'number' && playerKey(l.id, match.people) === player);
  if (!line) {
    return <p className="text-sm text-muted-foreground">{t('myMatch.none')}</p>;
  }
  const team = found[found.length - 1].stats;
  const mates = found.filter((l) => typeof l.id === 'number' && l.id !== line.id).map((l) => l.stats);
  const name = playerLabel(t, line.id) ?? '';
  const seconds = playingTime(line.id, set);
  const title = (tr: TFunction) => playerLabel(tr, line.id) ?? '';
  const row: CardRow = { key: line.id, name, title, stats: line.stats };
  const leads = tops(line.stats, mates, TOPS);
  const moments = highlights(rallies, player, match.people);
  const run = serveRun(rallies, player, match.people);
  const partners = duos(contacts, player, match.people);
  const chips = [...(strengths(found, (p) => playingTime(p, set), rallies).get(line.id) ?? []), ...toWorkOn(line.stats, team)];
  const touches = t('myMatch.summaryTouches', { count: line.stats.touches.length });
  const points = line.stats.points.length;
  const headline = [
    seconds ? t('myMatch.summaryTime', { name, touches, time: clock(seconds) }) : t('myMatch.summary', { name, touches }),
    points ? t('myMatch.summaryPoints', { count: points }) : null,
  ]
    .filter(Boolean)
    .join(', ');
  const main = MAIN.map((stat) => ({ stat, n: line.stats[stat].length })).sort((a, b) => b.n - a.n)[0];
  const measured = measures(line.stats.serves, line.stats.attacks);
  const fastest = measured.fastest;

  return (
    <div className="grid gap-6 md:grid-cols-[15rem_minmax(0,1fr)]">
      <div className="max-md:mx-auto max-md:w-full max-md:max-w-64">
        <PlayerCard row={row} g={g} mvp={best?.key === player ? best : undefined} />
      </div>
      <div className="grid content-start gap-6">
        <div className="grid gap-3">
          <p>
            <span className="font-medium">{`${headline}.`}</span>
            {main.n > 0 && ` ${t(`myMatch.mostly.${main.stat}`, { count: main.n })}`}
          </p>
          <div className="flex flex-wrap gap-2">
            <Replay picked={line.stats.touches} title={title} label={t('myMatch.replayAll', { count: line.stats.touches.length })} primary />
            {line.stats.points.length > 0 && <Replay picked={line.stats.points} title={title} label={t('myMatch.replayPoints', { count: line.stats.points.length })} />}
          </div>
          {(leads.length > 0 || chips.length > 0) && (
            <div className="flex flex-wrap gap-1">
              {leads.map((stat) => (
                <Lead key={stat} stat={stat} picked={line.stats[stat]} title={title} />
              ))}
              {chips.map((i) => (
                <InsightChip key={i.key} insight={i} who={title} />
              ))}
            </div>
          )}
        </div>
        {(fastest || measured.reach !== null) && (
          <Section title={t('myMatch.measures')}>
            {fastest && (
              <Row title={(tr) => tr('myMatch.fastestServe', { speed: fastest.speed })} clips={contactClips([fastest], match.duration)}>
                <b className="font-semibold">{t('myMatch.fastestServe', { speed: fastest.speed })}</b>
                {measured.speed !== null && <span className="block text-xs text-muted-foreground">{t('myMatch.usualSpeed', { speed: measured.speed, count: measured.timed })}</span>}
              </Row>
            )}
            {measured.reach !== null && (
              <Row title={(tr) => tr('myMatch.reach', { height: f.dec(measured.reach as number) })} clips={contactClips(measured.reached, match.duration)}>
                <b className="font-semibold">{t('myMatch.reach', { height: f.dec(measured.reach) })}</b>
                <span className="block text-xs text-muted-foreground">{t('myMatch.reachOf', { count: measured.reached.length })}</span>
              </Row>
            )}
            <li className="px-1.5 text-xs text-muted-foreground">{t('myMatch.measuresNote')}</li>
          </Section>
        )}
        {(moments.length > 0 || run) && (
          <Section title={t('myMatch.moments')}>
            {run && (
              <Row
                title={(tr) => tr('myMatch.serveRunTitle', { name: title(tr) })}
                clips={rallyClips(
                  allRallies.filter((r) => run.rallies.includes(r.i)),
                  match.duration,
                )}
              >
                {t('myMatch.serveRun', { count: run.rallies.length, from: run.from.join('-'), to: run.to.join('-') })}
              </Row>
            )}
            {moments.map((m) => (
              <Row key={m.contact.i} title={title} clips={contactClips([m.contact], match.duration)}>
                <b className="font-semibold">{t(`myMatch.highlight.${m.kind}`)}</b>
                <span className="block text-xs text-muted-foreground">
                  {t(m.kind === 'longRally' ? 'myMatch.highlightLong' : 'myMatch.highlightDetail', {
                    action: t(`actions.${m.contact.type}.point`),
                    touches: m.touches,
                    score: m.score.join('-'),
                    set: m.contact.set,
                  })}
                </span>
              </Row>
            ))}
          </Section>
        )}
        {partners.length > 0 && (
          <Section title={t('myMatch.duos')}>
            {partners.slice(0, DUOS_SHOWN).flatMap((d) => {
              const other = (tr: TFunction) => playerLabel(tr, d.person) ?? '';
              return [
                { attacks: d.fromThem, setter: other, attacker: title, id: `${d.person}:them` },
                { attacks: d.fromMe, setter: title, attacker: other, id: `${d.person}:me` },
              ]
                .filter((x) => x.attacks.length > 0)
                .map((x) => (
                  <Row key={x.id} title={(tr) => tr('myMatch.duo', { setter: x.setter(tr), attacker: x.attacker(tr) })} clips={contactClips(x.attacks, match.duration)}>
                    {t('myMatch.duo', { setter: x.setter(t), attacker: x.attacker(t) })}
                    <span className="block text-xs text-muted-foreground">{`${t('myMatch.duoAttacks', { count: x.attacks.length })}, ${t('myMatch.duoWon', { count: x.attacks.filter((c) => c.result === 'point').length })}`}</span>
                  </Row>
                ));
            })}
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2">
      <h3 className="font-semibold">{title}</h3>
      <ul className="m-0 grid list-none gap-1 p-0">{children}</ul>
    </section>
  );
}

/** A line that plays its clips. */
function Row({ title, clips, children }: { title: (t: TFunction) => string; clips: Clip[]; children: ReactNode }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  return (
    <li>
      <button
        type="button"
        title={t('story.replay')}
        onClick={() => play(title, clips)}
        className="flex w-full items-start gap-2 rounded-md px-1.5 py-1 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span className="min-w-0 flex-1">{children}</span>
        <Play aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
      </button>
    </li>
  );
}

function Replay({ picked, title, label, primary }: { picked: Contact[]; title: (t: TFunction) => string; label: string; primary?: boolean }) {
  const { play } = usePlayer();
  return (
    <Button variant={primary ? 'default' : 'outline'} onClick={() => play(title, contactClips(picked, match.duration))}>
      <Play aria-hidden />
      {label}
    </Button>
  );
}

/** What a player leads their team in, playing those touches. */
function Lead({ stat, picked, title }: { stat: Stat; picked: Contact[]; title: (t: TFunction) => string }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const name = (tr: TFunction) => tr('myMatch.topsTitle', { stat: tr(`stats.names.${stat}`), name: title(tr) });
  return (
    <button
      type="button"
      title={`${t('myMatch.tops')} · ${t('watchN', { count: picked.length })}`}
      onClick={() => play(name, contactClips(picked, match.duration))}
      className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium whitespace-nowrap text-emerald-900 outline-none hover:bg-emerald-200 focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-emerald-950 dark:text-emerald-200 dark:hover:bg-emerald-900"
    >
      <Trophy aria-hidden className="size-3" />
      {`${t(`stats.names.${stat}`)} · ${picked.length}`}
    </button>
  );
}
