import { useEffect, useRef, useState } from 'react';
import { LoaderCircle, Pause, Play, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';
import { Zoomable } from '@/components/Zoomable';
import { seekLine } from '@/components/Watch/helpers/seekBar';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';
import { chapterAt, sourceQuery } from './helpers/setup';

// How long the slider rests before its picture is asked for: one picture, not one per pixel dragged.
const SETTLE_MS = 200;

/** The recording to watch before importing it: which team plays on which side, where the match starts and ends. It plays
 * the camera's own video, chapter after chapter, zoomed and full screen at will; a browser that cannot play it shows the
 * pictures of a slider instead. A slider, steps, and "start here" / "end here"; `at` follows a time typed in a field, the
 * kept span (`from`..`to`) shows on the slider. */
export function CutPreview({
  source,
  recording,
  chapters,
  at,
  from,
  to,
  onPick,
}: {
  source: string | string[];
  recording: number;
  /** Each chapter's length, in seconds. */
  chapters: number[];
  at: number;
  from: number | null;
  to: number | null;
  onPick: (key: 'from' | 'to', seconds: number) => void;
}) {
  const { t } = useTranslation();
  const duration = chapters.reduce((a, b) => a + b, 0);
  const [time, setTime] = useState(at);
  const [pictures, setPictures] = useState(false);
  const [chapter, setChapter] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [ready, setReady] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  // Where to go once the chapter loaded, and whether to play on.
  const pending = useRef<number | null>(null);

  const seek = (seconds: number) => {
    const target = Math.min(duration, Math.max(0, seconds));
    setTime(target);
    if (pictures) {
      return;
    }
    const [k, offset] = chapterAt(chapters, target);
    if (k !== chapter) {
      pending.current = offset;
      setReady(false);
      setChapter(k);
    } else if (video.current) {
      video.current.currentTime = offset;
    }
  };
  useEffect(() => seek(at), [at]);

  const query = (extra: Record<string, string>) => sourceQuery(source, { recording: String(recording), ...extra });
  const toggle = () => {
    const v = video.current;
    if (v) {
      void (v.paused ? v.play() : v.pause());
    }
  };
  const line = seekLine(0, 0, duration, [[from ?? 0, to ?? duration]], {
    played: 'transparent',
    heldColor: 'var(--primary)',
    rest: 'color-mix(in oklab, var(--foreground) 15%, transparent)',
  });

  return (
    <div className="grid gap-2">
      <Zoomable
        className="aspect-video"
        controls={
          !pictures && (
            <>
              <Tip label={t(playing ? 'pauseVideo' : 'playVideo')}>
                <Button type="button" variant="secondary" size="icon-sm" aria-label={t(playing ? 'pauseVideo' : 'playVideo')} disabled={!ready} onClick={toggle}>
                  {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
                </Button>
              </Tip>
              <Tip label={t(muted ? 'unmuteVideo' : 'muteVideo')}>
                <Button type="button" variant="secondary" size="icon-sm" aria-label={t(muted ? 'unmuteVideo' : 'muteVideo')} onClick={() => setMuted(!muted)}>
                  {muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
                </Button>
              </Tip>
              <span className="mr-auto" />
            </>
          )
        }
      >
        {pictures ? (
          <Picture source={source} recording={recording} time={time} />
        ) : (
          <>
            <video
              ref={video}
              key={chapter}
              src={`/app/video?${query({ chapter: String(chapter) })}`}
              muted={muted}
              playsInline
              preload="auto"
              className={cn('size-full object-contain', !ready && 'invisible')}
              onLoadedMetadata={(e) => {
                const v = e.currentTarget;
                v.currentTime = pending.current ?? time - chapters.slice(0, chapter).reduce((a, b) => a + b, 0);
                pending.current = null;
              }}
              onCanPlay={(e) => {
                setReady(true);
                if (playing && e.currentTarget.paused) {
                  void e.currentTarget.play();
                }
              }}
              onPlay={() => setPlaying(true)}
              onPause={(e) => !e.currentTarget.ended && setPlaying(false)}
              onTimeUpdate={(e) => setTime(chapters.slice(0, chapter).reduce((a, b) => a + b, 0) + e.currentTarget.currentTime)}
              onEnded={() => {
                // The next chapter plays on.
                if (chapter + 1 < chapters.length) {
                  pending.current = 0;
                  setReady(false);
                  setChapter(chapter + 1);
                } else {
                  setPlaying(false);
                }
              }}
              // A browser that cannot play the camera's video (HEVC): the pictures.
              onError={() => setPictures(true)}
            />
            {!ready && <LoaderCircle aria-hidden className="absolute top-1/2 left-1/2 size-6 -translate-1/2 animate-spin text-muted-foreground" />}
          </>
        )}
      </Zoomable>
      <input
        type="range"
        min={0}
        max={duration}
        step={1}
        value={time}
        onChange={(e) => seek(Number(e.target.value))}
        aria-label={t('app.import.when')}
        aria-valuetext={clock(time)}
        style={line}
        className={cn(
          'h-7 w-full cursor-pointer appearance-none rounded-md bg-transparent outline-none focus-visible:ring-3',
          '[&::-webkit-slider-thumb]:size-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-(--primary)',
          '[&::-moz-range-thumb]:size-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-(--primary) [&::-moz-range-track]:bg-transparent',
        )}
      />
      <div className="flex flex-wrap items-center justify-center gap-1">
        {[-60, -10, null, 10, 60].map((step) =>
          step === null ? (
            <span key="time" className="min-w-16 text-center tabular-nums">
              {clock(time)}
            </span>
          ) : (
            <Button key={step} type="button" variant="ghost" size="sm" className="tabular-nums" onClick={() => seek(time + step)}>
              {(step < 0 ? '−' : '+') + (Math.abs(step) < 60 ? t('app.import.seconds', { n: Math.abs(step) }) : t('app.import.minutes', { n: Math.abs(step) / 60 }))}
            </Button>
          ),
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Button type="button" variant="outline" onClick={() => onPick('from', time)}>
          {t('app.import.fromHere')}
        </Button>
        <Button type="button" variant="outline" onClick={() => onPick('to', time)}>
          {t('app.import.toHere')}
        </Button>
      </div>
    </div>
  );
}

/** The recording's picture at `time`, asked for once the slider rests. */
function Picture({ source, recording, time }: { source: string | string[]; recording: number; time: number }) {
  const { t } = useTranslation();
  const [shown, setShown] = useState(time);
  const [loaded, setLoaded] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const wait = window.setTimeout(() => setShown(time), SETTLE_MS);
    return () => window.clearTimeout(wait);
  }, [time]);
  const src = `/app/preview?${sourceQuery(source, { recording: String(recording), at: String(Math.round(shown)) })}`;
  return (
    <>
      <img
        src={src}
        alt={t('app.import.preview', { time: clock(shown) })}
        draggable={false}
        onLoad={() => (setLoaded(src), setFailed(false))}
        onError={() => (setLoaded(src), setFailed(true))}
        className={cn('size-full object-contain', (failed || !loaded) && 'invisible')}
      />
      {loaded !== src && <LoaderCircle aria-hidden className="absolute top-1/2 left-1/2 size-6 -translate-1/2 animate-spin text-muted-foreground" />}
      {failed && loaded === src && <p className="absolute inset-0 grid place-items-center p-4 text-center text-muted-foreground">{t('app.import.noPreview')}</p>}
    </>
  );
}
