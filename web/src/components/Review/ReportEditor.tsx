import { useEffect, useRef, useState } from 'react';
import { Check, CircleCheck, CircleOff, Flag, MessageSquareText, PenLine, Play, Plus, RotateCcw, SquarePlus, Trash2, TriangleAlert, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { contacts, GROUPS, groupName, hasTeams, match, rallies, teamColor, teamRing, type Contact, type Group } from '@/lib/match';
import type { Named, ReportChanges } from '@/lib/review';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import { RallyComment } from '@/components/Review/RallyComment';
import type { NameOf } from '@/components/Review/helpers/players';
import { freeFrame, NEXT_TOUCH_S, nextTouch, offGiven, pieceOf, rallyAt, rallyOf, runningScores, withAdded, withSplits } from '@/components/Review/helpers/report';
import { problems, type Problem } from '@/components/Review/helpers/checks';

const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig', 'fault'] as const;
const RESULTS = ['play', 'point', 'error'] as const;
const SELECT = 'h-8 min-w-0 flex-1 rounded-md border bg-background px-1.5 text-sm disabled:opacity-50';
/** After the user scrolls the list, it stops following the video this long. */
const HOLD_MS = 3000;
/** The list shows this many rallies before and after the one the video is in. */
const AROUND_RALLIES = 2;

type Fix = { player?: string; type?: string; result?: string };
/** `join`: the rally and the next one are one, ending at the next one's end. `redo`: to replay,
 * nobody gets the point; false takes back what the page shows. `wrong`: the referee gave the
 * point to the wrong team, `winner` being the one that got it; false likewise. */
type RallyFix = { winner?: Group; play?: false; join?: true; redo?: boolean; wrong?: boolean };
/** The team of a player given as "TEAM:IDENTITY". */
const teamOf = (player: string) => Number(player.split(':')[0]) as Group;
const frameOf = (time: number) => Math.round(time * match.fps);
/** A touch added: its team the picked player's, else the touch before's. */
type Added = { frame: number; time: number; team: Group; type: string; result: string; player?: string };
/** A touch as listed: one of the page's, or one added. */
type Row = { frame: number; time: number; rally: number; team: Group; type: string; result: string; player: string; removed: boolean; added: boolean; contact?: Contact };

/** The page's touches a player makes, with that player as "TEAM:IDENTITY". */
const touches = contacts
  .filter((c) => (TYPES as readonly string[]).includes(c.type) && c.team !== null)
  .map((c) => {
    const p = c.person === null ? undefined : match.people[c.person];
    return { contact: c, frame: c.f ?? frameOf(c.t), player: p && p.number !== null ? `${p.team}:${p.number}` : '' };
  });

/** The match's touches beside its video: those of the rallies around where the video stands, the
 * one it plays centred, to correct (player of either team, action, result), remove or add at the
 * video's moment, or start a rally there (one missed, or the second of two taken for one); under it
 * the winner or to replay, no play and joining with the next one of the rally it is in (or just ended). It starts from the corrections saved and not applied yet (`saved`), marked as
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
  checked,
  onUncheck,
  onCaption,
  onChanges,
  onWarnings,
  saved,
  comments,
  onComment,
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
  /** The rallies checked, by their key, a report open on them or not. */
  checked: Set<number>;
  onUncheck: (rally: number) => void;
  /** The corrections as they stand, saved or not. */
  onChanges?: (changes: ReportChanges) => void;
  /** The rallies with a warning as they stand, by their key. */
  onWarnings?: (keys: number[]) => void;
  /** The touch the video is on in its rally, as it stands with the corrections: to show over the video. */
  onCaption?: (caption: { team: Group; text: string } | null) => void;
  saved: Partial<ReportChanges>;
  /** The owner's notes on the rallies, by their key. */
  comments: Record<number, string>;
  onComment: (rally: number, text: string) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [fixes, setFixes] = useState<Record<number, Fix>>(() => Object.fromEntries((saved.touches ?? []).map(({ frame, ...fix }) => [frame, fix])));
  const [added, setAdded] = useState<Added[]>(() => (saved.added ?? []).map((a) => ({ ...a, time: a.frame / match.fps })));
  // The rallies started by the review, by their start frame.
  const [splits, setSplits] = useState<number[]>(() => saved.splits ?? []);
  // By the rally's key: a rally started before one keeps its index from moving its fixes.
  const [rallyFixes, setRallyFixes] = useState<Record<number, RallyFix>>(() => Object.fromEntries((saved.rallies ?? []).map(({ start, ...fix }) => [start, fix])));
  // The touches and rallies the saved corrections change.
  const savedFrames = new Set([...(saved.touches ?? []), ...(saved.added ?? [])].map((x) => x.frame));
  const savedStarts = new Set([...(saved.rallies ?? []).map((r) => r.start), ...(saved.splits ?? [])]);

  // The rallies as they will be: those the review started, each starting at a serve added before it.
  const split = withSplits(rallies, splits, match.fps);
  const shown = withAdded(split, added);
  /** What the answers name a rally by. */
  const keyOf = (k: number) => shown[k].key;
  const fixOf = (k: number): RallyFix | undefined => (shown[k] ? rallyFixes[shown[k].key] : undefined);
  const toReplay = (k: number) => fixOf(k)?.redo ?? shown[k]?.redo ?? false;
  const calledWrong = (k: number) => fixOf(k)?.wrong ?? shown[k]?.wrongCall ?? false;

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
      const key = keyOf(k);
      const next: RallyFix = { ...all[key], ...change };
      // Joined, the rally's winner is the next one's.
      // Marked as the referee's error, the winner is said: no last touch gives it.
      if (!(next.wrong ?? shown[k].wrongCall) && next.winner === (next.join ? shown[k + 1]?.winner : shown[k].winner)) {
        delete next.winner;
      }
      if (next.redo === !!shown[k].redo) {
        delete next.redo;
      }
      if (next.wrong === !!shown[k].wrongCall) {
        delete next.wrong;
      }
      for (const key of ['winner', 'play', 'join', 'redo', 'wrong'] as const) {
        if (next[key] === undefined) {
          delete next[key];
        }
      }
      const out = { ...all };
      delete out[key];
      return Object.keys(next).length ? { ...out, [key]: next } : out;
    });

  // The rally the video is in, or just ended, and those shown around it.
  const here = rallyAt(shown, now);
  const first = Math.max(0, here - AROUND_RALLIES);
  const last = Math.min(shown.length - 1, here + AROUND_RALLIES);
  // Every touch, to check every rally; those of the rallies around listed.
  const allRows: Row[] = [
    ...touches.map(({ contact: c, frame, player }) => {
      const fix = fixes[frame] ?? {};
      return {
        frame,
        time: c.t,
        rally: pieceOf(split, c.rally, c.t),
        team: fix.player && fix.player !== 'none' ? teamOf(fix.player) : (c.team as Group),
        type: fix.type ?? c.type,
        result: fix.result ?? c.result,
        player: fix.player === 'none' ? '' : (fix.player ?? player),
        removed: fix.player === 'none',
        added: false,
        contact: c,
      };
    }),
    ...added.map((a) => ({ ...a, rally: rallyOf(shown, a.time, a.type), player: a.player ?? '', removed: false, added: true })),
  ].sort((a, b) => a.time - b.time);
  const rows = allRows.filter((row) => row.rally >= first && row.rally <= last);
  // The touches kept, by rally.
  const kept = new Map<number, Row[]>();
  for (const row of allRows) {
    if (!row.removed) {
      kept.set(row.rally, [...(kept.get(row.rally) ?? []), row]);
    }
  }
  /** A rally's touches kept, the next one's too when joined to it. */
  const mineOf = (k: number) => [...(kept.get(k) ?? []), ...(fixOf(k)?.join ? (kept.get(k + 1) ?? []) : [])];

  const changes: ReportChanges = {
    touches: Object.entries(fixes).map(([frame, c]) => ({ frame: Number(frame), ...c })),
    ...(added.length ? { added: added.map(({ frame, team, type, result, player }) => ({ frame, team, type, result, ...(player ? { player } : {}) })) } : {}),
    ...(Object.keys(rallyFixes).length ? { rallies: Object.entries(rallyFixes).map(([key, f]) => ({ start: Number(key), ...f })) } : {}),
    ...(splits.length ? { splits } : {}),
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
    const frame = freeFrame([...contacts.map((c) => c.f ?? frameOf(c.t)), ...added.map((a) => a.frame)], frameOf(timeOf()));
    const time = frame / match.fps;
    // What follows the touch before it in its rally; with none, a serve by the last rally's winner.
    const before = rows.filter((row) => !row.removed && row.time <= time).at(-1);
    const follows = before && before.rally === rallyAt(shown, time) && time - before.time < NEXT_TOUCH_S;
    const guess = nextTouch(follows ? before : undefined, (before && winnerOf(before.rally)) ?? before?.team ?? GROUPS[0]);
    setAdded((all) => [...all, { frame, time, ...guess, result: 'play' }]);
    setFresh({ key: `t${frame}` });
    onPause(time);
  };
  // A rally started where one already starts is that one.
  const startHere = () => {
    const frame = frameOf(timeOf());
    if (!shown.some((r) => r.key === frame || frameOf(r.start) === frame)) {
      setSplits((all) => [...all, frame]);
    }
    onPause(frame / match.fps);
  };
  const unsplit = (k: number) => {
    const key = keyOf(k);
    setSplits((all) => all.filter((f) => f !== key));
    setRallyFixes((all) => Object.fromEntries(Object.entries(all).filter(([k]) => Number(k) !== key)));
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

  const rally = shown[here];
  const fix = fixOf(here) ?? {};
  const endOf = (k: number) => clock(shown[k].end);
  const rallyLabel = (k: number) =>
    (fixOf(k)?.join
      ? t('review.reportRallyJoined', { n: k + 1, m: k + 2, from: clock(shown[k].start), to: endOf(k + 1) })
      : t(fixOf(k - 1)?.join ? 'review.reportRallyJoinedTo' : 'review.reportRally', { n: k + 1, m: k, from: clock(shown[k].start), to: endOf(k) })) +
    (splits.includes(shown[k].key) ? ` · ${t('review.reportRallyNew')}` : '') +
    (toReplay(k) ? ` · ${t('review.reportRedo')}` : '') +
    (calledWrong(k) ? ` · ${t('review.reportWrongCall')}` : '');
  // Joined only to the next rally of its set.
  const canJoin = shown[here + 1]?.set === rally?.set;

  // What looks wrong in each rally shown, as it stands with the corrections: a rally joined to the
  // next one is checked with its touches, one said no play not at all.
  // A rally's winner: the one set, else the one its last touch's result says, else the page's.
  const lastOf = (k: number) => kept.get(fixOf(k)?.join ? k + 1 : k)?.at(-1);
  const winnerOf = (k: number): Group | null => {
    if (toReplay(k)) {
      return null;
    }
    if (calledWrong(k)) {
      return fixOf(k)?.winner ?? (fixOf(k)?.join ? shown[k + 1]?.winner : shown[k]?.winner) ?? null;
    }
    // As on the page: the last touch says it, a point for its team or a fault for the other's; one
    // in play, or none, leaves the winner given.
    const last = lastOf(k);
    const said = last?.result === 'point' ? last.team : last?.result === 'error' ? ((3 - last.team) as Group) : undefined;
    return said ?? fixOf(k)?.winner ?? (fixOf(k)?.join ? shown[k + 1]?.winner : shown[k]?.winner) ?? null;
  };
  const setLastResult = (k: number, result: string) => {
    const last = lastOf(k);
    if (last?.added) {
      editAdded(last.frame, { result });
    } else if (last) {
      edit(last, { result });
    }
  };
  // A winner picked makes the rally's last touch a point for them or a fault of the other team.
  const pickWinner = (k: number, w: Group) => {
    const last = lastOf(k);
    if (last) {
      setLastResult(k, last.team === w ? 'point' : 'error');
    }
    editRally(k, { winner: w, redo: false, wrong: false });
  };
  // To replay: nobody gets the point, its last touch stays in play.
  const pickReplay = (k: number) => {
    setLastResult(k, 'play');
    editRally(k, { winner: undefined, redo: true, wrong: false });
  };
  // The referee's error: the winner stays the team that got the point, the last touch says what
  // really happened (the other team won it); taken back, it says the winner won it.
  const markWrongCall = (k: number, on: boolean) => {
    const w = winnerOf(k);
    const last = lastOf(k);
    if (w === null) {
      return;
    }
    if (last) {
      setLastResult(k, (last.team === w) === on ? 'error' : 'point');
    }
    editRally(k, { winner: w, wrong: on });
  };
  const winner = rally ? winnerOf(here) : null;
  const found = new Map<number, ReturnType<typeof problems>>();
  for (let k = 0; k < shown.length; k++) {
    if (fixOf(k)?.play === false || fixOf(k - 1)?.join) {
      continue;
    }
    const mine = mineOf(k);
    // After the referee's error the serve may follow what really happened or the point given: no check.
    const previous = k > 0 && shown[k - 1].set === shown[k].set && fixOf(k - 1)?.play !== false && !calledWrong(k - 1) ? winnerOf(k - 1) : null;
    found.set(k, problems(mine, winnerOf(k), previous, hasTeams && !toReplay(k)));
  }
  const problemsOf = (row: Row): Problem[] => {
    const k = fixOf(row.rally - 1)?.join ? row.rally - 1 : row.rally;
    const mine = mineOf(k);
    return row.removed ? [] : (found.get(k)?.touch.get(mine.indexOf(row)) ?? []);
  };
  const describe = (list: Problem[]) => list.map((p) => t(`feedback.kinds.auto.${p}`)).join(' · ');
  const rallyProblems = (k: number) => {
    const f = found.get(k);
    return f ? [...f.rally, ...[...f.touch.values()].flat()] : [];
  };
  // The score after each rally as it stands with the corrections, the rallies out of view with
  // their winner set or the page's; a set ending off the final score given is flagged.
  const scores = hasTeams ? runningScores(shown.map((r, k) => ({ set: r.set, winner: winnerOf(k), skip: fixOf(k)?.play === false || !!fixOf(k - 1)?.join }))) : [];
  const off = offGiven(
    shown.map((r) => r.set),
    scores,
    match.scores,
  );
  // The rallies with a warning, by their key, for the match's bar.
  const warned = shown.flatMap((r, k) => (rallyProblems(k).length > 0 || off.has(k) ? [r.key] : []));
  const warnedJson = JSON.stringify(warned);
  useEffect(() => {
    onWarnings?.(warned);
  }, [warnedJson]);

  return (
    <>
      {/* Beside the video and the rally's section under it; in full screen, the window's height: the
       * buttons under the list cover none of it. */}
      <div className="relative lg:row-span-2 lg:self-stretch lg:[:fullscreen_&]:sticky lg:[:fullscreen_&]:top-0 lg:[:fullscreen_&]:h-[calc(100vh-(--spacing(8)))] lg:[:fullscreen_&]:self-start">
        <div className="flex max-h-[70vh] flex-col gap-2 lg:absolute lg:inset-0 lg:max-h-none">
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button variant="outline" className="flex-1 bg-card" disabled={!canAdd} onClick={add}>
              <Plus aria-hidden />
              {t('review.reportAdd', { time: clock(now) })}
            </Button>
            <Button variant="outline" className="flex-1 bg-card" title={t('review.reportStartHelp')} onClick={startHere}>
              <SquarePlus aria-hidden />
              {t('review.reportStart', { time: clock(now) })}
            </Button>
          </div>
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
                    // A warning outweighs the check: the rally needs another look.
                    rallyProblems(k).length > 0 || off.has(k)
                      ? 'border-amber-300 bg-amber-100 text-amber-900 hover:bg-amber-200 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200 dark:hover:bg-amber-900'
                      : green.has(keyOf(k)) && 'border-emerald-300 bg-emerald-100 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
                    k === here && 'border-primary',
                    fixOf(k)?.play === false && 'line-through',
                  )}
                >
                  <Play aria-hidden className="size-3.5 shrink-0 fill-current" />
                  <span className="truncate">{rallyLabel(k)}</span>
                  {green.has(keyOf(k)) && <CircleCheck aria-label={t('review.rallyChecked')} className="size-3.5 shrink-0 text-emerald-700 dark:text-emerald-400" />}
                  {rallyProblems(k).length > 0 && (
                    <span role="img" title={describe([...new Set(rallyProblems(k))])} aria-label={describe([...new Set(rallyProblems(k))])} className="shrink-0">
                      <TriangleAlert aria-hidden className="size-3.5 text-amber-600 dark:text-amber-400" />
                    </span>
                  )}
                  {comments[keyOf(k)] && (
                    <span role="img" title={comments[keyOf(k)]} aria-label={comments[keyOf(k)]} className="shrink-0">
                      <MessageSquareText aria-hidden className="size-3.5 text-sky-600 dark:text-sky-400" />
                    </span>
                  )}
                  {savedStarts.has(keyOf(k)) && (
                    <span role="img" title={t('review.reportSaved')} aria-label={t('review.reportSaved')} className="ml-auto shrink-0">
                      <PenLine aria-hidden className="size-3.5" />
                    </span>
                  )}
                </button>
              </li>,
              ...(found.get(k)?.rally.length
                ? [
                    <li key={`p${k}`} className="flex items-center gap-1.5 px-2 text-xs text-amber-800 dark:text-amber-300">
                      <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
                      {describe(found.get(k)!.rally)}
                    </li>,
                  ]
                : []),
              ...rows
                .filter((row) => row.rally === k)
                .map((row) => {
                  const remove = () => (row.added ? setAdded((all) => all.filter((a) => a.frame !== row.frame)) : edit(row, { player: 'none' }));
                  const change = (c: Fix) => {
                    // A point or a fault said on a touch ends the rally: it is no longer to replay.
                    const owner = fixOf(row.rally - 1)?.join ? row.rally - 1 : row.rally;
                    if (c.result && c.result !== 'play' && toReplay(owner)) {
                      editRally(owner, { redo: false });
                    }
                    if (row.added) {
                      editAdded(row.frame, c);
                    } else {
                      edit(row, c);
                    }
                  };
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
                            <select
                              className={SELECT}
                              aria-label={t('review.reportType')}
                              value={row.type}
                              onChange={(e) => change({ type: e.target.value, ...(e.target.value === 'fault' ? { result: 'error' } : {}) })}
                            >
                              {TYPES.map((type) => (
                                <option key={type} value={type}>
                                  {t(`types.${type}`)}
                                </option>
                              ))}
                            </select>
                            <select
                              className={SELECT}
                              aria-label={t('review.reportResult')}
                              value={row.result}
                              // A playing fault is always one.
                              disabled={row.type === 'fault'}
                              onChange={(e) => {
                                change({ result: e.target.value });
                              }}
                            >
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
                      {problemsOf(row).length > 0 && (
                        <p className="m-0 flex items-center gap-1.5 px-1 text-xs text-amber-800 dark:text-amber-300">
                          <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
                          {describe(problemsOf(row))}
                        </p>
                      )}
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
              // The score once the rally is over, between it and the next one.
              ...(scores[k]
                ? [
                    <li
                      key={`s${k}`}
                      className={cn(
                        'my-1 flex flex-wrap items-center justify-center gap-x-2.5 gap-y-0.5 rounded-md border-2 border-foreground/25 bg-secondary px-3 py-1.5 text-sm shadow-sm',
                        off.has(k) && 'border-amber-500 bg-amber-100 text-amber-900 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-200',
                      )}
                    >
                      <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                        {t(shown[k + 1]?.set === shown[k].set ? 'review.reportScoreAfter' : 'review.reportScoreSet', { n: shown[k].set })}
                      </span>
                      <span className="flex items-center gap-1.5 font-medium tabular-nums">
                        <Swatch color={teamColor(1)} ring={teamRing(1)} />
                        {groupName(t, 1)}
                        <span className="text-lg font-bold">
                          {scores[k]![0]} – {scores[k]![1]}
                        </span>
                        {groupName(t, 2)}
                        <Swatch color={teamColor(2)} ring={teamRing(2)} />
                      </span>
                      {off.has(k) && (
                        <span className="flex items-center gap-1">
                          <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
                          {t('review.reportScoreGiven', { given: off.get(k) })}
                        </span>
                      )}
                    </li>,
                  ]
                : []),
            ])}
          </ol>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button className="h-auto min-h-9 flex-1 whitespace-normal" disabled={!rally} onClick={() => onSave(changes, keyOf(here))}>
              <Check aria-hidden />
              {t(rally && checked.has(keyOf(here)) ? 'review.updateRally' : 'review.validateRally', { n: here + 1 })}
            </Button>
            {rally && checked.has(keyOf(here)) && (
              <Button variant="outline" className="h-auto min-h-9 flex-1 whitespace-normal bg-card" onClick={() => onUncheck(keyOf(here))}>
                <CircleOff aria-hidden />
                {t('review.uncheckRally', { n: here + 1 })}
              </Button>
            )}
          </div>
        </div>
      </div>
      {rally && (
        <div className="grid gap-3">
          <p className="text-sm font-medium">{rallyLabel(here)}</p>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
            <span className="flex flex-wrap items-center gap-2">
              {t('review.reportWinner')}
              <ToggleGroup
                type="single"
                variant="outline"
                spacing={0}
                value={toReplay(here) ? 'redo' : winner === null ? '' : String(winner)}
                onValueChange={(v) => v && (v === 'redo' ? pickReplay(here) : pickWinner(here, Number(v) as Group))}
              >
                {GROUPS.map((g) => (
                  <ToggleGroupItem key={g} value={String(g)} className="h-9 gap-2 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                    <Swatch color={teamColor(g)} ring={teamRing(g)} />
                    {groupName(t, g)}
                  </ToggleGroupItem>
                ))}
                <ToggleGroupItem value="redo" title={t('review.reportRedoHelp')} className="h-9 gap-2 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                  <RotateCcw aria-hidden />
                  {t('review.reportRedo')}
                </ToggleGroupItem>
              </ToggleGroup>
            </span>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={fix.play === false} onChange={(e) => editRally(here, { play: e.target.checked ? false : undefined })} />
              {t('review.notPlay')}
            </label>
            <label className={cn('flex items-center gap-2', winner === null && 'text-muted-foreground')} title={t('review.reportWrongCallHelp')}>
              <input type="checkbox" checked={calledWrong(here)} disabled={winner === null} onChange={(e) => markWrongCall(here, e.target.checked)} />
              {t('review.reportWrongCall')}
            </label>
            <label className={cn('flex items-center gap-2', !canJoin && 'text-muted-foreground')}>
              <input type="checkbox" checked={fix.join === true} disabled={!canJoin} onChange={(e) => editRally(here, { join: e.target.checked ? true : undefined })} />
              {t('review.reportJoin', { n: here + 2 })}
            </label>
            {splits.includes(rally.key) && (
              <Button variant="ghost" size="sm" onClick={() => unsplit(here)}>
                <Undo2 aria-hidden />
                {t('review.reportStartUndo')}
              </Button>
            )}
          </div>
          {/* Typing stops the video: it would carry on to another rally's note. */}
          <RallyComment key={rally.key} text={comments[rally.key] ?? ''} onFocus={() => onPause(timeOf())} onSave={(text) => onComment(rally.key, text)} />
        </div>
      )}
    </>
  );
}
