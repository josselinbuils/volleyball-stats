import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import '@/i18n';
import { App } from '@/App';
import { Review } from '@/components/Review/Review';
import { applyTheme } from '@/helpers/theme';
import { match, teams } from '@/lib/match';
import { review } from '@/lib/review';

applyTheme(teams, match.brand);
// The review server adds review.js to the match page: the page turns into the review.
createRoot(document.getElementById('root')!).render(<StrictMode>{review ? <Review {...review} /> : <App />}</StrictMode>);
