import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import '@/i18n';
import { App } from '@/App';
import { TooltipProvider } from '@/components/ui/tooltip';
import { applyTheme } from '@/helpers/theme';
import { match, teams, versioned } from '@/lib/match';

declare global {
  interface Window {
    VolleyReviewBundle?: { mount: (element: HTMLElement) => void };
  }
}

applyTheme(teams, match.brand);
const root = document.getElementById('root')!;
// The review server adds review.js to the match page: the page turns into the review, whose screens are a script of
// their own (review-app.js) that the page viewers open never loads.
if (window.REVIEW) {
  const script = document.createElement('script');
  script.src = versioned('review-app.js');
  script.onload = () => window.VolleyReviewBundle?.mount(root);
  document.head.append(script);
} else {
  createRoot(root).render(
    <StrictMode>
      <TooltipProvider delayDuration={200}>
        <App />
      </TooltipProvider>
    </StrictMode>,
  );
}
