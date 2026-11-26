import { useState, type ReactNode } from 'react';
import { Camera, Frame } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { CalibrateDialog } from './CalibrateDialog';

// The settings by camera, grouped as its menus are: texts under app.guide.<camera>.<group> and .<setting>.
const SETTINGS = {
  osmo3: {
    up: ['resolution', 'fps', 'loop', 'stabilisation'],
    pro: ['fov', 'exposure', 'shutter', 'iso', 'white', 'colour', 'enhanced', 'wind', 'directional'],
    down: ['flicker', 'screen', 'off'],
  },
  other: { all: ['resolution', 'fps', 'stabilisation', 'loop', 'fov', 'exposure', 'shutter', 'iso', 'white', 'flicker'] },
} as const;
type CameraKind = keyof typeof SETTINGS;
const PACK = ['camera', 'power', 'stand', 'straps', 'fan', 'sandbags'];
const ONCE = ['card', 'test'];

const LABEL = 'fill-muted-foreground text-[0.8px]';

/** The court from above, the camera beyond the near sideline on the net's line, what it sees shaded. */
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
      <line x1={0} x2={0} y1={5.25} y2={10} stroke="var(--primary)" strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
      <line x1={0} x2={0} y1={-5.25} y2={5.25} stroke="var(--net)" strokeWidth={3} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {[-1, 1].map((side) => (
        <line key={side} x1={0} y1={10.5} x2={10 * side} y2={3.83} stroke="var(--primary)" strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
      ))}
      <rect x={-0.7} y={10.3} width={1.4} height={0.9} rx={0.15} fill="var(--foreground)" />
      <rect x={-0.35} y={10} width={0.7} height={0.35} fill="var(--foreground)" />
      <text x={0} y={-5.9} textAnchor="middle" className={LABEL}>
        {t('app.guide.net')}
      </text>
      <text x={1.1} y={11.1} className={LABEL}>
        {t('app.guide.camera')}
      </text>
    </svg>
  );
}

/** From an end line: the camera 3.6 m up a stand strapped to a goal post, 6 m from the near sideline, its fan below. */
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
        <line key={x} x1={0} y1={-3.6} x2={x} y2={k ? -2.7 : 0} stroke="var(--primary)" strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
      ))}
      {/* The goal post, the stand strapped to it at two heights, its legs. */}
      <rect x={-0.26} y={-2} width={0.16} height={2} fill="var(--muted-foreground)" opacity={0.6} />
      <g stroke="var(--foreground)" strokeWidth={2} strokeLinecap="round">
        <line x1={0} x2={0} y1={0} y2={-3.6} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={-0.7} y1={-0.8} y2={0} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={0.7} y1={-0.8} y2={0} vectorEffect="non-scaling-stroke" />
      </g>
      {[-0.3, -1.8].map((y) => (
        <rect key={y} x={-0.32} y={y - 0.06} width={0.4} height={0.12} rx={0.03} fill="var(--primary)" />
      ))}
      <g transform="translate(0 -3.6) rotate(25)">
        <rect x={-0.3} y={-0.22} width={0.6} height={0.44} rx={0.08} fill="var(--foreground)" />
        <rect x={0.3} y={-0.1} width={0.14} height={0.2} fill="var(--foreground)" />
      </g>
      {/* The fan 80 cm below, blowing up at the camera. */}
      <rect x={0.08} y={-2.95} width={0.34} height={0.3} rx={0.06} fill="var(--muted-foreground)" />
      <path d="M 0.25 -3.05 L 0.25 -3.3 M 0.17 -3.2 L 0.25 -3.3 L 0.33 -3.2" fill="none" stroke="var(--muted-foreground)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      <text x={0.6} y={-2.68} className={label}>
        {t('app.guide.fan')}
      </text>
      {/* Heights and distances. */}
      <g stroke="var(--muted-foreground)" strokeWidth={1}>
        <line x1={-1.2} x2={-1.2} y1={0} y2={-3.6} vectorEffect="non-scaling-stroke" />
        <line x1={-1.35} x2={-1.05} y1={-3.6} y2={-3.6} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={6} y1={0.65} y2={0.65} vectorEffect="non-scaling-stroke" />
        <line x1={6} x2={6} y1={0.5} y2={0.8} vectorEffect="non-scaling-stroke" />
        <line x1={0} x2={0} y1={0.5} y2={0.8} vectorEffect="non-scaling-stroke" />
      </g>
      <text x={-1.4} y={-1.65} textAnchor="end" className={label}>
        {t('app.guide.high')}
      </text>
      <text x={3} y={1.2} textAnchor="middle" className={label}>
        {t('app.guide.back')}
      </text>
      <text x={8.6} y={-2.75} textAnchor="middle" className={label}>
        {t('app.guide.net')}
      </text>
    </svg>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2">
      <h3 className="m-0 text-base font-semibold">{title}</h3>
      {children}
    </section>
  );
}

