import { useState } from 'react';
import { Check, CircleCheck, Flag, HelpCircle, Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { GROUPS, groupName, teamColor, teamRing, type Group } from '@/lib/match';
import type { Named, Question, ReportChanges } from '@/lib/review';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import type { NameOf } from '@/components/Review/helpers/players';

const TYPES = ['serve', 'pass', 'set', 'attack', 'relance', 'block', 'dig'] as const;
const RESULTS = ['play', 'point', 'error'] as const;
const SELECT = 'h-9 rounded-md border bg-background px-2 text-sm';

/** A viewer's report on a rally: what they said, then the rally's touches (player, action, result,
 * or no touch at all) and its winner to correct, or the rally marked as no play; only what is
 * changed is saved. */
export function ReportEditor({
  question,
  players,
  nameOf,
  now,
  onPlay,
  onSave,
  onSkip,
}: {
  question: Question;
  players: Named[];
  nameOf: NameOf;
  /** Where the video stands: its touch's row is highlighted. */
  now: number;
  /** Plays the video from a touch. */
  onPlay: (time: number) => void;
  onSave: (changes: ReportChanges) => void;
  onSkip: () => void;
}) {
  const { t } = useTranslation();
  const touches = question.touches ?? [];
  const [fixes, setFixes] = useState<Record<number, { player?: string; type?: string; result?: string }>>({});
  const [winner, setWinner] = useState<Group | null>(question.winner ?? null);
  const [notPlay, setNotPlay] = useState(false);
  const edit = (frame: number, change: { player?: string; type?: string; result?: string }) => setFixes((f) => ({ ...f, [frame]: { ...f[frame], ...change } }));
  const changes: ReportChanges = {
    touches: Object.entries(fixes).map(([frame, c]) => ({ frame: Number(frame), ...c })),
    ...(winner !== null && winner !== question.winner ? { winner } : {}),
    ...(notPlay ? { play: false } : {}),
  };
  const changed = changes.touches.length > 0 || changes.winner !== undefined || notPlay;
  // The touch the video is on: the last one started, until 3 s after it.
  const playing = touches.filter((touch) => touch.time - 0.2 <= now && now - touch.time < 3).at(-1)?.frame;
  // The touches a viewer reported from (the moment replayed then).
  const reported = new Set(touches.filter((touch) => question.reports?.some((r) => Math.abs(r.time - touch.time) <= 0.6)).map((touch) => touch.frame));

  return (
    <div className="grid gap-4 lg:col-span-2">
      {touches.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 pr-2 font-normal">{t('review.reportTime')}</th>
                <th className="py-1 pr-2 font-normal">{t('review.reportType')}</th>
                <th className="py-1 pr-2 font-normal">{t('review.reportPlayer')}</th>
                <th className="py-1 pr-2 font-normal">{t('review.reportResult')}</th>
                <th className="py-1 font-normal">{t('review.reportNoTouch')}</th>
              </tr>
            </thead>
            <tbody>
              {touches.map((touch) => {
                const fix = fixes[touch.frame] ?? {};
                const removed = fix.player === 'none';
                return (
                  <tr key={touch.frame} className={cn('border-t', touch.frame === playing && 'bg-primary/10')}>
                    <td className="py-1.5 pr-2 tabular-nums">
                      <button
                        type="button"
                        title={t('review.reportPlay')}
                        aria-label={`${t('review.reportPlay')} ${clock(touch.time)}`}
                        onClick={() => onPlay(touch.time)}
                        className="flex items-center gap-2 rounded-md px-1.5 py-1 outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        <Play aria-hidden className="size-3.5 fill-current" />
                        <Swatch color={teamColor(touch.team)} ring={teamRing(touch.team)} />
                        {clock(touch.time)}
                        {reported.has(touch.frame) && <Flag aria-label={t('review.reportedTouch')} className="size-3.5 text-primary" />}
                      </button>
                    </td>
                    <td className="py-1.5 pr-2">
                      <select className={SELECT} aria-label={t('review.reportType')} disabled={removed} value={fix.type ?? touch.type} onChange={(e) => edit(touch.frame, { type: e.target.value })}>
                        {TYPES.map((type) => (
                          <option key={type} value={type}>
                            {t(`types.${type}`)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="min-w-48 py-1.5 pr-2">
                      <PlayerSelect
                        players={players.filter((p) => p.team === touch.team)}
                        nameOf={nameOf}
                        value={removed ? '' : (fix.player ?? touch.player ?? '')}
                        empty={t('review.pickPlayer')}
                        label={t('review.reportPlayer')}
                        className="h-9 w-full text-sm font-normal"
                        openOnFocus={false}
                        onChange={(who) => who && edit(touch.frame, { player: who })}
                      />
                    </td>
                    <td className="py-1.5 pr-2">
                      <select
                        className={SELECT}
                        aria-label={t('review.reportResult')}
                        disabled={removed}
                        value={fix.result ?? touch.result ?? 'play'}
                        onChange={(e) => edit(touch.frame, { result: e.target.value })}
                      >
                        {RESULTS.map((result) => (
                          <option key={result} value={result}>
                            {t(`results.${result}`)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1.5 text-center">
                      <input
                        type="checkbox"
                        aria-label={t('review.reportNoTouch')}
                        checked={removed}
                        onChange={(e) => edit(touch.frame, { player: e.target.checked ? 'none' : (touch.player ?? undefined) })}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{t('review.reportNoTouches')}</p>
      )}
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
