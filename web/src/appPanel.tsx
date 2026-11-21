import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/i18n';
import { addSheet } from '@/lib/sheet';
import { AppMatches } from '@/components/AppMatches';
import type { MatchList } from '@/components/Matches';
import { TooltipProvider } from '@/components/ui/tooltip';

/** The review server's list of the matches in `element`, the app's screens with it (`AppMatches`): the online list never loads them. */
export function mountList(element: HTMLElement, list: MatchList) {
  addSheet();
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <AppMatches {...list} />
      </TooltipProvider>
    </StrictMode>,
  );
}
