import { useCallback, useEffect, useState } from 'react';
import { LoaderCircle, Wifi, WifiOff, Wrench } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';

interface Network {
  lan: boolean;
  /** The address to open on another device; null where the network does not reach it yet. */
  url: string | null;
  /** WSL's networking mode under Windows ("mirrored" once set up), null elsewhere. */
  wsl: string | null;
}

// The server starts again on a switch: asked again this often until it answers.
const BACK_MS = 700;
const TRIES = 30;

/** The review opened to the other devices of the local network, or not; the address to type there; under Windows, the
 * one setting it needs first (WSL sharing the computer's address, its firewall letting the port in). */
export function NetworkDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [network, setNetwork] = useState<Network | null>(null);
  const [error, setError] = useState<Explained | null>(null);
  const [running, setRunning] = useState<'switch' | 'windows' | null>(null);
  const [windowsDone, setWindowsDone] = useState(false);

  const read = useCallback(async () => {
    const found = await call<Network>('network');
    if (found.ok) {
      setNetwork(found);
    }
    return found.ok;
  }, []);
  useEffect(() => {
    void read().then((ok) => !ok && setError(explain(t, 'network')));
  }, [read, t]);

  const toggle = async () => {
    setRunning('switch');
    setError(null);
    const answer = await call<Network>('network', { on: !network?.lan });
    if (!answer.ok) {
      setError(explain(t, answer.error));
      setRunning(null);
      return;
    }
    // The server listens anew: its answer once it is back.
    for (let k = 0; k < TRIES; k += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, BACK_MS));
      if (await read()) {
        setRunning(null);
        return;
      }
    }
    setError(explain(t, 'network'));
    setRunning(null);
  };

  const setUpWindows = async () => {
    setRunning('windows');
    setError(null);
    const answer = await call<Network>('network', { action: 'windows' });
    if (answer.ok) {
      setWindowsDone(true);
    } else {
      setError(explain(t, answer.error));
    }
    setRunning(null);
  };

  const needsWindows = !!network?.wsl && network.wsl !== 'mirrored';
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('app.network.title')}</DialogTitle>
          <DialogDescription>{t('app.network.intro')}</DialogDescription>
        </DialogHeader>
        {!network && !error ? (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
            {t('app.network.reading')}
          </p>
        ) : (
          network && (
            <div className="grid gap-3">
              <Button className="justify-self-start" variant={network.lan ? 'outline' : 'default'} busy={running === 'switch'} disabled={!!running} onClick={() => void toggle()}>
                {network.lan ? <WifiOff aria-hidden /> : <Wifi aria-hidden />}
                {network.lan ? t('app.network.off') : t('app.network.on')}
              </Button>
              {network.lan && network.url && (
                <p className="m-0 grid gap-1">
                  {t('app.network.openOn')}
                  <code className="w-fit rounded-md bg-muted px-2 py-1 font-mono text-sm select-all">{network.url}</code>
                </p>
              )}
              {needsWindows &&
                (windowsDone ? (
                  <p role="status" className="m-0">
                    {t('app.network.restart')}
                  </p>
                ) : (
                  <div className="grid gap-2">
                    <p className="m-0">{t('app.network.windows')}</p>
                    <Button variant="outline" className="justify-self-start bg-card" busy={running === 'windows'} disabled={!!running} onClick={() => void setUpWindows()}>
                      <Wrench aria-hidden />
                      {t('app.network.setUp')}
                    </Button>
                  </div>
                ))}
            </div>
          )
        )}
        {error && <ErrorNote {...error} />}
      </DialogContent>
    </Dialog>
  );
}
