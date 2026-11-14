import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { Check, CircleCheck, CircleOff, CircleStop, Flag, Hand, MessageSquareText, PenLine, Play, Plus, RotateCcw, SquarePlus, Star, Trash2, TriangleAlert, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useRunning } from '@/hooks/useRunning';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { contacts, GROUPS, groupName, hasTeams, match, rallies, teamColor, teamRing, type Contact, type Group } from '@/lib/match';
import { railAt, shiftOf, topOf } from '@/components/Review/helpers/timeline';
import { type Named, type Question, type ReportChanges, type Timeout, type TimeoutChange } from '@/lib/review';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import { RallyComment } from '@/components/Review/RallyComment';
import { ReportRow } from '@/components/Review/ReportRow';
import { TimeoutRow } from '@/components/Review/TimeoutRow';
import type { NameOf } from '@/components/Review/helpers/players';
import {
  aboutEnd,
  joinEnd,
  joinStart,
  liveReports,
  changedSince,
  comingFirstTouch,
  freeFrame,
  LEAD_S,
  NEXT_TOUCH_S,
  nextTouch,
  offGiven,
  pieceOf,
  rallyAt,
  rallyOf,
  runningScores,
  type Span,
  splitAfter,
  timeoutsAfter,
  withAdded,
  withSplits,
} from '@/components/Review/helpers/report';
import { problems, warningTimes, type Problem } from '@/components/Review/helpers/checks';
import { labelled } from '@/helpers/contacts';
import { Tip } from '@/components/Tip';
import { ask } from '@/components/ask';
import { SLOW_BEFORE_S } from '@/helpers/slow';

const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig', 'fault'] as const;
const RESULTS = ['play', 'point', 'error'] as const;
const SELECT = 'h-8 min-w-0 flex-1 rounded-md border bg-background px-1.5 text-sm disabled:opacity-50';
/** After the user scrolls the list, it stops following the video this long. */
const HOLD_MS = 3000;
/** A touch's row lights up, and the video's caption names it, as the video slows down at it. */
const TOUCH_LEAD_S = SLOW_BEFORE_S;
/** The list shows this many rallies before and after the one the video is in. */
const AROUND_RALLIES = 2;
/** A rally started this close to a serve already has its serve. */
const SERVE_NEAR_S = 1;
/** Played to a rally's end, the video stops there again only once moved back this far. */
const REPLAY_BACK_S = 0.5;

/** The touch named over the video: `setPlayer` changes its player. */
export type Caption = { team: Group; text: string; key: string; player: string; setPlayer?: (player: string) => void };

/** `cause`: the frame of the teammate's touch a fault is put on, 0 for nobody else. */
type Fix = { player?: string; type?: string; result?: string; cause?: number };
/** `join`: the rally and the next one are one, ending at the next one's end. `redo`: to replay,
 * nobody gets the point; false takes back what the page shows. `wrong`: the referee gave the
 * point to the wrong team, `winner` being the one that got it; false likewise. */
type RallyFix = { winner?: Group; play?: false; end?: number; join?: true; redo?: boolean; wrong?: boolean };
/** The team of a player given as "TEAM:IDENTITY". */
const teamOf = (player: string) => Number(player.split(':')[0]) as Group;
const frameOf = (time: number) => Math.round(time * match.fps);
/** A touch added: its team the picked player's, else the touch before's. */
type Added = { frame: number; time: number; team: Group; type: string; result: string; player?: string; cause?: number };
/** A touch as listed: one of the page's, or one added. */
type Row = { frame: number; time: number; rally: number; team: Group; type: string; result: string; player: string; cause: number; removed: boolean; added: boolean; contact?: Contact };

/** The page's touches a player makes, with that player as "TEAM:IDENTITY". */
const touches = contacts
  .filter((c) => (TYPES as readonly string[]).includes(c.type) && c.team !== null)
  .map((c) => {
    const p = c.person === null ? undefined : match.people[c.person];
    return { contact: c, frame: c.f ?? frameOf(c.t), player: p && p.number !== null ? `${p.team}:${p.number}` : '' };
  });

// How often the list checks on the rail's end, and how near its edges that end may come, in pixels.
const RAIL_FOLLOW_PX = 24;
const RAIL_EDGE_PX = 64;

/** The match's touches beside its video: those of the rallies around where the video stands, the
 * one it plays centred, to correct (player of either team, action, result), remove or add at the
 * video's moment, or start a rally there (one missed, or the second of two taken for one), or delete a
 * rally; under it the winner or to replay, end and joining with the next one of the rally it is in (or just ended). It starts from the corrections saved and not applied yet (`saved`), marked as
 * such; saving sends them all, with the new ones. */
