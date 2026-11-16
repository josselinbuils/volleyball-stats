export const APP_NAME = 'Volleyball Stats';

/** Whether the page comes from the app's own server, on this machine (never the hosted pages). */
export function onAppServer(host = location.hostname): boolean {
  return host === '127.0.0.1' || host === 'localhost';
}

/** Whether this is the match page the review server shows at `/page` (by any address, "Réseau local" included):
 * a hosted page is never there. */
export function reviewPreview(path = location.pathname): boolean {
  return path === '/page';
}

/** A hosted match page's list of matches, where its build put one (`matches.link_list`); from disk, its index.html. */
export function listAddress(up: string | null | undefined = document.querySelector<HTMLMetaElement>('meta[name="list"]')?.content, protocol = location.protocol): string | null {
  return up ? (protocol === 'file:' ? `${up}index.html` : up) : null;
}

/** A page's title, the app's name after it in the app's own window. */
export function windowTitle(title: string, host = location.hostname): string {
  return onAppServer(host) ? `${title} – ${APP_NAME}` : title;
}

const ALIVE_MS = 30_000;

/** On the app's server: tells it this page is open, then that it goes, for `stats` to stop once its last window closes
 * (presence.py). A reload or another match's review leaves and comes back at once. */
export function keepPresence(host = location.hostname) {
  if (!onAppServer(host)) {
    return;
  }
  const body = JSON.stringify({ id: `${Date.now()}-${Math.random().toString(36).slice(2)}` });
  const alive = () => void fetch('/app/alive', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }).catch(() => {});
  alive();
  setInterval(alive, ALIVE_MS);
  // Back from the browser's page cache, the page is open again.
  window.addEventListener('pageshow', (event) => event.persisted && alive());
  window.addEventListener('pagehide', () => navigator.sendBeacon('/app/leaving', new Blob([body], { type: 'application/json' })));
}
