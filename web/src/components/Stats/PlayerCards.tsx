import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { useFormat } from '@/lib/format';
import { groupName, match, playerLabel, playerNumber, teamColor, type Contact, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import type { Stat } from '@/components/Stats/helpers/stats';
import { InsightChip, type Row } from '@/components/Stats/StatsTable';

const SIX: Stat[] = ['serves', 'receptions', 'sets', 'attacks', 'blocks', 'digs'];
const GOLD = 'linear-gradient(135deg, #fbe38e, #d4a017 45%, #fff1b8 55%, #b8860b)';
// The stars over a hovered picture: left and top (% of the picture), size (px), delay (s).
const SPARKLES: [number, number, number, number][] = [
  [10, 12, 16, 0],
  [66, 6, 12, 0.35],
  [74, 44, 18, 0.7],
  [20, 56, 11, 1.05],
];
// A FIFA card's shield: notched top, pointed bottom.
const SHIELD = 'polygon(0% 6%, 8% 6%, 14% 3%, 30% 3%, 38% 0%, 50% 2%, 62% 0%, 70% 3%, 86% 3%, 92% 6%, 100% 6%, 100% 87%, 50% 100%, 0% 87%)';

type CardRow = Row & { key: number };

/** One collection card per player of team `g`, shaped like a FIFA card, with their picture, number, name and counts, each
 * count playing its moments; their strengths and things to work on under it. */
export function PlayerCards({ id, rows, g }: { id: string; rows: CardRow[]; g: Group }) {
  return (
    <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-x-4 gap-y-6 p-0">
      {rows.map((r) => (
        <li key={r.key} className="grid content-start gap-2">
          <FifaCard id={`${id}:${r.key}`} row={r} g={g} />
          {r.insights && r.insights.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {r.insights.map((i) => (
                <InsightChip key={i.key} id={`${id}:${r.key}:${i.key}`} insight={i} who={r.title} />
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

interface CardProps {
  id: string;
  row: CardRow;
  g: Group;
}

/** A count that plays its touches, in the card's own style; 0 for none. */
function Play({ id, stat, row, className }: { id: string; stat: Stat; row: CardRow; className?: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play } = usePlayer();
  const picked: Contact[] = row.stats[stat];
  const title = (tr: TFunction) => `${tr(`stats.names.${stat}`)}, ${row.title(tr)}`;
  if (!picked.length) {
    return <span className={cn('opacity-60', className)}>0</span>;
  }
  const on = playlist?.key === `${id}:${stat}`;
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={`${f.num(picked.length)} · ${title(t)} · ${t('watchN', { count: picked.length })}`}
      title={t('watchN', { count: picked.length })}
      className={cn('rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-current/50', on && 'underline', className)}
      onClick={() => play(title, contactClips(picked, match.duration), 0, `${id}:${stat}`)}
    >
      {f.num(picked.length)}
    </button>
  );
}

/** The name a card shows: the one given, else the number. */
function cardName(t: TFunction, person: number): string {
  return match.people[person]?.name ?? playerLabel(t, person) ?? '';
}

function FifaCard({ id, row: r, g }: CardProps) {
  const { t } = useTranslation();
  const photo = match.people[r.key]?.photo;
  return (
    <article className="aspect-[5/7] p-[5px] drop-shadow-md" style={{ clipPath: SHIELD, background: GOLD }}>
      <div
        className="relative flex h-full flex-col overflow-hidden"
        style={{ clipPath: SHIELD, background: `linear-gradient(160deg, ${teamColor(g)}, color-mix(in oklch, ${teamColor(g)} 55%, black))`, color: `var(--team${g}-text)` }}
      >
        <div
          aria-hidden
          className="absolute inset-0 opacity-25"
          style={{ backgroundImage: 'radial-gradient(currentColor 1px, transparent 1.5px)', backgroundSize: '9px 9px', maskImage: 'linear-gradient(135deg, black, transparent 65%)' }}
        />
        <div className="relative flex min-h-0 flex-1 gap-2 px-[9%] pt-[13%]">
          <div className="grid content-start justify-items-center gap-1.5 pt-2">
            <span className="text-5xl leading-none font-black tabular-nums">{playerNumber(r.key)}</span>
            <span className="max-w-16 text-center text-[10px] leading-tight font-bold uppercase">{groupName(t, g)}</span>
          </div>
          {photo && (
            <div className="group/photo relative ml-auto h-full min-w-0" style={{ maskImage: 'linear-gradient(to bottom, black 70%, transparent)' }}>
              <img src={photo} alt="" loading="lazy" className="h-full object-cover object-top" />
              {/* A few stars twinkling over the picture while it is hovered. */}
              {SPARKLES.map(([left, top, size, delay]) => (
                <svg
                  key={`${left}${top}`}
                  aria-hidden
                  viewBox="0 0 24 24"
                  className="sparkle absolute"
                  style={{ left: `${left}%`, top: `${top}%`, width: size, height: size, animationDelay: `${delay}s` }}
                >
                  <path d="M12 0C13 8 16 11 24 12C16 13 13 16 12 24C11 16 8 13 0 12C8 11 11 8 12 0Z" />
                </svg>
              ))}
            </div>
          )}
        </div>
        <h3 className="relative mx-[9%] border-b border-current/40 pb-1 text-center text-xl font-black tracking-wide uppercase [overflow-wrap:anywhere]">{cardName(t, r.key)}</h3>
        {/* Each number above its label: room for a whole match's counts. */}
        <dl className="relative mx-[7%] my-2 grid grid-cols-3 gap-y-1.5">
          {SIX.map((stat, k) => (
            <div key={stat} className={cn('flex min-w-0 flex-col-reverse items-center', k % 3 > 0 && 'border-l border-current/30')}>
              <dt className="max-w-full truncate px-0.5 text-[9.5px] font-semibold tracking-tight uppercase">{t(`stats.names.${stat}`)}</dt>
              <dd className="m-0 text-xl leading-tight font-black tabular-nums">
                <Play id={id} stat={stat} row={r} />
              </dd>
            </div>
          ))}
        </dl>
        <Totals id={id} row={r} className="relative pb-[13%] text-xs font-semibold" />
      </div>
    </article>
  );
}

/** "3 points · 1 faute", each playing its moments. */
function Totals({ id, row, className }: { id: string; row: CardRow; className?: string }) {
  const { t } = useTranslation();
  return (
    <span className={cn('flex justify-center gap-3', className)}>
      {(['points', 'faults'] as const).map((stat) => (
        <span key={stat}>
          <Play id={id} stat={stat} row={row} className="font-black" /> {t(`players.cards.${stat}`, { count: row.stats[stat].length })}
        </span>
      ))}
    </span>
  );
}
