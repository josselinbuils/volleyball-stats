import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Swatch } from '@/components/Swatch';
import type { ListedMatch } from '@/components/Matches';
import { loadMatch } from '@/components/Season/helpers/loadMatch';
import { buildSeason, matchesOf, seasonTeams, type SeasonData } from '@/components/Season/helpers/season';
import { chipLook } from '@/components/Stats/helpers/insights';
import { Tip } from '@/components/Tip';
import { useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';

/** The team's results, oldest first. */
function Form({ season }: { season: SeasonData }) {
  const { t } = useTranslation();
  const f = useFormat();
  const wins = season.played.filter((p) => p.won > p.lost).length;
  const losses = season.played.filter((p) => p.won < p.lost).length;
  return (
    <Card className="gap-3 px-4 py-3.5">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        {season.colour && <Swatch color={season.colour} ring="var(--border)" />}
        <span className="min-w-0 truncate">{season.team}</span>
        <span className="ml-auto shrink-0 text-sm font-medium text-muted-foreground">
          {t('season.wins', { count: wins })} · {t('season.losses', { count: losses })}
        </span>
      </h2>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {season.played.map((p) => {
          const result = p.won > p.lost ? 'win' : p.won < p.lost ? 'loss' : 'draw';
          const rows = [
            { name: season.team, colour: p.colours[0], sets: p.won, points: p.scores.map(([us]) => us), other: p.scores.map(([, them]) => them) },
            { name: p.opponent ?? p.path, colour: p.colours[1], sets: p.lost, points: p.scores.map(([, them]) => them), other: p.scores.map(([us]) => us) },
          ];
          return (
            <li key={p.path} className="rounded-lg border px-3 py-2.5">
              <table className="w-full tabular-nums">
                <caption className="pb-1.5">
                  <span className="flex items-center justify-between gap-2 text-sm">
                    <span className="text-muted-foreground">{p.date && f.date(p.date)}</span>
                    <span className={cn('rounded-full px-2 py-0.5 text-xs font-semibold', result === 'win' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground')}>
                      {t(`season.${result}`)}
                    </span>
                  </span>
                </caption>
                <tbody>
                  {rows.map((row) => {
                    const won = row.sets > rows.find((r) => r !== row)!.sets;
                    return (
                      <tr key={row.name}>
                        <th scope="row" className={cn('w-full max-w-0 py-0.5 text-left', won ? 'font-semibold' : 'font-normal')}>
                          <span className="flex min-w-0 items-center gap-2">
                            {row.colour && <Swatch color={row.colour} ring="var(--border)" />}
                            <span className="truncate">{row.name}</span>
                          </span>
                        </th>
                        <td className={cn('w-8 px-1 text-center text-lg font-semibold', !won && 'text-muted-foreground')}>{row.sets}</td>
                        {row.points.map((n, k) => (
                          <td key={k} className={cn('w-9 px-1 text-center', n > row.other[k] ? 'font-semibold' : 'text-muted-foreground')}>
                            {n}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

/** Each player's season in words, as the match pages tell it: what they do well, what went up, what their last match
 * gave them to work on. Nothing compares them with one another. */
function Players({ season }: { season: SeasonData }) {
  const { t } = useTranslation();
  const f = useFormat();
  const shown = season.players.filter((p) => p.strengths.length + p.rising.length > 0 || p.work);
  if (!shown.length) {
    return null;
  }
  return (
    <Card className="gap-3 px-4 py-3.5">
      <h2 className="text-lg font-semibold">{t('season.players')}</h2>
      <ul className="grid gap-3">
        {shown.map((p) => (
          <li key={p.key} className="grid gap-1.5">
            <span className="flex min-w-0 items-baseline gap-2">
              <span className="truncate font-medium">{p.name ?? t('player', { n: p.jersey })}</span>
              <span className="shrink-0 text-sm text-muted-foreground">{t('season.matches', { count: p.matches })}</span>
            </span>
            <span className="flex flex-wrap gap-1.5">
              {p.strengths.map((s) => (
                <Tip key={s.key} label={t('season.strengthIn', { count: s.matches, of: p.matches })}>
                  <span tabIndex={0} className={chipLook(true)}>
                    {t(`stats.insights.${s.key}`, { count: s.n, of: s.of })}
                  </span>
                </Tip>
              ))}
              {p.rising.map((r) => (
                <Tip key={r.measure} label={t(r.measure === 'points' ? 'season.risingPoints' : 'season.risingGrade', { from: f.dec(r.from), to: f.dec(r.to) })}>
                  <span tabIndex={0} className={chipLook(true)}>
                    {t(`season.rising.${r.measure}`)}
                  </span>
                </Tip>
              ))}
              {p.work && (
                <Tip
                  label={t('season.lastMatch', {
                    detail: t('stats.insights.detail', {
                      n: p.work.n,
                      of: p.work.of,
                      p: f.pct(p.work.n / p.work.of),
                      restN: p.work.restN,
                      restOf: p.work.restOf,
                      restP: f.pct(p.work.restN / p.work.restOf),
                    }),
                  })}
                >
                  <span tabIndex={0} className={chipLook(false)}>
                    {t(`stats.insights.${p.work.key}`, { count: p.work.n, of: p.work.of })}
                  </span>
                </Tip>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** A team over its matches: its results, then each player's season. */
export function Season({ matches }: { matches: ListedMatch[] }) {
  const { t } = useTranslation();
  const teams = useMemo(() => seasonTeams(matches), [matches]);
  const [team, setTeam] = useState(teams[0]);
  const [season, setSeason] = useState<SeasonData | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    const played = matchesOf(matches, team);
    setSeason(null);
    setFailed(false);
    Promise.all(played.map(loadMatch))
      .then((data) => {
        if (current) {
          setSeason(
            buildSeason(
              team,
              played.map((match, k) => ({ match, data: data[k] })),
            ),
          );
        }
      })
      .catch(() => {
        if (current) {
          setFailed(true);
        }
      });
    return () => {
      current = false;
    };
  }, [matches, team, attempt]);

  return (
    <div className="grid gap-3">
      {teams.length > 1 && (
        <Select value={team} onValueChange={setTeam}>
          <SelectTrigger aria-label={t('season.pickTeam')} className="w-full sm:w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {teams.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {failed ? (
        <p className="flex flex-wrap items-center gap-3 px-1 text-destructive" role="alert">
          {t('season.failed')}
          <Button variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>
            {t('season.retry')}
          </Button>
        </p>
      ) : season ? (
        <>
          <Form season={season} />
          <Players season={season} />
        </>
      ) : (
        <p className="px-1 text-muted-foreground">{t('season.loading')}</p>
      )}
    </div>
  );
}
