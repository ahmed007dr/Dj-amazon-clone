import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router-dom';

import { Spinner } from '@/shared/ui/Spinner';
import { StateMessage } from '@/shared/ui/StateMessage';

import { useAuth } from '../useAuth';

/**
 * The route guard.
 *
 * ⚠️  **This is not security.** The server refuses regardless of this component.
 *
 *     Its value is that the user sees a login screen instead of a screen full of 403 messages.
 *
 * ⚠️  It waits for the session restore to finish before judging.
 *
 *     Without that, every returning user is thrown back to the login page at the
 *     moment the app boots — because `user` has not arrived yet, even though
 *     their session is perfectly valid.
 */
export function RequireAuth({
  children,
  allow,
}: {
  children: ReactNode;
  /** An extra check on the account — an admin, for instance. */
  allow?: (user: NonNullable<ReturnType<typeof useAuth>['user']>) => boolean;
}) {
  const { t } = useTranslation();
  const { user, isRestoring } = useAuth();
  const location = useLocation();

  if (isRestoring) return <Spinner />;

  if (!user) {
    // ⚠️  The destination is saved so they return to it after logging in rather than starting at the home page
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (allow && !allow(user)) {
    return <StateMessage icon="⚿" title={t('state.forbiddenTitle')} />;
  }

  return children;
}