export function ReportEditor({
  reports,
  players,
  nameOf,
  now,
  timeOf,
  isPlaying,
  onPlay,
  onPause,
  onSave,
  onSaveUnchecked,
  green,
  checked,
  onUncheck,
  onCaption,
  questions,
  onHandled,
  onWarnings,
  onUnsaved,
  onTouches,
  onRallies,
  saved,
  comments,
  onComment,
  picks,
  onPick,
  timeouts,
  onTimeout,
  place,
}: {
  /** The moments viewers reported: their touches are flagged. */
  reports: { time: number }[];
  players: Named[];
  nameOf: NameOf;
  /** Where the video stands: its touch's row is highlighted and kept in view. */
  now: number;
  /** Where the video stands, to the frame. */
  timeOf: () => number;
  /** Whether the video plays: played to the end of a rally not checked, it stops there. */
  isPlaying: () => boolean;
  /** Plays the video from a moment. */
  onPlay: (time: number) => void;
  /** Stops the video at a moment. */
  onPause: (time: number) => void;
  /** Saves the corrections, a rally (by its key) checked with them; `onward`: the video goes to the next rally. */
  onSave: (changes: ReportChanges, rally: number, onward: boolean) => Promise<void>;
  /** Saves the corrections, a rally (by its key) no longer checked. */
  onSaveUnchecked: (changes: ReportChanges, rally: number) => Promise<void>;
  /** The rallies checked with no report open nor corrections not saved since, by their key: shown green. */
  green: Set<number>;
  /** The rallies checked, by their key, a report open on them or not. */
  checked: Set<number>;
  onUncheck: (rally: number) => Promise<void>;
  /** The report questions left: each a rally's reports, listed under it. */
  questions: Question[];
  /** Marks a rally's reports handled, the corrections as they stand saved with them. */
  onHandled: (question: Question, changes: ReportChanges) => void;
  /** The warnings as they stand: their moments, the rallies they make orange and the rallies joined, by their key. */
  onWarnings?: (found: { times: number[]; warned: number[]; joined: number[] }) => void;
  /** The rallies with corrections not saved yet, by their key. */
  onUnsaved?: (keys: number[]) => void;
  /** The moments of the ball's touches as they stand with the corrections, sorted. */
  onTouches?: (times: number[]) => void;
  /** The rallies as they stand with the corrections, those deleted left out, those joined as one. */
  onRallies?: (rallies: Span[]) => void;
  /** The touch the video is on in its rally, as it stands with the corrections: to show over the video. */
  onCaption?: (caption: Caption | null) => void;
  saved: Partial<ReportChanges>;
  /** The owner's notes on the rallies, by their key. */
  comments: Record<number, string>;
  onComment: (rally: number, text: string) => Promise<boolean>;
  /** The touches in the films, by their frame. */
  picks: Set<number>;
  onPick: (frame: number, picked: boolean) => void;
  timeouts: Timeout[];
  onTimeout: (change: TimeoutChange) => void;
  /** Where the list stands and when the user last scrolled it: a save starts the editor again. */
  place: RefObject<{ top: number; scrolled: number }>;
}) {
  const { t } = useTranslation();
  const [fixes, setFixes] = useState<Record<number, Fix>>(() => Object.fromEntries((saved.touches ?? []).map(({ frame, ...fix }) => [frame, fix])));
  const [added, setAdded] = useState<Added[]>(() => (saved.added ?? []).map((a) => ({ ...a, time: a.frame / match.fps })));
  // The rallies started by the review, by their start frame.
  const [splits, setSplits] = useState<number[]>(() => saved.splits ?? []);
  // By the rally's key: a rally started before one keeps its index from moving its fixes.
  const [rallyFixes, setRallyFixes] = useState<Record<number, RallyFix>>(() =>
    Object.fromEntries((saved.rallies ?? []).map(({ start, end, ...fix }) => [start, { ...fix, ...(end !== undefined ? { end: end / match.fps } : {}) }])),
  );
  // The touches and rallies the saved corrections change.
  const savedFrames = new Set([...(saved.touches ?? []), ...(saved.added ?? [])].map((x) => x.frame));
  const savedStarts = new Set([...(saved.rallies ?? []).map((r) => r.start), ...(saved.splits ?? [])]);

  // The rallies as they will be: those the review started, each starting at a serve added before it.
  const split = withSplits(rallies, splits, match.fps);
  const shown = withAdded(split, added);
  /** What the answers name a rally by. */
  const keyOf = (k: number) => shown[k].key;
  const fixOf = (k: number): RallyFix | undefined => (shown[k] ? rallyFixes[shown[k].key] : undefined);
  const joins = (k: number) => !!fixOf(k)?.join && k + 1 < shown.length;
  const toReplay = (k: number) => fixOf(k)?.redo ?? shown[k]?.redo ?? false;
  const calledWrong = (k: number) => fixOf(k)?.wrong ?? shown[k]?.wrongCall ?? false;

  // A change back to the touch's own value is no change.
  const edit = (row: Row, change: Fix) =>
    setFixes((all) => {
      const c = row.contact!;
      const next: Fix = { ...all[row.frame], ...change };
      const own: Fix = { player: touches.find((x) => x.frame === row.frame)?.player || undefined, type: c.type, result: labelled(c), cause: c.cause ?? 0 };
      for (const k of ['player', 'type', 'result', 'cause'] as const) {
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
      if (!(next.wrong ?? shown[k].wrongCall) && next.winner === (next.join ? shown[joinEnd(k + 1, joins)]?.winner : shown[k].winner)) {
        delete next.winner;
      }
      if (next.redo === !!shown[k].redo) {
        delete next.redo;
      }
      if (next.wrong === !!shown[k].wrongCall) {
        delete next.wrong;
      }
      for (const key of ['winner', 'play', 'end', 'join', 'redo', 'wrong'] as const) {
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
  // A player the list cannot offer is no one: the field and the video's caption show the same.
  const offered = new Set(players.map((p) => `${p.team}:${p.identity}`));
  const listed = (player: string) => (offered.has(player) ? player : '');
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
        result: fix.result ?? labelled(c),
        player: fix.player === 'none' ? '' : listed(fix.player ?? player),
        cause: fix.cause ?? c.cause ?? 0,
        removed: fix.player === 'none',
        added: false,
        contact: c,
      };
    }),
    ...added.map((a) => ({ ...a, rally: rallyOf(shown, a.time, a.type), player: listed(a.player ?? ''), cause: a.cause ?? 0, removed: false, added: true })),
  ].sort((a, b) => a.time - b.time);
  const rows = allRows.filter((row) => row.rally >= first && row.rally <= last);
  // The touches kept, by rally.
  const kept = new Map<number, Row[]>();
  for (const row of allRows) {
    if (!row.removed) {
      kept.set(row.rally, [...(kept.get(row.rally) ?? []), row]);
    }
  }
  /** A rally's touches kept, those of the rallies joined after it too. */
  const mineOf = (k: number): Row[] => [...(kept.get(k) ?? []), ...(joins(k) ? mineOf(k + 1) : [])];

  const changes: ReportChanges = {
    touches: Object.entries(fixes).map(([frame, c]) => ({ frame: Number(frame), ...c })),
    ...(added.length ? { added: added.map(({ frame, team, type, result, player, cause }) => ({ frame, team, type, result, ...(player ? { player } : {}), ...(cause ? { cause } : {}) })) } : {}),
    ...(Object.keys(rallyFixes).length ? { rallies: Object.entries(rallyFixes).map(([key, f]) => ({ start: Number(key), ...f, ...(f.end !== undefined ? { end: frameOf(f.end) } : {}) })) } : {}),
    ...(splits.length ? { splits } : {}),
  };
  // The rallies with corrections not saved yet: one checked has to be saved again.
  const since = changedSince(changes, saved);
  const unsaved = new Set([...since.starts, ...since.frames.map((frame) => shown[allRows.find((row) => row.frame === frame)?.rally ?? rallyAt(shown, frame / match.fps)]?.key)]);
  const unsavedKeys = [...unsaved].filter((k) => k !== undefined);
  const unsavedJson = JSON.stringify(unsavedKeys);
  useEffect(() => {
    onUnsaved?.(unsavedKeys);
  }, [unsavedJson]);
  const touchesJson = JSON.stringify(allRows.filter((row) => !row.removed && row.type !== 'fault').map((row) => row.time));
  useEffect(() => {
    onTouches?.(JSON.parse(touchesJson));
  }, [touchesJson]);

  // The touch the video is on: the last one started, highlighted until 3 s after it; a removed one
  // gives way to the touch still there.
  const started = rows.filter((row) => !row.removed && row.time - TOUCH_LEAD_S <= now).at(-1);
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
    const guess = nextTouch(follows ? before : undefined, (before && winnerOf(before.rally)) ?? before?.team ?? GROUPS[0], before ? time - before.time : Infinity);
    setAdded((all) => [...all, { frame, time, ...guess, result: 'play' }]);
    setFresh({ key: `t${frame}` });
    onPause(time);
  };
  // A rally started where one already starts is that one. A new one comes with its serve (unless one is there), by
  // the last rally's winner, its player field ready to type in.
  const startHere = () => {
    const frame = freeFrame([...contacts.map((c) => c.f ?? frameOf(c.t)), ...added.map((a) => a.frame)], frameOf(timeOf()));
    const time = frame / match.fps;
    if (!shown.some((r) => r.key === frame || frameOf(r.start) === frame)) {
      setSplits((all) => [...all, frame]);
      if (!allRows.some((row) => !row.removed && row.type === 'serve' && Math.abs(row.time - time) < SERVE_NEAR_S)) {
        setAdded((all) => [...all, { frame, time, type: 'serve', team: serverAt(time), result: 'play' }]);
        setFresh({ key: `t${frame}` });
      }
    }
    onPause(time);
  };
  // Who serves a rally started at `time`: the winner of the one before, else of the touches before it in the rally it
  // splits, as their last result says.
  const serverAt = (time: number): Group => {
    const k = shown.findLastIndex((r) => r.start < time);
    if (k < 0) {
      return GROUPS[0];
    }
    const last = (kept.get(k) ?? []).filter((row) => row.time < time && row.type !== 'fault').at(-1);
    const said = time > shown[k].end ? null : last?.result === 'point' ? last.team : last?.result === 'error' ? ((3 - last.team) as Group) : null;
    return said ?? winnerOf(joinStart(k, joins)) ?? GROUPS[0];
  };

  // The rally's touches after its new end go to a new rally, started at the first of them.
  const endHere = () => {
    const at = Math.round(timeOf() * 100) / 100;
    editRally(here, { end: at });
    const frame = splitAfter(
      (kept.get(here) ?? []).map((row) => row.time),
      at,
      match.fps,
    );
    if (frame !== undefined && !shown.some((r) => r.key === frame)) {
      setSplits((all) => [...all, frame]);
    }
  };

  // The list follows the video, its touch (else its rally) centred, except while a field in it is
  // being filled or shortly after the user scrolled it.
  const list = useRef<HTMLOListElement>(null);
  const [editing, setEditing] = useState(false);
  useLayoutEffect(() => {
    if (list.current) {
      list.current.scrollTop = place.current.top;
    }
  }, []);
  const inHere = started && started.rally === here ? started : undefined;
  const who = (player: string) => {
    const [team, n] = player.split(':').map(Number);
    return player ? (nameOf(team as Group, n) ?? t('player', { n })) : t('players.rest');
  };
  const coming = comingFirstTouch(
    allRows.filter((row) => !row.removed),
    shown,
    now,
    TOUCH_LEAD_S,
  );
  const named = coming && !joins(coming.rally - 1) ? coming : inHere;
  const caption = named && (named.removed ? `${t(`types.${named.type}`)} · ${t('review.reportRemoved')}` : `${t(`actions.${named.type}.${named.result}`)} · ${who(named.player)}`);
  useEffect(() => {
    onCaption?.(
      named && caption
        ? {
            team: named.team,
            text: caption,
            key: `t${named.frame}`,
            player: named.player,
            setPlayer: named.removed ? undefined : (who) => (named.added ? editAdded(named.frame, { player: who, team: teamOf(who) }) : edit(named, { player: who })),
          }
        : null,
    );
  }, [caption, named?.team, named?.frame, named?.player]);
  useEffect(() => () => onCaption?.(null), []);
  const isCurrent = (o: Timeout) => o.start / match.fps <= now && now < o.end / match.fps;
  const inTimeout = timeouts.find(isCurrent);
  // A serve can light up just before its rally starts: the list goes straight to it.
  const followed = started && started.rally >= here ? started : undefined;
  const current = inTimeout ? `o${inTimeout.start}` : followed ? `t${followed.frame}` : `r${here}`;
  const centre = (key: string) => {
    const box = list.current;
    const item = box?.querySelector<HTMLElement>(`[data-key="${key}"]`);
    box?.scrollTo({ top: item ? topOf(item) - (box.clientHeight - item.offsetHeight) / 2 : 0, behavior: 'smooth' });
    return item;
  };
  useEffect(() => {
    if (!editing && Date.now() - place.current.scrolled > HOLD_MS) {
      centre(current);
    }
    // `first`: keeping the rows in place when the rallies around change stops the scroll under way.
  }, [current, editing, first]);
  // The rail along the list: how far the time has come, between rallies too, where no row is lit.
  const [rail, setRail] = useState({ at: 0, height: 0 });
  const placed = useRef({ first, tops: new Map<string, number>() });
  useLayoutEffect(() => {
    const box = list.current;
    const rows = [...(box?.querySelectorAll<HTMLElement>('[data-at]') ?? [])].map((e) => ({ key: e.dataset.key, at: Number(e.dataset.at), top: topOf(e), bottom: topOf(e) + e.offsetHeight }));
    // Rallies leaving the list or joining it must not move the rows still there on screen.
    const tops = new Map(rows.flatMap((r) => (r.key ? [[r.key, r.top] as const] : [])));
    if (box && placed.current.first !== first) {
      box.scrollTop += shiftOf(placed.current.tops, tops);
    }
    placed.current = { first, tops };
    const at = railAt(rows, now);
    const height = rows.at(-1)?.bottom ?? 0;
    setRail((r) => (Math.abs(r.at - at) < 1 && r.height === height ? r : { at, height }));
  });
  // Between rallies, no row is centred: the list follows the rail's end when it nears an edge.
  const railStep = Math.round(rail.at / RAIL_FOLLOW_PX);
  useEffect(() => {
    const box = list.current;
    // No height yet: the rail is not measured.
    if (box && rail.height && !editing && Date.now() - place.current.scrolled > HOLD_MS && (rail.at < box.scrollTop + RAIL_EDGE_PX || rail.at > box.scrollTop + box.clientHeight - RAIL_EDGE_PX)) {
      box.scrollTo({ top: rail.at - box.clientHeight / 2, behavior: 'smooth' });
    }
  }, [railStep]);
  // A touch just added: in view, its player field ready to type in.
  const [fresh, setFresh] = useState<{ key: string }>();
  useEffect(() => {
    if (fresh !== undefined) {
      centre(fresh.key)?.querySelector('input')?.focus({ preventScroll: true });
    }
  }, [fresh]);

  const rally = shown[here];
  const fix = fixOf(here) ?? {};
  const end = fix.end ?? rally?.end;
  const endOf = (k: number) => clock(fixOf(k)?.end ?? shown[k].end);
  const rallyLabel = (k: number) =>
    (joins(k)
      ? t('review.reportRallyJoined', { n: k + 1, m: k + 2, from: clock(shown[k].start), to: endOf(joinEnd(k, joins)) })
      : t(joins(k - 1) ? 'review.reportRallyJoinedTo' : 'review.reportRally', { n: k + 1, m: k, from: clock(shown[k].start), to: endOf(k) })) +
    (splits.includes(shown[k].key) ? ` · ${t('review.reportRallyNew')}` : '') +
    (toReplay(k) ? ` · ${t('review.reportRedo')}` : '') +
    (calledWrong(k) ? ` · ${t('review.reportWrongCall')}` : '');
  // Joined only to the next rally of its set.
  const canJoin = shown[here + 1]?.set === rally?.set;

  // What looks wrong in each rally shown, as it stands with the corrections: a rally joined to the
  // next one is checked with its touches, one said no play not at all.
  // A rally's winner: the one set, else the one its last touch's result says, else the page's.
  const lastOf = (k: number) => mineOf(k).at(-1);
  const winnerOf = (k: number): Group | null => {
    if (toReplay(k)) {
      return null;
    }
    if (calledWrong(k)) {
      return fixOf(k)?.winner ?? shown[joinEnd(k, joins)]?.winner ?? null;
    }
    // As on the page: the last touch says it, a point for its team or a fault for the other's; one
    // in play, or none, leaves the winner given.
    const last = lastOf(k);
    const said = last?.result === 'point' ? last.team : last?.result === 'error' ? ((3 - last.team) as Group) : undefined;
    return said ?? fixOf(k)?.winner ?? shown[joinEnd(k, joins)]?.winner ?? null;
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
  // How the rally ends is said on the first of those joined.
  const whole = joinStart(here, joins);
  const winner = rally ? winnerOf(whole) : null;
  const isEmpty = (k: number) => !mineOf(k).length && !joins(k) && !joins(k - 1);
  const isDeleted = (k: number) => fixOf(k)?.play === false;
  // Joined, rallies are deleted once taken apart.
  const deletable = (k: number) => !joins(k) && !joins(k - 1);
  // A touchless rally whose end was said explains a point: it is validated, not deleted at once.
  const canDelete = (k: number) => isEmpty(k) && fixOf(k)?.play !== false && fixOf(k)?.winner === undefined && !toReplay(k) && !calledWrong(k);
  const otherRallies = (key: number) => (changes.rallies ?? []).filter((r) => r.start !== key);
  // The rally whose change is being saved: its button shows a loader, the others wait.
  const [saving, run] = useRunning();
  const busyOn = (k: number) => saving === String(keyOf(k));
  // A rally the review started goes away; one of the page's is said no play.
  const deleteRally = (k: number) => {
    const key = keyOf(k);
    if (splits.includes(key)) {
      return onSaveUnchecked({ ...changes, splits: splits.filter((f) => f !== key), rallies: otherRallies(key) }, key);
    }
    return onSave({ ...changes, rallies: [...otherRallies(key), { ...changes.rallies?.find((r) => r.start === key), start: key, play: false }] }, key, k === here);
  };
  const restoreRally = (k: number) => {
    const key = keyOf(k);
    const { play: _, ...rest } = changes.rallies?.find((r) => r.start === key) ?? { start: key };
    return onSaveUnchecked({ ...changes, rallies: [...otherRallies(key), ...(Object.keys(rest).length > 1 ? [rest] : [])] }, key);
  };
  // `validated`: as it would stand checked.
  const problemsAt = (k: number, validated: boolean) => {
    // After the referee's error the serve may follow what really happened or the point given: no check.
    const before = joinStart(k - 1, joins);
    const previous = k > 0 && shown[k - 1].set === shown[k].set && fixOf(before)?.play !== false && !calledWrong(before) ? winnerOf(before) : null;
    return problems(mineOf(k), winnerOf(k), previous, hasTeams && !toReplay(k), validated);
  };
  const found = new Map<number, ReturnType<typeof problems>>();
  for (let k = 0; k < shown.length; k++) {
    if (fixOf(k)?.play === false || joins(k - 1)) {
      continue;
    }
    found.set(k, problemsAt(k, checked.has(keyOf(k)) && !unsaved.has(keyOf(k))));
  }
  const problemsOf = (row: Row): Problem[] => {
    const k = joinStart(row.rally, joins);
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
  const scores = hasTeams ? runningScores(shown.map((r, k) => ({ set: r.set, winner: winnerOf(k), skip: fixOf(k)?.play === false || joins(k - 1) }))) : [];
  const off = offGiven(
    shown.map((r) => r.set),
    scores,
    match.scores,
  );
  // A warning outweighs the check: the rally needs another look.
  const warnedAt = (k: number) => rallyProblems(k).length > 0 || off.has(k);
  const warningsAt = shown.map((r, k) => warningTimes(found.get(k), mineOf(k), r.start, shown[joinEnd(k, joins)].end, off.has(k)));
  const joinedKeys = shown.flatMap((r, k) => (joins(k) || joins(k - 1) ? [r.key] : []));
  const warningsJson = JSON.stringify({
    times: warningsAt.flat(),
    warned: shown.flatMap((r, k) => (warningsAt[joinStart(k, joins)].length ? [r.key] : [])),
    joined: joinedKeys,
  });
  useEffect(() => {
    onWarnings?.(JSON.parse(warningsJson));
  }, [warningsJson]);
  // What still warns once a rally is checked (a doubt no longer does): asked about before checking it.
  const endOfRally = (k: number) => fixOf(k)?.end ?? shown[k].end;
  const validate = async (k: number) => {
    const w = joinStart(k, joins);
    const f = problemsAt(w, true);
    const left = [...new Set([...f.rally, ...[...f.touch.values()].flat()])];
    const text = [...left.map((p) => t(`feedback.kinds.auto.${p}`)), ...(off.has(w) ? [t('feedback.kinds.auto.scoreOff')] : [])].join(' · ');
    if (text && !(await ask({ title: t('review.validateWarned', { n: k + 1 }), text, confirm: t('review.validateAnyway') }))) {
      return;
    }
    await run(String(keyOf(k)), () => onSave(changes, keyOf(k), k === here));
  };
  const spans: Span[] = shown.flatMap((r, k) =>
    joins(k - 1) || fixOf(k)?.play === false
      ? []
      : [{ key: r.key, n: k + 1, start: r.start, end: endOfRally(joinEnd(k, joins)), set: r.set, winner: winnerOf(k), redo: toReplay(k), wrongCall: calledWrong(k) }],
  );
  const spansJson = JSON.stringify(spans);
  useEffect(() => {
    onRallies?.(JSON.parse(spansJson));
  }, [spansJson]);
  // Played to the end of a rally not checked, the video stops there: time to check it. Once, until moved back.
  const lastNow = useRef(now);
  const stoppedAt = useRef<number | null>(null);
  useEffect(() => {
    const from = lastNow.current;
    lastNow.current = now;
    if (now < from - REPLAY_BACK_S) {
      stoppedAt.current = null;
    }
    if (now <= from || now - from > 1 || !isPlaying()) {
      return;
    }
    const k = shown.findIndex((_, k) => !joins(k) && fixOf(k)?.play !== false && from < endOfRally(k) && endOfRally(k) <= now);
    const key = k < 0 ? undefined : keyOf(joinStart(k, joins));
    if (key !== undefined && stoppedAt.current !== key && !(checked.has(key) && !unsaved.has(key))) {
      stoppedAt.current = key;
      onPause(timeOf());
    }
  }, [now]);
  const openQuestions = liveReports(questions, new Set(joinedKeys));

  // The reports under their rally's header; those in no rally between the rallies, as the timeouts.
  const reportRows = (list: Question[]) => list.map((q) => <ReportRow key={`q${q.id}`} question={q} onPlay={onPlay} onHandled={() => onHandled(q, changes)} />);
  const rallyOfReport = (q: Question) => shown.findIndex((r) => r.key === q.rally);
  // What is wrong with a rally as a whole: no touch above its touches, no winner below them.
  const rallyWarning = (k: number, place: 'start' | 'end') => {
    // Rallies joined end with the last of them.
    const list = place === 'end' && joins(k) ? [] : (found.get(place === 'end' ? joinStart(k, joins) : k)?.rally ?? []).filter((p) => (p === 'noWinner') === (place === 'end'));
    return list.length
      ? [
          <li key={`p${k}${place}`} className="flex items-center gap-1.5 px-2 text-xs text-amber-800 dark:text-amber-300">
            <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
            {describe(list)}
          </li>,
        ]
      : [];
  };
  const reportsIn = (k: number) => reportRows(openQuestions.filter((q) => rallyOfReport(q) === k && !aboutEnd(q)));
  const reportsAtEnd = (k: number) => reportRows(openQuestions.filter((q) => rallyOfReport(q) === k && aboutEnd(q)));
  const reportsAfter = (k: number) => reportRows(openQuestions.filter((q) => rallyOfReport(q) < 0 && shown.findLastIndex((r) => r.start <= (q.reports?.[0]?.time ?? q.clip.start)) === k));
  const timeoutRows = (k: number) =>
    timeoutsAfter(shown, timeouts, k, match.fps).map((o) => <TimeoutRow key={`o${o.start}`} timeout={o} current={isCurrent(o)} now={now} onPlay={onPlay} onChange={onTimeout} />);

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
            <Tip label={t('review.reportStartHelp')}>
              <Button variant="outline" className="flex-1 bg-card" onClick={startHere}>
                <SquarePlus aria-hidden />
                {t('review.reportStart', { time: clock(now) })}
              </Button>
            </Tip>
            <Button variant="outline" className="flex-1 bg-card" disabled={!!inTimeout} onClick={() => onTimeout({ frame: frameOf(timeOf()) })}>
              <Hand aria-hidden />
              {t('review.timeoutAdd', { time: clock(now) })}
            </Button>
          </div>
          <ol
            ref={list}
            aria-label={t('review.reportTouches')}
            className="relative grid min-h-0 flex-1 auto-rows-max grid-cols-[minmax(0,1fr)] gap-1.5 overflow-y-auto overscroll-contain pr-1 pl-4"
            onScroll={(e) => (place.current.top = e.currentTarget.scrollTop)}
            onWheel={() => (place.current.scrolled = Date.now())}
            onTouchMove={() => (place.current.scrolled = Date.now())}
            // A press, or leaving a field, must not scroll the list: the button pressed would move from under the pointer.
            onPointerDown={() => (place.current.scrolled = Date.now())}
            onFocus={(event) => setEditing(event.target.matches('input, select'))}
            onBlur={() => {
              place.current.scrolled = Date.now();
              setEditing(false);
            }}
          >
            <li aria-hidden className="pointer-events-none absolute top-0 left-1 w-0.5 rounded-full bg-border" style={{ height: rail.height }}>
              <div className="w-full rounded-full bg-primary" style={{ height: rail.at }} />
            </li>
            {first === 0 && [...reportsAfter(-1), ...timeoutRows(-1)]}
            {Array.from({ length: last - first + 1 }, (_, n) => first + n).flatMap((k) => [
              // The rally's whole surface: orange with a warning, else green once checked.
              <li key={`g${k}`} className={cn('rounded-lg', warnedAt(k) ? 'bg-amber-50 dark:bg-amber-950/40' : green.has(keyOf(k)) && 'bg-emerald-50 dark:bg-emerald-950/40')}>
                <ol className="grid grid-cols-[minmax(0,1fr)] gap-1.5 p-1">
                  {[
                    <li
                      key={`r${k}`}
                      data-key={`r${k}`}
                      data-at={Math.max(shown[k].start - LEAD_S, shown[k - 1]?.end ?? 0)}
                      className={cn('sticky top-0 z-10 rounded-md bg-card', k === here && 'text-primary')}
                    >
                      <div
                        className={cn(
                          'flex items-center overflow-hidden rounded-md border bg-muted',
                          warnedAt(k)
                            ? 'border-amber-300 bg-amber-100 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200'
                            : green.has(keyOf(k)) && 'border-emerald-300 bg-emerald-100 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
                          k === here && 'border-primary',
                        )}
                      >
                        <Tip label={t('review.reportRallyPlay')}>
                          <button
                            type="button"
                            onClick={() => onPlay(shown[k].start)}
                            className={cn(
                              'flex min-w-0 flex-1 items-center gap-1.5 px-2 py-1 text-left text-sm font-medium outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset',
                              warnedAt(k) && 'hover:bg-amber-200 dark:hover:bg-amber-900',
                              fixOf(k)?.play === false && 'line-through',
                            )}
                          >
                            <Play aria-hidden className="size-3.5 shrink-0 fill-current" />
                            <span className="truncate">{rallyLabel(k)}</span>
                            {green.has(keyOf(k)) && <CircleCheck aria-label={t('review.rallyChecked')} className="size-3.5 shrink-0 text-emerald-700 dark:text-emerald-400" />}
                            {rallyProblems(k).length > 0 && (
                              <Tip label={describe([...new Set(rallyProblems(k))])}>
                                <span role="img" aria-label={describe([...new Set(rallyProblems(k))])} className="shrink-0">
                                  <TriangleAlert aria-hidden className="size-3.5 text-amber-600 dark:text-amber-400" />
                                </span>
                              </Tip>
                            )}
                            {comments[keyOf(k)] && (
                              <Tip label={comments[keyOf(k)]}>
                                <span role="img" aria-label={comments[keyOf(k)]} className="shrink-0">
                                  <MessageSquareText aria-hidden className="size-3.5 text-sky-600 dark:text-sky-400" />
                                </span>
                              </Tip>
                            )}
                            {savedStarts.has(keyOf(k)) && (
                              <Tip label={t('review.reportSaved')}>
                                <span role="img" aria-label={t('review.reportSaved')} className="ml-auto shrink-0">
                                  <PenLine aria-hidden className="size-3.5" />
                                </span>
                              </Tip>
                            )}
                          </button>
                        </Tip>
                        {isDeleted(k) ? (
                          <Tip label={t('review.restoreRally', { n: k + 1 })}>
                            <Button
                              variant="outline"
                              size="xs"
                              className="mr-1 shrink-0 bg-card text-foreground"
                              aria-label={t('review.restoreRally', { n: k + 1 })}
                              busy={busyOn(k)}
                              disabled={saving !== null}
                              onClick={() => void run(String(keyOf(k)), () => restoreRally(k))}
                            >
                              <Undo2 aria-hidden />
                              {t('review.restore')}
                            </Button>
                          </Tip>
                        ) : (
                          <>
                            {!canDelete(k) && deletable(k) && (
                              <Tip label={t('review.deleteRally', { n: k + 1 })}>
                                <Button
                                  variant="ghost"
                                  size="icon-xs"
                                  className="mr-1 shrink-0 text-foreground"
                                  aria-label={t('review.deleteRally', { n: k + 1 })}
                                  busy={busyOn(k)}
                                  disabled={saving !== null}
                                  onClick={() => void run(String(keyOf(k)), () => deleteRally(k))}
                                >
                                  <Trash2 aria-hidden />
                                </Button>
                              </Tip>
                            )}
                            {checked.has(keyOf(k)) && !unsaved.has(keyOf(k)) ? (
                              <Tip label={t('review.uncheckRally', { n: k + 1 })}>
                                <Button
                                  variant="outline"
                                  size="xs"
                                  className="mr-1 shrink-0 bg-card text-foreground"
                                  aria-label={t('review.uncheckRally', { n: k + 1 })}
                                  busy={busyOn(k)}
                                  disabled={saving !== null}
                                  onClick={() => void run(String(keyOf(k)), () => onUncheck(keyOf(k)))}
                                >
                                  <CircleOff aria-hidden />
                                  {t('review.uncheck')}
                                </Button>
                              </Tip>
                            ) : canDelete(k) ? (
                              <Tip label={t('review.deleteRally', { n: k + 1 })}>
                                <Button
                                  variant="outline"
                                  size="xs"
                                  className="mr-1 shrink-0 bg-card text-foreground"
                                  aria-label={t('review.deleteRally', { n: k + 1 })}
                                  busy={busyOn(k)}
                                  disabled={saving !== null}
                                  onClick={() => void run(String(keyOf(k)), () => deleteRally(k))}
                                >
                                  <Trash2 aria-hidden />
                                  {t('review.delete')}
                                </Button>
                              </Tip>
                            ) : (
                              <Tip label={t('review.validateRally', { n: k + 1 })}>
                                <Button
                                  variant="outline"
                                  size="xs"
                                  className="mr-1 shrink-0 bg-card text-foreground"
                                  aria-label={t('review.validateRally', { n: k + 1 })}
                                  busy={busyOn(k)}
                                  disabled={saving !== null}
                                  onClick={() => void validate(k)}
                                >
                                  <Check aria-hidden />
                                  {t('review.validate')}
                                </Button>
                              </Tip>
                            )}
                          </>
                        )}
                      </div>
                    </li>,
                    ...rallyWarning(k, 'start'),
                    ...reportsIn(k),
                    ...rows
                      .filter((row) => row.rally === k)
                      .map((row) => {
                        const remove = () => (row.added ? setAdded((all) => all.filter((a) => a.frame !== row.frame)) : edit(row, { player: 'none' }));
                        const change = (said: Fix) => {
                          // A touch no longer a fault is put on nobody.
                          const c: Fix = said.result && said.result !== 'error' ? { ...said, cause: 0 } : said;
                          // A point or a fault said on a touch ends the rally: it is no longer to replay.
                          const owner = joinStart(row.rally, joins);
                          if (c.result && c.result !== 'play' && toReplay(owner)) {
                            editRally(owner, { redo: false });
                          }
                          if (row.added) {
                            editAdded(row.frame, c);
                          } else {
                            edit(row, c);
                          }
                        };
                        // A fault may be put on the team's touch just before it (and on one picked before, kept shown).
                        // A playing fault is always its player's.
                        const earlier =
                          row.removed || row.result !== 'error' || row.type === 'fault'
                            ? []
                            : mineOf(joinStart(row.rally, joins)).filter((r) => r.team === row.team && r.time < row.time && r.type !== 'fault');
                        const last = earlier.reduce<Row | undefined>((a, r) => (!a || r.time > a.time ? r : a), undefined);
                        const causes = earlier.filter((r) => r === last || r.frame === row.cause).sort((a, b) => a.time - b.time);
                        return (
                          <li
                            key={`t${row.frame}`}
                            data-key={`t${row.frame}`}
                            data-at={row.time - TOUCH_LEAD_S}
                            className={cn(
                              'grid grid-cols-[minmax(0,1fr)] gap-1.5 rounded-md border bg-card p-1.5 transition-colors',
                              row.frame === playing && 'border-primary bg-primary/10',
                              row.removed && 'bg-muted/50',
                            )}
                          >
                            <div className="flex items-center gap-1.5">
                              <Tip label={t('review.reportPlay')}>
                                <button
                                  type="button"
                                  aria-label={`${t('review.reportPlay')} ${clock(row.time)}`}
                                  onClick={() => onPlay(row.time)}
                                  className="flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-sm tabular-nums outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50"
                                >
                                  <Play aria-hidden className="size-3.5 fill-current" />
                                  <Swatch color={teamColor(row.team)} ring={teamRing(row.team)} />
                                  {clock(row.time)}
                                  {reported.has(row.frame) && <Flag aria-label={t('review.reportedTouch')} className="size-3.5 text-primary" />}
                                  {savedFrames.has(row.frame) && (
                                    <Tip label={t('review.reportSaved')}>
                                      <span role="img" aria-label={t('review.reportSaved')}>
                                        <PenLine aria-hidden className="size-3.5 text-muted-foreground" />
                                      </span>
                                    </Tip>
                                  )}
                                </button>
                              </Tip>
                              {row.removed ? (
                                <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground line-through">{t(`types.${row.type}`)}</span>
                              ) : (
                                <>
                                  <select
                                    className={SELECT}
                                    aria-label={t('review.reportType')}
                                    value={row.type}
                                    onChange={(e) => change({ type: e.target.value, ...(e.target.value === 'fault' ? { result: 'error', cause: 0 } : {}) })}
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
                              {!row.removed && (
                                <Tip label={t('review.inHighlights')}>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-8 shrink-0"
                                    aria-label={t('review.inHighlights')}
                                    aria-pressed={picks.has(row.frame)}
                                    onClick={() => onPick(row.frame, !picks.has(row.frame))}
                                  >
                                    <Star aria-hidden className={cn(picks.has(row.frame) && 'fill-amber-400 text-amber-500')} />
                                  </Button>
                                </Tip>
                              )}
                              <Tip label={t(row.removed ? 'review.reportRestore' : 'review.reportRemove')}>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="size-8 shrink-0"
                                  aria-label={t(row.removed ? 'review.reportRestore' : 'review.reportRemove')}
                                  onClick={() => (row.removed ? edit(row, { player: undefined }) : remove())}
                                >
                                  {row.removed ? <Undo2 aria-hidden /> : <Trash2 aria-hidden />}
                                </Button>
                              </Tip>
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
                            {causes.length > 0 && (
                              <select
                                className={cn(SELECT, 'w-full flex-none')}
                                aria-label={t('review.cause')}
                                value={causes.some((r) => r.frame === row.cause) ? row.cause : 0}
                                onChange={(e) => change({ cause: Number(e.target.value) })}
                              >
                                <option value={0}>{t('review.causeSelf')}</option>
                                {causes.map((r) => (
                                  <option key={r.frame} value={r.frame}>
                                    {t('review.causeOf', { touch: `${t(`types.${r.type}`)} · ${who(r.player)}` })}
                                  </option>
                                ))}
                              </select>
                            )}
                          </li>
                        );
                      }),
                    // A touch lands at the video's moment: only the rally on the video takes it.
                    <li key={`a${k}`}>
                      <Tip label={t('review.reportAdd', { time: clock(now) })}>
                        <Button variant="outline" size="xs" className="w-full bg-card" disabled={k !== here} aria-label={t('review.reportAdd', { time: clock(now) })} onClick={add}>
                          <Plus aria-hidden />
                        </Button>
                      </Tip>
                    </li>,
                    ...rallyWarning(k, 'end'),
                    ...reportsAtEnd(k),
                  ]}
                </ol>
              </li>,
              // The score once the rally is over, between it and the next one.
              ...(!joins(k) && scores[joinStart(k, joins)]
                ? [
                    <li
                      key={`s${k}`}
                      data-at={shown[k].end}
                      className={cn(
                        'my-1 flex flex-wrap items-center justify-center gap-x-2.5 gap-y-0.5 rounded-md border-2 border-foreground/25 bg-secondary px-3 py-1.5 text-sm shadow-sm',
                        off.has(joinStart(k, joins)) && 'border-amber-500 bg-amber-100 text-amber-900 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-200',
                      )}
                    >
                      <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                        {t(shown[k + 1]?.set === shown[k].set ? 'review.reportScoreAfter' : 'review.reportScoreSet', { n: shown[k].set })}
                      </span>
                      <span className="flex items-center gap-1.5 font-medium tabular-nums">
                        <Swatch color={teamColor(1)} ring={teamRing(1)} />
                        {groupName(t, 1)}
                        <span className="text-lg font-bold">
                          {scores[joinStart(k, joins)]![0]} – {scores[joinStart(k, joins)]![1]}
                        </span>
                        {groupName(t, 2)}
                        <Swatch color={teamColor(2)} ring={teamRing(2)} />
                      </span>
                      {off.has(joinStart(k, joins)) && (
                        <span className="flex items-center gap-1">
                          <TriangleAlert aria-hidden className="size-3.5 shrink-0" />
                          {t('review.reportScoreGiven', { given: off.get(joinStart(k, joins)) })}
                        </span>
                      )}
                    </li>,
                  ]
                : []),
              ...reportsAfter(k),
              ...timeoutRows(k),
            ])}
          </ol>
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
                value={toReplay(whole) ? 'redo' : winner === null ? '' : String(winner)}
                onValueChange={(v) => v && (v === 'redo' ? pickReplay(whole) : pickWinner(whole, Number(v) as Group))}
              >
                {GROUPS.map((g) => (
                  <ToggleGroupItem key={g} value={String(g)} className="h-9 gap-2 px-3 aria-checked:bg-primary aria-checked:text-primary-foreground">
                    <Swatch color={teamColor(g)} ring={teamRing(g)} />
                    {groupName(t, g)}
                  </ToggleGroupItem>
                ))}
                <Tip label={t('review.reportRedoHelp')}>
                  <ToggleGroupItem value="redo" className="h-9 gap-2 px-3 aria-checked:bg-primary aria-checked:text-primary-foreground">
                    <RotateCcw aria-hidden />
                    {t('review.reportRedo')}
                  </ToggleGroupItem>
                </Tip>
              </ToggleGroup>
            </span>
            <Tip label={t('review.reportWrongCallHelp')}>
              <label className={cn('flex items-center gap-2', winner === null && 'text-muted-foreground')}>
                <input type="checkbox" checked={calledWrong(whole)} disabled={winner === null} onChange={(e) => markWrongCall(whole, e.target.checked)} />
                {t('review.reportWrongCall')}
              </label>
            </Tip>
            <label className={cn('flex items-center gap-2', !canJoin && 'text-muted-foreground')}>
              <input type="checkbox" checked={fix.join === true} disabled={!canJoin} onChange={(e) => editRally(here, { join: e.target.checked ? true : undefined })} />
              {t('review.reportJoin', { n: here + 2 })}
            </label>
            <span className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" className="bg-card" disabled={now <= rally.start} onClick={endHere}>
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
            {/* Typing stops the video: it would carry on to another rally's note. */}
            <RallyComment key={rally.key} text={comments[rally.key] ?? ''} onFocus={() => onPause(timeOf())} onSave={(text) => onComment(rally.key, text)} />
          </div>
        </div>
      )}
    </>
  );
}
