import { useEffect, useRef, useState } from 'react';
import { Check, CircleCheck, CircleStop, Flag, PenLine, Play, Plus, Trash2, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { contacts, GROUPS, groupName, match, rallies, teamColor, teamRing, type Contact, type Group } from '@/lib/match';
import type { Named, ReportChanges } from '@/lib/review';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import type { NameOf } from '@/components/Review/helpers/players';
import { rallyAt, rallyOf, withServes } from '@/components/Review/helpers/report';

const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig'] as const;
const RESULTS = ['play', 'point', 'error'] as const;
const SELECT = 'h-8 min-w-0 flex-1 rounded-md border bg-background px-1.5 text-sm disabled:opacity-50';
/** A touch added under this long from one already listed is that one: the list shows it instead. */
const ADD_SAME_S = 0.1;
/** After the user scrolls the list, it stops following the video this long. */
const HOLD_MS = 3000;
/** The list shows this many rallies before and after the one the video is in. */
const AROUND_RALLIES = 2;

type Fix = { player?: string; type?: string; result?: string };
/** `join`: the rally and the next one are one, ending at the next one's end. */
type RallyFix = { winner?: Group; play?: false; end?: number; join?: true };
/** The team of a player given as "TEAM:IDENTITY". */
const teamOf = (player: string) => Number(player.split(':')[0]) as Group;
const frameOf = (time: number) => Math.round(time * match.fps);
/** What the answers name a rally by. */
const keyOf = (k: number) => rallies[k].key ?? frameOf(rallies[k].start);
/** A touch added: its team the picked player's, else the touch before's. */
type Added = { frame: number; time: number; team: Group; type: string; result: string; player?: string };
/** A touch as listed: one of the page's, or one added. */
type Row = { frame: number; time: number; rally: number; team: Group; type: string; result: string; player: string; removed: boolean; added: boolean; contact?: Contact };

/** The page's touches a player makes, with that player as "TEAM:IDENTITY". */
const touches = contacts
  .filter((c) => (TYPES as readonly string[]).includes(c.type) && c.team !== null)
  .map((c) => {
    const p = c.person === null ? undefined : match.people[c.person];
    return { contact: c, frame: frameOf(c.t), player: p && p.number !== null ? `${p.team}:${p.number}` : '' };
  });

/** The match's touches beside its video: those of the rallies around where the video stands, the
 * one it plays centred, to correct (player of either team, action, result), remove or add at the
 * video's moment; under it the winner, no play, end and joining with the next one of the rally it is
 * in (or just ended). It starts from the corrections saved and not applied yet (`saved`), marked as
 * such; saving sends them all, with the new ones. */
export function ReportEditor({
  reports,
  players,
  nameOf,
  now,
  timeOf,
  onPlay,
  onPause,
  onSave,
  green,
  onCaption,
  onChanges,
  saved,
}: {
  /** The moments viewers reported: their touches are flagged. */
  reports: { time: number }[];
  players: Named[];
  nameOf: NameOf;
  /** Where the video stands: its touch's row is highlighted and kept in view. */
  now: number;
  /** Where the video stands, to the frame. */
  timeOf: () => number;
  /** Plays the video from a moment. */
  onPlay: (time: number) => void;
  /** Stops the video at a moment. */
  onPause: (time: number) => void;
  /** Saves the corrections, the rally the video is in (by its key) checked with them. */
  onSave: (changes: ReportChanges, rally: number) => void;
  /** The rallies checked with no report open since, by their key: shown green. */
  green: Set<number>;
  /** The corrections as they stand, saved or not. */
  onChanges?: (changes: ReportChanges) => void;
  /** The touch the video is on in its rally, as it stands with the corrections: to show over the video. */
  onCaption?: (caption: { team: Group; text: string } | null) => void;
  saved: Partial<ReportChanges>;
}) {
  const { t } = useTranslation();
  const [fixes, setFixes] = useState<Record<number, Fix>>(() => Object.fromEntries((saved.touches ?? []).map(({ frame, ...fix }) => [frame, fix])));
  const [added, setAdded] = useState<Added[]>(() => (saved.added ?? []).map((a) => ({ ...a, time: a.frame / match.fps })));
  const [rallyFixes, setRallyFixes] = useState<Record<number, RallyFix>>(() =>
    Object.fromEntries(
      (saved.rallies ?? []).flatMap(({ start, end, ...fix }) => {
        const k = rallies.findIndex((_, n) => keyOf(n) === start);
        return k < 0 ? [] : [[k, { ...fix, ...(end !== undefined ? { end: end / match.fps } : {}) }]];
      }),
    ),
  );
  // The touches and rallies the saved corrections change.
  const savedFrames = new Set([...(saved.touches ?? []), ...(saved.added ?? [])].map((x) => x.frame));
  const savedStarts = new Set((saved.rallies ?? []).map((r) => r.start));

  // A change back to the touch's own value is no change.
  const edit = (row: Row, change: Fix) =>
    setFixes((all) => {
      const c = row.contact!;
      const next: Fix = { ...all[row.frame], ...change };
      const own: Fix = { player: touches.find((x) => x.frame === row.frame)?.player || undefined, type: c.type, result: c.result };
      for (const k of ['player', 'type', 'result'] as const) {
        if (next[k] === undefined || next[k] === own[k]) {
          delete next[k];
        }
      }
      const out = { ...all };
      delete out[row.frame];
      return Object.keys(next).length ? { ...out, [row.frame]: next } : out;
    });
  const editAdded = (frame: number, change: Partial<Added>) => setAdded((all) => all.map((a) => (a.frame === frame ? { ...a, ...change } : a)));
  const editRally = (k: number, change: RallyFix) =>
    setRallyFixes((all) => {
      const next: RallyFix = { ...all[k], ...change };
      // Joined, the rally's winner is the next one's.
      if (next.winner === (next.join ? rallies[k + 1]?.winner : rallies[k].winner)) {
        delete next.winner;
      }
      for (const key of ['play', 'end', 'join'] as const) {
        if (next[key] === undefined) {
          delete next[key];
        }
      }
      const out = { ...all };
      delete out[k];
      return Object.keys(next).length ? { ...out, [k]: next } : out;
    });

  // The rally the video is in, or just ended, and those shown around it.
  // The rallies as they will be: each starting at a serve added before it.
  const shown = withServes(rallies, added);
  const here = rallyAt(shown, now);
  const first = Math.max(0, here - AROUND_RALLIES);
  const last = Math.min(rallies.length - 1, here + AROUND_RALLIES);
  const rows: Row[] = [
    ...touches
      .filter((x) => x.contact.rally >= first && x.contact.rally <= last)
      .map(({ contact: c, frame, player }) => {
        const fix = fixes[frame] ?? {};
        return {
          frame,
          time: c.t,
          rally: c.rally,
          team: fix.player && fix.player !== 'none' ? teamOf(fix.player) : (c.team as Group),
          type: fix.type ?? c.type,
          result: fix.result ?? c.result,
          player: fix.player === 'none' ? '' : (fix.player ?? player),
          removed: fix.player === 'none',
          added: false,
          contact: c,
        };
      }),
    ...added.map((a) => ({ ...a, rally: rallyOf(shown, a.time, a.type), player: a.player ?? '', removed: false, added: true })).filter((a) => a.rally >= first && a.rally <= last),
  ].sort((a, b) => a.time - b.time);

  const changes: ReportChanges = {
    touches: Object.entries(fixes).map(([frame, c]) => ({ frame: Number(frame), ...c })),
    ...(added.length ? { added: added.map(({ frame, team, type, result, player }) => ({ frame, team, type, result, ...(player ? { player } : {}) })) } : {}),
    ...(Object.keys(rallyFixes).length ? { rallies: Object.entries(rallyFixes).map(([k, f]) => ({ start: keyOf(Number(k)), ...f, ...(f.end !== undefined ? { end: frameOf(f.end) } : {}) })) } : {}),
  };
  const json = JSON.stringify(changes);
  useEffect(() => {
    onChanges?.(changes);
  }, [json]);

  // The touch the video is on: the last one started, highlighted until 3 s after it; a removed one
  // gives way to the touch still there.
  const started = rows.filter((row) => !row.removed && row.time - 0.2 <= now).at(-1);
  const playing = started && now - started.time < 3 ? started.frame : undefined;
  // The touches a viewer reported from (the moment replayed then).
  const reported = new Set(rows.filter((row) => reports.some((r) => Math.abs(r.time - row.time) <= 0.6)).map((row) => row.frame));
  const canAdd = rallies.length > 0;
  const add = () => {
    const time = timeOf();
    const frame = frameOf(time);
    const there = rows.find((row) => Math.abs(row.time - time) < ADD_SAME_S);
    if (there) {
      setFresh({ key: `t${there.frame}` });
      onPause(there.time);
      return;
    }
    // The team of the touch before it, most often the same.
    const before = rows.filter((row) => row.time <= time).at(-1);
    setAdded((all) => [...all, { frame, time, team: before?.team ?? GROUPS[0], type: 'pass', result: 'play' }]);
    setFresh({ key: `t${frame}` });
    onPause(time);
  };

  // The list follows the video, its touch (else its rally) centred, except while a field in it is
  // being filled or shortly after the user scrolled it.
  const list = useRef<HTMLOListElement>(null);
  const [editing, setEditing] = useState(false);
  const scrolled = useRef(0);
  const inHere = started && started.rally === here ? started : undefined;
  const who = (player: string) => {
    const [team, n] = player.split(':').map(Number);
    return player ? (nameOf(team as Group, n) ?? t('player', { n })) : t('players.rest');
  };
  const caption = inHere && (inHere.removed ? `${t(`types.${inHere.type}`)} · ${t('review.reportRemoved')}` : `${t(`actions.${inHere.type}.${inHere.result}`)} · ${who(inHere.player)}`);
  useEffect(() => {
    onCaption?.(inHere && caption ? { team: inHere.team, text: caption } : null);
  }, [caption, inHere?.team]);
  useEffect(() => () => onCaption?.(null), []);
  const current = inHere ? `t${inHere.frame}` : `r${here}`;
  const centre = (key: string) => {
    const box = list.current;
    const item = box?.querySelector<HTMLElement>(`[data-key="${key}"]`);
    box?.scrollTo({ top: item ? item.offsetTop - (box.clientHeight - item.offsetHeight) / 2 : 0, behavior: 'smooth' });
    return item;
  };
  useEffect(() => {
    if (!editing && Date.now() - scrolled.current > HOLD_MS) {
      centre(current);
    }
  }, [current, editing]);
  // A touch just added: in view, its player field ready to type in.
  const [fresh, setFresh] = useState<{ key: string }>();
  useEffect(() => {
    if (fresh !== undefined) {
      centre(fresh.key)?.querySelector('input')?.focus({ preventScroll: true });
    }
  }, [fresh]);

  const rally = rallies[here];
  const fix = rallyFixes[here] ?? {};
  const winner = fix.winner ?? (fix.join ? rallies[here + 1]?.winner : rally?.winner) ?? null;
  const end = fix.end ?? rally?.end;
  const endOf = (k: number) => clock(rallyFixes[k]?.end ?? rallies[k].end);
  const rallyLabel = (k: number) =>
    rallyFixes[k]?.join
      ? t('review.reportRallyJoined', { n: k + 1, m: k + 2, from: clock(shown[k].start), to: endOf(k + 1) })
      : t(rallyFixes[k - 1]?.join ? 'review.reportRallyJoinedTo' : 'review.reportRally', { n: k + 1, m: k, from: clock(shown[k].start), to: endOf(k) });
  // Joined only to the next rally of its set.
  const canJoin = rallies[here + 1]?.set === rally?.set;

  return (
    <>
      <div className="relative lg:self-stretch">
        <div className="flex max-h-[70vh] flex-col gap-2 lg:absolute lg:inset-0 lg:max-h-none">
          <Button variant="outline" className="shrink-0 bg-card" disabled={!canAdd} onClick={add}>
            <Plus aria-hidden />
            {t('review.reportAdd', { time: clock(now) })}
          </Button>
          <ol
            ref={list}
            aria-label={t('review.reportTouches')}
            className="relative grid min-h-0 flex-1 auto-rows-max grid-cols-[minmax(0,1fr)] gap-1.5 overflow-y-auto overscroll-contain pr-1"
            onWheel={() => (scrolled.current = Date.now())}
            onTouchMove={() => (scrolled.current = Date.now())}
            onFocus={(event) => setEditing(event.target.matches('input, select'))}
            onBlur={() => setEditing(false)}
          >
            {Array.from({ length: last - first + 1 }, (_, n) => first + n).flatMap((k) => [
              <li key={`r${k}`} data-key={`r${k}`} className={cn('sticky top-0 z-10 rounded-md bg-card', k === here && 'text-primary')}>
                <button
                  type="button"
                  title={t('review.reportRallyPlay')}
                  onClick={() => onPlay(shown[k].start)}
                  className={cn(
                    'flex w-full items-center gap-1.5 rounded-md border bg-muted px-2 py-1 text-left text-sm font-medium outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50',
                    green.has(keyOf(k)) && 'border-emerald-300 bg-emerald-100 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
                    k === here && 'border-primary',
                    rallyFixes[k]?.play === false && 'line-through',
                  )}
                >
                  <Play aria-hidden className="size-3.5 shrink-0 fill-current" />
                  <span className="truncate">{rallyLabel(k)}</span>
                  {green.has(keyOf(k)) && <CircleCheck aria-label={t('review.rallyChecked')} className="size-3.5 shrink-0 text-emerald-700 dark:text-emerald-400" />}
                  {savedStarts.has(keyOf(k)) && (
                    <span role="img" title={t('review.reportSaved')} aria-label={t('review.reportSaved')} className="ml-auto shrink-0">
                      <PenLine aria-hidden className="size-3.5" />
                    </span>
                  )}
                </button>
              </li>,
              ...rows
                .filter((row) => row.rally === k)
                .map((row) => {
                  const remove = () => (row.added ? setAdded((all) => all.filter((a) => a.frame !== row.frame)) : edit(row, { player: 'none' }));
                  const change = (c: Fix) => (row.added ? editAdded(row.frame, c) : edit(row, c));
                  return (
                    <li
                      key={`t${row.frame}`}
                      data-key={`t${row.frame}`}
                      className={cn(
                        'grid grid-cols-[minmax(0,1fr)] gap-1.5 rounded-md border bg-card p-1.5 transition-colors',
                        row.frame === playing && 'border-primary bg-primary/10',
                        row.removed && 'bg-muted/50',
                      )}
                    >
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          title={t('review.reportPlay')}
                          aria-label={`${t('review.reportPlay')} ${clock(row.time)}`}
                          onClick={() => onPlay(row.time)}
                          className="flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-sm tabular-nums outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50"
                        >
                          <Play aria-hidden className="size-3.5 fill-current" />
                          <Swatch color={teamColor(row.team)} ring={teamRing(row.team)} />
                          {clock(row.time)}
                          {reported.has(row.frame) && <Flag aria-label={t('review.reportedTouch')} className="size-3.5 text-primary" />}
                          {savedFrames.has(row.frame) && (
                            <span role="img" title={t('review.reportSaved')} aria-label={t('review.reportSaved')}>
                              <PenLine aria-hidden className="size-3.5 text-muted-foreground" />
                            </span>
                          )}
                        </button>
                        {row.removed ? (
                          <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground line-through">{t(`types.${row.type}`)}</span>
                        ) : (
                          <>
                            <select className={SELECT} aria-label={t('review.reportType')} value={row.type} onChange={(e) => change({ type: e.target.value })}>
                              {TYPES.map((type) => (
                                <option key={type} value={type}>
                                  {t(`types.${type}`)}
                                </option>
                              ))}
                            </select>
                            <select className={SELECT} aria-label={t('review.reportResult')} value={row.result} onChange={(e) => change({ result: e.target.value })}>
                              {RESULTS.map((result) => (
                                <option key={result} value={result}>
                                  {t(`results.${result}`)}
                                </option>
                              ))}
                            </select>
                          </>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-8 shrink-0"
                          title={t(row.removed ? 'review.reportRestore' : 'review.reportRemove')}
                          aria-label={t(row.removed ? 'review.reportRestore' : 'review.reportRemove')}
                          onClick={() => (row.removed ? edit(row, { player: undefined }) : remove())}
                        >
                          {row.removed ? <Undo2 aria-hidden /> : <Trash2 aria-hidden />}
                        </Button>
                      </div>
                      {!row.removed && (
                        <PlayerSelect
                          // Anyone of either team: the touch takes the player's team.
                          players={players}
                          nameOf={nameOf}
                          value={row.player}
                          empty={t('review.pickPlayer')}
                          label={t('review.reportPlayer')}
                          className="h-8 min-w-0 text-sm font-normal"
                          openOnFocus={false}
                          onChange={(who) => who && (row.added ? editAdded(row.frame, { player: who, team: teamOf(who) }) : change({ player: who }))}
                        />
                      )}
                    </li>
                  );
                }),
            ])}
          </ol>
        </div>
      </div>
      {rally && (
        <div className="grid gap-3 lg:col-span-2">
          <p className="text-sm font-medium">{rallyLabel(here)}</p>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
            <span className="flex flex-wrap items-center gap-2">
              {t('review.reportWinner')}
              <ToggleGroup type="single" variant="outline" spacing={0} value={winner === null ? '' : String(winner)} onValueChange={(v) => v && editRally(here, { winner: Number(v) as Group })}>
                {GROUPS.map((g) => (
                  <ToggleGroupItem key={g} value={String(g)} className="h-9 gap-2 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                    <Swatch color={teamColor(g)} ring={teamRing(g)} />
                    {groupName(t, g)}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </span>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={fix.play === false} onChange={(e) => editRally(here, { play: e.target.checked ? false : undefined })} />
              {t('review.notPlay')}
            </label>
            <label className={cn('flex items-center gap-2', !canJoin && 'text-muted-foreground')}>
              <input type="checkbox" checked={fix.join === true} disabled={!canJoin} onChange={(e) => editRally(here, { join: e.target.checked ? true : undefined })} />
              {t('review.reportJoin', { n: here + 2 })}
            </label>
            <span className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" className="bg-card" disabled={now <= rally.start} onClick={() => editRally(here, { end: Math.round(timeOf() * 100) / 100 })}>
                <CircleStop aria-hidden />
                {t('review.reportEndHere', { time: clock(now) })}
              </Button>
              {fix.end !== undefined && (
                <Button variant="ghost" size="sm" onClick={() => editRally(here, { end: undefined })}>
                  <Undo2 aria-hidden />
                  {t('review.reportEndReset', { time: clock(rally.end) })}
                </Button>
              )}
              {end !== undefined && fix.end !== undefined && <span className="text-muted-foreground">{t('review.reportEndMoved', { time: clock(end) })}</span>}
            </span>
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2 lg:col-span-2">
        <Button disabled={!rally} onClick={() => onSave(changes, keyOf(here))}>
          <Check aria-hidden />
          {t('review.validateRally', { n: here + 1 })}
        </Button>
      </div>
    </>
  );
}