/** How to film a match: the camera's place as drawings, its settings for the cameras known, what to bring.
 * `onFraming` opens the framing check. recording.md is the long version. */
export function GuideDialog({ onClose, onFraming }: { onClose: () => void; onFraming: () => void }) {
  const { t } = useTranslation();
  const [camera, setCamera] = useState<CameraKind>('osmo3');
  const [calibrating, setCalibrating] = useState(false);
  const groups = SETTINGS[camera] as Record<string, readonly string[]>;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('app.guide.title')}</DialogTitle>
          <DialogDescription>{t('app.guide.why')}</DialogDescription>
        </DialogHeader>
        <Section title={t('app.guide.place')}>
          <div className="grid items-end gap-4 sm:grid-cols-2">
            <div className="mx-auto w-full max-w-xs">
              <TopView />
            </div>
            <div className="mx-auto w-full max-w-xs">
              <SideView />
            </div>
          </div>
          <ul className="m-0 grid list-disc gap-1 pl-5">
            {['where', 'frame', 'stand', 'fanText', 'battery'].map((key) => (
              <li key={key}>{t(`app.guide.${key}`)}</li>
            ))}
          </ul>
          <Button variant="outline" className="w-fit" onClick={onFraming}>
            <Frame aria-hidden />
            {t('app.framing.open')}
          </Button>
        </Section>
        <Section title={t('app.guide.settings')}>
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            value={camera}
            onValueChange={(v) => v && setCamera(v as CameraKind)}
            aria-label={t('app.guide.cameraKind')}
            className="w-fit bg-card"
          >
            {(Object.keys(SETTINGS) as CameraKind[]).map((kind) => (
              <ToggleGroupItem key={kind} value={kind} className="h-9 px-4 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
                {t(`app.guide.${kind}.name`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {Object.entries(groups).map(([group, settings]) => (
            <div key={group} className="grid gap-1.5">
              {group !== 'all' && <p className="m-0 mt-1 font-semibold">{t(`app.guide.${camera}.${group}`)}</p>}
              <dl className="m-0 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                {settings.map((setting) => (
                  <div key={setting} className="flex flex-wrap gap-x-1.5">
                    <dt className="text-muted-foreground">{t(`app.guide.setting.${setting}`)}</dt>
                    <dd className="m-0">{t(`app.guide.${camera}.${setting}`)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
          {camera === 'other' && (
            <div className="grid gap-2">
              <p className="m-0">{t('app.guide.lens')}</p>
              <Button variant="outline" className="w-fit" onClick={() => setCalibrating(true)}>
                <Camera aria-hidden />
                {t('app.lens.open')}
              </Button>
            </div>
          )}
        </Section>
        <Section title={t('app.guide.pack')}>
          <ul className="m-0 grid gap-1.5">
            {PACK.map((item) => (
              <li key={item}>
                <label className="flex items-start gap-2">
                  <input type="checkbox" className="mt-0.5 size-4 shrink-0 accent-(--primary)" />
                  {t(`app.guide.item.${item}`)}
                </label>
              </li>
            ))}
          </ul>
        </Section>
        <Section title={t('app.guide.once')}>
          <ul className="m-0 grid list-disc gap-1 pl-5">
            {ONCE.map((item) => (
              <li key={item}>{t(`app.guide.item.${item}`)}</li>
            ))}
          </ul>
        </Section>
        {calibrating && <CalibrateDialog onClose={() => setCalibrating(false)} />}
      </DialogContent>
    </Dialog>
  );
}
