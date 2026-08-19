import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@/styles/tokens.css';
import '@/styles/base.css';
import '@/styles/layout.css';

// ⚠️  Before any component — `i18n` must be initialised by the first render
import '@/shared/i18n/config';

import { Providers } from './app/Providers';
import { AppRouter } from './app/router';

const container = document.getElementById('root');
if (!container) throw new Error('عنصر #root غير موجود');

createRoot(container).render(
  <StrictMode>
    <Providers>
      <AppRouter />
    </Providers>
  </StrictMode>,
);
