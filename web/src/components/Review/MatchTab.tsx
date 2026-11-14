import { useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { Maximize, Minimize } from 'lucide-react';
import { VideoButton } from '@/components/VideoButton';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { match, rallies } from '@/lib/match';
import type { Named, Question, ReportChanges, Timeout, TimeoutChange } from '@/lib/review';
import type { NameOf } from '@/components/Review/helpers/players';
import { liveReports, openingTime, pageSpans, REPORT_LEAD_S, type Span } from '@/components/Review/helpers/report';
import { ClipVideo } from '@/components/Review/ClipVideo';
import { MatchTimeline } from '@/components/Review/MatchTimeline';
import { PlayerSelect } from '@/components/Review/PlayerSelect';
import { ReportEditor, type Caption } from '@/components/Review/ReportEditor';
import { slowStarts } from '@/components/Review/helpers/scrub';
import type { HeightDoubt } from '@/components/Review/helpers/checks';

// The automatic reports doubting of a touch's action by its height: the problem each flags, on a touch of that action.
const HEIGHT_DOUBTS: Record<string, { problem: HeightDoubt; type: string }> = {
  'auto.lowAttack': { problem: 'lowAttack', type: 'attack' },
  'auto.highRelance': { problem: 'highRelance', type: 'relance' },
};

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
  picks,
  onPick,
  timeouts,
  onTimeout,
  reports,
  onSave,
  onSaveUnchecked,
  onUncheck,
  onHandled,
  timeRef: clipTime,
  onUnsaved,
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
  /** The touches in the films, by their frame. */
  picks: Set<number>;
  onPick: (frame: number, picked: boolean) => void;
  timeouts: Timeout[];
  onTimeout: (change: TimeoutChange) => void;
  /** The report questions left: each a rally's reports. */
  reports: Question[];
  onSave: (changes: ReportChanges, rally: number) => Promise<void>;
  onSaveUnchecked: (changes: ReportChanges, rally: number) => Promise<void>;
  onUncheck: (rally: number) => Promise<void>;
  onHandled: (report: Question, changes: ReportChanges) => Promise<void>;
  /** Where the video stands, to the frame. */
  timeRef: RefObject<number>;
  /** How many rallies have corrections not saved yet. */
  onUnsaved: (count: number) => void;
}) {
  const { t } = useTranslation();
  const [now, setNow] = useState(0);
  const [seek, setSeek] = useState<{ time: number; n: number; play?: boolean }>();
  const [caption, setCaption] = useState<Caption | null>(null);
  // The rallies as they stand with the corrections, on both bars.
  const [spans, setSpans] = useState<Span[]>(() => pageSpans(rallies, match.fps));
  const playing = useRef(false);
  const [clip] = useState(() => {
    const at = openingTime(rallies, checked, reports, match.fps);
    return { start: at, end: at, around: 0, boxes: [] };
  });
  // During the video's lead-in to where it opened, the list already shows that rally.
  const opened = clip.start + REPORT_LEAD_S;
  const listNow = now >= clip.start && now < opened ? opened : now;
  // The editor starts again from the corrections saved, after each save.
  const [round, setRound] = useState(0);
  const listPlace = useRef({ top: 0, scrolled: 0 });
  const go = (time: number, play?: boolean) => setSeek((s) => ({ time: Math.max(0, time), n: (s?.n ?? 0) + 1, play }));
  // The warnings as the editor finds them.
  const [touchTimes, setTouchTimes] = useState<number[]>([]);
  // For the video's loop, which keeps the first onTime given.
  const touchesNow = useRef(touchTimes);
  touchesNow.current = touchTimes;
  const [found, setFound] = useState<{ times: number[]; warned: number[]; joined: number[] }>({ times: [], warned: [], joined: [] });
  const live = liveReports(reports, new Set(found.joined));
  const flags = live.flatMap((q) => q.reports ?? []).map((r) => ({ ...r, auto: r.kind?.startsWith('auto.') ?? false }));
  // A viewer's report flags the touch they saw; an automatic one is about the rally.
  const seen = flags.filter((r) => !r.auto);
  // An automatic report doubting of a touch's action by its height flags that touch.
  const doubts = flags.flatMap((r) => (r.kind && r.kind in HEIGHT_DOUBTS ? (r.at ?? []).map((time) => ({ time, ...HEIGHT_DOUBTS[r.kind!] })) : []));
  // Checked, with no report open on it nor corrections not saved since.
  const open = new Set(live.map((q) => q.rally));
  const [unsaved, setUnsaved] = useState<Set<number>>(new Set());
  useEffect(() => {
    onUnsaved(unsaved.size);
  }, [unsaved]);
  useEffect(() => () => onUnsaved(0), []);
  const green = new Set(checked.filter((k) => !open.has(k) && !unsaved.has(k)));
  const warned = new Set(found.warned);
  // The automatic reports the editor's warnings do not already show.
  const unwarned = live.filter((q) => q.rally == null || !warned.has(q.rally)).flatMap((q) => (q.reports ?? []).filter((r) => r.kind?.startsWith('auto.')));
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
      <CardContent className="grid grid-cols-[minmax(0,1fr)] gap-6">
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
              captionEdit={
                caption?.setPlayer &&
                ((close) => (
                  <PlayerSelect
                    players={players}
                    nameOf={nameOf}
                    value={caption.player}
                    likely={caption.likely}
                    empty={t('review.pickPlayer')}
                    label={t('review.reportPlayer')}
                    autoFocus
                    onDone={close}
                    onChange={(who) => who && caption.setPlayer?.(who)}
                  />
                ))
              }
              spans={spans}
              onPaused={(paused) => (playing.current = !paused)}
              marks={flags.map((r) => r.time)}
              touches={touchTimes}
              showTime
              onTime={(at: number) => setNow((n) => (Math.abs(n - at) >= 0.1 || slowStarts(touchesNow.current, n, at) ? at : n))}
              extra={
                document.fullscreenEnabled && (
                  <VideoButton label={t(full ? 'review.exitFullScreen' : 'review.fullScreen')} onClick={toggleFull}>
                    {full ? <Minimize aria-hidden /> : <Maximize aria-hidden />}
                  </VideoButton>
                )
              }
            />
            <MatchTimeline
              rallies={spans}
              now={now}
              saved={saved}
              reports={seen}
              warnings={[...found.times.map((time) => ({ time })), ...unwarned]}
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
            onWarnings={setFound}
            onUnsaved={(keys) => setUnsaved(new Set(keys))}
            onTouches={setTouchTimes}
            onRallies={setSpans}
            isPlaying={() => playing.current}
            reports={seen}
            doubts={doubts}
            players={players}
            nameOf={nameOf}
            now={listNow}
            timeOf={() => clipTime.current}
            onPlay={(at) => go(at - REPORT_LEAD_S, true)}
            onPause={(at) => go(at, false)}
            onSave={(changes, rally, onward) =>
              onSave(changes, rally).then(() => {
                setRound((r) => r + 1);
                const k = spans.findIndex((r) => r.key === rally);
                if (onward && k >= 0 && spans[k + 1]) {
                  go(spans[k + 1].start - REPORT_LEAD_S, true);
                }
              })
            }
            onSaveUnchecked={(changes, rally) => onSaveUnchecked(changes, rally).then(() => setRound((r) => r + 1))}
            green={green}
            checked={new Set(checked)}
            onUncheck={(rally) => onUncheck(rally)}
            onCaption={setCaption}
            questions={reports}
            onHandled={(q, changes) => void onHandled(q, changes).then(() => setRound((r) => r + 1))}
            saved={saved}
            comments={comments}
            onComment={onComment}
            picks={picks}
            onPick={onPick}
            timeouts={timeouts}
            onTimeout={onTimeout}
          />
        </div>
      </CardContent>
    </Card>
  );
}
