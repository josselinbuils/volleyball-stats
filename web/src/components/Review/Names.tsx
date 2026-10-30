import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { GROUPS, groupName, teamColor, teamRing, type Group } from '@/lib/match';
import { post, type Named, type Suggestion } from '@/lib/review';
import { Pictures } from '@/components/Review/Pictures';
import { More } from '@/components/Review/More';

interface Given {
  name: string;
  jersey: string;
}

const INPUT =
  'h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2.5 text-[15px] font-normal shadow-xs outline-none dark:bg-input/30 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50';

const keyOf = (p: Named) => `${p.team}:${p.identity}`;

/** Focuses the card `step` cards away from the one holding `from` (the first without one), on its
 * first picture. */
function focusCard(from: Element | null, step: number) {
  const cards = [...document.querySelectorAll<HTMLElement>('[data-card]')];
  const at = cards.findIndex((c) => from !== null && c.contains(from));
  const card = cards[Math.max(0, Math.min(cards.length - 1, at < 0 ? 0 : at + step))];
  if (card) {
    (card.querySelector<HTMLElement>('[data-picture]') ?? card).focus();
    card.scrollIntoView({ block: 'nearest' });
  }
}
const fold = (name: string) => name.trim().toLocaleLowerCase();

/** The players of both teams to name, longest on court first; each name is saved as it is typed,
 * `onNamed` given the names and numbers saved by `team:identity`, `onMarked` how many answers are
 * saved when a picture is marked as someone else. */
export function Names({
  players,
  roster,
  onNamed,
  onMarked,
  onError,
}: {
  players: Named[];
  roster: [Suggestion[], Suggestion[]];
  onNamed: (saved: Map<string, Given>) => void;
  onMarked: (answered: number) => void;
  onError: () => void;
}) {
  const { t } = useTranslation();
  const [given, setGiven] = useState(() => new Map(players.map((p) => [keyOf(p), { name: p.name ?? '', jersey: p.jersey === null ? '' : String(p.jersey) }])));
  const [saved, setSaved] = useState<Map<string, Given>>(() => new Map(given));
  // The keyboard: arrows (or J/K) between cards and pictures, Space marks a picture, N names.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (event.ctrlKey || event.metaKey || event.altKey || target?.closest('input, textarea, select, dialog[open]')) {
        return;
      }
      const card = document.activeElement?.closest<HTMLElement>('[data-card]') ?? null;
      const key = event.key.toLowerCase();
      if (key === 'arrowdown' || key === 'j' || key === 'arrowup' || key === 'k') {
        event.preventDefault();
        focusCard(card, key === 'arrowdown' || key === 'j' ? 1 : -1);
      } else if ((key === 'arrowright' || key === 'arrowleft') && card) {
        event.preventDefault();
        const pictures = [...card.querySelectorAll<HTMLElement>('[data-picture]')];
        const at = pictures.indexOf(document.activeElement as HTMLElement);
        pictures[Math.max(0, Math.min(pictures.length - 1, at + (key === 'arrowright' ? 1 : -1)))]?.focus();
      } else if (key === 'n' && card) {
        event.preventDefault();
        card.querySelector<HTMLInputElement>('input[data-name]')?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

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
      onNamed(next);
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
                  players={players}
                  nameOf={(team, n) => given.get(`${team}:${n}`)?.name.trim() || null}
                  onMarked={onMarked}
                  onError={onError}
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
  players,
  nameOf,
  onMarked,
  onError,
}: {
  player: Named;
  g: Group;
  value: Given;
  saved: Given;
  others: { identity: number; name: string }[];
  onEdit: (value: Given) => void;
  onSave: (value: Given) => void;
  players: Named[];
  nameOf: (team: Group, identity: number) => string | null;
  onMarked: (answered: number) => void;
  onError: () => void;
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
    <div data-card tabIndex={-1} className="grid content-start gap-2.5 rounded-lg border bg-card p-3 outline-none focus-within:ring-2 focus-within:ring-ring/60">
      <Pictures crops={p.crops} pieces={p.pieces} owner={p} players={players} nameOf={nameOf} onSaved={onMarked} onError={onError} />
      <More player={p} label={nameOf(p.team, p.identity) ?? t('player', { n: p.identity })} onSaved={onMarked} onError={onError} />
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
          focusCard(event.currentTarget, 1);
        }}
      >
        <label htmlFor={`${id}-name`} className="grid flex-1 gap-1 text-sm font-medium">
          {t('review.name')}
          <input
            id={`${id}-name`}
            data-name
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
