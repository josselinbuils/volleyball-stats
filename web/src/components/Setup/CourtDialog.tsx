import { useRef, useState, type FormEvent, type MouseEvent } from 'react';
import { Check, EyeOff, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import { LANDMARKS, MIN_CLICKS, imageUrl, nextLandmark } from './helpers/setup';

// The magnifier: its radius in screen pixels and how much it enlarges the picture as shown.
const LENS = 70;
const ZOOM = 4;

/** Where the court's points are on the court sketch, in its SVG units (1 per metre, the far side up). */
const sketch = (x: number, y: number) => ({ cx: x + 10.5, cy: y + 6.5 });

/** The court placed by hand, the first time in a gym: a click on each point the sketch shows (rough is fine, the lines
 * are found around it), then the gym's name, for its next matches to find it alone. */
export function CourtDialog({ match, onClose }: { match: string; onClose: (placed: boolean) => void }) {
  const { t } = useTranslation();
  const image = useRef<HTMLImageElement>(null);
  // Each landmark in order: its place in the picture's pixels, or null when hidden.
  const [done, setDone] = useState<([number, number] | null)[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [unreadable, setUnreadable] = useState(false);
  const [lens, setLens] = useState<{ x: number; y: number } | null>(null);
  const [name, setName] = useState('');
  const [error, setError] = useState(false);
  const current = nextLandmark(done.length);
  const clicks = Object.fromEntries(done.flatMap((p, k) => (p ? [[LANDMARKS[k][0], p]] : [])));
  const enough = Object.keys(clicks).length >= MIN_CLICKS;

  const place = (event: MouseEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    if (!current) {
      return;
    }
    const box = img.getBoundingClientRect();
    setDone((d) => [...d, [((event.clientX - box.left) / box.width) * img.naturalWidth, ((event.clientY - box.top) / box.height) * img.naturalHeight]]);
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const r = await call('court/fit', { match, clicks, court: name.trim() });
    if (r.ok) {
      onClose(true);
    } else {
      setError(true);
    }
  };
  const shown = image.current;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose(false)}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{t('app.court.title')}</DialogTitle>
          <DialogDescription>{t('app.court.intro')}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-3">
          <svg viewBox="0 0 21 13" className="h-20 shrink-0" aria-hidden>
            <rect x={1.5} y={2} width={18} height={9} className="fill-none stroke-muted-foreground" strokeWidth={0.15} />
            {[-3, 0, 3].map((x) => (
              <line key={x} x1={x + 10.5} x2={x + 10.5} y1={2} y2={11} className="stroke-muted-foreground" strokeWidth={x ? 0.1 : 0.2} />
            ))}
            {LANDMARKS.map(([id, x, y], k) => (
              <circle key={id} {...sketch(x, y)} r={id === current ? 0.7 : 0.35} className={id === current ? 'fill-destructive' : k < done.length ? 'fill-foreground' : 'fill-muted-foreground/50'} />
            ))}
          </svg>
          <p className="min-w-0 flex-1 font-medium">{current ? t('app.court.click', { point: t(`app.court.point.${current}`) }) : t('app.court.allDone')}</p>
          <div className="flex gap-2">
            {current && (
              <Button variant="outline" onClick={() => setDone((d) => [...d, null])}>
                <EyeOff aria-hidden />
                {t('app.court.hidden')}
              </Button>
            )}
            <Button variant="outline" disabled={!done.length} onClick={() => setDone((d) => d.slice(0, -1))}>
              <Undo2 aria-hidden />
              {t('app.court.undo')}
            </Button>
          </div>
        </div>
        <div className="relative">
          {!loaded && <p className={cn('py-12 text-center', unreadable ? 'text-destructive' : 'text-muted-foreground')}>{t(unreadable ? 'app.court.noPicture' : 'app.court.loading')}</p>}
          <img
            ref={image}
            src={imageUrl(match, 'background')}
            alt={t('app.court.picture')}
            onLoad={() => setLoaded(true)}
            onError={() => setUnreadable(true)}
            onClick={place}
            onMouseMove={(e) => {
              const box = e.currentTarget.getBoundingClientRect();
              setLens({ x: e.clientX - box.left, y: e.clientY - box.top });
            }}
            onMouseLeave={() => setLens(null)}
            className={cn('w-full rounded-md select-none', current ? 'cursor-crosshair' : 'cursor-default', !loaded && 'hidden')}
            draggable={false}
          />
          {loaded &&
            shown &&
            done.map((p, k) =>
              p ? (
                <span
                  key={k}
                  aria-hidden
                  className="pointer-events-none absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-primary shadow"
                  style={{ left: `${(p[0] / shown.naturalWidth) * 100}%`, top: `${(p[1] / shown.naturalHeight) * 100}%` }}
                />
              ) : null,
            )}
          {loaded && lens && current && shown && (
            <span
              aria-hidden
              className="pointer-events-none absolute rounded-full border-2 border-white shadow-lg"
              style={{
                width: 2 * LENS,
                height: 2 * LENS,
                left: lens.x + 24 + 2 * LENS < shown.clientWidth ? lens.x + 24 : lens.x - 24 - 2 * LENS,
                top: Math.max(0, lens.y - LENS),
                backgroundImage: `url("${shown.currentSrc}")`,
                backgroundSize: `${shown.clientWidth * ZOOM}px ${shown.clientHeight * ZOOM}px`,
                backgroundPosition: `${LENS - lens.x * ZOOM}px ${LENS - lens.y * ZOOM}px`,
              }}
            >
              <span className="absolute top-1/2 left-0 h-px w-full bg-destructive" />
              <span className="absolute top-0 left-1/2 h-full w-px bg-destructive" />
            </span>
          )}
        </div>
        {(!current || enough) && (
          <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
            <label className="grid min-w-0 flex-1 gap-1 font-medium">
              {t('app.court.name')}
              <input required value={name} onChange={(e) => setName(e.target.value)} className={INPUT} />
            </label>
            <Button type="submit" disabled={!enough || !name.trim() || /[,:/]/.test(name)}>
              <Check aria-hidden />
              {t('app.court.save')}
            </Button>
          </form>
        )}
        {error && (
          <p role="alert" className="text-destructive">
            {t('review.error')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
