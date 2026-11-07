import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/i18n';
import { Review } from '@/components/Review/Review';
import { TooltipProvider } from '@/components/ui/tooltip';
import { review } from '@/lib/review';

/** The review in `element`, from the review.js the review server adds to the page. */
export function mount(element: HTMLElement) {
  if (!review) {
    return;
  }
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <Review {...review} />
      </TooltipProvider>
    </StrictMode>,
  );
}
