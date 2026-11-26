import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { clock, useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import type { Explained } from '@/lib/errors';
import { RecordingPlayer } from './RecordingPlayer';
import { SourcePicker, type Found } from './SourcePicker';
import { suggestedTeams, type ClubState } from '@/components/helpers/club';
import { NET_RANGE, importError, parseTime, validName } from './helpers/setup';

interface TeamField {
  name: string;
  colour: string | null;
}

/** A match imported from the camera's card, a folder or a video picked in the system's file window: where, which recording, the teams, the day. The copy, then the
 * court's search, run in the background. */
export function ImportDialog({ onClose }: { onClose: (started: boolean) => void }) {
  const { t, i18n } = useTranslation();
  const metres = (x: number) => x.toLocaleString(i18n.language, { maximumFractionDigits: 2 });
  const f = useFormat();
  const [found, setFound] = useState<Found | null>(null);
  const [recording, setRecording] = useState(0);
  const [teams, setTeams] = useState<[TeamField, TeamField]>([
    { name: '', colour: null },
    { name: '', colour: null },
  ]);
  const [date, setDate] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [net, setNet] = useState('');
  // The player's time, following the last one typed in the cut's fields.
  const [previewAt, setPreviewAt] = useState(0);
  const [error, setError] = useState<Explained | null>(null);
  const [sending, setSending] = useState(false);
  const [suggested, setSuggested] = useState<string[]>([]);
  useEffect(() => {
    void call<ClubState>('club').then((r) => {
      if (r.ok) {
        setSuggested(suggestedTeams(r));
        setNet((typed) => typed || metres(r.net));
      }
    });
  }, []);
  const refuse = (error: string | undefined) => {
    const [key, values, detail] = importError(error);
    // Only a failure the app does not name may tell more in its log.
    setError({ text: t(key, values), detail: detail ?? null, log: key === 'app.import.failed' });
  };
  const read = (r: Found) => {
    setFound(r);
    setRecording(r.recordings.length - 1);
    setDate(r.recordings[r.recordings.length - 1].date);
    setFrom('');
    setTo('');
    setPreviewAt(0);
  };

  const times = [from, to].map((v) => (v.trim() ? parseTime(v) : 0));
  const netM = Number(net.replace(',', '.'));
  const netOk = net.trim() !== '' && netM >= NET_RANGE[0] && netM <= NET_RANGE[1];
  const ready = found && teams.every((team) => validName(team.name)) && times.every((v) => v !== null) && !!date && netOk;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready || sending) {
      return;
    }
    setSending(true);
    setError(null);
    const r = await call('import', {
      source: found.source,
      recording: recording + 1,
      teams: teams.map((team) => ({ name: team.name.trim(), colour: team.colour })),
      date,
      net: netM,
      from: from.trim() || null,
      to: to.trim() || null,
    });
    setSending(false);
    if (r.ok) {
      onClose(true);
    } else {
      refuse(r.error);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose(false)}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('app.import.title')}</DialogTitle>
          <DialogDescription>{t('app.import.where')}</DialogDescription>
        </DialogHeader>
        <SourcePicker onStart={() => (setError(null), setFound(null))} onFound={read} onError={refuse} />
        {found && (
          <form onSubmit={submit} className="grid gap-4">
            {found.recordings.length > 1 && (
              <fieldset className="grid gap-1.5">
                <legend className="mb-1.5 font-medium">{t('app.import.recording')}</legend>
                {found.recordings.map((r, k) => (
                  <label key={k} className="flex items-center gap-2">
                    <input type="radio" name="recording" checked={recording === k} onChange={() => (setRecording(k), setDate(r.date), setFrom(''), setTo(''), setPreviewAt(0))} />
                    <span className="tabular-nums">
                      {r.start ? f.when(r.start) : t('app.import.recordingN', { n: k + 1 })} · {clock(r.duration)}
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            <RecordingPlayer
              key={recording}
              source={found.source}
              recording={recording + 1}
              chapters={found.recordings[recording].chapters}
              at={previewAt}
              from={from.trim() ? times[0] : null}
              to={to.trim() ? times[1] : null}
              onPick={(key, seconds) => (key === 'from' ? setFrom : setTo)(clock(seconds))}
            />
            <div className="flex flex-wrap gap-3">
              {(
                [
                  ['from', from, setFrom],
                  ['to', to, setTo],
                ] as const
              ).map(([key, value, set], k) => (
                <label key={key} className="grid gap-1">
                  {t(`app.import.${key}`)}
                  <input
                    placeholder={key === 'from' ? '0:00' : clock(found.recordings[recording].duration)}
                    value={value}
                    aria-invalid={times[k] === null}
                    onChange={(e) => {
                      set(e.target.value);
                      const typed = parseTime(e.target.value);
                      if (typed !== null) {
                        setPreviewAt(Math.min(typed, found.recordings[recording].duration));
                      }
                    }}
                    className={cn(INPUT, 'w-28 tabular-nums')}
                  />
                </label>
              ))}
            </div>
            <fieldset className="grid gap-1.5">
              <legend className="mb-1.5 font-medium">{t('app.import.sides')}</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                {teams.map((team, k) => (
                  <div key={k} className="grid gap-1">
                    <label htmlFor={`team-${k}`} className={cn('text-sm text-muted-foreground', k === 1 && 'sm:text-right')}>
                      {t(k === 0 ? 'app.import.left' : 'app.import.right')}
                    </label>
                    <div className="flex gap-2">
                      <input
                        id={`team-${k}`}
                        list="team-names"
                        autoComplete="off"
                        required
                        value={team.name}
                        aria-invalid={team.name !== '' && !validName(team.name)}
                        onChange={(e) => setTeams((all) => all.map((x, j) => (j === k ? { ...x, name: e.target.value } : x)) as [TeamField, TeamField])}
                        className={cn(INPUT, 'min-w-0 flex-1')}
                      />
                      <input
                        type="color"
                        aria-label={t('app.import.colour')}
                        value={team.colour ?? '#888888'}
                        onChange={(e) => setTeams((all) => all.map((x, j) => (j === k ? { ...x, colour: e.target.value } : x)) as [TeamField, TeamField])}
                        className={cn('h-9 w-12 shrink-0 cursor-pointer rounded-md border border-input bg-transparent p-1', !team.colour && 'opacity-50')}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </fieldset>
            <datalist id="team-names">
              {suggested.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
            <div className="flex flex-wrap gap-3">
              <label className="grid gap-1 font-medium">
                {t('app.import.date')}
                <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} className={cn(INPUT, 'w-fit')} />
              </label>
              <label className="grid gap-1 font-medium">
                {t('app.import.net')}
                <span className="flex items-center gap-2 font-normal">
                  <input
                    inputMode="decimal"
                    required
                    placeholder={metres(2.43)}
                    value={net}
                    aria-invalid={net.trim() !== '' && !netOk}
                    onChange={(e) => setNet(e.target.value)}
                    className={cn(INPUT, 'w-20 tabular-nums')}
                  />
                  m
                </span>
              </label>
            </div>
            <Button type="submit" busy={sending} disabled={!ready}>
              {t('app.import.start')}
            </Button>
          </form>
        )}
        {error && <ErrorNote {...error} />}
      </DialogContent>
    </Dialog>
  );
}
