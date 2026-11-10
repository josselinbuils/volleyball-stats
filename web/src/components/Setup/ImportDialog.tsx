import { useEffect, useState, type FormEvent } from 'react';
import { HardDrive, Folder, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { clock, useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import { suggestedTeams, type ClubState } from '@/components/helpers/club';
import { importError, parseTime, validName, type Recording, type Source } from './helpers/setup';

interface TeamField {
  name: string;
  colour: string | null;
}

/** A match imported from the camera's card or a folder: where, which recording, the teams, the day. The copy, then the
 * court's search, run in the background. */
export function ImportDialog({ onClose }: { onClose: (started: boolean) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [path, setPath] = useState('');
  const [scanning, setScanning] = useState(false);
  const [found, setFound] = useState<{ source: string; recordings: Recording[] } | null>(null);
  const [recording, setRecording] = useState(0);
  const [teams, setTeams] = useState<[TeamField, TeamField]>([
    { name: '', colour: null },
    { name: '', colour: null },
  ]);
  const [date, setDate] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [suggested, setSuggested] = useState<string[]>([]);
  useEffect(() => {
    void call<ClubState>('club').then((r) => {
      if (r.ok) {
        setSuggested(suggestedTeams(r));
      }
    });
  }, []);
  useEffect(() => {
    fetch('/app/sources')
      .then((r) => (r.ok ? (r.json() as Promise<Source[]>) : []))
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  const refuse = (error: string | undefined) => {
    const [key, values] = importError(error);
    setError(t(key, values));
  };
  const scan = async (source: string, drive?: string) => {
    setPath(source);
    setScanning(true);
    setError(null);
    setFound(null);
    // A Windows drive is mounted first (WSL2).
    const mounted = drive ? await call('mount', { drive }) : null;
    if (mounted && !mounted.ok) {
      setScanning(false);
      refuse(mounted.error);
      return;
    }
    const r = await call<{ source: string; recordings: Recording[] }>('scan', { source });
    setScanning(false);
    if (!r.ok) {
      refuse(r.error);
      return;
    }
    setFound(r);
    setRecording(r.recordings.length - 1);
    setDate(r.recordings[r.recordings.length - 1].date);
  };

  const times = [from, to].map((v) => (v.trim() ? parseTime(v) : 0));
  const ready = found && teams.every((team) => validName(team.name)) && times.every((v) => v !== null) && !!date;
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
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('app.import.title')}</DialogTitle>
          <DialogDescription>{t('app.import.where')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {sources?.map((source) => (
            <Button key={source.path} variant={path === source.path ? 'secondary' : 'outline'} className="justify-start" onClick={() => void scan(source.path, source.drive)}>
              {source.card ? <HardDrive aria-hidden /> : <Folder aria-hidden />}
              <span className="truncate">{source.card ? t('app.import.card', { name: source.name }) : source.name}</span>
            </Button>
          ))}
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (path.trim()) {
                void scan(path.trim());
              }
            }}
          >
            <input aria-label={t('app.import.path')} placeholder={t('app.import.path')} value={path} onChange={(e) => setPath(e.target.value)} className={cn(INPUT, 'min-w-0 flex-1 text-sm')} />
            <Button type="submit" variant="outline" disabled={!path.trim() || scanning}>
              <Search aria-hidden />
              {t('app.import.look')}
            </Button>
          </form>
          {scanning && <p className="text-muted-foreground">{t('app.import.scanning')}</p>}
        </div>
        {found && (
          <form onSubmit={submit} className="grid gap-4">
            {found.recordings.length > 1 && (
              <fieldset className="grid gap-1.5">
                <legend className="mb-1.5 font-medium">{t('app.import.recording')}</legend>
                {found.recordings.map((r, k) => (
                  <label key={k} className="flex items-center gap-2">
                    <input type="radio" name="recording" checked={recording === k} onChange={() => (setRecording(k), setDate(r.date))} />
                    <span className="tabular-nums">
                      {r.start ? f.when(r.start) : t('app.import.recordingN', { n: k + 1 })} · {clock(r.duration)}
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
            {teams.map((team, k) => (
              <div key={k} className="grid gap-1">
                <label htmlFor={`team-${k}`} className="font-medium">
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
            <datalist id="team-names">
              {suggested.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
            <label className="grid gap-1 font-medium">
              {t('app.import.date')}
              <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} className={cn(INPUT, 'w-fit')} />
            </label>
            <details className="grid gap-2">
              <summary className="cursor-pointer text-muted-foreground">{t('app.import.cut')}</summary>
              <div className="mt-2 flex flex-wrap gap-3">
                {(
                  [
                    ['from', from, setFrom],
                    ['to', to, setTo],
                  ] as const
                ).map(([key, value, set], k) => (
                  <label key={key} className="grid gap-1">
                    {t(`app.import.${key}`)}
                    <input placeholder="0:00" value={value} aria-invalid={times[k] === null} onChange={(e) => set(e.target.value)} className={cn(INPUT, 'w-28 tabular-nums')} />
                  </label>
                ))}
              </div>
            </details>
            <Button type="submit" disabled={!ready || sending}>
              {t('app.import.start')}
            </Button>
          </form>
        )}
        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
