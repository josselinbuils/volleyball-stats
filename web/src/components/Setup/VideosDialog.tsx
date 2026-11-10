import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, Radio, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useRunning } from '@/hooks/useRunning';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import { type AppState, type VideosJob } from './helpers/setup';

/** A numbered step of the dialog. */
function Step({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span aria-hidden className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium tabular-nums">
        {n}
      </span>
      <div className="grid min-w-0 flex-1 gap-2 pt-0.5">{children}</div>
    </li>
  );
}

/** The videos copied straight between this machine and the other one on the same network (data_sync.py): one waits and
 * shows an address and a code, the other types them. Each gets the videos only the other has. WSL2 cannot be reached from
 * the network: there it only joins, and the steps say to wait on the other machine, which must be a Mac or Linux:
 * two Windows PCs cannot sync (ponytail: a PowerShell relay on the Windows side would let WSL wait). */
export function VideosDialog({ job, system, onChange, onClose }: { job: VideosJob | null; system: AppState['system']; onChange: () => Promise<void>; onClose: () => void }) {
  const { t } = useTranslation();
  const [address, setAddress] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState(false);
  const [doing, run] = useRunning();
  const act = (path: string, body: object = {}) =>
    run(path, async () => {
      const r = await call(path, body);
      setError(!r.ok);
      await onChange();
    });
  const join = (event: FormEvent) => {
    event.preventDefault();
    void act('videos/join', { address: address.trim(), code: code.trim() });
  };
  const ended = job && !job.running;
  const joinForm = (
    <form onSubmit={join} className="grid gap-2">
      <div className="flex flex-wrap gap-2">
        <input
          aria-label={t('app.videos.address')}
          placeholder={t('app.videos.address')}
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          className={cn(INPUT, 'min-w-0 flex-1 font-mono text-sm')}
        />
        <input aria-label={t('app.videos.code')} placeholder={t('app.videos.code')} value={code} onChange={(e) => setCode(e.target.value)} className={cn(INPUT, 'w-32 font-mono text-sm')} />
      </div>
      <Button
        type="submit"
        variant={system === 'wsl' ? 'default' : 'outline'}
        className="w-fit"
        busy={doing === 'videos/join'}
        disabled={!/^[\w.-]+:\d+$/.test(address.trim()) || !code.trim() || !!doing}
      >
        <Link aria-hidden />
        {t('app.videos.join')}
      </Button>
    </form>
  );

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('app.videos.title')}</DialogTitle>
          <DialogDescription>{t('app.videos.intro')}</DialogDescription>
        </DialogHeader>
        {job?.running ? (
          <div className="grid gap-3">
            {job.code && !job.copying ? (
              <>
                <p>{t('app.videos.waiting', { open: t('app.videos.open') })}</p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                  <dt className="text-muted-foreground">{t('app.videos.address')}</dt>
                  <dd className="font-mono select-all">
                    {job.address}:{job.port}
                  </dd>
                  <dt className="text-muted-foreground">{t('app.videos.code')}</dt>
                  <dd className="font-mono select-all">{job.code}</dd>
                </dl>
              </>
            ) : (
              <p>{t('app.videos.copying')}</p>
            )}
            <Button variant="outline" className="w-fit" busy={doing === 'stop'} onClick={() => void act('stop', { id: job.id })}>
              <Square aria-hidden />
              {t('app.stop')}
            </Button>
          </div>
        ) : (
          <div className="grid gap-4">
            {ended && <p className={job.failed ? 'text-destructive' : undefined}>{job.failed ? t('app.videos.failed', { error: job.error ?? '' }) : t('app.videos.done')}</p>}
            {system === 'wsl' ? (
              <ol className="grid gap-4">
                <Step n={1}>
                  <p>{t('app.videos.thereWait', { open: t('app.videos.open'), wait: t('app.videos.wait') })}</p>
                  <p className="text-muted-foreground">{t('app.videos.otherSystem')}</p>
                </Step>
                <Step n={2}>
                  <p>{t('app.videos.hereJoin')}</p>
                  {joinForm}
                </Step>
              </ol>
            ) : (
              <>
                <ol className="grid gap-4">
                  <Step n={1}>
                    <Button className="w-fit" busy={doing === 'videos/wait'} disabled={!!doing} onClick={() => void act('videos/wait')}>
                      <Radio aria-hidden />
                      {t('app.videos.wait')}
                    </Button>
                  </Step>
                  <Step n={2}>
                    <p>{t('app.videos.thereJoin', { open: t('app.videos.open') })}</p>
                  </Step>
                </ol>
                <div className="grid gap-2 border-t pt-4">
                  <p className="font-medium">{t('app.videos.joinTitle')}</p>
                  {joinForm}
                </div>
              </>
            )}
          </div>
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
