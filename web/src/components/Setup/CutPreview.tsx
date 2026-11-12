import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { seekLine } from '@/components/Watch/helpers/seekBar';
import { clock } from '@/lib/format';
import { cn } from '@/lib/utils';

// How long the slider rests before its picture is asked for: one picture, not one per pixel dragged.
const SETTLE_MS = 200;

/** The recording's picture at a time, to find where the match starts and ends: a slider, steps, and "start here" / "end
 * here". `at` follows a time typed in a field; the kept span (`from`..`to`) shows on the slider. */
export function CutPreview({
  source,
  recording,
  duration,
  at,
  from,
  to,
  onPick,
}: {
  source: string;
  recording: number;
  duration: number;
  at: number;
  from: number | null;
  to: number | null;
  onPick: (key: 'from' | 'to', seconds: number) => void;
}) {
  const { t } = useTranslation();
  const [time, setTime] = useState(at);
  const [shown, setShown] = useState(at);
  const [loaded, setLoaded] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => setTime(at), [at]);
  useEffect(() => {
    const wait = window.setTimeout(() => setShown(time), SETTLE_MS);
    return () => window.clearTimeout(wait);
  }, [time]);
  const src = `/app/preview?${new URLSearchParams({ source, recording: String(recording), at: String(Math.round(shown)) })}`;
  const move = (seconds: number) => setTime(Math.min(duration, Math.max(0, seconds)));
  const line = seekLine(0, 0, duration, [[from ?? 0, to ?? duration]], {
    played: 'transparent',
    heldColor: 'var(--primary)',
    rest: 'color-mix(in oklab, var(--foreground) 15%, transparent)',
  });

  return (
    <div className="grid gap-2">
      <div className="relative aspect-video overflow-hidden rounded-md bg-muted">
        <img
          src={src}
          alt={t('app.import.preview', { time: clock(shown) })}
          onLoad={() => (setLoaded(src), setFailed(false))}
          onError={() => (setLoaded(src), setFailed(true))}
          className={cn('size-full object-contain', (failed || !loaded) && 'invisible')}
        />
        {loaded !== src && <LoaderCircle aria-hidden className="absolute top-1/2 left-1/2 size-6 -translate-1/2 animate-spin text-muted-foreground" />}
        {failed && loaded === src && <p className="absolute inset-0 grid place-items-center p-4 text-center text-muted-foreground">{t('app.import.noPreview')}</p>}
      </div>
      <input
        type="range"
        min={0}
        max={duration}
        step={1}
        value={time}
        onChange={(e) => move(Number(e.target.value))}
        aria-label={t('app.import.when')}
        aria-valuetext={clock(time)}
        style={line}
        className={cn(
          'h-7 w-full cursor-pointer appearance-none rounded-md bg-transparent outline-none focus-visible:ring-3',
          '[&::-webkit-slider-thumb]:size-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-(--primary)',
          '[&::-moz-range-thumb]:size-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-(--primary) [&::-moz-range-track]:bg-transparent',
        )}
      />
      <div className="flex items-center justify-center gap-1">
        {[-60, -10, null, 10, 60].map((step) =>
          step === null ? (
            <span key="time" className="min-w-16 text-center tabular-nums">
              {clock(time)}
            </span>
          ) : (
            <Button key={step} type="button" variant="ghost" size="sm" className="tabular-nums" onClick={() => move(time + step)}>
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
