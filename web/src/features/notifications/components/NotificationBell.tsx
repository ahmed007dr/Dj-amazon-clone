import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';

import { useUnreadCount } from '../hooks';

import './NotificationBell.css';

/**
 * The notifications bell.
 *
 * ⚠️  **It never appears to a visitor.**
 *
 *     The counter endpoint requires a token; showing the bell to an
 *     unregistered user means a repeated `401` every minute, each one
 *     triggering an attempt to refresh a session that does not exist.
 *
 * ⚠️  And a link rather than a button with a dropdown: a dropdown needs focus
 *     management, a keyboard trap and closing on an outside click — all of
 *     which are built once on the full screen instead of in two copies that drift apart.
 */
export function NotificationBell() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const { data } = useUnreadCount(user !== null);

  if (!user) return null;

  const unread = data?.unread ?? 0;

  return (
    <Link
      to="/account/notifications"
      className="notification-bell"
      aria-label={t('notifications.title')}
    >
      <span className="notification-bell__icon" aria-hidden>
        ✉
      </span>

      {/* ⚠️  Zero is not shown — "0" reads as a disabled element rather than "nothing new". */}
      {unread > 0 ? (
        <span className="notification-bell__count" aria-hidden>
          {unread > 99 ? '99+' : unread}
        </span>
      ) : null}

      <span className="visually-hidden">{t('notifications.unreadCount', { count: unread })}</span>
    </Link>
  );
}
