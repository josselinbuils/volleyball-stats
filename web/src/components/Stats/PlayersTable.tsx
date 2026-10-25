import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SetBadge } from '@/components/SetBadge';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasTeams, match, playerLabel, playerNumber, teamColor, teamRing, type Group } from '@/lib/match';
import { useSet } from '@/lib/sets';
import { lines } from '@/components/Stats/helpers/stats';
import { StatsTable } from '@/components/Stats/StatsTable';

/** What each player of a team did with the ball, a count per action and how it ended. */
export function PlayersTable() {
  const { t } = useTranslation();
  const { set, contacts } = useSet();
  const [group, setGroup] = useState<Group>(1);
  if (!hasTeams || !Object.values(match.people).some((p) => p.number !== null)) {
    return null;
  }
  const rows = lines(contacts, match.people, group).map((line) => ({
    key: line.id,
    name:
      typeof line.id === 'number' ? (
        <Who person={line.id} g={group} />
      ) : (
        <span className={cn('flex min-h-8 items-center', line.id === 'rest' && 'text-muted-foreground')}>{t(`players.${line.id}`)}</span>
      ),
    title: (tr: TFunction) => (line.id === 'rest' ? tr('players.rest') : line.id === 'total' ? groupName(tr, group) : (playerLabel(tr, line.id) ?? '')),
    stats: line.stats,
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
        <CardDescription>{t('players.caption')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
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
        <StatsTable id={`players:${set}:${group}`} first={t('players.player')} rows={rows} />
        <p className="text-[13px] text-muted-foreground">{[t('players.note'), t('stats.noteVideo')].join(' ')}</p>
      </CardContent>
    </Card>
  );
}

/** A player's number in their team's colour, and their name. */
function Who({ person, g }: { person: number; g: Group }) {
  const { t } = useTranslation();
  return (
    <span className="flex min-h-8 items-center gap-2">
      <span
        aria-hidden
        className="inline-grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold"
        style={{ background: teamColor(g), color: `var(--team${g}-text)`, boxShadow: `inset 0 0 0 1.5px ${teamRing(g)}` }}
      >
        {playerNumber(person)}
      </span>
      <span className="break-words">{playerLabel(t, person)}</span>
    </span>
  );
}
