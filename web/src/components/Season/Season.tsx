import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Swatch } from '@/components/Swatch';
import type { ListedMatch } from '@/components/Matches';
import { loadMatch } from '@/components/Season/helpers/loadMatch';
import { buildSeason, matchesOf, MEASURES, seasonTeams, type Measure, type Played, type SeasonData } from '@/components/Season/helpers/season';
import { useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';

const WIDE = 96;
const TALL = 32;
const INSET = 5;

/** A row's values over the matches, on the scale all its table's rows share. */
function Sparkline({ values, played, top, label }: { values: (number | null)[]; played: Played[]; top: number; label: string }) {
  const f = useFormat();
  const x = (k: number) => (values.length > 1 ? INSET + (k * (WIDE - 2 * INSET)) / (values.length - 1) : WIDE / 2);
  const y = (value: number) => TALL - INSET - (value / top) * (TALL - 2 * INSET);
  const known = values.flatMap((value, k) => (value === null ? [] : [{ value, k }]));
  return (
    <svg viewBox={`0 0 ${WIDE} ${TALL}`} width={WIDE} height={TALL} role="img" aria-label={label} className="block">
      <polyline points={known.map((p) => `${x(p.k)},${y(p.value)}`).join(' ')} fill="none" stroke="var(--primary)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {known.map((p) => (
        <g key={p.k}>
          <circle cx={x(p.k)} cy={y(p.value)} r={4} fill="var(--primary)" stroke="var(--card)" strokeWidth={1} />
          <circle cx={x(p.k)} cy={y(p.value)} r={12} fill="transparent">
            <title>{`${played[p.k].opponent ?? ''} · ${f.dec(p.value)}`}</title>
          </circle>
        </g>
      ))}
    </svg>
  );
}

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
        <span className="ml-auto shrink-0 text-sm font-medium text-muted-foreground tabular-nums">{t('season.record', { wins, losses })}</span>
      </h2>
      <ol className="grid gap-2">
        {season.played.map((p) => (
          <li key={p.path} className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3">
            <span
              className={cn(
                'row-span-2 flex size-8 items-center justify-center rounded-md border text-sm font-semibold',
                p.won > p.lost ? 'border-primary bg-primary text-primary-foreground' : 'text-muted-foreground',
              )}
            >
              {t(p.won > p.lost ? 'season.win' : p.won < p.lost ? 'season.loss' : 'season.draw')}
            </span>
            <span className="truncate font-medium">{p.opponent ? t('season.versus', { team: p.opponent }) : p.path}</span>
            <span className="text-sm text-muted-foreground tabular-nums">{[p.date && f.date(p.date), p.scores.map(([us, them]) => `${us}-${them}`).join(' · ')].filter(Boolean).join(' · ')}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

/** A value's change since the match before it, in neutral ink: "=" when it stays. */
function change(values: (number | null)[], dec: (x: number) => string): string | null {
  const known = values.filter((v) => v !== null);
  if (known.length < 2) {
    return null;
  }
  const by = known[known.length - 1] - known[known.length - 2];
  return Math.abs(by) < 0.05 ? '=' : `${by > 0 ? '+' : ''}${dec(by)}`;
}

function Progress({ season }: { season: SeasonData }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [measure, setMeasure] = useState<Measure>('points');
  const rows = [
    { key: 'total', label: t('season.team'), values: season.total[measure], team: true },
    ...season.players.filter((p) => p.values[measure].some((v) => v !== null)).map((p) => ({ key: p.key, label: p.name ?? t('player', { n: p.jersey }), values: p.values[measure], team: false })),
  ];
  // Points: the team's row on its own scale, its total dwarfing a player's.
  const top = (values: (number | null)[]) => (measure === 'points' ? Math.max(1, ...values.map((v) => v ?? 0)) : 5);
  const playersTop = top(rows.slice(1).flatMap((r) => r.values));
  return (
    <Card className="gap-3 px-4 py-3.5">
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        spacing={2}
        className="flex-wrap"
        value={measure}
        onValueChange={(v) => {
          if (v) {
            setMeasure(v as Measure);
          }
        }}
        aria-label={t('season.measure')}
      >
        {MEASURES.map((m) => (
          <ToggleGroupItem key={m} value={m} className="data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
            {t(`season.measures.${m}`)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-full px-0" />
            <TableHead className="px-2" />
            <TableHead className="px-2 text-right">{t('season.last')}</TableHead>
            <TableHead className="pr-0 pl-2 text-right">{t('season.change')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const last = row.values.filter((v) => v !== null).at(-1);
            return (
              <TableRow key={row.key}>
                <TableCell className={cn('max-w-0 truncate px-0', row.team && 'font-semibold')}>{row.label}</TableCell>
                <TableCell className="px-2">
                  <Sparkline values={row.values} played={season.played} top={row.team ? top(row.values) : playersTop} label={row.values.map((v) => (v === null ? '–' : f.dec(v))).join(', ')} />
                </TableCell>
                <TableCell className={cn('px-2 text-right tabular-nums', row.team && 'font-semibold')}>{last == null ? '–' : f.dec(last)}</TableCell>
                <TableCell className="pr-0 pl-2 text-right text-muted-foreground tabular-nums">{change(row.values, f.dec) ?? ''}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}

/** A team over its matches: its results, then each player's progress. */
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
          <Progress season={season} />
        </>
      ) : (
        <p className="px-1 text-muted-foreground">{t('season.loading')}</p>
      )}
    </div>
  );
}
