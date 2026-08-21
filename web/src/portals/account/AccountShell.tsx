import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/features/auth/useAuth';
import { Alert } from '@/shared/ui/Alert';

import { AccountNav } from './components/AccountNav';

import './AccountShell.css';

/**
 * The account portal shell — inside the store shell rather than replacing it.
 *
 * ⚠️  The customer moves between their account and the store constantly: a
 *     different header makes them feel they have left the site, and takes the
 *     cart out of their sight at the very moment they want to complete a purchase.
 */
export function AccountShell() {
  const { t } = useTranslation();
  const { user } = useAuth();

  return (
    <div className="container account-shell">
      <aside className="account-shell__side">
        <AccountNav />
      </aside>

      <div className="account-shell__content">
        {/* ⚠️  The verification status is shown on every account screen rather than on
            one page: a professional awaiting review sees retail prices and
            assumes the system is broken. */}
        {user?.verification_status === 'PENDING' ? (
          <Alert tone="info">{t('auth.awaitingVerification')}</Alert>
        ) : null}
        {user?.verification_status === 'REJECTED' ? (
          <Alert tone="warning">{t('account.verificationRejected')}</Alert>
        ) : null}

        <Outlet />
      </div>
    </div>
  );
}
