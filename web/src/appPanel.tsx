import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/i18n';
import { ServerTab } from '@/components/ServerTab';
import { Setup } from '@/components/Setup/Setup';
import { TooltipProvider } from '@/components/ui/tooltip';

/** The app's screens in `element`, on the review server's list of the matches. */
export function mount(element: HTMLElement) {
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <Setup />
      </TooltipProvider>
    </StrictMode>,
  );
}

/** The "Serveur" tab's screen in `element`. */
export function mountServer(element: HTMLElement) {
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <ServerTab />
      </TooltipProvider>
    </StrictMode>,
  );
}
