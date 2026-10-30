import { useEffect, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { match } from '@/lib/match';
import type { Clip } from '@/lib/review';
import { boxAt, viewAt } from '@/components/Review/helpers/box';

/** Half a second of context around a clip, played in a loop. */
const AROUND = 0.5;

/** The video looping over `clip`, the player outlined in yellow, which stands out from both jerseys and the floor, and zoomed on them unless the whole frame is asked for. */
export function ClipVideo({ clip, width, height, timeRef }: { clip: Clip; width: number; height: number; timeRef?: RefObject<number> }) {
  const { t } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(clip.start);
  const [zoom, setZoom] = useState(true);

  useEffect(() => {
    const v = video.current;
    if (!v) {
      return;
    }
    v.currentTime = Math.max(0, clip.start - AROUND);
    void v.play().catch(() => {});
    let frame = 0;
    const tick = () => {
      if (v.currentTime > clip.end + AROUND) {
        v.currentTime = Math.max(0, clip.start - AROUND);
      }
      setTime(v.currentTime);
      if (timeRef) {
        timeRef.current = v.currentTime;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [clip]);

  const box = boxAt(clip, time);
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
      <Button variant="outline" size="sm" className="justify-self-start bg-card" onClick={() => setZoom((z) => !z)}>
        {zoom ? <ZoomOut aria-hidden /> : <ZoomIn aria-hidden />}
        {t(zoom ? 'review.zoomOut' : 'review.zoomIn')}
      </Button>
    </div>
  );
}
