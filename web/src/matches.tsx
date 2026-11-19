import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import '@/i18n';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Matches, type MatchList } from '@/components/Matches';
import { applyTheme } from '@/helpers/theme';
import { keepPresence } from '@/lib/appServer';
import { linkedKey, setVideoKey } from '@/lib/videoPassword';

declare global {
  interface Window {
    MATCHES: MatchList;
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
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TooltipProvider delayDuration={200}>
      <Matches {...window.MATCHES} />
    </TooltipProvider>
  </StrictMode>,
);
