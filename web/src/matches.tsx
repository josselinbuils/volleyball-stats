import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import '@/i18n';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ListLoading } from '@/components/ListLoading';
import { Matches, type MatchList } from '@/components/Matches';
import { applyTheme } from '@/helpers/theme';
import { keepPresence } from '@/lib/appServer';
import { linkedKey, setVideoKey } from '@/lib/videoPassword';

declare global {
  interface Window {
    MATCHES: MatchList;
    VolleyAppBundle?: { mountList: (element: HTMLElement, list: MatchList) => void };
  }
}

/** The list of the match pages of a site, from matches.js. */
// A shared link's key: every match's video then opens without the password.
const linked = linkedKey();
if (linked) {
  setVideoKey(linked, location.pathname.replace(/[^/]*$/, ''));
}
applyTheme(null, window.MATCHES.club);
keepPresence();
const element = document.getElementById('root')!;
const root = createRoot(element);
root.render(
  <StrictMode>
    <TooltipProvider delayDuration={200}>{window.MATCHES.review ? <ListLoading /> : <Matches {...window.MATCHES} />}</TooltipProvider>
  </StrictMode>,
);
// The review server's list is the app's script's (app.js), which the online list never loads.
if (window.MATCHES.review) {
  const script = document.createElement('script');
  script.src = 'app.js';
  script.onload = () => {
    root.unmount();
    window.VolleyAppBundle?.mountList(element, window.MATCHES);
  };
  script.onerror = () =>
    root.render(
      <StrictMode>
        <ListLoading failed />
      </StrictMode>,
    );
  document.head.append(script);
}
