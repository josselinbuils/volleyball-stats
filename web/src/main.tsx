import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import '@/i18n';
import { App } from '@/App';
import { applyTheme } from '@/helpers/theme';
import { match, teams } from '@/lib/match';

applyTheme(teams, match.brand);
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
