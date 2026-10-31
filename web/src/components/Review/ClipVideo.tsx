import { useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { clock } from '@/lib/format';
import { match } from '@/lib/match';
import type { Clip } from '@/lib/review';
import { boxAt, viewAt } from '@/components/Review/helpers/box';

/** Half a second of context around a clip, played in a loop, unless the clip says otherwise. */
const AROUND = 0.5;
/** Playback speeds offered, to catch a short moment; the one picked carries over to the next clip. */
const SPEEDS = [1, 0.5, 0.25];
let picked = 1;

/** The video looping over `clip`, the player outlined in yellow, which stands out from both jerseys and the floor, and zoomed on them unless the whole frame is asked for;
 * with `showTime` the match time under it, `marks` (times) drawn on its progress bar, `onTime` told where it stands. */
export function ClipVideo({
  clip,
  width,
  height,
  timeRef,
  seek,
  marks = [],
  showTime = false,
  onTime,
}: {
  clip: Clip;
  width: number;
  height: number;
  timeRef?: RefObject<number>;
  seek?: { time: number; n: number; play?: boolean };
  marks?: number[];
  showTime?: boolean;
  onTime?: (time: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(clip.start);
  const [zoom, setZoom] = useState(true);
  const [speed, setSpeed] = useState(picked);
  // Loading the video resets its rate to the default one: both are set.
  useEffect(() => {
    if (video.current) {
      video.current.defaultPlaybackRate = speed;
      video.current.playbackRate = speed;
    }
  }, [speed]);

  const around = clip.around ?? AROUND;
  useEffect(() => {
    const v = video.current;
    if (!v) {
      return;
    }
    v.currentTime = Math.max(0, clip.start - around);
    void v.play().catch(() => {});
    let frame = 0;
    const tick = () => {
      if (v.currentTime > clip.end + around) {
        v.currentTime = Math.max(0, clip.start - around);
      }
      const rate = clip.slow && v.currentTime >= clip.start && v.currentTime <= clip.end ? Math.min(clip.slow, picked) : picked;
      if (v.playbackRate !== rate) {
        v.playbackRate = rate;
      }
      setTime(v.currentTime);
      if (timeRef) {
        timeRef.current = v.currentTime;
      }
      onTime?.(v.currentTime);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [clip]);

  // A moment asked for (`n` counts the asks, so the same moment can be asked again): shown paused,
  // or played from there (`play`).
  useEffect(() => {
    const v = video.current;
    if (v && seek) {
      v.currentTime = seek.time;
      void (seek.play ? v.play().catch(() => {}) : v.pause());
    }
  }, [seek]);

  const box = boxAt(clip, time);
  // Where the loop stands, and the outlined part of it.
  const from = Math.max(0, clip.start - around);
  const share = (at: number) => `${(100 * (Math.min(clip.end + around, Math.max(from, at)) - from)) / (clip.end + around - from)}%`;
  const view = zoom ? viewAt(clip, time, width, height) : { x: 0, y: 0, w: width, h: height };
  // The native controls would zoom with the video: a click plays or pauses it instead.
  const toggle = () => {
    const v = video.current;
    if (v) {
      void (v.paused ? v.play().catch(() => {}) : v.pause());
    }
  };
  return (
    <div className="grid gap-2">
      <div className="relative aspect-video overflow-hidden rounded-lg bg-black">
        <div className="absolute inset-0 origin-top-left" style={{ transform: `scale(${width / view.w}) translate(${(-100 * view.x) / width}%, ${(-100 * view.y) / height}%)` }}>
          <video ref={video} src={match.video ?? undefined} muted playsInline controls={!zoom} onClick={zoom ? toggle : undefined} aria-label={t('review.video')} className="block size-full" />
          <svg viewBox={`0 0 ${width} ${height}`} aria-hidden className="pointer-events-none absolute inset-0 size-full">
            {box && (
              <rect
                x={box[0] - 6}
                y={box[1] - 6}
                width={box[2] - box[0] + 12}
                height={box[3] - box[1] + 12}
                rx={6}
                fill="none"
                stroke="#ffd400"
                strokeWidth={3}
                vectorEffect="non-scaling-stroke"
                className="drop-shadow-[0_0_3px_rgba(0,0,0,0.9)]"
              />
            )}
          </svg>
        </div>
      </div>
      <div className="relative h-1.5 rounded-full bg-muted" aria-hidden>
        <div className="absolute inset-y-0 rounded-full bg-[#ffd400]" style={{ left: share(clip.start), right: `calc(100% - ${share(clip.end)})` }} />
        {marks.map((m) => (
          <div key={m} className="absolute -inset-y-1.5 w-1 -translate-x-1/2 rounded-full bg-primary" style={{ left: share(m) }} />
        ))}
        <div className="absolute -inset-y-1 w-0.5 rounded-full bg-foreground" style={{ left: share(time) }} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {showTime && <span className="min-w-12 text-sm font-medium tabular-nums">{clock(time)}</span>}
        {/* No outline, nothing to zoom on. */}
        {clip.boxes.length > 0 && (
          <Button variant="outline" size="sm" className="bg-card" onClick={() => setZoom((z) => !z)}>
            {zoom ? <ZoomOut aria-hidden /> : <ZoomIn aria-hidden />}
            {t(zoom ? 'review.zoomOut' : 'review.zoomIn')}
          </Button>
        )}
        <div role="group" aria-label={t('review.speed')} className="flex gap-1">
          {SPEEDS.map((s) => (
            <Button
              key={s}
              variant={s === speed ? 'default' : 'outline'}
              size="sm"
              className={s === speed ? undefined : 'bg-card'}
              aria-pressed={s === speed}
              onClick={() => {
                picked = s;
                setSpeed(s);
              }}
            >
              {`${new Intl.NumberFormat(i18n.language).format(s)}×`}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}
