import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Maximize, Minimize } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { match, rallies, type Group } from '@/lib/match';
import type { Named, Question, ReportChanges, Timeout, TimeoutChange } from '@/lib/review';
import type { NameOf } from '@/components/Review/helpers/players';
import { REPORT_LEAD_S } from '@/components/Review/helpers/report';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { MatchTimeline } from '@/components/Review/MatchTimeline';
import { ReportEditor } from '@/components/Review/ReportEditor';

/** The whole match to correct: its video, the bar of its rallies, touches and the viewers' reports
 * under it, the touches around where it stands beside it, each rally's reports left to handle under
 * its header. */
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
  onEnd,
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
  onEnd: (time: string) => void;
}) {
  const { t } = useTranslation();
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
  const listPlace = useRef({ top: 0, scrolled: 0 });
  const go = (time: number, play?: boolean) => setSeek((s) => ({ time: Math.max(0, time), n: (s?.n ?? 0) + 1, play }));
  const flags = reports.flatMap((q) => q.reports ?? []).map((r) => ({ ...r, auto: r.kind?.startsWith('auto.') ?? false }));
  // A viewer's report flags the touch they saw; an automatic one is about the rally.
  const seen = flags.filter((r) => !r.auto);
  // Checked, with no report open on it nor corrections not saved since.
  const open = new Set(reports.map((q) => q.rally));
  const [unsaved, setUnsaved] = useState<Set<number>>(new Set());
  const green = new Set(checked.filter((k) => !open.has(k) && !unsaved.has(k)));
  // The warnings as the editor finds them.
  const [warnings, setWarnings] = useState<{ rally: number; time: number }[]>([]);
  const warned = new Set(warnings.map((w) => w.rally));
  // The automatic reports the editor's warnings do not already show.
  const unwarned = reports.filter((q) => q.rally == null || !warned.has(q.rally)).flatMap((q) => (q.reports ?? []).filter((r) => r.kind?.startsWith('auto.')));
  // The video, its bar and the editor fill the screen, the video as large as what is under it leaves room for.
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
            full && 'h-screen overflow-y-auto overscroll-contain bg-background p-4 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,26rem)] lg:grid-rows-[minmax(0,1fr)_auto]',
          )}
        >
          <div className={cn('grid min-w-0 gap-4', full && 'max-lg:mx-auto max-lg:w-full max-lg:max-w-[calc((100vh-11rem)*16/9)] lg:h-full lg:grid-rows-[minmax(0,1fr)_auto] lg:self-stretch')}>
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
            <MatchTimeline
              now={now}
              saved={saved}
              reports={seen}
              warnings={[...warnings, ...unwarned]}
              green={green}
              warned={warned}
              comments={comments}
              timeouts={timeouts}
              onSeek={(time) => go(time)}
            />
          </div>
          <ReportEditor
            key={round}
            place={listPlace}
            onEnd={onEnd}
            onWarnings={setWarnings}
            onUnsaved={(keys) => setUnsaved(new Set(keys))}
            reports={seen}
            players={players}
            nameOf={nameOf}
            now={now}
            timeOf={() => clipTime.current}
            onPlay={(at) => go(at - REPORT_LEAD_S, true)}
            onPause={(at) => go(at, false)}
            onSave={(changes, rally, onward) =>
              void onSave(changes, rally).then(() => {
                setRound((r) => r + 1);
                const k = rallies.findIndex((r) => (r.key ?? Math.round(r.start * match.fps)) === rally);
                if (onward && k >= 0 && rallies[k + 1]) {
                  go(rallies[k + 1].start - REPORT_LEAD_S, true);
                }
              })
            }
            green={green}
            checked={new Set(checked)}
            onUncheck={(rally) => void onUncheck(rally)}
            onCaption={setCaption}
            questions={reports}
            onHandled={(q, changes) => void onHandled(q, changes).then(() => setRound((r) => r + 1))}
            saved={saved}
            comments={comments}
            onComment={onComment}
            timeouts={timeouts}
            onTimeout={onTimeout}
          />
        </div>
      </CardContent>
    </Card>
  );
}
