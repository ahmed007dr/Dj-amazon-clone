import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/features/auth/useAuth';
import { useStudentVerificationEnforced } from '@/features/settings/publicConfig';
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
  const verificationEnforced = useStudentVerificationEnforced();

  return (
    <div className="container account-shell">
      <aside className="account-shell__side">
        <AccountNav />
      </aside>

      <div className="account-shell__content">
        {/* ⚠️  The verification status is shown on every account screen rather than on
            one page: a professional awaiting review sees retail prices and
            assumes the system is broken.

            ⚠️  …but only while verification is a requirement at all. With the switch
            off nothing waits on a review, so "under review" would be a notice about a
            process that does not exist (and the rejected one asks for a re-upload that
            changes nothing). */}
        {verificationEnforced && user?.verification_status === 'PENDING' ? (
          <Alert tone="info">{t('auth.awaitingVerification')}</Alert>
        ) : null}
        {verificationEnforced && user?.verification_status === 'REJECTED' ? (
          <Alert tone="warning">{t('account.verificationRejected')}</Alert>
        ) : null}

        <Outlet />
      </div>
    </div>
  );
}
