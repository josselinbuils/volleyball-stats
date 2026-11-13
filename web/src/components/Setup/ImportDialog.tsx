import { useEffect, useState, type FormEvent } from 'react';
import { FileVideo, Folder, FolderOpen, HardDrive, LoaderCircle, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { clock, useFormat } from '@/lib/format';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import { RecordingPlayer } from './RecordingPlayer';
import { suggestedTeams, type ClubState } from '@/components/helpers/club';
import { importError, parseTime, validName, type Recording, type Source } from './helpers/setup';

interface TeamField {
  name: string;
  colour: string | null;
}

/** A match imported from the camera's card, a folder or a video picked in the system's file window: where, which recording, the teams, the day. The copy, then the
 * court's search, run in the background. */
export function ImportDialog({ onClose }: { onClose: (started: boolean) => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [sources, setSources] = useState<Source[] | null>(null);
  // Whether this machine can open its own file window, and whether it is open.
  const [picker, setPicker] = useState(false);
  const [picking, setPicking] = useState(false);
  const [path, setPath] = useState('');
  // The folder being read: a listed one's path, or the one typed.
  const [scanning, setScanning] = useState<string | null>(null);
  const [found, setFound] = useState<{ source: string | string[]; recordings: Recording[] } | null>(null);
  const [recording, setRecording] = useState(0);
  const [teams, setTeams] = useState<[TeamField, TeamField]>([
    { name: '', colour: null },
    { name: '', colour: null },
  ]);
  const [date, setDate] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  // The player's time, following the last one typed in the cut's fields.
  const [previewAt, setPreviewAt] = useState(0);
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
    void Promise.all([
      fetch('/app/sources')
        .then((r) => (r.ok ? (r.json() as Promise<Source[]>) : []))
        .catch(() => [] as Source[]),
      call<{ available: boolean }>('picker'),
    ]).then(([found, own]) => {
      setPicker(own.ok && own.available);
      setSources(found);
    });
  }, []);

  const refuse = (error: string | undefined) => {
    const [key, values] = importError(error);
    setError(t(key, values));
  };
  const scan = async (source: string | string[], drive?: string, from = typeof source === 'string' ? source : 'pick') => {
    if (typeof source === 'string') {
      setPath(source);
    }
    setScanning(from);
    setError(null);
    setFound(null);
    // A Windows drive is mounted first (WSL2).
    const mounted = drive ? await call('mount', { drive }) : null;
    if (mounted && !mounted.ok) {
      setScanning(null);
      refuse(mounted.error);
      return;
    }
    const r = await call<{ source: string | string[]; recordings: Recording[] }>('scan', { source });
    setScanning(null);
    if (!r.ok) {
      refuse(r.error);
      return;
    }
    setFound(r);
    setRecording(r.recordings.length - 1);
    setDate(r.recordings[r.recordings.length - 1].date);
    setFrom('');
    setTo('');
    setPreviewAt(0);
  };

  /** Videos (several at once) or a folder picked in the system's own file window. */
  const pick = async (what: 'files' | 'folder') => {
    setScanning(what);
    setPicking(true);
    setError(null);
    const r = await call<{ source: string[] | null }>('pick', { what });
    setPicking(false);
    if (r.ok && r.source) {
      await scan(r.source.length === 1 ? r.source[0] : r.source, undefined, what);
      return;
    }
    setScanning(null);
    if (!r.ok) {
      refuse(r.error);
    }
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
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t('app.import.title')}</DialogTitle>
          <DialogDescription>{t('app.import.where')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 sm:grid-cols-2">
          {!sources && (
            <p role="status" className="flex items-center gap-2 text-muted-foreground">
              <LoaderCircle aria-hidden className="size-4 animate-spin" />
              {t('app.import.finding')}
            </p>
          )}
          {sources?.map((source) => (
            <Button
              key={source.path}
              variant={path === source.path ? 'secondary' : 'outline'}
              className="justify-start"
              busy={scanning === source.path}
              disabled={!!scanning}
              onClick={() => void scan(source.path, source.drive)}
            >
              {source.card ? <HardDrive aria-hidden /> : <Folder aria-hidden />}
              <span className="truncate">{source.card ? t('app.import.card', { name: source.name }) : source.name}</span>
            </Button>
          ))}
          {sources &&
            picker &&
            (['files', 'folder'] as const).map((what) => (
              <Button key={what} variant="outline" className="justify-start" busy={scanning === what} disabled={!!scanning} onClick={() => void pick(what)}>
                {what === 'files' ? <FileVideo aria-hidden /> : <FolderOpen aria-hidden />}
                {t(what === 'files' ? 'app.import.pickFiles' : 'app.import.pickFolder')}
              </Button>
            ))}
          <form
            className="flex gap-2 sm:col-span-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (path.trim()) {
                void scan(path.trim(), undefined, 'typed');
              }
            }}
          >
            <input aria-label={t('app.import.path')} placeholder={t('app.import.path')} value={path} onChange={(e) => setPath(e.target.value)} className={cn(INPUT, 'min-w-0 flex-1 text-sm')} />
            <Button type="submit" variant="outline" busy={scanning === 'typed'} disabled={!path.trim() || !!scanning}>
              <Search aria-hidden />
              {t('app.import.look')}
            </Button>
          </form>
          {!!scanning && !picking && <p className="text-muted-foreground sm:col-span-2">{t('app.import.scanning')}</p>}
        </div>
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
            <label className="grid gap-1 font-medium">
              {t('app.import.date')}
              <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} className={cn(INPUT, 'w-fit')} />
            </label>
            <Button type="submit" busy={sending} disabled={!ready}>
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
