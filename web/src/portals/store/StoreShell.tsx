import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { StoreFooter } from './components/StoreFooter';
import { StoreHeader } from './components/StoreHeader';

import './StoreShell.css';

/**
 * The store portal shell — composition only, no logic.
 *
 * ⚠️  The shell assembles the header, the footer and the content and does
 *     nothing else. Putting data fetching or permission logic here makes every
 *     page in the portal wait on it even when it does not need it.
 */
export function StoreShell() {
  const { t } = useTranslation();

  return (
    <div className="store-shell">
      {/* ⚠️  The skip link is the first focusable element — without it a keyboard
          user passes over every link in the header before every page. */}
      <a className="skip-link" href="#main">
        {t('common.skipToContent')}
      </a>

      <StoreHeader />

      <main id="main" className="store-shell__main">
        <Outlet />
      </main>

      <StoreFooter />
    </div>
  );
}
