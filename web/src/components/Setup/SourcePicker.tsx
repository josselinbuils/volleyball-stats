import { useEffect, useState } from 'react';
import { FileVideo, Folder, FolderOpen, HardDrive, LoaderCircle, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import type { Recording, Source } from './helpers/setup';

/** What a source read gives: its path (several for videos picked together) and its recordings. */
export interface Found {
  source: string | string[];
  recordings: Recording[];
}

/** Where the videos are: the camera's card or a folder found, videos or a folder picked in the system's file window, or
 * a path typed. Read, its recordings go to `onFound`; a refusal's code to `onError`. */
export function SourcePicker({ onStart, onFound, onError }: { onStart: () => void; onFound: (found: Found) => void; onError: (error: string | undefined) => void }) {
  const { t } = useTranslation();
  const [sources, setSources] = useState<Source[] | null>(null);
  // Whether this machine can open its own file window, and whether it is open.
  const [picker, setPicker] = useState(false);
  const [picking, setPicking] = useState(false);
  const [path, setPath] = useState('');
  // The folder being read: a listed one's path, or the one typed.
  const [scanning, setScanning] = useState<string | null>(null);
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

  const scan = async (source: string | string[], drive?: string, from = typeof source === 'string' ? source : 'pick') => {
    if (typeof source === 'string') {
      setPath(source);
    }
    setScanning(from);
    onStart();
    // A Windows drive is mounted first (WSL2).
    const mounted = drive ? await call('mount', { drive }) : null;
    if (mounted && !mounted.ok) {
      setScanning(null);
      onError(mounted.error);
      return;
    }
    const r = await call<Found>('scan', { source });
    setScanning(null);
    if (r.ok) {
      onFound(r);
    } else {
      onError(r.error);
    }
  };

  /** Videos (several at once) or a folder picked in the system's own file window. */
  const pick = async (what: 'files' | 'folder') => {
    setScanning(what);
    setPicking(true);
    onStart();
    const r = await call<{ source: string[] | null }>('pick', { what });
    setPicking(false);
    if (r.ok && r.source) {
      await scan(r.source.length === 1 ? r.source[0] : r.source, undefined, what);
      return;
    }
    setScanning(null);
    if (!r.ok) {
      onError(r.error);
    }
  };

  return (
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
        <input aria-label={t('app.import.path')} placeholder={t('app.import.path')} value={path} onChange={(e) => setPath(e.target.value)} className={cn(INPUT, 'w-0 min-w-0 flex-1 text-sm')} />
        <Button type="submit" variant="outline" busy={scanning === 'typed'} disabled={!path.trim() || !!scanning}>
          <Search aria-hidden />
          {t('app.import.look')}
        </Button>
      </form>
      {!!scanning && !picking && <p className="text-muted-foreground sm:col-span-2">{t('app.import.scanning')}</p>}
    </div>
  );
}
