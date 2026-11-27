import { useState, type ReactNode } from 'react';
import { Camera, Frame } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { CalibrateDialog } from './CalibrateDialog';

// Texts under app.guide.<key>, app.guide.setting.<key> and app.guide.item.<key>.
const PLACE = ['where', 'high', 'frame', 'still'];
const SETTINGS = ['resolution', 'fps', 'stabilisation', 'fov', 'exposure', 'shutter', 'white', 'flicker', 'loop'];
const PACK = ['camera', 'power', 'stand', 'hold', 'fan'];
const ONCE = ['card', 'test'];

const DASHED = { stroke: 'var(--primary)', strokeWidth: 1, strokeDasharray: '3 3', vectorEffect: 'non-scaling-stroke' } as const;

/** The court from above, the camera beyond a sideline on the net's line, what it sees shaded. */
function TopView() {
  const { t } = useTranslation();
  return (
    <svg viewBox="-10.5 -6.7 21 18.4" role="img" aria-label={t('app.guide.top')} className="block h-auto w-full">
      <polygon points="0,10.5 -10,3.83 -10,-5.6 10,-5.6 10,3.83" fill="var(--primary)" opacity={0.08} />
      <rect x={-9} y={-4.5} width={18} height={9} className="fill-court" />
      <rect x={-9} y={-4.5} width={18} height={9} className="court-line" />
      {[-3, 3].map((x) => (
        <line key={x} x1={x} x2={x} y1={-4.5} y2={4.5} className="court-line" />
      ))}
      <line x1={0} x2={0} y1={5.25} y2={10} {...DASHED} />
      <line x1={0} x2={0} y1={-5.25} y2={5.25} stroke="var(--net)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {[-1, 1].map((side) => (
        <line key={side} x1={0} y1={10.5} x2={10 * side} y2={3.83} {...DASHED} />
      ))}
      <rect x={-0.7} y={10.3} width={1.4} height={0.9} rx={0.15} fill="var(--foreground)" />
      <rect x={-0.35} y={10} width={0.7} height={0.35} fill="var(--foreground)" />
      <text x={0} y={-5.9} textAnchor="middle" className="fill-muted-foreground text-[0.8px]">
        {t('app.guide.net')}
      </text>
      <text x={1.1} y={11.1} className="fill-muted-foreground text-[0.8px]">
        {t('app.guide.camera')}
      </text>
    </svg>
  );
}

/** From an end line: the camera high on a stand, back from the sideline, looking down across the court. */
function SideView() {
  const { t } = useTranslation();
  // Heights go up: the drawing's y is minus the height in metres. Its labels as large as the top view's, both as wide.
  const label = 'fill-muted-foreground text-[0.53px]';
  return (
    <svg viewBox="-2.8 -4.3 14 5.6" role="img" aria-label={t('app.guide.side')} className="block h-auto w-full">
      <polygon points="0,-3.6 6,0 11.2,0 11.2,-2.7" fill="var(--primary)" opacity={0.08} />
      <line x1={-2.8} x2={11.2} y1={0} y2={0} stroke="var(--muted-foreground)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      {/* The net: its post on the near sideline, the band running away from the camera. */}
      <rect x={6} y={-2.43} width={5.2} height={1} fill="var(--net)" opacity={0.15} />
      <line x1={6} x2={11.2} y1={-2.43} y2={-2.43} stroke="var(--net)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      <line x1={6} x2={6} y1={0} y2={-2.55} stroke="var(--net)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {[6, 11.2].map((x, k) => (
        <line key={x} x1={0} y1={-3.6} x2={x} y2={k ? -2.7 : 0} {...DASHED} />
      ))}
      <g stroke="var(--foreground)" strokeWidth={2} strokeLinecap="round">
        <line x1={0} x2={0} y1={0} y2={-3.6} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={-0.7} y1={-0.8} y2={0} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={0.7} y1={-0.8} y2={0} vectorEffect="non-scaling-stroke" />
      </g>
      <g transform="translate(0 -3.6) rotate(25)">
        <rect x={-0.3} y={-0.22} width={0.6} height={0.44} rx={0.08} fill="var(--foreground)" />
        <rect x={0.3} y={-0.1} width={0.14} height={0.2} fill="var(--foreground)" />
      </g>
      <g stroke="var(--muted-foreground)" strokeWidth={1}>
        <line x1={-1.2} x2={-1.2} y1={0} y2={-3.6} vectorEffect="non-scaling-stroke" />
        <line x1={-1.35} x2={-1.05} y1={-3.6} y2={-3.6} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={6} y1={0.65} y2={0.65} vectorEffect="non-scaling-stroke" />
        <line x1={6} x2={6} y1={0.5} y2={0.8} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={0} y1={0.5} y2={0.8} vectorEffect="non-scaling-stroke" />
      </g>
      <text transform="translate(-1.45 -1.8) rotate(-90)" textAnchor="middle" className={label}>
        {t('app.guide.up')}
      </text>
      <text x={3} y={1.2} textAnchor="middle" className={label}>
        {t('app.guide.back')}
      </text>
      <text x={8.6} y={-1.75} textAnchor="middle" className={label}>
        {t('app.guide.net')}
      </text>
    </svg>
  );
}

