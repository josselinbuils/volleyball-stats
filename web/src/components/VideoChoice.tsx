import { useEffect, useId, useState, type FormEvent } from 'react';
import { Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { match } from '@/lib/match';

// The copy with the video opens to the cookie COOKIE holding the SHA-256 of SALT and its password: the
// server keeps the same fingerprint, never the password, and sends the visitor back with ?video=denied
// without it. Kept for a year, on this match's folder.
const COOKIE = 'video_key';
const SALT = 'volleyball:';
const SKIPPED = 'video-skipped';
const ASK = 'video-choice';

const folder = () => location.pathname.replace(/index\.html$/, '');
const hasKey = () => document.cookie.split('; ').some((c) => c.startsWith(`${COOKIE}=`));
const setKey = (key: string | null) => {
  document.cookie = `${COOKIE}=${key ?? ''}; Path=${folder()}; Max-Age=${key ? 31536000 : 0}; Secure; SameSite=Lax`;
};

async function fingerprint(password: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(SALT + password));
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** Opens the choice, from a link to the copy with the video. */
export function askVideo(): void {
  window.dispatchEvent(new Event(ASK));
}

/** On the page without the video, the choice between it and the copy with the video behind a password,
 * asked on arrival unless the viewer chose to stay this visit, or skipped when this browser holds the
 * password already (it goes there at once). */
export function VideoChoice() {
  const { t } = useTranslation();
  const title = useId();
  const page = match.videoPage;
  const denied = new URLSearchParams(location.search).get('video') === 'denied';
  const [open, setOpen] = useState(() => !!page && (denied || (!hasKey() && sessionStorageGet(SKIPPED) !== folder())));
  const [password, setPassword] = useState('');
  const [state, setState] = useState<'idle' | 'checking' | 'wrong' | 'changed'>(() => (denied && hasKey() ? 'changed' : 'idle'));
  useEffect(() => {
    if (!page) {
      return;
    }
    if (denied) {
      // A key the server refused: the password changed.
      setKey(null);
      history.replaceState(null, '', folder());
    } else if (hasKey()) {
      location.replace(page);
    }
    const ask = () => setOpen(true);
    window.addEventListener(ASK, ask);
    return () => window.removeEventListener(ASK, ask);
  }, [page, denied]);
  useEffect(() => {
    if (!open) {
      return;
    }
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && stay();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  const stay = () => {
    sessionStorageSet(SKIPPED, folder());
    setOpen(false);
  };
  const enter = async (event: FormEvent) => {
    event.preventDefault();
    if (!page || !password) {
      return;
    }
    setState('checking');
    setKey(await fingerprint(password));
    const found = await fetch(page, { method: 'HEAD', cache: 'no-store', redirect: 'manual' }).catch(() => null);
    if (found?.ok) {
      location.href = page;
      return;
    }
    setKey(null);
    setState('wrong');
  };
  if (!page || !open) {
    return null;
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby={title} className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4">
      <form onSubmit={(e) => void enter(e)} className="grid w-full max-w-sm gap-4 rounded-xl border bg-card p-5 text-card-foreground shadow-xl">
        <h2 id={title} className="m-0 text-lg font-semibold">
          {t('videoChoice.title')}
        </h2>
        <p className="m-0 text-sm text-muted-foreground">{t('videoChoice.text')}</p>
        <label className="grid gap-1 text-sm font-medium">
          {t('videoChoice.password')}
          <input
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-9 rounded-md border border-input bg-transparent px-2.5 text-base font-normal shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        </label>
        {(state === 'wrong' || state === 'changed') && (
          <p role="alert" className="m-0 text-sm text-destructive">
            {t(`videoChoice.${state}`)}
          </p>
        )}
        <div className="grid gap-2">
          <Button type="submit" disabled={!password || state === 'checking'}>
            <Lock aria-hidden />
            {t(state === 'checking' ? 'videoChoice.checking' : 'videoChoice.video')}
          </Button>
          <Button type="button" variant="outline" className="bg-card" onClick={stay}>
            {t('videoChoice.without')}
          </Button>
        </div>
      </form>
    </div>
  );
}

function sessionStorageGet(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function sessionStorageSet(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // The choice is asked again on the next visit.
  }
}
