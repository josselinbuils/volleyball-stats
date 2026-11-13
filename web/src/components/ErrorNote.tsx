import { useEffect, useRef, useState, type ReactNode } from 'react';
import { LoaderCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import { onAppServer } from '@/lib/appServer';
import { cn } from '@/lib/utils';

/** A failure, the same look everywhere: red, under what failed, `text` (a generic "failed: try again" by default), the
 * server's own words `detail` small below it, `action` beside it (a retry), and on the app's server a link to its log
 * when it may tell more (`log`, by default for the generic text). */
export function ErrorNote({ text, detail, log = !text, action, className }: { text?: string; detail?: string | null; log?: boolean; action?: ReactNode; className?: string }) {
  const { t } = useTranslation();
  const [reading, setReading] = useState(false);
  return (
    <div role="alert" className={cn('grid gap-0.5 [overflow-wrap:anywhere]', className)}>
      <p className="m-0 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-destructive">
          {text ?? t('error.failed')}
          {log && onAppServer() && (
            <Button variant="link" className="ml-1.5 h-auto p-0 align-baseline text-[length:inherit] text-destructive underline" onClick={() => setReading(true)}>
              {t('error.details')}
            </Button>
          )}
        </span>
        {action}
      </p>
      {detail && <p className="m-0 text-xs text-muted-foreground">{detail}</p>}
      {reading && <LogDialog onClose={() => setReading(false)} />}
    </div>
  );
}

/** The end of the app's log, the newest last, in view. */
export function LogDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const box = useRef<HTMLPreElement>(null);
  useEffect(() => {
    void call<{ text: string }>('log').then((r) => (r.ok ? setText(r.text) : setFailed(true)));
  }, []);
  useEffect(() => {
    box.current?.scrollTo(0, box.current.scrollHeight);
  }, [text]);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent container={document.fullscreenElement} aria-describedby={undefined} className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('error.log')}</DialogTitle>
        </DialogHeader>
        {failed ? (
          <ErrorNote text={t('error.noAnswer')} />
        ) : text === null ? (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
            {t('error.logLoading')}
          </p>
        ) : (
          <pre ref={box} className="m-0 max-h-[60dvh] overflow-auto rounded-md bg-muted p-2 font-mono text-xs whitespace-pre-wrap [overflow-wrap:anywhere]">
            {text.trim() || t('error.logEmpty')}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}
