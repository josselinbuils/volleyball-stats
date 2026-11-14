import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/i18n';
import { ProgressTab } from '@/components/Progress/Progress';
import { SiteTab } from '@/components/SiteTab';
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

/** The "Site" tab's screen in `element`. */
export function mountSite(element: HTMLElement) {
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <SiteTab />
      </TooltipProvider>
    </StrictMode>,
  );
}

/** The "Progrès" tab's screen in `element`. */
export function mountProgress(element: HTMLElement) {
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <ProgressTab />
      </TooltipProvider>
    </StrictMode>,
  );
}
