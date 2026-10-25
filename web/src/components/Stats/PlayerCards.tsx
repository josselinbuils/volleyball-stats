import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { CountButton } from '@/components/CountButton';
import { match, playerLabel, playerNumber, teamColor, teamRing, type Group } from '@/lib/match';
import { COLUMNS, InsightChip, type Row } from '@/components/Stats/StatsTable';

// The card's three headline counts; the other groups follow, those the player played.
const HEADLINE = ['touches', 'points', 'faults'] as const;
const GROUPS = [...new Set(COLUMNS.map((c) => c.of))].filter((of) => of !== 'touches' && of !== 'overall');

/** One card per player of team `g`: their picture, number and name, their counts and their
 * strengths and things to work on, each playing its moments. */
export function PlayerCards({ id, rows, g }: { id: string; rows: (Row & { key: number })[]; g: Group }) {
  return (
    <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {rows.map((r) => (
        <li key={r.key}>
          <PlayerCard id={`${id}:${r.key}`} row={r} g={g} />
        </li>
      ))}
    </ul>
  );
}

function PlayerCard({ id, row: r, g }: { id: string; row: Row & { key: number }; g: Group }) {
  const { t } = useTranslation();
  const photo = match.people[r.key]?.photo;
  const title = (stat: string) => (tr: TFunction) => `${tr(`stats.names.${stat}`)}, ${r.title(tr)}`;
  const played = GROUPS.filter((of) => r.stats[of as keyof typeof r.stats].length > 0);
  return (
    <article className="grid h-full content-start overflow-hidden rounded-xl border bg-card shadow-xs">
      {/* The team's colour fading into grey behind the picture: a white team's still shows. */}
      <header
        className="relative flex h-36 items-end justify-between gap-2 px-3 pt-3"
        style={{ background: `linear-gradient(135deg, color-mix(in oklch, ${teamColor(g)} 45%, var(--muted)), var(--muted) 70%)` }}
      >
        <div className="min-w-0 pb-3">
          <span
            className="inline-grid size-11 place-items-center rounded-full text-xl font-bold"
            style={{ background: teamColor(g), color: `var(--team${g}-text)`, boxShadow: `inset 0 0 0 2px ${teamRing(g)}` }}
          >
            {playerNumber(r.key)}
          </span>
          {/* The number alone stands for an unnamed player. */}
          <h3 className="mt-2 text-lg leading-tight font-semibold [overflow-wrap:anywhere]">{match.people[r.key]?.name ?? <span className="sr-only">{playerLabel(t, r.key)}</span>}</h3>
        </div>
        {photo && <img src={photo} alt="" loading="lazy" className="h-32 max-w-[45%] shrink-0 rounded-t-lg object-cover object-top" />}
      </header>
      <div className="grid grid-cols-3 border-b">
        {HEADLINE.map((stat) => (
          <div key={stat} className="grid justify-items-center gap-0.5 py-2.5">
            <CountButton id={`${id}:${stat}`} title={title(stat)} picked={r.stats[stat]} className="min-w-10" />
            <span className="text-xs text-muted-foreground">{t(`stats.names.${stat}`)}</span>
          </div>
        ))}
      </div>
      <dl className="m-0 grid gap-1 px-3 py-2.5 text-sm">
        {played.map((of) => (
          <div key={of} className="flex items-start gap-2">
            <dt className="w-24 shrink-0 pt-1 font-medium">{t(`stats.names.${of}`)}</dt>
            {/* The total, then only the outcomes that happened. */}
            <dd className="m-0 flex min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-1">
              {COLUMNS.filter((c) => c.of === of && (c.label === 'total' || r.stats[c.stat].length > 0)).map((c) => (
                <span key={c.stat} className={cn('inline-flex items-center gap-1', c.label !== 'total' && 'text-muted-foreground')}>
                  <CountButton id={`${id}:${c.stat}`} title={title(c.stat)} picked={r.stats[c.stat]} className="h-7 min-w-8 text-sm" />
                  {c.label !== 'total' && <span className="text-xs">{t(`stats.columns.${c.label}`).toLowerCase()}</span>}
                </span>
              ))}
            </dd>
          </div>
        ))}
        {!played.length && <dd className="m-0 text-muted-foreground">{t('players.noTouch')}</dd>}
      </dl>
      {r.insights && r.insights.length > 0 && (
        <div className="flex flex-wrap gap-1 border-t px-3 py-2.5">
          {r.insights.map((i) => (
            <InsightChip key={i.key} id={`${id}:${i.key}`} insight={i} who={r.title} />
          ))}
        </div>
      )}
    </article>
  );
}
