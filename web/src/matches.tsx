import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import '@/i18n';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Matches, type MatchList } from '@/components/Matches';
import { applyTheme } from '@/helpers/theme';

declare global {
  interface Window {
    MATCHES: MatchList;
  }
}

/** The list of the match pages of a site, from matches.js. */
applyTheme(null, window.MATCHES.brand);
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TooltipProvider delayDuration={200}>
      <Matches {...window.MATCHES} />
    </TooltipProvider>
  </StrictMode>,
);
