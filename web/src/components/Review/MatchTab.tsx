import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Maximize, Minimize, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { clock, useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
import { match, rallies, type Group } from '@/lib/match';
import type { Named, Question, ReportChanges, Timeout, TimeoutChange } from '@/lib/review';
import type { NameOf } from '@/components/Review/helpers/players';
import { REPORT_LEAD_S } from '@/components/Review/helpers/report';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { MatchTimeline } from '@/components/Review/MatchTimeline';
import { ReportEditor } from '@/components/Review/ReportEditor';

/** The whole match to correct: its video, the bar of its rallies, touches and the viewers' reports
 * under it, the touches around where it stands beside it; under them the reports left to handle,
 * each marked handled once looked at (the corrections as they stand saved with it). */
export function MatchTab({
  width,
  height,
  players,
  nameOf,
  saved,
  checked,
  comments,
  onComment,
  timeouts,
  onTimeout,
  reports,
  onSave,
  onUncheck,
  onHandled,
}: {
  width: number;
  height: number;
  players: Named[];
  nameOf: NameOf;
  /** The corrections saved and not applied yet. */
  saved: Partial<ReportChanges>;
  /** The rallies checked, by their key. */
  checked: number[];
  /** The owner's notes on the rallies, by their key. */
  comments: Record<number, string>;
  onComment: (rally: number, text: string) => Promise<boolean>;
  timeouts: Timeout[];
  onTimeout: (change: TimeoutChange) => void;
  /** The report questions left: each a rally's reports. */
  reports: Question[];
  onSave: (changes: ReportChanges, rally: number) => Promise<void>;
  onUncheck: (rally: number) => Promise<void>;
  onHandled: (report: Question, changes: ReportChanges) => Promise<void>;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const clipTime = useRef(0);
  const [now, setNow] = useState(0);
  const [seek, setSeek] = useState<{ time: number; n: number; play?: boolean }>();
  const [caption, setCaption] = useState<{ team: Group; text: string } | null>(null);
  // The video starts at the first report, else at the first rally.
  const [clip] = useState(() => {
    const at = Math.max(0, (reports[0]?.reports?.[0]?.time ?? rallies[0]?.start ?? 0) - REPORT_LEAD_S);
    return { start: at, end: at, around: 0, boxes: [] };
  });
  // The editor starts again from the corrections saved, after each save.
  const [round, setRound] = useState(0);
  const latest = useRef<ReportChanges>({ touches: [], ...saved });
  const go = (time: number, play?: boolean) => setSeek((s) => ({ time: Math.max(0, time), n: (s?.n ?? 0) + 1, play }));
  const flags = reports.flatMap((q) => q.reports ?? []).map((r) => ({ ...r, auto: r.kind?.startsWith('auto.') ?? false }));
  // A viewer's report flags the touch they saw; an automatic one is about the rally.
  const seen = flags.filter((r) => !r.auto);
  // Checked, and no report open on it since.
  const open = new Set(reports.map((q) => q.rally));
  const green = new Set(checked.filter((k) => !open.has(k)));
  // The rallies with a warning as the editor finds them, by their key.
  const [warned, setWarned] = useState<Set<number>>(new Set());
  // The video, its bar, the editor and the reports fill the screen, the video as large as its height allows.
  const block = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const changed = () => setFull(document.fullscreenElement === block.current);
    document.addEventListener('fullscreenchange', changed);
    return () => document.removeEventListener('fullscreenchange', changed);
  }, []);
  const toggleFull = () => void (full ? document.exitFullscreen() : block.current?.requestFullscreen());

  return (
    <Card>
      <CardContent className="grid grid-cols-[minmax(0,1fr)] gap-6 pt-6">
        <div
          ref={block}
          className={cn(
            'grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:grid-rows-[auto_1fr]',
            full && 'h-screen overflow-y-auto overscroll-contain bg-background p-4 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,26rem)]',
          )}
        >
          <div className={cn('grid min-w-0 gap-4', full && 'mx-auto w-full max-w-[calc((100vh-11rem)*16/9)]')}>
            <ClipVideo
              clip={clip}
              width={width}
              height={height}
              timeRef={clipTime}
              seek={seek}
              free
              autoPlay={false}
              caption={caption}
              marks={flags.map((r) => r.time)}
              showTime
              onTime={(at: number) => setNow((n) => (Math.abs(n - at) >= 0.1 ? at : n))}
              extra={
                document.fullscreenEnabled && (
                  <Button variant="outline" size="sm" className="bg-card" onClick={toggleFull}>
                    {full ? <Minimize aria-hidden /> : <Maximize aria-hidden />}
                    {t(full ? 'review.exitFullScreen' : 'review.fullScreen')}
                  </Button>
                )
              }
            />
            <MatchTimeline now={now} saved={saved} reports={flags} green={green} warned={warned} comments={comments} timeouts={timeouts} onSeek={(time) => go(time)} />
          </div>
          <ReportEditor
            key={round}
            onWarnings={(keys) => setWarned(new Set(keys))}
            reports={seen}
            players={players}
            nameOf={nameOf}
            now={now}
            timeOf={() => clipTime.current}
            onPlay={(at) => go(at - REPORT_LEAD_S, true)}
            onPause={(at) => go(at, false)}
            onSave={(changes, rally) =>
              void onSave(changes, rally).then(() => {
                setRound((r) => r + 1);
                // Checked: on to the next rally.
                const k = rallies.findIndex((r) => (r.key ?? Math.round(r.start * match.fps)) === rally);
                if (k >= 0 && rallies[k + 1]) {
                  go(rallies[k + 1].start - REPORT_LEAD_S, true);
                }
              })
            }
            green={green}
            checked={new Set(checked)}
            onUncheck={(rally) => void onUncheck(rally)}
            onCaption={setCaption}
            onChanges={(changes) => (latest.current = changes)}
            saved={saved}
            comments={comments}
            onComment={onComment}
            timeouts={timeouts}
            onTimeout={onTimeout}
          />
          <section className="grid gap-2 lg:col-span-2" aria-labelledby="reports-title">
            <h3 id="reports-title" className="text-base font-semibold">
              {t('review.reportsTitle', { count: reports.length })}
            </h3>
            {reports.length === 0 && <p className="text-sm text-muted-foreground">{t('review.noReports')}</p>}
            <ol className="grid gap-2">
              {reports.map((q) => {
                const at = q.reports?.[0]?.time ?? q.clip.start;
                return (
                  <li key={q.id} className="grid gap-2 rounded-md border-l-4 border-primary bg-muted/50 px-3 py-2 text-sm sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-start">
                    <Button variant="outline" size="sm" className="justify-self-start bg-card tabular-nums" title={t('review.reportGo')} onClick={() => go(at - REPORT_LEAD_S, true)}>
                      <Play aria-hidden className="fill-current" />
                      {clock(at)}
                    </Button>
                    <div className="grid gap-1">
                      {q.reports?.map((r, k) => (
                        <p key={k} className="m-0">
                          {r.kind?.startsWith('auto.') && <span className="mr-1.5 rounded-sm bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{t('review.autoReport')}</span>}
                          <span className="font-medium">{t(`feedback.kinds.${r.kind}`, { defaultValue: r.kind ?? '' })}</span>
                          {r.shown && <span className="text-muted-foreground">{` · ${r.shown}`}</span>}
                          {r.comment && <span>{` · « ${r.comment} »`}</span>}
                          {r.received && <span className="text-muted-foreground">{` · ${t('review.reportReceived', { when: f.when(r.received) })}`}</span>}
                        </p>
                      ))}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="justify-self-start bg-card"
                      title={t('review.reportHandledNote')}
                      onClick={() => void onHandled(q, latest.current).then(() => setRound((r) => r + 1))}
                    >
                      <Check aria-hidden />
                      {t('review.reportHandled')}
                    </Button>
                  </li>
                );
              })}
            </ol>
          </section>
        </div>
      </CardContent>
    </Card>
  );
}
