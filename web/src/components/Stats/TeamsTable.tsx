import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { Swatch } from '@/components/Swatch';
import { GROUPS, groupName, hasTeams, teamColor, teamRing } from '@/lib/match';
import { useSet } from '@/lib/sets';
import { stats } from '@/components/Stats/helpers/stats';
import { StatsTable } from '@/components/Stats/StatsTable';

/** What each team did with the ball, side by side; without player tracks, each side of the net. */
export function TeamsTable() {
  const { t } = useTranslation();
  const { set, contacts } = useSet();
  const rows = GROUPS.map((g) => ({
    key: g,
    name: (
      <span className="flex min-h-8 items-center gap-2">
        <Swatch color={teamColor(g)} ring={teamRing(g)} />
        {groupName(t, g)}
      </span>
    ),
    title: (tr: typeof t) => groupName(tr, g),
    stats: stats(
      contacts,
      (c) => c.g === g,
      (c) => c.g !== g,
    ),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('teams.title')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t(hasTeams ? 'teams.caption' : 'teams.captionSides')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <StatsTable id={`teams:${set}`} first={t(hasTeams ? 'teams.team' : 'teams.side')} rows={rows} />
        <p className="text-[13px] text-muted-foreground">{[t('stats.note'), t('stats.noteUnattacked'), t('stats.noteVideo')].join(' ')}</p>
      </CardContent>
    </Card>
  );
}
