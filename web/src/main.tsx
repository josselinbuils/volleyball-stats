import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import '@/i18n';
import { App } from '@/App';
import { TooltipProvider } from '@/components/ui/tooltip';
import { applyTheme } from '@/helpers/theme';
import { match, teams, versioned } from '@/lib/match';
import { keepPresence, reviewPreview } from '@/lib/appServer';

declare global {
  interface Window {
    VolleyReviewBundle?: { mount: (element: HTMLElement) => void; mountTasks: (element: HTMLElement) => void };
  }
}

applyTheme(teams, match.club);
keepPresence();
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
  // On the app's preview of the page, its tasks too, from the review's script.
  if (reviewPreview()) {
    const tasks = document.createElement('div');
    document.body.append(tasks);
    const script = document.createElement('script');
    script.src = versioned('review-app.js');
    script.onload = () => window.VolleyReviewBundle?.mountTasks(tasks);
    document.head.append(script);
  }
}
