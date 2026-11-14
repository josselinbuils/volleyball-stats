import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Keyboard } from 'lucide-react';
import { VideoButton } from '@/components/VideoButton';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ARROW_STEP_S } from '@/components/Review/ClipVideo';
import { ADD_KEY, TYPE_KEYS, VALIDATE_KEY } from '@/components/Review/ReportEditor';

const KBD = 'justify-self-start rounded border px-1.5 text-xs text-muted-foreground';

function Keys({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="col-span-2 grid grid-cols-subgrid items-center gap-y-2">
      {rows.map(([key, label]) => (
        <Fragment key={key}>
          <dt>
            <kbd className={KBD}>{key}</kbd>
          </dt>
          <dd>{label}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

/** The Match tab's keyboard shortcuts, all of them in a dialog opened from the video's bar; none on a touch screen. */
export function Shortcuts() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <>
      <VideoButton label={t('review.shortcuts')} className="pointer-coarse:hidden" onClick={() => setOpen(true)}>
        <Keyboard aria-hidden />
      </VideoButton>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          container={document.fullscreenElement}
          aria-describedby={undefined}
          // On the dialog, not its close button: nothing there to press.
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            (event.currentTarget as HTMLElement).focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t('review.shortcuts')}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2">
            <Keys
              rows={[
                [t('review.spaceKey'), t('review.shortcutPlay')],
                ['← →', t('review.shortcutStep', { s: ARROW_STEP_S })],
                [ADD_KEY.toUpperCase(), t('review.shortcutAdd')],
                [VALIDATE_KEY.toUpperCase(), t('review.shortcutValidate')],
              ]}
            />
            <h3 className="col-span-2 mt-2 font-medium">{t('review.shortcutType')}</h3>
            <Keys rows={Object.entries(TYPE_KEYS).map(([key, type]) => [key.toUpperCase(), t(`types.${type}`)])} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
