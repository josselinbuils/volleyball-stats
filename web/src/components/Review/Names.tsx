import { useState } from 'react';
import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { GROUPS, groupName, teamColor, teamRing, type Group } from '@/lib/match';
import { post, type Named, type Suggestion } from '@/lib/review';

interface Given {
  name: string;
  jersey: string;
}

const INPUT =
  'h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2.5 text-[15px] font-normal shadow-xs outline-none dark:bg-input/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50';

const keyOf = (p: Named) => `${p.team}:${p.identity}`;
const fold = (name: string) => name.trim().toLocaleLowerCase();

/** The players of both teams to name, longest on court first; each name is saved as it is typed,
 * `onNamed` told how many players have a name or a number. */
export function Names({ players, roster, onNamed, onError }: { players: Named[]; roster: [Suggestion[], Suggestion[]]; onNamed: (count: number) => void; onError: () => void }) {
  const { t } = useTranslation();
  const [given, setGiven] = useState(() => new Map(players.map((p) => [keyOf(p), { name: p.name ?? '', jersey: p.jersey === null ? '' : String(p.jersey) }])));
  const [saved, setSaved] = useState<Map<string, Given>>(() => new Map(given));

  const save = async (p: Named, value: Given) => {
    const key = keyOf(p);
    const before = saved.get(key);
    if (before && before.name.trim() === value.name.trim() && before.jersey === value.jersey) {
      return;
    }
    try {
      await post('name', { team: p.team, identity: p.identity, name: value.name.trim() || null, jersey: value.jersey || null });
      const next = new Map(saved).set(key, value);
      setSaved(next);
      onNamed([...next.values()].filter((g) => g.name.trim() || g.jersey).length);
    } catch {
      onError();
    }
  };
  const edit = (p: Named, value: Given) => setGiven((g) => new Map(g).set(keyOf(p), value));

  return (
    <div className="grid gap-6">
      {GROUPS.map((g) => {
        const mine = players.filter((p) => p.team === g);
        if (!mine.length) {
          return null;
        }
        const count = mine.filter((p) => saved.get(keyOf(p))?.name.trim()).length;
        return (
          <section key={g} className="grid gap-3">
            <h2 className="flex flex-wrap items-center gap-x-2 gap-y-1 px-1 text-lg font-semibold">
              <Swatch color={teamColor(g)} ring={teamRing(g)} />
              {groupName(t, g)}
              <span className="text-sm font-normal text-muted-foreground">{t('review.namedCount', { count, total: mine.length })}</span>
            </h2>
            <datalist id={`roster-${g}`}>
              {roster[g - 1].map((r) => (
                <option key={r.name} value={r.name} />
              ))}
            </datalist>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {mine.map((p) => (
                <NameCard
                  key={keyOf(p)}
                  player={p}
                  g={g}
                  value={given.get(keyOf(p))!}
                  saved={saved.get(keyOf(p))!}
                  others={mine.filter((o) => o !== p).map((o) => ({ identity: o.identity, name: fold(given.get(keyOf(o))!.name) }))}
                  onEdit={(value) => edit(p, value)}
                  onSave={(value) => void save(p, value)}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function NameCard({
  player: p,
  g,
  value,
  saved,
  others,
  onEdit,
  onSave,
}: {
  player: Named;
  g: Group;
  value: Given;
  saved: Given;
  others: { identity: number; name: string }[];
  onEdit: (value: Given) => void;
  onSave: (value: Given) => void;
}) {
  const { t } = useTranslation();
  const taken = new Set(others.map((o) => o.name).filter(Boolean));
  const twins = others.filter((o) => o.name && o.name === fold(value.name));
  const suggestions = value.name.trim() ? [] : p.suggestions.filter((s) => !taken.has(fold(s.name)));
  const isSaved = (value.name.trim() || value.jersey) && saved.name.trim() === value.name.trim() && saved.jersey === value.jersey;
  // A suggestion brings its jersey number when none is typed.
  const pick = (s: Suggestion) => {
    const next = { name: s.name, jersey: value.jersey || (s.jersey === null ? '' : String(s.jersey)) };
    onEdit(next);
    onSave(next);
  };
  const id = `name-${g}-${p.identity}`;

  return (
    <div className="grid content-start gap-2.5 rounded-lg border bg-card p-3">
      <div className="flex h-24 gap-1.5 overflow-hidden">
        {p.crops.map((src) => (
          <img key={src} src={src} alt="" loading="lazy" className="h-24 rounded-md bg-muted" />
        ))}
      </div>
      <p className="m-0 flex flex-wrap items-center gap-x-1.5 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{t('player', { n: p.identity })}</span>
        <span>· {t('review.played', { time: clock(p.seconds) })}</span>
        {p.contacts > 0 && <span>· {t('touchesN', { count: p.contacts })}</span>}
        {isSaved && (
          <span className="ml-auto inline-flex items-center gap-1">
            <Check aria-hidden className="size-3.5" />
            {t('review.saved')}
          </span>
        )}
      </p>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          onSave(value);
        }}
      >
        <label htmlFor={`${id}-name`} className="grid flex-1 gap-1 text-sm font-medium">
          {t('review.name')}
          <input
            id={`${id}-name`}
            className={INPUT}
            list={`roster-${g}`}
            autoComplete="off"
            value={value.name}
            onChange={(event) => onEdit({ ...value, name: event.target.value })}
            onBlur={() => onSave(value)}
          />
        </label>
        <label htmlFor={`${id}-jersey`} className="grid w-20 shrink-0 gap-1 text-sm font-medium">
          {t('review.jersey')}
          <input
            id={`${id}-jersey`}
            className={cn(INPUT, 'tabular-nums')}
            inputMode="numeric"
            maxLength={2}
            autoComplete="off"
            value={value.jersey}
            onChange={(event) => onEdit({ ...value, jersey: event.target.value.replace(/\D/g, '') })}
            onBlur={() => onSave(value)}
          />
        </label>
      </form>
      {suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="text-muted-foreground">{t('review.suggestions')}</span>
          {suggestions.map((s) => (
            <button
              key={s.name}
              type="button"
              className="rounded-full border bg-background px-2.5 py-0.5 hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              onClick={() => pick(s)}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}
      {twins.length > 0 && (
        <p role="status" className="m-0 text-sm">
          {t('review.sameName', { players: twins.map((o) => t('player', { n: o.identity })).join(', ') })}
        </p>
      )}
    </div>
  );
}
