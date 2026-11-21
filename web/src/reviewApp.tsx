import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/i18n';
import { addSheet } from '@/lib/sheet';
import { Tasks } from '@/components/Tasks';
import { Review } from '@/components/Review/Review';
import { TooltipProvider } from '@/components/ui/tooltip';
import { review } from '@/lib/review';

/** The review in `element`, from the review.js the review server adds to the page. */
export function mount(element: HTMLElement) {
  if (!review) {
    return;
  }
  addSheet();
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <Review {...review} />
      </TooltipProvider>
    </StrictMode>,
  );
}

/** The app's tasks in `element`, on its preview of the match page (`/page`): the online page never loads them. */
export function mountTasks(element: HTMLElement) {
  addSheet();
  createRoot(element).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <Tasks />
      </TooltipProvider>
    </StrictMode>,
  );
}
