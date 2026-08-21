import { Outlet } from 'react-router-dom';

import { useMyEmployeeProfile } from '@/features/employees/api';
import { isApiError } from '@/shared/http/errors';
import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';
import { useTranslation } from 'react-i18next';

import { StaffHeader } from './components/StaffHeader';

import './StaffShell.css';

/**
 * The staff portal shell.
 *
 * ⚠️  **The profile is an entry condition, not a step inside the screen.**
 *
 *     Every endpoint on the server refuses to work without an active employee
 *     profile. Letting the screens open and then fail one by one gives the user
 *     four scattered error messages instead of one answer.
 *
 * ⚠️  And **a suspended employee is turned away here**, not at their first operation.
 *
 *     An employee whose service has ended while their token is still valid is
 *     the clearest possible hole; the server returns 403 on every endpoint, and
 *     the shell translates that into an intelligible message.
 */
export function StaffShell() {
  const { t } = useTranslation();
  const profile = useMyEmployeeProfile();

  if (profile.isPending) return <Spinner />;

  if (profile.error) {
    const forbidden = isApiError(profile.error) && profile.error.status === 403;

    return (
      <div className="staff-shell">
        <StaffHeader />
        <main className="staff-shell__body">
          <StateMessage
            icon="🔒"
            title={forbidden ? t('staff.noAccess') : t('staff.noProfile')}
            body={
              isApiError(profile.error)
                ? profile.error.displayMessage
                : t('state.errorTitle')
            }
          />
        </main>
      </div>
    );
  }

  return (
    <div className="staff-shell">
      <StaffHeader />
      <main className="staff-shell__body">
        <Outlet />
      </main>
    </div>
  );
}
