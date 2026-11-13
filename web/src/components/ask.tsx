import { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';

type Question = { title: string; text?: string; confirm: string; danger?: boolean };

/** Asks the user to confirm, in the app's own dialog (never the browser's, which looks otherwise everywhere): true once
 * confirmed, false once cancelled. */
export function ask(question: Question): Promise<boolean> {
  const host = document.createElement('div');
  document.body.append(host);
  const root = createRoot(host);
  return new Promise((resolve) => {
    const done = (yes: boolean) => {
      resolve(yes);
      // Once its closing animation ends.
      window.setTimeout(() => {
        root.unmount();
        host.remove();
      }, 300);
    };
    root.render(<Asked {...question} onDone={done} />);
  });
}

function Asked({ title, text, confirm, danger, onDone }: Question & { onDone: (yes: boolean) => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);
  const answered = useRef(false);
  const close = (yes: boolean) => {
    if (!answered.current) {
      answered.current = true;
      setOpen(false);
      onDone(yes);
    }
  };
  return (
    <Dialog open={open} onOpenChange={(next) => !next && close(false)}>
      <DialogContent container={document.fullscreenElement} showCloseButton={false} {...(text ? {} : { 'aria-describedby': undefined })}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {text && <DialogDescription>{text}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            {t('app.cancel')}
          </Button>
          <Button variant={danger ? 'destructive' : 'default'} autoFocus onClick={() => close(true)}>
            {confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
