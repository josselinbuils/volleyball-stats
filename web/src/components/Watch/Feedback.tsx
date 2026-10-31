import { useEffect, useState, type FormEvent } from 'react';
import { Check, Flag, MessageSquarePlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { clock, useFormat } from '@/lib/format';
import { groupName, match } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { clipLabel, rallyNear } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { cn } from '@/lib/utils';

const KINDS = ['player', 'action', 'result', 'ball', 'notPlay', 'other'] as const;

// How long the thanks, and the offer to give details, stay on the button.
const THANKS_MS = 8000;

/** A report as sent: one tap sends the moment alone (kind "flag"); details sent later keep its `id`. */
interface Report {
  id: string;
  page: string;
  match: string;
  time: number;
  rally: number | null;
  clip: { time: number; type: string | null; team: number | null; player: number | null; name: string | null } | null;
  shown: string;
  kind: string;
  comment: string;
}

const newId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

/** A viewer reporting what is wrong in the moment shown, from a button over the top right corner of the
 * video, else (`inline`) in the court replay's title bar: one tap sends the moment (the clip playing,
 * else the rally the video is on), then "Préciser" opens a dialog to say what is wrong and comment,
 * sent as the same report to `match.feedback`, to correct the analysis later. */
export function Feedback({ inline = false }: { inline?: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, video } = usePlayer();
  const { rallies } = useSet();
  const near = useVideoTime((time) => rallyNear(rallies, time)?.i ?? -1);
  const rally = rallies.find((r) => r.i === near);
  const clip = playlist?.clips[playlist.at];
  const shown = playlist && clip ? `${playlist.title(t)} · ${clipLabel(clip, t, f, (g) => groupName(t, g))}` : rally ? `${t('rally', { n: rally.i + 1 })} · ${clock(rally.start)}` : '';
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<(typeof KINDS)[number]>('player');
  const [comment, setComment] = useState('');
  // The moment the last tap reported, which details complete.
  const [flagged, setFlagged] = useState<Report | null>(null);
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle');
  useEffect(() => {
    if (state !== 'sent' || open) {
      return;
    }
    const timer = window.setTimeout(() => setState('idle'), THANKS_MS);
    return () => window.clearTimeout(timer);
  }, [state, open]);
  if (!match.feedback) {
    return null;
  }
  const post = async (report: Report) => {
    setState('sending');
    try {
      const response = await fetch(match.feedback!, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(report) });
      setState(response.ok ? 'sent' : 'failed');
      return response.ok;
    } catch {
      setState('failed');
      return false;
    }
  };
  const flag = () => {
    const report: Report = {
      id: newId(),
      page: location.pathname,
      match: match.name,
      time: Math.round((video?.currentTime ?? 0) * 100) / 100,
      rally: rally?.i ?? null,
      clip: clip ? { time: clip.time, type: clip.type ?? null, team: clip.team ?? null, player: clip.player ?? null, name: clip.name ?? null } : null,
      shown,
      kind: 'flag',
      comment: '',
    };
    setFlagged(report);
    void post(report);
  };
  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (flagged && (await post({ ...flagged, kind, comment: comment.trim() }))) {
      setComment('');
      setOpen(false);
    }
  };
  const details = () => {
    video?.pause();
    setOpen(true);
  };
  const look = inline
    ? 'inline-flex h-8 items-center gap-1.5 rounded-md border bg-card px-2.5 text-xs font-medium shadow-xs outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50'
    : 'inline-flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm outline-none hover:bg-black/75 focus-visible:ring-3 focus-visible:ring-white/60';
  return (
    <div className={cn('flex items-center gap-1.5', inline ? 'relative shrink-0' : 'absolute top-2 right-2 z-10')}>
      <button type="button" title={t('feedback.open')} disabled={state === 'sending'} onClick={flag} className={look}>
        {state === 'sent' ? <Check aria-hidden className={inline ? 'size-3.5' : 'size-4'} /> : <Flag aria-hidden className={inline ? 'size-3.5' : 'size-4'} />}
        <span role="status">{t(state === 'sent' ? 'feedback.thanksShort' : state === 'sending' ? 'feedback.sending' : state === 'failed' ? 'feedback.retry' : 'feedback.button')}</span>
      </button>
      {state === 'sent' && flagged && (
        <button type="button" aria-haspopup="dialog" onClick={details} className={look}>
          <MessageSquarePlus aria-hidden className={inline ? 'size-3.5' : 'size-4'} />
          {t('feedback.details')}
        </button>
      )}
      {/* Escape, a click outside or Annuler close it. */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent showCloseButton={false} container={document.fullscreenElement}>
          <form onSubmit={(e) => void send(e)} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>{t('feedback.what')}</DialogTitle>
              {flagged?.shown && <DialogDescription>{flagged.shown}</DialogDescription>}
            </DialogHeader>
            <fieldset className="grid gap-1.5">
              <legend className="sr-only">{t('feedback.what')}</legend>
              {KINDS.map((k) => (
                <label key={k} className="flex items-center gap-2">
                  <input type="radio" name="kind" value={k} checked={kind === k} onChange={() => setKind(k)} />
                  {t(`feedback.kinds.${k}`)}
                </label>
              ))}
            </fieldset>
            <label className="grid gap-1">
              {t('feedback.comment')}
              <textarea
                value={comment}
                maxLength={500}
                rows={2}
                onChange={(e) => setComment(e.target.value)}
                className="rounded-md border border-input bg-transparent px-2 py-1.5 outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
            </label>
            {state === 'failed' && (
              <p role="alert" className="m-0 text-destructive">
                {t('feedback.failed')}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" size="sm" disabled={state === 'sending'}>
                {t(state === 'sending' ? 'feedback.sending' : 'feedback.send')}
              </Button>
              <DialogClose asChild>
                <Button type="button" variant="outline" size="sm" className="bg-card">
                  {t('feedback.cancel')}
                </Button>
              </DialogClose>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