/** A numbered step: its number, its title, then its content under the title (under both on a phone). */
function Step({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  return (
    <section className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-3">
      <span aria-hidden className="flex size-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
        {number}
      </span>
      <h3 className="m-0 self-center text-base leading-snug font-semibold">{title}</h3>
      <div className="col-span-2 grid min-w-0 gap-3 sm:col-span-1 sm:col-start-2">{children}</div>
    </section>
  );
}

/** How to film a match with any camera: where it goes, how it is set, what to bring. `onFraming` opens the framing
 * check. recording.md is the long version, for the camera this project was made with. */
export function GuideDialog({ onClose, onFraming }: { onClose: () => void; onFraming: () => void }) {
  const { t } = useTranslation();
  const [calibrating, setCalibrating] = useState(false);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] gap-6 overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('app.guide.title')}</DialogTitle>
          <DialogDescription>{t('app.guide.why')}</DialogDescription>
        </DialogHeader>
        <Step number={1} title={t('app.guide.place')}>
          <div className="grid items-end gap-4 rounded-lg bg-muted/50 p-4 sm:grid-cols-2">
            <div className="mx-auto w-full max-w-xs">
              <TopView />
            </div>
            <div className="mx-auto w-full max-w-xs">
              <SideView />
            </div>
          </div>
          <ul className="m-0 grid list-disc gap-1 pl-5">
            {PLACE.map((key) => (
              <li key={key}>{t(`app.guide.${key}`)}</li>
            ))}
          </ul>
          <Button variant="outline" className="w-fit" onClick={onFraming}>
            <Frame aria-hidden />
            {t('app.framing.open')}
          </Button>
        </Step>
        <Step number={2} title={t('app.guide.settings')}>
          <dl className="m-0 grid divide-y rounded-lg border">
            {SETTINGS.map((setting) => (
              <div key={setting} className="grid gap-x-4 gap-y-0.5 px-3 py-2 sm:grid-cols-[12rem_1fr]">
                <dt className="text-muted-foreground">{t(`app.guide.setting.${setting}`)}</dt>
                <dd className="m-0">{t(`app.guide.value.${setting}`)}</dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <p className="m-0">{t('app.guide.lens')}</p>
            <Button variant="outline" className="w-fit" onClick={() => setCalibrating(true)}>
              <Camera aria-hidden />
              {t('app.lens.open')}
            </Button>
          </div>
        </Step>
        <Step number={3} title={t('app.guide.pack')}>
          <ul className="m-0 grid gap-2 sm:grid-cols-2">
            {PACK.map((item) => (
              <li key={item}>
                <label className="flex h-full cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 has-checked:border-primary has-checked:bg-primary/5">
                  <input type="checkbox" className="mt-0.5 size-4 shrink-0 accent-(--primary)" />
                  {t(`app.guide.item.${item}`)}
                </label>
              </li>
            ))}
          </ul>
        </Step>
        <section className="grid gap-1.5 rounded-lg bg-muted/50 px-4 py-3">
          <h3 className="m-0 font-semibold">{t('app.guide.once')}</h3>
          <ul className="m-0 grid list-disc gap-1 pl-5">
            {ONCE.map((item) => (
              <li key={item}>{t(`app.guide.item.${item}`)}</li>
            ))}
          </ul>
        </section>
        {calibrating && <CalibrateDialog onClose={() => setCalibrating(false)} />}
      </DialogContent>
    </Dialog>
  );
}
