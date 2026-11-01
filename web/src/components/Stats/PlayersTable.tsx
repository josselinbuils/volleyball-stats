import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SetBadge } from '@/components/SetBadge';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasTeams, match, playerLabel, playerMark, teamColor, teamRing, type Contact, type Group } from '@/lib/match';
import { playerKey } from '@/helpers/players';
import { useSet } from '@/lib/sets';
import { bestPlayer, playingTime } from '@/components/Stats/helpers/best';
import { drops, type Drop } from '@/components/Stats/helpers/between';
import { insights } from '@/components/Stats/helpers/insights';
import { strengths } from '@/components/Stats/helpers/strengths';
import { lines } from '@/components/Stats/helpers/stats';
import { Mvp } from '@/components/Stats/Mvp';
import { COLUMNS, StatsTable } from '@/components/Stats/StatsTable';

/** What each player of a team did with the ball, a count per action and how it ended, and the whole
 * team's; without identified players, the team's alone (each side of the net's without teams). */
export function PlayersTable() {
  const { t } = useTranslation();
  const { set, contacts, rallies } = useSet();
  const [group, setGroup] = useState<Group>(1);
  const withPlayers = hasTeams && Object.values(match.people).some((p) => p.number !== null);
  const dropped = useMemo(() => drops(contacts, match.people), [contacts]);
  const seconds = (person: number) => playingTime(person, set);
  const best = useMemo(() => (withPlayers ? bestPlayer() : null), [withPlayers]);
  const found = lines(contacts, match.people, group, dropped);
  const earned = strengths(found, seconds, contacts, rallies, match.people);
  const team = found[found.length - 1].stats;
  const rows = found
    .filter((line) => withPlayers || line.id === 'total')
    .map((line) => ({
      key: line.id,
      name:
        typeof line.id === 'number' ? (
          <Who person={line.id} g={group} />
        ) : (
          <span className={cn('flex min-h-8 items-center', line.id === 'rest' && 'text-muted-foreground')}>{line.id === 'total' && !hasTeams ? groupName(t, group) : t(`players.${line.id}`)}</span>
        ),
      title: (tr: TFunction) => (line.id === 'rest' ? tr('players.rest') : line.id === 'total' ? groupName(tr, group) : (playerLabel(tr, line.id) ?? '')),
      stats: line.stats,
      tips: { between: pairs(t, dropped, line.stats.between) },
      insights: typeof line.id === 'number' ? [...(earned.get(line.id) ?? []), ...insights(line.stats, team).filter((i) => !i.strength)] : undefined,
      badge: typeof line.id === 'number' && best && playerKey(line.id, match.people) === best.key ? <Mvp stats={best.stats} seconds={best.seconds} /> : undefined,
      seconds: typeof line.id === 'number' ? seconds(line.id) : undefined,
      total: line.id === 'total',
    }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('players.title')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t(hasTeams ? 'players.caption' : 'players.captionSides')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            value={String(group)}
            onValueChange={(v) => {
              if (v) {
                setGroup(Number(v) as Group);
              }
            }}
            aria-label={t('teamFilter')}
            className="w-full items-stretch bg-card sm:w-auto"
          >
            {GROUPS.map((g) => (
              <ToggleGroupItem
                key={g}
                value={String(g)}
                className="h-auto min-h-8 flex-1 gap-2 py-1.5 leading-tight whitespace-normal data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-none"
              >
                <Swatch color={teamColor(g)} ring={teamRing(g)} />
                {groupName(t, g)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        <StatsTable id={`players:${set}:${group}`} first={t('players.player')} rows={rows} columns={COLUMNS} insights={withPlayers} />
        <p className="text-[13px] text-muted-foreground">{`${t('stats.noteTitles')} ${t('stats.noteVideo')}`}</p>
      </CardContent>
    </Card>
  );
}

/** A player's mark in their team's colour, and their name. */
function Who({ person, g }: { person: number; g: Group }) {
  const { t } = useTranslation();
  return (
    <span className="flex min-h-8 items-center gap-2">
      <span
        aria-hidden
        className="inline-grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold"
        style={{ background: teamColor(g), color: `var(--team${g}-text)`, boxShadow: `inset 0 0 0 1.5px ${teamRing(g)}` }}
      >
        {playerMark(person)}
      </span>
      <span className="break-words">{playerLabel(t, person)}</span>
    </span>
  );
}

/** The pairs the balls of `landings` dropped between, most first: "no. 2 & no. 7 (3), …". */
function pairs(t: TFunction, dropped: Drop[], landings: Contact[]): string {
  const counts = new Map<string, number>();
  for (const d of dropped) {
    if (landings.includes(d.landing)) {
      const key = d.pair
        .map((p) => playerLabel(t, p) ?? t('players.rest'))
        .sort()
        .join(' & ');
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return [...counts]
    .sort((a, b) => b[1] - a[1])
    .map(([pair, n]) => `${pair} (${n})`)
    .join(', ');
}
