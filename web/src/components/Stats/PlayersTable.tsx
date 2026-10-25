import { useState } from 'react';
import { LayoutGrid, Table2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SetBadge } from '@/components/SetBadge';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasTeams, match, playerLabel, playerNumber, teamColor, teamRing, type Group } from '@/lib/match';
import { useSet } from '@/lib/sets';
import { insights } from '@/components/Stats/helpers/insights';
import { lines } from '@/components/Stats/helpers/stats';
import { PlayerCards } from '@/components/Stats/PlayerCards';
import { StatsTable } from '@/components/Stats/StatsTable';

/** What each player of a team did with the ball, a count per action and how it ended, and the whole
 * team's; without identified players, the team's alone (each side of the net's without teams). */
export function PlayersTable() {
  const { t } = useTranslation();
  const { set, contacts } = useSet();
  const [group, setGroup] = useState<Group>(1);
  const [view, setView] = useState<'table' | 'cards'>('table');
  const withPlayers = hasTeams && Object.values(match.people).some((p) => p.number !== null);
  const found = lines(contacts, match.people, group);
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
      insights: typeof line.id === 'number' ? insights(line.stats, team) : undefined,
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
          {withPlayers && (
            <ToggleGroup
              type="single"
              variant="outline"
              spacing={0}
              value={view}
              onValueChange={(v) => {
                if (v) {
                  setView(v as 'table' | 'cards');
                }
              }}
              aria-label={t('players.viewsLabel')}
              className="w-full items-stretch bg-card sm:w-auto"
            >
              {(['table', 'cards'] as const).map((v) => (
                <ToggleGroupItem key={v} value={v} className="h-auto min-h-8 flex-1 gap-2 py-1.5 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-none">
                  {v === 'table' ? <Table2 aria-hidden /> : <LayoutGrid aria-hidden />}
                  {t(`players.views.${v}`)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          )}
        </div>
        {view === 'cards' && withPlayers ? (
          <PlayerCards id={`cards:${set}:${group}`} rows={rows.filter((r): r is (typeof rows)[number] & { key: number } => typeof r.key === 'number')} g={group} />
        ) : (
          <StatsTable id={`players:${set}:${group}`} first={t('players.player')} rows={rows} insights={withPlayers} />
        )}
        <p className="text-[13px] text-muted-foreground">{[t('stats.note'), t('stats.noteUnattacked'), withPlayers && t('stats.noteInsights'), t('stats.noteVideo')].filter(Boolean).join(' ')}</p>
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
