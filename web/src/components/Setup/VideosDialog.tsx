import { useState, type FormEvent } from 'react';
import { Link, Radio, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useRunning } from '@/hooks/useRunning';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import { type AppState, type VideosJob } from './helpers/setup';

/** The videos copied straight between this machine and the other one on the same network (data_sync.py): one waits and
 * shows an address and a code, the other types them. Each gets the videos only the other has. */
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
                <p>{t('app.videos.waiting')}</p>
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
            {system !== 'wsl' && (
              <Button className="w-fit" busy={doing === 'videos/wait'} disabled={!!doing} onClick={() => void act('videos/wait')}>
                <Radio aria-hidden />
                {t('app.videos.wait')}
              </Button>
            )}
            <form onSubmit={join} className="grid gap-2">
              <p className="font-medium">{t('app.videos.joinTitle')}</p>
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
              <Button type="submit" variant="outline" className="w-fit" busy={doing === 'videos/join'} disabled={!/^[\w.-]+:\d+$/.test(address.trim()) || !code.trim() || !!doing}>
                <Link aria-hidden />
                {t('app.videos.join')}
              </Button>
            </form>
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
