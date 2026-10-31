import { useEffect, useRef, useState } from 'react';
import { Check, CircleCheck, Flag, HelpCircle, Play, Plus, Trash2, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { GROUPS, groupName, match, teamColor, teamRing, type Group } from '@/lib/match';
import type { Named, Question, ReportChanges, ReportTouch } from '@/lib/review';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import type { NameOf } from '@/components/Review/helpers/players';

const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig'] as const;
const RESULTS = ['play', 'point', 'error'] as const;
const SELECT = 'h-8 min-w-0 flex-1 rounded-md border bg-background px-1.5 text-sm disabled:opacity-50';
/** A touch can be added from this long before the rally's start: the page counts its touches from there. */
const ADD_BEFORE_S = 0.3;
/** A touch added under this long from one already listed is that one: the list shows it instead. */
const ADD_SAME_S = 0.1;
/** After the user scrolls the list, it stops following the video this long. */
const HOLD_MS = 3000;

type Fix = { player?: string; type?: string; result?: string };
/** The team of a player given as "TEAM:IDENTITY". */
const teamOf = (player: string) => Number(player.split(':')[0]) as Group;
/** A touch added: its team the picked player's, else the touch before's. */
type Added = { frame: number; time: number; team: Group; type: string; result: string; player?: string };
/** A touch as listed: one of the rally's, or one added. */
type Row = { frame: number; time: number; team: Group; type: string; result: string; player: string; removed: boolean; added: boolean };

/** A viewer's report on a rally: the rally's touches beside the video, the one it plays centred,
 * to correct (player of either team, action, result), remove or add at the video's moment; then its winner, or the
 * rally marked as no play. Only what is changed is saved. */
export function ReportEditor({
  question,
  players,
  nameOf,
  now,
  timeOf,
  onPlay,
  onPause,
  onSave,
  onSkip,
}: {
  question: Question;
  players: Named[];
  nameOf: NameOf;
  /** Where the video stands: its touch's row is highlighted and kept in view. */
  now: number;
  /** Where the video stands, to the frame. */
  timeOf: () => number;
  /** Plays the video from a touch. */
  onPlay: (time: number) => void;
  /** Stops the video at a moment. */
  onPause: (time: number) => void;
  onSave: (changes: ReportChanges) => void;
  onSkip: () => void;
}) {
  const { t } = useTranslation();
  const touches = question.touches ?? [];
  const [fixes, setFixes] = useState<Record<number, Fix>>({});
  const [added, setAdded] = useState<Added[]>([]);
  const [winner, setWinner] = useState<Group | null>(question.winner ?? null);
  const [notPlay, setNotPlay] = useState(false);

  // A change back to the touch's own value is no change.
  const edit = (touch: ReportTouch, change: Fix) =>
    setFixes((all) => {
      const next: Fix = { ...all[touch.frame], ...change };
      const own: Fix = { player: touch.player ?? undefined, type: touch.type, result: touch.result ?? 'play' };
      for (const k of ['player', 'type', 'result'] as const) {
        if (next[k] === undefined || next[k] === own[k]) {
          delete next[k];
        }
      }
      const out = { ...all };
      delete out[touch.frame];
      return Object.keys(next).length ? { ...out, [touch.frame]: next } : out;
    });
  const editAdded = (frame: number, change: Partial<Added>) => setAdded((all) => all.map((a) => (a.frame === frame ? { ...a, ...change } : a)));

  const rows: Row[] = [
    ...touches.map((touch) => {
      const fix = fixes[touch.frame] ?? {};
      return {
        frame: touch.frame,
        time: touch.time,
        team: fix.player && fix.player !== 'none' ? teamOf(fix.player) : touch.team,
        type: fix.type ?? touch.type,
        result: fix.result ?? touch.result ?? 'play',
        player: fix.player === 'none' ? '' : (fix.player ?? touch.player ?? ''),
        removed: fix.player === 'none',
        added: false,
      };
    }),
    ...added.map((a) => ({ ...a, player: a.player ?? '', removed: false, added: true })),
  ].sort((a, b) => a.time - b.time);

  const changes: ReportChanges = {
    touches: Object.entries(fixes).map(([frame, c]) => ({ frame: Number(frame), ...c })),
    ...(added.length ? { added: added.map(({ frame, team, type, result, player }) => ({ frame, team, type, result, ...(player ? { player } : {}) })) } : {}),
    ...(winner !== null && winner !== question.winner ? { winner } : {}),
    ...(notPlay ? { play: false as const } : {}),
  };
  const changed = changes.touches.length > 0 || added.length > 0 || changes.winner !== undefined || notPlay;

  // The touch the video is on: the last one started, highlighted until 3 s after it.
  const started = rows.filter((row) => row.time - 0.2 <= now).at(-1);
  const playing = started && now - started.time < 3 ? started.frame : undefined;
  // The touches a viewer reported from (the moment replayed then).
  const reported = new Set(touches.filter((touch) => question.reports?.some((r) => Math.abs(r.time - touch.time) <= 0.6)).map((touch) => touch.frame));
  const canAdd = now >= question.clip.start - ADD_BEFORE_S;
  const add = () => {
    const time = timeOf();
    const frame = Math.round(time * match.fps);
    const there = rows.find((row) => Math.abs(row.time - time) < ADD_SAME_S);
    if (there) {
      setFresh({ frame: there.frame });
      onPause(there.time);
      return;
    }
    // The team of the touch before it, most often the same.
    const before = rows.filter((row) => row.time <= time).at(-1);
    setAdded((all) => [...all, { frame, time, team: before?.team ?? GROUPS[0], type: 'pass', result: 'play' }]);
    setFresh({ frame });
    onPause(time);
  };

  // The list follows the video, its touch centred, except while a field in it is being filled or
  // shortly after the user scrolled it.
  const list = useRef<HTMLOListElement>(null);
  const [editing, setEditing] = useState(false);
  const scrolled = useRef(0);
  const current = (started ?? rows[0])?.frame;
  const centre = (frame: number | undefined) => {
    const box = list.current;
    const item = box?.querySelector<HTMLElement>(`[data-frame="${frame}"]`);
    box?.scrollTo({ top: item ? item.offsetTop - (box.clientHeight - item.offsetHeight) / 2 : 0, behavior: 'smooth' });
    return item;
  };
  useEffect(() => {
    if (!editing && Date.now() - scrolled.current > HOLD_MS) {
      centre(current);
    }
  }, [current, editing]);
  // A touch just added: in view, its player field ready to type in.
  const [fresh, setFresh] = useState<{ frame: number }>();
  useEffect(() => {
    if (fresh !== undefined) {
      centre(fresh.frame)?.querySelector('input')?.focus({ preventScroll: true });
    }
  }, [fresh]);

  return (
    <>
      <div className="relative lg:self-stretch">
        <div className="flex max-h-[70vh] flex-col gap-2 lg:absolute lg:inset-0 lg:max-h-none">
          <Button variant="outline" className="shrink-0 bg-card" disabled={!canAdd} onClick={add}>
            <Plus aria-hidden />
            {t('review.reportAdd', { time: clock(now) })}
          </Button>
          {rows.length ? (
            <ol
              ref={list}
              aria-label={t('review.reportTouches')}
              className="relative grid min-h-0 flex-1 auto-rows-max grid-cols-[minmax(0,1fr)] gap-1.5 overflow-y-auto overscroll-contain pr-1"
              onWheel={() => (scrolled.current = Date.now())}
              onTouchMove={() => (scrolled.current = Date.now())}
              onFocus={(event) => setEditing(event.target.matches('input, select'))}
              onBlur={() => setEditing(false)}
            >
              {rows.map((row) => {
                const touch = touches.find((x) => x.frame === row.frame);
                const remove = () => (touch ? edit(touch, { player: 'none' }) : setAdded((all) => all.filter((a) => a.frame !== row.frame)));
                const change = (c: Fix) => (touch ? edit(touch, c) : editAdded(row.frame, c));
                return (
                  <li
                    key={row.frame}
                    data-frame={row.frame}
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
                        onClick={() => (row.removed && touch ? edit(touch, { player: undefined }) : remove())}
                      >
                        {row.removed ? <Undo2 aria-hidden /> : <Trash2 aria-hidden />}
                      </Button>
                    </div>
                    {!row.removed && (
                      <div className="flex items-center gap-1.5">
                        <PlayerSelect
                          // Anyone of either team: the touch takes the player's team.
                          players={players}
                          nameOf={nameOf}
                          value={row.player}
                          empty={t('review.pickPlayer')}
                          label={t('review.reportPlayer')}
                          className="h-8 min-w-0 flex-1 text-sm font-normal"
                          openOnFocus={false}
                          onChange={(who) => who && (row.added ? editAdded(row.frame, { player: who, team: teamOf(who) }) : change({ player: who }))}
                        />
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">{t('review.reportNoTouches')}</p>
          )}
        </div>
      </div>
      <div className="grid gap-4 lg:col-span-2">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
          <span className="flex flex-wrap items-center gap-2">
            {t('review.reportWinner')}
            <ToggleGroup type="single" variant="outline" spacing={0} value={winner === null ? '' : String(winner)} onValueChange={(v) => v && setWinner(Number(v) as Group)}>
              {GROUPS.map((g) => (
                <ToggleGroupItem key={g} value={String(g)} className="h-9 gap-2 px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                  <Swatch color={teamColor(g)} ring={teamRing(g)} />
                  {groupName(t, g)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </span>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={notPlay} onChange={(e) => setNotPlay(e.target.checked)} />
            {t('review.notPlay')}
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!changed} onClick={() => onSave(changes)}>
            <Check aria-hidden />
            {t('review.reportSave')}
          </Button>
          <Button variant="outline" onClick={() => onSave({ touches: [] })}>
            <CircleCheck aria-hidden />
            {t('review.reportNothing')}
          </Button>
          <Button variant="outline" onClick={onSkip}>
            <HelpCircle aria-hidden />
            {t('review.skip')}
          </Button>
        </div>
      </div>
    </>
  );
}

/** What the viewers reported about a rally: the kind of problem, the moment they saw, their comment. */
export function ReportComments({ question }: { question: Question }) {
  const { t } = useTranslation();
  return (
    <div className="grid gap-2">
      {question.reports?.map((report, k) => (
        <div key={k} className="grid gap-1 rounded-md border-l-4 border-primary bg-muted/50 px-3 py-2 text-sm">
          <span className="font-medium">{t(`feedback.kinds.${report.kind}`, { defaultValue: report.kind ?? '' })}</span>
          {report.shown && <span className="text-muted-foreground">{report.shown}</span>}
          {report.comment && <span>« {report.comment} »</span>}
        </div>
      ))}
    </div>
  );
}
