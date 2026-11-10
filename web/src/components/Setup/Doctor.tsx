import { CircleCheck, CircleX, RefreshCw, TriangleAlert } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useRunning } from '@/hooks/useRunning';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { Check } from './helpers/setup';

/** A check's text: what was found, and when it is not right, what to do. */
export function checkText(t: TFunction, check: Check): string {
  if (check.detail) {
    return t('app.doctor.failed', { detail: check.detail });
  }
  switch (check.id) {
    case 'tools':
      return check.status === 'ok' ? t('app.doctor.tools.ok') : t('app.doctor.tools.missing', { tools: (check.missing as string[]).join(', ') });
    case 'gpu':
      return t(`app.doctor.gpu.${check.kind}`, { name: check.name });
    case 'memory':
      return t(`app.doctor.memory.${check.status}${check.status !== 'ok' && check.wsl ? 'Wsl' : ''}`, { gb: check.gb });
    case 'disk':
      return check.slow ? t('app.doctor.disk.slow', { gb: check.gb }) : t(`app.doctor.disk.${check.status}`, { gb: check.gb });
    case 'models':
      return check.status === 'ok' ? t('app.doctor.models.ok') : t('app.doctor.models.missing', { count: check.missing as number });
    case 'code':
      return check.status === 'ok' ? t('app.doctor.code.ok') : t('app.doctor.code.behind', { count: check.behind });
    case 'busy':
      return check.status === 'ok' ? t('app.doctor.busy.ok') : t('app.doctor.busy.busy', { load: check.load, cores: check.cores });
  }
}

const ICONS = { ok: CircleCheck, warn: TriangleAlert, error: CircleX };
const COLOURS = { ok: 'text-(--point)', warn: 'text-warning', error: 'text-destructive' };

/** Every check of the machine, passed or not. */
export function Doctor({ checks, onRecheck, onClose }: { checks: Check[] | null; onRecheck: () => Promise<void>; onClose: () => void }) {
  const [checking, run] = useRunning();
  const { t } = useTranslation();

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('app.doctor.title')}</DialogTitle>
        </DialogHeader>
        {checks ? (
          <ul className="grid gap-3">
            {checks.map((check) => {
              const Icon = ICONS[check.status];
              return (
                <li key={check.id} className="flex items-start gap-2">
                  <Icon aria-label={t(`app.doctor.status.${check.status}`)} className={`mt-0.5 size-4 shrink-0 ${COLOURS[check.status]}`} />
                  <span className="grid gap-1">
                    <span className="font-medium">{t(`app.doctor.name.${check.id}`)}</span>
                    <span className="text-muted-foreground">{checkText(t, check)}</span>
                    {check.command && <code className="w-fit rounded-md bg-muted px-2 py-1 font-mono text-xs select-all">{check.command}</code>}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-muted-foreground">{t('app.doctor.checking')}</p>
        )}
        <Button variant="outline" className="w-fit" busy={!!checking} onClick={() => void run('recheck', onRecheck)}>
          <RefreshCw aria-hidden />
          {t('app.doctor.again')}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
