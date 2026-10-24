import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { match } from '@/lib/match';
import type { Clip } from '@/lib/review';
import { boxAt } from '@/components/Review/helpers/box';

/** Half a second of context around a clip, played in a loop. */
const AROUND = 0.5;

/** The video looping over `clip`, the player outlined in yellow, which stands out from both jerseys and the floor. */
export function ClipVideo({ clip, width, height }: { clip: Clip; width: number; height: number }) {
  const { t } = useTranslation();
  const video = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(clip.start);

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
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [clip]);

  const box = boxAt(clip, time);
  return (
    <div className="relative">
      <video ref={video} src={match.video} muted playsInline controls aria-label={t('review.video')} className="block aspect-video w-full rounded-lg bg-black" />
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
            strokeWidth={4}
            className="drop-shadow-[0_0_3px_rgba(0,0,0,0.9)]"
          />
        )}
      </svg>
    </div>
  );
}
