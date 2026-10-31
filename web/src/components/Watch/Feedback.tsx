import { useEffect, useState, type FormEvent } from 'react';
import { Flag } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { clock, useFormat } from '@/lib/format';
import { groupName, match } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { clipLabel, rallyNear } from '@/lib/playlist';
import { useSet } from '@/lib/sets';

const KINDS = ['player', 'action', 'result', 'ball', 'other'] as const;

// How long the thanks stay on the button.
const THANKS_MS = 4000;

/** A viewer reporting what is wrong in the moment shown, from a button over the top right corner of the
 * video, else (`inline`) in the court replay's title bar: what it shows (the clip playing, else the rally the video is on), what is wrong and a
 * comment, sent to `match.feedback` to correct the analysis later. */
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
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle');
  useEffect(() => {
    if (state !== 'sent') {
      return;
    }
    const timer = window.setTimeout(() => setState('idle'), THANKS_MS);
    return () => window.clearTimeout(timer);
  }, [state]);
  if (!match.feedback) {
    return null;
  }
  const send = async (event: FormEvent) => {
    event.preventDefault();
    setState('sending');
    const report = {
      page: location.pathname,
      match: match.name,
      time: Math.round((video?.currentTime ?? 0) * 100) / 100,
      rally: rally?.i ?? null,
      clip: clip ? { time: clip.time, type: clip.type ?? null, team: clip.team ?? null, player: clip.player ?? null, name: clip.name ?? null } : null,
      shown,
      kind,
      comment: comment.trim(),
    };
    try {
      const response = await fetch(match.feedback!, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(report) });
      setState(response.ok ? 'sent' : 'failed');
      if (response.ok) {
        setComment('');
        setOpen(false);
      }
    } catch {
      setState('failed');
    }
  };

  const toggle = () => {
    if (!open) {
      video?.pause();
      setState('idle');
    }
    setOpen(!open);
  };
  return (
    <div className={inline ? 'relative shrink-0' : 'absolute top-2 right-2 z-10 flex max-w-[calc(100%-1rem)] flex-col items-end gap-2'}>
      <button
        type="button"
        aria-expanded={open}
        title={t('feedback.open')}
        onClick={toggle}
        className={
          inline
            ? 'inline-flex h-8 items-center gap-1.5 rounded-md border bg-card px-2.5 text-xs font-medium shadow-xs outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50'
            : 'inline-flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm outline-none hover:bg-black/75 focus-visible:ring-3 focus-visible:ring-white/60'
        }
      >
        <Flag aria-hidden className={inline ? 'size-3.5' : 'size-4'} />
        <span role="status">{state === 'sent' ? t('feedback.thanksShort') : t('feedback.button')}</span>
      </button>
      {open && (
        <form
          onSubmit={(e) => void send(e)}
          className={cn(
            'grid w-80 gap-3 rounded-lg border bg-card p-3 text-sm font-normal text-card-foreground shadow-lg',
            inline ? 'absolute top-full right-0 z-20 mt-2 max-w-[calc(100vw-2rem)]' : 'max-w-full',
          )}
        >
          <fieldset className="grid gap-1.5">
            <legend className="mb-1 font-medium">{t('feedback.what')}</legend>
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
            <Button type="button" variant="outline" size="sm" className="bg-card" onClick={() => setOpen(false)}>
              {t('feedback.cancel')}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
